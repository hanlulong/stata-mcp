#!/usr/bin/env node

/**
 * Script to start the Stata MCP server.
 * This is a cross-platform alternative to using bash scripts.
 */

const { spawn, exec, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const net = require('net');

// Default options
const options = {
    host: 'localhost',
    port: 4001,
    logLevel: 'INFO',
    stataPath: null,
    forcePort: false, // Don't force port by default
    logFile: null,    // Add log file option
    stataEdition: 'mp', // Default Stata edition is MP
    logFileLocation: 'extension', // Default log file location
    customLogDirectory: null, // Custom log directory
};

// Parse command line arguments
process.argv.slice(2).forEach((arg, i, argv) => {
    if (arg === '--port' && argv[i + 1]) {
        options.port = parseInt(argv[i + 1], 10);
    } else if (arg === '--host' && argv[i + 1]) {
        options.host = argv[i + 1];
    } else if (arg === '--log-level' && argv[i + 1]) {
        options.logLevel = argv[i + 1];
    } else if (arg === '--stata-path' && argv[i + 1]) {
        options.stataPath = argv[i + 1];
    } else if (arg === '--log-file' && argv[i + 1]) {
        options.logFile = argv[i + 1];
    } else if (arg === '--stata-edition' && argv[i + 1]) {
        options.stataEdition = argv[i + 1].toLowerCase();
        console.log(`Setting Stata edition to: ${options.stataEdition}`);
    } else if (arg === '--log-file-location' && argv[i + 1]) {
        options.logFileLocation = argv[i + 1];
    } else if (arg === '--custom-log-directory' && argv[i + 1]) {
        options.customLogDirectory = argv[i + 1];
    } else if (arg === '--force-port') {
        options.forcePort = true;
    } else if (arg === '--help') {
        console.log(`
Usage: node start-server.js [options]

Options:
  --port PORT           Port to run the server on (default: 4000)
  --host HOST           Host to bind to (default: localhost)
  --stata-path PATH     Path to Stata installation
  --stata-edition EDITION Stata edition to use (mp, se, be) - default: mp
  --log-level LEVEL     Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  --log-file FILE       Log file path
  --log-file-location LOCATION Location for .do file logs (extension, workspace, custom) - default: extension
  --custom-log-directory DIR Custom directory for logs (when location is custom)
  --force-port          Force the specified port, killing any process using it
  --help                Show this help message
        `);
        process.exit(0);
    }
});

// Get extension directory and server script path
const extensionDir = path.resolve(__dirname, '..');
const serverScript = path.join(extensionDir, 'src', 'stata_mcp_server.py');

// Check if port is in use
async function isPortInUse(port) {
    return new Promise((resolve) => {
        const server = net.createServer();
        server.once('error', () => resolve(true));
        server.once('listening', () => {
            server.close();
            resolve(false);
        });
        server.listen(port);
    });
}

// Function to check if a port is available
async function isPortAvailable(port) {
    return new Promise((resolve) => {
        const server = net.createServer();
        server.once('error', err => {
            console.log(`Port ${port} is not available: ${err.message}`);
            resolve(false);
        });
        server.once('listening', () => {
            server.close();
            resolve(true);
        });
        server.listen(port);
    });
}

// Main function to start the server
async function startServer() {
    console.log(`Operating system: ${process.platform}`);
    
    try {
        // Get extension directory
        const extensionDir = path.resolve(__dirname, '..');
        const pythonPathFile = path.join(extensionDir, '.python-path');
        const setupCompleteFile = path.join(extensionDir, '.setup-complete');
        const serverScriptPath = path.join(extensionDir, 'src', 'stata_mcp_server.py');
        
        // Use the port from options (could be user specified)
        const port = options.port;
        const host = options.host;
        
        // Only attempt to free the port if force-port is enabled
        if (options.forcePort && await isPortInUse(port)) {
            console.log(`Port ${port} is in use. Attempting to free it...`);
            // Try platform-specific kill commands
            if (process.platform === 'win32') {
                try {
                    execSync(`FOR /F "tokens=5" %P IN ('netstat -ano ^| findstr :${port} ^| findstr LISTENING') DO taskkill /F /PID %P`);
                    console.log(`Killed process on port ${port} (Windows)`);
                } catch (error) {
                    console.log(`Could not kill process using Windows method: ${error.message}`);
                }
            } else {
                try {
                    execSync(`lsof -ti:${port} | xargs kill -9`);
                    console.log(`Killed process on port ${port} (Unix)`);
                } catch (error) {
                    console.log(`Could not kill process using Unix method: ${error.message}`);
                }
            }
            
            // Wait a moment for the port to be released
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            // Verify the port is now available
            if (await isPortInUse(port)) {
                console.warn(`Warning: Port ${port} is still in use after kill attempt.`);
            } else {
                console.log(`Successfully freed port ${port}`);
            }
        }
        
        // Check for Python path file
        let pythonPath;
        if (fs.existsSync(pythonPathFile)) {
            pythonPath = fs.readFileSync(pythonPathFile, 'utf8').trim();
            console.log(`Using Python from path file: ${pythonPath}`);
        } else if (fs.existsSync(setupCompleteFile)) {
            // Try to find the Python in virtual environment
            const venvPath = path.join(extensionDir, '.venv');
            if (process.platform === 'win32') {
                pythonPath = path.join(venvPath, 'Scripts', 'python.exe');
            } else {
                pythonPath = path.join(venvPath, 'bin', 'python');
            }
            console.log(`Python path file not found, using venv Python: ${pythonPath}`);
        } else {
            // Try system Python
            pythonPath = process.platform === 'win32' ? 'py' : 'python3';
            console.log(`No Python environment found, using system Python: ${pythonPath}`);
        }
        
        // Check if Python exists
        try {
            if (pythonPath !== 'py' && pythonPath !== 'python3') {
                // For explicit paths, check if the file exists
                if (!fs.existsSync(pythonPath)) {
                    throw new Error(`Python path does not exist: ${pythonPath}`);
                }
            }
            
            // Parse a cleaned (properly quoted) state path
            if (options.stataPath) {
                // Remove any quotes that might cause issues
                options.stataPath = options.stataPath.replace(/^["']|["']$/g, '');
                console.log(`Using Stata path: ${options.stataPath}`);
            }
            
            let serverProcess;
            
            if (process.platform === 'win32') {
                // For Windows, use the Python module approach to avoid script path duplication issue
                
                // Extract the directory containing the script
                const scriptDir = path.dirname(serverScriptPath);
                
                // Build command using Python module execution
                let cmdString = `"${pythonPath}" -m stata_mcp_server`;
                
                // Add arguments
                cmdString += ` --port ${port} --host ${host}`;
                
                // Add Stata path if provided
                if (options.stataPath) {
                    cmdString += ` --stata-path "${options.stataPath}"`;
                }
                
                // Add log file if specified
                if (options.logFile) {
                    cmdString += ` --log-file "${options.logFile}"`;
                }
                
                // Always add Stata edition parameter
                cmdString += ` --stata-edition ${options.stataEdition}`;
                
                console.log(`Windows command string: ${cmdString}`);
                
                // Use exec with the correct working directory
                serverProcess = exec(cmdString, {
                    stdio: 'inherit',
                    cwd: scriptDir  // Set working directory to script location for module import
                });
            } else {
                // Unix/macOS - use normal array arguments with spawn
                const cmd = pythonPath;
                const args = [
                    serverScriptPath,
                    '--port', port.toString(),
                    '--host', host
                ];
                
                // Add Stata path if provided
                if (options.stataPath) {
                    args.push('--stata-path');
                    // Handle spaces in paths properly without additional quotes that become part of the argument
                    args.push(options.stataPath);
                }
                
                // Add log file if specified
                if (options.logFile) {
                    args.push('--log-file');
                    args.push(options.logFile);
                }
                
                // Always add Stata edition parameter
                args.push('--stata-edition');
                args.push(options.stataEdition);
                
                console.log(`Unix command: ${cmd} ${args.join(' ')}`);

                // Use spawn without shell for Unix
                // On macOS, use detached mode and pipe stdio to prevent showing in dock
                serverProcess = spawn(cmd, args, {
                    stdio: ['ignore', 'pipe', 'pipe'],
                    shell: false,
                    detached: false,
                    env: {
                        ...process.env,
                        // Prevent Python from showing in dock on macOS
                        PYTHONDONTWRITEBYTECODE: '1'
                    }
                });

                // Log output from the server for debugging
                if (serverProcess.stdout) {
                    serverProcess.stdout.on('data', (data) => {
                        console.log(`[MCP Server] ${data.toString().trim()}`);
                    });
                }
                if (serverProcess.stderr) {
                    serverProcess.stderr.on('data', (data) => {
                        const message = data.toString().trim();
                        // Filter out Java initialization messages (informational, not errors)
                        if (message.includes('Picked up _JAVA_OPTIONS') ||
                            message.includes('Picked up JAVA_TOOL_OPTIONS')) {
                            // Silently ignore Java options messages
                            return;
                        }
                        console.error(`[MCP Server Error] ${message}`);
                    });
                }
            }
            
            serverProcess.on('error', (err) => {
                console.error(`Failed to start server: ${err.message}`);
                process.exit(1);
            });
            
            serverProcess.on('close', (code) => {
                if (code !== 0 && code !== null) {
                    console.error(`Server exited with code ${code}`);
                    process.exit(code);
                }
            });
            
            // Keep the process running
            process.on('SIGINT', () => {
                console.log('Shutting down server...');
                serverProcess.kill();
                process.exit(0);
            });
            
        } catch (error) {
            console.error(`Error starting server: ${error.message}`);
            process.exit(1);
        }
    } catch (error) {
        console.error(`Unexpected error: ${error.message}`);
        process.exit(1);
    }
}

// Start the server
startServer().catch(err => {
    console.error(`Unhandled error: ${err.message}`);
    process.exit(1);
}); 