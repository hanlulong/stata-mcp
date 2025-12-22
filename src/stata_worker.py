#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stata Worker Process - Independent PyStata instance for parallel session support

Each worker runs in a separate process with its own PyStata instance, providing
complete state isolation (data, variables, macros) between sessions.

Key Design Decisions:
1. Uses multiprocessing.Queue for IPC (thread-safe, handles serialization)
2. Requires 'spawn' start method for clean process isolation (set in session_manager)
3. Worker lifecycle: CREATED -> INITIALIZING -> READY <-> BUSY -> STOPPED
4. Output capture via stdout redirection during Stata execution
"""

import os
import sys
import io
import re
import time
import queue
import platform
import traceback
import threading
from typing import Optional, Dict, Any
from enum import Enum


def deduplicate_break_messages(output: str) -> str:
    """Remove duplicate --Break-- messages from Stata output."""
    if not output or '--Break--' not in output:
        return output
    # Collapse multiple break messages into one
    return re.sub(r'(--Break--\s*\n\s*r\(1\);\s*\n?)+', '--Break--\nr(1);\n', output)


from contextlib import redirect_stdout
from dataclasses import dataclass, field


class WorkerState(Enum):
    """Worker lifecycle states"""
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    STOPPING = "stopping"
    STOPPED = "stopped"
    INIT_FAILED = "init_failed"


class CommandType(Enum):
    """Types of commands that can be sent to a worker"""
    EXECUTE = "execute"          # Execute Stata code
    EXECUTE_FILE = "execute_file"  # Execute a .do file
    GET_STATUS = "get_status"    # Get worker status
    STOP_EXECUTION = "stop"      # Interrupt current execution
    EXIT = "exit"                # Shutdown worker


@dataclass
class WorkerCommand:
    """Command message sent to worker"""
    type: CommandType
    payload: Dict[str, Any] = field(default_factory=dict)
    command_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class WorkerResult:
    """Result message returned from worker"""
    command_id: str
    status: str  # "success", "error", "cancelled", "timeout"
    output: str = ""
    error: str = ""
    execution_time: float = 0.0
    worker_id: str = ""
    worker_state: str = ""
    timestamp: float = field(default_factory=time.time)
    extra: Dict[str, Any] = field(default_factory=dict)


class OutputCapture:
    """Capture stdout during Stata execution with optional streaming"""

    def __init__(self, stream_callback=None):
        """
        Args:
            stream_callback: Optional callable(str) for streaming output chunks
        """
        self.buffer = io.StringIO()
        self._original_stdout = None
        self._stream_callback = stream_callback
        self._lock = threading.Lock()

    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = self
        return self

    def __exit__(self, *args):
        sys.stdout = self._original_stdout

    def write(self, text):
        """Write to buffer and optionally stream"""
        with self._lock:
            self.buffer.write(text)
            if self._stream_callback and text.strip():
                try:
                    self._stream_callback(text)
                except Exception:
                    pass  # Don't let streaming errors affect execution

    def flush(self):
        """Flush the buffer"""
        self.buffer.flush()
        if self._original_stdout:
            self._original_stdout.flush()

    def get_output(self) -> str:
        """Get all captured output"""
        return self.buffer.getvalue()

    def get_and_clear(self) -> str:
        """Get output and clear buffer (for streaming)"""
        with self._lock:
            output = self.buffer.getvalue()
            self.buffer = io.StringIO()
            return output


def worker_process(
    worker_id: str,
    command_queue,  # multiprocessing.Queue
    result_queue,   # multiprocessing.Queue
    stata_path: str,
    stata_edition: str = "mp",
    init_timeout: float = 60.0,
    stop_event=None  # multiprocessing.Event for stop signaling
):
    """
    Main worker process function - runs in a separate process.

    Each worker initializes its own PyStata instance and processes commands
    from the command queue, sending results back via the result queue.

    Args:
        worker_id: Unique identifier for this worker
        command_queue: Queue to receive commands from main process
        result_queue: Queue to send results back to main process
        stata_path: Path to Stata installation
        stata_edition: Stata edition (mp, se, be)
        init_timeout: Timeout for Stata initialization
        stop_event: Optional Event for signaling stop (avoids queue race condition)
    """
    # CRITICAL: Redirect stdout to devnull immediately to prevent worker output
    # from appearing in parent process stdout (which VS Code pipes to output channel).
    # This prevents duplicate output - the SSE stream is the only output path.
    original_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w')

    worker_state = WorkerState.CREATED
    stata = None
    stlib = None
    cancelled = False

    def send_result(command_id: str, status: str, output: str = "", error: str = "",
                    execution_time: float = 0.0, extra: Dict = None):
        """Helper to send result back to main process"""
        result = WorkerResult(
            command_id=command_id,
            status=status,
            output=output,
            error=error,
            execution_time=execution_time,
            worker_id=worker_id,
            worker_state=worker_state.value,
            extra=extra or {}
        )
        result_queue.put(result.__dict__)

    def initialize_stata():
        """Initialize PyStata in this worker process"""
        nonlocal stata, stlib, worker_state

        worker_state = WorkerState.INITIALIZING

        try:
            # Add Stata utilities paths - required for pystata import
            utilities_path = os.path.join(stata_path, "utilities", "pystata")
            utilities_parent = os.path.join(stata_path, "utilities")

            if os.path.exists(utilities_path):
                sys.path.insert(0, utilities_path)
            if os.path.exists(utilities_parent):
                sys.path.insert(0, utilities_parent)

            # Set environment variables
            os.environ['SYSDIR_STATA'] = stata_path

            # Set Java headless mode on Mac to prevent Dock icon
            if platform.system() == 'Darwin':
                os.environ['_JAVA_OPTIONS'] = '-Djava.awt.headless=true'

            # Initialize PyStata configuration
            from pystata import config
            config.init(stata_edition)

            # Import stata module after initialization
            from pystata import stata as stata_module
            stata = stata_module

            # Get stlib for stop/break functionality
            from pystata.config import stlib as stlib_module
            stlib = stlib_module

            # On Windows, redirect PyStata's output to devnull as well
            # to prevent duplicate output (we capture output via log files, not stdout)
            if platform.system() == 'Windows':
                # Create a devnull text wrapper for PyStata output
                devnull_file = open(os.devnull, 'w', encoding='utf-8')
                config.stoutputf = devnull_file

            worker_state = WorkerState.READY
            return True

        except Exception as e:
            worker_state = WorkerState.INIT_FAILED
            error_msg = f"Failed to initialize Stata: {str(e)}\n{traceback.format_exc()}"
            return False, error_msg

    # Flag to prevent multiple SetBreak calls - declared here for visibility
    stop_already_sent = False

    def execute_stata_code(code: str, timeout: float = 600.0) -> tuple:
        """
        Execute Stata code with output capture and timeout support.

        Returns:
            tuple: (success: bool, output: str, error: str, execution_time: float)
        """
        nonlocal worker_state, cancelled, stop_already_sent

        if stata is None:
            return False, "", "Stata not initialized", 0.0

        worker_state = WorkerState.BUSY
        # IMPORTANT: Clear stop_event FIRST to prevent race condition with monitor thread
        # If we reset cancelled/stop_already_sent first, monitor could catch stale signal
        # and set cancelled=True between our reset and clear
        if stop_event is not None:
            stop_event.clear()
        cancelled = False
        stop_already_sent = False  # Reset for new execution
        start_time = time.time()

        try:
            with OutputCapture() as capture:
                stata.run(code, echo=True)

            output = capture.get_output()
            execution_time = time.time() - start_time
            worker_state = WorkerState.READY

            # Deduplicate break messages
            output = deduplicate_break_messages(output)

            # Check if execution was cancelled
            if cancelled or "--Break--" in output:
                return False, output, "Execution cancelled", execution_time

            return True, output, "", execution_time

        except Exception as e:
            execution_time = time.time() - start_time
            worker_state = WorkerState.READY
            error_str = str(e)

            # Check if this was a user-initiated break
            if "--Break--" in error_str or cancelled:
                return False, "", "Execution cancelled", execution_time

            return False, "", error_str, execution_time

    def execute_stata_file(file_path: str, timeout: float = 600.0, log_file: str = None) -> tuple:
        """
        Execute a .do file with log file support for streaming.

        When log_file is provided, wraps the execution with log commands so the
        output can be monitored in real-time for streaming.

        Returns:
            tuple: (success: bool, output: str, error: str, execution_time: float, log_file: str)
        """
        nonlocal worker_state, cancelled, stop_already_sent

        if not os.path.exists(file_path):
            return False, "", f"File not found: {file_path}", 0.0, ""

        if stata is None:
            return False, "", "Stata not initialized", 0.0, ""

        # Determine log file path
        if log_file is None:
            # Create log file next to the do file
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            log_dir = os.path.dirname(os.path.abspath(file_path))
            log_file = os.path.join(log_dir, f"{base_name}_mcp.log")

        worker_state = WorkerState.BUSY
        # IMPORTANT: Clear stop_event FIRST to prevent race condition with monitor thread
        # If we reset cancelled/stop_already_sent first, monitor could catch stale signal
        # and set cancelled=True between our reset and clear
        if stop_event is not None:
            stop_event.clear()
        cancelled = False
        stop_already_sent = False  # Reset for new execution
        start_time = time.time()

        try:
            # Read the original do file
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                original_code = f.read()

            # Wrap with log commands for streaming support
            wrapped_code = f"""capture log close _all
capture program drop _all
capture macro drop _all
log using "{log_file}", replace text
{original_code}
capture log close _all
"""

            # Execute with output capture
            with OutputCapture() as capture:
                stata.run(wrapped_code, echo=True, inline=False)

            output = capture.get_output()
            execution_time = time.time() - start_time
            worker_state = WorkerState.READY

            # Also read the log file if it exists for complete output
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                        log_output = f.read()
                    # Use log file content as primary output (more reliable for streaming)
                    if log_output.strip():
                        output = log_output
                except Exception:
                    pass  # Fall back to captured output

            # Deduplicate break messages (Stata may output multiple when breaking nested commands)
            output = deduplicate_break_messages(output)

            if cancelled or "--Break--" in output:
                return False, output, "Execution cancelled", execution_time, log_file

            return True, output, "", execution_time, log_file

        except Exception as e:
            execution_time = time.time() - start_time
            worker_state = WorkerState.READY
            error_str = str(e)

            if "--Break--" in error_str or cancelled:
                return False, "", "Execution cancelled", execution_time, log_file

            return False, "", error_str, execution_time, log_file

    def handle_stop():
        """Handle stop/break request - ONLY call when worker is actually executing.

        IMPORTANT: Only call StataSO_SetBreak() ONCE to avoid corrupting Stata's
        internal state. Multiple calls can cause SIGSEGV crashes.
        """
        nonlocal cancelled, stop_already_sent

        # Prevent multiple SetBreak calls for the same execution
        if stop_already_sent:
            return True  # Already sent, don't send again

        # Only send break if we're actually executing something
        if worker_state != WorkerState.BUSY:
            return False  # Not executing, nothing to stop

        cancelled = True
        stop_already_sent = True

        if stlib is not None:
            try:
                # Call SetBreak only ONCE - multiple calls can crash Stata
                # with SIGSEGV in dsa_putdtaobs or similar functions
                stlib.StataSO_SetBreak()
                return True
            except Exception:
                pass
        return False

    # === Stop Signal Monitor Thread ===
    # This thread monitors the stop_event (if provided) to interrupt execution
    # Uses a separate Event to avoid race conditions with the command queue
    stop_monitor_running = True

    def stop_monitor_thread():
        """Background thread that monitors stop_event during execution"""
        nonlocal stop_monitor_running

        while stop_monitor_running:
            try:
                # Check if stop_event is set (non-blocking check every 100ms)
                if stop_event is not None and stop_event.is_set():
                    # Clear the event first to prevent re-triggering
                    stop_event.clear()

                    # Only try to stop if worker is actually busy executing
                    if worker_state == WorkerState.BUSY:
                        if handle_stop():
                            send_result("_stop", "stopped", "Stop signal sent to Stata")
                        else:
                            send_result("_stop", "stop_skipped", "Stop already sent or not executing")
                    # If not busy, just ignore the stop request silently

                # Small sleep to avoid busy-waiting
                time.sleep(0.1)

            except Exception as e:
                # Log but continue - monitor thread must stay alive for stop functionality
                import traceback
                traceback.print_exc()
                time.sleep(0.5)  # Longer sleep on error to avoid spam

    # Start the stop monitor thread only if stop_event is provided
    monitor_thread = None
    if stop_event is not None:
        monitor_thread = threading.Thread(target=stop_monitor_thread, daemon=True)
        monitor_thread.start()

    # === Main Worker Loop ===

    try:
        # Initialize Stata
        init_result = initialize_stata()

        if init_result is True:
            send_result(
                command_id="_init",
                status="ready",
                output=f"Worker {worker_id} initialized successfully"
            )
        else:
            success, error_msg = init_result
            send_result(
                command_id="_init",
                status="init_failed",
                error=error_msg
            )
            return  # Exit worker process

        # Process commands
        while worker_state not in (WorkerState.STOPPED, WorkerState.STOPPING):
            try:
                # Get command with timeout (allows checking for shutdown)
                try:
                    cmd_dict = command_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                # Parse command
                cmd_type = CommandType(cmd_dict.get('type', 'execute'))
                cmd_id = cmd_dict.get('command_id', '')
                payload = cmd_dict.get('payload', {})

                if cmd_type == CommandType.EXIT:
                    worker_state = WorkerState.STOPPING
                    send_result(
                        command_id=cmd_id,
                        status="exiting",
                        output=f"Worker {worker_id} shutting down"
                    )
                    break

                elif cmd_type == CommandType.GET_STATUS:
                    send_result(
                        command_id=cmd_id,
                        status="status",
                        extra={
                            "state": worker_state.value,
                            "stata_available": stata is not None,
                            "worker_id": worker_id
                        }
                    )

                elif cmd_type == CommandType.STOP_EXECUTION:
                    # Note: Most STOP commands are handled by the monitor thread during execution.
                    # This branch handles STOP when no command is currently executing.
                    if worker_state == WorkerState.BUSY:
                        # Unlikely to reach here - monitor thread should handle it
                        if handle_stop():
                            send_result(cmd_id, "stopped", "Stop signal sent")
                        else:
                            send_result(cmd_id, "stop_sent", "Stop signal attempted")
                    else:
                        send_result(cmd_id, "not_running", "No execution in progress")

                elif cmd_type == CommandType.EXECUTE:
                    code = payload.get('code', '')
                    timeout = payload.get('timeout', 600.0)

                    success, output, error, exec_time = execute_stata_code(code, timeout)
                    send_result(
                        command_id=cmd_id,
                        status="success" if success else "error",
                        output=output,
                        error=error,
                        execution_time=exec_time
                    )

                elif cmd_type == CommandType.EXECUTE_FILE:
                    file_path = payload.get('file_path', '')
                    timeout = payload.get('timeout', 600.0)
                    log_file = payload.get('log_file', None)

                    success, output, error, exec_time, actual_log_file = execute_stata_file(
                        file_path, timeout, log_file
                    )
                    send_result(
                        command_id=cmd_id,
                        status="success" if success else "error",
                        output=output,
                        error=error,
                        execution_time=exec_time,
                        extra={"file_path": file_path, "log_file": actual_log_file}
                    )

                else:
                    send_result(
                        command_id=cmd_id,
                        status="error",
                        error=f"Unknown command type: {cmd_type}"
                    )

            except Exception as loop_error:
                # Log but continue processing
                try:
                    send_result(
                        command_id=cmd_id if 'cmd_id' in dir() else "_error",
                        status="error",
                        error=f"Worker loop error: {str(loop_error)}"
                    )
                except Exception:
                    pass

    except Exception as fatal_error:
        # Fatal error - try to notify main process
        try:
            send_result(
                command_id="_fatal",
                status="fatal",
                error=f"Worker fatal error: {str(fatal_error)}\n{traceback.format_exc()}"
            )
        except Exception:
            pass

    finally:
        # Stop the monitor thread
        stop_monitor_running = False
        if monitor_thread is not None and monitor_thread.is_alive():
            monitor_thread.join(timeout=1.0)
        worker_state = WorkerState.STOPPED


# For testing worker independently
if __name__ == "__main__":
    import multiprocessing

    # Must use spawn for clean process isolation
    multiprocessing.set_start_method('spawn', force=True)

    # Create test queues
    cmd_q = multiprocessing.Queue()
    result_q = multiprocessing.Queue()

    # Default Stata path for Mac
    stata_path = "/Applications/StataNow"

    print("Starting test worker...")
    p = multiprocessing.Process(
        target=worker_process,
        args=("test_worker", cmd_q, result_q, stata_path, "mp")
    )
    p.start()

    # Wait for initialization
    try:
        init_result = result_q.get(timeout=60)
        print(f"Init result: {init_result}")

        if init_result.get('status') == 'ready':
            # Test execution
            cmd_q.put({
                'type': 'execute',
                'command_id': 'test_1',
                'payload': {'code': 'display "Hello from worker!"'}
            })

            result = result_q.get(timeout=30)
            print(f"Execution result: {result}")

            # Exit worker
            cmd_q.put({'type': 'exit', 'command_id': 'exit_1'})

    except queue.Empty:
        print("Timeout waiting for worker")

    p.join(timeout=5)
    if p.is_alive():
        p.terminate()

    print("Test complete")
