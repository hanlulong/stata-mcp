#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Manager - Manages multiple Stata worker processes for parallel sessions

This module provides session lifecycle management, request routing, and worker
health monitoring. It enables multiple Claude Code instances to run independent
Stata tasks simultaneously through a single server port.

Key Features:
1. Session creation/destruction with automatic cleanup
2. Request routing to correct worker by session_id
3. Worker health monitoring and automatic restart
4. Backward compatibility via default session (session_id=None uses default)
5. Configurable session limits and timeouts

Architecture:
    SessionManager
        ├── Session "default" (Worker 0) - always exists for backward compatibility
        ├── Session "abc123" (Worker 1) - created on demand
        └── Session "xyz789" (Worker 2) - created on demand
"""

import os
import sys
import time
import uuid
import queue
import logging
import threading
import multiprocessing
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

# Add the script's directory to Python path for stata_worker import
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from stata_worker import (
    worker_process,
    WorkerState,
    CommandType,
    WorkerCommand,
    WorkerResult
)


def join_stata_line_continuations(code: str) -> str:
    """Join lines with Stata line continuation (///) into single logical lines.

    This prevents options like legend(off) from being treated as separate commands
    when code is selected and run.

    Args:
        code: Stata code that may contain /// line continuations

    Returns:
        Code with continuations joined into single lines
    """
    raw_lines = code.splitlines()
    joined_lines = []
    current_line = ""

    for raw_line in raw_lines:
        # Check if line ends with /// (Stata line continuation)
        stripped = raw_line.rstrip()
        if stripped.endswith('///'):
            # Remove /// and append to current line (keep one space)
            current_line += stripped[:-3].rstrip() + " "
        else:
            # No continuation - complete the line
            current_line += raw_line
            joined_lines.append(current_line)
            current_line = ""

    # Handle any remaining content (in case code ends with ///)
    if current_line:
        joined_lines.append(current_line)

    return "\n".join(joined_lines)


class SessionState(Enum):
    """Session lifecycle states"""
    CREATING = "creating"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"


@dataclass
class Session:
    """Represents a Stata session with its worker process"""
    session_id: str
    process: Optional[multiprocessing.Process] = None
    command_queue: Optional[multiprocessing.Queue] = None
    result_queue: Optional[multiprocessing.Queue] = None
    stop_event: Optional[multiprocessing.Event] = None  # For signaling stop without queue race
    state: SessionState = SessionState.CREATING
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    current_command_id: Optional[str] = None
    error_message: str = ""
    is_default: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for API responses"""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "last_activity": datetime.fromtimestamp(self.last_activity).isoformat(),
            "is_busy": self.state == SessionState.BUSY,
            "is_default": self.is_default,
            "error": self.error_message if self.state == SessionState.ERROR else None
        }


class SessionManager:
    """
    Manages multiple Stata worker processes for parallel session support.

    Thread-safe management of worker processes, request routing, and session
    lifecycle. Provides backward compatibility by always maintaining a default
    session for requests without explicit session_id.
    """

    DEFAULT_SESSION_ID = "default"

    def __init__(
        self,
        stata_path: str,
        stata_edition: str = "mp",
        max_sessions: int = 100,
        session_timeout: int = 3600,
        worker_start_timeout: int = 60,
        command_timeout: int = 600,
        enabled: bool = True,
        graphs_dir: str = None
    ):
        """
        Initialize the session manager.

        Args:
            stata_path: Path to Stata installation
            stata_edition: Stata edition (mp, se, be)
            max_sessions: Maximum number of concurrent sessions
            session_timeout: Session idle timeout in seconds
            worker_start_timeout: Worker initialization timeout in seconds
            command_timeout: Default command execution timeout
            enabled: Whether multi-session mode is enabled
            graphs_dir: Directory for graph exports (shared with main server)
        """
        self.stata_path = stata_path
        self.stata_edition = stata_edition
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout
        self.worker_start_timeout = worker_start_timeout
        self.command_timeout = command_timeout
        self.enabled = enabled
        self.graphs_dir = graphs_dir

        self._sessions: Dict[str, Session] = {}
        self._lock = threading.RLock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._shutdown = False

        # Set spawn method for clean process isolation (required for PyStata)
        # Must be called before any Process creation
        try:
            multiprocessing.set_start_method('spawn', force=True)
        except RuntimeError:
            # Already set - that's fine
            pass

        self._logger = logging.getLogger(__name__)

    def start(self) -> bool:
        """
        Start the session manager and create the default session.

        Returns:
            True if started successfully, False otherwise
        """
        if not self.enabled:
            self._logger.info("Multi-session mode disabled, using single-session mode")
            return True

        self._logger.info("Starting session manager...")

        # Create default session for backward compatibility
        try:
            success = self._create_session_internal(
                self.DEFAULT_SESSION_ID,
                is_default=True
            )
            if not success:
                self._logger.error("Failed to create default session")
                return False
        except Exception as e:
            self._logger.error(f"Error creating default session: {e}")
            return False

        # Start cleanup thread
        self._shutdown = False
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="session-cleanup"
        )
        self._cleanup_thread.start()

        self._logger.info("Session manager started successfully")
        return True

    def stop(self):
        """Stop the session manager and destroy all sessions"""
        self._logger.info("Stopping session manager...")
        self._shutdown = True

        # Stop cleanup thread
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5.0)

        # Destroy all sessions
        with self._lock:
            session_ids = list(self._sessions.keys())

        for session_id in session_ids:
            try:
                self.destroy_session(session_id, force=True)
            except Exception as e:
                self._logger.error(f"Error destroying session {session_id}: {e}")

        self._logger.info("Session manager stopped")

    def create_session(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new session.

        Args:
            session_id: Optional session ID. If not provided, a unique ID will be generated.

        Returns:
            Dict with 'success', 'session_id', and 'error' keys
        """
        with self._lock:
            # Check session limit
            active_count = sum(
                1 for s in self._sessions.values()
                if s.state in (SessionState.READY, SessionState.BUSY, SessionState.CREATING)
            )
            if active_count >= self.max_sessions:
                return {"success": False, "session_id": "", "error": f"Maximum sessions ({self.max_sessions}) reached"}

            # Check if session already exists
            if session_id and session_id in self._sessions:
                return {"success": True, "session_id": session_id, "error": ""}

        # Generate unique session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())[:8]

        success = self._create_session_internal(session_id, is_default=False)
        if success:
            return {"success": True, "session_id": session_id, "error": ""}
        else:
            return {"success": False, "session_id": "", "error": "Failed to create worker process"}

    def _create_session_internal(self, session_id: str, is_default: bool = False) -> bool:
        """
        Internal method to create a session and its worker process.

        Args:
            session_id: The session ID to use
            is_default: Whether this is the default session

        Returns:
            True if created successfully
        """
        self._logger.info(f"Creating session {session_id} (default={is_default})")

        # Create queues for IPC
        command_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        stop_event = multiprocessing.Event()  # For signaling stop without queue race

        # Create session object
        session = Session(
            session_id=session_id,
            command_queue=command_queue,
            result_queue=result_queue,
            stop_event=stop_event,
            state=SessionState.CREATING,
            is_default=is_default
        )

        with self._lock:
            self._sessions[session_id] = session

        # Start worker process
        try:
            process = multiprocessing.Process(
                target=worker_process,
                args=(
                    session_id,
                    command_queue,
                    result_queue,
                    self.stata_path,
                    self.stata_edition,
                    self.worker_start_timeout,
                    stop_event,  # Pass stop_event to worker
                    self.graphs_dir  # Pass graphs_dir for graph exports
                ),
                name=f"stata-worker-{session_id}"
            )
            process.start()
            session.process = process

            # Wait for initialization
            try:
                init_result = result_queue.get(timeout=self.worker_start_timeout)

                if init_result.get('status') == 'ready':
                    session.state = SessionState.READY
                    self._logger.info(f"Session {session_id} ready")
                    return True
                else:
                    session.state = SessionState.ERROR
                    session.error_message = init_result.get('error', 'Unknown init error')
                    self._logger.error(f"Session {session_id} init failed: {session.error_message}")
                    self._terminate_worker(session)
                    return False

            except queue.Empty:
                session.state = SessionState.ERROR
                session.error_message = "Worker initialization timeout"
                self._logger.error(f"Session {session_id} init timeout")
                self._terminate_worker(session)
                return False

        except Exception as e:
            session.state = SessionState.ERROR
            session.error_message = str(e)
            self._logger.error(f"Failed to start worker for session {session_id}: {e}")
            return False

    def destroy_session(self, session_id: str, force: bool = False) -> tuple:
        """
        Destroy a session and its worker process.

        Args:
            session_id: The session to destroy
            force: If True, skip graceful shutdown

        Returns:
            tuple: (success: bool, error: str)
        """
        with self._lock:
            if session_id not in self._sessions:
                return False, f"Session {session_id} not found"

            session = self._sessions[session_id]

            # Prevent destroying default session unless forced
            if session.is_default and not force:
                return False, "Cannot destroy default session"

            session.state = SessionState.DESTROYING

        # Graceful shutdown
        if not force and session.command_queue:
            try:
                session.command_queue.put({
                    'type': CommandType.EXIT.value,
                    'command_id': 'shutdown'
                })
                if session.process:
                    session.process.join(timeout=5.0)
            except Exception:
                pass

        # Force terminate if still alive
        self._terminate_worker(session)

        # Remove from registry
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                session.state = SessionState.DESTROYED

        self._logger.info(f"Session {session_id} destroyed")
        return True, ""

    def _terminate_worker(self, session: Session):
        """Force terminate a worker process"""
        if session.process and session.process.is_alive():
            try:
                session.process.terminate()
                session.process.join(timeout=2.0)
                if session.process.is_alive():
                    session.process.kill()
            except Exception as e:
                self._logger.error(f"Error terminating worker: {e}")

    def get_session(self, session_id: Optional[str] = None) -> Optional[Session]:
        """
        Get a session by ID, or the default session if no ID provided.

        Args:
            session_id: Session ID, or None for default session

        Returns:
            Session object or None if not found
        """
        with self._lock:
            if session_id is None:
                session_id = self.DEFAULT_SESSION_ID
            return self._sessions.get(session_id)

    def wait_for_ready(self, session: Session, timeout: float = 30.0) -> bool:
        """
        Wait for a session to become ready (not busy).

        This helps handle rapid consecutive requests by waiting a short time
        for the previous command to complete instead of immediately returning
        a 'session busy' error.

        Args:
            session: The session to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            True if session became ready, False if timeout
        """
        start_time = time.time()
        poll_interval = 0.1  # Check every 100ms

        while time.time() - start_time < timeout:
            if session.state == SessionState.READY:
                return True
            if session.state in (SessionState.ERROR, SessionState.DESTROYED, SessionState.DESTROYING):
                # Session is in a terminal state, don't wait
                return False
            time.sleep(poll_interval)

        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all active sessions.

        Returns:
            List of session dictionaries
        """
        with self._lock:
            return [
                session.to_dict()
                for session in self._sessions.values()
                if session.state not in (SessionState.DESTROYED, SessionState.DESTROYING)
            ]

    def execute(
        self,
        code: str,
        session_id: Optional[str] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Execute Stata code in a session.

        Args:
            code: Stata code to execute
            session_id: Target session ID (None for default)
            timeout: Execution timeout in seconds

        Returns:
            Result dictionary with status, output, error
        """
        session = self.get_session(session_id)
        if not session:
            # Auto-create session on demand if session_id is provided
            if session_id and session_id != self.DEFAULT_SESSION_ID:
                self._logger.info(f"Auto-creating session: {session_id}")
                create_result = self.create_session(session_id)
                if not create_result.get('success'):
                    return {
                        "status": "error",
                        "error": f"Failed to auto-create session: {create_result.get('error', 'Unknown error')}"
                    }
                session = self.get_session(session_id)
                if not session:
                    return {
                        "status": "error",
                        "error": f"Session creation succeeded but session not found: {session_id}"
                    }
            else:
                return {
                    "status": "error",
                    "error": f"Session not found: {session_id or 'default'}"
                }

        # If session is busy, auto-create a new session for parallel execution
        if session.state == SessionState.BUSY:
            self._logger.info(f"Session {session.session_id} is busy, creating new session for parallel execution")
            new_session_id = str(uuid.uuid4())[:8]
            create_result = self.create_session(new_session_id)
            if create_result.get('success'):
                session = self.get_session(new_session_id)
                if session is None:
                    return {
                        "status": "error",
                        "error": "Failed to get newly created session"
                    }
                self._logger.info(f"Using new session {new_session_id} for parallel execution")
            else:
                return {
                    "status": "error",
                    "error": f"Session busy and failed to create new session: {create_result.get('error', 'Unknown error')}"
                }
        elif session.state != SessionState.READY:
            return {
                "status": "error",
                "error": f"Session not ready: {session.state.value}"
            }

        # Process line continuations (///) before execution
        processed_code = join_stata_line_continuations(code)
        return self._execute_command(
            session,
            CommandType.EXECUTE,
            {"code": processed_code, "timeout": timeout or self.command_timeout},
            timeout or self.command_timeout
        )

    def execute_file(
        self,
        file_path: str,
        session_id: Optional[str] = None,
        timeout: Optional[float] = None,
        log_file: Optional[str] = None,
        working_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a .do file in a session.

        Args:
            file_path: Path to .do file
            session_id: Target session ID (None for default)
            timeout: Execution timeout in seconds
            log_file: Optional path to log file for streaming support
            working_dir: Working directory to cd to before running (affects where outputs are saved).
                         If None, defaults to the .do file's directory.

        Returns:
            Result dictionary with status, output, error, log_file
        """
        session = self.get_session(session_id)
        if not session:
            # Auto-create session on demand if session_id is provided
            if session_id and session_id != self.DEFAULT_SESSION_ID:
                self._logger.info(f"Auto-creating session: {session_id}")
                create_result = self.create_session(session_id)
                if not create_result.get('success'):
                    return {
                        "status": "error",
                        "error": f"Failed to auto-create session: {create_result.get('error', 'Unknown error')}"
                    }
                session = self.get_session(session_id)
                if not session:
                    return {
                        "status": "error",
                        "error": f"Session creation succeeded but session not found: {session_id}"
                    }
            else:
                return {
                    "status": "error",
                    "error": f"Session not found: {session_id or 'default'}"
                }

        # If session is busy, auto-create a new session for parallel execution
        if session.state == SessionState.BUSY:
            self._logger.info(f"Session {session.session_id} is busy, creating new session for parallel file execution")
            new_session_id = str(uuid.uuid4())[:8]
            create_result = self.create_session(new_session_id)
            if create_result.get('success'):
                session = self.get_session(new_session_id)
                if session is None:
                    return {
                        "status": "error",
                        "error": "Failed to get newly created session"
                    }
                self._logger.info(f"Using new session {new_session_id} for parallel file execution")
            else:
                return {
                    "status": "error",
                    "error": f"Session busy and failed to create new session: {create_result.get('error', 'Unknown error')}"
                }
        elif session.state != SessionState.READY:
            return {
                "status": "error",
                "error": f"Session not ready: {session.state.value}"
            }

        # Determine log file path if not provided
        # Include session_id to prevent file locking conflicts in parallel execution
        if log_file is None:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            log_dir = os.path.dirname(os.path.abspath(file_path))
            log_file = os.path.join(log_dir, f"{base_name}_{session.session_id}_mcp.log")

        return self._execute_command(
            session,
            CommandType.EXECUTE_FILE,
            {
                "file_path": file_path,
                "timeout": timeout or self.command_timeout,
                "log_file": log_file,
                "working_dir": working_dir
            },
            timeout or self.command_timeout
        )

    def get_data(
        self,
        session_id: Optional[str] = None,
        if_condition: Optional[str] = None,
        max_rows: int = 10000,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Get current dataset from a session as a dictionary.

        Args:
            session_id: Target session ID (None for default)
            if_condition: Optional Stata if condition for filtering
            max_rows: Maximum number of rows to return (default 10000). User can configure via extension settings.
            timeout: Command timeout in seconds

        Returns:
            Result dictionary with status, data, columns, dtypes, rows, index,
            total_rows, displayed_rows, max_rows
        """
        session = self.get_session(session_id)
        if not session:
            return {
                "status": "error",
                "error": f"Session not found: {session_id or 'default'}"
            }

        if session.state != SessionState.READY:
            return {
                "status": "error",
                "error": f"Session not ready: {session.state.value}"
            }

        result = self._execute_command(
            session,
            CommandType.GET_DATA,
            {"if_condition": if_condition, "max_rows": max_rows},
            timeout or 30.0  # 30 second timeout for data retrieval
        )

        # Extract data from the extra field
        if result.get('status') == 'success' and 'extra' in result:
            extra = result['extra']
            return {
                "status": "success",
                "data": extra.get('data', []),
                "columns": extra.get('columns', []),
                "dtypes": extra.get('dtypes', {}),
                "rows": extra.get('rows', 0),
                "index": extra.get('index', []),
                "total_rows": extra.get('total_rows', extra.get('rows', 0)),
                "displayed_rows": extra.get('displayed_rows', extra.get('rows', 0)),
                "max_rows": extra.get('max_rows', max_rows)
            }
        return result

    def stop_execution(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Stop execution in a session using the stop_event for immediate signaling.

        This method uses a multiprocessing.Event to signal the worker's monitor
        thread to call StataSO_SetBreak(), avoiding race conditions with the
        command queue.

        Note: Always tries to send stop signal even if session isn't marked BUSY,
        because streaming endpoints may run execution in a thread that hasn't
        updated the session state yet.

        Args:
            session_id: Target session ID (None for default)

        Returns:
            Result dictionary
        """
        session = self.get_session(session_id)
        if not session:
            return {"status": "error", "error": "Session not found"}

        was_busy = session.state == SessionState.BUSY

        # Always try stop_event for immediate signaling (handles streaming case)
        # The stop_event approach works even if session state hasn't been updated yet
        if session.stop_event is not None:
            session.stop_event.set()
            self._logger.info(f"Stop event set for session {session.session_id} (was_busy={was_busy})")
            return {"status": "stop_sent", "message": "Stop signal sent via event"}

        # Only check BUSY state for queue-based fallback
        if not was_busy:
            return {"status": "not_running", "message": "No execution running"}

        # Fallback to queue-based stop (backward compatibility)
        return self._execute_command(
            session,
            CommandType.STOP_EXECUTION,
            {},
            timeout=2.0  # Shorter timeout for stop command
        )

    def _execute_command(
        self,
        session: Session,
        command_type: CommandType,
        payload: Dict[str, Any],
        timeout: float
    ) -> Dict[str, Any]:
        """
        Execute a command in a session's worker.

        Args:
            session: Target session
            command_type: Type of command
            payload: Command payload
            timeout: Timeout in seconds

        Returns:
            Result dictionary
        """
        command_id = str(uuid.uuid4())[:8]

        # Check worker health
        if session.process and not session.process.is_alive():
            session.state = SessionState.ERROR
            session.error_message = "Worker process died"
            return {"status": "error", "error": "Worker process died"}

        # Update session state
        with self._lock:
            if command_type in (CommandType.EXECUTE, CommandType.EXECUTE_FILE):
                session.state = SessionState.BUSY
            session.current_command_id = command_id
            session.last_activity = time.time()

        try:
            # Send command
            session.command_queue.put({
                'type': command_type.value,
                'command_id': command_id,
                'payload': payload
            })

            # Wait for result - loop to find matching command_id
            # (Drains any leftover results from stop signals or previous cancelled commands)
            try:
                start_wait = time.time()
                deadline = start_wait + timeout + 5.0
                result = None

                while time.time() < deadline:
                    remaining_timeout = deadline - time.time()
                    if remaining_timeout <= 0:
                        break

                    try:
                        candidate = session.result_queue.get(timeout=min(remaining_timeout, 1.0))
                        candidate_id = candidate.get('command_id', '')

                        # Check if this result matches our command
                        if candidate_id == command_id:
                            result = candidate
                            break
                        else:
                            # Discard results from stop signals or previous commands
                            self._logger.debug(
                                f"Discarding stale result with command_id={candidate_id} "
                                f"(expected {command_id})"
                            )
                            continue
                    except queue.Empty:
                        # No result yet, keep waiting until deadline
                        continue

                if result is None:
                    raise queue.Empty()

                # Update session state
                with self._lock:
                    session.state = SessionState.READY
                    session.current_command_id = None
                    session.last_activity = time.time()

                # Get extra data (includes log_file for file execution)
                extra = result.get('extra', {})

                return {
                    "status": result.get('status', 'unknown'),
                    "output": result.get('output', ''),
                    "error": result.get('error', ''),
                    "execution_time": result.get('execution_time', 0),
                    "session_id": session.session_id,
                    "log_file": extra.get('log_file', ''),
                    "extra": extra
                }

            except queue.Empty:
                with self._lock:
                    session.state = SessionState.READY
                    session.current_command_id = None

                return {
                    "status": "timeout",
                    "error": f"Command timeout after {timeout}s",
                    "session_id": session.session_id
                }

        except Exception as e:
            with self._lock:
                session.state = SessionState.ERROR
                session.error_message = str(e)

            return {
                "status": "error",
                "error": str(e),
                "session_id": session.session_id
            }

    def _cleanup_loop(self):
        """Background thread for session cleanup"""
        while not self._shutdown:
            try:
                self._check_sessions()
                time.sleep(60)  # Check every minute
            except Exception as e:
                self._logger.error(f"Cleanup loop error: {e}")

    def _check_sessions(self):
        """Check session health and cleanup idle sessions"""
        current_time = time.time()

        with self._lock:
            sessions_to_check = list(self._sessions.items())

        for session_id, session in sessions_to_check:
            # Skip default session for timeout cleanup
            if session.is_default:
                continue

            # Check for idle timeout
            if (session.state == SessionState.READY and
                current_time - session.last_activity > self.session_timeout):
                self._logger.info(f"Session {session_id} idle timeout, destroying")
                self.destroy_session(session_id)
                continue

            # Check worker health
            if session.process and not session.process.is_alive():
                if session.state not in (SessionState.DESTROYED, SessionState.DESTROYING):
                    self._logger.warning(f"Session {session_id} worker died unexpectedly")
                    session.state = SessionState.ERROR
                    session.error_message = "Worker process died"

    @property
    def available_slots(self) -> int:
        """Number of available session slots"""
        with self._lock:
            active_count = sum(
                1 for s in self._sessions.values()
                if s.state in (SessionState.READY, SessionState.BUSY, SessionState.CREATING)
            )
            return max(0, self.max_sessions - active_count)

    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics"""
        with self._lock:
            sessions = list(self._sessions.values())

        return {
            "enabled": self.enabled,
            "total_sessions": len(sessions),
            "active_sessions": sum(1 for s in sessions if s.state == SessionState.READY),
            "busy_sessions": sum(1 for s in sessions if s.state == SessionState.BUSY),
            "max_sessions": self.max_sessions,
            "available_slots": self.available_slots,
            "session_timeout": self.session_timeout
        }


# Singleton instance for the server
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> Optional[SessionManager]:
    """Get the global session manager instance"""
    return _session_manager


def init_session_manager(
    stata_path: str,
    stata_edition: str = "mp",
    **kwargs
) -> SessionManager:
    """
    Initialize the global session manager.

    Args:
        stata_path: Path to Stata installation
        stata_edition: Stata edition
        **kwargs: Additional SessionManager parameters

    Returns:
        The initialized SessionManager
    """
    global _session_manager
    _session_manager = SessionManager(
        stata_path=stata_path,
        stata_edition=stata_edition,
        **kwargs
    )
    return _session_manager


# For testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG)

    stata_path = "/Applications/StataNow"

    print("Initializing session manager...")
    manager = init_session_manager(
        stata_path=stata_path,
        stata_edition="mp",
        max_sessions=4,
        enabled=True
    )

    if manager.start():
        print("Session manager started!")

        # Test execution on default session
        print("\nTesting default session...")
        result = manager.execute('display "Hello from default session!"')
        print(f"Result: {result}")

        # Create a new session
        print("\nCreating new session...")
        create_result = manager.create_session()
        if create_result.get("success"):
            new_session_id = create_result.get("session_id")
            print(f"Created session: {new_session_id}")

            # Execute on new session
            result = manager.execute('display "Hello from new session!"', session_id=new_session_id)
            print(f"Result: {result}")

            # Destroy session
            manager.destroy_session(new_session_id)
            print(f"Destroyed session: {new_session_id}")

        # List sessions
        print("\nActive sessions:")
        for session in manager.list_sessions():
            print(f"  - {session}")

        # Stop manager
        manager.stop()
        print("\nSession manager stopped")

    else:
        print("Failed to start session manager")
        sys.exit(1)
