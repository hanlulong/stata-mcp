#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stata Worker Process - Two modes for different use cases

Mode 1: PyStata Mode (default session)
- Uses PyStata library for direct Stata integration
- Better performance, persistent state within session
- Single instance due to PyStata's global state limitation

Mode 2: Subprocess Mode (parallel sessions)
- Launches independent Stata processes via command line
- True parallelism with complete process isolation
- Each session runs in its own Stata executable
- Stateless: each command runs fresh (no persistent data between commands)

Key Design Decisions:
1. Uses multiprocessing.Queue for IPC (thread-safe, handles serialization)
2. Subprocess mode uses `stata -b do file.do` for true isolation
3. Worker lifecycle: CREATED -> INITIALIZING -> READY <-> BUSY -> STOPPED
4. Output capture via log files for reliable output handling
"""

import os
import sys
import io
import re
import time
import queue
import logging
import platform
import traceback
import threading
import tempfile
import shutil
from typing import Optional, Dict, Any, Tuple
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
    GET_DATA = "get_data"        # Get current dataset as DataFrame
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


def reset_graph_tracking(stlib) -> bool:
    """Reset graph tracking before command execution.

    Clears the graph list and re-enables tracking so only NEW graphs
    created after this call will be detected.

    Args:
        stlib: The pystata.config.stlib module

    Returns:
        True if successful, False otherwise
    """
    try:
        from pystata.config import get_encode_str
        # Reset by turning off then on - this clears the tracking list
        stlib.StataSO_Execute(get_encode_str("qui _gr_list off"), False)
        stlib.StataSO_Execute(get_encode_str("qui _gr_list on"), False)
        return True
    except Exception:
        return False


def detect_and_export_graphs_worker(stata, stlib, graphs_dir: str) -> list:
    """Detect and export graphs created during Stata execution.

    Uses _gr_list low-level API to get list of graphs, then exports each one.
    This approach works on both Windows and Mac.

    Note: Call reset_graph_tracking() BEFORE execution to ensure only NEW graphs
    are detected (the reset clears the tracking list).

    Args:
        stata: The pystata.stata module
        stlib: The pystata.config.stlib module for low-level operations
        graphs_dir: Directory to export graphs to

    Returns:
        List of graph info dicts: [{"name": "Graph", "path": "/path/to/graph.png"}, ...]
    """
    logging.debug(f"detect_and_export_graphs_worker: Platform={platform.system()}, graphs_dir={graphs_dir}")

    if stata is None or stlib is None:
        logging.debug("detect_and_export_graphs_worker: stata or stlib is None, returning empty list")
        return []

    try:
        # Import required modules for low-level API
        import sfi
        from pystata.config import get_encode_str

        # Use _gr_list low-level API to get graph names (same approach as Mac)
        logging.debug("detect_and_export_graphs_worker: Using _gr_list to get graph list...")

        # Get the list of graphs using _gr_list
        rc = stlib.StataSO_Execute(get_encode_str("qui _gr_list list"), False)
        logging.debug(f"detect_and_export_graphs_worker: _gr_list list returned rc={rc}")

        # Get the graph names from the r(_grlist) macro
        gnamelist = sfi.Macro.getGlobal("r(_grlist)")
        logging.debug(f"detect_and_export_graphs_worker: r(_grlist) = {repr(gnamelist)}")

        if not gnamelist or not gnamelist.strip():
            logging.debug("detect_and_export_graphs_worker: No graphs found (gnamelist is empty)")
            return []

        graph_names = gnamelist.strip().split()
        logging.info(f"detect_and_export_graphs_worker: Found {len(graph_names)} graph(s): {graph_names}")

        graphs_info = []

        # Create graphs directory
        os.makedirs(graphs_dir, exist_ok=True)

        # Export each graph to PNG using low-level API
        for gname in graph_names:
            try:
                # First display the graph to make it the active window
                # This is required before export, especially for non-current graphs
                display_cmd = f'quietly graph display {gname}'
                rc = stlib.StataSO_Execute(get_encode_str(display_cmd), False)
                if rc != 0:
                    logging.debug(f"Graph display warning for '{gname}': rc={rc}")
                    # Continue to try export anyway

                # Export as PNG using low-level API
                # Use forward slashes in path to avoid Stata interpreting backslashes as escape sequences
                graph_file = os.path.join(graphs_dir, f'{gname}.png')
                graph_file_stata = graph_file.replace('\\', '/')
                export_cmd = f'quietly graph export "{graph_file_stata}", name({gname}) replace width(800) height(600)'

                logging.debug(f"Exporting graph '{gname}' with command: {export_cmd}")

                rc = stlib.StataSO_Execute(get_encode_str(export_cmd), False)
                if rc != 0:
                    logging.error(f"Graph export failed for '{gname}': rc={rc}")
                    continue

                # Verify the file was actually created
                if os.path.exists(graph_file):
                    file_size = os.path.getsize(graph_file)
                    if file_size > 0:
                        # Normalize path to forward slashes for cross-platform compatibility
                        normalized_path = graph_file.replace('\\', '/')
                        graphs_info.append({
                            "name": gname,
                            "path": normalized_path
                        })
                        logging.info(f"Successfully exported graph '{gname}' ({file_size} bytes) to {normalized_path}")
                    else:
                        logging.warning(f"Graph file created but empty: {graph_file}")
                else:
                    logging.warning(f"Graph file not found after export: {graph_file}")
                    # List directory contents for debugging
                    if os.path.exists(graphs_dir):
                        available = os.listdir(graphs_dir)
                        logging.debug(f"Available files in {graphs_dir}: {available}")
            except Exception as e:
                logging.error(f"Error processing graph '{gname}': {e}")
                continue

        logging.info(f"Graph detection complete: {len(graphs_info)} graphs exported")
        return graphs_info

    except Exception as e:
        logging.error(f"Graph detection failed: {e}")
        logging.debug(f"Exception details: {traceback.format_exc()}")
        return []


def worker_process(
    worker_id: str,
    command_queue,  # multiprocessing.Queue
    result_queue,   # multiprocessing.Queue
    stata_path: str,
    stata_edition: str = "mp",
    init_timeout: float = 60.0,
    stop_event=None,  # multiprocessing.Event for stop signaling
    graphs_dir: str = None  # Directory to export graphs (shared with main server)
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
    # Set up worker-specific logging to a file (since stdout is redirected)
    # This helps debug issues in the worker process
    # NOTE: Must create a new logger since parent process may have already configured root logger
    worker_log_file = os.path.join(tempfile.gettempdir(), f'stata_worker_{worker_id}.log')

    # Create a dedicated logger for this worker (not root logger)
    worker_logger = logging.getLogger(f'stata_worker_{worker_id}')
    worker_logger.setLevel(logging.DEBUG)
    # Remove any existing handlers
    worker_logger.handlers = []
    # Add file handler
    file_handler = logging.FileHandler(worker_log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(f'%(asctime)s - worker-{worker_id} - %(levelname)s - %(message)s'))
    worker_logger.addHandler(file_handler)
    worker_logger.info(f"Worker {worker_id} started, logging to {worker_log_file}")

    # Also set the root logger to use this for convenience in other functions
    logging.root.handlers = [file_handler]
    logging.root.setLevel(logging.DEBUG)

    # CRITICAL: Redirect stdout to devnull immediately to prevent worker output
    # from appearing in parent process stdout (which VS Code pipes to output channel).
    # This prevents duplicate output - the SSE stream is the only output path.
    original_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w')

    worker_state = WorkerState.CREATED
    stata = None
    stlib = None
    cancelled = False
    worker_temp_dir = None  # Track temp directory for cleanup

    # Set default graphs directory if not provided
    if graphs_dir is None:
        graphs_dir = os.path.join(tempfile.gettempdir(), 'stata_mcp_graphs')
    os.makedirs(graphs_dir, exist_ok=True)

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
        """Initialize PyStata in this worker process with proper isolation for parallelism"""
        nonlocal stata, stlib, worker_state, worker_temp_dir

        worker_state = WorkerState.INITIALIZING

        try:
            # === CRITICAL FOR PARALLELISM ===
            # Create a unique temp directory for this worker to isolate Stata's temp files
            # This prevents file locking conflicts between parallel workers
            worker_temp_dir = tempfile.mkdtemp(prefix=f"stata_worker_{worker_id}_")

            # Set environment variables for isolation BEFORE importing pystata
            os.environ['SYSDIR_STATA'] = stata_path
            os.environ['STATATMP'] = worker_temp_dir  # Stata temp directory
            os.environ['TMPDIR'] = worker_temp_dir    # Unix temp
            os.environ['TEMP'] = worker_temp_dir      # Windows temp
            os.environ['TMP'] = worker_temp_dir       # Windows temp alt

            # Add Stata utilities paths - required for pystata import
            utilities_path = os.path.join(stata_path, "utilities", "pystata")
            utilities_parent = os.path.join(stata_path, "utilities")

            if os.path.exists(utilities_path):
                sys.path.insert(0, utilities_path)
            if os.path.exists(utilities_parent):
                sys.path.insert(0, utilities_parent)

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

            # === SET UNIQUE RANDOM SEED FOR THIS WORKER ===
            # This ensures each parallel session has independent random state
            # Use worker_id hash + current time for uniqueness
            import hashlib
            seed_input = f"{worker_id}_{time.time()}_{os.getpid()}"
            seed_hash = int(hashlib.md5(seed_input.encode()).hexdigest()[:8], 16)
            try:
                stata.run(f"set seed {seed_hash}", quietly=True)
            except Exception:
                pass  # Non-critical if seed setting fails

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

        # === ENSURE UNIQUE RANDOM STATE FOR THIS SESSION ===
        # Set seed only on FIRST successful execution to ensure session isolation
        # Track whether seed has been successfully set (not just attempted)
        if not hasattr(execute_stata_code, '_seed_confirmed'):
            execute_stata_code._seed_confirmed = {}

        # Generate seed prefix if not yet confirmed for this session
        seed_prefix = ""
        if worker_id not in execute_stata_code._seed_confirmed:
            import hashlib
            seed_input = f"{worker_id}_{os.getpid()}"
            # Stata requires seed < 2^31 (2147483648), so mask to 31 bits
            seed_hash = int(hashlib.md5(seed_input.encode()).hexdigest()[:8], 16) % 2147483647
            seed_prefix = f"quietly set seed {seed_hash}\n"

        # Create temp log file for output capture (Windows PyStata doesn't write to stdout)
        temp_log_file = os.path.join(tempfile.gettempdir(), f'stata_run_{worker_id}_{int(time.time()*1000)}.log')
        temp_log_stata = temp_log_file.replace('\\', '/')

        try:
            # Wrap code with log commands for reliable output capture
            wrapped_code = f"""capture log close _all
log using "{temp_log_stata}", replace text
{seed_prefix}{code}
capture log close _all
"""
            logging.debug(f"execute_stata_code: Running wrapped code with log file: {temp_log_file}")

            # Run the wrapped code
            # CRITICAL: Use inline=False because inline=True calls _gr_list off at the end,
            # which clears the graph list before we can detect graphs!
            with OutputCapture() as capture:
                stata.run(wrapped_code, echo=True, inline=False)

            # Try to read output from log file first (more reliable on Windows)
            output = ""
            if os.path.exists(temp_log_file):
                try:
                    with open(temp_log_file, 'r', encoding='utf-8', errors='replace') as f:
                        output = f.read()
                    logging.debug(f"execute_stata_code: Read {len(output)} chars from log file")
                except Exception as e:
                    logging.warning(f"execute_stata_code: Could not read log file: {e}")

            # Fall back to captured stdout if log file is empty
            if not output.strip():
                output = capture.get_output()
                logging.debug(f"execute_stata_code: Using stdout capture ({len(output)} chars)")

            # Clean up temp log file
            try:
                if os.path.exists(temp_log_file):
                    os.unlink(temp_log_file)
            except Exception:
                pass

            execution_time = time.time() - start_time
            worker_state = WorkerState.READY

            # Deduplicate break messages
            output = deduplicate_break_messages(output)

            # Check if execution was cancelled
            if cancelled or "--Break--" in output:
                return False, output, "Execution cancelled", execution_time

            # Mark seed as confirmed after successful execution
            if worker_id not in execute_stata_code._seed_confirmed:
                execute_stata_code._seed_confirmed[worker_id] = True

            return True, output, "", execution_time

        except Exception as e:
            # Clean up temp log file on error
            try:
                if os.path.exists(temp_log_file):
                    os.unlink(temp_log_file)
            except Exception:
                pass

            execution_time = time.time() - start_time
            worker_state = WorkerState.READY
            error_str = str(e)

            # Check if this was a user-initiated break
            if "--Break--" in error_str or cancelled:
                return False, "", "Execution cancelled", execution_time

            return False, "", error_str, execution_time

    def execute_stata_file(file_path: str, timeout: float = 600.0, log_file: str = None, working_dir: str = None) -> tuple:
        """
        Execute a .do file with log file support for streaming.

        When log_file is provided, wraps the execution with log commands so the
        output can be monitored in real-time for streaming.

        Args:
            file_path: Path to .do file to execute
            timeout: Execution timeout in seconds
            log_file: Optional path to log file for streaming support
            working_dir: Working directory to cd to before running (affects where outputs are saved).
                         If None, defaults to the .do file's directory.

        Returns:
            tuple: (success: bool, output: str, error: str, execution_time: float, log_file: str)
        """
        nonlocal worker_state, cancelled, stop_already_sent

        if not os.path.exists(file_path):
            return False, "", f"File not found: {file_path}", 0.0, ""

        if stata is None:
            return False, "", "Stata not initialized", 0.0, ""

        # Determine log file path - INCLUDE SESSION ID to prevent locking conflicts
        if log_file is None:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            log_dir = os.path.dirname(os.path.abspath(file_path))
            # Include worker_id in log filename to prevent conflicts between parallel sessions
            log_file = os.path.join(log_dir, f"{base_name}_{worker_id}_mcp.log")

        worker_state = WorkerState.BUSY
        # IMPORTANT: Clear stop_event FIRST to prevent race condition with monitor thread
        # If we reset cancelled/stop_already_sent first, monitor could catch stale signal
        # and set cancelled=True between our reset and clear
        if stop_event is not None:
            stop_event.clear()
        cancelled = False
        stop_already_sent = False  # Reset for new execution
        start_time = time.time()

        # === GENERATE UNIQUE SEED FOR THIS EXECUTION ===
        # Generate seed hash to embed in wrapped code for reliable session isolation
        # Stata requires seed < 2^31 (2147483648), so mask to 31 bits
        import hashlib
        seed_input = f"{worker_id}_{time.time()}_{os.getpid()}"
        seed_hash = int(hashlib.md5(seed_input.encode()).hexdigest()[:8], 16) % 2147483647

        try:
            # Read the original do file
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                original_code = f.read()

            # Convert log file path to use forward slashes (works on all platforms in Stata)
            # This prevents Windows backslash escape issues in Stata commands
            log_file_stata = log_file.replace('\\', '/')

            # Get the working directory for cd command (like native Stata behavior)
            # This ensures outputs (graph export, save, etc.) go to the expected location
            # Use provided working_dir, or default to the .do file's directory
            if working_dir:
                do_file_dir = os.path.abspath(working_dir).replace('\\', '/')
            else:
                do_file_dir = os.path.dirname(os.path.abspath(file_path)).replace('\\', '/')

            # Wrap with log commands for streaming support
            # CRITICAL: Embed seed directly in wrapped code to ensure it's set reliably
            # This avoids race conditions from separate stata.run() calls that might fail silently
            # NOTE: cd to .do file's directory so outputs go there (log file location is separate)
            wrapped_code = f"""capture log close _all
set seed {seed_hash}
cd "{do_file_dir}"
log using "{log_file_stata}", replace text
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

                    # Reset graph tracking BEFORE execution to only detect NEW graphs
                    if stlib is not None:
                        reset_graph_tracking(stlib)

                    success, output, error, exec_time = execute_stata_code(code, timeout)

                    # Detect and export graphs after execution
                    graphs = []
                    if success and stlib is not None and graphs_dir:
                        try:
                            graphs = detect_and_export_graphs_worker(stata, stlib, graphs_dir)
                        except Exception:
                            pass  # Non-critical - don't fail command if graph export fails

                    send_result(
                        command_id=cmd_id,
                        status="success" if success else "error",
                        output=output,
                        error=error,
                        execution_time=exec_time,
                        extra={"graphs": graphs} if graphs else None
                    )

                elif cmd_type == CommandType.EXECUTE_FILE:
                    file_path = payload.get('file_path', '')
                    timeout = payload.get('timeout', 600.0)
                    log_file = payload.get('log_file', None)
                    working_dir = payload.get('working_dir', None)

                    # Reset graph tracking BEFORE execution to only detect NEW graphs
                    if stlib is not None:
                        reset_graph_tracking(stlib)

                    success, output, error, exec_time, actual_log_file = execute_stata_file(
                        file_path, timeout, log_file, working_dir
                    )

                    # Detect and export graphs after execution
                    graphs = []
                    if success and stlib is not None and graphs_dir:
                        try:
                            graphs = detect_and_export_graphs_worker(stata, stlib, graphs_dir)
                        except Exception:
                            pass  # Non-critical - don't fail if graph export fails

                    send_result(
                        command_id=cmd_id,
                        status="success" if success else "error",
                        output=output,
                        error=error,
                        execution_time=exec_time,
                        extra={"file_path": file_path, "log_file": actual_log_file, "graphs": graphs}
                    )

                elif cmd_type == CommandType.GET_DATA:
                    # Get current dataset as DataFrame with efficient filtering and row limits
                    if_condition = payload.get('if_condition', None)
                    max_rows = payload.get('max_rows', 10000)
                    # Ensure minimum value (no hard upper limit - controlled by extension settings)
                    max_rows = max(100, max_rows)

                    try:
                        if stata is None:
                            send_result(
                                command_id=cmd_id,
                                status="error",
                                error="Stata is not initialized"
                            )
                        else:
                            import sfi
                            import numpy as np

                            total_obs = sfi.Data.getObsTotal()

                            if total_obs == 0:
                                send_result(
                                    command_id=cmd_id,
                                    status="success",
                                    output="",
                                    extra={
                                        "data": [],
                                        "columns": [],
                                        "dtypes": {},
                                        "rows": 0,
                                        "index": [],
                                        "total_rows": 0,
                                        "displayed_rows": 0,
                                        "max_rows": max_rows
                                    }
                                )
                            elif if_condition:
                                # Use efficient Stata-native filtering with preserve/restore
                                try:
                                    stata.run("preserve", inline=False, echo=False)

                                    try:
                                        # Create temp variable to track original observation numbers (0-based for JS)
                                        stata.run("quietly gen long _stata_mcp_orig_obs = _n - 1", inline=False, echo=False)

                                        # Use Stata's native keep if - very fast even for millions of rows
                                        stata.run(f"quietly keep if {if_condition}", inline=False, echo=False)

                                        filtered_obs = sfi.Data.getObsTotal()

                                        # Apply row limit if needed
                                        if filtered_obs > max_rows:
                                            stata.run(f"quietly keep in 1/{max_rows}", inline=False, echo=False)

                                        df = stata.pdataframe_from_data()

                                        # Extract original obs numbers as index, then drop the temp column
                                        orig_obs_index = df['_stata_mcp_orig_obs'].tolist()
                                        df = df.drop(columns=['_stata_mcp_orig_obs'])

                                        stata.run("restore", inline=False, echo=False)

                                        total_matching = filtered_obs
                                        displayed_rows = min(filtered_obs, max_rows)

                                    except Exception as filter_err:
                                        try:
                                            stata.run("restore", inline=False, echo=False)
                                        except:
                                            pass
                                        send_result(
                                            command_id=cmd_id,
                                            status="error",
                                            error=f"Filter error: {str(filter_err)}"
                                        )
                                        continue

                                except Exception as preserve_err:
                                    send_result(
                                        command_id=cmd_id,
                                        status="error",
                                        error=f"Filter error: {str(preserve_err)}"
                                    )
                                    continue
                                # For filtered case, orig_obs_index is already set above
                            else:
                                # No filter - just apply row limit
                                total_matching = total_obs
                                displayed_rows = min(total_obs, max_rows)

                                if total_obs > max_rows:
                                    # Use range() for obs parameter (0-based Python indexing)
                                    df = stata.pdataframe_from_data(obs=range(max_rows))
                                else:
                                    df = stata.pdataframe_from_data()

                                # Sequential index for non-filtered case (0-based, JS adds 1)
                                orig_obs_index = list(range(len(df))) if df is not None else []

                            if df is None or df.empty:
                                send_result(
                                    command_id=cmd_id,
                                    status="success",
                                    output="",
                                    extra={
                                        "data": [],
                                        "columns": [],
                                        "dtypes": {},
                                        "rows": 0,
                                        "index": [],
                                        "total_rows": total_matching if 'total_matching' in dir() else 0,
                                        "displayed_rows": 0,
                                        "max_rows": max_rows
                                    }
                                )
                            else:
                                # Clean data for JSON serialization
                                df_clean = df.replace({np.nan: None})

                                send_result(
                                    command_id=cmd_id,
                                    status="success",
                                    output="",
                                    extra={
                                        "data": df_clean.values.tolist(),
                                        "columns": df_clean.columns.tolist(),
                                        "dtypes": {col: str(df[col].dtype) for col in df.columns},
                                        "rows": len(df),
                                        "index": orig_obs_index,
                                        "total_rows": total_matching,
                                        "displayed_rows": displayed_rows,
                                        "max_rows": max_rows
                                    }
                                )
                    except Exception as data_err:
                        send_result(
                            command_id=cmd_id,
                            status="error",
                            error=f"Error getting data: {str(data_err)}"
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

        # Clean up temporary directory to prevent disk space leakage
        if worker_temp_dir and os.path.exists(worker_temp_dir):
            try:
                shutil.rmtree(worker_temp_dir, ignore_errors=True)
            except Exception:
                pass  # Best effort cleanup


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def find_stata_executable(stata_path: str, stata_edition: str = "mp") -> Optional[str]:
    """
    Find the Stata executable path based on OS and edition.

    Args:
        stata_path: Base Stata installation path
        stata_edition: Edition (mp, se, be)

    Returns:
        Full path to Stata executable, or None if not found
    """
    system = platform.system()
    edition_lower = stata_edition.lower()

    if system == 'Darwin':  # macOS
        # Try different app bundle names
        app_names = [
            f"Stata{edition_lower.upper()}.app",  # StataMP.app
            f"stata-{edition_lower}",              # stata-mp (command line)
            "Stata.app",
        ]

        for app_name in app_names:
            if app_name.endswith('.app'):
                # macOS app bundle
                exe_path = os.path.join(stata_path, app_name, "Contents", "MacOS", f"stata-{edition_lower}")
                if os.path.exists(exe_path):
                    return exe_path
                # Try without edition suffix
                exe_path = os.path.join(stata_path, app_name, "Contents", "MacOS", "stata")
                if os.path.exists(exe_path):
                    return exe_path
            else:
                # Direct executable
                exe_path = os.path.join(stata_path, app_name)
                if os.path.exists(exe_path):
                    return exe_path

        # Fallback: look for any stata executable in the path
        for edition in ['mp', 'se', 'be', '']:
            suffix = f"-{edition}" if edition else ""
            exe_path = os.path.join(stata_path, f"stata{suffix}")
            if os.path.exists(exe_path):
                return exe_path

    elif system == 'Windows':
        # Windows executables
        exe_names = [
            f"Stata{edition_lower.upper()}-64.exe",  # StataMP-64.exe
            f"Stata{edition_lower.upper()}.exe",      # StataMP.exe
            "Stata-64.exe",
            "Stata.exe",
        ]

        for exe_name in exe_names:
            exe_path = os.path.join(stata_path, exe_name)
            if os.path.exists(exe_path):
                return exe_path

    else:  # Linux
        exe_names = [
            f"stata-{edition_lower}",
            "stata",
        ]

        for exe_name in exe_names:
            exe_path = os.path.join(stata_path, exe_name)
            if os.path.exists(exe_path):
                return exe_path

    return None


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
