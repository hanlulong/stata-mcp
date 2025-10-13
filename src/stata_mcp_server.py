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
import importlib.util
import subprocess
import traceback
import socket
from typing import Dict, Any, Optional
import warnings
import re

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
    from fastapi import FastAPI, Request, Response
    from fastapi_mcp import FastApiMCP
    from pydantic import BaseModel, Field
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
SERVER_VERSION = "1.0.0"

# Flag for Stata availability
stata_available = False
has_stata = False
stata = None  # Module-level reference to stata module
STATA_PATH = None
# Add a flag to track if we've already displayed the Stata banner
stata_banner_displayed = False
# Add a storage for continuous command history
command_history = []
# Store the current Stata edition
stata_edition = 'mp'  # Default to MP edition
# Store log file settings
log_file_location = 'extension'  # Default to extension directory
custom_log_directory = ''  # Custom log directory
extension_path = None  # Path to the extension directory

# Try to import pandas
try:
    import pandas as pd
    has_pandas = True
    logging.info("pandas module loaded successfully")
except ImportError:
    has_pandas = False
    logging.warning("pandas not available, data transfer functionality will be limited")
    warnings.warn("pandas not available, data transfer functionality will be limited")

# Function to update Stata availability
def set_stata_available(value):
    """Update the module-level stata_available variable"""
    global stata_available
    stata_available = value

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
                
                # Initialize with the specified Stata edition
                config.init(stata_edition)
                logging.info(f"Stata initialized successfully with {stata_edition.upper()} edition")
                
                # Now import stata after initialization
                from pystata import stata as stata_module
                # Set module-level stata reference
                globals()['stata'] = stata_module
                
                # Successfully initialized Stata
                has_stata = True
                stata_available = True
                
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

def get_log_file_path(do_file_path, do_file_base):
    """Get the appropriate log file path based on user settings

    Returns an absolute path to ensure log files are saved to the correct location
    regardless of Stata's working directory.
    """
    global log_file_location, custom_log_directory, extension_path

    if log_file_location == 'extension':
        # Use logs folder in extension directory
        if extension_path:
            logs_dir = os.path.join(extension_path, 'logs')
            # Create logs directory if it doesn't exist
            os.makedirs(logs_dir, exist_ok=True)
            log_path = os.path.join(logs_dir, f"{do_file_base}_mcp.log")
            return os.path.abspath(log_path)
        else:
            # Fallback to workspace if extension path is not available
            do_file_dir = os.path.dirname(do_file_path)
            log_path = os.path.join(do_file_dir, f"{do_file_base}_mcp.log")
            return os.path.abspath(log_path)
    elif log_file_location == 'custom':
        # Use custom directory
        if custom_log_directory and os.path.exists(custom_log_directory):
            log_path = os.path.join(custom_log_directory, f"{do_file_base}_mcp.log")
            return os.path.abspath(log_path)
        else:
            # Fallback to workspace if custom directory is invalid
            logging.warning(f"Custom log directory not valid: {custom_log_directory}, falling back to workspace")
            do_file_dir = os.path.dirname(do_file_path)
            log_path = os.path.join(do_file_dir, f"{do_file_base}_mcp.log")
            return os.path.abspath(log_path)
    else:  # workspace
        # Use same directory as .do file (original behavior)
        do_file_dir = os.path.dirname(do_file_path)
        log_path = os.path.join(do_file_dir, f"{do_file_base}_mcp.log")
        return os.path.abspath(log_path)

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

# Function to run a Stata command
def run_stata_command(command: str, clear_history=False):
    """Run a Stata command

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
            # Enable graph listing for this command using low-level API
            try:
                from pystata.config import stlib, get_encode_str
                logging.debug("Enabling graph listing with _gr_list on...")
                stlib.StataSO_Execute(get_encode_str("qui _gr_list on"), False)
                logging.debug("Successfully enabled graph listing")
            except Exception as e:
                logging.warning(f"Could not enable graph listing: {str(e)}")
                logging.debug(f"Graph listing enable error: {traceback.format_exc()}")

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

                # Immediately check for graphs while they're still in memory
                # This happens right after stata.run() completes, before any cleanup
                try:
                    logging.debug("Checking for graphs immediately after execution (interactive mode)...")
                    graphs_from_interactive = display_graphs_interactive(graph_format='png', width=800, height=600)
                    if graphs_from_interactive:
                        logging.info(f"Captured {len(graphs_from_interactive)} graphs in interactive mode")
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
        return []

    try:
        import sfi
        from pystata.config import stlib, get_encode_str

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
                # The name() option does NOT need quotes - it's a Stata name, not a string
                gph_exp = f'qui graph export "{graph_file}", name({gname}) replace width(800) height(600)'

                logging.debug(f"Executing graph export command: {gph_exp}")
                rc = stlib.StataSO_Execute(get_encode_str(gph_exp), False)
                if rc != 0:
                    logging.warning(f"Failed to export graph '{gname}' (rc={rc})")
                    continue

                if os.path.exists(graph_file):
                    graphs_info.append({
                        "name": gname,
                        "path": graph_file
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

    Args:
        graph_format: Format for exported graphs ('svg', 'png', or 'pdf')
        width: Width for graph export (pixels for png, inches for svg/pdf)
        height: Height for graph export (pixels for png, inches for svg/pdf)

    Returns:
        List of dictionaries with graph info: [{"name": "graph1", "path": "/path/to/graph.png", "format": "png", "command": "scatter y x"}, ...]
    """
    global stata_available, has_stata, extension_path

    if not (has_stata and stata_available):
        return []

    try:
        import sfi
        from pystata.config import stlib, get_encode_str

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
                if graph_format == 'svg':
                    graph_file = os.path.join(graphs_dir, f'{gname}.svg')
                    if width and height:
                        gph_exp = f'qui graph export "{graph_file}", name({gname}) replace width({width}) height({height})'
                    else:
                        gph_exp = f'qui graph export "{graph_file}", name({gname}) replace'
                elif graph_format == 'pdf':
                    graph_file = os.path.join(graphs_dir, f'{gname}.pdf')
                    # For PDF, use xsize/ysize instead of width/height
                    if width and height:
                        gph_exp = f'qui graph export "{graph_file}", name({gname}) replace xsize({width/96:.2f}) ysize({height/96:.2f})'
                    else:
                        gph_exp = f'qui graph export "{graph_file}", name({gname}) replace'
                else:  # png (default)
                    graph_file = os.path.join(graphs_dir, f'{gname}.png')
                    if width and height:
                        gph_exp = f'qui graph export "{graph_file}", name({gname}) replace width({width}) height({height})'
                    else:
                        gph_exp = f'qui graph export "{graph_file}", name({gname}) replace width(800) height(600)'

                # Export the graph
                logging.debug(f"Exporting graph: {gph_exp}")
                rc = stlib.StataSO_Execute(get_encode_str(gph_exp), False)
                if rc != 0:
                    logging.warning(f"Failed to export graph '{gname}' (rc={rc})")
                    continue

                if os.path.exists(graph_file):
                    graph_dict = {
                        "name": gname,
                        "path": graph_file,
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

def run_stata_selection(selection, working_dir=None):
    """Run selected Stata code

    Args:
        selection: The Stata code to run
        working_dir: Optional working directory to change to before execution
    """
    # If a working directory is provided, prepend a cd command
    if working_dir and os.path.isdir(working_dir):
        logging.info(f"Changing working directory to: {working_dir}")
        # Normalize path for the OS
        working_dir = os.path.normpath(working_dir)
        # On Windows, ensure backslashes
        if platform.system() == "Windows":
            working_dir = working_dir.replace('/', '\\')
        # Use double quotes for the cd command to handle spaces
        cd_command = f'cd "{working_dir}"'
        # Combine cd command with the selection
        full_command = f"{cd_command}\n{selection}"
        return run_stata_command(full_command)
    else:
        return run_stata_command(selection)

def run_stata_file(file_path: str, timeout=600):
    """Run a Stata .do file with improved handling for long-running processes
    
    Args:
        file_path: The path to the .do file to run
        timeout: Timeout in seconds (default: 600 seconds / 10 minutes)
    """
    # Set timeout from parameter instead of hardcoding
    MAX_TIMEOUT = timeout
    
    try:
        original_path = file_path
        
        # Normalize path separators for the current OS
        file_path = os.path.normpath(file_path)
        
        # On Windows, convert forward slashes to backslashes if needed
        if platform.system() == "Windows" and '/' in file_path:
            file_path = file_path.replace('/', '\\')
            logging.info(f"Converted path for Windows: {file_path}")
        
        # Path resolution logic for relative paths
        if not os.path.isabs(file_path):
            # Get the current working directory
            cwd = os.getcwd()
            logging.info(f"File path is not absolute. Current working directory: {cwd}")
            
            # Try paths in this order - add more specific path resolution for Windows
            possible_paths = [
                file_path,  # As provided
                os.path.join(cwd, file_path),  # Relative to CWD
                os.path.join(cwd, os.path.basename(file_path)),  # Just filename in CWD
            ]
            
            # Add Windows-specific path checks
            if platform.system() == "Windows":
                # Try both forward and backward slashes on Windows
                if '/' in file_path:
                    win_path = file_path.replace('/', '\\')
                    possible_paths.append(win_path)
                    possible_paths.append(os.path.join(cwd, win_path))
                elif '\\' in file_path:
                    unix_path = file_path.replace('\\', '/')
                    possible_paths.append(unix_path)
                    possible_paths.append(os.path.join(cwd, unix_path))
            
            # Check for file in subdirectories (up to 2 levels)
            for root, dirs, files in os.walk(cwd, topdown=True, followlinks=False):
                if os.path.basename(file_path) in files and root != cwd:
                    subdir_path = os.path.join(root, os.path.basename(file_path))
                    if subdir_path not in possible_paths:
                        possible_paths.append(subdir_path)
                
                # Limit depth to 2 levels
                if root.replace(cwd, '').count(os.sep) >= 2:
                    dirs[:] = []  # Don't go deeper
            
            # Try to find the file in one of the possible paths
            found = False
            for test_path in possible_paths:
                # Normalize path for comparison
                test_path = os.path.normpath(test_path)
                if os.path.exists(test_path) and test_path.lower().endswith('.do'):
                    file_path = test_path
                    found = True
                    logging.info(f"Found file at: {file_path}")
                    break
            
            if not found:
                error_msg = f"Error: File not found: {original_path}. Tried these paths: {', '.join(possible_paths)}"
                logging.error(error_msg)
                
                # Add more helpful error message for Windows
                if platform.system() == "Windows":
                    error_msg += "\n\nCommon Windows path issues:\n"
                    error_msg += "1. Make sure the file path uses correct separators (use \\ instead of /)\n"
                    error_msg += "2. Check if the file exists in the specified location\n"
                    error_msg += "3. If using relative paths, the current working directory is: " + os.getcwd()
                
                return error_msg
        
        # Verify file exists (final check)
        if not os.path.exists(file_path):
            error_msg = f"Error: File not found: {file_path}"
            logging.error(error_msg)
            
            # Add more helpful error message for Windows
            if platform.system() == "Windows":
                error_msg += "\n\nCommon Windows path issues:\n"
                error_msg += "1. Make sure the file path uses correct separators (use \\ instead of /)\n"
                error_msg += "2. Check if the file exists in the specified location\n"
                error_msg += "3. If using relative paths, the current working directory is: " + os.getcwd()
                
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

            # Process line by line to comment out log commands and add graph names where needed
            cls_commands_found = 0
            for line in do_file_content.splitlines():
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

                # Check if this is a graph creation command that might need a name
                # Match: scatter, histogram, twoway, kdensity, graph bar/box/dot/etc (but not graph export)
                graph_match = re.match(r'^(\s*)(scatter|histogram|twoway|kdensity|graph\s+(bar|box|dot|pie|matrix|hbar|hbox|combine))\s+(.*)$', line, re.IGNORECASE)

                if graph_match:
                    indent = graph_match.group(1)
                    graph_cmd = graph_match.group(2)
                    rest = graph_match.group(4) if graph_match.lastindex >= 4 else ""

                    # Check if it already has name() option
                    if not re.search(r'\bname\s*\(', rest, re.IGNORECASE):
                        # Add automatic unique name
                        graph_counter += 1
                        graph_name = f"graph{graph_counter}"

                        # Add name option - if there's a comma, add after it; otherwise add with comma
                        if ',' in rest:
                            # Insert name option right after the first comma
                            rest = re.sub(r',', f', name({graph_name}, replace)', 1)
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
                # Change working directory to the .do file's directory
                # This ensures the .do file executes in its workspace (relative paths work correctly)
                # The log file uses an absolute path, so it's saved to the configured location
                temp_do.write(f"cd \"{do_file_dir}\"\n")
                # Note: _gr_list on is enabled externally before .do file execution
                # Note: Graph names are auto-injected above into modified_content
                # Then add our own log command with absolute path
                temp_do.write(f"log using \"{custom_log_file}\", replace text\n")
                temp_do.write(modified_content)
                temp_do.write(f"\ncapture log close _all\n")  # Ensure all logs are closed at the end
                # Note: We intentionally do NOT disable _gr_list so graphs persist for detection
                modified_do_file = temp_do.name
                
            logging.info(f"Created modified do file at {modified_do_file}")
                
        except Exception as e:
            error_msg = f"Error processing do file: {str(e)}"
            logging.error(error_msg)
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
                # Enable graph listing for this do file execution using low-level API
                try:
                    from pystata.config import stlib, get_encode_str
                    stlib.StataSO_Execute(get_encode_str("qui _gr_list on"), False)
                    logging.debug("Enabled graph listing for do file")
                except Exception as e:
                    logging.warning(f"Could not enable graph listing: {str(e)}")

                # Record start time for timeout tracking
                start_time = time.time()
                last_update_time = start_time
                update_interval = 10  # Update every 10 seconds initially
                
                # Initialize log tracking
                log_file_exists = False
                last_log_size = 0
                last_reported_lines = 0
                
                # Execute command via PyStata in separate thread to allow polling
                stata_thread = None
                stata_error = None
                
                def run_stata_thread():
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
                    except Exception as e:
                        nonlocal stata_error
                        stata_error = str(e)
                
                import threading
                stata_thread = threading.Thread(target=run_stata_thread)
                stata_thread.daemon = True
                stata_thread.start()
                
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
                            # ATTEMPT 1: Send Stata break command
                            logging.warning(f"TIMEOUT - Attempt 1: Sending Stata break command")
                            try:
                                globals()['stata'].run("break", echo=False)
                                time.sleep(0.5)  # Give it a moment
                                if not stata_thread.is_alive():
                                    termination_successful = True
                                    logging.warning("Thread terminated via Stata break command")
                            except Exception as e:
                                logging.warning(f"Stata break command failed: {str(e)}")

                            # ATTEMPT 2: Try to forcibly raise an exception in the thread
                            if not termination_successful and hasattr(stata_thread, "_stop"):
                                logging.warning(f"TIMEOUT - Attempt 2: Forcing thread stop")
                                try:
                                    # This is a more aggressive approach
                                    # The _stop method is not officially supported but often works
                                    stata_thread._stop()
                                    time.sleep(0.5)  # Give it a moment
                                    if not stata_thread.is_alive():
                                        termination_successful = True
                                        logging.warning("Thread terminated via thread._stop")
                                except Exception as e:
                                    logging.warning(f"Thread stop failed: {str(e)}")

                            # ATTEMPT 3: Try to find and kill the Stata process (last resort)
                            if not termination_successful:
                                logging.warning(f"TIMEOUT - Attempt 3: Looking for Stata process to terminate")
                                try:
                                    # Find any Stata processes
                                    if platform.system() == "Windows":
                                        # Windows approach
                                        subprocess.run(["taskkill", "/F", "/IM", "stata*.exe"], 
                                                      stdout=subprocess.DEVNULL, 
                                                      stderr=subprocess.DEVNULL)
                                    else:
                                        # macOS/Linux approach
                                        subprocess.run(["pkill", "-f", "stata"], 
                                                      stdout=subprocess.DEVNULL, 
                                                      stderr=subprocess.DEVNULL)
                                    
                                    logging.warning("Sent kill signal to Stata processes")
                                except Exception as e:
                                    logging.error(f"Process kill failed: {str(e)}")
                        except Exception as term_error:
                            logging.error(f"Error during forced termination: {str(term_error)}")
                        
                        # Set a flag indicating timeout regardless of termination success
                        stata_error = f"Operation timed out after {MAX_TIMEOUT} seconds"
                        logging.warning(f"Setting timeout error: {stata_error}")
                        break
                    
                    # Check if it's time for an update
                    if current_time - last_update_time >= update_interval:
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
                                            
                                            last_reported_lines = len(lines)
                                except Exception as e:
                                    logging.warning(f"Error reading log for progress update: {str(e)}")
                            
                            last_log_size = current_log_size
                        
                        last_update_time = current_time
                        
                        # Adaptive polling - increase interval as the process runs longer
                        if elapsed_time > 600:  # After 10 minutes
                            update_interval = 60  # Check every minute
                        elif elapsed_time > 300:  # After 5 minutes
                            update_interval = 30  # Check every 30 seconds
                        elif elapsed_time > 60:  # After 1 minute
                            update_interval = 20  # Check every 20 seconds
                    
                    # Sleep briefly to avoid consuming too much CPU
                    time.sleep(0.5)
                
                # Thread completed or timed out
                if stata_error:
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
                                line = lines[i].rstrip()
                                
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
        return result
        
    except Exception as e:
        error_msg = f"Error in run_stata_file: {str(e)}"
        logging.error(error_msg)
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

# Parameter models for the MCP tools
class RunSelectionParams(BaseModel):
    selection: str = Field(..., description="The Stata code to execute")

class RunFileParams(BaseModel):
    file_path: str = Field(..., description="The full path to the .do file")
    timeout: int = Field(600, description="Timeout in seconds (default: 600 seconds / 10 minutes)")

# Define Legacy VS Code Extension Support
class ToolRequest(BaseModel):
    tool: str
    parameters: Dict[str, Any]

class ToolResponse(BaseModel):
    status: str
    result: Optional[str] = None
    message: Optional[str] = None

# Create the FastAPI app
app = FastAPI(
    title=SERVER_NAME,
    version=SERVER_VERSION,
    description="Stata MCP Server - Exposes Stata functionality to AI models via MCP protocol"
)

# Define regular FastAPI routes for Stata functions
@app.post("/run_selection", operation_id="stata_run_selection", response_class=Response)
async def stata_run_selection_endpoint(selection: str) -> Response:
    """Run selected Stata code and return the output"""
    logging.info(f"Running selection: {selection}")
    result = run_stata_selection(selection)
    # Format output for better display - replace escaped newlines with actual newlines
    formatted_result = result.replace("\\n", "\n")
    return Response(content=formatted_result, media_type="text/plain")

@app.post("/run_file", operation_id="stata_run_file", response_class=Response)
async def stata_run_file_endpoint(file_path: str, timeout: int = 600) -> Response:
    """Run a Stata .do file and return the output
    
    Args:
        file_path: Path to the .do file
        timeout: Timeout in seconds (default: 600 seconds / 10 minutes)
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
    
    logging.info(f"Running file: {file_path} with timeout {timeout} seconds ({timeout/60:.1f} minutes)")
    result = run_stata_file(file_path, timeout=timeout)
    
    # Format output for better display - replace escaped newlines with actual newlines
    formatted_result = result.replace("\\n", "\n")
    
    # Log the output (truncated) for debugging
    logging.debug(f"Run file output (first 100 chars): {formatted_result[:100]}...")
    
    return Response(content=formatted_result, media_type="text/plain")

# MCP server will be initialized in main() after args are parsed

# Add FastAPI endpoint for legacy VS Code extension
@app.post("/v1/tools", include_in_schema=False)
async def call_tool(request: ToolRequest) -> ToolResponse:
    try:
        # Map VS Code extension tool names to MCP tool names
        tool_name_map = {
            "run_selection": "stata_run_selection", 
            "run_file": "stata_run_file"
        }
        
        # Get the actual tool name
        mcp_tool_name = tool_name_map.get(request.tool, request.tool)
        
        # Log the request
        logging.info(f"REST API request for tool: {request.tool} -> {mcp_tool_name}")
        
        # Check if the tool exists
        if mcp_tool_name not in ["stata_run_selection", "stata_run_file"]:
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
            # Get optional working_dir parameter
            working_dir = request.parameters.get("working_dir", None)
            result = run_stata_selection(request.parameters["selection"], working_dir=working_dir)
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
                
            logging.info(f"MCP run_file request for: {file_path} with timeout {timeout} seconds ({timeout/60:.1f} minutes)")
            
            # Normalize the path for cross-platform compatibility
            file_path = os.path.normpath(file_path)
            
            # On Windows, convert forward slashes to backslashes if needed
            if platform.system() == "Windows" and '/' in file_path:
                file_path = file_path.replace('/', '\\')
            
            # Run the file through the run_stata_file function with timeout
            result = run_stata_file(file_path, timeout=timeout)
            
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
                if platform.system() == "Windows":
                    result += "\n\nCommon Windows path issues:\n"
                    result += "1. Make sure the file path uses correct separators (use \\ instead of /)\n"
                    result += "2. Check if the file exists in the specified location\n"
                    result += "3. If using relative paths, the current working directory is: " + os.getcwd()
        
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

# Endpoint to serve graph images
# Hidden from OpenAPI schema so it won't be exposed to LLMs via MCP
@app.get("/graphs/{graph_name}", include_in_schema=False)
async def get_graph(graph_name: str):
    """Serve a graph image file"""
    try:
        # Construct the path to the graph file
        if extension_path:
            graphs_dir = os.path.join(extension_path, 'graphs')
        else:
            graphs_dir = os.path.join(tempfile.gettempdir(), 'stata_mcp_graphs')

        # Support both with and without .png extension
        if not graph_name.endswith('.png'):
            graph_name = f"{graph_name}.png"

        graph_path = os.path.join(graphs_dir, graph_name)

        # Check if file exists
        if not os.path.exists(graph_path):
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
async def view_data_endpoint(if_condition: str = None):
    """Get current Stata data as a pandas DataFrame and return as JSON

    Args:
        if_condition: Optional Stata if condition (e.g., "price > 5000 & mpg < 30")
    """
    global stata_available, stata

    try:
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

        # Apply if condition if provided
        if if_condition:
            logging.info(f"Applying filter: if {if_condition}")
            try:
                # Get full data first
                df = stata.pdataframe_from_data()

                if df is None or df.empty:
                    raise Exception("No data currently loaded in Stata")

                # Use Stata to create a filter marker variable
                try:
                    import sfi

                    # First, check if variable already exists and drop it
                    try:
                        stata.run("capture drop _filter_marker", inline=False, echo=False)
                    except:
                        pass

                    # Generate marker for rows that match the condition
                    gen_cmd = f"quietly generate byte _filter_marker = ({if_condition})"
                    logging.debug(f"Running filter command: {gen_cmd}")

                    try:
                        stata.run(gen_cmd, inline=False, echo=False)
                        logging.debug(f"Generate command executed successfully")
                    except SystemError as se:
                        logging.error(f"SystemError in generate command: {str(se)}")
                        raise Exception(f"Invalid condition syntax: {if_condition}")
                    except Exception as e:
                        logging.error(f"Exception in generate command: {type(e).__name__}: {str(e)}")
                        raise Exception(f"Error creating filter: {str(e)}")

                    # Get the marker variable values using SFI
                    n_obs = sfi.Data.getObsTotal()
                    logging.debug(f"Total observations: {n_obs}")

                    # Get the variable index for _filter_marker
                    var_index = sfi.Data.getVarIndex('_filter_marker')
                    logging.debug(f"Filter marker variable index: {var_index}")

                    if var_index < 0:
                        raise Exception("Failed to create filter marker variable")

                    # Read the filter values for all observations
                    # NOTE: sfi.Data.get() returns nested lists like [[1]] or [[0]]
                    # We need to extract the actual value
                    filter_mask = []
                    for i in range(n_obs):
                        val = sfi.Data.get('_filter_marker', i)
                        # Extract the actual value from nested list structure
                        if isinstance(val, list) and len(val) > 0:
                            if isinstance(val[0], list) and len(val[0]) > 0:
                                actual_val = val[0][0]
                            else:
                                actual_val = val[0]
                        else:
                            actual_val = val
                        filter_mask.append(actual_val == 1)

                    # Debug: Log first few values and count
                    true_count = sum(filter_mask)
                    if n_obs > 0:
                        sample_vals = [sfi.Data.get('_filter_marker', i) for i in range(min(5, n_obs))]
                        logging.debug(f"First 5 marker values (raw): {sample_vals}")
                    logging.debug(f"Filter mask true count: {true_count} out of {n_obs}")

                    # Drop the temporary marker
                    stata.run("quietly drop _filter_marker", inline=False, echo=False)

                    # Filter the DataFrame using the mask
                    df = df[filter_mask].reset_index(drop=True)
                    logging.info(f"Filtered data: {len(df)} rows match condition (out of {n_obs} total)")

                except Exception as stata_err:
                    # Clean up if there's an error
                    try:
                        stata.run("capture drop _filter_marker", inline=False, echo=False)
                    except:
                        pass
                    logging.error(f"Filter processing error: {type(stata_err).__name__}: {str(stata_err)}")
                    raise Exception(f"{str(stata_err)}")

            except Exception as filter_err:
                logging.error(f"Filter error: {str(filter_err)}")
                return Response(
                    content=json.dumps({
                        "status": "error",
                        "message": f"Filter error: {str(filter_err)}"
                    }),
                    media_type="application/json",
                    status_code=400
                )
        else:
            # Get data as pandas DataFrame without filtering
            logging.info("Getting data from Stata using pdataframe_from_data()")
            df = stata.pdataframe_from_data()

        # Check if data is empty
        if df is None or df.empty:
            logging.info("No data currently loaded in Stata")
            return Response(
                content=json.dumps({
                    "status": "success",
                    "message": "No data currently loaded",
                    "data": [],
                    "columns": [],
                    "rows": 0
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
                "index": df.index.tolist()
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
                        parameters: { selection: command }
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
                    parameters: { file_path: autoRunFile }
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
                    parameters: { selection: autoRunCode }
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
        parser.add_argument('--log-file-location', type=str, choices=['extension', 'workspace', 'custom'], default='extension',
                          help='Location for .do file logs (extension, workspace, custom) - default: extension')
        parser.add_argument('--custom-log-directory', type=str, default='',
                          help='Custom directory for .do file logs (when location is custom)')
        
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
        global stata_edition, log_file_location, custom_log_directory, extension_path
        stata_edition = args.stata_edition.lower()
        log_file_location = args.log_file_location
        custom_log_directory = args.custom_log_directory
        
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
        
        # Try to initialize Stata
        try_init_stata(STATA_PATH)
        
        # Create and mount the MCP server
        # Only expose run_selection and run_file to LLMs
        # Other endpoints are still accessible via direct HTTP calls from VS Code extension
        mcp = FastApiMCP(
            app,
            name=SERVER_NAME,
            description="This server provides tools for running Stata commands and scripts. Use stata_run_selection for running code snippets and stata_run_file for executing .do files.",
            exclude_operations=[
                "call_tool_v1_tools_post",  # Legacy VS Code extension endpoint
                "health_check_health_get",  # Health check endpoint
                "view_data_endpoint_view_data_get",  # Data viewer endpoint (VS Code only)
                "get_graph_graphs_graph_name_get",  # Graph serving endpoint (VS Code only)
                "clear_history_endpoint_clear_history_post",  # History clearing (VS Code only)
                "interactive_window_interactive_get"  # Interactive window (VS Code only)
            ]
        )

        # Mount the MCP server to the FastAPI app
        mcp.mount()
        
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