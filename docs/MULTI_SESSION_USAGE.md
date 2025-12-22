# Multi-Session Stata MCP Server - Usage Guide

This guide explains how to use the multi-session feature to run multiple Stata sessions in parallel.

## Overview

The multi-session feature enables:
- **Parallel Execution**: Run Stata commands simultaneously in different sessions
- **State Isolation**: Each session has its own data, variables, and macros
- **Backward Compatibility**: Existing clients work without changes (uses default session)

## Quick Start

### Enable Multi-Session Mode

Add to your MCP server configuration or command line:

```bash
python stata_mcp_server.py \
    --multi-session \
    --max-sessions 4 \
    --session-timeout 3600
```

### VS Code Settings

```json
{
    "stata-vscode.multiSession.enabled": true,
    "stata-vscode.multiSession.maxSessions": 4,
    "stata-vscode.multiSession.sessionTimeout": 3600
}
```

## API Reference

### Session Management Endpoints

#### Create Session
```http
POST /sessions
```

**Response:**
```json
{
    "status": "success",
    "session_id": "abc123",
    "message": "Session created successfully"
}
```

#### List Sessions
```http
GET /sessions
```

**Response:**
```json
{
    "sessions": [
        {
            "session_id": "default",
            "state": "ready",
            "created_at": "2024-01-01T00:00:00Z",
            "last_activity": "2024-01-01T00:01:00Z",
            "is_busy": false,
            "is_default": true
        },
        {
            "session_id": "abc123",
            "state": "ready",
            "created_at": "2024-01-01T00:00:30Z",
            "last_activity": "2024-01-01T00:00:45Z",
            "is_busy": false,
            "is_default": false
        }
    ],
    "max_sessions": 4,
    "available_slots": 2
}
```

#### Get Session Details
```http
GET /sessions/{session_id}
```

#### Destroy Session
```http
DELETE /sessions/{session_id}
```

### Executing Commands with Sessions

All existing execution endpoints support an optional `session_id` parameter:

#### MCP Tool Execution
```json
{
    "tool": "stata_run_file",
    "parameters": {
        "file_path": "/path/to/file.do",
        "timeout": 600,
        "session_id": "abc123"
    }
}
```

#### Run File Endpoint
```http
GET /run_file?file_path=/path/to/file.do&session_id=abc123
```

#### Run Selection Endpoint
```http
POST /run_selection?session_id=abc123
Content-Type: text/plain

display "Hello from session abc123"
```

### Backward Compatibility

**If you don't specify `session_id`**, the default session is used automatically:

```json
// Uses default session
{
    "tool": "stata_run_file",
    "parameters": {
        "file_path": "/path/to/file.do"
    }
}
```

This means existing clients require **zero changes** to continue working.

## Use Cases

### 1. Parallel Data Analysis

Run different analyses simultaneously:

```python
# Session 1: Regression analysis
session1 = create_session()
execute("use dataset1.dta\nreg y x1 x2 x3", session_id=session1)

# Session 2: Summary statistics (runs in parallel)
session2 = create_session()
execute("use dataset2.dta\nsummarize", session_id=session2)
```

### 2. Isolated Testing

Test code without affecting main session state:

```python
# Main session: production data
execute("use production_data.dta")  # Uses default session

# Test session: experiment without affecting main
test_session = create_session()
execute("use test_data.dta\n// ... test code ...", session_id=test_session)
destroy_session(test_session)

# Main session still has production_data loaded
execute("list in 1/5")  # Uses default session
```

### 3. Multiple Claude Code Instances

When multiple Claude Code instances connect to the same MCP server:

- Each instance can create its own session
- Sessions are isolated - one instance's commands don't affect another
- The server manages resource limits (max sessions)

## Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `multiSession.enabled` | `false` | Enable multi-session mode |
| `multiSession.maxSessions` | `4` | Maximum concurrent sessions |
| `multiSession.sessionTimeout` | `3600` | Session idle timeout (seconds) |
| `multiSession.workerStartTimeout` | `60` | Worker initialization timeout |
| `multiSession.commandTimeout` | `600` | Default command execution timeout |

## Resource Considerations

### Memory Usage
Each Stata session uses approximately 200-300 MB RAM. With 4 sessions, expect:
- ~1 GB RAM for Stata processes
- Additional memory for data loaded in each session

### Stata Licensing
Some Stata licenses limit concurrent instances. Check your license terms before enabling multi-session mode.

### Recommendations
- Start with `maxSessions=2` and increase as needed
- Set appropriate `sessionTimeout` to clean up idle sessions
- Monitor system resources during parallel execution

## Error Handling

### Common Errors

**Maximum sessions reached:**
```json
{
    "status": "error",
    "error": "Maximum sessions (4) reached"
}
```
*Solution*: Destroy unused sessions or increase `maxSessions`

**Session not found:**
```json
{
    "status": "error",
    "error": "Session not found: xyz789"
}
```
*Solution*: Session may have timed out; create a new session

**Worker initialization failed:**
```json
{
    "status": "error",
    "error": "Failed to initialize Stata: [details]"
}
```
*Solution*: Check Stata installation, license, and system resources

## Troubleshooting

### Session stuck in "busy" state
- The execution may still be running
- Use the stop endpoint: `POST /sessions/{session_id}/stop`
- If unresponsive, destroy and recreate the session

### Sessions not starting
1. Check Stata installation path is correct
2. Verify Stata license allows concurrent instances
3. Check system has sufficient memory
4. Review server logs for detailed error messages

### Performance issues
- Reduce `maxSessions` if system is memory-constrained
- Increase `sessionTimeout` to reduce session churn
- Consider running analyses sequentially if parallelism isn't needed

## Example: Full Workflow

```python
import requests

BASE_URL = "http://localhost:4000"

# 1. Check current sessions
sessions = requests.get(f"{BASE_URL}/sessions").json()
print(f"Active sessions: {len(sessions['sessions'])}")

# 2. Create a new session
response = requests.post(f"{BASE_URL}/sessions")
session_id = response.json()['session_id']
print(f"Created session: {session_id}")

# 3. Execute commands in the session
result = requests.post(
    f"{BASE_URL}/v1/tools",
    json={
        "tool": "stata_run_selection",
        "parameters": {
            "selection": "display \"Hello from session!\"",
            "session_id": session_id
        }
    }
).json()
print(f"Output: {result['output']}")

# 4. Clean up
requests.delete(f"{BASE_URL}/sessions/{session_id}")
print(f"Destroyed session: {session_id}")
```

## Version Compatibility

Multi-session support is available in Stata MCP Server version 0.4.0 and later.

Clients using earlier versions or not specifying `session_id` will automatically use the default session with full backward compatibility.
