# Graph Viewer Webview Renders Blank — Diagnostic Handoff and Patch Update

**Issue tracker**: [GitHub Issue #60](https://github.com/hanlulong/stata-mcp/issues/60)
**Related design note**: `docs/incidents/GRAPH_VIEWER_LONG_TERM_FIX_PLAN.md`
**Affected versions**: Observed in v0.5.1 and v0.5.2 (possibly earlier)
**Affected platforms**: VS Code on macOS AND Windows (universal, not OS-specific)
**Extension**: `DeepEcon.stata-mcp` (a Stata integration extension for VS Code)

---

## Status Update (2026-04-18)

This document began as a diagnostic handoff. After reviewing the regression window and the earlier remote-environment fixes from Issue #54, the graph viewer was patched in the working tree without reverting the older graph-loading changes.

### What changed in the patch

1. **Kept the Issue #54 remote/resource fixes intact.**
   - `webview.asWebviewUri(...)` is still used for graph PNGs
   - `localResourceRoots` still includes the graph directories
   - external browser graph display still uses `vscode.env.asExternalUri()`

2. **Changed only the graph viewer webview shell.**
   - moved inline CSS into [`media/graph-viewer.css`](../../media/graph-viewer.css)
   - moved inline JS into [`media/graph-viewer.js`](../../media/graph-viewer.js)
   - replaced inline `onclick` / `onerror` handlers with event listeners in external JS
   - changed CSP to the stricter external-resource pattern:
     - `style-src ${webview.cspSource}`
     - `script-src 'nonce-${nonce}' ${webview.cspSource}`

3. **Changed graph panel lifecycle behavior.**
   - `retainContextWhenHidden` is now `false` for the graph viewer panel only, to avoid a retained dead/blank iframe state

4. **Added webview resource helpers.**
   - `getMediaDir()`
   - `getExtensionResourceWebviewUri()`
   - `getNonce()`

### Current status

- Patch has been applied in source and compiled successfully with `npm run compile`
- Manual VS Code verification is still required to confirm that the blank panel is resolved on the original repro
- If the panel is still blank after this patch, the next step is webview DevTools inspection, not reverting Issue #54

---

## Symptom

When the user runs a Stata graph command (e.g. `hist mpg, normal`), the "Stata Graphs" webview panel opens with the correct tab title, but the panel body is **completely blank** — not just missing images, but *no visible content at all*, including the `<h1>Stata Graphs</h1>` header text that should render in light gray on the dark body background.

See screenshots attached to Issue #60.

## What is NOT the problem

These have been ruled out by logs and by reading code:

1. **Server-side graph export.** Stata server correctly exports PNG files to disk. Verified:
   - Log shows `Exported graph 'graph1' (35549 bytes) to /Users/.../graphs/graph1.png`
   - Files exist on disk with non-zero sizes (20 KB – 78 KB for `hist mpg, normal` and friends)
   - Server emits the expected SSE block:
     ```
     ============================================================
     GRAPHS DETECTED: 4 graph(s) created
     ============================================================
       • graph1: /Users/.../graphs/graph1.png
       ...
     ```

2. **Extension-side parsing.** `parseGraphsFromOutput` regex correctly extracts all graphs:
   - Log shows `Displaying 4 graph(s) in VS Code webview`
   - `displayGraphsInVSCode` runs to completion, logs `Displayed 4 graph(s) in VS Code webview (total: 4)` at the end

3. **HTML generation and assignment.** `updateGraphViewerPanel` completes without throwing:
   - Log shows `[GraphViewer] cspSource=''self' https://*.vscode-cdn.net', rendering 5 graph(s)`
   - Each graph URI is generated and logged:
     `[GraphViewer] graph='graph4' path='/Users/.../graphs/graph4.png' uri='https://file%2B.vscode-resource.vscode-cdn.net/Users/.../graphs/graph4.png'`
   - Log confirms `[GraphViewer] Setting webview.html (length=6803 chars)` — meaning `webview.html = fullHtml` was executed
   - No `[GraphViewer] updateGraphViewerPanel failed` log (the defensive try/catch did not trip)

4. **Path resolution / symlink issues.** Already tested with `fs.realpathSync` helpers (`toRealPath`, `ensureDirRealPath`). On the user's macOS, the paths have no symlinks in the ancestor chain:
   - `/Users/hanlulong/.vscode/extensions/deepecon.stata-mcp-0.5.2/graphs/` → realpath returns same path
   - `realpathSync('/tmp/x/y/z.png')` correctly resolves to `/private/tmp/x/y/z.png` (macOS symlink)

5. **CSP wildcard matching.** Per CSP3 spec §6.6.2.6, `*.vscode-cdn.net` matches `file+.vscode-resource.vscode-cdn.net` (wildcard matches any non-empty prefix including subdomains with dots). Verified by CSP3 spec reading; consistent with Microsoft's webview-sample pattern.

6. **Extension installed correctly.** Verified by SHA-256 hash match between source bundle and installed `dist/extension.js`. Debug log strings are present in the installed bundle.

7. **CSS causing invisibility.** Body has `color: var(--vscode-editor-foreground, #cccccc)` — light gray — with a fallback. Dark theme would still show light text on dark background. Even if all CSS failed to parse, browser defaults would produce black text on white body (not blank).

## The central contradiction

`webview.html = fullHtml` with a 6803-char valid HTML string is successfully executed, but the webview renders absolutely nothing. Even a bare `<h1>Stata Graphs</h1>` in the `<body>` is invisible.

If the HTML were parsed and rendered, we would see *at minimum* the header text. We don't. This strongly suggests the webview is **not rendering the HTML at all**, not just failing to load images.

## What the logs look like during a failed run

User's actual log output (from Stata output channel):

```
============================================================
GRAPHS DETECTED: 4 graph(s) created
============================================================
  • graph1: /Users/hanlulong/.vscode/extensions/deepecon.stata-mcp-0.5.2/graphs/graph1.png
  • graph2: /Users/hanlulong/.vscode/extensions/deepecon.stata-mcp-0.5.2/graphs/graph2.png
  • graph3: /Users/hanlulong/.vscode/extensions/deepecon.stata-mcp-0.5.2/graphs/graph3.png
  • graph4: /Users/hanlulong/.vscode/extensions/deepecon.stata-mcp-0.5.2/graphs/graph4.png
Displaying 4 graph(s) in VS Code webview
[GraphViewer] cspSource=''self' https://*.vscode-cdn.net', rendering 5 graph(s)
[GraphViewer] graph='graph4' path='/Users/.../graph4.png' uri='https://file%2B.vscode-resource.vscode-cdn.net/Users/.../graph4.png'
[GraphViewer] graph='graph1' path='/Users/.../graph1.png' uri='https://file%2B.vscode-resource.vscode-cdn.net/Users/.../graph1.png'
[GraphViewer] graph='graph2' path='/Users/.../graph2.png' uri='https://file%2B.vscode-resource.vscode-cdn.net/Users/.../graph2.png'
[GraphViewer] graph='graph3' path='/Users/.../graph3.png' uri='https://file%2B.vscode-resource.vscode-cdn.net/Users/.../graph3.png'
[GraphViewer] graph='graph4' path='/Users/.../graph4.png' uri='https://file%2B.vscode-resource.vscode-cdn.net/Users/.../graph4.png'
[GraphViewer] Setting webview.html (length=6803 chars)
Displayed 4 graph(s) in VS Code webview (total: 4)
```

## Relevant code locations (repo root: this directory)

- **Graph viewer panel + message handling**: [src/extension.js:3127-3182](src/extension.js#L3127-L3182) (`displayGraphsInVSCode`)
- **Graph viewer HTML generation**: [src/extension.js:3293-3322](src/extension.js#L3293-L3322) (`getGraphViewerHtml`)
- **Graph viewer per-graph render path**: [src/extension.js:3184-3273](src/extension.js#L3184-L3273) (`updateGraphViewerPanel`)
- **Per-graph URI generation**: [src/extension.js:3099-3108](src/extension.js#L3099-L3108) (`getGraphWebviewUri`)
- **Webview resource helpers**: [src/extension.js:3030-3049](src/extension.js#L3030-L3049) (`getMediaDir`, `getExtensionResourceWebviewUri`, `getNonce`)
- **Realpath helpers**: [src/extension.js:3051-3097](src/extension.js#L3051-L3097) (`toRealPath`, `ensureDirRealPath`)
- **Graph viewer stylesheet**: [media/graph-viewer.css](../../media/graph-viewer.css)
- **Graph viewer script**: [media/graph-viewer.js](../../media/graph-viewer.js)
- **Graph output parser (server → extension)**: [src/extension.js:2970-3019](src/extension.js#L2970-L3019) (`parseGraphsFromOutput`)
- **Server-side PNG export**: [src/stata_mcp_server.py:1087-1140](src/stata_mcp_server.py#L1087-L1140) (`detect_and_export_graphs`)
- **Server-side SSE stream for graph info**: [src/stata_mcp_server.py:2295-2306](src/stata_mcp_server.py#L2295-L2306)

## Historical HTML that was getting set in the webview before the patch

This is the inline-CSS / inline-JS template that was active during the blank-panel investigation. The current working-tree patch replaces this template with external CSS/JS assets plus nonce-based script loading.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' https://*.vscode-cdn.net data:; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
    <title>Stata Graphs</title>
    <style>
        html { box-sizing: border-box; }
        *, *:before, *:after { box-sizing: inherit; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: var(--vscode-editor-background, #1e1e1e);
            color: var(--vscode-editor-foreground, #cccccc);
        }
        .header { … }
        .graph-container { … }
        /* … more styles … */
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <h1>Stata Graphs</h1>
            <div class="graph-count">1 graph(s) displayed</div>
        </div>
        <button class="clear-button" onclick="clearGraphs()">Clear All</button>
    </div>
    <div id="graphs-container">
        <div class="graph-container" data-graph-name="graph1">
            <h3>graph1</h3>
            <img src="https://file%2B.vscode-resource.vscode-cdn.net/Users/.../graph1.png" alt="graph1"
                 onerror="this.style.display='none'; var e=this.nextElementSibling; if(e) e.style.display='block';">
            <div class="error" style="display:none;">Failed to load graph: graph1 (path: /Users/.../graph1.png)</div>
        </div>
    </div>
    <script>
        const vscode = acquireVsCodeApi();
        function clearGraphs() {
            vscode.postMessage({ command: 'clearGraphs' });
        }
    </script>
</body>
</html>
```

## Fixes already attempted (none resolved the blank panel)

These are live in v0.5.2 HEAD:

1. **Reverted CSS flex-column pattern** from v0.5.2 pre-release back to v0.5.1-style simple CSS (but without `height: 100vh` + `overflow-y: auto`, since those were removed as a separate attempted fix). See [src/extension.js:3281-3290](src/extension.js#L3281-L3290).
2. **Added fallback colors** on every `var(--vscode-*)` theme variable.
3. **`fs.realpathSync` resolution** on `localResourceRoots` and on each graph's path before passing to `webview.asWebviewUri`.
4. **Defensive `onerror` handler** with null-check for `nextElementSibling`.
5. **Per-graph try/catch** in `graphsArray.map(...)` so one bad entry doesn't blank the whole panel.
6. **Top-level try/catch** in `updateGraphViewerPanel` that, on error, sets a visible error HTML fallback.
7. **Server-side file-size validation** rejecting empty PNG exports.
8. **Verbose logging** at INFO level showing cspSource, each graph URI, and final HTML length.

Nothing above has changed the symptom: panel still blank.

## Patch applied after this handoff

These changes have now been applied in the working tree:

1. **Preserved the remote graph-loading fix from Issue #54.**
   - No rollback to `http://localhost/...`
   - `asWebviewUri(...)` and `localResourceRoots` remain in place

2. **Moved the graph viewer to external webview assets.**
   - CSS now loads from [`media/graph-viewer.css`](../../media/graph-viewer.css)
   - JS now loads from [`media/graph-viewer.js`](../../media/graph-viewer.js)

3. **Removed inline event handlers and inline script setup.**
   - clear button now uses `addEventListener('click', ...)`
   - image load failures now use `addEventListener('error', ...)`
   - `acquireVsCodeApi()` is called inside external JS with a `try/catch`

4. **Hardened the CSP.**
   - moved from `'unsafe-inline'` style/script allowances to external resources + nonce-based script loading

5. **Disabled retained webview context for the graph viewer.**
   - `retainContextWhenHidden: false`

6. **Added the media directory to `localResourceRoots`.**
   - required for the external CSS/JS assets to load inside the webview

7. **Recompiled the extension bundle.**
   - `npm run compile` completed successfully after the patch

This patch is intentionally narrow: it changes the graph viewer shell, not the graph export pipeline, not the remote-environment fix, and not the browser-mode graph display path.

## Hypotheses I could NOT rule out (candidates for Codex investigation)

### H1. VS Code webview on some versions silently rejects our HTML

**What to check**: Does our HTML hit some undocumented VS Code webview requirement?

Compared with [microsoft/vscode-extension-samples/webview-sample](https://github.com/microsoft/vscode-extension-samples/tree/main/webview-sample), our HTML differs in:
- **CSP style-src**: we use `'unsafe-inline'`, sample uses `${webview.cspSource}` (external CSS)
- **CSP script-src**: we use `'unsafe-inline'`, sample uses `'nonce-${nonce}'`
- **Inline event handlers**: our HTML has `onclick="clearGraphs()"` and `onerror="..."`; sample has none
- **Script call**: we call `acquireVsCodeApi()` inline at top level of our script

Microsoft's security guidance has been moving toward nonce-based CSP and away from `'unsafe-inline'` — it's possible that a VS Code webview version has silently broken `'unsafe-inline'` or inline event handlers in a way that causes the entire document to fail to render.

**Try**: Port our HTML to exactly match the Microsoft sample pattern (external CSS + nonce-based scripts + no inline event handlers + `acquireVsCodeApi` in an external script file). See if that renders.

### H2. The `<script>` with `acquireVsCodeApi()` is throwing on some VS Code versions and halting rendering

`acquireVsCodeApi()` can only be called once per webview context. If something about our webview is causing it to be called twice (e.g. the user had the panel open from a prior session and our new HTML re-runs the script), it throws. In strict modes some browsers do halt rendering on uncaught script errors.

**Try**: Wrap the `acquireVsCodeApi()` call in a try/catch; OR move scripts to `defer` / external file; OR check `typeof acquireVsCodeApi !== 'undefined'`.

### H3. CSP `'unsafe-inline'` is being ignored, and VS Code is blocking our `<style>` and `<script>` tags

If the webview is blocking the `<style>` tag, the page would render with browser-default styles (white body, black text) — NOT blank.
If the webview is blocking the `<script>` tag, the script fails but HTML still renders.

So this on its own doesn't explain "absolutely blank". BUT combined with some other parsing issue, it might.

**Try**: Inspect the *actual* rendered DOM using `Developer: Open Webview Developer Tools` (note: this command opens a SEPARATE DevTools window scoped to the webview iframe, different from `Developer: Toggle Developer Tools` which shows the workbench). Check:
- Is the `<body>` present with our HTML children?
- Is the `<body>` empty?
- Any Console errors about CSP violations, scripts throwing, or style parse errors?

### H4. The image URI scheme mismatch

Our image URIs use `https://file+.vscode-resource.vscode-cdn.net/…`. The webview's `cspSource` is `'self' https://*.vscode-cdn.net`. In Chromium's CSP matcher:
- `*.vscode-cdn.net` should match `file+.vscode-resource.vscode-cdn.net` per spec
- But some implementations interpret `*` as matching ONLY a single subdomain label

If `*.vscode-cdn.net` only matches single-label subdomains in the user's Chromium version, all image loads would fail with CSP violations. But that alone doesn't explain a blank panel — the non-image HTML would still render.

**Try**: Capture Console output when the panel is blank. CSP violations log to Console as: `Refused to load the image 'https://...' because it violates the following Content Security Policy directive: …`.

### H5. Cached webview state

`retainContextWhenHidden: true` keeps the webview's iframe alive when the panel is hidden. VS Code has had bugs where `webview.html = ...` doesn't actually re-render a retained context. There's a known workaround: dispose and recreate the panel entirely when content must be refreshed.

**Try**: Set `retainContextWhenHidden: false` to force re-render every time.

### H6. `cspSource` value contains a literal `'self'` that breaks our CSP string

Observed cspSource value: `'self' https://*.vscode-cdn.net`

After interpolation, our CSP becomes:
```
default-src 'none'; img-src 'self' https://*.vscode-cdn.net data:; style-src 'unsafe-inline'; script-src 'unsafe-inline';
```

This is valid CSP. But: the `'self'` token in the cspSource is possibly meant to apply to `script-src`/`style-src` (to allow webview-origin resources), not to `img-src`. We're only using cspSource in `img-src`. That means the `'self'` in cspSource effectively widens `img-src` to also allow the webview's own origin — which is harmless, not harmful.

**Still worth trying**: what Microsoft's sample does is:
- `style-src ${webview.cspSource}` (NOT `'unsafe-inline'`)
- `img-src ${webview.cspSource} https:`
- `script-src 'nonce-${nonce}'`

### H7. Our HTML is fine but VS Code's webview host has a layout bug

The webview is an iframe. If the iframe's parent (VS Code's webview host container) has `width: 0` or `height: 0` or `display: none`, our content never appears regardless of what's inside. This can happen with certain VS Code layout states or with certain panel-sizing conflicts.

**Try**: User should open the webview DevTools (separate from workbench DevTools) and inspect the iframe's computed dimensions.

## Recommended next-step verification plan

1. **Verify the patched build in desktop VS Code** using the original repro:
   - install/run the current build
   - run:
     ```stata
     sysuse auto, clear
     hist mpg, normal
     ```
   - confirm whether the "Stata Graphs" panel now renders header text and images

2. **If the panel is still blank, get the webview's actual rendered DOM** using `Developer: Open Webview Developer Tools`:
   - Elements tab: is the body empty, or does it contain our HTML?
   - Console tab: any CSP violations, uncaught exceptions, or `acquireVsCodeApi`-related errors?
   - Network tab: did the image requests fire? What status code?

3. **If needed, do a minimal repro**: temporarily replace `getGraphViewerHtml` with the absolute minimum:
   ```javascript
   function getGraphViewerHtml(graphsHtml, graphCount, cspSource) {
       return '<!DOCTYPE html><html><body style="background:red;color:white;padding:20px"><h1>TEST</h1><p>graphs: ' + graphCount + '</p></body></html>';
   }
   ```
   If this TEST HTML renders → the bug is in our full template. If TEST also renders blank → the webview pipeline is broken (serious VS Code issue or env-specific problem).

4. **If minimal HTML works**, binary-search add pieces back:
   - Add CSP meta tag → does it still render?
   - Add `<style>` block → does it still render?
   - Add `<script>` block → does it still render?
   - Add `acquireVsCodeApi()` call → does it still render?
   - Add `<img>` with webview URI → does the IMAGE load, and does the header still render?

5. **Keep `retainContextWhenHidden: false`** while debugging to rule out webview-cache bugs.

6. **Do not revert Issue #54 while debugging.**
   - reverting to `http://localhost/...` would risk re-breaking `code-server`, Remote-SSH, Codespaces, and other proxied/remote environments

## Hard constraints / preferences

- The user is on VS Code (not Cursor/Trae), on both macOS and Windows.
- Solution must work across VS Code, Cursor, Trae, code-server, Remote-SSH, and Codespaces.
- The Data Viewer webview (same codebase, same extension) renders fine — so **webview functionality is NOT universally broken**. The Data Viewer HTML is in `src/extension.js` near line 2240 and can be used as a working reference.
- Do not remove the UUID-based frame fix, toolbar ordering, preserve/restore fix, help HTML syntax fix, or session restart recovery — those are unrelated to #60 and address other confirmed bugs.

## Repro steps

1. Install `stata-mcp-0.5.2.vsix`
2. Open any `.do` file, or create one with:
   ```stata
   sysuse auto, clear
   hist mpg, normal
   ```
3. Run via the Stata MCP "Run Selection" or "Run File" button
4. Observe: "Stata Graphs" panel opens beside the editor, completely blank

## Expected behavior

The panel should display the exported PNG graphs with a header, a "Clear All" button, and each graph shown in a styled container.

---

**Last updated by**: Codex session, 2026-04-18
**Reporter**: Lu Han
**Repo**: https://github.com/hanlulong/stata-mcp
