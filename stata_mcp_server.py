#!/usr/bin/env python
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

# Check Python version on Windows but don't exit immediately to allow logging
if platform.system() == 'Windows':
    required_version = (3, 11)
    current_version = (sys.version_info.major, sys.version_info.minor)
    if current_version < required_version:
        print(f"WARNING: Python 3.11 or higher is recommended on Windows. Current version: {sys.version}")
        print("Please install Python 3.11 from python.org for best compatibility.")
        # Log this but don't exit immediately so logs can be written

try:
    from fastapi import FastAPI, Request
    from fastapi_mcp.server import FastMCP, mount_mcp_server
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
    level=logging.DEBUG,
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

# Try to import pandas
try:
    import pandas as pd
    has_pandas = True
    logging.info("pandas module loaded successfully")
except ImportError:
    has_pandas = False
    logging.warning("pandas not available, data transfer functionality will be limited")

# Function to update Stata availability
def set_stata_available(value):
    """Update the module-level stata_available variable"""
    global stata_available
    stata_available = value

# Try to import Stata modules - real implementation only, no mocks
def try_init_stata(stata_path):
    """Try to initialize Stata with the given path"""
    global stata_available, has_stata, stata
    
    # Clean the path (remove quotes if present)
    if stata_path:
        stata_path = stata_path.strip('"\'')
    
    logging.info(f"Attempting to initialize Stata from path: {stata_path}")
    
    try:
        # Add environment variables to help with library loading
        if stata_path:
            if not os.path.exists(stata_path):
                logging.error(f"Stata path does not exist: {stata_path}")
                return False
                
            os.environ['SYSDIR_STATA'] = stata_path
            logging.info(f"Setting Stata path to: {stata_path}")
        
        stata_utilities_path = os.path.join(os.environ.get('SYSDIR_STATA', ''), 'utilities')
        if os.path.exists(stata_utilities_path):
            sys.path.insert(0, stata_utilities_path)
            logging.info(f"Added Stata utilities path to sys.path: {stata_utilities_path}")
        else:
            logging.warning(f"Stata utilities path not found: {stata_utilities_path}")
            
        # First try to import pystata.config
        try:
            from pystata import config
            logging.info("Successfully imported pystata")
            
            # Try to initialize Stata 
            try:
                # Initialize with MP edition
                config.init('mp')
                logging.info("Stata initialized successfully with MP edition")
                
                # Now import stata after initialization
                from pystata import stata as stata_module
                # Set module-level stata reference
                globals()['stata'] = stata_module
                
                # Successfully initialized Stata
                has_stata = True
                stata_available = True
                logging.info("pystata module loaded and initialized successfully")
                
                return True
            except Exception as init_error:
                logging.error(f"Failed to initialize Stata: {str(init_error)}")
                logging.error("Will attempt to continue without full Stata integration")
                
                # Some features will still work without full initialization
                has_stata = False
                stata_available = False
                
                return False
        except ImportError as config_error:
            logging.error(f"Could not import pystata.config: {str(config_error)}")
            logging.error("Stata commands will not be available")
            has_stata = False
            stata_available = False
            
            return False
    except Exception as e:
        logging.error(f"General error setting up Stata environment: {str(e)}")
        logging.error("Stata commands will not be available")
        has_stata = False
        stata_available = False
        
        return False

# Function to run a Stata command
def run_stata_command(command: str):
    """Run a Stata command"""
    logging.info(f"Running Stata command: {command}")
    
    # For multi-line commands, don't add semicolons - just clean up whitespace
    if "\n" in command:
        # Clean up the commands to ensure proper formatting without adding semicolons
        command = "\n".join(line.strip() for line in command.splitlines() if line.strip())
        logging.debug(f"Processed multiline command: {command}")
    
    # Check if pystata is available
    if has_stata and stata_available:
        # Run the command via pystata
        try:
            # Create a temp file to capture output
            with tempfile.NamedTemporaryFile(suffix='.do', delete=False, mode='w') as f:
                # Write the command to the file
                f.write(f"capture log close _all\n")
                f.write(f"log using \"{f.name}.log\", replace text\n")
                f.write(f"{command}\n")
                f.write(f"capture log close\n")
                do_file = f.name
            
            # Execute the do file with echo=False to completely silence Stata output to console
            try:
                # Redirect stdout temporarily to silence Stata output
                original_stdout = sys.stdout
                sys.stdout = open(os.devnull, 'w')
                
                try:
                    globals()['stata'].run(f"do \"{do_file}\"", echo=False)
                    logging.debug(f"Command executed successfully via pystata")
                finally:
                    # Restore stdout
                    sys.stdout.close()
                    sys.stdout = original_stdout
            except Exception as e:
                error_msg = f"Error running command: {str(e)}"
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
                
                # Return properly formatted output
                if not result_lines:
                    return "Command executed successfully (no output)"
                
                return "\n".join(result_lines)
                
            except Exception as e:
                error_msg = f"Error reading log file: {str(e)}"
                logging.error(error_msg)
                return error_msg
                
        except Exception as e:
            error_msg = f"Error executing Stata command: {str(e)}"
            logging.error(error_msg)
            return error_msg
            
    else:
        error_msg = "Stata is not available. Please check if Stata is installed and configured correctly."
        logging.error(error_msg)
        return error_msg

def run_stata_selection(selection: str):
    """Run selected Stata code"""
    return run_stata_command(selection)

def run_stata_file(file_path: str):
    """Run a Stata .do file"""
    try:
        # Verify file exists and has .do extension
        if not os.path.exists(file_path):
            return f"Error: File not found: {file_path}"
        
        if not file_path.endswith('.do'):
            return f"Error: File must be a Stata .do file with .do extension"
        
        # Run the do file
        return run_stata_command(f"do \"{file_path}\"")
    except Exception as e:
        logging.error(f"Error running do file: {str(e)}")
        return f"Error: {str(e)}"

# Function to kill any process using the specified port
def kill_process_on_port(port):
    """Kill any process that is currently using the specified port"""
    try:
        if platform.system() == "Windows":
            # Windows command to find and kill process on port
            find_cmd = f"netstat -ano | findstr :{port}"
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

# Create the MCP server
mcp = FastMCP(
    name=SERVER_NAME,
    instructions="This server provides tools for running Stata commands and scripts."
)

# Add tools to the MCP server
@mcp.tool()
def stata_run_selection(selection: str) -> str:
    """Run selected Stata code and return the output"""
    logging.info(f"Running selection: {selection}")
    return run_stata_selection(selection)

@mcp.tool()
def stata_run_file(file_path: str) -> str:
    """Run a Stata .do file and return the output"""
    logging.info(f"Running file: {file_path}")
    return run_stata_file(file_path)

# Mount the MCP server to the FastAPI app
mount_mcp_server(app, mcp)

# Add FastAPI endpoint for legacy VS Code extension
@app.post("/v1/tools")
async def call_tool(request: ToolRequest):
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
            result = run_stata_selection(request.parameters["selection"])
            
        elif mcp_tool_name == "stata_run_file":
            if "file_path" not in request.parameters:
                return ToolResponse(
                    status="error",
                    message="Missing required parameter: file_path"
                )
            result = run_stata_file(request.parameters["file_path"])
        
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

# Add health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": SERVER_NAME,
        "version": SERVER_VERSION,
        "stata_available": stata_available
    }

def main():
    """Main function to set up and run the server"""
    try:
        # Get Stata path from arguments
        parser = argparse.ArgumentParser(description='Stata MCP Server')
        parser.add_argument('--stata-path', type=str, help='Path to Stata installation')
        parser.add_argument('--port', type=int, default=4000, help='Port to run MCP server on')
        parser.add_argument('--host', type=str, default='localhost', help='Host to bind the server to')
        parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
                          default='DEBUG', help='Logging level')
        parser.add_argument('--force-port', action='store_true', help='Force the specified port, even if it requires killing processes')
        parser.add_argument('--log-file', type=str, help='Path to log file (default: stata_mcp_server.log in current directory)')
        args = parser.parse_args()

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
            # Try to find an available port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                if result == 0:  # Port is in use
                    logging.warning(f"Port {port} is already in use")
                    logging.info("Searching for an available port...")
                    new_port = find_available_port(port + 1)
                    if new_port:
                        logging.info(f"Using port {new_port} instead of {port}")
                        port = new_port
                    else:
                        logging.error("Could not find an available port. Will attempt to use specified port anyway.")
                        # Try to kill processes on the port as a last resort
                        kill_process_on_port(port)
        
        # Try to initialize Stata
        try_init_stata(STATA_PATH)
        
        try:
            # Start the server
            logging.info(f"Starting Stata MCP Server on {args.host}:{port}")
            logging.info(f"Stata available: {stata_available}")
            
            # Print to stdout as well to ensure visibility
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