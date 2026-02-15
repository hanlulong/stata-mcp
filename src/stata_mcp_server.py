#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stata MCP Server - Exposes Stata functionality to AI models via MCP protocol
Using fastapi-mcp for clean implementation
"""

import os
import tempfile
import json
import sys
import time
import argparse
import logging
import platform
import signal
import subprocess
import traceback
import socket
import asyncio
from typing import Dict, Any, Optional
from urllib.parse import unquote
import warnings
import re

# Import utility functions
from utils import get_windows_path_help_message, normalize_path_for_platform

# Import API models
from api_models import (
    RunSelectionParams,
    RunFileParams,
    ToolRequest,
    ToolResponse,
)

# Fix encoding issues on Windows for Unicode characters
if platform.system() == 'Windows':
    # Force UTF-8 encoding for stdout and stderr on Windows
    import io
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    # Set environment variable for Python to use UTF-8
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Hide Python process from Mac Dock (server should be background process)
if platform.system() == 'Darwin':
    try:
        from AppKit import NSApplication
        # Set activation policy to accessory - hides dock icon but allows functionality
        # This must be called early, before any GUI operations (like Stata's JVM graphics)
        app = NSApplication.sharedApplication()
        # NSApplicationActivationPolicyAccessory = 1 (hidden from dock, can show windows)
        # NSApplicationActivationPolicyProhibited = 2 (completely hidden)
        app.setActivationPolicy_(1)  # Use Accessory to allow Stata's GUI operations
    except Exception:
        # Silently ignore if AppKit not available or fails
        # This is just a UI improvement, not critical for functionality
        pass

# Check if running as a module (using -m flag)
is_running_as_module = __name__ == "__main__" and not sys.argv[0].endswith('stata_mcp_server.py')
if is_running_as_module:
    print(f"Running as a module, using modified command-line handling")

# Check Python version on Windows but don't exit immediately to allow logging
if platform.system() == 'Windows':
    required_version = (3, 11)
    current_version = (sys.version_info.major, sys.version_info.minor)
    if current_version < required_version:
        print(f"WARNING: Python 3.11 or higher is recommended on Windows. Current version: {sys.version}")
        print("Please install Python 3.11 from python.org for best compatibility.")
        # Log this but don't exit immediately so logs can be written

try:
    from fastapi import FastAPI, Request, Response, Query
    from fastapi.responses import StreamingResponse
    from fastapi_mcp import FastApiMCP
    from pydantic import BaseModel, Field
    from contextlib import asynccontextmanager
    import httpx
except ImportError as e:
    print(f"ERROR: Required Python packages not found: {str(e)}")
    print("Please install the required packages:")
    print("pip install fastapi uvicorn fastapi-mcp pydantic")
    
    # On Windows, provide more guidance
    if platform.system() == 'Windows':
        print("\nOn Windows, you can install required packages by running:")
        print("py -3.11 -m pip install fastapi uvicorn fastapi-mcp pydantic")
        print("\nIf you need to install Python 3.11, download it from: https://www.python.org/downloads/")
    
    # Exit with error
    sys.exit(1)

# Configure logging - will be updated in main() with proper log file
# Start with basic console logging
logging.basicConfig(
    level=logging.INFO,  # Changed from DEBUG to INFO to reduce verbosity
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout  # Default to stdout until log file is configured
)

# Create console handler for debugging
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.WARNING)  # Only show WARNING level and above to keep console output clean
formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)

# Silence uvicorn access logs but allow warnings
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

# Server info
SERVER_NAME = "Stata MCP Server"
SERVER_VERSION = "0.4.1"

# Flag for Stata availability
stata_available = False
has_stata = False
stata = None  # Module-level reference to stata module
STATA_PATH = None
# Add a flag to track if we've already displayed the Stata banner
stata_banner_displayed = False
# Add a flag to track if MCP server is fully initialized
mcp_initialized = False
# Add a storage for continuous command history
command_history = []
# Store the current Stata edition
stata_edition = 'mp'  # Default to MP edition
# Store log file settings
log_file_location = 'extension'  # Default to extension directory
custom_log_directory = ''  # Custom log directory
workspace_root = ''  # VS Code workspace root directory
extension_path = None  # Path to the extension directory

# Result display settings for MCP returns (token-saving mode)
result_display_mode = 'compact'  # 'compact' or 'full'
max_output_tokens = 10000  # Maximum tokens (approx 4 chars each), 0 for unlimited

# Multi-session settings
multi_session_enabled = True  # Whether multi-session mode is enabled (default: True)
multi_session_max_sessions = 100  # Maximum concurrent sessions
multi_session_timeout = 3600  # Session idle timeout in seconds
session_manager = None  # Will be initialized if multi-session is enabled

# Execution tracking for stop/cancel functionality
import threading
execution_registry = {}  # Map: execution_id -> {'thread': thread, 'start_time': time, 'cancelled': bool, 'file': file}
execution_lock = threading.Lock()  # Protect concurrent access to execution_registry
current_execution_id = None  # Track the current execution ID

# Try to import pandas
try:
    import pandas as pd
    has_pandas = True
    logging.info("pandas module loaded successfully")
except ImportError:
    has_pandas = False
    logging.warning("pandas not available, data transfer functionality will be limited")
    warnings.warn("pandas not available, data transfer functionality will be limited")

# Try to initialize Stata with the given path
def try_init_stata(stata_path):
    """Try to initialize Stata with the given path"""
    global stata_available, has_stata, stata, STATA_PATH, stata_banner_displayed, stata_edition
    
    # If Stata is already available, don't re-initialize
    if stata_available and has_stata and stata is not None:
        logging.debug("Stata already initialized, skipping re-initialization")
        return True
    
    # Clean the path (remove quotes if present)
    if stata_path:
        # Remove any quotes that might have been added
        stata_path = stata_path.strip('"\'')
        STATA_PATH = stata_path
        logging.info(f"Using Stata path: {stata_path}")
    
    logging.info(f"Initializing Stata from path: {stata_path}")
    
    try:
        # Add environment variables to help with library loading
        if stata_path:
            if not os.path.exists(stata_path):
                error_msg = f"Stata path does not exist: {stata_path}"
                logging.error(error_msg)
                print(f"ERROR: {error_msg}")
                return False
                
            os.environ['SYSDIR_STATA'] = stata_path
        
        stata_utilities_path = os.path.join(os.environ.get('SYSDIR_STATA', ''), 'utilities')
        if os.path.exists(stata_utilities_path):
            sys.path.insert(0, stata_utilities_path)
            logging.debug(f"Added Stata utilities path to sys.path: {stata_utilities_path}")
        else:
            warning_msg = f"Stata utilities path not found: {stata_utilities_path}"
            logging.warning(warning_msg)
            
        # Try to import pystata or stata-sfi
        try:
            # First try pystata
            from pystata import config
            logging.debug("Successfully imported pystata")
            
            # Try to initialize Stata 
            try:
                # Only show banner once (suppress if we've shown it before)
                if not stata_banner_displayed and platform.system() == 'Windows':
                    # On Windows, the banner appears even if we try to suppress it
                    # At least mark that we've displayed it
                    stata_banner_displayed = True
                    logging.debug("Stata banner will be displayed (first time)")
                else:
                    # On subsequent initializations, try to suppress the banner
                    # This doesn't always work on Windows, but at least we're trying
                    logging.debug("Attempting to suppress Stata banner on re-initialization")
                    os.environ['STATA_QUIETLY'] = '1'  # Add this environment variable

                # Set Java headless mode to prevent Dock icon on Mac (must be before config.init)
                # When Stata's embedded JVM initializes for graphics, it normally creates a Dock icon
                # Setting headless=true prevents this GUI behavior
                if platform.system() == 'Darwin':
                    # Use _JAVA_OPTIONS instead of JAVA_TOOL_OPTIONS to suppress the informational message
                    # _JAVA_OPTIONS is picked up by the JVM but doesn't print "Picked up..." to stderr
                    os.environ['_JAVA_OPTIONS'] = '-Djava.awt.headless=true'
                    logging.debug("Set Java headless mode to prevent Dock icon")

                # Initialize with the specified Stata edition
                config.init(stata_edition)
                logging.info(f"Stata initialized successfully with {stata_edition.upper()} edition")

                # On Windows, redirect PyStata's output to devnull
                # to prevent duplicate output (we capture output via log files, not stdout)
                if platform.system() == 'Windows':
                    import io
                    devnull_file = open(os.devnull, 'w', encoding='utf-8')
                    config.stoutputf = devnull_file
                    logging.debug("Redirected PyStata output to devnull on Windows")

                # Now import stata after initialization
                from pystata import stata as stata_module
                # Set module-level stata reference
                globals()['stata'] = stata_module
                
                # Successfully initialized Stata
                has_stata = True
                stata_available = True

                # Initialize PNG export capability to prevent JVM crash in daemon threads (Mac-specific)
                #
                # Root cause: On Mac, Stata's graphics use embedded JVM. When PNG export is first
                # called from a daemon thread, the JVM initialization fails with SIGBUS error in
                # CodeHeap::allocate(). This is Mac-specific due to different JVM/threading model
                # in libstata-mp.dylib compared to Windows stata-mp-64.dll.
                #
                # Solution: Initialize JVM in main thread by doing one PNG export at startup.
                # All subsequent daemon thread PNG exports will reuse the initialized JVM.
                #
                # See: tests/MAC_SPECIFIC_ANALYSIS.md for detailed technical analysis
                try:
                    from pystata.config import stlib, get_encode_str
                    import tempfile

                    # Create minimal dataset and graph (2 obs, 1 var)
                    stlib.StataSO_Execute(get_encode_str("qui clear"), False)
                    stlib.StataSO_Execute(get_encode_str("qui set obs 2"), False)
                    stlib.StataSO_Execute(get_encode_str("qui gen x=1"), False)
                    stlib.StataSO_Execute(get_encode_str("qui twoway scatter x x, name(_init, replace)"), False)

                    # Export tiny PNG (10x10px) to initialize JVM in main thread
                    # This prevents SIGBUS crash when daemon threads later export PNG
                    png_init = os.path.join(tempfile.gettempdir(), "_stata_png_init.png")
                    stlib.StataSO_Execute(get_encode_str(f'qui graph export "{png_init}", name(_init) replace width(10) height(10)'), False)
                    stlib.StataSO_Execute(get_encode_str("qui graph drop _init"), False)

                    # Cleanup temporary files
                    if os.path.exists(png_init):
                        os.unlink(png_init)

                    logging.debug("PNG export initialized successfully (Mac JVM fix)")
                except Exception as png_init_error:
                    # Non-fatal: log but continue - PNG may still work on some platforms
                    logging.warning(f"PNG initialization failed (non-fatal): {str(png_init_error)}")

                return True
            except Exception as init_error:
                error_msg = f"Failed to initialize Stata: {str(init_error)}"
                logging.error(error_msg)
                print(f"ERROR: {error_msg}")
                print("Will attempt to continue without full Stata integration")
                print("Check if Stata is already running in another instance, or if your Stata license is valid")
                
                # Some features will still work without full initialization
                has_stata = False
                stata_available = False
                
                return False
        except ImportError as config_error:
            # Try stata-sfi as fallback
            try:
                import stata_setup
                
                # Only show banner once
                if not stata_banner_displayed and platform.system() == 'Windows':
                    stata_banner_displayed = True
                    logging.debug("Stata banner will be displayed (first time)")
                else:
                    # On subsequent initializations, try to suppress the banner
                    logging.debug("Attempting to suppress Stata banner on re-initialization")
                    os.environ['STATA_QUIETLY'] = '1'
                
                stata_setup.config(stata_path, stata_edition)
                logging.debug("Successfully configured stata_setup")
                
                try:
                    import sfi
                    # Set module-level stata reference for compatibility
                    globals()['stata'] = sfi
                    
                    has_stata = True
                    stata_available = True
                    logging.info("Stata initialized successfully using sfi")
                    
                    return True
                except ImportError as sfi_error:
                    error_msg = f"Could not import sfi: {str(sfi_error)}"
                    logging.error(error_msg)
                    print(f"ERROR: {error_msg}")
                    has_stata = False
                    stata_available = False
                    return False
            except Exception as setup_error:
                error_msg = f"Could not import pystata or sfi: {str(setup_error)}"
                logging.error(error_msg)
                print(f"ERROR: {error_msg}")
                print("Stata commands will not be available")
            has_stata = False
            stata_available = False
            
            return False
    except Exception as e:
        error_msg = f"General error setting up Stata environment: {str(e)}"
        logging.error(error_msg)
        print(f"ERROR: {error_msg}")
        print("Stata commands will not be available")
        print(f"Check if the Stata path is correct: {stata_path}")
        print("And ensure Stata is properly licensed and not running in another process")
        has_stata = False
        stata_available = False
        
        return False

# Lock file mechanism removed - VS Code/Cursor handles extension instances properly
# If there are port conflicts, the server will fail to start cleanly

def get_log_file_path(do_file_path, do_file_base, session_id=None):
    """Get the appropriate log file path based on user settings

    Returns an absolute path to ensure log files are saved to the correct location
    regardless of Stata's working directory.

    Args:
        do_file_path: Path to the .do file
        do_file_base: Base name of the .do file (without extension)
        session_id: Optional session ID to include in filename for parallel execution
    """
    global log_file_location, custom_log_directory, extension_path

    do_file_dir = os.path.dirname(do_file_path)

    # Include session_id in filename to prevent file locking conflicts in parallel execution
    session_suffix = f"_{session_id}" if session_id else ""

    if log_file_location == 'extension':
        # Use logs folder in extension directory
        if extension_path:
            logs_dir = os.path.join(extension_path, 'logs')
            # Create logs directory if it doesn't exist
            os.makedirs(logs_dir, exist_ok=True)
            log_path = os.path.join(logs_dir, f"{do_file_base}{session_suffix}_mcp.log")
            return os.path.abspath(log_path)
        else:
            # Fallback to dofile if extension path is not available
            log_path = os.path.join(do_file_dir, f"{do_file_base}{session_suffix}_mcp.log")
            return os.path.abspath(log_path)
    elif log_file_location == 'dofile':
        # Use same directory as .do file
        log_path = os.path.join(do_file_dir, f"{do_file_base}{session_suffix}_mcp.log")
        return os.path.abspath(log_path)
    elif log_file_location == 'parent':
        # Use parent directory of .do file
        parent_dir = os.path.dirname(do_file_dir)
        if parent_dir and os.path.exists(parent_dir):
            log_path = os.path.join(parent_dir, f"{do_file_base}{session_suffix}_mcp.log")
            return os.path.abspath(log_path)
        else:
            # Fallback to dofile directory if parent doesn't exist
            log_path = os.path.join(do_file_dir, f"{do_file_base}{session_suffix}_mcp.log")
            return os.path.abspath(log_path)
    elif log_file_location == 'custom':
        # Use custom directory
        if custom_log_directory and os.path.exists(custom_log_directory):
            log_path = os.path.join(custom_log_directory, f"{do_file_base}{session_suffix}_mcp.log")
            return os.path.abspath(log_path)
        else:
            # Fallback to dofile if custom directory is invalid
            logging.warning(f"Custom log directory not valid: {custom_log_directory}, falling back to dofile directory")
            log_path = os.path.join(do_file_dir, f"{do_file_base}{session_suffix}_mcp.log")
            return os.path.abspath(log_path)
    else:  # workspace
        # Use VS Code workspace root if available, otherwise fall back to dofile directory
        if workspace_root and os.path.isdir(workspace_root):
            log_path = os.path.join(workspace_root, f"{do_file_base}{session_suffix}_mcp.log")
            return os.path.abspath(log_path)
        else:
            # Fallback to dofile directory if workspace root not available
            logging.warning(f"Workspace root not available, falling back to dofile directory")
            log_path = os.path.join(do_file_dir, f"{do_file_base}{session_suffix}_mcp.log")
            return os.path.abspath(log_path)

def resolve_do_file_path(file_path: str) -> tuple[Optional[str], list[str]]:
    """Resolve a .do file path to an absolute location, mirroring run_stata_file logic.

    Returns:
        A tuple of (resolved_path, tried_paths). resolved_path is None if the file
        could not be located. tried_paths contains the normalized paths that were examined.
    """
    original_path = file_path
    normalized_path = os.path.normpath(file_path)

    # Normalize Windows paths to use backslashes for consistency
    if platform.system() == "Windows" and '/' in normalized_path:
        normalized_path = normalized_path.replace('/', '\\')
        logging.info(f"Converted path for Windows: {normalized_path}")

    candidates: list[str] = []
    tried_paths: list[str] = []

    if not os.path.isabs(normalized_path):
        cwd = os.getcwd()
        logging.info(f"File path is not absolute. Current working directory: {cwd}")

        candidates.extend([
            normalized_path,
            os.path.join(cwd, normalized_path),
            os.path.join(cwd, os.path.basename(normalized_path)),
        ])

        if platform.system() == "Windows":
            if '/' in original_path:
                win_path = original_path.replace('/', '\\')
                candidates.append(win_path)
                candidates.append(os.path.join(cwd, win_path))
            elif '\\' in original_path:
                unix_path = original_path.replace('\\', '/')
                candidates.append(unix_path)
                candidates.append(os.path.join(cwd, unix_path))

        # Search subdirectories up to two levels deep for the file
        for root, dirs, files in os.walk(cwd, topdown=True, followlinks=False):
            if os.path.basename(normalized_path) in files and root != cwd:
                subdir_path = os.path.join(root, os.path.basename(normalized_path))
                candidates.append(subdir_path)

            # Limit depth to two levels
            if root.replace(cwd, '').count(os.sep) >= 2:
                dirs[:] = []
    else:
        candidates.append(normalized_path)

    # Deduplicate while preserving order
    seen = set()
    unique_candidates = []
    for candidate in candidates:
        normalized_candidate = os.path.normpath(candidate)
        if normalized_candidate not in seen:
            seen.add(normalized_candidate)
            unique_candidates.append(normalized_candidate)

    for candidate in unique_candidates:
        tried_paths.append(candidate)
        if os.path.isfile(candidate) and candidate.lower().endswith('.do'):
            resolved = os.path.abspath(candidate)
            logging.info(f"Found file at: {resolved}")
            return resolved, tried_paths

    return None, tried_paths

def get_stata_path():
    """Get the Stata executable path based on the platform and configured path"""
    global STATA_PATH
    
    if not STATA_PATH:
        return None
        
    # Build the actual executable path based on the platform
    if platform.system() == "Windows":
        # On Windows, executable is StataMP.exe or similar
        # Try different executable names
        for exe_name in ["StataMP-64.exe", "StataMP.exe", "StataSE-64.exe", "StataSE.exe", "Stata-64.exe", "Stata.exe"]:
            exe_path = os.path.join(STATA_PATH, exe_name)
            if os.path.exists(exe_path):
                return exe_path
                
        # If no specific executable found, use the default path with StataMP.exe
        return os.path.join(STATA_PATH, "StataMP.exe")
    else:
        # On macOS, executable is StataMPC inside the app bundle
        if platform.system() == "Darwin":  # macOS
            # Check if STATA_PATH is the app bundle path
            if STATA_PATH.endswith(".app"):
                # App bundle format like /Applications/Stata/StataMC.app
                exe_path = os.path.join(STATA_PATH, "Contents", "MacOS", "StataMP")
                if os.path.exists(exe_path):
                    return exe_path
                    
                # Try other Stata variants    
                for variant in ["StataSE", "Stata"]:
                    exe_path = os.path.join(STATA_PATH, "Contents", "MacOS", variant)
                    if os.path.exists(exe_path):
                        return exe_path
            else:
                # Direct path like /Applications/Stata
                for variant in ["StataMP", "StataSE", "Stata"]:
                    # Check if there's an app bundle inside the directory
                    app_path = os.path.join(STATA_PATH, f"{variant}.app")
                    if os.path.exists(app_path):
                        exe_path = os.path.join(app_path, "Contents", "MacOS", variant)
                        if os.path.exists(exe_path):
                            return exe_path
                            
                    # Also check for direct executable
                    exe_path = os.path.join(STATA_PATH, variant)
                    if os.path.exists(exe_path):
                        return exe_path
        else:
            # Linux - executable should be inside the path directly
            for variant in ["stata-mp", "stata-se", "stata"]:
                exe_path = os.path.join(STATA_PATH, variant)
                if os.path.exists(exe_path):
                    return exe_path
    
    # If we get here, we couldn't find the executable
    logging.error(f"Could not find Stata executable in {STATA_PATH}")
    return STATA_PATH  # Return the base path as fallback

def check_stata_installed():
    """Check if Stata is installed and available"""
    global stata_available
    
    # First check if we have working Python integration
    if stata_available and 'stata' in globals():
        return True
        
    # Otherwise check for executable
    stata_path = get_stata_path()
    if not stata_path:
        return False
        
    # Check if the file exists and is executable
    if not os.path.exists(stata_path):
        return False
        
    # On non-Windows, check if it's executable
    if platform.system() != "Windows" and not os.access(stata_path, os.X_OK):
        return False
        
    return True

# ============================================================================
# Output Filtering Functions - Imported from output_filter.py
# ============================================================================
# Note: The core filtering functions (apply_compact_mode_filter, check_token_limit_and_save,
# process_mcp_output) are now in output_filter.py. The imports are done at the top of this file.
# The functions are re-exported here with wrappers that use global configuration.

# Import the base functions with different names to avoid shadowing
from output_filter import (
    apply_compact_mode_filter as _apply_compact_mode_filter,
    check_token_limit_and_save as _check_token_limit_and_save,
    process_mcp_output as _process_mcp_output,
)

# Wrapper that uses global config
def _local_check_token_limit_and_save(output: str, original_log_path: str = None) -> tuple:
    """Wrapper for check_token_limit_and_save that uses global config."""
    global max_output_tokens, extension_path
    return _check_token_limit_and_save(
        output,
        max_output_tokens,
        extension_path,
        original_log_path
    )

# Wrapper that uses global config
def _local_process_mcp_output(output: str, log_path: str = None, for_mcp: bool = True, filter_command_echo: bool = False) -> str:
    """Wrapper for process_mcp_output that uses global config."""
    global result_display_mode, max_output_tokens, extension_path
    return _process_mcp_output(
        output,
        result_display_mode,
        max_output_tokens,
        extension_path,
        log_path,
        for_mcp,
        filter_command_echo
    )

# Re-assign for backward compatibility (existing code uses these names)
apply_compact_mode_filter = _apply_compact_mode_filter  # No globals needed
check_token_limit_and_save = _local_check_token_limit_and_save
process_mcp_output = _local_process_mcp_output


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


def preprocess_do_file_for_graphs(file_path: str) -> str:
    """Pre-process a .do file to auto-name graphs and handle line continuations.

    This function reads a .do file and:
    1. Joins lines with /// continuation
    2. Auto-names graph commands that don't have names (avoiding conflicts with existing names)

    Args:
        file_path: Path to the .do file

    Returns:
        Path to the pre-processed temporary file
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            do_file_content = f.read()

        # First, join lines with Stata line continuation (///) into single logical lines
        raw_lines = do_file_content.splitlines()
        joined_lines = []
        current_line = ""
        for raw_line in raw_lines:
            stripped = raw_line.rstrip()
            if stripped.endswith('///'):
                current_line += stripped[:-3].rstrip() + " "
            else:
                current_line += raw_line
                joined_lines.append(current_line)
                current_line = ""
        if current_line:
            joined_lines.append(current_line)

        # Find all existing graph names like "graph1", "graph2", etc. to avoid conflicts
        existing_graph_nums = set()
        for line in joined_lines:
            # Look for name(graphN, ...) or name(graphN)
            name_matches = re.findall(r'\bname\s*\(\s*graph(\d+)', str(line), re.IGNORECASE)
            for num_str in name_matches:
                try:
                    existing_graph_nums.add(int(num_str))
                except ValueError:
                    pass

        # Start counter from the next available number after existing ones
        graph_counter = max(existing_graph_nums) if existing_graph_nums else 0

        # Process each line to auto-name graphs
        modified_content = ""

        for line in joined_lines:
            line = str(line) if line is not None else ""

            # Check if this is a graph creation command that might need a name
            graph_match = re.match(r'^(\s*)(scatter|histogram|twoway|kdensity|graph\s+(bar|box|dot|pie|matrix|hbar|hbox|combine))\s+(.*)$', line, re.IGNORECASE)

            if graph_match:
                indent = str(graph_match.group(1) or "")
                graph_cmd = str(graph_match.group(2) or "")
                rest_raw = graph_match.group(4) if graph_match.lastindex >= 4 else ""
                rest = str(rest_raw) if rest_raw else ""

                # Check if it already has name() option
                if not re.search(r'\bname\s*\(', rest, re.IGNORECASE):
                    graph_counter += 1
                    graph_name = f"graph{graph_counter}"

                    if ',' in rest:
                        rest = re.sub(r',', f', name({graph_name}, replace)', rest, 1)
                    else:
                        rest = rest.rstrip() + f', name({graph_name}, replace)'

                    modified_content += f"{indent}{graph_cmd} {rest}\n"
                    continue

            modified_content += f"{line}\n"

        auto_named_count = graph_counter - (max(existing_graph_nums) if existing_graph_nums else 0)
        if auto_named_count > 0:
            logging.info(f"Pre-processed {auto_named_count} graph commands for auto-naming (starting from graph{(max(existing_graph_nums) if existing_graph_nums else 0) + 1})")

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.do', delete=False, mode='w', encoding='utf-8') as temp_do:
            temp_do.write(modified_content)
            return temp_do.name

    except Exception as e:
        logging.error(f"Error pre-processing do file: {e}")
        return file_path  # Return original file on error


# Function to run a Stata command
def run_stata_command(
    command: str,
    clear_history: bool = False,
    auto_detect_graphs: bool = False
) -> str:
    """Run a Stata command.

    Args:
        command: The Stata command to run
        clear_history: Whether to clear command history
        auto_detect_graphs: Whether to detect and export graphs after execution

    Returns:
        Stata output as a string

    Note: This function manually enables _gr_list on before execution and detects graphs after.
    We do NOT use inline=True because it calls _gr_list off at the end, clearing our graph list!
    This function is only called from /v1/tools endpoint which is excluded from MCP.
    """
    global stata_available, has_stata, command_history
    
    # Only log at debug level instead of info to reduce verbosity
    logging.debug(f"Running Stata command: {command}")
    
    # Clear history if requested
    if clear_history:
        logging.info(f"Clearing command history (had {len(command_history)} items)")
        command_history = []
        # If it's just a clear request with no command, return empty
        if not command or command.strip() == '':
            logging.info("Clear history request completed")
            return ''

    # For multi-line commands, don't add semicolons - just clean up whitespace
    if "\n" in command:
        # Clean up the commands to ensure proper formatting without adding semicolons
        command = "\n".join(line.strip() for line in command.splitlines() if line.strip())
        logging.debug(f"Processed multiline command: {command}")
    
    # Special handling for 'do' commands with file paths
    if command.lower().startswith('do '):
        # Extract the file path part
        parts = command.split(' ', 1)
        if len(parts) > 1:
            file_path = parts[1].strip()
            
            # Remove any existing quotes
            if (file_path.startswith('"') and file_path.endswith('"')) or \
               (file_path.startswith("'") and file_path.endswith("'")):
                file_path = file_path[1:-1]
            
            # Normalize path for OS
            file_path = os.path.normpath(file_path)
            
            # On Windows, make sure backslashes are used
            if platform.system() == "Windows" and '/' in file_path:
                file_path = file_path.replace('/', '\\')
                logging.debug(f"Converted path for Windows: {file_path}")
            
            # For Stata's do command, ALWAYS use double quotes regardless of platform
            # This is the most reliable approach to handle spaces and special characters
            file_path = f'"{file_path}"'
            
            # Reconstruct the command with the properly formatted path
            command = f"do {file_path}"
            logging.debug(f"Reformatted 'do' command: {command}")
    
    # Check if pystata is available
    if has_stata and stata_available:
        # Run the command via pystata
        try:
            # Reset graph tracking BEFORE execution to only detect NEW graphs
            try:
                from pystata.config import stlib, get_encode_str
                logging.debug("Resetting graph list for new command...")
                stlib.StataSO_Execute(get_encode_str("qui _gr_list off"), False)
                stlib.StataSO_Execute(get_encode_str("qui _gr_list on"), False)
                logging.debug("Graph list reset successfully")
            except Exception as e:
                logging.warning(f"Could not reset graph listing: {str(e)}")
                logging.debug(f"Graph listing reset error: {traceback.format_exc()}")

            # Initialize graphs list (will be populated if graphs are found)
            graphs_from_interactive = []

            # Create a temp file to capture output
            with tempfile.NamedTemporaryFile(

                suffix='.do', delete=False, mode='w', encoding='utf-8'

            ) as f:
                # Write the command to the file
                f.write(f"capture log close _all\n")
                f.write(f"log using \"{f.name}.log\", replace text\n")

                # Process command line by line to comment out cls commands
                cls_commands_found = 0
                processed_command = ""
                for line in command.splitlines():
                    # Ensure line is a string (defensive programming)
                    line = str(line) if line is not None else ""

                    # Check if this is a cls command
                    if re.match(r'^\s*cls\s*$', line, re.IGNORECASE):
                        processed_command += f"* COMMENTED OUT BY MCP: {line}\n"
                        cls_commands_found += 1
                    else:
                        processed_command += f"{line}\n"

                if cls_commands_found > 0:
                    logging.info(f"Found and commented out {cls_commands_found} cls commands in the selection")

                # Special handling for 'do' commands to ensure proper quoting
                if command.lower().startswith('do '):
                    # For do commands, we need to make sure the file path is properly handled
                    # The command already has the file in quotes from the code above
                    f.write(f"{processed_command}")
                else:
                    # Normal commands don't need special treatment
                    f.write(f"{processed_command}")

                f.write(f"capture log close\n")
                do_file = f.name

            # Execute the do file with echo=False to completely silence Stata output to console
            try:
                # Redirect stdout temporarily to silence Stata output
                original_stdout = sys.stdout
                sys.stdout = open(os.devnull, 'w')
                
                try:
                    # Always use double quotes for the do file path for PyStata
                    run_cmd = f"do \"{do_file}\""
                    # Use inline=False because inline=True calls _gr_list off at the end!
                    globals()['stata'].run(run_cmd, echo=False, inline=False)
                    logging.debug(f"Command executed successfully via pystata: {run_cmd}")
                except Exception as e:
                    # If command fails, try to reinitialize Stata once
                    logging.warning(f"Stata command failed, attempting to reinitialize: {str(e)}")
                    
                    # Try to reinitialize Stata with the global path
                    if STATA_PATH:
                        if try_init_stata(STATA_PATH):
                            # Retry the command if reinitialization succeeded
                            try:
                                globals()['stata'].run(f"do \"{do_file}\"", echo=False, inline=False)
                                logging.info(f"Command succeeded after Stata reinitialization")
                            except Exception as retry_error:
                                logging.error(f"Command still failed after reinitializing Stata: {str(retry_error)}")
                                raise retry_error
                        else:
                            logging.error(f"Failed to reinitialize Stata")
                            raise e
                    else:
                        logging.error(f"No Stata path available for reinitialization")
                        raise e
                finally:
                    # Restore stdout
                    sys.stdout.close()
                    sys.stdout = original_stdout

                # Detect and export only NEW graphs if enabled (matching run_stata_file behavior)
                if auto_detect_graphs:
                    # Immediately check for graphs while they're still in memory
                    try:
                        logging.debug("Checking for graphs immediately after execution (interactive mode)...")
                        graphs_from_interactive = display_graphs_interactive(graph_format='png', width=800, height=600)
                        if graphs_from_interactive:
                            logging.info(f"Captured {len(graphs_from_interactive)} NEW graphs in interactive mode")
                    except Exception as graph_err:
                        logging.warning(f"Could not capture graphs in interactive mode: {str(graph_err)}")

            except Exception as exec_error:
                error_msg = f"Error running command: {str(exec_error)}"
                logging.error(error_msg)
                return error_msg

            # Read the log file
            log_file = f"{do_file}.log"
            logging.debug(f"Reading log file: {log_file}")
            
            # Wait for the log file to be written
            max_attempts = 10
            attempts = 0
            while not os.path.exists(log_file) and attempts < max_attempts:
                time.sleep(0.3)
                attempts += 1
            
            if not os.path.exists(log_file):
                logging.error(f"Log file not created: {log_file}")
                return "Command executed but no output was captured"
            
            # Wait a moment for file writing to complete
            time.sleep(0.5)
            
            try:
                with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                    log_content = f.read()
                
                # MUCH SIMPLER APPROACH: Just filter beginning and end of log file
                lines = log_content.strip().split('\n')
                
                # Find the first actual command (first line that starts with a dot that's not log related)
                start_index = 0
                for i, line in enumerate(lines):
                    if line.strip().startswith('.') and 'log ' not in line and 'capture log close' not in line:
                        # Found the first actual command, so output starts right after this
                        start_index = i + 1
                        break
                
                # Find end of output (the "capture log close" or "end of do-file" at the end)
                end_index = len(lines)
                for i in range(len(lines)-1, 0, -1):
                    if 'capture log close' in lines[i] or 'end of do-file' in lines[i]:
                        end_index = i
                        break
                
                # Extract just the middle part (the actual output)
                result_lines = []
                for i in range(start_index, end_index):
                    line = lines[i].rstrip()  # Remove trailing whitespace
                    
                    # Skip empty lines at beginning or end
                    if not line.strip():
                        continue
                    
                    # Keep command lines (don't filter out lines starting with '.')
                    
                    # Remove consecutive blank lines (keep just one)
                    if (not line.strip() and result_lines and not result_lines[-1].strip()):
                        continue
                        
                    result_lines.append(line)
                
                # Clean up temporary files
                try:
                    os.unlink(do_file)
                    os.unlink(log_file)
                except Exception as e:
                    logging.warning(f"Could not delete temporary files: {str(e)}")
                
                # Add timestamp to the result
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                command_entry = f"[{timestamp}] {command}"
                
                # Return properly formatted output
                if not result_lines:
                    result = "Command executed successfully (no output)"
                else:
                    result = "\n".join(result_lines)

                # Use graphs captured in interactive mode (if any)
                # These were already captured right after execution while still in memory
                if graphs_from_interactive:
                    graph_info = "\n\n" + "="*60 + "\n"
                    graph_info += f"GRAPHS DETECTED: {len(graphs_from_interactive)} graph(s) created\n"
                    graph_info += "="*60 + "\n"
                    for graph in graphs_from_interactive:
                        # Include command if available, using special format for JavaScript parsing
                        if 'command' in graph and graph['command']:
                            graph_info += f"  • {graph['name']}: {graph['path']} [CMD: {graph['command']}]\n"
                        else:
                            graph_info += f"  • {graph['name']}: {graph['path']}\n"
                    result += graph_info
                    logging.info(f"Added {len(graphs_from_interactive)} graphs to output (from interactive mode)")
                else:
                    logging.debug("No graphs were captured in interactive mode")

                # Disable graph listing after detection
                try:
                    from pystata.config import stlib, get_encode_str
                    stlib.StataSO_Execute(get_encode_str("qui _gr_list off"), False)
                    logging.debug("Disabled graph listing")
                except Exception as e:
                    logging.warning(f"Could not disable graph listing: {str(e)}")

                # For interactive window, just return the current result
                # The client will handle displaying history
                return result
                
            except Exception as e:
                error_msg = f"Error reading log file: {str(e)}"
                logging.error(error_msg)
                return error_msg
                
        except Exception as e:
            error_msg = f"Error executing Stata command: {str(e)}"
            logging.error(error_msg)
            # Add to command history
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            command_entry = f"[{timestamp}] {command}"
            command_history.append({"command": command_entry, "result": error_msg})
            return error_msg
            
    else:
        error_msg = "Stata is not available. Please check if Stata is installed and configured correctly."
        logging.error(error_msg)
        # Add to command history
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        command_entry = f"[{timestamp}] {command}"
        command_history.append({"command": command_entry, "result": error_msg})
        return error_msg

def detect_and_export_graphs():
    """Detect and export any graphs created by Stata commands

    Returns:
        List of dictionaries with graph info: [{"name": "graph1", "path": "/path/to/graph.png"}, ...]
    """
    global stata_available, has_stata, extension_path

    if not (has_stata and stata_available):
        logging.debug("detect_and_export_graphs: Stata not available, skipping")
        return []

    try:
        import sfi
        from pystata.config import stlib, get_encode_str

        # Log platform for debugging Windows-specific issues
        logging.debug(f"detect_and_export_graphs: Platform={platform.system()}, extension_path={extension_path}")

        # Get list of graphs using low-level API like PyStata does
        logging.debug("Checking for graphs using _gr_list (low-level API)...")

        # Get the list (_gr_list should already be on from before command execution)
        rc = stlib.StataSO_Execute(get_encode_str("qui _gr_list list"), False)
        logging.debug(f"_gr_list list returned rc={rc}")
        gnamelist = sfi.Macro.getGlobal("r(_grlist)")
        logging.debug(f"r(_grlist) returned: '{gnamelist}' (type: {type(gnamelist)}, length: {len(gnamelist) if gnamelist else 0})")

        if not gnamelist:
            logging.debug("No graphs found (gnamelist is empty)")
            return []

        graphs_info = []
        graph_names = gnamelist.split()
        logging.info(f"Found {len(graph_names)} graph(s): {graph_names}")

        # Create graphs directory in extension path or temp
        if extension_path:
            graphs_dir = os.path.join(extension_path, 'graphs')
        else:
            graphs_dir = os.path.join(tempfile.gettempdir(), 'stata_mcp_graphs')

        os.makedirs(graphs_dir, exist_ok=True)
        logging.debug(f"Exporting graphs to: {graphs_dir}")

        # Export each graph to PNG
        for i, gname in enumerate(graph_names):
            try:
                # Display the graph first using low-level API
                # Stata graph names should not be quoted in graph display command
                gph_disp = f'qui graph display {gname}'
                rc = stlib.StataSO_Execute(get_encode_str(gph_disp), False)
                if rc != 0:
                    logging.warning(f"Failed to display graph '{gname}' (rc={rc})")
                    continue

                # Export as PNG (best for VS Code display)
                # Use a sanitized filename but keep the original name for the name() option
                graph_file = os.path.join(graphs_dir, f'{gname}.png')
                # Use forward slashes in Stata command to avoid backslash escape sequence issues on Windows
                graph_file_stata = graph_file.replace('\\', '/')
                # The name() option does NOT need quotes - it's a Stata name, not a string
                gph_exp = f'qui graph export "{graph_file_stata}", name({gname}) replace width(800) height(600)'

                logging.debug(f"Executing graph export command: {gph_exp}")
                rc = stlib.StataSO_Execute(get_encode_str(gph_exp), False)
                if rc != 0:
                    logging.warning(f"Failed to export graph '{gname}' (rc={rc})")
                    continue

                if os.path.exists(graph_file):
                    # Normalize path to forward slashes for cross-platform compatibility
                    normalized_path = graph_file.replace('\\', '/')
                    graphs_info.append({
                        "name": gname,
                        "path": normalized_path
                    })
                    logging.info(f"Exported graph '{gname}' to {graph_file}")
                else:
                    logging.warning(f"Failed to export graph '{gname}' - file not created")

            except Exception as e:
                logging.error(f"Error exporting graph '{gname}': {str(e)}")
                continue

        return graphs_info

    except Exception as e:
        logging.error(f"Error detecting graphs: {str(e)}")
        return []

def display_graphs_interactive(graph_format='png', width=800, height=600):
    """Display graphs using PyStata's interactive approach (similar to Jupyter)

    This function mimics PyStata's grdisplay.py approach for exporting graphs.
    It should be called immediately after command execution while graphs are still in memory.

    Note: Call reset_graph_tracking (off then on) BEFORE execution to ensure only
    NEW graphs are detected.

    Args:
        graph_format: Format for exported graphs ('svg', 'png', or 'pdf')
        width: Width for graph export (pixels for png, inches for svg/pdf)
        height: Height for graph export (pixels for png, inches for svg/pdf)

    Returns:
        List of dictionaries with graph info: [{"name": "graph1", "path": "/path/to/graph.png", "format": "png", "command": "scatter y x"}, ...]
    """
    global stata_available, has_stata, extension_path

    if not (has_stata and stata_available):
        logging.debug("display_graphs_interactive: Stata not available, skipping")
        return []

    try:
        import sfi
        from pystata.config import stlib, get_encode_str

        # Log platform for debugging Windows-specific issues
        logging.debug(f"display_graphs_interactive: Platform={platform.system()}, extension_path={extension_path}")

        # Use the same approach as PyStata's grdisplay.py
        logging.debug(f"Interactive graph display: checking for graphs (format: {graph_format})...")

        # Get the list of graphs (_gr_list should already be on from before file execution)
        rc = stlib.StataSO_Execute(get_encode_str("qui _gr_list list"), False)
        logging.debug(f"_gr_list list returned rc={rc}")
        gnamelist = sfi.Macro.getGlobal("r(_grlist)")
        logging.debug(f"r(_grlist) returned: '{gnamelist}' (type: {type(gnamelist)}, length: {len(gnamelist) if gnamelist else 0})")

        if not gnamelist:
            logging.debug("No graphs found in interactive mode")
            return []

        graphs_info = []
        graph_names = gnamelist.split()
        logging.info(f"Found {len(graph_names)} graph(s) in interactive mode: {graph_names}")

        # Create graphs directory
        if extension_path:
            graphs_dir = os.path.join(extension_path, 'graphs')
        else:
            graphs_dir = os.path.join(tempfile.gettempdir(), 'stata_mcp_graphs')

        os.makedirs(graphs_dir, exist_ok=True)
        logging.debug(f"Exporting graphs to: {graphs_dir}")

        # Export each graph using PyStata's approach
        for i, gname in enumerate(graph_names):
            try:
                # Display the graph first (required before export)
                # Stata graph names should not be quoted in graph display command
                gph_disp = f'qui graph display {gname}'
                logging.debug(f"Displaying graph: {gph_disp}")
                rc = stlib.StataSO_Execute(get_encode_str(gph_disp), False)
                if rc != 0:
                    logging.warning(f"Failed to display graph '{gname}' (rc={rc})")
                    continue

                # Determine file extension and export command based on format
                # Use forward slashes in Stata command to avoid backslash escape sequence issues on Windows
                if graph_format == 'svg':
                    graph_file = os.path.join(graphs_dir, f'{gname}.svg')
                    graph_file_stata = graph_file.replace('\\', '/')
                    if width and height:
                        gph_exp = f'qui graph export "{graph_file_stata}", name({gname}) replace width({width}) height({height})'
                    else:
                        gph_exp = f'qui graph export "{graph_file_stata}", name({gname}) replace'
                elif graph_format == 'pdf':
                    graph_file = os.path.join(graphs_dir, f'{gname}.pdf')
                    graph_file_stata = graph_file.replace('\\', '/')
                    # For PDF, use xsize/ysize instead of width/height
                    if width and height:
                        gph_exp = f'qui graph export "{graph_file_stata}", name({gname}) replace xsize({width/96:.2f}) ysize({height/96:.2f})'
                    else:
                        gph_exp = f'qui graph export "{graph_file_stata}", name({gname}) replace'
                else:  # png (default)
                    graph_file = os.path.join(graphs_dir, f'{gname}.png')
                    graph_file_stata = graph_file.replace('\\', '/')
                    if width and height:
                        gph_exp = f'qui graph export "{graph_file_stata}", name({gname}) replace width({width}) height({height})'
                    else:
                        gph_exp = f'qui graph export "{graph_file_stata}", name({gname}) replace width(800) height(600)'

                # Export the graph
                logging.debug(f"Exporting graph: {gph_exp}")
                rc = stlib.StataSO_Execute(get_encode_str(gph_exp), False)
                if rc != 0:
                    logging.warning(f"Failed to export graph '{gname}' (rc={rc})")
                    continue

                if os.path.exists(graph_file):
                    # Normalize path to forward slashes for cross-platform compatibility
                    normalized_path = graph_file.replace('\\', '/')
                    graph_dict = {
                        "name": gname,
                        "path": normalized_path,
                        "format": graph_format
                    }
                    graphs_info.append(graph_dict)
                    logging.info(f"Exported graph '{gname}' to {graph_file} (format: {graph_format})")
                else:
                    logging.warning(f"Graph file not found after export: {graph_file}")

            except Exception as e:
                logging.error(f"Error exporting graph '{gname}': {str(e)}")
                continue

        return graphs_info

    except Exception as e:
        logging.error(f"Error in interactive graph display: {str(e)}")
        logging.debug(f"Interactive display error details: {traceback.format_exc()}")
        return []

def run_stata_selection(
    selection: str,
    working_dir: Optional[str] = None,
    auto_detect_graphs: bool = False
) -> str:
    """Run selected Stata code.

    Args:
        selection: The Stata code to run
        working_dir: Optional working directory to change to before execution
        auto_detect_graphs: Whether to detect and export graphs

    Returns:
        Stata output as a string
    """
    # Preprocess: Join lines with /// continuation into single logical lines
    # This ensures multi-line commands with continuations work correctly
    processed_selection = join_stata_line_continuations(selection)

    # If a working directory is provided, prepend a cd command
    if working_dir and os.path.isdir(working_dir):
        logging.info(f"Changing working directory to: {working_dir}")
        # Normalize path for the OS
        working_dir = os.path.normpath(working_dir)
        # Use forward slashes for Stata commands to avoid escape sequence issues on Windows
        working_dir_stata = working_dir.replace('\\', '/')
        # Use double quotes for the cd command to handle spaces
        cd_command = f'cd "{working_dir_stata}"'
        # Combine cd command with the processed selection
        full_command = f"{cd_command}\n{processed_selection}"
        return run_stata_command(full_command, auto_detect_graphs=auto_detect_graphs)
    else:
        return run_stata_command(processed_selection, auto_detect_graphs=auto_detect_graphs)

def run_stata_file(
    file_path: str,
    timeout: int = 600,
    auto_name_graphs: bool = False,
    working_dir: Optional[str] = None
) -> str:
    """Run a Stata .do file with improved handling for long-running processes.

    Args:
        file_path: The path to the .do file to run
        timeout: Timeout in seconds (default: 600 seconds / 10 minutes)
        auto_name_graphs: Whether to automatically add names to graphs (default: False for MCP/LLM calls)
        working_dir: Working directory to cd to before running (None = defaults to .do file's directory).
                     This affects where outputs like graph export, save, etc. are written.
                     Log files are saved to the location configured in logFileLocation setting (separate from working dir).
    """
    # Set timeout from parameter instead of hardcoding
    MAX_TIMEOUT = timeout
    
    try:
        original_path = file_path

        resolved_path, tried_paths = resolve_do_file_path(file_path)
        if not resolved_path:
            tried_display = ', '.join(tried_paths) if tried_paths else os.path.normpath(file_path)
            error_msg = f"Error: File not found: {original_path}. Tried these paths: {tried_display}"
            logging.error(error_msg)
            
            # Add more helpful error message for Windows
            error_msg += get_windows_path_help_message()

            return error_msg

        file_path = resolved_path
        
        # Verify file exists (final check)
        if not os.path.exists(file_path):
            error_msg = f"Error: File not found: {file_path}"
            logging.error(error_msg)

            # Add more helpful error message for Windows
            error_msg += get_windows_path_help_message()

            return error_msg
            
        # Check file extension
        if not file_path.lower().endswith('.do'):
            error_msg = f"Error: File must be a Stata .do file with .do extension: {file_path}"
            logging.error(error_msg)
            return error_msg

        logging.info(f"Running Stata do file: {file_path}")

        # Ensure file_path is absolute for consistent behavior
        file_path = os.path.abspath(file_path)

        # Get the directory and filename for later use
        do_file_dir = os.path.dirname(file_path)  # This is now guaranteed to be absolute
        do_file_name = os.path.basename(file_path)
        do_file_base = os.path.splitext(do_file_name)[0]

        # Create a custom log file path based on user settings
        # The log file path will be absolute, allowing it to be saved anywhere
        # regardless of Stata's current working directory
        custom_log_file = get_log_file_path(file_path, do_file_base)
        logging.info(f"Will save log to: {custom_log_file}")
        
        # Read the do file content
        do_file_content = ""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                do_file_content = f.read()

            # Create a modified version with log commands commented out and auto-name graphs
            modified_content = ""
            log_commands_found = 0
            graph_counter = 0

            # First, join lines with Stata line continuation (///) into single logical lines
            # This prevents options like legend(off) from being treated as separate commands
            raw_lines = do_file_content.splitlines()
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
            # Handle any remaining content (in case file ends with ///)
            if current_line:
                joined_lines.append(current_line)

            # Process line by line to comment out log commands and add graph names where needed
            cls_commands_found = 0
            for line in joined_lines:
                # Ensure line is a string (defensive programming)
                line = str(line) if line is not None else ""

                # Check if this line has a log command
                if re.match(r'^\s*(log\s+using|log\s+close|capture\s+log\s+close)', line, re.IGNORECASE):
                    modified_content += f"* COMMENTED OUT BY MCP: {line}\n"
                    log_commands_found += 1
                    continue

                # Check if this is a cls command
                if re.match(r'^\s*cls\s*$', line, re.IGNORECASE):
                    modified_content += f"* COMMENTED OUT BY MCP: {line}\n"
                    cls_commands_found += 1
                    continue

                # Only auto-name graphs if called from VS Code extension (not from LLM/MCP)
                if auto_name_graphs:
                    # Check if this is a graph creation command that might need a name
                    # Match: scatter, histogram, twoway, kdensity, graph bar/box/dot/etc (but not graph export)
                    graph_match = re.match(r'^(\s*)(scatter|histogram|twoway|kdensity|graph\s+(bar|box|dot|pie|matrix|hbar|hbox|combine))\s+(.*)$', line, re.IGNORECASE)

                    if graph_match:
                        indent = str(graph_match.group(1) or "")
                        graph_cmd = str(graph_match.group(2) or "")

                        # Extract and ensure rest is a string
                        rest_raw = graph_match.group(4) if graph_match.lastindex >= 4 else ""
                        if rest_raw is None:
                            rest_raw = ""
                        # Force conversion to string to handle any edge cases
                        rest = str(rest_raw)

                        # Double-check rest is a string before any operations
                        if not isinstance(rest, str):
                            logging.warning(f"rest is not a string, type: {type(rest)}, value: {rest}, converting to string")
                            rest = str(rest)

                        # Check if it already has name() option
                        if not re.search(r'\bname\s*\(', rest, re.IGNORECASE):
                            # Add automatic unique name
                            graph_counter += 1
                            graph_name = f"graph{graph_counter}"

                            # Add name option - if there's a comma, add after it; otherwise add with comma
                            if ',' in rest:
                                # Insert name option right after the first comma
                                # Ensure rest is definitely a string before re.sub
                                rest = str(rest)
                                rest = re.sub(r',', f', name({graph_name}, replace)', rest, 1)
                            else:
                                # No comma yet, add it
                                rest = rest.rstrip() + f', name({graph_name}, replace)'

                            modified_content += f"{indent}{graph_cmd} {rest}\n"
                            logging.debug(f"Auto-named graph: {graph_name}")
                            continue

                # Keep line as-is (including graph export commands)
                modified_content += f"{line}\n"

            logging.info(f"Found and commented out {log_commands_found} log commands in the do file")
            if cls_commands_found > 0:
                logging.info(f"Found and commented out {cls_commands_found} cls commands in the do file")
            if graph_counter > 0:
                logging.info(f"Auto-named {graph_counter} graph commands")
            
            # Save the modified content to a temporary file
            with tempfile.NamedTemporaryFile(

                suffix='.do', delete=False, mode='w', encoding='utf-8'

            ) as temp_do:
                # First close any existing log files
                temp_do.write(f"capture log close _all\n")
                # Change working directory based on working_dir parameter
                # If working_dir is None, default to .do file's directory (like native Stata)
                # Otherwise, cd to the specified directory
                # The log file uses an absolute path, so it's saved to the configured location
                effective_working_dir = working_dir if working_dir is not None else do_file_dir
                # Use forward slashes for Stata commands to avoid escape sequence issues on Windows
                wd = os.path.normpath(effective_working_dir).replace('\\', '/')
                temp_do.write(f"cd \"{wd}\"\n")
                logging.info(f"Setting working directory to: {wd}")
                # Note: _gr_list on is enabled externally before .do file execution
                # Note: Graph names are auto-injected above into modified_content
                # Then add our own log command with absolute path
                # Use forward slashes for Stata commands to avoid escape sequence issues on Windows
                log_file_stata = custom_log_file.replace('\\', '/')
                temp_do.write(f"log using \"{log_file_stata}\", replace text\n")
                temp_do.write(modified_content)
                temp_do.write(f"\ncapture log close _all\n")  # Ensure all logs are closed at the end
                # Note: We intentionally do NOT disable _gr_list so graphs persist for detection
                modified_do_file = temp_do.name
                
            logging.info(f"Created modified do file at {modified_do_file}")
                
        except Exception as e:
            import traceback
            error_msg = f"Error processing do file: {str(e)}"
            logging.error(error_msg)
            logging.error(f"Traceback: {traceback.format_exc()}")
            # Include line number and more details
            tb = traceback.extract_tb(e.__traceback__)
            if tb:
                last_frame = tb[-1]
                error_msg += f"\n  at line {last_frame.lineno} in {last_frame.name}"
            return error_msg
            
        # Prepare command entry for history
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        command_entry = f"[{timestamp}] do '{file_path}'"
        
        # Create initial result to update the user
        initial_result = f">>> {command_entry}\nExecuting Stata do file with timeout: {MAX_TIMEOUT} seconds ({MAX_TIMEOUT/60:.1f} minutes)...\n"
        
        # Need to define result variable here so it's accessible in all code paths
        result = initial_result
        
        # Create a properly escaped file path for Stata
        if platform.system() == "Windows":
            # On Windows, escape backslashes and quotes
            stata_path = modified_do_file.replace('"', '\\"')
            # Ensure the path is properly quoted for Windows
            do_command = f'do "{stata_path}"'
        else:
            # On Unix systems (macOS/Linux), use double quotes for better compatibility
            # Double quotes work more reliably across systems
            do_command = f'do "{modified_do_file}"'
        
        # Run the command in background with timeout
        try:
            # Execute the Stata command
            logging.info(f"Running modified do file: {do_command}")
            
            # Set up for PyStata execution
            if has_stata and stata_available:
                # Reset graph tracking BEFORE execution to only detect NEW graphs
                try:
                    from pystata.config import stlib, get_encode_str
                    stlib.StataSO_Execute(get_encode_str("qui _gr_list off"), False)
                    stlib.StataSO_Execute(get_encode_str("qui _gr_list on"), False)
                    logging.debug("Graph list reset for file execution")
                except Exception as e:
                    logging.warning(f"Could not reset graph listing: {str(e)}")

                # Record start time for timeout tracking
                start_time = time.time()
                last_update_time = start_time
                update_interval = 60  # Update every 60 seconds (1 minute) initially
                
                # Initialize log tracking
                log_file_exists = False
                last_log_size = 0
                last_reported_lines = 0
                
                # Execute command via PyStata in separate thread to allow polling
                stata_thread = None
                stata_error = None
                
                def run_stata_thread():
                    nonlocal stata_error
                    try:
                        # Make sure to properly quote the path - this is the key fix
                        # Use inline=False because inline=True calls _gr_list off!
                        if platform.system() == "Windows":
                            # Make sure Windows paths are properly escaped
                            globals()['stata'].run(do_command, echo=False, inline=False)
                        else:
                            # On macOS/Linux, double-check the quoting - adding extra safety
                            if not (do_command.startswith('do "') or do_command.startswith("do '")):
                                do_command_fixed = f'do "{stata_path}"'
                                globals()['stata'].run(do_command_fixed, echo=False, inline=False)
                            else:
                                globals()['stata'].run(do_command, echo=False, inline=False)
                    except KeyboardInterrupt:
                        stata_error = "cancelled"
                        logging.debug("Stata thread received KeyboardInterrupt")
                        # Try to call StataSO_SetBreak to clean up Stata state
                        try:
                            from pystata.config import stlib
                            if stlib is not None:
                                stlib.StataSO_SetBreak()
                        except:
                            pass
                    except Exception as e:
                        stata_error = str(e)
                
                import threading
                stata_thread = threading.Thread(target=run_stata_thread)
                stata_thread.daemon = True
                stata_thread.start()

                # Register execution for cancellation support
                global current_execution_id
                exec_id = f"exec_{int(time.time() * 1000)}"
                with execution_lock:
                    current_execution_id = exec_id
                    execution_registry[exec_id] = {
                        'thread': stata_thread,
                        'start_time': start_time,
                        'cancelled': False,
                        'file': file_path
                    }
                logging.info(f"Registered execution {exec_id} for file {file_path}")

                # Poll for progress while command is running
                while stata_thread.is_alive():
                    # Check for timeout
                    current_time = time.time()
                    elapsed_time = current_time - start_time
                    
                    if elapsed_time > MAX_TIMEOUT:
                        logging.warning(f"Execution timed out after {MAX_TIMEOUT} seconds")
                        result += f"\n*** TIMEOUT: Execution exceeded {MAX_TIMEOUT} seconds ({MAX_TIMEOUT/60:.1f} minutes) ***\n"
                        
                        # Force terminate Stata operation with increasing severity
                        termination_successful = False

                        try:
                            # ATTEMPT 1: Use PyStata's native break mechanism (StataSO_SetBreak)
                            logging.warning(f"TIMEOUT - Attempt 1: Using StataSO_SetBreak()")
                            try:
                                from pystata.config import stlib
                                if stlib is not None:
                                    stlib.StataSO_SetBreak()
                                    logging.warning("Called StataSO_SetBreak() to interrupt Stata")
                                    time.sleep(0.5)  # Give it a moment
                                    if not stata_thread.is_alive():
                                        termination_successful = True
                                        logging.warning("Thread terminated via StataSO_SetBreak()")
                            except Exception as e:
                                logging.warning(f"StataSO_SetBreak() failed: {str(e)}")

                            # ATTEMPT 2: Try to raise KeyboardInterrupt in the thread using ctypes
                            if not termination_successful and stata_thread.is_alive():
                                logging.warning(f"TIMEOUT - Attempt 2: Raising KeyboardInterrupt in thread via ctypes")
                                try:
                                    import ctypes
                                    thread_id = stata_thread.ident
                                    if thread_id is not None:
                                        # Raise KeyboardInterrupt in the target thread
                                        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                                            ctypes.c_ulong(thread_id),
                                            ctypes.py_object(KeyboardInterrupt)
                                        )
                                        if res == 1:
                                            logging.warning("KeyboardInterrupt raised in thread")
                                            time.sleep(1.0)  # Give more time for interrupt to propagate
                                            if not stata_thread.is_alive():
                                                termination_successful = True
                                                logging.warning("Thread terminated via KeyboardInterrupt")
                                        else:
                                            # Reset if more than one thread affected
                                            if res > 1:
                                                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                                                    ctypes.c_ulong(thread_id),
                                                    None
                                                )
                                except Exception as e:
                                    logging.warning(f"Thread interrupt failed: {str(e)}")

                            # Note: We do NOT try to kill processes because:
                            # 1. Stata runs as a shared library within the Python process (not separate)
                            # 2. pkill -f "stata" would match and kill stata_mcp_server.py itself!
                            # StataSO_SetBreak() is the correct and only way to interrupt Stata
                            if not termination_successful:
                                logging.warning(f"TIMEOUT - StataSO_SetBreak did not terminate thread immediately")
                                logging.warning("Stata will stop at the next break point in execution")
                        except Exception as term_error:
                            logging.error(f"Error during forced termination: {str(term_error)}")
                        
                        # Set a flag indicating timeout regardless of termination success
                        stata_error = f"Operation timed out after {MAX_TIMEOUT} seconds"
                        logging.warning(f"Setting timeout error: {stata_error}")
                        break

                    # Check for user-initiated cancellation
                    with execution_lock:
                        if exec_id in execution_registry and execution_registry[exec_id].get('cancelled', False):
                            logging.debug(f"Execution {exec_id} was cancelled by user")
                            stata_error = "cancelled"
                            break

                    # Check if it's time for an update
                    if current_time - last_update_time >= update_interval:
                        # IMPORTANT: Log progress frequently to keep SSE connection alive for long-running scripts
                        logging.info(f"⏱️  Execution in progress: {elapsed_time:.0f}s elapsed ({elapsed_time/60:.1f} minutes) of {MAX_TIMEOUT}s timeout")

                        # Check if log file exists and has been updated
                        if os.path.exists(custom_log_file):
                            log_file_exists = True

                            # Check log file size
                            current_log_size = os.path.getsize(custom_log_file)

                            # If log has grown, report progress
                            if current_log_size > last_log_size:
                                try:
                                    with open(custom_log_file, 'r', encoding='utf-8', errors='replace') as log:
                                        log_content = log.read()
                                        lines = log_content.splitlines()

                                        # Report only new lines since last update
                                        if last_reported_lines < len(lines):
                                            new_lines = lines[last_reported_lines:]

                                            # Only report meaningful lines (skip empty lines and headers)
                                            meaningful_lines = [line for line in new_lines if line.strip() and not line.startswith('-')]

                                            # If we have meaningful content, add it to result
                                            if meaningful_lines:
                                                progress_update = f"\n*** Progress update ({elapsed_time:.0f} seconds) ***\n"
                                                progress_update += "\n".join(meaningful_lines[-10:])  # Show last 10 lines
                                                result += progress_update
                                                # Also log the progress for SSE keep-alive
                                                logging.info(f"📊 Progress: Log file grew to {current_log_size} bytes, {len(meaningful_lines)} new meaningful lines")

                                            last_reported_lines = len(lines)
                                except Exception as e:
                                    logging.warning(f"Error reading log for progress update: {str(e)}")

                            last_log_size = current_log_size

                        last_update_time = current_time
                        
                        # Adaptive polling - keep interval at 60 seconds to maintain SSE connection
                        # This ensures we send at least one log message every 60 seconds (1 minute) to keep the connection alive
                        if elapsed_time > 600:  # After 10 minutes
                            update_interval = 60  # Check every 60 seconds (1 minute)
                        elif elapsed_time > 300:  # After 5 minutes
                            update_interval = 60  # Check every 60 seconds (1 minute)
                        elif elapsed_time > 60:  # After 1 minute
                            update_interval = 60  # Check every 60 seconds (1 minute)
                    
                    # Sleep briefly to avoid consuming too much CPU
                    time.sleep(0.5)
                
                # Thread completed or timed out
                if stata_error:
                    # Check if this was a user-initiated cancellation
                    # Cancellation can be detected by:
                    # 1. stata_error == "cancelled" (set in polling loop)
                    # 2. "--Break--" in error message (Stata's break exception)
                    # 3. execution was marked as cancelled in registry
                    is_cancelled = (
                        stata_error == "cancelled" or
                        "--Break--" in str(stata_error) or
                        (exec_id in execution_registry and execution_registry[exec_id].get('cancelled', False))
                    )

                    if is_cancelled:
                        logging.debug("Execution was cancelled by user")
                        # Read final log to include any output up to the break
                        if os.path.exists(custom_log_file):
                            try:
                                with open(custom_log_file, 'r', encoding='utf-8', errors='replace') as log:
                                    log_content = log.read()
                                    # Extract just the output portion (after header)
                                    lines = log_content.splitlines()
                                    start_index = 0
                                    for i, line in enumerate(lines):
                                        if '-------------' in line and i < 20:
                                            start_index = i + 1
                                            break
                                    if start_index < len(lines):
                                        result = '\n'.join(lines[start_index:])
                            except Exception as e:
                                logging.debug(f"Could not read log file for cancelled execution: {e}")
                        # Add clear cancellation indicator and print to stdout
                        # (stdout is captured by VS Code extension for real-time display)
                        print("\n=== Execution stopped ===", flush=True)
                        result += "\n\n=== Execution stopped ==="
                        # Return result without error wrapper
                        command_history.append({"command": command_entry, "result": result})
                        return result
                    else:
                        error_msg = f"Error executing Stata command: {stata_error}"
                        logging.error(error_msg)
                        result += f"\n*** ERROR: {stata_error} ***\n"

                        # Add command to history and return
                        command_history.append({"command": command_entry, "result": result})
                        return result
                
                # Read final log output
                if os.path.exists(custom_log_file):
                    try:
                        with open(custom_log_file, 'r', encoding='utf-8', errors='replace') as log:
                            log_content = log.read()
                            
                            # Clean up log content - remove headers and Stata startup info
                            lines = log_content.splitlines()
                            result_lines = []
                            
                            # Skip Stata header if present (search for the separator line)
                            start_index = 0
                            for i, line in enumerate(lines):
                                if '-------------' in line and i < 20:  # Look in first 20 lines
                                    start_index = i + 1
                                    break
                            
                            # Process the content
                            for i in range(start_index, len(lines)):
                                # Ensure line is a string (defensive programming)
                                line = str(lines[i]) if lines[i] is not None else ""
                                line = line.rstrip()

                                # Skip empty lines at beginning or redundant empty lines
                                if not line.strip() and (not result_lines or not result_lines[-1].strip()):
                                    continue

                                # Clean up SMCL formatting if present
                                if '{' in line:
                                    line = re.sub(r'\{[^}]*\}', '', line)  # Remove {...} codes
                                    
                                result_lines.append(line)
                            
                            # Add completion message with final log content
                            completion_msg = f"\n*** Execution completed in {time.time() - start_time:.1f} seconds ***\n"
                            completion_msg += "Final output:\n"
                            completion_msg += "\n".join(result_lines)

                            # Replace the result with a clean summary
                            result = f">>> {command_entry}\n{completion_msg}"

                            # Only detect and export graphs if called from VS Code extension (not from LLM/MCP)
                            if auto_name_graphs:
                                # Detect and export any graphs created by the do file
                                # Using interactive mode which should work because inline=True keeps graphs in memory
                                try:
                                    logging.debug("Attempting to detect graphs from do file (interactive mode)...")
                                    graphs = display_graphs_interactive(graph_format='png', width=800, height=600)
                                    logging.debug(f"Graph detection returned: {graphs}")
                                    if graphs:
                                        graph_info = "\n\n" + "="*60 + "\n"
                                        graph_info += f"GRAPHS DETECTED: {len(graphs)} graph(s) created\n"
                                        graph_info += "="*60 + "\n"
                                        for graph in graphs:
                                            # Include command if available, using special format for JavaScript parsing
                                            if 'command' in graph and graph['command']:
                                                graph_info += f"  • {graph['name']}: {graph['path']} [CMD: {graph['command']}]\n"
                                            else:
                                                graph_info += f"  • {graph['name']}: {graph['path']}\n"
                                        result += graph_info
                                        logging.info(f"Detected {len(graphs)} graphs from do file: {[g['name'] for g in graphs]}")
                                    else:
                                        logging.debug("No graphs detected from do file")
                                except Exception as e:
                                    logging.warning(f"Error detecting graphs: {str(e)}")
                                    logging.debug(f"Graph detection error details: {traceback.format_exc()}")

                            # Log the final file location
                            result += f"\n\nLog file saved to: {custom_log_file}"
                    except Exception as e:
                        logging.error(f"Error reading final log: {str(e)}")
                        result += f"\n*** WARNING: Error reading final log: {str(e)} ***\n"
                else:
                    logging.warning(f"Log file not found after execution: {custom_log_file}")
                    result += f"\n*** WARNING: Log file not found after execution ***\n"
                    
                    # Try to get a status update from Stata
                    try:
                        status = run_stata_command("display _rc", clear_history=False)
                        result += f"\nStata return code: {status}\n"
                    except Exception as e:
                        pass
            else:
                # Stata not available
                error_msg = "Stata is not available. Please check if Stata is installed and configured correctly."
                logging.error(error_msg)
                result = f">>> {command_entry}\n{error_msg}"
        except Exception as e:
            error_msg = f"Error running do file: {str(e)}"
            logging.error(error_msg)
            result = f">>> {command_entry}\n{error_msg}"
        
        # Add to command history and return result
        command_history.append({"command": command_entry, "result": result})

        # Cleanup: unregister execution
        with execution_lock:
            if 'exec_id' in dir() and exec_id in execution_registry:
                del execution_registry[exec_id]
                logging.info(f"Unregistered execution {exec_id}")
            current_execution_id = None

        return result

    except Exception as e:
        error_msg = f"Error in run_stata_file: {str(e)}"
        logging.error(error_msg)

        # Cleanup on error: unregister execution
        with execution_lock:
            if 'exec_id' in dir() and exec_id in execution_registry:
                del execution_registry[exec_id]
            current_execution_id = None

        return error_msg

# Function to kill any process using the specified port
def kill_process_on_port(port):
    """Kill any process that is currently using the specified port"""
    try:
        if platform.system() == "Windows":
            # Windows command to find and kill process on port
            find_cmd = f"netstat -ano | findstr :{port}"
            try:
                result = subprocess.check_output(find_cmd, shell=True).decode()
                
                if result:
                    # Extract PID from the result
                    for line in result.strip().split('\n'):
                        if f":{port}" in line and "LISTENING" in line:
                            pid = line.strip().split()[-1]
                            logging.info(f"Found process with PID {pid} using port {port}")
                            
                            # Kill the process
                            kill_cmd = f"taskkill /F /PID {pid}"
                            subprocess.check_output(kill_cmd, shell=True)
                            logging.info(f"Killed process with PID {pid}")
                            break
                else:
                    logging.info(f"No process found using port {port}")
            except subprocess.CalledProcessError:
                # No process found using the port (findstr returns 1 when no matches found)
                logging.info(f"No process found using port {port}")
        else:
            # macOS/Linux command to find and kill process on port
            try:
                # Find the process IDs using the port
                find_cmd = f"lsof -i :{port} -t"
                result = subprocess.check_output(find_cmd, shell=True).decode().strip()
                
                if result:
                    # Handle multiple PIDs (one per line)
                    pids = result.split('\n')
                    for pid in pids:
                        pid = pid.strip()
                        if pid:
                            logging.info(f"Found process with PID {pid} using port {port}")
                            
                            # Kill the process
                            try:
                                os.kill(int(pid), signal.SIGKILL)  # Use SIGKILL for more forceful termination
                                logging.info(f"Killed process with PID {pid}")
                            except Exception as kill_error:
                                logging.warning(f"Error killing process with PID {pid}: {str(kill_error)}")
                    
                    # Wait a moment to ensure the port is released
                    time.sleep(1)
                else:
                    logging.info(f"No process found using port {port}")
            except subprocess.CalledProcessError:
                # No process found using the port
                logging.info(f"No process found using port {port}")
                
    except Exception as e:
        logging.warning(f"Error killing process on port {port}: {str(e)}")
    
    # Double-check if port is still in use
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('localhost', port))
            if result == 0:
                logging.warning(f"Port {port} is still in use after attempting to kill processes")
                logging.warning(f"Please manually kill any processes using port {port} or use a different port")
            else:
                logging.info(f"Port {port} is now available")
    except Exception as socket_error:
        logging.warning(f"Error checking port availability: {str(socket_error)}")

# Function to find an available port
def find_available_port(start_port, max_attempts=10):
    """Find an available port starting from start_port"""
    for port_offset in range(max_attempts):
        port = start_port + port_offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                if result != 0:  # Port is available
                    logging.info(f"Found available port: {port}")
                    return port
        except Exception as e:
            logging.warning(f"Error checking port {port}: {str(e)}")
    
    # If we get here, we couldn't find an available port
    logging.warning(f"Could not find an available port after {max_attempts} attempts")
    return None

# Note: API models (RunSelectionParams, RunFileParams, ToolRequest, ToolResponse)
# are now imported from api_models.py

# Define lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifespan events"""
    # Startup: Log startup
    logging.info("FastAPI application starting up")

    # Start HTTP session manager if it exists
    if hasattr(app.state, '_http_session_manager_starter'):
        logging.debug("Calling HTTP session manager startup handler")
        await app.state._http_session_manager_starter()

    yield  # Application runs

    # Shutdown: Stop HTTP session manager if it exists
    if hasattr(app.state, '_http_session_manager_stopper'):
        logging.debug("Calling HTTP session manager shutdown handler")
        await app.state._http_session_manager_stopper()

    # Cleanup if needed
    logging.info("FastAPI application shutting down")

# API Tags for documentation organization
tags_metadata = [
    {
        "name": "Execution",
        "description": "Run Stata code and .do files. Core functionality for AI assistants.",
    },
    {
        "name": "Sessions",
        "description": "Multi-session management for parallel Stata execution.",
    },
    {
        "name": "Control",
        "description": "Server control, monitoring, and execution management.",
    },
    {
        "name": "Utilities",
        "description": "Helper endpoints for graphs, data viewing, and interactive mode.",
    },
]

# Create the FastAPI app with comprehensive documentation
app = FastAPI(
    title=SERVER_NAME,
    version=SERVER_VERSION,
    description="""
# Stata MCP Server

Exposes Stata functionality to AI models via the Model Context Protocol (MCP).

## Features

- **Code Execution**: Run Stata code selections and .do files
- **Multi-Session Support**: Parallel execution with isolated sessions
- **Graph Export**: Automatic graph detection and PNG export
- **Streaming Output**: Real-time output for long-running jobs
- **Token Optimization**: Compact mode filtering for efficient AI communication

## Authentication

No authentication required for local development. For production, consider
running behind a reverse proxy with appropriate security measures.

## Rate Limiting

No built-in rate limiting. Stata execution is inherently sequential per session.
""",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=tags_metadata,
    contact={
        "name": "Stata MCP Server",
        "url": "https://github.com/hanlulong/stata-mcp",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# Define regular FastAPI routes for Stata functions
@app.post(
    "/run_selection",
    operation_id="stata_run_selection",
    response_class=Response,
    tags=["Execution"],
    summary="Run Stata code selection",
    description="Execute Stata code and return the output. Supports multi-session mode for parallel execution.",
)
async def stata_run_selection_endpoint(selection: str, session_id: str = None, working_dir: str = None) -> Response:
    """Run selected Stata code and return the output (MCP endpoint - applies compact mode filtering)

    Args:
        selection: Stata code to execute
        session_id: Optional session ID for multi-session mode (uses default session if not specified)
        working_dir: Optional working directory to change to before execution
    """
    global multi_session_enabled, session_manager

    logging.info(f"Running selection: {selection[:100]}...")
    if session_id:
        logging.info(f"Using session: {session_id}")
    if working_dir:
        logging.info(f"Working directory: {working_dir}")

    # Route through session manager if multi-session is enabled
    if multi_session_enabled and session_manager is not None:
        # Run blocking session_manager.execute in thread pool to allow concurrent requests
        # Note: Multi-session mode doesn't support working_dir yet - each session manages its own directory
        result_dict = await asyncio.to_thread(
            session_manager.execute,
            selection,
            session_id=session_id
        )
        if result_dict.get('status') == 'success':
            result = result_dict.get('output', '')
        else:
            result = f"Error: {result_dict.get('error', 'Unknown error')}"
    else:
        result = run_stata_selection(selection, working_dir=working_dir)

    # Format output for better display - replace escaped newlines with actual newlines
    formatted_result = result.replace("\\n", "\n")
    # Apply MCP output processing (compact mode filtering and token limit)
    formatted_result = process_mcp_output(formatted_result, for_mcp=True)
    return Response(content=formatted_result, media_type="text/plain")

async def stata_run_file_stream(file_path: str, timeout: int = 600, working_dir: str = None, session_id: str = None):
    """Async generator that runs Stata file and yields SSE progress events

    Streams output incrementally by monitoring the log file during execution.
    Works with both single-session and multi-session modes.

    Args:
        file_path: Path to the .do file
        timeout: Timeout in seconds
        working_dir: Optional working directory for execution
        session_id: Optional session ID for multi-session mode

    Yields:
        SSE formatted events with incremental output
    """
    import threading
    import queue as queue_module

    # Queue to communicate between threads
    result_queue = queue_module.Queue()

    # Determine log file path - must match what run_stata_file/worker uses
    abs_file_path = os.path.abspath(file_path)
    base_name = os.path.splitext(os.path.basename(abs_file_path))[0]

    # For single-session mode, use get_log_file_path() which respects user settings
    # For multi-session mode, we pass this path to the worker
    # Include session_id to prevent file locking conflicts in parallel execution
    log_file = get_log_file_path(file_path, base_name, session_id)

    logging.info(f"[STREAM] Monitoring log file: {log_file}")

    # Clear (truncate) the log file before starting new execution
    # This ensures we don't read stale content from previous runs
    try:
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        # Truncate or create empty file
        with open(log_file, 'w') as f:
            pass  # Just open and close to truncate
        logging.debug(f"[STREAM] Cleared log file: {log_file}")
    except Exception as e:
        logging.warning(f"[STREAM] Could not clear log file: {e}")

    # Pre-process the file to auto-name graphs and handle line continuations
    processed_file = preprocess_do_file_for_graphs(file_path)
    logging.debug(f"[STREAM] Pre-processed file: {processed_file}")

    # Get the original file's directory for working_dir (not the temp file's directory)
    original_file_dir = os.path.dirname(os.path.abspath(file_path))

    def run_with_progress():
        """Run Stata file in thread"""
        try:
            graphs = []  # To store detected graphs
            # Route through session manager if multi-session is enabled
            if multi_session_enabled and session_manager is not None:
                logging.info(f"[STREAM] Using multi-session mode, session_id={session_id or 'default'}")
                result_dict = session_manager.execute_file(
                    processed_file,
                    session_id=session_id,
                    timeout=float(timeout),
                    log_file=log_file,  # Pass log file path to worker
                    working_dir=original_file_dir  # Use original file's directory
                )
                if result_dict.get('status') == 'success':
                    result = result_dict.get('output', '')
                    # Extract graph info from result_dict
                    extra = result_dict.get('extra', {})
                    graphs = extra.get('graphs', []) if extra else []
                else:
                    result = f"Error: {result_dict.get('error', 'Unknown error')}"
            else:
                logging.info("[STREAM] Using single-session mode")
                # Note: run_stata_file handles graph reset and detection internally
                result = run_stata_file(processed_file, timeout=timeout, working_dir=working_dir, auto_name_graphs=True)
                # Detect graphs after execution for single-session streaming mode
                # This is needed because streaming reads log file directly, not the returned result string
                # run_stata_file already reset the graph list before execution
                try:
                    logging.debug("[STREAM] Detecting graphs for single-session mode...")
                    graphs = display_graphs_interactive(graph_format='png', width=800, height=600)
                    if graphs:
                        logging.info(f"[STREAM] Detected {len(graphs)} graph(s) in single-session mode")
                    else:
                        logging.debug("[STREAM] No graphs detected in single-session mode")
                except Exception as e:
                    logging.warning(f"[STREAM] Error detecting graphs: {str(e)}")
            result_queue.put(('success', result, graphs))
        except Exception as e:
            logging.error(f"[STREAM] Execution error: {str(e)}")
            result_queue.put(('error', str(e), []))

    # Start execution thread
    thread = threading.Thread(target=run_with_progress, daemon=True)
    thread.start()

    start_time = time.time()
    last_read_pos = 0  # Track byte position in file for incremental reading
    check_interval = 0.5  # Check every 500ms for responsive streaming

    # Monitor progress by reading log file incrementally using byte offset
    # Wrap in try-except to handle client disconnection gracefully
    # All yields are inside try-except to handle client disconnect at any point
    try:
        # Yield initial event
        yield f"data: Starting execution of {os.path.basename(file_path)}...\n\n"

        while thread.is_alive():
            current_time = time.time()
            elapsed = current_time - start_time

            # Check log file for new content
            if os.path.exists(log_file):
                try:
                    current_size = os.path.getsize(log_file)
                    if current_size > last_read_pos:
                        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                            f.seek(last_read_pos)
                            new_content = f.read()
                            last_read_pos = f.tell()

                        # Send only new lines (no filtering for VS Code - full output)
                        if new_content.strip():
                            for line in new_content.splitlines():
                                if line.strip():
                                    escaped = line.replace('\\', '\\\\')
                                    yield f"data: {escaped}\n\n"
                except Exception as e:
                    logging.debug(f"Error reading log file: {e}")

            await asyncio.sleep(check_interval)

            # Check timeout
            if elapsed > timeout:
                yield f"data: ERROR: Execution timed out after {timeout}s\n\n"
                break

        # Get final result - check for any remaining content
        try:
            status, result, graphs = result_queue.get(timeout=5.0)

            # Read any remaining log file content not yet sent
            if os.path.exists(log_file):
                try:
                    current_size = os.path.getsize(log_file)
                    if current_size > last_read_pos:
                        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                            f.seek(last_read_pos)
                            remaining = f.read()
                        if remaining.strip():
                            for line in remaining.splitlines():
                                if line.strip():
                                    escaped = line.replace('\\', '\\\\')
                                    yield f"data: {escaped}\n\n"
                except Exception as e:
                    logging.debug(f"Error reading final log content: {e}")

            if status == 'error':
                yield f"data: ERROR: {result}\n\n"
            else:
                yield "data: *** Execution completed ***\n\n"

                # Output graph info in the expected format for VS Code extension's parseGraphsFromOutput
                if graphs:
                    yield f"data: \n\n"
                    yield f"data: {'='*60}\n\n"
                    yield f"data: GRAPHS DETECTED: {len(graphs)} graph(s) created\n\n"
                    yield f"data: {'='*60}\n\n"
                    for graph in graphs:
                        yield f"data:   • {graph['name']}: {graph['path']}\n\n"
                    logging.info(f"[STREAM] Sent {len(graphs)} graph(s) info to client")

        except queue_module.Empty:
            yield "data: ERROR: Failed to get execution result (timeout)\n\n"

    except (GeneratorExit, asyncio.CancelledError):
        # Client disconnected - exit cleanly without trying to yield more data
        logging.debug("[STREAM] Client disconnected, stopping stream")
        return

@app.get(
    "/run_file",
    operation_id="stata_run_file",
    response_class=Response,
    tags=["Execution"],
    summary="Run Stata .do file",
    description="Execute a Stata .do file and return the output. Supports timeout and multi-session mode.",
)
async def stata_run_file_endpoint(
    file_path: str,
    timeout: int = 600,
    session_id: str = None,
    working_dir: str = None
) -> Response:
    """Run a Stata .do file and return the output (MCP endpoint - applies compact mode filtering)

    Args:
        file_path: Path to the .do file
        timeout: Timeout in seconds (default: 600 seconds / 10 minutes)
        session_id: Optional session ID for multi-session mode (uses default session if not specified)
        working_dir: Optional working directory to change to before execution

    Returns:
        Response with plain text output (filtered in compact mode)
    """
    global multi_session_enabled, session_manager

    # Ensure timeout is a valid integer
    try:
        timeout = int(timeout)
        if timeout <= 0:
            logging.warning(f"Invalid timeout value: {timeout}, using default 600")
            timeout = 600
    except (ValueError, TypeError):
        logging.warning(f"Non-integer timeout value: {timeout}, using default 600")
        timeout = 600

    logging.info(f"Running file: {file_path} with timeout {timeout} seconds ({timeout/60:.1f} minutes)")
    if session_id:
        logging.info(f"Using session: {session_id}")
    if working_dir:
        logging.info(f"Working directory: {working_dir}")

    # Pre-process the file to auto-name graphs and handle line continuations
    processed_file = preprocess_do_file_for_graphs(file_path)
    logging.debug(f"Pre-processed file: {processed_file}")

    # Route through session manager if multi-session is enabled
    if multi_session_enabled and session_manager is not None:
        # Determine log file path based on user settings
        # Include session_id in log filename to prevent file locking conflicts in parallel execution
        abs_file_path = os.path.abspath(file_path)
        base_name = os.path.splitext(os.path.basename(abs_file_path))[0]
        log_file = get_log_file_path(file_path, base_name, session_id)

        # Get the original file's directory for working_dir (not the temp file's directory)
        original_file_dir = os.path.dirname(abs_file_path)

        # Run blocking session_manager.execute_file in thread pool to allow concurrent requests
        result_dict = await asyncio.to_thread(
            session_manager.execute_file,
            processed_file,
            session_id=session_id,
            timeout=float(timeout),
            log_file=log_file,  # Pass log file path to respect logFileLocation setting
            working_dir=original_file_dir  # Use original file's directory for outputs
        )
        if result_dict.get('status') == 'success':
            result = result_dict.get('output', '')
        else:
            result = f"Error: {result_dict.get('error', 'Unknown error')}"
    else:
        result = await asyncio.to_thread(run_stata_file, processed_file, timeout=timeout, working_dir=working_dir)

    # Format output for better display - replace escaped newlines with actual newlines
    formatted_result = result.replace("\\n", "\n")

    # Apply MCP output processing (compact mode filtering and token limit)
    # filter_command_echo=True for run_file (LLM already knows the file contents)
    formatted_result = process_mcp_output(formatted_result, for_mcp=True, filter_command_echo=True)

    # Log the output (truncated) for debugging
    logging.debug(f"Run file output (first 100 chars): {formatted_result[:100]}...")

    return Response(content=formatted_result, media_type="text/plain")

@app.get(
    "/run_file/stream",
    tags=["Execution"],
    summary="Run Stata .do file with streaming output",
    description="Execute a Stata .do file and stream output via Server-Sent Events (SSE) for real-time updates.",
    include_in_schema=False,  # Hide from MCP tools - this is for HTTP streaming only
)
async def stata_run_file_stream_endpoint(
    file_path: str,
    timeout: int = 600,
    working_dir: str = None,
    session_id: str = None
):
    """Run a Stata .do file and stream the output via Server-Sent Events (SSE)

    This is a separate endpoint for HTTP clients that want real-time streaming updates.
    For MCP clients, use the regular /run_file endpoint.

    Args:
        file_path: Path to the .do file
        timeout: Timeout in seconds (default: 600 seconds / 10 minutes)
        working_dir: Optional working directory for execution
        session_id: Optional session ID for multi-session mode

    Returns:
        StreamingResponse with text/event-stream content type
    """
    # Ensure timeout is a valid integer
    try:
        timeout = int(timeout)
        if timeout <= 0:
            logging.warning(f"Invalid timeout value: {timeout}, using default 600")
            timeout = 600
    except (ValueError, TypeError):
        logging.warning(f"Non-integer timeout value: {timeout}, using default 600")
        timeout = 600

    logging.info(f"[STREAM] Running file: {file_path} with timeout {timeout} seconds ({timeout/60:.1f} minutes)")
    if working_dir:
        logging.info(f"[STREAM] Working directory: {working_dir}")
    if session_id:
        logging.info(f"[STREAM] Using session: {session_id}")

    return StreamingResponse(
        stata_run_file_stream(file_path, timeout, working_dir, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


async def stata_run_selection_stream(selection: str, timeout: int = 600, working_dir: str = None, session_id: str = None):
    """Async generator that runs Stata selection code and yields SSE progress events

    Streams output incrementally by creating a temp file and monitoring the log file during execution.
    Works with both single-session and multi-session modes.

    Structured to match run_file_stream approach - no try-finally wrapper to avoid
    h11 protocol errors on client disconnect.

    Args:
        selection: The Stata code to run
        timeout: Timeout in seconds
        working_dir: Optional working directory for execution
        session_id: Optional session ID for multi-session mode

    Yields:
        SSE formatted events with incremental output
    """
    import threading
    import queue as queue_module
    import tempfile

    # Preprocess: Join lines with /// continuation into single logical lines
    processed_selection = join_stata_line_continuations(selection)

    # Markers to identify user code output boundaries
    START_MARKER = "__STATA_MCP_OUTPUT_START__"
    END_MARKER = "__STATA_MCP_OUTPUT_END__"

    # Create temp file BEFORE the generator logic (not in try-finally)
    # This matches run_file_stream approach
    fd, temp_file = tempfile.mkstemp(suffix='.do', prefix='stata_selection_')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        # If working directory specified, prepend cd command
        if working_dir and os.path.isdir(working_dir):
            working_dir_stata = os.path.normpath(working_dir).replace('\\', '/')
            f.write(f'cd "{working_dir_stata}"\n')
        # Add start marker before user code
        f.write(f'display "{START_MARKER}"\n')
        f.write(processed_selection)
        # Add end marker after user code
        f.write(f'\ndisplay "{END_MARKER}"\n')

    logging.info(f"[STREAM-SEL] Created temp file: {temp_file}")

    # Queue to communicate between threads
    result_queue = queue_module.Queue()

    # Determine log file path
    base_name = os.path.splitext(os.path.basename(temp_file))[0]
    log_file = get_log_file_path(temp_file, base_name, session_id)

    logging.info(f"[STREAM-SEL] Monitoring log file: {log_file}")

    # Clear (truncate) the log file before starting new execution
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'w') as f:
            pass
        logging.debug(f"[STREAM-SEL] Cleared log file: {log_file}")
    except Exception as e:
        logging.warning(f"[STREAM-SEL] Could not clear log file: {e}")

    # Pre-process the temp file to auto-name graphs
    processed_file = preprocess_do_file_for_graphs(temp_file)
    logging.debug(f"[STREAM-SEL] Pre-processed file: {processed_file}")

    def run_with_progress():
        """Run Stata selection in thread and cleanup temp file when done"""
        try:
            graphs = []
            if multi_session_enabled and session_manager is not None:
                logging.info(f"[STREAM-SEL] Using multi-session mode, session_id={session_id or 'default'}")
                result_dict = session_manager.execute_file(
                    processed_file,
                    session_id=session_id,
                    timeout=float(timeout),
                    log_file=log_file,
                    working_dir=working_dir
                )
                if result_dict.get('status') == 'success':
                    result = result_dict.get('output', '')
                    extra = result_dict.get('extra', {})
                    graphs = extra.get('graphs', []) if extra else []
                else:
                    result = f"Error: {result_dict.get('error', 'Unknown error')}"
            else:
                logging.info("[STREAM-SEL] Using single-session mode")
                result = run_stata_file(processed_file, timeout=timeout, working_dir=working_dir, auto_name_graphs=True)
                try:
                    logging.debug("[STREAM-SEL] Detecting graphs for single-session mode...")
                    graphs = display_graphs_interactive(graph_format='png', width=800, height=600)
                    if graphs:
                        logging.info(f"[STREAM-SEL] Detected {len(graphs)} graph(s)")
                except Exception as e:
                    logging.warning(f"[STREAM-SEL] Error detecting graphs: {str(e)}")
            result_queue.put(('success', result, graphs))
        except Exception as e:
            logging.error(f"[STREAM-SEL] Execution error: {str(e)}")
            result_queue.put(('error', str(e), []))
        finally:
            # Clean up temp files in the worker thread (not in generator)
            # This avoids the try-finally in generator that causes h11 issues
            # Clean up processed_file first (created by preprocess_do_file_for_graphs)
            if processed_file and processed_file != temp_file and os.path.exists(processed_file):
                try:
                    os.unlink(processed_file)
                    logging.debug(f"[STREAM-SEL] Cleaned up processed file: {processed_file}")
                except Exception as e:
                    logging.warning(f"[STREAM-SEL] Could not delete processed file: {e}")
            # Clean up original temp file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                    logging.debug(f"[STREAM-SEL] Cleaned up temp file: {temp_file}")
                except Exception as e:
                    logging.warning(f"[STREAM-SEL] Could not delete temp file: {e}")

    # Start execution thread
    thread = threading.Thread(target=run_with_progress, daemon=True)
    thread.start()

    # State-based filtering: only output lines between START and END markers
    in_user_output = False

    def process_line(line: str) -> tuple:
        """Process a line and return (should_output, new_state).

        Returns:
            (output_line, new_in_user_output_state)
            output_line is None if line should be skipped
        """
        nonlocal in_user_output
        stripped = line.strip()

        # Check for start marker - transition to user output mode
        if START_MARKER in stripped:
            in_user_output = True
            return (None, True)  # Skip the marker line itself

        # Check for end marker - transition out of user output mode
        if END_MARKER in stripped:
            in_user_output = False
            return (None, False)  # Skip the marker line itself

        # Only output if we're in user output mode
        if in_user_output and stripped:
            return (line, True)

        return (None, in_user_output)

    start_time = time.time()
    last_read_pos = 0
    check_interval = 0.5

    # Monitor progress by reading log file incrementally
    # Same structure as run_file_stream - wrap in try-except for client disconnect
    # All yields are inside try-except to handle client disconnect at any point
    try:
        # Yield initial separator for new execution
        yield f"data: \n\n"

        while thread.is_alive():
            current_time = time.time()
            elapsed = current_time - start_time

            if os.path.exists(log_file):
                try:
                    current_size = os.path.getsize(log_file)
                    if current_size > last_read_pos:
                        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                            f.seek(last_read_pos)
                            new_content = f.read()
                            last_read_pos = f.tell()

                        if new_content.strip():
                            for line in new_content.splitlines():
                                output_line, _ = process_line(line)
                                if output_line:
                                    escaped = output_line.replace('\\', '\\\\')
                                    yield f"data: {escaped}\n\n"
                except Exception as e:
                    logging.debug(f"Error reading log file: {e}")

            await asyncio.sleep(check_interval)

            if elapsed > timeout:
                yield f"data: ERROR: Execution timed out after {timeout}s\n\n"
                break

        # Get final result
        try:
            status, result, graphs = result_queue.get(timeout=5.0)

            # Read any remaining log file content
            if os.path.exists(log_file):
                try:
                    current_size = os.path.getsize(log_file)
                    if current_size > last_read_pos:
                        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                            f.seek(last_read_pos)
                            remaining = f.read()
                        if remaining.strip():
                            for line in remaining.splitlines():
                                output_line, _ = process_line(line)
                                if output_line:
                                    escaped = output_line.replace('\\', '\\\\')
                                    yield f"data: {escaped}\n\n"
                except Exception as e:
                    logging.debug(f"Error reading final log content: {e}")

            if status == 'error':
                yield f"data: ERROR: {result}\n\n"
            else:
                yield "data: *** Execution completed ***\n\n"

                # Output graph info for VS Code extension's parseGraphsFromOutput
                if graphs:
                    yield f"data: \n\n"
                    yield f"data: {'='*60}\n\n"
                    yield f"data: GRAPHS DETECTED: {len(graphs)} graph(s) created\n\n"
                    yield f"data: {'='*60}\n\n"
                    for graph in graphs:
                        yield f"data:   • {graph['name']}: {graph['path']}\n\n"
                    logging.info(f"[STREAM-SEL] Sent {len(graphs)} graph(s) info to client")

        except queue_module.Empty:
            yield "data: ERROR: Failed to get execution result (timeout)\n\n"

    except (GeneratorExit, asyncio.CancelledError):
        # Client disconnected - exit cleanly without trying to yield more data
        # Temp file cleanup is handled by the worker thread
        logging.debug("[STREAM-SEL] Client disconnected, stopping stream")
        return


@app.get(
    "/run_selection/stream",
    tags=["Execution"],
    summary="Run Stata selection with streaming output",
    description="Execute Stata code selection and stream output via Server-Sent Events (SSE) for real-time updates.",
    include_in_schema=False,  # Hide from MCP tools - this is for HTTP streaming only
)
async def stata_run_selection_stream_endpoint(
    selection: str,
    timeout: int = 600,
    working_dir: str = None,
    session_id: str = None
):
    """Run Stata code selection and stream the output via Server-Sent Events (SSE)

    This endpoint provides real-time streaming updates for code selection execution.

    Args:
        selection: The Stata code to run
        timeout: Timeout in seconds (default: 600 seconds / 10 minutes)
        working_dir: Optional working directory for execution
        session_id: Optional session ID for multi-session mode

    Returns:
        StreamingResponse with text/event-stream content type
    """
    try:
        timeout = int(timeout)
        if timeout <= 0:
            logging.warning(f"Invalid timeout value: {timeout}, using default 600")
            timeout = 600
    except (ValueError, TypeError):
        logging.warning(f"Non-integer timeout value: {timeout}, using default 600")
        timeout = 600

    logging.info(f"[STREAM-SEL] Running selection with timeout {timeout} seconds")
    if working_dir:
        logging.info(f"[STREAM-SEL] Working directory: {working_dir}")
    if session_id:
        logging.info(f"[STREAM-SEL] Using session: {session_id}")

    return StreamingResponse(
        stata_run_selection_stream(selection, timeout, working_dir, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# MCP server will be initialized in main() after args are parsed

# Add FastAPI endpoint for legacy VS Code extension
@app.post("/v1/tools", include_in_schema=False)
async def call_tool(request: ToolRequest) -> ToolResponse:
    try:
        # Map VS Code extension tool names to MCP tool names
        tool_name_map = {
            "run_selection": "stata_run_selection",
            "run_file": "stata_run_file",
            "session": "stata_session"
        }

        # Get the actual tool name
        mcp_tool_name = tool_name_map.get(request.tool, request.tool)

        # Log the request
        logging.info(f"REST API request for tool: {request.tool} -> {mcp_tool_name}")

        # List of valid tools
        valid_tools = ["stata_run_selection", "stata_run_file", "stata_session"]

        # Check if the tool exists
        if mcp_tool_name not in valid_tools:
            return ToolResponse(
                status="error",
                message=f"Unknown tool: {request.tool}"
            )
        
        # Execute the appropriate function
        if mcp_tool_name == "stata_run_selection":
            if "selection" not in request.parameters:
                return ToolResponse(
                    status="error",
                    message="Missing required parameter: selection"
                )
            # Get optional parameters
            working_dir = request.parameters.get("working_dir", None)
            session_id = request.parameters.get("session_id", None)

            # Route through session manager if multi-session is enabled
            if multi_session_enabled and session_manager is not None:
                if session_id:
                    logging.info(f"MCP run_selection using session: {session_id}")
                result_dict = await asyncio.to_thread(
                    session_manager.execute,
                    request.parameters["selection"],
                    session_id=session_id
                )
                if result_dict.get('status') == 'success':
                    result = result_dict.get('output', '')
                    # Append graph info if any graphs were created
                    # (matching run_file behavior - no keyword check needed since worker already detected them)
                    extra = result_dict.get('extra', {})
                    graphs = extra.get('graphs', []) if extra else []
                    if graphs:
                        graph_info = "\n\n" + "="*60 + "\n"
                        graph_info += f"GRAPHS DETECTED: {len(graphs)} graph(s) created\n"
                        graph_info += "="*60 + "\n"
                        for graph in graphs:
                            graph_info += f"  • {graph['name']}: {graph['path']}\n"
                        result += graph_info
                        logging.info(f"Multi-session: Added {len(graphs)} graphs to output")
                else:
                    result = f"Error: {result_dict.get('error', 'Unknown error')}"
            else:
                # Single-session mode: use direct execution
                # Enable auto_detect_graphs for VS Code extension calls
                result = await asyncio.to_thread(run_stata_selection, request.parameters["selection"], working_dir, True)
            # Format output for better display
            result = result.replace("\\n", "\n")
            
        elif mcp_tool_name == "stata_run_file":
            if "file_path" not in request.parameters:
                return ToolResponse(
                    status="error",
                    message="Missing required parameter: file_path"
                )

            # Get the file path from the parameters
            file_path = request.parameters["file_path"]

            # Get timeout parameter if provided, otherwise use default (10 minutes)
            timeout = request.parameters.get("timeout", 600)
            try:
                timeout = int(timeout)  # Ensure it's an integer
                if timeout <= 0:
                    logging.warning(f"Invalid timeout value: {timeout}, using default 600")
                    timeout = 600
            except (ValueError, TypeError):
                logging.warning(f"Non-integer timeout value: {timeout}, using default 600")
                timeout = 600

            # Get optional parameters
            working_dir = request.parameters.get("working_dir", None)
            session_id = request.parameters.get("session_id", None)

            logging.info(f"MCP run_file request for: {file_path} with timeout {timeout} seconds ({timeout/60:.1f} minutes)")
            if working_dir:
                logging.info(f"Working directory: {working_dir}")
            if session_id:
                logging.info(f"Using session: {session_id}")

            # Normalize the path for cross-platform compatibility
            file_path = os.path.normpath(file_path)

            # On Windows, convert forward slashes to backslashes if needed
            if platform.system() == "Windows" and '/' in file_path:
                file_path = file_path.replace('/', '\\')

            # Route through session manager if multi-session is enabled
            if multi_session_enabled and session_manager is not None:
                # Pre-process the file to auto-name graphs and handle line continuations
                processed_file = preprocess_do_file_for_graphs(file_path)
                logging.debug(f"Pre-processed file: {processed_file}")

                # Get the original file's directory for working_dir (not the temp file's directory)
                # This ensures outputs go to the expected location like native Stata
                abs_file_path = os.path.abspath(file_path)
                original_file_dir = os.path.dirname(abs_file_path)

                # Determine log file path based on user settings
                # Include session_id in log filename to prevent file locking conflicts in parallel execution
                base_name = os.path.splitext(os.path.basename(abs_file_path))[0]
                log_file = get_log_file_path(file_path, base_name, session_id)

                result_dict = await asyncio.to_thread(
                    session_manager.execute_file,
                    processed_file,
                    session_id=session_id,
                    timeout=float(timeout),
                    log_file=log_file,  # Pass log file path to respect logFileLocation setting
                    working_dir=original_file_dir
                )
                if result_dict.get('status') == 'success':
                    result = result_dict.get('output', '')
                    # Append graph info if any graphs were created (format must match extension's parseGraphsFromOutput)
                    extra = result_dict.get('extra', {})
                    graphs = extra.get('graphs', []) if extra else []
                    if graphs:
                        graph_info = "\n\n" + "="*60 + "\n"
                        graph_info += f"GRAPHS DETECTED: {len(graphs)} graph(s) created\n"
                        graph_info += "="*60 + "\n"
                        for graph in graphs:
                            graph_info += f"  • {graph['name']}: {graph['path']}\n"
                        result += graph_info
                        logging.info(f"Multi-session run_file: Added {len(graphs)} graphs to output")
                else:
                    result = f"Error: {result_dict.get('error', 'Unknown error')}"
            else:
                # Single-session mode: use direct execution
                # Enable auto_name_graphs for VS Code extension calls
                result = await asyncio.to_thread(run_stata_file, file_path, timeout, True, working_dir)

            # Format output for better display
            result = result.replace("\\n", "\n")

            # Log the output length for debugging
            logging.debug(f"MCP run_file output length: {len(result)}")

            # If no output was captured, log a warning
            if "Command executed but" in result and "output not captured" in result:
                logging.warning(f"No output captured for file: {file_path}")

            # If file not found error, make the message more helpful
            if "File not found" in result:
                # Add help text explaining common issues with Windows paths
                result += get_windows_path_help_message()

        # Session management tool - unified with action parameter
        elif mcp_tool_name == "stata_session":
            action = request.parameters.get("action", "list")
            session_id = request.parameters.get("session_id", None)

            # Action: list - List all active sessions
            if action == "list":
                if multi_session_enabled and session_manager is not None:
                    sessions = session_manager.list_sessions()
                    stats = session_manager.get_stats()
                    result_data = {
                        "sessions": sessions,
                        "max_sessions": stats.get("max_sessions", 0),
                        "available_slots": stats.get("available_slots", 0),
                        "multi_session_enabled": True
                    }
                else:
                    result_data = {
                        "sessions": [],
                        "multi_session_enabled": False,
                        "message": "Multi-session mode is not enabled"
                    }
                return ToolResponse(
                    status="success",
                    result=json.dumps(result_data, indent=2)
                )

            # Action: destroy - Destroy a session
            elif action == "destroy":
                if not multi_session_enabled or session_manager is None:
                    return ToolResponse(
                        status="error",
                        message="Multi-session mode is not enabled"
                    )

                if not session_id:
                    return ToolResponse(
                        status="error",
                        message="Missing required parameter: session_id (required for destroy action)"
                    )

                logging.info(f"Destroying session: {session_id}")
                success, error = session_manager.destroy_session(session_id)

                if success:
                    return ToolResponse(
                        status="success",
                        result=json.dumps({
                            "action": "destroy",
                            "session_id": session_id,
                            "message": f"Session '{session_id}' destroyed successfully"
                        }, indent=2)
                    )
                else:
                    return ToolResponse(
                        status="error",
                        message=error or f"Failed to destroy session '{session_id}'"
                    )

            else:
                return ToolResponse(
                    status="error",
                    message=f"Unknown action: {action}. Valid actions: list, destroy"
                )

        # Apply output filtering for MCP returns (skip if interactive mode)
        # Interactive mode sets skip_filter=true to get full unfiltered output
        skip_filter = request.parameters.get("skip_filter", False)
        if not skip_filter:
            # For run_file: filter_command_echo=True because VS Code already knows the file contents
            # For run_selection: filter_command_echo=False to preserve command context
            if mcp_tool_name == "stata_run_file":
                result = process_mcp_output(result, log_path=None, for_mcp=True, filter_command_echo=True)
            elif mcp_tool_name == "stata_run_selection":
                result = process_mcp_output(result, log_path=None, for_mcp=True, filter_command_echo=False)

        # Return successful response
        return ToolResponse(
            status="success",
            result=result
        )
        
    except Exception as e:
        logging.error(f"Error handling tool request: {str(e)}")
        return ToolResponse(
            status="error",
            message=f"Server error: {str(e)}"
        )

# Simplified health check endpoint - only report server status without executing Stata commands
@app.get("/health", include_in_schema=False)
async def health_check():
    return {
        "status": "ok",
        "service": SERVER_NAME,
        "version": SERVER_VERSION,
        "stata_available": stata_available
    }

# Endpoint to stop a running execution
# Hidden from OpenAPI schema so it won't be exposed to LLMs via MCP
@app.post("/stop_execution", include_in_schema=False)
async def stop_execution(session_id: str = None):
    """Stop the currently running Stata execution.

    Works with both single-session and multi-session modes.
    In multi-session mode, sends stop signal to the worker process.

    Args:
        session_id: Optional session ID for multi-session mode
    """
    global current_execution_id, multi_session_enabled, session_manager

    stop_sent = False
    method_used = None

    # Try multi-session mode if enabled
    if multi_session_enabled and session_manager is not None:
        logging.info(f"[STOP] Using multi-session mode, session_id={session_id or 'default'}")
        try:
            # Use shorter timeout and don't block on result
            result = await asyncio.wait_for(
                asyncio.to_thread(session_manager.stop_execution, session_id),
                timeout=2.0
            )
            logging.info(f"[STOP] Session manager result: {result}")
            if result.get('status') in ('stopped', 'stop_sent'):
                stop_sent = True
                method_used = "session_manager"
            elif result.get('status') == 'not_running':
                logging.info("[STOP] Session not busy, but will try StataSO_SetBreak anyway")
        except asyncio.TimeoutError:
            logging.info("[STOP] Session manager stop timed out, continuing...")
        except Exception as e:
            logging.debug(f"[STOP] Session manager stop failed: {str(e)}")

    # Only try StataSO_SetBreak if NOT using multi-session mode
    # In multi-session mode, we already sent stop via session_manager above
    # Calling SetBreak in BOTH places causes double break messages
    if not multi_session_enabled:
        try:
            from pystata.config import stlib
            if stlib is not None:
                logging.info("[STOP] Trying StataSO_SetBreak() (single-session mode)")
                stlib.StataSO_SetBreak()  # Call only ONCE to avoid crashes
                stop_sent = True
                method_used = method_used or "stata_setbreak"
                logging.info("[STOP] StataSO_SetBreak() called successfully")
        except ImportError:
            logging.debug("[STOP] pystata not available in main process")
        except Exception as e:
            logging.debug(f"[STOP] StataSO_SetBreak() failed: {str(e)}")

    # Mark any tracked execution as cancelled
    exec_id = None
    with execution_lock:
        if current_execution_id is not None:
            exec_id = current_execution_id
            if exec_id in execution_registry:
                execution_registry[exec_id]['cancelled'] = True
                logging.info(f"[STOP] Marked execution {exec_id} as cancelled")

    if stop_sent:
        return {
            "status": "stop_requested",
            "execution_id": exec_id,
            "method": method_used,
            "message": "Stop signal sent"
        }
    else:
        return {
            "status": "stop_requested",
            "execution_id": exec_id,
            "method": "signal",
            "message": "Stop signal sent (multi-session mode)"
        }

@app.post("/reload_workers", include_in_schema=False)
async def reload_workers():
    """Reload worker processes without restarting the server.

    This allows updating worker code (stata_worker.py) without killing
    the MCP connection. The main server stays running.
    """
    global session_manager, multi_session_enabled

    if not multi_session_enabled or session_manager is None:
        return {
            "status": "skipped",
            "message": "Multi-session mode not enabled, no workers to reload"
        }

    try:
        # Get current session count
        old_sessions = session_manager.list_sessions()

        # Shutdown all existing workers
        logging.info("[RELOAD] Shutting down existing workers...")
        session_manager.stop()

        # Wait for workers to stop
        await asyncio.sleep(2)

        # Reload the worker module
        import importlib
        import stata_worker
        importlib.reload(stata_worker)
        logging.info("[RELOAD] Worker module reloaded")

        # Create new session manager with fresh workers
        from session_manager import SessionManager
        importlib.reload(__import__('session_manager'))
        from session_manager import SessionManager as ReloadedSessionManager

        # Determine graphs directory
        if extension_path:
            reload_graphs_dir = os.path.join(extension_path, 'graphs')
        else:
            reload_graphs_dir = os.path.join(tempfile.gettempdir(), 'stata_mcp_graphs')

        session_manager = ReloadedSessionManager(
            stata_path=session_manager.stata_path if hasattr(session_manager, 'stata_path') else os.environ.get('SYSDIR_STATA', '/Applications/Stata'),
            stata_edition=session_manager.stata_edition if hasattr(session_manager, 'stata_edition') else 'mp',
            max_sessions=100,
            graphs_dir=reload_graphs_dir
        )

        logging.info("[RELOAD] New session manager created")

        return {
            "status": "success",
            "message": f"Workers reloaded. Previous sessions: {len(old_sessions)}, new default session ready.",
            "old_sessions": len(old_sessions)
        }

    except Exception as e:
        logging.error(f"[RELOAD] Error reloading workers: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/execution_status", include_in_schema=False)
async def get_execution_status():
    """Get the current execution status"""
    global current_execution_id

    with execution_lock:
        if current_execution_id is None:
            return {"status": "idle", "executing": False}

        if current_execution_id in execution_registry:
            execution = execution_registry[current_execution_id]
            elapsed = time.time() - execution.get('start_time', time.time())
            return {
                "status": "running",
                "executing": True,
                "execution_id": current_execution_id,
                "file": execution.get('file', 'unknown'),
                "elapsed_seconds": round(elapsed, 1),
                "cancelled": execution.get('cancelled', False)
            }

        return {"status": "idle", "executing": False}

# ============================================================================
# Multi-Session Management Endpoints
# ============================================================================

@app.post("/sessions", include_in_schema=False)
async def create_session():
    """Create a new Stata session for parallel execution"""
    global session_manager, multi_session_enabled

    if not multi_session_enabled:
        return {
            "status": "error",
            "message": "Multi-session mode is not enabled. Start server with --multi-session flag."
        }

    if session_manager is None:
        return {
            "status": "error",
            "message": "Session manager not initialized"
        }

    try:
        result = session_manager.create_session()
        if result["success"]:
            return {
                "status": "success",
                "session_id": result["session_id"],
                "message": "Session created successfully"
            }
        else:
            return {
                "status": "error",
                "message": result.get("error", "Unknown error")
            }
    except Exception as e:
        logging.error(f"Error creating session: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/sessions", include_in_schema=False)
async def list_sessions():
    """List all active Stata sessions"""
    global session_manager, multi_session_enabled

    if not multi_session_enabled:
        return {
            "sessions": [],
            "multi_session_enabled": False,
            "message": "Multi-session mode is not enabled"
        }

    if session_manager is None:
        return {
            "sessions": [],
            "multi_session_enabled": True,
            "message": "Session manager not initialized"
        }

    try:
        sessions = session_manager.list_sessions()
        stats = session_manager.get_stats()
        return {
            "sessions": sessions,
            "max_sessions": stats.get("max_sessions", 4),
            "available_slots": stats.get("available_slots", 0),
            "multi_session_enabled": True
        }
    except Exception as e:
        logging.error(f"Error listing sessions: {str(e)}")
        return {
            "sessions": [],
            "error": str(e)
        }


@app.get("/sessions/{session_id}", include_in_schema=False)
async def get_session_details(session_id: str):
    """Get details about a specific session"""
    global session_manager, multi_session_enabled

    if not multi_session_enabled or session_manager is None:
        return {
            "status": "error",
            "message": "Multi-session mode is not enabled or not initialized"
        }

    try:
        session = session_manager.get_session(session_id)
        if session:
            return {
                "status": "success",
                "session": session.to_dict()
            }
        else:
            return {
                "status": "error",
                "message": f"Session not found: {session_id}"
            }
    except Exception as e:
        logging.error(f"Error getting session {session_id}: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.delete("/sessions/{session_id}", include_in_schema=False)
async def destroy_session(session_id: str):
    """Destroy a Stata session"""
    global session_manager, multi_session_enabled

    if not multi_session_enabled or session_manager is None:
        return {
            "status": "error",
            "message": "Multi-session mode is not enabled or not initialized"
        }

    try:
        success, error = session_manager.destroy_session(session_id)
        if success:
            return {
                "status": "success",
                "message": f"Session {session_id} destroyed"
            }
        else:
            return {
                "status": "error",
                "message": error
            }
    except Exception as e:
        logging.error(f"Error destroying session {session_id}: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/sessions/{session_id}/stop", include_in_schema=False)
async def stop_session_execution(session_id: str):
    """Stop execution in a specific session"""
    global session_manager, multi_session_enabled

    if not multi_session_enabled or session_manager is None:
        return {
            "status": "error",
            "message": "Multi-session mode is not enabled or not initialized"
        }

    try:
        result = session_manager.stop_execution(session_id)
        return result
    except Exception as e:
        logging.error(f"Error stopping execution in session {session_id}: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


_single_session_restart_lock = threading.Lock()

def _single_session_restart():
    """Run single-session restart commands in a thread to avoid blocking the event loop."""
    stata.run("capture log close _all", inline=False, echo=False)
    stata.run("capture clear all", inline=False, echo=False)
    stata.run("capture graph drop _all", inline=False, echo=False)
    # clear all resets Stata defaults including `set more on`,
    # which would deadlock the session on long output
    stata.run("capture set more off", inline=False, echo=False)
    stata.run("set more off", inline=False, echo=False)

@app.post("/sessions/restart", include_in_schema=False)
async def restart_session():
    """Restart the default Stata session to get a clean state.

    In multi-session mode: destroys and recreates the default worker process.
    In single-session mode: runs cleanup commands to reset Stata state.
    """
    global session_manager, multi_session_enabled, stata_available

    if multi_session_enabled and session_manager is not None:
        try:
            result = await asyncio.to_thread(session_manager.restart_default_session)
            if result.get("success"):
                return {"status": "success", "message": "Stata session restarted"}
            else:
                return {"status": "error", "message": result.get("error", "Unknown error")}
        except Exception as e:
            logging.error(f"Error restarting session: {str(e)}")
            return {"status": "error", "message": str(e)}
    else:
        # Single-session mode: run cleanup commands as soft reset
        if not stata_available or 'stata' not in globals():
            return {"status": "error", "message": "Stata is not available"}

        if not _single_session_restart_lock.acquire(blocking=False):
            return {"status": "error", "message": "Session is already being restarted"}

        try:
            await asyncio.to_thread(_single_session_restart)
            return {"status": "success", "message": "Stata session state cleared (single-session mode)"}
        except Exception as e:
            # If clear all ran but set more off failed, the session is in
            # `set more on` mode which deadlocks on long output. Try to recover.
            try:
                await asyncio.to_thread(
                    lambda: stata.run("capture set more off", inline=False, echo=False)
                )
            except Exception:
                pass
            logging.error(f"Error resetting Stata state: {str(e)}")
            return {"status": "error", "message": str(e)}
        finally:
            _single_session_restart_lock.release()


# Endpoint to serve graph images
# Hidden from OpenAPI schema so it won't be exposed to LLMs via MCP
@app.get("/graphs/{graph_name}", include_in_schema=False)
async def get_graph(graph_name: str):
    """Serve a graph image file"""
    try:
        # CRITICAL: Decode URL-encoded graph name (e.g., "Graph%201" -> "Graph 1")
        # The extension uses encodeURIComponent() which encodes spaces and special chars
        graph_name = unquote(graph_name)

        # Construct the path to the graph file
        if extension_path:
            graphs_dir = os.path.join(extension_path, 'graphs')
        else:
            graphs_dir = os.path.join(tempfile.gettempdir(), 'stata_mcp_graphs')

        # Support both with and without .png extension
        if not graph_name.endswith('.png'):
            graph_name = f"{graph_name}.png"

        graph_path = os.path.join(graphs_dir, graph_name)
        logging.debug(f"Looking for graph at: {graph_path}")

        # Check if file exists
        if not os.path.exists(graph_path):
            # Log available files for debugging
            if os.path.exists(graphs_dir):
                available = os.listdir(graphs_dir)
                logging.warning(f"Graph not found: {graph_name}. Available: {available}")
            else:
                logging.warning(f"Graphs directory does not exist: {graphs_dir}")
            return Response(
                content=f"Graph not found: {graph_name}",
                status_code=404,
                media_type="text/plain"
            )

        # Read and return the image file
        with open(graph_path, 'rb') as f:
            image_data = f.read()

        return Response(content=image_data, media_type="image/png")

    except Exception as e:
        logging.error(f"Error serving graph {graph_name}: {str(e)}")
        return Response(
            content=f"Error serving graph: {str(e)}",
            status_code=500
        )

@app.post("/clear_history", include_in_schema=False)
async def clear_history_endpoint():
    """Clear the command history"""
    global command_history
    try:
        count = len(command_history)
        command_history = []
        logging.info(f"Cleared command history ({count} items)")
        return {"status": "success", "message": f"Cleared {count} items from history"}
    except Exception as e:
        logging.error(f"Error clearing history: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/view_data", include_in_schema=False)
async def view_data_endpoint(if_condition: str = None, session_id: str = None, max_rows: int = 10000):
    """Get current Stata data as a pandas DataFrame and return as JSON

    Args:
        if_condition: Optional Stata if condition (e.g., "price > 5000 & mpg < 30")
        session_id: Optional session ID for multi-session mode
        max_rows: Maximum number of rows to return (default 10000). User can configure via extension settings.
    """
    global stata_available, stata, multi_session_enabled, session_manager

    # Ensure max_rows has minimum value (no hard upper limit - controlled by extension settings)
    max_rows = max(100, max_rows)

    try:
        # Route through session manager if multi-session mode is enabled
        if multi_session_enabled and session_manager is not None:
            result = await asyncio.to_thread(
                session_manager.get_data,
                session_id=session_id,
                if_condition=if_condition,
                max_rows=max_rows
            )

            if result.get('status') == 'error':
                return Response(
                    content=json.dumps({
                        "status": "error",
                        "message": result.get('error', 'Unknown error')
                    }),
                    media_type="application/json",
                    status_code=500
                )

            return Response(
                content=json.dumps({
                    "status": "success",
                    "data": result.get('data', []),
                    "columns": result.get('columns', []),
                    "dtypes": result.get('dtypes', {}),
                    "rows": result.get('rows', 0),
                    "index": result.get('index', []),
                    "total_rows": result.get('total_rows', result.get('rows', 0)),
                    "displayed_rows": result.get('displayed_rows', result.get('rows', 0)),
                    "max_rows": result.get('max_rows', max_rows)
                }),
                media_type="application/json"
            )

        # Single-session mode: use direct Stata access
        if not stata_available or stata is None:
            logging.error("Stata is not available")
            return Response(
                content=json.dumps({
                    "status": "error",
                    "message": "Stata is not initialized"
                }),
                media_type="application/json",
                status_code=500
            )

        # Use efficient Stata-native filtering with preserve/restore
        # This is MUCH faster than the old O(n) SFI approach
        import sfi

        total_obs = sfi.Data.getObsTotal()
        if total_obs == 0:
            logging.info("No data currently loaded in Stata")
            return Response(
                content=json.dumps({
                    "status": "success",
                    "message": "No data currently loaded",
                    "data": [],
                    "columns": [],
                    "rows": 0,
                    "total_rows": 0,
                    "displayed_rows": 0
                }),
                media_type="application/json"
            )

        logging.info(f"Total observations in Stata: {total_obs}")

        # Apply if condition using Stata's native filtering (much faster)
        if if_condition:
            logging.info(f"Applying filter: if {if_condition}")
            try:
                # Preserve current data state
                stata.run("preserve", inline=False, echo=False)

                try:
                    # Create temp variable to track original observation numbers (0-based for JS)
                    stata.run("quietly gen long _stata_mcp_orig_obs = _n - 1", inline=False, echo=False)

                    # Use Stata's native keep if - this is very fast even for millions of rows
                    keep_cmd = f"quietly keep if {if_condition}"
                    logging.debug(f"Running: {keep_cmd}")
                    stata.run(keep_cmd, inline=False, echo=False)

                    # Get count of matching rows
                    filtered_obs = sfi.Data.getObsTotal()
                    logging.info(f"Filter matched {filtered_obs} rows (out of {total_obs})")

                    # If more than max_rows, limit the data
                    if filtered_obs > max_rows:
                        stata.run(f"quietly keep in 1/{max_rows}", inline=False, echo=False)
                        logging.info(f"Limited to first {max_rows} rows")

                    # Get the filtered data
                    df = stata.pdataframe_from_data()

                    # Extract original obs numbers as index, then drop the temp column
                    orig_obs_index = df['_stata_mcp_orig_obs'].tolist()
                    df = df.drop(columns=['_stata_mcp_orig_obs'])

                    # Restore original data
                    stata.run("restore", inline=False, echo=False)

                    total_matching = filtered_obs
                    displayed_rows = min(filtered_obs, max_rows)

                except Exception as filter_err:
                    # Make sure to restore on error
                    try:
                        stata.run("restore", inline=False, echo=False)
                    except:
                        pass
                    raise filter_err

            except Exception as e:
                error_msg = str(e)
                # Check for common Stata error patterns
                if "invalid syntax" in error_msg.lower() or "unknown function" in error_msg.lower():
                    error_msg = f"Invalid condition syntax: {if_condition}"
                logging.error(f"Filter error: {error_msg}")
                return Response(
                    content=json.dumps({
                        "status": "error",
                        "message": f"Filter error: {error_msg}"
                    }),
                    media_type="application/json",
                    status_code=400
                )
            # For filtered case, orig_obs_index is already set above
        else:
            # No filter - just get data with row limit
            total_matching = total_obs
            displayed_rows = min(total_obs, max_rows)

            if total_obs > max_rows:
                # Use range() for obs parameter (0-based Python indexing)
                logging.info(f"Limiting to first {max_rows} rows (total: {total_obs})")
                df = stata.pdataframe_from_data(obs=range(max_rows))
            else:
                df = stata.pdataframe_from_data()

            # Sequential index for non-filtered case (0-based, JS adds 1)
            orig_obs_index = list(range(len(df))) if df is not None and not df.empty else []

        # Check if data is empty
        if df is None or df.empty:
            logging.info("No data returned from Stata")
            return Response(
                content=json.dumps({
                    "status": "success",
                    "message": "No data matches the condition" if if_condition else "No data loaded",
                    "data": [],
                    "columns": [],
                    "rows": 0,
                    "total_rows": total_matching,
                    "displayed_rows": 0
                }),
                media_type="application/json"
            )

        # Get data info
        rows, cols = df.shape
        logging.info(f"Data retrieved: {rows} observations, {cols} variables")

        # Convert DataFrame to JSON format
        # Replace NaN with None for proper JSON serialization
        df_clean = df.replace({float('nan'): None})

        # Convert to list of lists for better performance
        data_values = df_clean.values.tolist()
        column_names = df_clean.columns.tolist()

        # Get data types for each column
        dtypes = {col: str(df[col].dtype) for col in df.columns}

        return Response(
            content=json.dumps({
                "status": "success",
                "data": data_values,
                "columns": column_names,
                "dtypes": dtypes,
                "rows": int(rows),
                "total_rows": int(total_matching),
                "displayed_rows": int(displayed_rows),
                "max_rows": max_rows,
                "index": orig_obs_index  # Original observation numbers (0-based, JS adds 1)
            }),
            media_type="application/json"
        )

    except Exception as e:
        error_msg = f"Error getting data: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        return Response(
            content=json.dumps({
                "status": "error",
                "message": error_msg
            }),
            media_type="application/json",
            status_code=500
        )

@app.get("/interactive", include_in_schema=False)
async def interactive_window(file: str = None, code: str = None):
    """Serve the interactive Stata window as a full webpage"""
    # If a file path or code is provided, we'll auto-execute it on page load
    auto_run_file = file if file else ""
    auto_run_code = code if code else ""

    # Use regular string and insert the file path separately to avoid f-string conflicts
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stata Interactive Window</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1e1e1e;
            color: #d4d4d4;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .main-container {
            display: flex;
            flex: 1;
            overflow: hidden;
        }
        .left-panel {
            flex: 1;
            display: flex;
            flex-direction: column;
            border-right: 1px solid #3e3e42;
            overflow: hidden;
        }
        .output-section {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }
        .output-cell {
            border-left: 3px solid #007acc;
            padding-left: 15px;
            margin-bottom: 20px;
            background: #252526;
            padding: 15px;
            border-radius: 4px;
        }
        .command-line {
            color: #4fc1ff;
            font-weight: bold;
            margin-bottom: 10px;
            font-family: 'Consolas', 'Monaco', monospace;
        }
        .command-output {
            font-family: 'Consolas', 'Monaco', monospace;
            white-space: pre-wrap;
            font-size: 13px;
            line-height: 1.5;
        }
        .input-section {
            border-top: 1px solid #3e3e42;
            padding: 20px;
            background: #252526;
        }
        .input-container {
            display: flex;
            gap: 10px;
        }
        #command-input {
            flex: 1;
            background: #3c3c3c;
            border: 1px solid #6c6c6c;
            color: #d4d4d4;
            padding: 12px 15px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 14px;
            border-radius: 4px;
        }
        #command-input:focus {
            outline: none;
            border-color: #007acc;
        }
        #run-button {
            background: #0e639c;
            color: white;
            border: none;
            padding: 12px 30px;
            font-weight: 600;
            cursor: pointer;
            border-radius: 4px;
            transition: background 0.2s;
        }
        #run-button:hover {
            background: #1177bb;
        }
        #run-button:disabled {
            background: #555;
            cursor: not-allowed;
        }
        .right-panel {
            width: 40%;
            overflow-y: auto;
            padding: 20px;
            background: #1e1e1e;
        }
        .graphs-title {
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 20px;
            color: #ffffff;
        }
        .graph-card {
            background: #252526;
            border: 1px solid #3e3e42;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .graph-card h3 {
            margin-bottom: 15px;
            color: #ffffff;
        }
        .graph-card img {
            width: 100%;
            height: auto;
            border-radius: 4px;
        }
        .error {
            background: #5a1d1d;
            border-left: 3px solid #f48771;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .hint {
            color: #858585;
            font-size: 12px;
            margin-top: 8px;
        }
        .no-graphs {
            color: #858585;
            font-style: italic;
            text-align: center;
            padding: 40px;
        }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="left-panel">
            <div class="output-section" id="output-container"></div>

            <div class="input-section">
                <div class="input-container">
                    <input type="text" id="command-input"
                           placeholder="Enter Stata command (e.g., summarize, scatter y x, regress y x)..."
                           autocomplete="off" />
                    <button id="run-button">Run</button>
                </div>
                <div class="hint">Press Enter to execute • Ctrl+L to clear output</div>
            </div>
        </div>

        <div class="right-panel">
            <div class="graphs-title">Graphs</div>
            <div id="graphs-container">
                <div class="no-graphs">No graphs yet. Run commands to generate graphs.</div>
            </div>
        </div>
    </div>

    <script>
        const commandInput = document.getElementById('command-input');
        const runButton = document.getElementById('run-button');
        const outputContainer = document.getElementById('output-container');
        const graphsContainer = document.getElementById('graphs-container');

        runButton.addEventListener('click', executeCommand);
        commandInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') executeCommand();
        });

        document.addEventListener('keydown', async (e) => {
            if (e.ctrlKey && e.key === 'l') {
                e.preventDefault();
                // Clear text output visually
                outputContainer.innerHTML = '';
                // Clear graphs visually
                graphsContainer.innerHTML = '<div class="no-graphs">No graphs yet. Run commands to generate graphs.</div>';
                // Clear server-side command history so it doesn't come back
                try {
                    const response = await fetch('/clear_history', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    const data = await response.json();
                    console.log('History cleared:', data.message);
                } catch (err) {
                    console.error('Error clearing history:', err);
                }
            }
        });

        async function executeCommand() {
            const command = commandInput.value.trim();
            if (!command) return;

            runButton.disabled = true;
            runButton.textContent = 'Running...';

            try {
                const response = await fetch('/v1/tools', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool: 'run_selection',
                        parameters: { selection: command, skip_filter: true }
                    })
                });

                const data = await response.json();

                if (data.status === 'success') {
                    addOutputCell(command, data.result);
                    updateGraphs(data.result);
                } else {
                    addError(data.message || 'Command failed');
                }
            } catch (error) {
                addError(error.message);
            }

            runButton.disabled = false;
            runButton.textContent = 'Run';
            commandInput.value = '';
            commandInput.focus();
        }

        function addOutputCell(command, output) {
            const cell = document.createElement('div');
            cell.className = 'output-cell';
            cell.innerHTML = `
                <div class="command-line">> ${escapeHtml(command)}</div>
                <div class="command-output">${escapeHtml(output)}</div>
            `;
            outputContainer.appendChild(cell);
            outputContainer.scrollTop = outputContainer.scrollHeight;
        }

        function addError(message) {
            const error = document.createElement('div');
            error.className = 'error';
            error.textContent = 'Error: ' + message;
            outputContainer.appendChild(error);
            outputContainer.scrollTop = outputContainer.scrollHeight;
        }

        function updateGraphs(output) {
            // Updated regex to capture optional command: • name: path [CMD: command]
            // Use [^\\n\\[] to stop at newlines or opening bracket
            const graphRegex = /• ([^:]+): ([^\\n\\[]+)(?:\\[CMD: ([^\\]]+)\\])?/g;
            const matches = [...output.matchAll(graphRegex)];

            if (matches.length > 0) {
                // Remove "no graphs" message if it exists
                const noGraphsMsg = graphsContainer.querySelector('.no-graphs');
                if (noGraphsMsg) {
                    graphsContainer.innerHTML = '';
                }

                // Add or update each graph
                matches.forEach(match => {
                    const name = match[1].trim();
                    const path = match[2].trim();
                    const command = match[3] ? match[3].trim() : null;

                    // Check if graph already exists
                    const existingGraph = graphsContainer.querySelector(`[data-graph-name="${name}"]`);
                    if (existingGraph) {
                        // Update existing graph - force reload by adding timestamp
                        updateGraph(existingGraph, name, `/graphs/${encodeURIComponent(name)}`, command);
                    } else {
                        // Add new graph
                        addGraph(name, `/graphs/${encodeURIComponent(name)}`, command);
                    }
                });
            }
        }

        function updateGraph(existingCard, name, url, command) {
            // Force reload by adding timestamp to bypass cache
            const timestamp = new Date().getTime();
            const urlWithTimestamp = `${url}?t=${timestamp}`;

            const commandHtml = command ? `<div style="color: #858585; font-size: 12px; margin-bottom: 8px; font-family: 'Courier New', monospace; background: #1a1a1a; padding: 6px; border-radius: 3px; border-left: 3px solid #4a9eff;">$ ${escapeHtml(command)}</div>` : '';
            existingCard.innerHTML = `
                <h3>${escapeHtml(name)}</h3>
                ${commandHtml}
                <img src="${urlWithTimestamp}" alt="${escapeHtml(name)}"
                     onerror="this.parentElement.innerHTML='<p style=\\'color:#f48771\\'>Failed to load graph</p>'">
            `;
        }

        function addGraph(name, url, command) {
            const card = document.createElement('div');
            card.className = 'graph-card';
            card.setAttribute('data-graph-name', name);
            const commandHtml = command ? `<div style="color: #858585; font-size: 12px; margin-bottom: 8px; font-family: 'Courier New', monospace; background: #1a1a1a; padding: 6px; border-radius: 3px; border-left: 3px solid #4a9eff;">$ ${escapeHtml(command)}</div>` : '';
            card.innerHTML = `
                <h3>${escapeHtml(name)}</h3>
                ${commandHtml}
                <img src="${url}" alt="${escapeHtml(name)}"
                     onerror="this.parentElement.innerHTML='<p style=\\'color:#f48771\\'>Failed to load graph</p>'">
            `;
            graphsContainer.appendChild(card);
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Auto-execute file or code if provided in URL parameter
        const urlParams = new URLSearchParams(window.location.search);
        const autoRunFile = urlParams.get('file');
        const autoRunCode = urlParams.get('code');

        if (autoRunFile) {
            console.log('Auto-running file from URL parameter:', autoRunFile);
            // Run the file on page load
            fetch('/v1/tools', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool: 'run_file',
                    parameters: { file_path: autoRunFile, skip_filter: true }
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    addOutputCell('Running file: ' + autoRunFile, data.result);
                    updateGraphs(data.result);
                } else {
                    addError(data.message || 'Failed to run file');
                }
            })
            .catch(error => {
                addError('Error running file: ' + error.message);
            });
        } else if (autoRunCode) {
            console.log('Auto-running code from URL parameter');
            // Run the selected code on page load
            fetch('/v1/tools', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool: 'run_selection',
                    parameters: { selection: autoRunCode, skip_filter: true }
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    addOutputCell('Running selection', data.result);
                    updateGraphs(data.result);
                } else {
                    addError(data.message || 'Failed to run code');
                }
            })
            .catch(error => {
                addError('Error running code: ' + error.message);
            });
        }

        commandInput.focus();
    </script>
</body>
</html>
    """
    # Replace the placeholder with the actual file path (with proper escaping)
    if auto_run_file:
        # Escape the file path for JavaScript string
        escaped_file = auto_run_file.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        html_content = html_content.replace('AUTO_RUN_FILE_PLACEHOLDER', escaped_file)

    return Response(content=html_content, media_type="text/html")


def main():
    """Main function to set up and run the server"""
    try:
        # Get Stata path from arguments
        parser = argparse.ArgumentParser(description='Stata MCP Server')
        parser.add_argument('--stata-path', type=str, help='Path to Stata installation')
        parser.add_argument('--port', type=int, default=4000, help='Port to run MCP server on')
        parser.add_argument('--host', type=str, default='localhost', help='Host to bind the server to')
        parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
                          default='INFO', help='Logging level')
        parser.add_argument('--force-port', action='store_true', help='Force the specified port, even if it requires killing processes')
        parser.add_argument('--log-file', type=str, help='Path to log file (default: stata_mcp_server.log in current directory)')
        parser.add_argument('--stata-edition', type=str, choices=['mp', 'se', 'be'], default='mp', 
                          help='Stata edition to use (mp, se, be) - default: mp')
        parser.add_argument('--log-file-location', type=str, choices=['dofile', 'parent', 'workspace', 'extension', 'custom'], default='extension',
                          help='Location for .do file logs (dofile, parent, workspace, extension, custom) - default: extension')
        parser.add_argument('--custom-log-directory', type=str, default='',
                          help='Custom directory for .do file logs (when location is custom)')
        parser.add_argument('--workspace-root', type=str, default='',
                          help='VS Code workspace root directory (for workspace log file location)')
        parser.add_argument('--result-display-mode', type=str, choices=['compact', 'full'], default='compact',
                          help='Result display mode for MCP returns: compact (filters verbose output) or full - default: compact')
        parser.add_argument('--max-output-tokens', type=int, default=10000,
                          help='Maximum tokens for MCP output (0 for unlimited) - default: 10000')
        # Multi-session arguments (multi-session is enabled by default)
        parser.add_argument('--multi-session', action='store_true', default=True,
                          help='Enable multi-session mode for parallel Stata execution (default: enabled)')
        parser.add_argument('--no-multi-session', action='store_true',
                          help='Disable multi-session mode (use single shared Stata instance)')
        parser.add_argument('--max-sessions', type=int, default=100,
                          help='Maximum concurrent sessions when multi-session is enabled - default: 100')
        parser.add_argument('--session-timeout', type=int, default=3600,
                          help='Session idle timeout in seconds - default: 3600 (1 hour)')

        # Special handling when running as a module
        if is_running_as_module:
            print(f"Command line arguments when running as module: {sys.argv}")
            # When run as a module, the first arg won't be the script path
            args_to_parse = sys.argv[1:]
        else:
            # Regular mode - arg 0 is script path
            #print(f"[MCP Server] Original command line arguments: {sys.argv}")
            args_to_parse = sys.argv
            
            # Skip if an argument is a duplicate script path (e.g., on Windows with shell:true)
            clean_args = []
            script_path_found = False
            
            for arg in args_to_parse:
                # Skip duplicate script paths, but keep the first one (sys.argv[0])
                if arg.endswith('stata_mcp_server.py'):
                    if script_path_found and arg != sys.argv[0]:
                        logging.debug(f"Skipping duplicate script path: {arg}")
                        continue
                    script_path_found = True
                
                clean_args.append(arg)
            
            args_to_parse = clean_args
        
        # Process commands for Stata path with spaces
        fixed_args = []
        i = 0
        while i < len(args_to_parse):
            arg = args_to_parse[i]
                
            if arg == '--stata-path' and i + 1 < len(args_to_parse):
                # The next argument might be a path that got split
                stata_path = args_to_parse[i + 1]
                
                # Check if this is a quoted path
                if (stata_path.startswith('"') and not stata_path.endswith('"')) or (stata_path.startswith("'") and not stata_path.endswith("'")):
                    # Look for the rest of the path in subsequent arguments
                    i += 2  # Move past '--stata-path' and the first part
                    
                    # Get the quote character (single or double)
                    quote_char = stata_path[0]
                    path_parts = [stata_path[1:]]  # Remove the starting quote
                    
                    # Collect all parts until we find the end quote
                    while i < len(args_to_parse):
                        current = args_to_parse[i]
                        if current.endswith(quote_char):
                            # Found the end quote
                            path_parts.append(current[:-1])  # Remove the ending quote
                            break
                        else:
                            path_parts.append(current)
                        i += 1
                    
                    # Join all parts to form the complete path
                    complete_path = " ".join(path_parts)
                    fixed_args.append('--stata-path')
                    fixed_args.append(complete_path)
                else:
                    # Normal path handling (either without quotes or with properly matched quotes)
                    fixed_args.append(arg)
                    fixed_args.append(stata_path)
                    i += 2
            else:
            # For all other arguments, add them as-is
                fixed_args.append(arg)
                i += 1
        
        # Print debug info
        print(f"Command line arguments: {fixed_args}")
        
        # Use the fixed arguments
        args = parser.parse_args(fixed_args[1:] if fixed_args and not is_running_as_module else fixed_args)
        print(f"Parsed arguments: stata_path={args.stata_path}, port={args.port}")
        
        # Check if args.stata_path accidentally captured other arguments
        if args.stata_path and ' --' in args.stata_path:
            # The stata_path might have captured other arguments
            parts = args.stata_path.split(' --')
            # The first part is the actual stata_path
            stata_path = parts[0].strip()
            print(f"WARNING: Detected merged arguments in Stata path. Fixing: {args.stata_path} -> {stata_path}")
            logging.warning(f"Fixed merged arguments in Stata path: {args.stata_path} -> {stata_path}")
            args.stata_path = stata_path
        
        # If Stata path was enclosed in quotes, remove them
        if args.stata_path:
            args.stata_path = args.stata_path.strip('"\'')
            logging.debug(f"Cleaned Stata path: {args.stata_path}")

        # Configure log file
        log_file = args.log_file or 'stata_mcp_server.log'
        log_dir = os.path.dirname(log_file)
        
        # Create log directory if needed
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
                print(f"Created log directory: {log_dir}")
            except Exception as e:
                print(f"ERROR: Failed to create log directory {log_dir}: {str(e)}")
                # Continue anyway, the file handler creation will fail if needed
        
        # Always print where we're trying to log
        print(f"Logging to: {os.path.abspath(log_file)}")
            
        # Remove existing handlers
        for handler in logging.getLogger().handlers[:]:
            logging.getLogger().removeHandler(handler)
            
        # Add file handler
        try:
            file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logging.getLogger().addHandler(file_handler)
            print(f"Successfully configured log file: {os.path.abspath(log_file)}")
        except Exception as log_error:
            print(f"ERROR: Failed to configure log file {log_file}: {str(log_error)}")
            # Continue with console logging only
        
        # Re-add console handler
        logging.getLogger().addHandler(console_handler)
        
        # Set log level
        log_level = getattr(logging, args.log_level)
        logging.getLogger().setLevel(log_level)
        
        # Set Stata edition
        global stata_edition, log_file_location, custom_log_directory, workspace_root, extension_path
        global result_display_mode, max_output_tokens
        global multi_session_enabled, multi_session_max_sessions, multi_session_timeout
        stata_edition = args.stata_edition.lower()
        log_file_location = args.log_file_location
        custom_log_directory = args.custom_log_directory
        workspace_root = args.workspace_root
        result_display_mode = args.result_display_mode
        max_output_tokens = args.max_output_tokens
        # Multi-session is enabled by default, but can be disabled with --no-multi-session
        multi_session_enabled = args.multi_session and not args.no_multi_session
        multi_session_max_sessions = args.max_sessions
        multi_session_timeout = args.session_timeout

        # Try to determine extension path from the log file path
        if args.log_file:
            # If log file is in a logs subdirectory, the parent of that is the extension path
            log_file_dir = os.path.dirname(os.path.abspath(args.log_file))
            if log_file_dir.endswith('logs'):
                extension_path = os.path.dirname(log_file_dir)
            else:
                extension_path = log_file_dir

        logging.info(f"Using Stata {stata_edition.upper()} edition")
        logging.info(f"Log file location setting: {log_file_location}")
        logging.info(f"Result display mode: {result_display_mode}")
        logging.info(f"Max output tokens: {max_output_tokens}")
        logging.info(f"Multi-session mode: {'enabled' if multi_session_enabled else 'disabled'}")
        if multi_session_enabled:
            logging.info(f"Max sessions: {multi_session_max_sessions}")
            logging.info(f"Session timeout: {multi_session_timeout}s")
        if custom_log_directory:
            logging.info(f"Custom log directory: {custom_log_directory}")
        if extension_path:
            logging.info(f"Extension path: {extension_path}")
        
        # Log startup information
        logging.info(f"Log initialized at {os.path.abspath(log_file)}")
        logging.info(f"Log level set to {args.log_level}")
        logging.info(f"Platform: {platform.system()} {platform.release()}")
        logging.info(f"Python version: {sys.version}")
        logging.info(f"Working directory: {os.getcwd()}")

        # Set Stata path
        global STATA_PATH
        if args.stata_path:
            # Strip quotes if present
            STATA_PATH = args.stata_path.strip('"\'')
        else:
            STATA_PATH = os.environ.get('STATA_PATH')
            if not STATA_PATH:
                if platform.system() == 'Darwin':  # macOS
                    STATA_PATH = '/Applications/Stata'
                elif platform.system() == 'Windows':
                    # Try common Windows paths
                    potential_paths = [
                        'C:\\Program Files\\Stata18',
                        'C:\\Program Files\\Stata17', 
                        'C:\\Program Files\\Stata16',
                        'C:\\Program Files (x86)\\Stata18',
                        'C:\\Program Files (x86)\\Stata17',
                        'C:\\Program Files (x86)\\Stata16'
                    ]
                    for path in potential_paths:
                        if os.path.exists(path):
                            STATA_PATH = path
                            break
                    if not STATA_PATH:
                        STATA_PATH = 'C:\\Program Files\\Stata18'  # Default if none found
                else:  # Linux
                    STATA_PATH = '/usr/local/stata'
                    
        logging.info(f"Using Stata path: {STATA_PATH}")
        if not os.path.exists(STATA_PATH):
            logging.error(f"Stata path does not exist: {STATA_PATH}")
            print(f"ERROR: Stata path does not exist: {STATA_PATH}")
            sys.exit(1)
        
        # Check if the requested port is available
        port = args.port
        
        if args.force_port:
            # Kill any existing process on the port
            kill_process_on_port(port)
        else:
            # Always kill processes on port 4000
            if port == 4000:
                logging.info(f"Ensuring port 4000 is available by terminating any existing processes")
                kill_process_on_port(port)
            else:
                # For other ports, check if available
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    result = s.connect_ex(('localhost', port))
                    if result == 0:  # Port is in use
                        logging.warning(f"Port {port} is already in use")
                        # Kill the process on the port instead of finding a new one
                        logging.info(f"Attempting to kill process using port {port}")
                        kill_process_on_port(port)
        
        # Try to initialize Stata (for single-session mode or as fallback)
        if not multi_session_enabled:
            try_init_stata(STATA_PATH)
        else:
            # In multi-session mode, initialize the session manager
            # Each session will initialize its own Stata instance in a worker process
            logging.info("Multi-session mode enabled - initializing session manager")
            try:
                # Add the script's directory to Python path for session_manager import
                script_dir = os.path.dirname(os.path.abspath(__file__))
                if script_dir not in sys.path:
                    sys.path.insert(0, script_dir)
                from session_manager import SessionManager

                # Determine graphs directory (same as used by single-session mode)
                if extension_path:
                    graphs_dir = os.path.join(extension_path, 'graphs')
                else:
                    graphs_dir = os.path.join(tempfile.gettempdir(), 'stata_mcp_graphs')
                os.makedirs(graphs_dir, exist_ok=True)
                logging.info(f"Graphs directory for multi-session mode: {graphs_dir}")

                global session_manager
                session_manager = SessionManager(
                    stata_path=STATA_PATH,
                    stata_edition=stata_edition,
                    max_sessions=multi_session_max_sessions,
                    session_timeout=multi_session_timeout,
                    enabled=True,
                    graphs_dir=graphs_dir
                )
                if session_manager.start():
                    logging.info("Session manager started successfully")
                    # Mark Stata as available (through session manager)
                    global stata_available, has_stata
                    stata_available = True
                    has_stata = True
                else:
                    logging.error("Failed to start session manager")
                    multi_session_enabled = False
                    # Fall back to single-session mode
                    try_init_stata(STATA_PATH)
            except ImportError as e:
                logging.error(f"Failed to import session_manager: {e}")
                logging.info("Falling back to single-session mode")
                multi_session_enabled = False
                try_init_stata(STATA_PATH)
            except Exception as e:
                logging.error(f"Error initializing session manager: {e}")
                logging.info("Falling back to single-session mode")
                multi_session_enabled = False
                try_init_stata(STATA_PATH)

        # Create and mount the MCP server
        # Only expose run_selection and run_file to LLMs
        # Other endpoints are still accessible via direct HTTP calls from VS Code extension
        # Configure HTTP client with ASGI transport and extended timeout for long-running Stata operations
        http_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://apiserver",
            timeout=1200.0  # 20 minutes timeout for long Stata operations
        )

        mcp = FastApiMCP(
            app,
            name=SERVER_NAME,
            description="This server provides tools for running Stata commands and scripts. Use stata_run_selection for running code snippets and stata_run_file for executing .do files.",
            http_client=http_client,
            exclude_operations=[
                "call_tool_v1_tools_post",  # Legacy VS Code extension endpoint
                "health_check_health_get",  # Health check endpoint
                "view_data_endpoint_view_data_get",  # Data viewer endpoint (VS Code only)
                "get_graph_graphs_graph_name_get",  # Graph serving endpoint (VS Code only)
                "clear_history_endpoint_clear_history_post",  # History clearing (VS Code only)
                "interactive_window_interactive_get",  # Interactive window (VS Code only)
                "stata_run_file_stream_endpoint_run_file_stream_get"  # SSE streaming endpoint (HTTP clients only)
            ]
        )

        # Mount SSE transport at /mcp for backward compatibility
        mcp.mount_sse(mount_path="/mcp")

        # ========================================================================
        # HTTP (Streamable) Transport - Separate Server Instance
        # ========================================================================
        # Create a SEPARATE MCP server instance for HTTP to avoid session conflicts
        # This ensures notifications go to the correct transport
        from mcp.server import Server as MCPServer
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from starlette.responses import StreamingResponse as StarletteStreamingResponse

        logging.info("Creating separate MCP server instance for HTTP transport...")
        http_mcp_server = MCPServer(SERVER_NAME)

        # Register list_tools handler to expose the same tools
        @http_mcp_server.list_tools()
        async def list_tools_http():
            """List available tools - delegate to main server"""
            # Get tools from the main fastapi_mcp server
            import mcp.types as types

            tools_list = []
            # stata_run_selection tool
            tools_list.append(types.Tool(
                name="stata_run_selection",
                description="Stata Run Selection Endpoint\n\nRun selected Stata code and return the output\n\n### Responses:\n\n**200**: Successful Response (Success Response)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "selection": {"type": "string", "title": "selection"}
                    },
                    "title": "stata_run_selectionArguments",
                    "required": ["selection"]
                }
            ))
            # stata_run_file tool
            tools_list.append(types.Tool(
                name="stata_run_file",
                description="Stata Run File Endpoint\n\nRun a Stata .do file and return the output (MCP-compatible endpoint)\n\nArgs:\n    file_path: Path to the .do file\n    timeout: Timeout in seconds (default: 600 seconds / 10 minutes)\n\nReturns:\n    Response with plain text output\n\n### Responses:\n\n**200**: Successful Response (Success Response)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "title": "file_path"},
                        "timeout": {"type": "integer", "default": 600, "title": "timeout"}
                    },
                    "title": "stata_run_fileArguments",
                    "required": ["file_path"]
                }
            ))
            # stata_session tool for session management
            tools_list.append(types.Tool(
                name="stata_session",
                description="Stata Session Management\n\nManage Stata sessions for parallel execution. Supports two actions:\n- list: List all active sessions and their status\n- destroy: Destroy an existing session\n\nIn multi-session mode, you can run multiple Stata tasks in parallel by specifying different session_id values in run_selection or run_file calls. Sessions are created automatically when needed.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "destroy"],
                            "default": "list",
                            "description": "Action to perform: 'list' to show sessions, 'destroy' to remove a session"
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Session ID. Required for 'destroy' action"
                        }
                    },
                    "title": "stata_sessionArguments"
                }
            ))
            return tools_list

        # Register call_tool handler to execute tools with HTTP server's context
        @http_mcp_server.call_tool()
        async def call_tool_http(name: str, arguments: dict) -> list:
            """Execute tools using HTTP server's own context for proper notification routing"""
            import mcp.types as types

            logging.debug(f"HTTP server executing tool: {name}")

            # Handle stata_session tool specially since it's not in operation_map
            if name == "stata_session":
                # Call the /v1/tools endpoint directly
                response = await http_client.post(
                    "/v1/tools",
                    json={
                        "tool": "stata_session",
                        "parameters": arguments
                    }
                )
                response_data = response.json()
                if response_data.get("status") == "success":
                    return [types.TextContent(
                        type="text",
                        text=response_data.get("result", "")
                    )]
                else:
                    return [types.TextContent(
                        type="text",
                        text=f"Error: {response_data.get('message', 'Unknown error')}"
                    )]

            # Call the fastapi_mcp's execute method, which has the streaming wrapper
            # The streaming wrapper will check http_mcp_server.request_context (which is set by StreamableHTTPSessionManager)
            result = await mcp._execute_api_tool(
                client=http_client,
                tool_name=name,
                arguments=arguments,
                operation_map=mcp.operation_map,  # Correct attribute name
                http_request_info=None
            )

            return result

        logging.debug("Registered tool handlers with HTTP server")

        # Create HTTP session manager with dedicated server
        http_session_manager = StreamableHTTPSessionManager(
            app=http_mcp_server,  # Use dedicated HTTP server, not shared
            event_store=None,
            json_response=False,  # Use SSE format for responses
            stateless=False,  # Maintain session state
        )
        logging.info("HTTP transport configured with dedicated MCP server")

        # Create a custom Response class that properly handles ASGI streaming
        class ASGIPassthroughResponse(StarletteStreamingResponse):
            """Response that passes through ASGI calls without buffering"""
            def __init__(self, asgi_handler, scope, receive):
                # Initialize the parent class with a dummy streaming function
                # We need this to set up all required attributes like background, headers, etc.
                super().__init__(content=iter([]), media_type="text/event-stream")

                # Store our ASGI handler
                self.asgi_handler = asgi_handler
                self.scope_data = scope
                self.receive_func = receive

            async def __call__(self, scope, receive, send):
                """Handle ASGI request/response cycle"""
                # Call the ASGI handler directly with the provided send callback
                # This allows SSE events to be sent immediately without buffering
                await self.asgi_handler(self.scope_data, self.receive_func, send)

        @app.api_route(
            "/mcp-streamable",
            methods=["GET", "POST", "DELETE"],
            include_in_schema=False,
            operation_id="mcp_http_streamable"
        )
        async def handle_mcp_streamable(request: Request):
            """Handle MCP Streamable HTTP requests with proper ASGI passthrough"""
            # Return a response that directly passes through to the ASGI handler
            # This avoids any buffering by FastAPI/Starlette
            return ASGIPassthroughResponse(
                asgi_handler=http_session_manager.handle_request,
                scope=request.scope,
                receive=request.receive
            )

        # Store the session manager for startup/shutdown
        app.state.http_session_manager = http_session_manager
        app.state.http_session_manager_cm = None

        # Define startup handler for the HTTP session manager
        async def _start_http_session_manager():
            """Start the HTTP session manager task group"""
            try:
                logging.info("Starting StreamableHTTP session manager...")
                # Enter the context manager
                app.state.http_session_manager_cm = http_session_manager.run()
                await app.state.http_session_manager_cm.__aenter__()
                logging.info("✓ StreamableHTTP session manager started successfully")
            except Exception as e:
                logging.error(f"Failed to start StreamableHTTP session manager: {e}", exc_info=True)
                raise

        # Define shutdown handler for the HTTP session manager
        async def _stop_http_session_manager():
            """Stop the HTTP session manager"""
            if app.state.http_session_manager_cm:
                try:
                    logging.info("Stopping StreamableHTTP session manager...")
                    await app.state.http_session_manager_cm.__aexit__(None, None, None)
                    logging.info("✓ StreamableHTTP session manager stopped")
                except Exception as e:
                    logging.error(f"Error stopping HTTP session manager: {e}", exc_info=True)

        # Store handlers on app.state for the lifespan manager to call
        app.state._http_session_manager_starter = _start_http_session_manager
        app.state._http_session_manager_stopper = _stop_http_session_manager
        logging.debug("HTTP session manager startup/shutdown handlers registered with lifespan")

        # Store reference
        mcp._http_transport = http_session_manager
        logging.info("MCP HTTP Streamable transport mounted at /mcp-streamable with TRUE SSE streaming (ASGI direct)")

        LOG_LEVEL_RANK = {
            "debug": 0,
            "info": 1,
            "notice": 2,
            "warning": 3,
            "error": 4,
            "critical": 5,
            "alert": 6,
            "emergency": 7,
        }
        DEFAULT_LOG_LEVEL = "notice"

        @mcp.server.set_logging_level()
        async def handle_set_logging_level(level: str):
            """Persist client-requested log level for the current session."""
            try:
                ctx = mcp.server.request_context
            except LookupError:
                logging.debug("logging/setLevel received outside of request context")
                return

            session = getattr(ctx, "session", None)
            if session is not None:
                setattr(session, "_stata_log_level", (level or "info").lower())
                logging.debug(f"Set MCP log level for session to {level}")

        # Enhance stata_run_file with MCP-native streaming updates
        original_execute = mcp._execute_api_tool

        async def execute_with_streaming(*call_args, **call_kwargs):
            """Wrap tool execution to stream progress for long-running Stata jobs."""
            if not call_args:
                raise TypeError("execute_with_streaming requires bound 'self'")

            bound_self = call_args[0]
            original_args = call_args[1:]
            original_kwargs = dict(call_kwargs)

            # Extract known keyword arguments
            working_kwargs = dict(call_kwargs)
            client = working_kwargs.pop("client", None)
            tool_name = working_kwargs.pop("tool_name", None)
            arguments = working_kwargs.pop("arguments", None)
            operation_map = working_kwargs.pop("operation_map", None)
            http_request_info = working_kwargs.pop("http_request_info", None)

            # Log and discard unexpected kwargs to stay forwards-compatible
            for extra_key in list(working_kwargs.keys()):
                extra_val = working_kwargs.pop(extra_key, None)
                logging.debug(f"Ignoring unexpected MCP execute kwarg: {extra_key}={extra_val!r}")

            remaining = list(original_args)

            # Fill from positional args if any are missing
            if client is None and remaining:
                client = remaining.pop(0)
            if tool_name is None and remaining:
                tool_name = remaining.pop(0)
            if arguments is None and remaining:
                arguments = remaining.pop(0)
            if operation_map is None and remaining:
                operation_map = remaining.pop(0)
            if http_request_info is None and remaining:
                http_request_info = remaining.pop(0)

            # If not our tool or required data missing, fall back to original implementation
            if (
                tool_name != "stata_run_file"
                or client is None
                or operation_map is None
            ):
                return await original_execute(*original_args, **original_kwargs)

            arguments_dict = dict(arguments or {})

            # Try to get request context from either HTTP or SSE server
            # IMPORTANT: Check HTTP first! If we check SSE first, we might get stale SSE context
            # even when the request came through HTTP.
            ctx = None
            server_type = "unknown"
            try:
                ctx = http_mcp_server.request_context
                server_type = "HTTP"
                logging.debug(f"Using HTTP server request context: {ctx}")
            except (LookupError, NameError):
                # HTTP server has no context, try SSE server
                try:
                    ctx = bound_self.server.request_context
                    server_type = "SSE"
                    logging.debug(f"Using SSE server request context: {ctx}")
                except LookupError:
                    logging.debug("No MCP request context available; skipping streaming wrapper")
                    return await original_execute(
                        client=client,
                        tool_name=tool_name,
                        arguments=arguments_dict,
                        operation_map=operation_map,
                        http_request_info=http_request_info,
                    )

            session = getattr(ctx, "session", None)
            request_id = getattr(ctx, "request_id", None)
            progress_token = getattr(getattr(ctx, "meta", None), "progressToken", None)

            # DEBUG: Log session information
            logging.info(f"✓ Streaming enabled via {server_type} server - Tool: {tool_name}")
            if session:
                session_attrs = [attr for attr in dir(session) if not attr.startswith('__')]
                logging.debug(f"Session type: {type(session)}, Attributes: {session_attrs[:10]}")
                session_id = getattr(session, "_session_id", getattr(session, "session_id", getattr(session, "id", None)))
            else:
                session_id = None
            logging.debug(f"Tool execution - Server: {server_type}, Session ID: {session_id}, Request ID: {request_id}, Progress Token: {progress_token}")

            if session is None:
                logging.debug("MCP session not available; falling back to default execution")
                return await original_execute(
                    client=client,
                    tool_name=tool_name,
                    arguments=arguments_dict,
                    operation_map=operation_map,
                    http_request_info=http_request_info,
                )

            if not hasattr(session, "_stata_log_level"):
                setattr(session, "_stata_log_level", DEFAULT_LOG_LEVEL)

            file_path = arguments_dict.get("file_path", "")

            try:
                timeout = int(arguments_dict.get("timeout", 600))
            except (TypeError, ValueError):
                timeout = 600

            resolved_path, resolution_candidates = resolve_do_file_path(file_path)
            effective_path = resolved_path or os.path.abspath(file_path)
            base_name = os.path.splitext(os.path.basename(effective_path))[0]
            log_file_path = get_log_file_path(effective_path, base_name)

            logging.info(f"📡 MCP streaming enabled for {os.path.basename(file_path)}")
            logging.debug(f"MCP log streaming monitoring: {log_file_path}")
            if not resolved_path:
                logging.debug(f"Resolution attempts: {resolution_candidates}")

            import asyncio as _asyncio
            import time as _time

            async def send_log(level: str, message: str):
                level = (level or "info").lower()
                session_level = getattr(session, "_stata_log_level", DEFAULT_LOG_LEVEL)
                if LOG_LEVEL_RANK.get(level, 0) < LOG_LEVEL_RANK.get(session_level, LOG_LEVEL_RANK[DEFAULT_LOG_LEVEL]):
                    return
                logging.debug(f"MCP streaming log [{level}] (session level {session_level}): {message}")
                try:
                    await session.send_log_message(
                        level=level,
                        data=message,
                        logger="stata-mcp",
                        related_request_id=request_id,
                    )
                except Exception as send_exc:  # noqa: BLE001
                    logging.debug(f"Unable to send MCP log message: {send_exc}")

            async def send_progress(elapsed: float, message: str | None = None):
                if progress_token is None:
                    return
                try:
                    await session.send_progress_notification(
                        progress_token=progress_token,
                        progress=elapsed,
                        total=timeout,
                        message=message,
                        related_request_id=request_id,
                    )
                except Exception as send_exc:  # noqa: BLE001
                    logging.debug(f"Unable to send MCP progress notification: {send_exc}")

            task = _asyncio.create_task(
                original_execute(
                    client=client,
                    tool_name=tool_name,
                    arguments=arguments_dict,
                    operation_map=operation_map,
                    http_request_info=http_request_info,
                )
            )

            start_time = _time.time()
            stream_interval = 5
            poll_interval = 2
            last_stream = 0.0
            last_offset = 0

            start_message = f"▶️  Starting Stata execution: {os.path.basename(effective_path)}"
            await send_log("notice", start_message)
            await send_progress(0.0, start_message)

            try:
                while not task.done():
                    await _asyncio.sleep(poll_interval)
                    now = _time.time()
                    elapsed = now - start_time

                    if now - last_stream >= stream_interval:
                        progress_msg = f"⏱️  {elapsed:.0f}s elapsed / {timeout}s timeout"
                        await send_progress(elapsed, progress_msg)

                        if os.path.exists(log_file_path):
                            await send_log(
                                "notice",
                                f"{progress_msg}\n\n(📁 Inspecting Stata log for new output...)",
                            )
                            try:
                                with open(log_file_path, "r", encoding="utf-8", errors="replace") as log_file:
                                    log_file.seek(last_offset)
                                    new_content = log_file.read()
                                    last_offset = log_file.tell()

                                snippet = ""
                                if new_content.strip():
                                    lines = new_content.strip().splitlines()
                                    snippet = "\n".join(lines[-3:])


                                if snippet:
                                    progress_msg = f"{progress_msg}\n\n📝 Recent output:\n{snippet}"

                                await send_log("notice", progress_msg)
                            except Exception as read_exc:  # noqa: BLE001
                                logging.debug(f"Error reading log for streaming: {read_exc}")
                                await send_log(
                                    "notice",
                                    f"{progress_msg} (waiting for output...)",
                                )
                        else:
                            await send_log(
                                "notice",
                                f"{progress_msg} (initializing...)",
                            )

                        last_stream = now

                result = await task
                total_time = _time.time() - start_time
                await send_log("notice", f"✅ Execution completed in {total_time:.1f}s")
                return result
            except Exception as exc:
                logging.error(f"❌ Error during MCP streaming: {exc}", exc_info=True)
                await send_log("error", f"Error during execution: {exc}")
                raise

        import types as _types

        mcp._execute_api_tool = _types.MethodType(execute_with_streaming, mcp)
        logging.info("📡 MCP streaming wrapper installed for stata_run_file")

        # Mark MCP as initialized (will also be set in startup event)
        global mcp_initialized
        mcp_initialized = True
        logging.info("MCP server mounted and initialized")

        try:
            # Start the server
            logging.info(f"Starting Stata MCP Server on {args.host}:{port}")
            logging.info(f"Stata available: {stata_available}")
            
            # Print to stdout as well to ensure visibility
            if platform.system() == 'Windows':
                # For Windows, completely skip the startup message if another instance is detected
                # as we already printed information above
                if not stata_banner_displayed:
                    print(f"INITIALIZATION SUCCESS: Stata MCP Server starting on {args.host}:{port}")
                    print(f"Stata available: {stata_available}")
                    print(f"Log file: {os.path.abspath(log_file)}")
            else:
                # Normal behavior for macOS/Linux
                print(f"INITIALIZATION SUCCESS: Stata MCP Server starting on {args.host}:{port}")
                print(f"Stata available: {stata_available}")
                print(f"Log file: {os.path.abspath(log_file)}")
            
            import uvicorn
            import asyncio

            # On Windows, use custom server setup to handle IOCP socket errors gracefully
            if platform.system() == "Windows":
                def windows_exception_handler(loop, context):
                    """Custom exception handler to suppress Windows IOCP socket errors."""
                    exception = context.get('exception')
                    message = context.get('message', '')

                    # Check for known non-critical socket errors
                    if exception and isinstance(exception, OSError):
                        # WinError 64: The specified network name is no longer available
                        # WinError 995: The I/O operation has been aborted
                        # These are normal when clients disconnect and can be safely ignored
                        winerror = getattr(exception, 'winerror', None)
                        if winerror in (64, 995):
                            logging.debug(f"Suppressed Windows socket error (winerror={winerror}): {exception}")
                            return
                        # Also check error message for network-related issues
                        err_str = str(exception).lower()
                        if 'network name is no longer available' in err_str:
                            logging.debug(f"Suppressed Windows network error: {exception}")
                            return

                    # Suppress "Accept failed on a socket" messages for network errors
                    if 'accept failed' in message.lower():
                        if exception and isinstance(exception, OSError):
                            logging.debug(f"Suppressed accept failed error: {exception}")
                            return

                    # For other exceptions, use the default handler
                    loop.default_exception_handler(context)

                async def run_server_windows():
                    """Run uvicorn server with custom exception handling on Windows."""
                    config = uvicorn.Config(
                        app,
                        host=args.host,
                        port=port,
                        log_level="warning",
                        access_log=False
                    )
                    server = uvicorn.Server(config)
                    await server.serve()

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.set_exception_handler(windows_exception_handler)
                try:
                    loop.run_until_complete(run_server_windows())
                finally:
                    loop.close()
            else:
                # Standard uvicorn.run for macOS/Linux
                uvicorn.run(
                    app,
                    host=args.host,
                    port=port,
                    log_level="warning",  # Use warning to allow important messages through
                    access_log=False  # Disable access logs
                )
            
        except Exception as e:
            logging.error(f"Server error: {str(e)}")
            traceback.print_exc()
            sys.exit(1)

    except Exception as e:
        logging.error(f"Error in main function: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 
