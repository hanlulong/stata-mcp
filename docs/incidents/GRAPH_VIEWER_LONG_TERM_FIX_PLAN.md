# Graph Viewer Long-Term Fix Plan

**Related incident**: `docs/incidents/GRAPH_VIEWER_BLANK_PANEL.md`
**Scope**: Graph Viewer only
**Status**: Implemented in code, runtime validation pending
**Last updated**: 2026-04-19

## Summary

The long-term fix should move the Graph Viewer away from full-document webview reloads and toward a stable webview shell that is hydrated with structured graph state.

This is the right direction for three reasons:

1. The blank-panel issue appears on both macOS and Windows, so it is unlikely to be a purely platform-specific paint bug.
2. Current diagnostics show that the Graph Viewer page and images can load correctly inside the webview, which points to a webview lifecycle/state problem rather than a graph export problem.
3. The current graph state model has real correctness issues even when the panel is not blank, especially because Stata graph names such as `graph1` and `graph2` are reused across runs.

The recommended architecture is:

- stable Graph Viewer shell
- extension-side graph store keyed by ephemeral execution/batch/artifact identity, not graph name
- postMessage-based updates instead of repeated `webview.html = ...`
- batch-scoped temporary graph files with unique paths
- explicit execution/batch identity carried through extension, server, and worker code paths
- explicit runtime configuration for graph storage instead of inferring it from log-file-derived extension paths
- compatibility shims for browser mode and existing routes

This should be implemented in phases. The first phase should fix the viewer architecture without bundling every storage and transport change into one large patch.

## Implementation Status

The staged implementation described in this document has now been applied in code.

Implemented:

- Graph Viewer now uses a stable webview shell and `postMessage(...)` hydration instead of repeated full-document `webview.html` replacement.
- Extension-side graph state now uses `GraphStore` with current-batch semantics instead of the old `allGraphs` object keyed by reused Stata graph names.
- Graph artifacts now use execution-scoped, batch-scoped temporary storage with structured metadata including `executionId`, `batchId`, `artifactId`, `path`, and `browserPath`.
- The extension now passes an explicit graph storage root to the Python server via `STATA_MCP_GRAPHS_DIR`.
- Streaming and non-streaming execution paths now carry structured graph metadata so the extension no longer relies only on parsing textual `GRAPHS DETECTED` blocks.
- Browser mode now prefers explicit `browserPath` artifact routes while keeping the old logical-name route as fallback.
- Interactive Window graph rendering now consumes structured graph metadata when available.

Still required:

- Runtime validation on macOS, Windows, and Linux/Unix with real Stata executions.
- Regression checks for remote/webview environments such as Remote-SSH, code-server, or Codespaces.

## Goals

- Fix the VS Code Graph Viewer in a way that is stable across macOS, Windows, remote environments, and browser-proxied environments.
- Preserve Issue #54 behavior: `asWebviewUri`, `localResourceRoots`, and browser-mode `asExternalUri()` support for remote/code-server/Codespaces scenarios.
- Preserve browser mode.
- Preserve the Interactive Window graph behavior.
- Preserve graph auto-display and existing command flows.
- Remove correctness bugs in graph state handling.
- Make the graph viewer testable with extension-side unit tests.
- Make graph storage and startup behavior explicit and robust on macOS, Windows, and Linux/Unix.

## Non-Goals

- Rewriting the Data Viewer.
- Rewriting the Interactive Window in the same first patch.
- Replacing the current streaming transport in the same first patch.
- Changing the Stata-side graph detection method (`_gr_list`) unless separate evidence requires it.

## Current Architecture Review

### Extension-side graph state

Current graph state is held in:

- `src/extension.js`: `let graphViewerPanel = null;`
- `src/extension.js`: `let allGraphs = {};`

The current model has a structural flaw: `allGraphs` is keyed by `graph.name`, but Stata routinely reuses names like `graph1`, `graph2`, and `graph4` on later runs. This means later runs overwrite earlier artifacts logically, even before any viewer bug is considered.

### Pre-run clearing behavior

For `run_selection`, the extension currently does this before the new execution completes:

- clears `allGraphs`
- immediately redraws the Graph Viewer if the panel exists

This happens in `executeStataCode(...)` in `src/extension.js`.

This is a poor lifecycle design because:

- it triggers a full webview redraw before new results exist
- it makes the viewer state transiently empty by design
- it introduces extra webview churn during the most failure-prone part of the flow

### Full-document webview replacement

Current Graph Viewer rendering is driven by:

- `displayGraphsInVSCode(...)`
- `updateGraphViewerPanel(...)`
- `graphViewerPanel.webview.html = fullHtml`

The webview HTML is regenerated and reassigned every refresh. That means:

- the entire document is recreated
- CSS and JS are reloaded
- every image is reattached
- the panel lifecycle depends on repeated full webview navigation

Even if this were not the direct cause of the blank panel, it is an unnecessarily fragile design.

### File naming and storage

The Python server and worker currently export graphs to fixed names such as:

- `graph1.png`
- `graph2.png`

under a shared graphs directory rooted at either:

- `<extension_path>/graphs`
- `<temp>/stata_mcp_graphs`

Relevant code paths:

- `src/stata_mcp_server.py`: `detect_and_export_graphs`
- `src/stata_mcp_server.py`: `display_graphs_interactive`
- `src/stata_worker.py`: `detect_and_export_graphs_worker`

This creates several long-term problems:

- graph files are overwritten across runs
- graph identity is coupled to a reused display name
- browser mode relies on a route keyed by logical graph name instead of a stable artifact identifier
- the extension install directory is not the ideal long-term storage root

### Browser mode coupling

Browser mode currently opens:

- `/graphs/{graph_name}`

via:

- `displayGraphsInBrowser(...)` in `src/extension.js`
- `@app.get("/graphs/{graph_name}")` in `src/stata_mcp_server.py`

This is tightly coupled to the current fixed-name file layout. Any storage redesign that changes artifact naming must preserve this behavior or provide a compatibility path.

### Interactive Window coupling

The Interactive Window uses:

- `getGraphWebviewUri(interactivePanel.webview, g)`

and currently renders graph URLs inside its own webview. This means any storage-root change must preserve webview-readability for those paths. The Interactive Window should not be rewritten in phase 1, but it must remain compatible with the new storage model.

### Testing gap

The repository has Python tests and some diagnostic scripts, but there is no meaningful automated test coverage for Graph Viewer state management. `package.json` references JS test scripts that do not appear to exist in the current tree. That means graph-viewer lifecycle changes are currently under-tested by default.

This should be treated as a design constraint, not a documentation footnote. The long-term fix needs a real JS-side test entrypoint in the repository.

### Cross-platform coupling that should be removed

Today, graph storage is inferred from `extension_path`, and `extension_path` is inferred from the server log-file path during startup. That coupling is too implicit for a robust cross-platform design.

This is risky on all three platform families:

- macOS: app and workspace paths routinely include spaces, and temp paths may resolve through `/private`
- Windows: command-line quoting and trailing backslashes make path arguments fragile, especially when built as a single command string
- Linux/Unix: extension installs may live under remote, containerized, or read-only locations where install directories are the wrong place for mutable graph artifacts

The long-term design should make graph storage its own explicit runtime input.

## Target Design

## 1. Stable Graph Viewer Shell

Create the Graph Viewer panel once and set `webview.html` once.

After the panel is initialized:

- do not regenerate the whole HTML document for every graph update
- send graph snapshots into the webview with `webview.postMessage(...)`
- let `media/graph-viewer.js` render updates into the existing DOM

The Graph Viewer becomes a stable shell instead of a repeatedly recreated page.

## 2. Extension-Side Graph Store

Replace `allGraphs` with a proper store based on execution-scoped batches and artifacts.

Important semantic clarification:

- a batch is an internal container for one execution that produced graphs
- a batch is not a user-facing saved history concept
- graphs remain temporary by default
- the store should keep only the current batch, plus at most one prior batch transiently during safe handoff/cleanup if needed

Suggested model:

```text
GraphBatch
- batchId
- executionId
- source: run_selection | run_file
- createdAt
- graphs: GraphArtifact[]

GraphArtifact
- artifactId
- logicalName
- displayName
- filePath
- browserPath?        // optional server/browser route
- orderInBatch
```

Important properties:

- `batchId` is unique per execution batch
- `artifactId` is unique per graph artifact
- `logicalName` may repeat across batches
- `filePath` is the source of truth for local/webview rendering
- batch retention is intentionally short-lived by default

This solves the current key-collision problem.

## 3. Graph Viewer Controller

Move Graph Viewer lifecycle into a dedicated controller module.

Suggested responsibilities:

- own the panel instance
- own panel readiness state
- hold the last sent snapshot version
- serialize updates into a single render queue
- decide when to recreate the panel if the webview becomes unhealthy

Suggested API:

```text
GraphViewerController
- show(snapshot)
- clear()
- dispose()
- onReady()
- onApplied(version)
- recreateAndHydrateIfNeeded()
```

This keeps Graph Viewer lifecycle logic out of `src/extension.js` and makes it easier to test.

## 4. Explicit Webview Protocol

Use a structured protocol between extension host and webview:

```text
webview -> extension: ready
extension -> webview: hydrate { version, snapshot }
webview -> extension: applied { version }
webview -> extension: clearRequested
```

Recommended behavior:

- the extension does not assume the webview is ready until `ready` arrives
- if `hydrate(version)` is sent before readiness, it should be queued
- the webview applies only the latest version
- the extension can recreate the panel once if `applied(version)` never arrives

This is much safer than using `webview.html` as the update mechanism.

## 5. Batch-Scoped Graph Artifacts

Move exported graph files to unique per-batch paths.

Recommended storage shape:

```text
<graphs_root>/
  <batchId>/
    graph1.png
    graph2.png
    manifest.json
```

or equivalently:

```text
<graphs_root>/
  <artifactId>.png
```

Batch-scoped directories are easier to inspect manually and easier to clean up by batch.

Important semantic clarification:

- these directories are temporary cache artifacts, not user-owned saved output
- unique batch paths exist to isolate one execution from another
- they should be deleted aggressively

Recommended root:

- primary: extension-managed writable storage directory, preferably `globalStorageUri`
- fallback: temp directory

The extension should provide this root to the Python server and worker at startup. The worker already accepts a `graphs_dir` argument, so the architecture already has a place to inject this value.

Important review note:

- graph storage should become its own explicit server input
- it should not continue to be inferred indirectly from `extension_path` or log-file settings

Today, the server effectively derives graph storage from `extension_path`, and `extension_path` is itself tied to startup/log configuration. That coupling is too implicit for the long-term design.

### Storage root requirements

The chosen root must satisfy all of these:

- writable by the extension host and the Python server
- stable across runs in the same environment
- available in local and remote extension-host scenarios
- safe to expose through `webview.asWebviewUri(...)`
- safe to clean up without touching the extension install directory

`globalStorageUri` is the best primary candidate. Temp storage remains a necessary fallback.

## 5A. Explicit Execution and Batch Identity

The extension should generate an `executionId` for each run that can produce graphs.

That identity should flow through:

- extension execution request
- server execution handling
- worker execution handling in multi-session mode
- graph export paths
- graph metadata returned to the extension

Recommended relationship:

```text
executionId -> batchId -> artifactId
```

This improves both correctness and robustness:

- stale results can be rejected cleanly
- graph artifacts can be grouped without relying on reused graph names
- browser routes can reference a stable artifact or batch identity
- cleanup can prune complete batches safely

Even in a temporary-only model, `executionId -> batchId -> artifactId` is still useful because it isolates runs without forcing long-lived retention.

Without explicit execution identity, phase 2 still risks hidden collisions in multi-session or rapid-run scenarios.

## 6. Late Binding of Webview URIs

The graph store should not persist `asWebviewUri(...)` outputs.

Store only:

- real file path
- artifact metadata

When the controller builds a snapshot for a specific panel, it converts:

- `filePath -> webview.asWebviewUri(...)`

This matters because a webview URI is panel-specific state, not durable graph metadata.

## 6A. Runtime Config Transport

Graph storage configuration should be passed to the Python server explicitly, but the transport mechanism should minimize platform-specific quoting issues.

Preferred order:

1. environment variable or runtime config file
2. explicit CLI argument only if kept consistent across Windows and Unix startup paths

Why this matters:

- current Windows startup uses `exec()` with a constructed command string
- adding more filesystem path arguments increases quoting and escaping risk
- macOS and Linux/Unix commonly use paths with spaces as well

A small runtime config file or environment variable such as `STATA_MCP_GRAPHS_DIR` is more robust than proliferating more shell-assembled path arguments.

## 7. Browser Mode Compatibility

Browser mode should stop depending only on the logical graph name.

Recommended direction:

- server returns an opaque `browserPath` or `browserToken` per artifact
- extension opens that path in browser mode

Example:

```text
/graphs/artifact/<artifactId>
```

or:

```text
/graphs/batch/<batchId>/<filename>
```

The old route:

```text
/graphs/{graph_name}
```

should remain as a compatibility alias for now, but new extension code should prefer the explicit artifact route when available.

## 8. Cleanup Policy

Graph storage must have a cleanup strategy.

Recommended policy:

- treat graph artifacts as temporary cache, not retained history
- keep only the current batch by default
- optionally keep one immediately previous batch during handoff or delayed cleanup
- enforce a small size cap as a secondary safeguard
- cleanup should happen in extension host logic, not ad hoc in the webview
- never delete the currently displayed batch
- on Windows, failed deletions due to file locking should be retried later

Recommended cleanup triggers:

- after a successful new batch is exported and the viewer/browser has switched over
- when the user clears graphs
- when the graph panel is disposed
- on extension activation/startup sweep
- on extension deactivation as best effort

This keeps the temporary-use behavior aligned with product intent while still fixing file identity and caching issues.

## 9. Efficiency Improvements

The long-term design should improve performance as well as correctness.

Recommended efficiency rules:

- never replace `webview.html` for normal graph updates
- update only the current execution batch in the DOM
- avoid the pre-run empty redraw
- prefer replacing the visible batch only after the new batch is ready
- add `loading=\"lazy\"` to non-current images within the current batch when appropriate
- prune aggressively on disk, not by growing in-memory history

### Note on the current \"Last Graph\" duplication

The current viewer intentionally duplicates the last graph at the top and again in the batch list. This preserves an existing UX behavior, but it also doubles DOM/image work for the same artifact.

The long-term design should preserve this visible behavior unless deliberately changed later, but the implementation should be careful not to create unnecessary duplicate decode/paint work.

## Phased Implementation Plan

## Phase 1: Extension-Side Viewer Refactor

Goal:

- fix the Graph Viewer lifecycle without changing server transport or browser routes yet

Changes:

- introduce `GraphStore`
- introduce `GraphViewerController`
- stop using `allGraphs`
- stop using repeated `webview.html = ...`
- remove the pre-run empty redraw for `run_selection`
- keep current `graph.path` values from the server
- keep browser mode route unchanged for this phase
- preserve the current visible Graph Viewer layout, including the `Last Graph` summary behavior

Why phase 1 first:

- smallest compatibility surface
- directly targets the part most likely involved in the blank-panel behavior
- avoids bundling storage migration and transport redesign into the same patch

## Phase 2: Storage Root and Unique Artifact Paths

Goal:

- eliminate reused file paths and move temporary graphs out of the extension install directory

Changes:

- add configurable `graphs_root`
- pass that root from extension startup into Python server and worker using an explicit runtime config mechanism
- add `executionId` / `batchId` support through the server and worker graph export path
- export graphs to unique batch-scoped paths
- add aggressive cleanup by batch

Implementation note:

- `startMcpServer()` currently builds server startup arguments separately for Windows and Unix paths
- if a CLI argument is used, it must be added to both code paths
- if runtime config uses env or a config file, both code paths must still populate it consistently
- server reload and multi-session worker startup paths must use the same root consistently

Compatibility:

- keep `graph.path` in graph metadata
- keep old browser route as fallback

## Phase 3: Browser Route Modernization

Goal:

- decouple browser-mode display from logical graph names

Changes:

- add explicit artifact route such as `/graphs/artifact/{artifactId}`
- return `browserPath` or equivalent in graph metadata
- update `displayGraphsInBrowser(...)` to prefer explicit artifact routes

Compatibility:

- retain `/graphs/{graph_name}` temporarily

## Phase 4: Transport Cleanup

Goal:

- stop relying on textual graph markers in output parsing as the only graph metadata path

Changes:

- add structured graph metadata for stream and non-stream responses
- keep the textual `GRAPHS DETECTED` block for compatibility during transition

This should be deferred until after the viewer lifecycle and storage model are stable.

## Deep Review

## What is strong in this plan

### Stable shell + postMessage

This is the right long-term rendering model. It reduces lifecycle churn, avoids repeated full-page navigation, and is the cleanest place to add retries and health checks.

### Batch/artifact identity

This is not optional. The current graph-name-keyed model is incorrect by construction because graph names repeat across runs. Any serious fix needs unique batch/artifact identity.

Important clarification:

- this does not imply long-lived history
- it only means each execution gets a clean temporary identity

### Late-bound webview URIs

This is the correct boundary. Webview URIs belong to the panel/controller layer, not to persistent graph state.

### Phase split

This is critical. The viewer lifecycle fix should not be bundled with a full transport redesign or a full Interactive Window rewrite.

## Risks and Weak Points

### Risk 1: Over-bundling phase 1

If phase 1 also changes:

- server storage root
- browser routes
- stream metadata format
- interactive panel rendering

then any regression will be harder to diagnose and rollback.

**Recommendation**:

- keep phase 1 extension-side only
- do not move graph storage in the same first patch unless there is direct evidence that reused file paths are the immediate trigger

### Risk 2: Message ordering and stale snapshots

Switching to `postMessage(...)` introduces ordering problems if multiple updates are sent quickly.

**Mitigation**:

- use monotonic `version`
- have the webview ignore older versions
- apply only the most recent queued snapshot

### Risk 3: Hidden-panel behavior

If the panel is hidden or recreated, messages can be lost or applied before readiness.

**Mitigation**:

- queue the latest snapshot until `ready`
- replay the current snapshot after panel creation or recovery
- do not rely on implicit webview persistence

### Risk 4: Browser mode regression

Browser mode currently depends on a server route keyed by logical name. Unique batch-scoped file names will break that if changed carelessly.

**Mitigation**:

- add a new explicit artifact route before removing or bypassing the old route
- let extension prefer the new route but keep old route as fallback

### Risk 5: Interactive Window regression

The Interactive Window uses the same underlying graph files but a different rendering path.

**Mitigation**:

- keep Interactive Window unchanged in phase 1
- in phase 2, only update its graph root assumptions and `localResourceRoots`
- do not mix interactive renderer changes with graph viewer lifecycle changes

### Risk 6: Writable storage assumptions

Moving graphs into extension-managed storage is the right long-term choice, but it requires the extension to supply a writable graph root to the server and workers on every platform and in every remote mode.

**Mitigation**:

- add an explicit runtime config value for graph storage
- prefer env or config-file transport over piling more path arguments into shell-built commands
- use the same root consistently in server single-session and worker multi-session paths
- keep temp-directory fallback

### Risk 6A: Missing execution identity

If graph storage is moved to batch-scoped files without an explicit `executionId`, rapid successive runs and multi-session execution can still produce hard-to-debug ownership ambiguities.

**Mitigation**:

- generate `executionId` in the extension
- propagate it through server and worker execution paths
- derive `batchId` and storage layout from that identity

### Risk 6B: Read-only or unsuitable install directories

The current implementation writes graphs under the extension install path when available. That is not a good long-term assumption.

**Mitigation**:

- move mutable graph artifacts to `globalStorageUri` or another dedicated writable storage root
- treat the extension install directory as code/assets only

### Risk 7: Retain-context choice

`retainContextWhenHidden` can help performance, but it may worsen stale-state problems if enabled too early.

**Recommendation**:

- keep `retainContextWhenHidden: false` until the stable-shell viewer has proven reliable
- revisit later only if needed

## What should not be part of phase 1

- full browser-route redesign
- full Interactive Window redesign
- replacement of the output parser with structured stream events
- new UX semantics for graph history beyond what is needed for correctness

## Semantics that need an explicit decision

The current behavior is inconsistent:

- `run_selection` clears history before the new run
- `run_file` does not

The long-term design should make this explicit.

Recommended policy after this review:

- both `run_selection` and `run_file` should treat graphs as temporary current-run output
- prior graphs should remain visible only until a successful new batch is ready to replace them
- there should be no long-lived append-history model in the default Graph Viewer
- the current visible layout within a run should be preserved

## Rejected Alternatives

### Always dispose and recreate the panel every run

This is an acceptable fallback, not a good architecture. It hides lifecycle bugs by discarding state and adds unnecessary churn.

### Keep regenerating `webview.html` but add more cache-busting

This treats symptoms, not the architectural problem.

### Use data URIs for all graph images

This may reduce file-path concerns but creates memory and transport overhead, especially for multiple large graphs. It is not the right primary design.

### Big-bang rewrite of Graph Viewer, Browser Mode, and Interactive Mode together

Too much regression surface for one patch.

## Test Plan

## Unit tests

Add extension-side tests for:

- graph batch ordering
- duplicate logical graph names across batches
- cleanup and prune policy
- snapshot versioning
- stale snapshot rejection

These tests should target pure JS modules, not VS Code UI directly.

Before these tests can be relied on, the repository needs a real JS test entrypoint instead of the current placeholder references in `package.json`.

## Integration checks

Verify:

- Graph Viewer still displays latest graphs in VS Code
- browser mode still opens graphs externally
- Interactive Window still renders command graphs
- remote/code-server graph URIs still work
- graph cleanup does not remove current artifacts too early
- graph cleanup removes stale temporary batches promptly

## Regression checks

Specific regressions to guard against:

- Issue #54 remote graph loading
- graph scroll/history cap behavior
- stop/restart stale-result handling
- duplicate graph-name handling across multiple runs
- path handling with spaces, trailing slashes, and Windows drive letters
- temp-path realpath differences such as `/tmp` vs `/private/tmp`
- multi-session graph ownership and cleanup

## Cross-Platform Validation Matrix

The final implementation should be validated against these categories:

### macOS

- paths containing spaces
- temp-directory realpath differences
- standard VS Code install and remote/SSH scenarios

### Windows

- paths with spaces under `Program Files`
- trailing backslash handling
- drive-letter paths
- multi-session startup and server restart flow

### Linux/Unix

- `/tmp` and nonstandard temp roots
- remote/containerized extension-host scenarios
- extension installs where the install directory should be treated as non-mutable

## Recommended Implementation Order

1. Add `GraphStore` and tests.
2. Add `GraphViewerController` and stable-shell webview rendering.
3. Remove pre-run empty redraw.
4. Preserve current server graph paths and verify viewer behavior.
5. Only then move graph storage to a new root and unique batch paths.
6. Add explicit browser artifact routes.
7. Later, add structured graph metadata transport.

## Go/No-Go Criteria

The plan is sound if implemented in phases.

It becomes risky if:

- phase 1 is expanded into a storage + browser + transport rewrite
- browser and interactive regressions are not explicitly tested
- graph identity continues to rely on `graph.name`

The most important conclusion from this review is:

**the long-term fix should start as an extension-side viewer/state refactor, not as a big-bang rewrite of the entire graph pipeline.**
