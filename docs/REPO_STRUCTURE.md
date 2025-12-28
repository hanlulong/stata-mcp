# Repository Structure Overview

This guide summarizes the key directories and utilities in the `stata-mcp` repository.

## Top-Level Directories
- `src/` – Extension source code (VS Code activation logic, MCP server entrypoints, Python helpers, plus dev tooling under `src/devtools/`).
- `dist/` – Bundled JavaScript produced by webpack for the published extension.
- `docs/` – Documentation, release notes, troubleshooting guides, and sample artefacts in `docs/examples/`.
- `tests/` – Long-lived automated tests, diagnostics, and `.do` fixtures (see below).
- `archive/` – Historical VSIX packages and backups (ignored by git).

## Test & Diagnostic Assets
- `tests/` – Lightweight diagnostics for MCP transports, streaming, notifications, and timeout handling (Python + `.do` fixtures in a single directory).
- `tests/README.md` – Overview of the retained diagnostics and fixtures.

## Generated Packages
- `stata-mcp-*.vsix` – Locally built extension archives for VS Code, Cursor, and Antigravity.
- `node_modules/` – NPM dependencies (ignored in version control).

## Additional References
- `README.md` / `README.zh-CN.md` – Primary usage documentation.
- `CHANGELOG.md` – Release-facing change log.
- `docs/incidents/` – Chronological debugging diaries and status reports (see `docs/incidents/README.md`).
