# Multi-Session Stata MCP Server - Design Document

## Executive Summary

This document outlines the design for enabling parallel Stata sessions in the MCP server, allowing multiple Claude Code instances to run independent Stata tasks simultaneously through a single server port.

## Problem Statement

**Current Limitation:** PyStata runs as an in-process shared library. All requests share the same Stata state (data, variables, macros), making parallel execution impossible.

**Solution:** Spawn separate Python worker processes, each with its own PyStata instance, managed by a central session manager.

## Proof of Concept Results

The test in `tests/test_multiprocess_pystata.py` proved:
- ✅ Multiple PyStata instances work in separate processes
- ✅ Complete state isolation between workers
- ✅ True parallel execution (2s sleep in 2 workers = 2s total, not 4s)
- ✅ Cross-platform compatible (uses Python multiprocessing)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       FastAPI Server (Main Process)                     │
│                              Port 4000                                  │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      Session Manager                               │  │
│  │                                                                    │  │
│  │  Responsibilities:                                                 │  │
│  │  • Create/destroy worker processes on demand                      │  │
│  │  • Route requests to correct worker by session_id                 │  │
│  │  • Monitor worker health and restart if needed                    │  │
│  │  • Enforce max session limits                                     │  │
│  │  • Cleanup idle sessions after timeout                            │  │
│  │  • Provide backward compatibility (default session)               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│         ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│         │   Worker 0   │  │   Worker 1   │  │   Worker N   │           │
│         │  (Default)   │  │  Session A   │  │  Session X   │           │
│         │              │  │              │  │              │           │
│         │  ┌────────┐  │  │  ┌────────┐  │  │  ┌────────┐  │           │
│         │  │PyStata │  │  │  │PyStata │  │  │  │PyStata │  │           │
│         │  │Instance│  │  │  │Instance│  │  │  │Instance│  │           │
│         │  └────────┘  │  │  └────────┘  │  │  └────────┘  │           │
│         │              │  │              │  │              │           │
│         │  cmd_queue   │  │  cmd_queue   │  │  cmd_queue   │           │
│         │  result_queue│  │  result_queue│  │  result_queue│           │
│         └──────────────┘  └──────────────┘  └──────────────┘           │
│              │                  │                  │                    │
│              └──────────────────┼──────────────────┘                    │
│                    multiprocessing.Queue                                │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Critical Design Decisions

### 1. Process Start Method: `spawn`

```python
multiprocessing.set_start_method('spawn', force=True)
```

**Why `spawn` not `fork`:**
- `fork` copies parent memory including any initialized PyStata state
- This causes conflicts with Stata's shared library
- `spawn` creates clean child processes
- Required for Windows compatibility (Windows only supports spawn)
- Must be called once, early, before any Process creation

**Implementation Note:** Must be called in `if __name__ == '__main__':` block or at module import time.

### 2. Inter-Process Communication: multiprocessing.Queue

**Why Queue over Pipe:**
- Thread-safe by design
- Handles serialization automatically
- Supports timeout on get()
- Works across platforms

**Queue Types:**
- `command_queue`: Main → Worker (commands to execute)
- `result_queue`: Worker → Main (execution results, status updates)
- `output_queue`: Worker → Main (streaming stdout capture)

### 3. Worker Lifecycle States

```
    ┌─────────────┐
    │   CREATED   │
    └──────┬──────┘
           │ process.start()
           ▼
    ┌─────────────┐
    │INITIALIZING │──────────► INIT_FAILED
    └──────┬──────┘
           │ PyStata ready
           ▼
    ┌─────────────┐
    │    READY    │◄───────────────────────┐
    └──────┬──────┘                        │
           │ command received              │
           ▼                               │
    ┌─────────────┐                        │
    │    BUSY     │────────────────────────┘
    └──────┬──────┘     command complete
           │
           │ EXIT command or error
           ▼
    ┌─────────────┐
    │   STOPPED   │
    └─────────────┘
```

### 4. Backward Compatibility

**Default Session (Worker 0):**
- Always exists when server starts
- Used when no `session_id` provided in request
- Maintains 100% backward compatibility with existing clients
- No API changes required for single-session usage

**Explicit Sessions:**
- Created on demand via `/sessions` endpoint
- Each gets unique `session_id`
- Must include `session_id` in requests to use
- Cleaned up after timeout or explicit deletion

---

## Output Capture Strategy

### Challenge
PyStata's `stata.run()` outputs to stdout directly. In worker processes, we need to capture this and send it back to the main process.

### Solution: Dual Capture

```python
import io
import sys
from contextlib import redirect_stdout

class OutputCapture:
    """Capture stdout during Stata execution"""

    def __init__(self):
        self.buffer = io.StringIO()
        self._original_stdout = None

    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = self.buffer
        return self

    def __exit__(self, *args):
        sys.stdout = self._original_stdout

    def get_output(self) -> str:
        return self.buffer.getvalue()

# Usage in worker:
with OutputCapture() as capture:
    stata.run(command, echo=True)
output = capture.get_output()
```

### Streaming Output (Optional Enhancement)
For long-running commands, stream output periodically:

```python
def execute_with_streaming(self, command: str):
    """Execute command with periodic output streaming"""

    # Use a separate thread to periodically read and send output
    # while main thread executes Stata command

    output_thread = threading.Thread(
        target=self._stream_output,
        args=(self.output_queue,)
    )
    output_thread.start()

    try:
        stata.run(command)
    finally:
        self._stop_streaming = True
        output_thread.join()
```

---

## Error Handling Matrix

| Error Type | Detection | Recovery | User Impact |
|------------|-----------|----------|-------------|
| Worker init failure | result_queue timeout | Retry once, then fail session creation | Error message, retry suggested |
| Worker crash | `process.is_alive() == False` | Remove session, notify user | Session lost, data lost |
| Command timeout | Queue.get timeout | Cancel command, worker remains | Command failed, session preserved |
| Stata error | Exception in `stata.run()` | Capture error, return to user | Error message, session preserved |
| Queue corruption | Exception on put/get | Terminate worker, recreate | Session lost |
| Max sessions reached | `len(sessions) >= max` | Reject new session | Error: "Max sessions reached" |
| Memory exhaustion | Process killed by OS | Detect via is_alive, cleanup | Session lost |

---

## API Design

### New Endpoints

```python
# Session Management
POST   /sessions                    # Create new session
GET    /sessions                    # List all sessions
GET    /sessions/{session_id}       # Get session details
DELETE /sessions/{session_id}       # Destroy session

# Enhanced Execution (backward compatible)
POST   /v1/tools                    # Execute (optional session_id in body)
GET    /run_file                    # Execute file (optional session_id query param)
POST   /run_selection               # Execute code (optional session_id query param)
```

### Request Format

```json
// Existing format (uses default session)
{
    "tool": "stata_run_file",
    "parameters": {
        "file_path": "/path/to/file.do",
        "timeout": 600
    }
}

// New format with session
{
    "tool": "stata_run_file",
    "parameters": {
        "file_path": "/path/to/file.do",
        "timeout": 600,
        "session_id": "abc123"
    }
}
```

### Response Format

```json
// Session creation
{
    "status": "success",
    "session_id": "abc123",
    "message": "Session created successfully"
}

// Session list
{
    "sessions": [
        {
            "session_id": "default",
            "status": "ready",
            "created_at": "2024-01-01T00:00:00Z",
            "last_activity": "2024-01-01T00:01:00Z"
        },
        {
            "session_id": "abc123",
            "status": "busy",
            "created_at": "2024-01-01T00:00:30Z",
            "last_activity": "2024-01-01T00:00:45Z"
        }
    ],
    "max_sessions": 4,
    "available_slots": 2
}
```

---

## Configuration

### New Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `multiSession.enabled` | boolean | `false` | Enable multi-session mode |
| `multiSession.maxSessions` | number | `4` | Maximum concurrent sessions |
| `multiSession.sessionTimeout` | number | `3600` | Session idle timeout (seconds) |
| `multiSession.workerStartTimeout` | number | `60` | Worker init timeout (seconds) |
| `multiSession.commandTimeout` | number | `600` | Default command timeout (seconds) |

### Command Line Arguments

```bash
python stata_mcp_server.py \
    --multi-session \
    --max-sessions 4 \
    --session-timeout 3600
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (Priority: P0)

**Files to create:**
- `src/stata_worker.py` - Worker process implementation
- `src/session_manager.py` - Session lifecycle management

**Estimated effort:** 2-3 days

### Phase 2: API Integration (Priority: P0)

**Files to modify:**
- `src/stata_mcp_server.py` - Add session endpoints, modify execution flow

**Estimated effort:** 1-2 days

### Phase 3: Output Capture (Priority: P1)

**Implement:**
- stdout capture in workers
- Streaming output support
- Log file handling per session

**Estimated effort:** 1 day

### Phase 4: VS Code Extension (Priority: P2)

**Files to modify:**
- `src/extension.js` - Add session management UI/commands

**Estimated effort:** 1 day

### Phase 5: Testing & Documentation (Priority: P0)

**Create:**
- Unit tests for worker and session manager
- Integration tests for multi-session scenarios
- Platform-specific tests (Windows, Mac, Linux)
- Documentation updates

**Estimated effort:** 2-3 days

---

## Risk Assessment

### High Risk
1. **Memory usage**: Each Stata ~200-300MB RAM
   - Mitigation: Limit max sessions, aggressive cleanup

2. **Stata license**: Some licenses limit concurrent instances
   - Mitigation: Document requirement, add startup warning

### Medium Risk
3. **Windows compatibility**: spawn behavior, path handling
   - Mitigation: Test early, use pathlib

4. **Worker startup time**: 5-10s per worker
   - Mitigation: Pre-warm default worker, lazy initialization

### Low Risk
5. **Queue size limits**: Very large outputs
   - Mitigation: Stream to file for large outputs

---

## Testing Strategy

### Unit Tests
- Worker initialization success/failure
- Session creation/destruction
- Command execution and result capture
- Timeout handling
- Error propagation

### Integration Tests
- Multiple sessions with different data
- Parallel execution verification
- Session cleanup after timeout
- Worker crash recovery
- Backward compatibility (no session_id)

### Platform Tests
- macOS (primary development)
- Windows (critical path)
- Linux (CI/server deployments)

### Stress Tests
- Maximum sessions
- Rapid create/destroy cycles
- Long-running commands
- Large output handling

---

## Success Criteria

1. ✅ Multiple Claude Code instances can run Stata commands simultaneously
2. ✅ Each session has isolated state (data, variables, macros)
3. ✅ Backward compatible - existing clients work without changes
4. ✅ Works on Windows, Mac, Linux
5. ✅ Proper cleanup on session timeout/destruction
6. ✅ Clear error messages for session limits/failures
7. ✅ Documentation updated with multi-session usage

---

## Appendix: File Structure

```
src/
├── stata_mcp_server.py      # Main server (modified)
├── stata_worker.py          # NEW: Worker process
├── session_manager.py       # NEW: Session management
└── output_capture.py        # NEW: Output handling

tests/
├── test_multiprocess_pystata.py  # Existing POC
├── test_worker.py                # NEW: Worker unit tests
├── test_session_manager.py       # NEW: Session tests
└── test_integration.py           # NEW: Integration tests

docs/
├── MULTI_SESSION_DESIGN.md       # This document
└── MULTI_SESSION_USAGE.md        # NEW: User guide
```

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024-12-22 | Claude | Initial design document |
| 1.1 | 2024-12-22 | Claude | Added implementation files: stata_worker.py, session_manager.py, test_session_manager.py |
