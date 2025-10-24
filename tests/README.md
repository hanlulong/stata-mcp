# Tests Overview

The `tests/` directory intentionally keeps a minimal set of diagnostics and fixtures that cover the core MCP workflows:

## Python Diagnostics
- `simple_mcp_test.py` – Quick sanity check for the `/health`, `/run_file`, and `/openapi.json` endpoints.
- `test_streaming_http.py` – Verifies streaming output over the `/run_file/stream` HTTP endpoint.
- `test_notifications.py` – Exercises the MCP HTTP streamable transport to confirm that log/progress notifications reach clients.
- `test_timeout_direct.py` – Calls `run_stata_file` directly to ensure timeout enforcement works end-to-end.

## Stata `.do` Fixtures
- Streaming: `test_streaming.do`, `test_keepalive.do`
- Timeout: `test_timeout.do`
- Graph investigations: `test_gr_list_issue.do`, `test_graph_issue.do`, `test_graph_name_param.do`
- Log path validation: `test_log_location.do`
- General regression harnesses: `test_stata.do`, `test_stata2.do`, `test_understanding.do`

> All tests assume the MCP server is available at `http://localhost:4000`. Adjust the scripts if your environment differs.
