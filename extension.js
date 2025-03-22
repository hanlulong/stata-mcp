const vscode = require('vscode');
const { exec, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const axios = require('axios');
const net = require('net');
const childProcess = require('child_process');

// Global variables
let stataOutputChannel;
let stataAgentChannel;
let statusBarItem;
let mcpServerProcess;
let mcpServerRunning = false;
let agentWebviewPanel = null;
let stataOutputWebviewPanel = null;
let globalContext;
let detectedStataPath = null;

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    console.log('Stata extension activated');

    // Store context for later use
    globalContext = context;

    // Create output channel
    stataOutputChannel = vscode.window.createOutputChannel('Stata');
    stataOutputChannel.show(true);
    stataOutputChannel.appendLine('Stata extension activated.');
    
    // Create agent output channel
    stataAgentChannel = vscode.window.createOutputChannel('Stata Agent');
    
    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = "$(beaker) Stata";
    statusBarItem.tooltip = "Stata Integration";
    statusBarItem.command = 'stata-vscode.showOutput';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Log the extension path for debugging
    console.log(`Extension path: ${context.extensionPath || __dirname}`);
    stataOutputChannel.appendLine(`Extension path: ${context.extensionPath || __dirname}`);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('stata-vscode.runSelection', runSelection),
        vscode.commands.registerCommand('stata-vscode.runFile', runFile),
        vscode.commands.registerCommand('stata-vscode.showOutput', showOutput),
        vscode.commands.registerCommand('stata-vscode.showOutputWebview', showStataOutputWebview),
        vscode.commands.registerCommand('stata-vscode.testMcpServer', testMcpServer),
        vscode.commands.registerCommand('stata-vscode.detectStataPath', detectAndUpdateStataPath),
        vscode.commands.registerCommand('stata-vscode.askAgent', askAgent)
    );

    // Register file type/extension for Stata (this needs to happen immediately)
    vscode.languages.setLanguageConfiguration('stata', {
        comments: {
            lineComment: '*',
            blockComment: ['/*', '*/']
        },
        brackets: [['{', '}'], ['[', ']'], ['(', ')']],
        autoClosingPairs: [
            { open: '{', close: '}' },
            { open: '[', close: ']' },
            { open: '(', close: ')' },
            { open: '"', close: '"', notIn: ['string'] },
            { open: "'", close: "'", notIn: ['string'] }
        ]
    });

    // Automatically detect Stata path on startup
    detectStataPath().then(path => {
        if (path) {
            const config = vscode.workspace.getConfiguration('stata-vscode');
            const userPath = config.get('stataPath');
            
            // Only set the detected path if the user hasn't specified one
            if (!userPath) {
                config.update('stataPath', path, vscode.ConfigurationTarget.Global)
                    .then(() => {
                        console.log(`[DEBUG] Automatically set Stata path to: ${path}`);
                        stataOutputChannel.appendLine(`Detected Stata installation: ${path}`);
                    });
            }
        }
    });

    // Register event handlers
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(handleConfigurationChange),
        vscode.window.onDidChangeActiveTextEditor(checkActiveEditorIsStata)
    );

    // Check the current active editor
    checkActiveEditorIsStata(vscode.window.activeTextEditor);
    
    // Check for Python dependencies and install them if needed during activation
    const extensionPath = context.extensionPath || __dirname;
    const pythonPathFile = path.join(extensionPath, '.python-path');
    const backupPythonPathFile = path.join(extensionPath, '.python-path.backup');
    const setupInProgressFile = path.join(extensionPath, '.setup-in-progress');
    const setupErrorFile = path.join(extensionPath, '.setup-error');
    const setupCompleteFile = path.join(extensionPath, '.setup-complete');
    
    if (!fs.existsSync(pythonPathFile)) {
        stataOutputChannel.appendLine('Setting up Python dependencies during extension activation...');
        // Install Python dependencies immediately
        installDependencies();
        // We'll start the server after dependencies are installed
    } else {
        // Dependencies already installed, start the server
        startMcpServer();
    }
}

function deactivate() {
    // Stop MCP server if it was started by the extension
    if (mcpServerProcess) {
        mcpServerProcess.kill();
        mcpServerRunning = false;
    }
}

// Start the MCP server if it's not already running
async function startMcpServer() {
    const config = vscode.workspace.getConfiguration('stata-vscode');
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;
    
    // Get Stata path from settings, or detect it
    let stataPath = config.get('stataPath');
    if (!stataPath) {
        stataPath = await detectStataPath();
        
        if (stataPath) {
            // Save the detected path to settings
            await config.update('stataPath', stataPath, vscode.ConfigurationTarget.Global);
        } else {
            // Prompt user to set Stata path
            const result = await vscode.window.showErrorMessage(
                'Stata path not set. The extension needs to know where Stata is installed.',
                'Detect Automatically', 'Set Manually'
            );
            
            if (result === 'Detect Automatically') {
                await detectAndUpdateStataPath();
                stataPath = config.get('stataPath'); // Try to get it again after detection
            } else if (result === 'Set Manually') {
                vscode.commands.executeCommand('workbench.action.openSettings', 'stata-vscode.stataPath');
            }
            
            // If we still don't have a path, we can't continue
            if (!stataPath) {
                vscode.window.showErrorMessage('Stata path is required for the extension to work.');
                return;
            }
        }
    }
    
    // Now stataPath should be set
    console.log(`[DEBUG] Using Stata path: ${stataPath}`);
    stataOutputChannel.appendLine(`Using Stata path: ${stataPath}`);

    // Check if server is already running
    if (await isMcpServerRunning(host, port)) {
        console.log(`[DEBUG] MCP server already running on ${host}:${port}`);
        stataOutputChannel.appendLine(`MCP server already running on ${host}:${port}`);
        mcpServerRunning = true;
        updateStatusBar();
        return;
    }

    try {
        // Kill any existing process on the port just to be safe
        try {
            if (process.platform === 'win32') {
                await exec(`FOR /F "tokens=5" %P IN ('netstat -ano ^| findstr :${port} ^| findstr LISTENING') DO taskkill /F /PID %P`);
            } else {
                await exec(`lsof -t -i:${port} | xargs -r kill -9`);
            }
            stataOutputChannel.appendLine(`Killed existing processes on port ${port}`);
        } catch (error) {
            // Ignore errors, it's just a precaution
        }
        
        // Get the path of the current script
        const extensionPath = globalContext.extensionPath || __dirname;
        console.log(`[DEBUG] Using extension path: ${extensionPath}`);
        stataOutputChannel.appendLine(`Extension path: ${extensionPath}`);
        
        // Look for stata_mcp_server.py in various locations
        const possibleServerPaths = [
            path.join(extensionPath, 'stata_mcp_server.py'),
            path.join(extensionPath, 'scripts', 'stata_mcp_server.py')
        ];
        
        let mcpServerPath = null;
        for (const p of possibleServerPaths) {
                if (fs.existsSync(p)) {
                mcpServerPath = p;
                    break;
                }
            }

        if (!mcpServerPath) {
            const error = 'MCP server script not found. Please check your installation.';
            stataOutputChannel.appendLine(`Error: ${error}`);
            vscode.window.showErrorMessage(error);
                return;
            }

        stataOutputChannel.appendLine(`Server script found at: ${mcpServerPath}`);
            
        // Check for virtual environment Python
        let pythonCommand;
        const pythonPathFile = path.join(extensionPath, '.python-path');
        const backupPythonPathFile = path.join(extensionPath, '.python-path.backup');
        const setupInProgressFile = path.join(extensionPath, '.setup-in-progress');
        const setupErrorFile = path.join(extensionPath, '.setup-error');
        const setupCompleteFile = path.join(extensionPath, '.setup-complete');

        // Check if setup is in progress
        if (fs.existsSync(setupInProgressFile)) {
            const setupStartTime = fs.readFileSync(setupInProgressFile, 'utf8').trim();
            const setupStartDate = new Date(setupStartTime);
            const currentTime = new Date();
            const minutesSinceStart = (currentTime - setupStartDate) / (1000 * 60);
            
            if (minutesSinceStart < 10) {
                stataOutputChannel.appendLine(`Python dependency setup is in progress (started ${Math.round(minutesSinceStart)} minutes ago)`);
                vscode.window.showInformationMessage('Stata MCP extension is still setting up Python dependencies. Please wait a moment and try again.');
                return;
            } else {
                // Setup has been running too long, assume it failed
                stataOutputChannel.appendLine('Python dependency setup seems to be stuck. Attempting to restart setup.');
                fs.unlinkSync(setupInProgressFile);
            }
        }

        // Check if there was a setup error
        if (fs.existsSync(setupErrorFile)) {
            try {
                const errorDetails = fs.readFileSync(setupErrorFile, 'utf8');
                stataOutputChannel.appendLine(`Previous Python dependency setup failed: ${errorDetails}`);
            } catch (error) {
                stataOutputChannel.appendLine('Previous Python dependency setup failed. Details not available.');
            }
        }

        // First check the primary Python path file
        if (fs.existsSync(pythonPathFile)) {
            try {
                pythonCommand = fs.readFileSync(pythonPathFile, 'utf8').trim();
                // Check if this Python exists
                if (!fs.existsSync(pythonCommand)) {
                    stataOutputChannel.appendLine(`Python path ${pythonCommand} does not exist`);
                    
                    // Try the backup path file
                    if (fs.existsSync(backupPythonPathFile)) {
                        try {
                            pythonCommand = fs.readFileSync(backupPythonPathFile, 'utf8').trim();
                            if (fs.existsSync(pythonCommand)) {
                                stataOutputChannel.appendLine(`Using backup Python path: ${pythonCommand}`);
                            } else {
                                stataOutputChannel.appendLine(`Backup Python path ${pythonCommand} also does not exist`);
                                pythonCommand = process.platform === 'win32' ? 'py -3.11' : 'python3';
                            }
                        } catch (error) {
                            stataOutputChannel.appendLine(`Error reading backup Python path file: ${error.message}`);
                            pythonCommand = process.platform === 'win32' ? 'py -3.11' : 'python3';
                        }
                    } else {
                        stataOutputChannel.appendLine('No backup Python path file found, falling back to system Python');
                        pythonCommand = process.platform === 'win32' ? 'py -3.11' : 'python3';
                    }
                } else {
                    stataOutputChannel.appendLine(`Using virtual environment Python: ${pythonCommand}`);
                }
            } catch (error) {
                stataOutputChannel.appendLine(`Error reading Python path file: ${error.message}`);
                pythonCommand = process.platform === 'win32' ? 'py -3.11' : 'python3';
            }
        } else {
            // Fall back to system Python
            pythonCommand = process.platform === 'win32' ? 'py -3.11' : 'python3';
            
            // Check if setup has completed
            if (fs.existsSync(setupCompleteFile)) {
                stataOutputChannel.appendLine('Setup appears to be complete but Python path file is missing. Attempting repair...');
                // Attempt to recreate the Python path file
                try {
                    const venvPythonPath = process.platform === 'win32' 
                        ? path.join(extensionPath, '.venv', 'Scripts', 'python.exe')
                        : path.join(extensionPath, '.venv', 'bin', 'python');
                        
                    if (fs.existsSync(venvPythonPath)) {
                        fs.writeFileSync(pythonPathFile, venvPythonPath);
                        stataOutputChannel.appendLine(`Recreated Python path file pointing to: ${venvPythonPath}`);
                        pythonCommand = venvPythonPath;
                    } else {
                        stataOutputChannel.appendLine('Could not find virtual environment Python executable');
                    }
                } catch (error) {
                    stataOutputChannel.appendLine(`Error recreating Python path file: ${error.message}`);
                }
            } else {
                // Try to set up the virtual environment
                stataOutputChannel.appendLine('Python virtual environment not found, attempting to create it...');
                installDependencies();
                return;
            }
        }
        
        // Prepare the command arguments
        let args = [];
        
        // Windows-specific handling for system Python (not needed for venv Python)
        if (process.platform === 'win32' && !pythonCommand.endsWith('.exe')) {
            // Use Python 3.11 on Windows, with correct command structure
            pythonCommand = 'py';
            args.push('-3.11');
        }
        
        args.push(mcpServerPath, '--port', port.toString());
            
        if (stataPath) {
            // On Windows, handle paths with spaces correctly by wrapping in quotes
            if (process.platform === 'win32') {
                args.push('--stata-path', `"${stataPath}"`);
            } else {
                args.push('--stata-path', stataPath);
            }
        }
        
        // Add log file path in the extension directory
        if (process.platform === 'win32') {
            // Place log file in extension directory instead of temp folder
            const logFile = path.join(extensionPath, 'stata_mcp_server.log');
            args.push('--log-file', logFile);
            stataOutputChannel.appendLine(`Log file will be saved to: ${logFile}`);
        }
        
        // Log what we're about to execute
        const cmdString = `${pythonCommand} ${args.join(' ')}`;
        stataOutputChannel.appendLine(`Starting server with command: ${cmdString}`);
        console.log(`[DEBUG] Starting MCP server with command: ${cmdString}`);
        
        // Set the working directory to the directory containing the script
        const options = {
            cwd: path.dirname(mcpServerPath),
            detached: process.platform !== 'win32', // Don't detach on Windows
            shell: false, // Don't use shell to prevent command window
            stdio: 'pipe',  // Capture stdout and stderr
            windowsHide: true // Hide the window on Windows
        };
        
        // Start the server
        try {
            mcpServerProcess = spawn(pythonCommand, args, options);
        } catch (spawnError) {
            const errorMsg = `Failed to start Python: ${spawnError.message}`;
            stataOutputChannel.appendLine(errorMsg);
            if (process.platform === 'win32') {
                stataOutputChannel.appendLine("On Windows, make sure Python 3.11 is installed and in your PATH");
                stataOutputChannel.appendLine("Try running 'py -3.11 --version' in a command prompt to verify");
                vscode.window.showErrorMessage(`${errorMsg}. Please install Python 3.11 from python.org.`);
            } else {
                vscode.window.showErrorMessage(errorMsg);
            }
            return;
        }

        // Log stdout and stderr
        if (mcpServerProcess.stdout) {
            mcpServerProcess.stdout.on('data', (data) => {
            const output = data.toString().trim();
            console.log(`[MCP Server] ${output}`);
            stataOutputChannel.appendLine(`[MCP Server] ${output}`);
            });
        }
        
        if (mcpServerProcess.stderr) {
            mcpServerProcess.stderr.on('data', (data) => {
            const output = data.toString().trim();
            console.error(`[MCP Server Error] ${output}`);
            stataOutputChannel.appendLine(`[MCP Server Error] ${output}`);
            });
        }

        mcpServerProcess.on('error', (err) => {
            console.error(`[DEBUG] Failed to start MCP server: ${err.message}`);
            stataOutputChannel.appendLine(`Failed to start MCP server: ${err.message}`);
            
            if (process.platform === 'win32' && err.code === 'ENOENT') {
                const pyMsg = "Python not found. Please install Python 3.11 from python.org and add it to your PATH.";
                stataOutputChannel.appendLine(pyMsg);
                vscode.window.showErrorMessage(pyMsg);
            } else {
                vscode.window.showErrorMessage(`Failed to start MCP server: ${err.message}`);
            }
        });

        mcpServerProcess.on('exit', (code, signal) => {
            console.log(`[DEBUG] MCP server process exited with code ${code} and signal ${signal}`);
        stataOutputChannel.appendLine(`MCP server process exited with code ${code} and signal ${signal}`);
        if (code !== 0 && code !== null) {
                vscode.window.showErrorMessage(`MCP server exited with code ${code}`);
            }
            mcpServerRunning = false;
            updateStatusBar();
        });

        // Wait for the server to start
        let attempts = 0;
        const maxAttempts = 10;
        while (attempts < maxAttempts) {
            if (await isMcpServerRunning(host, port)) {
                mcpServerRunning = true;
                updateStatusBar();
            
            // Show success message
            const successMsg = `Stata MCP server is running on ${host}:${port}`;
            stataOutputChannel.appendLine(successMsg);
            vscode.window.showInformationMessage(successMsg);
            
            // Configure MCP for Cursor if enabled
            if (config.get('autoConfigureMcp')) {
                configureCursorMcp(host, port);
            }
            
            return;
        }
        
        // Wait before trying again
        await new Promise(resolve => setTimeout(resolve, 1000));
            attempts++;
        stataOutputChannel.appendLine(`Waiting for server to start... (attempt ${attempts}/${maxAttempts})`);
    }
    
    const errorMsg = 'Failed to start MCP server after multiple attempts.';
    stataOutputChannel.appendLine(errorMsg);
    vscode.window.showErrorMessage(errorMsg);
    
} catch (error) {
    console.error(`[DEBUG] Error starting MCP server: ${error.message}`);
    stataOutputChannel.appendLine(`Error starting MCP server: ${error.message}`);
    vscode.window.showErrorMessage(`Error starting MCP server: ${error.message}`);
}
}

// Check if MCP server is running
async function isMcpServerRunning(host, port) {
    return new Promise(resolve => {
        const socket = new net.Socket();
        
        // Set a timeout to handle connection issues
        socket.setTimeout(500);
        
        socket.on('connect', () => {
            socket.destroy();
            resolve(true);
        });
        
        socket.on('error', () => {
            socket.destroy();
            resolve(false);
        });
        
        socket.on('timeout', () => {
            socket.destroy();
            resolve(false);
        });
        
        socket.connect(port, host);
    });
}

// Configure Cursor MCP integration
function configureCursorMcp(host, port) {
    const homeDir = os.homedir();
    const mcpConfigDir = path.join(homeDir, '.cursor');
    const mcpConfigPath = path.join(mcpConfigDir, 'mcp.json');
    
    try {
        // Create the .cursor directory if it doesn't exist
        if (!fs.existsSync(mcpConfigDir)) {
            fs.mkdirSync(mcpConfigDir, { recursive: true });
        }
        
        // Check if config file exists, if not create it
        let mcpConfig = { mcpServers: {} };
        if (fs.existsSync(mcpConfigPath)) {
            try {
                const configContent = fs.readFileSync(mcpConfigPath, 'utf8');
                mcpConfig = JSON.parse(configContent);
                // Ensure mcpServers property exists
                mcpConfig.mcpServers = mcpConfig.mcpServers || {};
            } catch (error) {
                console.error(`[DEBUG] Error reading MCP config: ${error.message}`);
                mcpConfig = { mcpServers: {} };
            }
        }
        
        // Add or update the Stata server configuration
        mcpConfig.mcpServers["stata-mcp"] = {
            url: `http://${host}:${port}/mcp`,
            transport: "sse"
        };
        
        // Write the updated configuration
        fs.writeFileSync(mcpConfigPath, JSON.stringify(mcpConfig, null, 2), 'utf8');
        console.log(`[DEBUG] Updated MCP config at ${mcpConfigPath}`);
        stataOutputChannel.appendLine(`Updated MCP configuration at ${mcpConfigPath}`);
        
        // Skip workspace configuration to avoid cluttering user workspaces
        
        return true;
    } catch (error) {
        console.error(`[DEBUG] Error configuring Cursor MCP: ${error.message}`);
        stataOutputChannel.appendLine(`Error configuring Cursor MCP: ${error.message}`);
        vscode.window.showWarningMessage(`Failed to configure Cursor MCP: ${error.message}`);
        return false;
    }
}

// Execute selected Stata code
async function runSelection() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor');
        return;
    }
    
    const selection = editor.selection;
    let text;
    
    if (selection.isEmpty) {
        // If nothing is selected, use the current line
        const line = editor.document.lineAt(selection.active.line);
        text = line.text;
    } else {
        // Otherwise use the selected text
        text = editor.document.getText(selection);
    }
    
    if (!text.trim()) {
        vscode.window.showErrorMessage('No text selected or current line is empty');
        return;
    }
    
    // Execute the selected code
    await executeStataCode(text, 'run_selection');
}

// Execute a Stata .do file
async function runFile() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor');
        return;
    }

    const filePath = editor.document.uri.fsPath;
    
    // Check if it's a .do file
    if (!filePath.toLowerCase().endsWith('.do')) {
        vscode.window.showErrorMessage('Not a Stata .do file');
        return;
    }

    // Execute the file
    await executeStataFile(filePath);
}

// Execute Stata code using the MCP server
async function executeStataCode(code, toolName = 'run_command') {
    const config = vscode.workspace.getConfiguration('stata-vscode');
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;
    const debugMode = config.get('debugMode') || false;
    
    // Check if server is running
    if (!await isMcpServerRunning(host, port)) {
        // Try to start the server
        await startMcpServer();
        
        // Check again
        if (!await isMcpServerRunning(host, port)) {
            vscode.window.showErrorMessage('Failed to connect to MCP server');
            return;
        }
    }
    
    // Don't clear previous output anymore
    stataOutputChannel.show(true);
    
    if (debugMode) {
        stataOutputChannel.appendLine('Executing Stata code...');
        stataOutputChannel.appendLine('```');
        stataOutputChannel.appendLine(code);
        stataOutputChannel.appendLine('```');
        stataOutputChannel.appendLine('');
    }
    
    // Determine which parameter name to use based on the tool
    let paramName;
    switch (toolName) {
        case 'run_selection':
            paramName = 'selection';
            break;
        case 'run_command':
            paramName = 'command';
            break;
        default:
            paramName = 'command';
    }

    try {
        // Build the request body
        const requestBody = {
            tool: toolName,
            parameters: {
                [paramName]: code
            }
        };
        
        // Call the MCP server
        const response = await axios.post(
            `http://${host}:${port}/v1/tools`,
            requestBody,
            {
                headers: {
                    'Content-Type': 'application/json'
                },
                timeout: 30000 // 30 second timeout
            }
        );
        
        // Process the response
        if (response.status === 200) {
            const result = response.data;
            
            if (result.status === 'success') {
                // Extract the output content from the result
                const outputContent = result.result || 'Command executed successfully (no output)';
                
                // Show the result in the output channel
                if (debugMode) {
                    stataOutputChannel.appendLine('--- Output ---');
                }
                
                // Append the output to the channel
                if (stataOutputChannel.value && stataOutputChannel.value.trim().length > 0) {
                    // Add separator if there's existing content
                    stataOutputChannel.appendLine('\n----------------------------------------\n');
                }
                stataOutputChannel.appendLine(outputContent);
                stataOutputChannel.show(true);
                
                return outputContent;
            } else {
                // Show error in the output channel
                const errorMessage = result.message || 'Unknown error';
                stataOutputChannel.appendLine(`Error: ${errorMessage}`);
                stataOutputChannel.show(true);
                vscode.window.showErrorMessage(`Stata error: ${errorMessage}`);
                return null;
            }
        } else {
            const errorMessage = `HTTP error: ${response.status}`;
            stataOutputChannel.appendLine(errorMessage);
            stataOutputChannel.show(true);
            vscode.window.showErrorMessage(errorMessage);
            return null;
        }
    } catch (error) {
        console.error(`[DEBUG] Error executing Stata code: ${error.message}`);
        const errorMessage = `Error executing Stata code: ${error.message}`;
        stataOutputChannel.appendLine(errorMessage);
        if (debugMode) {
            stataOutputChannel.appendLine(`Full error: ${JSON.stringify(error)}`);
        }
        stataOutputChannel.show(true);
        vscode.window.showErrorMessage(errorMessage);
        return null;
    }
}

// Execute a Stata .do file
async function executeStataFile(filePath) {
    const config = vscode.workspace.getConfiguration('stata-vscode');
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;
    const debugMode = config.get('debugMode') || false;
    
    // Don't clear previous output anymore
    stataOutputChannel.show(true);
    
    if (debugMode) {
        stataOutputChannel.appendLine(`Executing Stata file: ${filePath}`);
        stataOutputChannel.appendLine('');
    }
    
    // Check if server is running
    if (!await isMcpServerRunning(host, port)) {
        // Try to start the server
        await startMcpServer();
        
        // Check again
        if (!await isMcpServerRunning(host, port)) {
            const errorMessage = 'Failed to connect to MCP server';
            stataOutputChannel.appendLine(errorMessage);
            stataOutputChannel.show(true);
            vscode.window.showErrorMessage(errorMessage);
            return;
        }
    }
    
    try {
        // Build the request body
        const requestBody = {
            tool: 'run_file',
            parameters: {
                file_path: filePath
            }
        };
        
        // Call the MCP server
        const response = await axios.post(
            `http://${host}:${port}/v1/tools`,
            requestBody,
            {
                headers: {
                    'Content-Type': 'application/json'
                },
                timeout: 60000 // 60 second timeout for files
            }
        );
        
        // Process the response
        if (response.status === 200) {
            const result = response.data;
            
            if (result.status === 'success') {
                // Extract the output content from the result
                const outputContent = result.result || 'File executed successfully (no output)';
                
                // Show the result in the output channel
                if (debugMode) {
                    stataOutputChannel.appendLine('--- Output ---');
                }
                
                // Append the output to the channel
                if (stataOutputChannel.value && stataOutputChannel.value.trim().length > 0) {
                    // Add separator if there's existing content
                    stataOutputChannel.appendLine('\n----------------------------------------\n');
                }
                stataOutputChannel.appendLine(outputContent);
                stataOutputChannel.show(true);
                
                return outputContent;
            } else {
                // Show error in the output channel
                const errorMessage = result.message || 'Unknown error';
                stataOutputChannel.appendLine(`Error: ${errorMessage}`);
                stataOutputChannel.show(true);
                vscode.window.showErrorMessage(`Error executing Stata file: ${errorMessage}`);
                return null;
            }
        } else {
            const errorMessage = `HTTP error: ${response.status}`;
            stataOutputChannel.appendLine(errorMessage);
            stataOutputChannel.show(true);
            vscode.window.showErrorMessage(errorMessage);
            return null;
        }
    } catch (error) {
        console.error(`[DEBUG] Error executing Stata file: ${error.message}`);
        const errorMessage = `Error executing Stata file: ${error.message}`;
        stataOutputChannel.appendLine(errorMessage);
        if (debugMode) {
            stataOutputChannel.appendLine(`Full error: ${JSON.stringify(error)}`);
        }
        stataOutputChannel.show(true);
        vscode.window.showErrorMessage(errorMessage);
        return null;
    }
}

// Show output in the output channel or webview
function showOutput(content) {
    // Only append content if it exists and isn't already shown
    if (content) {
        stataOutputChannel.append(content);
    }
    stataOutputChannel.show(true);
    
    // Only use webview if explicitly configured
    const config = vscode.workspace.getConfiguration('stata-vscode');
    const useWebview = config.get('alwaysUseWebview');
    
    if (useWebview) {
        showStataOutputWebview(content);
    }
}

// Show output in a webview
function showStataOutputWebview(content = null) {
    if (!stataOutputWebviewPanel) {
        // Create a new webview panel
        stataOutputWebviewPanel = vscode.window.createWebviewPanel(
            'stataOutput',
            'Stata Output',
            vscode.ViewColumn.Two,
            {
                enableScripts: true
            }
        );
        
        // Handle disposal
        stataOutputWebviewPanel.onDidDispose(
            () => {
                stataOutputWebviewPanel = null;
            },
            null,
            globalContext.subscriptions
        );
    }
    
    // Set webview content if provided
    if (content) {
        // Escape HTML characters in the content
        const htmlContent = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;')
            .replace(/\n/g, '<br>');
        
        // Set the HTML content
        stataOutputWebviewPanel.webview.html = `
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Stata Output</title>
                <style>
                    body {
                        font-family: 'Courier New', monospace;
                        white-space: pre-wrap;
                        padding: 10px;
                    }
                </style>
            </head>
            <body>
                ${htmlContent}
            </body>
            </html>
        `;
    }
    
    // Reveal the panel
    stataOutputWebviewPanel.reveal(vscode.ViewColumn.Two);
}

// Test the MCP server
async function testMcpServer() {
    const config = vscode.workspace.getConfiguration('stata-vscode');
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;
    
    try {
        // Test the server with a simple command
        const testCommand = "di \"Hello from Stata MCP Server!\"";
        const testResponse = await axios.post(
            `http://${host}:${port}/v1/tools`,
            {
                tool: "stata_run_selection",
                parameters: {
                    selection: testCommand
                }
            },
            {
                headers: {
                    'Content-Type': 'application/json'
                }
            }
        );
        
        // Check if we got a successful response
        if (testResponse.status === 200) {
            vscode.window.showInformationMessage(`MCP server is running properly`);
            
            // Extract and display the result
            let result = "No result returned";
            
            if (testResponse.data && typeof testResponse.data === 'object') {
                result = testResponse.data.result || "No result in response data";
            } else if (testResponse.data) {
                result = String(testResponse.data);
            }
            
            stataOutputChannel.appendLine('Test Command Result:');
            stataOutputChannel.appendLine(result);
            stataOutputChannel.show();
            
            return true;
        } else {
            vscode.window.showErrorMessage(`MCP server returned status: ${testResponse.status}`);
            return false;
        }
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to connect to MCP server: ${error.message}`);
        
        // Try to start the server
        const startServer = await vscode.window.showErrorMessage(
            'MCP server is not running. Do you want to start it?',
            'Yes', 'No'
        );
        
        if (startServer === 'Yes') {
            await startMcpServer();
        }
        
        return false;
    }
}

// Detect Stata path
async function detectStataPath() {
    // If we've already detected the path, return it
    if (detectedStataPath) {
        return detectedStataPath;
    }
    
    // Platform-specific paths to check
    const isWindows = process.platform === 'win32';
    const isMac = process.platform === 'darwin';
    const isLinux = !isWindows && !isMac;
    
    let possiblePaths = [];
    
    if (isWindows) {
        // Windows paths
        const programFiles = process.env.ProgramFiles || 'C:\\Program Files';
        const programFilesX86 = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)';
        
        possiblePaths = [
            path.join(programFiles, 'Stata18'),
            path.join(programFiles, 'Stata17'),
            path.join(programFiles, 'Stata16'),
            path.join(programFiles, 'Stata15'),
            path.join(programFilesX86, 'Stata18'),
            path.join(programFilesX86, 'Stata17'),
            path.join(programFilesX86, 'Stata16'),
            path.join(programFilesX86, 'Stata15')
        ];
    } else if (isMac) {
        // macOS paths
        possiblePaths = [
            '/Applications/Stata18',
            '/Applications/Stata17',
            '/Applications/Stata16',
            '/Applications/Stata15',
            '/Applications/Stata'
        ];
    } else if (isLinux) {
        // Linux paths
        possiblePaths = [
            '/usr/local/stata18',
            '/usr/local/stata17',
            '/usr/local/stata16',
            '/usr/local/stata15',
            '/usr/local/stata'
        ];
    }
    
    // Check each path
    for (const p of possiblePaths) {
        try {
            if (fs.existsSync(p)) {
                console.log(`[DEBUG] Found Stata at: ${p}`);
                detectedStataPath = p;
                return p;
            }
        } catch (error) {
            console.error(`[DEBUG] Error checking path ${p}: ${error.message}`);
        }
    }
    
    // If we couldn't find Stata, return null
    return null;
}

// Detect and update Stata path
async function detectAndUpdateStataPath() {
    const path = await detectStataPath();
    
    if (path) {
        const config = vscode.workspace.getConfiguration('stata-vscode');
        await config.update('stataPath', path, vscode.ConfigurationTarget.Global);
        vscode.window.showInformationMessage(`Stata path detected and set to: ${path}`);
        return path;
    } else {
        vscode.window.showErrorMessage('Could not detect Stata installation path. Please set it manually in settings.');
        vscode.commands.executeCommand('workbench.action.openSettings', 'stata-vscode.stataPath');
        return null;
    }
}

// Handle configuration changes
function handleConfigurationChange(event) {
    // Check if relevant settings were changed
    if (event.affectsConfiguration('stata-vscode.mcpServerPort') ||
        event.affectsConfiguration('stata-vscode.mcpServerHost') ||
        event.affectsConfiguration('stata-vscode.stataPath')) {
        
        // Restart the MCP server if it's running
        if (mcpServerRunning && mcpServerProcess) {
            mcpServerProcess.kill();
            mcpServerRunning = false;
            updateStatusBar();
            
            // Start the server again
            startMcpServer();
        }
    }
}

// Update status bar
function updateStatusBar() {
    if (mcpServerRunning) {
        statusBarItem.text = "$(beaker) Stata: Connected";
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    } else {
        statusBarItem.text = "$(beaker) Stata: Disconnected";
        statusBarItem.backgroundColor = undefined;
    }
}

// Check if active editor is a Stata file and update UI accordingly
function checkActiveEditorIsStata(editor) {
    // Skip if no editor is active
    if (!editor) {
        return;
    }
    
    // Check if current file is a Stata file
    const doc = editor.document;
    const isStataFile = doc.fileName.toLowerCase().endsWith('.do') || 
                       doc.fileName.toLowerCase().endsWith('.ado') || 
                       doc.fileName.toLowerCase().endsWith('.mata') || 
                       doc.languageId === 'stata';
    
    // Update UI based on file type
    if (isStataFile) {
        statusBarItem.show();
    } else {
        // Only hide if configured to do so
        const config = vscode.workspace.getConfiguration('stata-vscode');
        const alwaysShowStatusBar = config.get('alwaysShowStatusBar');
        
        if (!alwaysShowStatusBar) {
            statusBarItem.hide();
        }
    }
}

// Ask the Stata agent for help
async function askAgent() {
    // Create and show a webview panel for the agent
    if (!agentWebviewPanel) {
        agentWebviewPanel = vscode.window.createWebviewPanel(
            'stataAgent',
            'Stata Agent',
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true
            }
        );

        // Handle messages from the webview
        agentWebviewPanel.webview.onDidReceiveMessage(
            async message => {
                if (message.command === 'askAgent') {
                    const response = await getAgentResponse(message.text);
                    agentWebviewPanel.webview.postMessage({ command: 'agentResponse', text: response });
                } else if (message.command === 'runCode') {
                    await runStataCode(message.code);
                    agentWebviewPanel.webview.postMessage({ command: 'codeRun' });
                }
            },
            undefined,
            globalContext.subscriptions
        );

        // Handle panel disposal
        agentWebviewPanel.onDidDispose(
            () => {
                agentWebviewPanel = null;
            },
            null,
            globalContext.subscriptions
        );

        // Set the HTML content
        agentWebviewPanel.webview.html = getAgentWebviewContent();
    } else {
        agentWebviewPanel.reveal();
    }
}

// Get a response from the agent
async function getAgentResponse(query) {
    // In a real implementation, this would call an AI service
    // For now, we'll just return a simple response
    stataAgentChannel.appendLine(`User: ${query}`);
    
    // Simple pattern matching for demo purposes
    let response = '';
    if (query.toLowerCase().includes('help')) {
        response = 'I can help you with Stata commands and syntax. What would you like to know?';
    } else if (query.toLowerCase().includes('regression')) {
        response = 'To run a regression in Stata, you can use the `regress` command. For example:\n\n```\nregress y x1 x2 x3\n```';
    } else if (query.toLowerCase().includes('summarize') || query.toLowerCase().includes('summary')) {
        response = 'To get summary statistics in Stata, you can use the `summarize` command. For example:\n\n```\nsummarize x y z\n```';
    } else if (query.toLowerCase().includes('graph') || query.toLowerCase().includes('plot')) {
        response = 'To create graphs in Stata, you can use various graph commands. For example:\n\n```\ngraph twoway scatter y x\n```';
    } else {
        response = 'I\'m a simple Stata assistant. You can ask me about basic Stata commands, regression, summary statistics, or graphs.';
    }
    return response;
}

// Get the webview content for the agent
function getAgentWebviewContent() {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stata Agent</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        #conversation {
            flex-grow: 1;
            overflow-y: auto;
            border: 1px solid #ddd;
            padding: 10px;
            margin-bottom: 10px;
        }
        .user-message {
            background-color: #e6f7ff;
            padding: 8px 12px;
            border-radius: 12px;
            margin: 5px 0;
            max-width: 80%;
            align-self: flex-end;
        }
        .agent-message {
            background-color: #f0f0f0;
            padding: 8px 12px;
            border-radius: 12px;
            margin: 5px 0;
            max-width: 80%;
        }
        #input-area {
            display: flex;
        }
        #user-input {
            flex-grow: 1;
            padding: 10px;
            margin-right: 5px;
        }
        button {
            padding: 10px 15px;
            background-color: #0078d4;
            color: white;
            border: none;
            cursor: pointer;
        }
        button:hover {
            background-color: #005a9e;
        }
        pre {
            background-color: #f5f5f5;
            padding: 10px;
            border-radius: 5px;
            overflow-x: auto;
        }
        code {
            font-family: 'Courier New', monospace;
        }
    </style>
</head>
<body>
    <div id="conversation"></div>
    <div id="input-area">
        <input type="text" id="user-input" placeholder="Ask me about Stata...">
        <button id="send-button">Send</button>
    </div>
    <script>
        (function() {
            const vscode = acquireVsCodeApi();
            const conversation = document.getElementById('conversation');
            const userInput = document.getElementById('user-input');
            const sendButton = document.getElementById('send-button');
            
            // Add welcome message
            addAgentMessage('Hello! I am your Stata assistant. How can I help you today?');
            
            // Handle send button click
            sendButton.addEventListener('click', sendMessage);
            
            // Handle Enter key press
            userInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });
            
            // Handle messages from the extension
            window.addEventListener('message', event => {
                const message = event.data;
                
                switch (message.command) {
                    case 'agentResponse':
                        addAgentMessage(message.text);
                        break;
                    case 'codeRun':
                        addAgentMessage('Code executed in Stata.');
                        break;
                }
            });
            
            function sendMessage() {
                const text = userInput.value.trim();
                if (text) {
                    addUserMessage(text);
                    
                    // Send message to extension
                    vscode.postMessage({
                        command: 'askAgent',
                        text: text
                    });
                    
                    // Check if it's a code execution request
                    if (text.toLowerCase().startsWith('run:')) {
                        const code = text.substring(4).trim();
                        vscode.postMessage({
                            command: 'runCode',
                            code: code
                        });
                    }
                    
                    // Clear input
                    userInput.value = '';
                }
            }
            
            function addUserMessage(text) {
                const div = document.createElement('div');
                div.className = 'user-message';
                div.textContent = text;
                conversation.appendChild(div);
                conversation.scrollTop = conversation.scrollHeight;
            }
            
            function addAgentMessage(text) {
                const div = document.createElement('div');
                div.className = 'agent-message';
                
                // Handle markdown code blocks
                if (text.includes('\`\`\`')) {
                    const parts = text.split('\`\`\`');
                    for (let i = 0; i < parts.length; i++) {
                        if (i % 2 === 0) {
                            // Regular text
                            const textNode = document.createTextNode(parts[i]);
                            div.appendChild(textNode);
                        } else {
                            // Code block
                            const pre = document.createElement('pre');
                            const code = document.createElement('code');
                            code.textContent = parts[i];
                            pre.appendChild(code);
                            div.appendChild(pre);
                        }
                    }
                } else {
                    div.textContent = text;
                }
                
                conversation.appendChild(div);
                conversation.scrollTop = conversation.scrollHeight;
            }
        })();
    </script>
</body>
</html>`
}

// Function to run Stata code from the agent
async function runStataCode(code) {
    // Use the existing executeStataCode function
    return await executeStataCode(code, 'run_selection');
}

// Install Python dependencies
function installDependencies() {
    const extensionPath = globalContext.extensionPath;
    const installScriptPath = path.join(extensionPath, 'scripts', 'install-python-deps.js');
    
    stataOutputChannel.appendLine('Installing Python dependencies...');
    
    try {
        // Execute install script in a new process
        const installProcess = childProcess.fork(installScriptPath, [], {
            stdio: 'pipe',
            shell: true
        });
        
        // Handle stdout and stderr
        installProcess.stdout?.on('data', (data) => {
            stataOutputChannel.appendLine(`[Dependency Installer] ${data.toString().trim()}`);
        });
        
        installProcess.stderr?.on('data', (data) => {
            stataOutputChannel.appendLine(`[Dependency Installer Error] ${data.toString().trim()}`);
        });
        
        installProcess.on('exit', (code) => {
            if (code === 0) {
                stataOutputChannel.appendLine('Python dependencies installed successfully');
                vscode.window.showInformationMessage('Stata MCP server Python dependencies installed successfully.');
                
                // Kill existing server process if it exists
                if (mcpServerProcess) {
                    mcpServerProcess.kill();
                    mcpServerProcess = null;
                    mcpServerRunning = false;
                    updateStatusBar();
                }
                
                // Give a moment for the process to fully terminate
                setTimeout(() => {
                    stataOutputChannel.appendLine('Restarting MCP server with installed dependencies...');
                    // Start a new server process with the newly installed dependencies
                    startMcpServer();
                }, 1000);
            } else {
                stataOutputChannel.appendLine(`Failed to install Python dependencies. Exit code: ${code}`);
                vscode.window.showErrorMessage('Failed to install Python dependencies for Stata MCP server. Please check the output panel for details.');
            }
        });
        
        installProcess.on('error', (error) => {
            stataOutputChannel.appendLine(`Error installing Python dependencies: ${error.message}`);
            vscode.window.showErrorMessage(`Error installing Python dependencies: ${error.message}`);
        });
    } catch (error) {
        stataOutputChannel.appendLine(`Error running dependency installation script: ${error.message}`);
        vscode.window.showErrorMessage(`Error installing Python dependencies: ${error.message}`);
    }
}

// Auto-update the global Cursor MCP configuration file
function autoUpdateGlobalMcpConfig() {
    const config = vscode.workspace.getConfiguration('stata-vscode');
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;
    
    try {
        // Get the appropriate path for the global MCP config
        const homeDir = os.homedir();
        const mcpConfigDir = path.join(homeDir, '.cursor');
        const mcpConfigPath = path.join(mcpConfigDir, 'mcp.json');
        
        stataOutputChannel.appendLine(`Checking MCP configuration at ${mcpConfigPath}`);
        
        // Create the .cursor directory if it doesn't exist
        if (!fs.existsSync(mcpConfigDir)) {
            fs.mkdirSync(mcpConfigDir, { recursive: true });
            stataOutputChannel.appendLine(`Created directory: ${mcpConfigDir}`);
        }
        
        // Read existing config or create new one
        let mcpConfig = { mcpServers: {} };
        let configChanged = false;
        
        if (fs.existsSync(mcpConfigPath)) {
            try {
                const configContent = fs.readFileSync(mcpConfigPath, 'utf8');
                mcpConfig = JSON.parse(configContent);
                
                // Ensure mcpServers property exists
                mcpConfig.mcpServers = mcpConfig.mcpServers || {};
                
                // Check if stata-mcp exists and needs updating
                const currentConfig = mcpConfig.mcpServers["stata-mcp"];
                const correctUrl = `http://${host}:${port}/mcp`;
                
                if (!currentConfig || currentConfig.url !== correctUrl || currentConfig.transport !== "sse") {
                    stataOutputChannel.appendLine(`Updating stata-mcp configuration to ${correctUrl}`);
                    mcpConfig.mcpServers["stata-mcp"] = {
                        url: correctUrl,
                        transport: "sse"
                    };
                    configChanged = true;
                } else {
                    stataOutputChannel.appendLine(`stata-mcp configuration is already correct`);
                }
            } catch (error) {
                stataOutputChannel.appendLine(`Error reading MCP config: ${error.message}`);
                // Create a new config with just our server
                mcpConfig = { mcpServers: {} };
                mcpConfig.mcpServers["stata-mcp"] = {
                    url: `http://${host}:${port}/mcp`,
                    transport: "sse"
                };
                configChanged = true;
            }
        } else {
            // File doesn't exist, create new config
            stataOutputChannel.appendLine(`Creating new MCP configuration`);
            mcpConfig.mcpServers["stata-mcp"] = {
                url: `http://${host}:${port}/mcp`,
                transport: "sse"
            };
            configChanged = true;
        }
        
        // Write the updated configuration if changed
        if (configChanged) {
            fs.writeFileSync(mcpConfigPath, JSON.stringify(mcpConfig, null, 2), 'utf8');
            stataOutputChannel.appendLine(`Updated MCP configuration at ${mcpConfigPath}`);
        }
        
        return true;
    } catch (error) {
        stataOutputChannel.appendLine(`Error updating MCP config: ${error.message}`);
        console.error(`[DEBUG] Error updating MCP config: ${error.message}`);
        return false;
    }
}

module.exports = {
    activate,
    deactivate
};