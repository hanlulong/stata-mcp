# Issue #57 Analysis: Cursor/Trae No Output Display

Date: 2026-04-01

Issue: https://github.com/hanlulong/stata-mcp/issues/57

## Summary

Issue #57 appears to involve two separate failure modes:

1. A client-side streaming adapter problem in Cursor/Trae.
2. A remaining server-side streaming fallback gap that can still produce a blank output panel even when execution succeeds.

The first problem appears to be fixed in `v0.5.1`. The second problem is still plausible from the current code, especially on Windows.

## Reported Timeline

- 2026-03-28: Issue #57 was opened reporting that Trae/Cursor executed `.do` files successfully but showed no output.
- 2026-03-28: Commit `ab0a309` landed on `main` with message: `fix: force Node.js HTTP adapter for streaming in Cursor/Trae (Issue #57)`.
- 2026-03-28: Release `v0.5.1` was published.
- 2026-03-29: A follow-up issue comment reported that `v0.5.1` still showed no output in Cursor on Windows, even though the generated `*_mcp.log` file contained the full regression table.

## What Was Verified Locally

- `main` already contains the `Issue #57` fix.
- The packaged `stata-mcp-0.5.1.vsix` also contains the same fix.
- Therefore, a local test on current `main` or on the local `0.5.1` artifact can reasonably fail to reproduce the original report.

## Confirmed Fix in `v0.5.1`

The extension now forces axios to use the Node.js HTTP adapter for both streaming endpoints:

- `src/extension.js`
  - `executeStataCode()` for `/run_selection/stream`
  - `executeStataFile()` for `/run_file/stream`

Relevant lines in current source:

- `src/extension.js:1691-1695`
- `src/extension.js:1952-1956`

Specifically, both requests now include:

```js
adapter: 'http'
```

This directly addresses the original hypothesis in the issue discussion: Cursor/Trae may expose browser-like globals that cause axios to choose a non-Node adapter, which does not behave correctly for `responseType: 'stream'`.

## Why The Follow-Up Report Still Looks Real

The March 29, 2026 follow-up comment contains a strong clue:

- Stata execution completed.
- The output log file contained the full regression table.
- The Cursor output panel remained blank.
- No error was shown.

That pattern matches a different failure mode from the adapter issue.

## Current Streaming Design

For both streaming endpoints, the server sends output by tailing the log file while execution is running:

- `src/stata_mcp_server.py:2237-2252` for `/run_file/stream`
- `src/stata_mcp_server.py:2612-2626` for `/run_selection/stream`

At the end of execution, the server reads any remaining log content and emits it:

- `src/stata_mcp_server.py:2267-2281`
- `src/stata_mcp_server.py:2640-2655`

If execution succeeds, the server then emits only a completion marker:

- `src/stata_mcp_server.py:2285-2295`
- `src/stata_mcp_server.py:2659-2669`

The extension intentionally treats `*** Execution completed ***` as a status line and does not display it as user output:

- `src/extension.js:1713-1723`
- `src/extension.js:1978-1990`

## Important Gap

In multi-session execution, the worker already returns the final captured output from the log file:

- `src/stata_worker.py:623-640`

The stream generator receives that result:

- `src/stata_mcp_server.py:2183-2194`
- `src/stata_mcp_server.py:2519-2529`

However, on successful execution, the stream generator does not fall back to emitting `result` if log tailing produced nothing. It only emits:

- any lines successfully read from the log file, and then
- `*** Execution completed ***`

That means the following silent failure path exists:

1. Stata executes successfully.
2. The worker returns the full result.
3. The stream tail logic fails to read the expected user lines from the log file at the right time.
4. The server emits only the completion marker.
5. The extension suppresses the completion marker as a status line.
6. The user sees a blank output panel with no error.

This is highly consistent with the follow-up report in Issue #57.

## Why It May Not Reproduce Locally

Several factors could make this intermittent or environment-specific:

- plain VS Code vs Cursor/Trae extension host behavior,
- Windows file locking and timing differences,
- differences in multi-session vs single-session execution,
- local filesystem speed and log flush timing,
- local testing against `main` or a rebuilt extension instead of the exact reporter environment.

So "works on my machine" is compatible with the remaining bug hypothesis.

## Most Likely Interpretation

Issue #57 likely combines:

### 1. Original adapter bug

This was likely real and is addressed by `v0.5.1`.

### 2. Remaining stream fallback bug

This is still plausible in current code:

- successful execution,
- log file contains output,
- streamed UI shows nothing,
- no visible error.

That second path looks like the stronger explanation for the March 29, 2026 follow-up report.

## Best Verification Steps

To narrow this down further in a reporter environment, the most useful checks would be:

1. Enable `stata-vscode.debugMode` and inspect whether there are any `Error reading log file:` or `Error reading final log content:` messages.
2. Test the same command in plain VS Code on the same Windows machine.
3. Test once with `stata-vscode.multiSession = false`.

Interpretation:

- If the problem only appears in Cursor/Trae, the client/host layer remains suspect.
- If it also appears in plain VS Code, the server-side stream fallback is more likely.
- If it disappears with `multiSession = false`, the multi-session log-tail path becomes the primary suspect.

## Conclusion

The current evidence does not support closing Issue #57 as fully resolved.

The adapter fix in `v0.5.1` is present and correct, but the code still appears to have a silent success-without-output path when streaming depends on log tailing and does not emit the already-captured final result as a fallback.
