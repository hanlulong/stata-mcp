const vscode = require('vscode');
const { exec, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const axios = require('axios');
const net = require('net');

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

    // Create output channels
    stataOutputChannel = vscode.window.createOutputChannel('Stata Output');
    stataAgentChannel = vscode.window.createOutputChannel('Stata Agent');
    
    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = "$(beaker) Stata";
    statusBarItem.tooltip = "Stata Integration";
    statusBarItem.command = 'stata-vscode.showOutput';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('stata-vscode.runSelection', runSelection),
        vscode.commands.registerCommand('stata-vscode.runFile', runFile),
        vscode.commands.registerCommand('stata-vscode.showOutput', showOutput),
        vscode.commands.registerCommand('stata-vscode.showOutputWebview', showStataOutputWebview),
        vscode.commands.registerCommand('stata-vscode.askAgent', askAgent),
        vscode.commands.registerCommand('stata-vscode.testMcpServer', testMcpServer),
        vscode.commands.registerCommand('stata-vscode.detectStataPath', detectAndUpdateStataPath),
        vscode.commands.registerCommand('stata-vscode.setupMcpServer', setupMcpServer),
        vscode.commands.registerCommand('stata-vscode.startMcpServer', startMcpServerCommand)
    );

    // Store context for later use
    globalContext = context;

    // Detect Stata path immediately
    detectStataPath().then(path => {
        if (path) {
            console.log(`[DEBUG] Detected Stata path: ${path}`);
            detectedStataPath = path;
            
            const config = vscode.workspace.getConfiguration('stata-vscode');
            const userPath = config.get('stataPath');
            
            // Only set the detected path if the user hasn't specified one
            if (!userPath) {
                config.update('stataPath', path, vscode.ConfigurationTarget.Global)
                    .then(() => {
                        console.log(`[DEBUG] Automatically set Stata path to: ${path}`);
                        stataOutputChannel.appendLine(`Detected Stata installation: ${path}`);
                        
                        // Setup and start MCP server after path is set
                        setupAndStartMcpServer();
                    });
            } else {
                // Setup and start MCP server with user-defined path
                setupAndStartMcpServer();
            }
        } else {
            // Prompt user to set Stata path
            vscode.window.showWarningMessage(
                'Stata path not detected. Please set it in settings.',
                'Open Settings'
            ).then(selection => {
                if (selection === 'Open Settings') {
                    vscode.commands.executeCommand('workbench.action.openSettings', 'stata-vscode.stataPath');
                }
            });
        }
    });

    // Register event handlers
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(handleConfigurationChange)
    );

    // Show welcome message
    stataOutputChannel.appendLine('Stata extension activated');
    stataOutputChannel.appendLine('Select Stata code and press Ctrl+Shift+Enter (Cmd+Shift+Enter on Mac) to execute');
}

// Function to setup and start MCP server
async function setupAndStartMcpServer() {
    try {
        // First setup the MCP server configuration
        await setupMcpServer();
        
        // Then start the MCP server
        await startMcpServer()
            .then(() => {
                console.log('[DEBUG] MCP server started successfully');
                
                // Test server connection
                testMcpServerConnection();
            })
            .catch(error => {
                console.error(`[DEBUG] Failed to start MCP server: ${error.message}`);
                vscode.window.showErrorMessage(`Failed to start MCP server: ${error.message}`, 'Retry').then(selection => {
                    if (selection === 'Retry') {
                        startMcpServer();
                    }
                });
            });
    } catch (error) {
        console.error(`[DEBUG] Error in setupAndStartMcpServer: ${error.message}`);
    }
}

// Command to manually start the MCP server
function startMcpServerCommand() {
    startMcpServer()
        .then(() => {
            vscode.window.showInformationMessage('Stata MCP server started successfully');
        })
        .catch(error => {
            vscode.window.showErrorMessage(`Failed to start MCP server: ${error.message}`);
        });
}

// Test if MCP server is responding correctly
async function testMcpServerConnection() {
    const config = vscode.workspace.getConfiguration('stata-vscode');
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 8000;
    
    try {
        // Use node-fetch or similar to test the health endpoint
        const http = require('http');
        const url = `http://${host}:${port}/health`;
        
        console.log(`[DEBUG] Testing MCP server connection at: ${url}`);
        
        // Simple HTTP GET request
        const request = http.get(url, (response) => {
            let data = '';
            response.on('data', (chunk) => {
                data += chunk;
            });
            
            response.on('end', () => {
                try {
                    const jsonData = JSON.parse(data);
                    console.log(`[DEBUG] MCP server health check response: ${JSON.stringify(jsonData)}`);
                    
                    if (jsonData.status === 'ok') {
                        console.log('[DEBUG] MCP server is running and responding correctly');
                        vscode.window.showInformationMessage('Stata MCP server is running');
                    } else {
                        console.log('[DEBUG] MCP server response indicates an issue');
                    }
                } catch (error) {
                    console.error(`[DEBUG] Error parsing MCP server response: ${error.message}`);
                }
            });
        });
        
        request.on('error', (error) => {
            console.error(`[DEBUG] Error connecting to MCP server: ${error.message}`);
        });
        
        request.end();
    } catch (error) {
        console.error(`[DEBUG] Error testing MCP server connection: ${error.message}`);
    }
}

function deactivate() {
    // Stop MCP server if it was started by the extension
    if (mcpServerProcess) {
        mcpServerProcess.kill();
        mcpServerRunning = false;
    }
}

// Register MCP protocol handlers for Stata services
function registerMcpServices(context) {
    console.log('[DEBUG] Registering MCP services for Stata');
    
    // Check if we're running in an environment that supports MCP
    const isMcpSupported = vscode.extensions.getExtension('cursor.cursor') || 
                          process.env.VSCODE_MCP || 
                          process.env.CODE_SERVER;
    
    if (!isMcpSupported) {
        console.log('[DEBUG] MCP not supported in this environment');
        return;
    }
    
    try {
        // Register the Stata service namespace
        const stataServiceNamespace = 'stata';
        
        // Get the configuration
        const config = vscode.workspace.getConfiguration('stata-vscode');
        const host = config.get('mcpServerHost') || 'localhost';
        const port = config.get('mcpServerPort') || 8000;
        
        // Explicitly set the MCP server URL to ensure it's using our Flask server
        const mcpServerUrl = `http://${host}:${port}/mcp`;
        console.log(`[DEBUG] Using MCP server URL: ${mcpServerUrl}`);
        
        // Register command handlers for various Stata operations
        context.subscriptions.push(
            vscode.commands.registerCommand(`mcp.${stataServiceNamespace}.run`, async (args) => {
                console.log(`[DEBUG] MCP stata.run called with args: ${JSON.stringify(args)}`);
                
                if (!args || !args.code) {
                    return { error: 'No code specified' };
                }
                
                try {
                    const result = await runStataCode(args.code);
                    return { result };
                } catch (error) {
                    console.error(`[DEBUG] Error running Stata code: ${error.message}`);
                    return { error: error.message };
                }
            }),
            
            vscode.commands.registerCommand(`mcp.${stataServiceNamespace}.status`, async () => {
                console.log(`[DEBUG] MCP stata.status called`);
                
                try {
                    const isRunning = await isMcpServerRunning(
                        vscode.workspace.getConfiguration('stata-vscode').get('mcpServerHost') || 'localhost',
                        vscode.workspace.getConfiguration('stata-vscode').get('mcpServerPort') || 8766
                    );
                    
                    return { 
                        serverRunning: mcpServerRunning, 
                        serverStatus: isRunning ? 'online' : 'offline',
                        stataPath: vscode.workspace.getConfiguration('stata-vscode').get('stataPath')
                    };
                } catch (error) {
                    console.error(`[DEBUG] Error getting Stata status: ${error.message}`);
                    return { error: error.message };
                }
            }),
            
            vscode.commands.registerCommand(`mcp.${stataServiceNamespace}.getData`, async () => {
                console.log(`[DEBUG] MCP stata.getData called`);
                
                try {
                    // Get current data from Stata by running a command to describe the data
                    const result = await runStataCode('describe');
                    return { result };
                } catch (error) {
                    console.error(`[DEBUG] Error getting Stata data: ${error.message}`);
                    return { error: error.message };
                }
            }),
            
            vscode.commands.registerCommand(`mcp.${stataServiceNamespace}.summarize`, async (args) => {
                console.log(`[DEBUG] MCP stata.summarize called with args: ${JSON.stringify(args)}`);
                
                try {
                    // Build the summarize command with optional variable names
                    let cmd = 'summarize';
                    if (args && args.variables) {
                        cmd += ` ${args.variables}`;
                    }
                    if (args && args.detail) {
                        cmd += ', detail';
                    }
                    
                    const result = await runStataCode(cmd);
                    return { result };
                } catch (error) {
                    console.error(`[DEBUG] Error summarizing data: ${error.message}`);
                    return { error: error.message };
                }
            }),
            
            vscode.commands.registerCommand(`mcp.${stataServiceNamespace}.regression`, async (args) => {
                console.log(`[DEBUG] MCP stata.regression called with args: ${JSON.stringify(args)}`);
                
                if (!args || !args.model || !args.dependent || !args.independent) {
                    return { error: 'Missing required parameters: model, dependent, independent' };
                }
                
                try {
                    // Build the regression command
                    const cmd = `${args.model} ${args.dependent} ${args.independent} ${args.options || ''}`;
                    const result = await runStataCode(cmd);
                    return { result };
                } catch (error) {
                    console.error(`[DEBUG] Error running regression: ${error.message}`);
                    return { error: error.message };
                }
            }),
            
            vscode.commands.registerCommand(`mcp.${stataServiceNamespace}.graph`, async (args) => {
                console.log(`[DEBUG] MCP stata.graph called with args: ${JSON.stringify(args)}`);
                
                if (!args || !args.type || !args.variables) {
                    return { error: 'Missing required parameters: type, variables' };
                }
                
                try {
                    // Build the graph command
                    const cmd = `graph ${args.type} ${args.variables} ${args.options || ''}`;
                    const result = await runStataCode(cmd);
                    return { result };
                } catch (error) {
                    console.error(`[DEBUG] Error creating graph: ${error.message}`);
                    return { error: error.message };
                }
            }),
            
            vscode.commands.registerCommand(`mcp.${stataServiceNamespace}.loadData`, async (args) => {
                console.log(`[DEBUG] MCP stata.loadData called with args: ${JSON.stringify(args)}`);
                
                if (!args || !args.filePath) {
                    return { error: 'Missing required parameter: filePath' };
                }
                
                try {
                    // Determine the file type and load it
                    const filePath = args.filePath;
                    let cmd = '';
                    
                    if (filePath.endsWith('.dta')) {
                        cmd = `use "${filePath}", clear`;
                    } else if (filePath.endsWith('.csv')) {
                        cmd = `import delimited "${filePath}", clear`;
                    } else if (filePath.endsWith('.xlsx') || filePath.endsWith('.xls')) {
                        cmd = `import excel "${filePath}", firstrow clear`;
                    } else {
                        return { error: 'Unsupported file type. Supported: .dta, .csv, .xlsx, .xls' };
                    }
                    
                    const result = await runStataCode(cmd);
                    return { result };
                } catch (error) {
                    console.error(`[DEBUG] Error loading data: ${error.message}`);
                    return { error: error.message };
                }
            })
        );
        
        // Add support for service discovery
        context.subscriptions.push(
            vscode.commands.registerCommand('mcp.getServices', () => {
                return {
                    [stataServiceNamespace]: {
                        version: '1.0.0',
                        commands: [
                            'run', 
                            'status', 
                            'getData', 
                            'summarize', 
                            'regression', 
                            'graph',
                            'load_data',
                            'describe'
                        ],
                        description: 'Stata integration services via MCP',
                        documentation: {
                            run: {
                                description: 'Execute arbitrary Stata code',
                                parameters: {
                                    code: 'String containing Stata commands to run'
                                },
                                example: 'mcp.stata.run({code: "generate x = rnormal()\nsummarize x"})'
                            },
                            status: {
                                description: 'Get the status of the Stata MCP server',
                                parameters: {},
                                example: 'mcp.stata.status()'
                            },
                            getData: {
                                description: 'Get information about the current dataset',
                                parameters: {},
                                example: 'mcp.stata.getData()'
                            },
                            summarize: {
                                description: 'Summarize variables in the current dataset',
                                parameters: {
                                    variables: '(Optional) Space-separated list of variables to summarize',
                                    detail: '(Optional) Boolean for detailed summary statistics'
                                },
                                example: 'mcp.stata.summarize({variables: "mpg weight price", detail: true})'
                            },
                            regression: {
                                description: 'Run a regression model',
                                parameters: {
                                    model: 'Regression model type (regress, logit, etc.)',
                                    dependent: 'Dependent variable',
                                    independent: 'Space-separated list of independent variables',
                                    options: '(Optional) Additional Stata options'
                                },
                                example: 'mcp.stata.regression({model: "regress", dependent: "price", independent: "mpg weight", options: ", robust"})'
                            },
                            graph: {
                                description: 'Create a graph',
                                parameters: {
                                    type: 'Graph type (scatter, histogram, etc.)',
                                    variables: 'Space-separated list of variables to graph',
                                    options: '(Optional) Additional Stata options'
                                },
                                example: 'mcp.stata.graph({type: "scatter", variables: "mpg weight", options: ", title(MPG vs Weight)"})'
                            },
                            loadData: {
                                description: 'Load data from a file',
                                parameters: {
                                    filePath: 'Path to the data file (.dta, .csv, .xlsx, or .xls)'
                                },
                                example: 'mcp.stata.loadData({filePath: "/path/to/data.dta"})'
                            },
                            describe: {
                                description: 'Describe the current dataset',
                                parameters: {},
                                example: 'mcp.stata.describe()'
                            }
                        },
                        mcpUrl: mcpServerUrl
                    }
                };
            })
        );
        
        console.log('[DEBUG] Successfully registered MCP services for Stata');
    } catch (error) {
        console.error(`[DEBUG] Error registering MCP services: ${error.message}`);
    }
}

// Start the MCP server if it's not already running
async function startMcpServer() {
    const config = vscode.workspace.getConfiguration('stata-vscode');
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 8000;  // Using port 8000 as default
    
    console.log(`[DEBUG] Starting MCP server on ${host}:${port}`);
    
    // Get Stata path from settings, or use detected path
    let stataPath = config.get('stataPath') || detectedStataPath;
    
    if (!stataPath) {
        stataPath = await detectStataPath();
        
        if (stataPath) {
            // Save the detected path to settings
            await config.update('stataPath', stataPath, vscode.ConfigurationTarget.Global);
            console.log(`[DEBUG] Updated Stata path in settings to: ${stataPath}`);
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

    // Check if server is already running
    try {
        if (await isMcpServerRunning(host, port)) {
            console.log(`[DEBUG] MCP server already running on ${host}:${port}`);
            mcpServerRunning = true;
            updateStatusBar();
            return;
        }
    } catch (error) {
        console.log(`[DEBUG] Error checking if MCP server is running: ${error.message}`);
        // Continue trying to start the server anyway
    }
    
    // Find the server script
    const serverScriptPath = await findServerScriptPath();
    
    if (!serverScriptPath) {
        vscode.window.showErrorMessage('Could not find the Stata MCP server script. Please check installation.');
        return;
    }
    
    console.log(`[DEBUG] Using server script at: ${serverScriptPath}`);
    
    try {
        // Start the MCP server
        const isWindows = process.platform === 'win32';
        const pythonCommand = isWindows ? 'python' : 'python3';
        
        // Build the command with arguments
        const args = [
            serverScriptPath,
            '--stata-path', stataPath,
            '--port', port.toString()
        ];
        
        console.log(`[DEBUG] Starting MCP server with command: ${pythonCommand} ${args.join(' ')}`);
        
        // Use spawn to start the server as a child process
        mcpServerProcess = spawn(pythonCommand, args, {
            detached: true,
            stdio: 'pipe'  // Capture stdout and stderr
        });
        
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
                const error = data.toString().trim();
                console.error(`[MCP Server Error] ${error}`);
                stataOutputChannel.appendLine(`[MCP Server Error] ${error}`);
            });
        }
        
        mcpServerProcess.on('error', (err) => {
            console.error(`[DEBUG] Failed to start MCP server: ${err.message}`);
            vscode.window.showErrorMessage(`Failed to start MCP server: ${err.message}`);
            mcpServerRunning = false;
            updateStatusBar();
        });
        
        mcpServerProcess.on('exit', (code, signal) => {
            console.log(`[DEBUG] MCP server process exited with code ${code} and signal ${signal}`);
            if (code !== 0 && code !== null) {
                vscode.window.showErrorMessage(`MCP server exited with code ${code}`);
            }
            mcpServerRunning = false;
            updateStatusBar();
        });
        
        // Wait for the server to start
        let attempts = 0;
        const maxAttempts = 20;  // More attempts with shorter wait time
        
        while (attempts < maxAttempts) {
            console.log(`[DEBUG] Checking if MCP server is running (attempt ${attempts + 1}/${maxAttempts})`);
            try {
                if (await isMcpServerRunning(host, port)) {
                    mcpServerRunning = true;
                    updateStatusBar();
                    console.log(`[DEBUG] MCP server is now running`);
                    
                    // Register MCP protocol handlers now that the server is running
                    registerMcpServices(globalContext);
                    
                    return;
                }
            } catch (error) {
                console.log(`[DEBUG] Error checking server: ${error.message}`);
            }
            await new Promise(resolve => setTimeout(resolve, 300));  // Shorter wait between attempts
            attempts++;
        }
        
        if (!mcpServerRunning) {
            console.log(`[DEBUG] Failed to start MCP server after ${maxAttempts} attempts`);
            vscode.window.showErrorMessage('Failed to start MCP server. Please check logs and try again.');
        }
    } catch (error) {
        console.log(`[DEBUG] Error starting MCP server: ${error.message}`);
        vscode.window.showErrorMessage(`Failed to start MCP server: ${error.message}`);
    }
}

// Find the MCP server script
async function findServerScriptPath() {
    // Try to find the server script in several locations
    const possibleLocations = [
        // Current extension directory
        path.join(__dirname, '..', 'stata_mcp_server.py'),
        
        // Parent of extension directory (for development)
        path.join(__dirname, '..', '..', 'stata_mcp_server.py'),
        
        // User home directory MCP folder
        path.join(os.homedir(), 'mcp', 'stata_mcp_server.py'),
        
        // Common Stata locations
        '/Applications/Stata/mcp/stata_mcp_server.py',
        'C:\\Program Files\\Stata17\\mcp\\stata_mcp_server.py',
        'C:\\Program Files\\Stata16\\mcp\\stata_mcp_server.py',
        
        // Current working directory (for development)
        path.join(process.cwd(), 'stata_mcp_server.py'),
        
        // Check the absolute extension path if available
        globalContext ? path.join(globalContext.extensionPath, 'stata_mcp_server.py') : null,
        
        // Check if in workspace
        vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0 ?
            path.join(vscode.workspace.workspaceFolders[0].uri.fsPath, 'stata_mcp_server.py') : null
    ].filter(Boolean); // Filter out null entries
    
    console.log('[DEBUG] Searching for server script in these locations:');
    for (const loc of possibleLocations) {
        console.log(`[DEBUG] - ${loc}`);
        try {
            if (fs.existsSync(loc)) {
                console.log(`[DEBUG] Found server script at: ${loc}`);
                return loc;
            }
        } catch (error) {
            // Ignore errors checking paths
        }
    }
    
    console.log('[DEBUG] Server script not found in any of the expected locations');
    return null;
}

// Check if the MCP server is running
async function isMcpServerRunning(host, port) {
    return new Promise(resolve => {
        const socket = new net.Socket();
        socket.setTimeout(500);
        
        socket.on('connect', () => {
            socket.destroy();
            resolve(true);
        });
        
        socket.on('error', () => {
            resolve(false);
        });
        
        socket.on('timeout', () => {
            socket.destroy();
            resolve(false);
        });
        
        socket.connect(port, host);
    });
}

// Update the status bar based on the MCP server status
function updateStatusBar() {
    if (mcpServerRunning) {
        statusBarItem.text = "$(check) Stata";
        statusBarItem.tooltip = "Stata Integration (MCP server running)";
    } else {
        statusBarItem.text = "$(error) Stata";
        statusBarItem.tooltip = "Stata Integration (MCP server not running)";
    }
}

// Handle configuration changes
function handleConfigurationChange(event) {
    if (event.affectsConfiguration('stata-vscode')) {
        // Restart MCP server if configuration changed
        if (mcpServerProcess) {
            mcpServerProcess.kill();
            mcpServerRunning = false;
        }
        startMcpServer();
    }
}

// Run the selected text or current line in Stata
async function runSelection() {
    console.log(`[DEBUG] runSelection called`);
    
    // Get the active editor
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        console.log(`[DEBUG] No active editor`);
        vscode.window.showErrorMessage('No active editor');
        return;
    }
    
    console.log(`[DEBUG] Active editor: ${editor.document.fileName}`);
    
    // Get the selected text or current line
    let text;
    if (editor.selection.isEmpty) {
        // No selection, get the current line
        const line = editor.document.lineAt(editor.selection.active.line);
        text = line.text;
        console.log(`[DEBUG] No selection, using current line: ${text}`);
    } else {
        // Get the selected text
        text = editor.document.getText(editor.selection);
        console.log(`[DEBUG] Selection found, length: ${text.length}`);
    }
    
    // Trim the text
    text = text.trim();
    
    // Check if there's any text to run
    if (!text) {
        console.log(`[DEBUG] No text to run`);
        vscode.window.showErrorMessage('No text to run');
        return;
    }
    
    // Show a notification about what's being run
    const displayText = text.length > 50 ? text.substring(0, 47) + '...' : text;
    vscode.window.showInformationMessage(`Running: ${displayText}`);
    
    // Run the code
    try {
        console.log(`[DEBUG] Running code: ${text}`);
        await runStataCode(text);
    } catch (error) {
        console.log(`[DEBUG] Error running code: ${error.message}`);
        vscode.window.showErrorMessage(`Error running code: ${error.message}`);
    }
}

// Run the entire file
async function runFile() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor');
        return;
    }

    const code = editor.document.getText();
    if (!code.trim()) {
        vscode.window.showErrorMessage('File is empty');
        return;
    }

    // Run the code
    await runStataCode(code);
}

// Run Stata code via the MCP server
async function runStataCode(code) {
    const config = vscode.workspace.getConfiguration('stata-vscode');
    const host = config.get('mcpServerHost');
    const port = config.get('mcpServerPort');
    const alwaysUseWebview = config.get('alwaysUseWebview');

    // Debug log
    console.log(`[DEBUG] Running Stata code: ${code}`);
    console.log(`[DEBUG] MCP server: ${host}:${port}, Server running: ${mcpServerRunning}`);
    console.log(`[DEBUG] Always use webview: ${alwaysUseWebview}, Is Cursor: ${isCursorEditor()}`);

    // Don't clear the output channel - preserve previous output
    // Instead, add a separator for new output
    stataOutputChannel.appendLine('\n' + '='.repeat(80) + '\n');
    
    // Force focus on the output panel
    vscode.commands.executeCommand('workbench.action.output.focus');

    if (!mcpServerRunning) {
        console.log(`[DEBUG] MCP server not running, prompting user to start it`);
        stataOutputChannel.appendLine('MCP server is not running. Attempting to start it...');
        
        try {
            await startMcpServer();
            if (!mcpServerRunning) {
                console.log(`[DEBUG] Failed to start MCP server`);
                stataOutputChannel.appendLine('Failed to start MCP server. Please start it manually.');
                return;
            }
            console.log(`[DEBUG] MCP server started successfully`);
            stataOutputChannel.appendLine('MCP server started successfully.');
        } catch (error) {
            console.log(`[DEBUG] Error starting MCP server: ${error.message}`);
            stataOutputChannel.appendLine(`Error starting MCP server: ${error.message}`);
            return;
        }
    }

    try {
        // First check if Stata is initialized
        const statusResponse = await sendToMcpServer(host, port, 'status');
        console.log(`[DEBUG] Stata status: ${JSON.stringify(statusResponse)}`);
        
        if (statusResponse.stata_status && statusResponse.stata_status.initialized === false) {
            console.log(`[DEBUG] Stata is not initialized, attempting to initialize`);
            stataOutputChannel.appendLine('Stata is not initialized. Attempting to initialize...');
            
            // Try to initialize Stata with the init command
            const initResponse = await sendToMcpServer(host, port, 'init', { edition: 'MP', splash: false });
            console.log(`[DEBUG] Init response: ${JSON.stringify(initResponse)}`);
            
            if (initResponse.status === 'ok') {
                stataOutputChannel.appendLine('Stata initialized successfully.');
            } else {
                stataOutputChannel.appendLine(`Failed to initialize Stata: ${initResponse.message || 'Unknown error'}`);
                // Try to continue anyway with a simple command
                stataOutputChannel.appendLine('Trying with a simple command instead...');
                await sendToMcpServer(host, port, 'run', { cmd: 'clear all' });
            }
        }
        
        // Send the code to the MCP server
        stataOutputChannel.appendLine('Executing Stata command...');
        const response = await sendToMcpServer(host, port, 'run', { cmd: code });
        
        // Debug log
        console.log(`[DEBUG] Received response from MCP server: ${JSON.stringify(response)}`);
        
        if (response.status === 'ok') {
            // Format the output for better readability
            const formattedOutput = formatStataOutput(response.output || 'Command executed successfully');
            
            // Only display the result without additional headers
            stataOutputChannel.appendLine(formattedOutput);
            
            // Show a notification
            vscode.window.showInformationMessage('Stata command executed successfully. Output is in the Output panel.', 'Show Output')
                .then(selection => {
                    if (selection === 'Show Output') {
                        stataOutputChannel.show(true);
                        vscode.commands.executeCommand('workbench.action.output.focus');
                    }
                });
            
            // Always make sure the output is visible
            stataOutputChannel.show(true);
            vscode.commands.executeCommand('workbench.action.output.focus');
            
            return {
                status: 'ok',
                output: response.output,
                result: response.result
            };
        } else {
            console.log(`[DEBUG] Error response from MCP server: ${JSON.stringify(response)}`);
            stataOutputChannel.appendLine(`ERROR: ${response.message || 'Unknown error'}`);
            vscode.window.showErrorMessage(`Stata error: ${response.message || 'Unknown error'}`);
            
            // Always show the output channel for errors
            stataOutputChannel.show(true);
            vscode.commands.executeCommand('workbench.action.output.focus');
            
            return {
                status: 'error',
                message: response.message
            };
        }
    } catch (error) {
        console.log(`[DEBUG] Exception in runStataCode: ${error.message}`);
        console.log(`[DEBUG] Error stack: ${error.stack}`);
        stataOutputChannel.appendLine(`ERROR: ${error.message}`);
        stataOutputChannel.appendLine(`Stack: ${error.stack}`);
        vscode.window.showErrorMessage(`Error running Stata code: ${error.message}`);
        
        // Always show the output channel for errors
        stataOutputChannel.show(true);
        vscode.commands.executeCommand('workbench.action.output.focus');
        
        return {
            status: 'error',
            message: error.message
        };
    }
}

// Format Stata output for better readability
function formatStataOutput(output) {
    if (!output) return '';
    
    console.log(`[DEBUG] Formatting output: ${output.substring(0, 100)}...`);
    
    // Split by lines and preserve formatting
    const lines = output.split('\n');
    
    // Track if we're in a table section
    let inTable = false;
    
    // Process each line
    const formattedLines = lines.map(line => {
        // Detect table headers or separators
        if (line.includes('|') || line.includes('+')) {
            inTable = true;
            // Make table borders more visible
            return line.replace(/\+/g, '┼')
                      .replace(/-/g, '─')
                      .replace(/\|/g, '│');
        }
        
        // Reset table detection if we hit an empty line after a table
        if (inTable && line.trim() === '') {
            inTable = false;
        }
        
        // Highlight errors (but preserve everything else)
        if (line.toLowerCase().includes('error') || line.includes('r(')) {
            return `! ${line}`;
        }
        
        // Keep everything else as-is
        return line;
    });
    
    const formattedOutput = formattedLines.join('\n');
    console.log(`[DEBUG] Formatted output length: ${formattedOutput.length}`);
    return formattedOutput;
}

// Send a request to the MCP server
async function sendToMcpServer(host, port, command, args = {}) {
    const request = {
        command,
        args
    };

    try {
        console.log(`[DEBUG] Making HTTP request to ${host}:${port}/api`);
        
        const response = await axios.post(`http://${host}:${port}/api`, request, {
            headers: { 'Content-Type': 'application/json' },
            timeout: 30000
        });
        
        console.log(`[DEBUG] HTTP response status: ${response.status}`);
        console.log(`[DEBUG] HTTP response data: ${JSON.stringify(response.data)}`);
        
        return response.data;
    } catch (error) {
        console.log(`[DEBUG] HTTP request error: ${error.message}`);
        
        if (error.response) {
            console.log(`[DEBUG] Error response: ${error.response.status} ${error.response.statusText}`);
            throw new Error(`Server error: ${error.response.status} ${error.response.statusText}`);
        } else if (error.request) {
            console.log(`[DEBUG] No response received`);
            throw new Error('No response from server. Make sure the MCP server is running.');
        } else {
            console.log(`[DEBUG] Request setup error: ${error.message}`);
            throw new Error(`Error: ${error.message}`);
        }
    }
}

// Show the Stata output channel
function showOutput() {
    console.log(`[DEBUG] showOutput called`);
    
    // SUPER AGGRESSIVE OUTPUT CHANNEL SHOWING
    stataOutputChannel.show(true);
    vscode.commands.executeCommand('workbench.action.output.focus');
    
    // Try to select the Stata Output channel in the dropdown
    try {
        console.log(`[DEBUG] Trying to select Stata Output channel`);
        vscode.commands.executeCommand('workbench.action.output.show.stata');
    } catch (error) {
        console.log(`[DEBUG] Error selecting Stata Output channel: ${error.message}`);
    }
    
    // Show a notification to help the user find the output
    vscode.window.showInformationMessage(
        'Stata output is in the Output panel. Look for "Stata Output" in the dropdown menu.',
        { modal: true },
        'OK'
    );
    
    // Force focus on the output channel multiple times with increasing delays
    [100, 500, 1000, 2000].forEach(delay => {
        setTimeout(() => {
            console.log(`[DEBUG] Forcing output channel focus after ${delay}ms`);
            stataOutputChannel.show(true);
            vscode.commands.executeCommand('workbench.action.output.focus');
        }, delay);
    });
    
    // Create a direct link to the output in the status bar
    const outputButton = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 1000);
    outputButton.text = "$(output) Stata Output";
    outputButton.tooltip = "Click to show Stata output";
    outputButton.command = 'stata-vscode.showOutput';
    outputButton.show();
    
    // Dispose of the button after 30 seconds
    setTimeout(() => {
        outputButton.dispose();
    }, 30000);
}

// Check if we're running in Cursor editor
function isCursorEditor() {
    const appName = vscode.env.appName || '';
    return appName.toLowerCase().includes('cursor');
}

// Show Stata output in a webview panel (more reliable in Cursor)
function showStataOutputWebview() {
    // Get the current output content
    const outputContent = stataOutputChannel.toString();
    
    // Debug log
    console.log(`[DEBUG] showStataOutputWebview called with content length: ${outputContent.length}`);
    console.log(`[DEBUG] First 100 chars of output: ${outputContent.substring(0, 100)}`);
    
    // Show a notification that we're about to display output
    vscode.window.showInformationMessage('Displaying Stata output in webview...');
    
    // Create and show a webview panel for the output
    if (!stataOutputWebviewPanel) {
        console.log(`[DEBUG] Creating new webview panel for Stata output`);
        
        // Try to create the webview in the most visible location
        stataOutputWebviewPanel = vscode.window.createWebviewPanel(
            'stataOutput',
            'Stata Output',
            {
                viewColumn: vscode.ViewColumn.Beside, 
                preserveFocus: false
            },
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: []
            }
        );
        
        // Handle messages from the webview
        stataOutputWebviewPanel.webview.onDidReceiveMessage(
            message => {
                console.log(`[DEBUG] Received message from webview: ${JSON.stringify(message)}`);
                if (message.command === 'refresh') {
                    // Update the webview with the latest output
                    const latestOutput = stataOutputChannel.toString();
                    console.log(`[DEBUG] Refreshing webview with latest output length: ${latestOutput.length}`);
                    
                    const formattedOutput = latestOutput.replace(/\n/g, '<br>')
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/"/g, '&quot;')
                        .replace(/'/g, '&#039;');
                    
                    stataOutputWebviewPanel.webview.postMessage({
                        command: 'update',
                        content: formattedOutput || 'No output available. Run some Stata code to see results here.'
                    });
                    console.log(`[DEBUG] Sent update message to webview`);
                }
            },
            undefined,
            globalContext.subscriptions
        );
        
        // Handle panel disposal
        stataOutputWebviewPanel.onDidDispose(
            () => {
                console.log(`[DEBUG] Stata output webview panel disposed`);
                stataOutputWebviewPanel = null;
            },
            null,
            globalContext.subscriptions
        );
    } else {
        console.log(`[DEBUG] Revealing existing webview panel`);
        // Make sure it's visible and focused
        stataOutputWebviewPanel.reveal(undefined, true);
    }
    
    // Set the HTML content
    console.log(`[DEBUG] Setting HTML content for webview`);
    stataOutputWebviewPanel.webview.html = getStataOutputWebviewContent(outputContent);
    console.log(`[DEBUG] Webview HTML content set`);
    
    // Force the webview to be visible
    forceWebviewVisibility();
    
    // Return a promise that resolves when the webview is ready
    return new Promise(resolve => {
        setTimeout(() => {
            console.log(`[DEBUG] Webview should now be visible`);
            resolve();
        }, 1000);
    });
}

// Force the webview to be visible
function forceWebviewVisibility() {
    if (stataOutputWebviewPanel) {
        console.log(`[DEBUG] Forcing webview visibility`);
        
        // Reveal the panel and focus it
        stataOutputWebviewPanel.reveal(vscode.ViewColumn.Beside, false);
        
        // Try multiple reveals with increasing delays
        const revealTimes = [100, 500, 1000, 2000];
        
        revealTimes.forEach((delay, index) => {
            setTimeout(() => {
                if (stataOutputWebviewPanel) {
                    console.log(`[DEBUG] Re-revealing webview panel after ${delay}ms delay (attempt ${index + 1})`);
                    stataOutputWebviewPanel.reveal(vscode.ViewColumn.Beside, false);
                    
                    // On the last attempt, show a more prominent notification
                    if (index === revealTimes.length - 1) {
                        vscode.window.showInformationMessage(
                            'Stata output is available. Click to view it.',
                            { modal: true },
                            'Show Output'
                        ).then(selection => {
                            if (selection === 'Show Output' && stataOutputWebviewPanel) {
                                console.log(`[DEBUG] User clicked to focus on output panel from modal`);
                                stataOutputWebviewPanel.reveal(vscode.ViewColumn.Beside, false);
                            }
                        });
                    }
                }
            }, delay);
        });
        
        // Also show a notification immediately
        vscode.window.showInformationMessage(
            'Stata output is available in a separate panel. Click to focus on it.',
            'Show Output'
        ).then(selection => {
            if (selection === 'Show Output' && stataOutputWebviewPanel) {
                console.log(`[DEBUG] User clicked to focus on output panel`);
                stataOutputWebviewPanel.reveal(vscode.ViewColumn.Beside, false);
            }
        });
    }
}

// Get the HTML content for the Stata output webview
function getStataOutputWebviewContent(outputContent) {
    // Escape HTML special characters
    const escapedOutput = outputContent
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    
    // Convert line breaks to <br> tags
    const formattedOutput = escapedOutput.replace(/\n/g, '<br>');
    
    // Add timestamp for debugging
    const timestamp = new Date().toISOString();
    
    // Check if there's actual content
    const hasContent = outputContent.trim().length > 0;
    
    return `<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Stata Output</title>
        <style>
            body {
                font-family: 'Courier New', Courier, monospace;
                padding: 20px;
                white-space: pre-wrap;
                color: var(--vscode-editor-foreground);
                background-color: var(--vscode-editor-background);
                margin: 0;
            }
            .header {
                position: sticky;
                top: 0;
                background-color: var(--vscode-editor-background);
                padding: 10px 0;
                border-bottom: 1px solid var(--vscode-panel-border);
                display: flex;
                justify-content: space-between;
                align-items: center;
                z-index: 10;
            }
            .title {
                font-weight: bold;
                font-size: 16px;
                color: var(--vscode-editor-foreground);
            }
            .timestamp {
                font-size: 12px;
                color: var(--vscode-descriptionForeground);
            }
            .output-container {
                border: 1px solid var(--vscode-panel-border);
                padding: 15px;
                border-radius: 4px;
                overflow: auto;
                margin-top: 10px;
                background-color: var(--vscode-editor-background);
                min-height: 200px;
                max-height: 80vh;
            }
            .refresh-button {
                padding: 5px 10px;
                background-color: var(--vscode-button-background);
                color: var(--vscode-button-foreground);
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-weight: bold;
            }
            .refresh-button:hover {
                background-color: var(--vscode-button-hoverBackground);
            }
            .notification {
                background-color: #5cb85c;
                color: white;
                padding: 10px;
                margin: 10px 0;
                border-radius: 4px;
                text-align: center;
                animation: fadeOut 5s forwards;
                display: none;
            }
            @keyframes fadeOut {
                0% { opacity: 1; }
                70% { opacity: 1; }
                100% { opacity: 0; }
            }
            .section-header {
                font-weight: bold;
                margin-top: 10px;
                margin-bottom: 5px;
                color: var(--vscode-editor-foreground);
                border-bottom: 1px solid var(--vscode-panel-border);
                padding-bottom: 3px;
            }
            .no-content {
                color: #888;
                font-style: italic;
                text-align: center;
                margin-top: 50px;
            }
            .has-content {
                color: #5cb85c;
                font-weight: bold;
                text-align: center;
                margin: 10px 0;
                padding: 5px;
                border-radius: 4px;
                background-color: rgba(92, 184, 92, 0.1);
            }
            .content-indicator {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                margin-right: 5px;
                background-color: ${hasContent ? '#5cb85c' : '#888'};
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="title">
                <span class="content-indicator"></span>
                Stata Output
            </div>
            <div class="timestamp">Last updated: ${timestamp}</div>
            <button class="refresh-button" onclick="refreshOutput()">Refresh Output</button>
        </div>
        
        <div id="notification" class="notification">
            Output updated!
        </div>
        
        ${hasContent ? '<div class="has-content">Output available</div>' : ''}
        
        <div class="output-container">
            ${formattedOutput || '<div class="no-content">No output available. Run some Stata code to see results here.</div>'}
        </div>
        
        <script>
            const vscode = acquireVsCodeApi();
            
            function refreshOutput() {
                vscode.postMessage({
                    command: 'refresh'
                });
            }
            
            // Listen for messages from the extension
            window.addEventListener('message', event => {
                const message = event.data;
                if (message.command === 'update') {
                    document.querySelector('.output-container').innerHTML = message.content;
                    document.querySelector('.timestamp').textContent = 'Last updated: ' + new Date().toISOString();
                    
                    // Show notification
                    const notification = document.getElementById('notification');
                    notification.style.display = 'block';
                    setTimeout(() => {
                        notification.style.display = 'none';
                    }, 5000);
                    
                    // Update content indicator
                    const hasContent = message.content && message.content.trim() !== 'No output available. Run some Stata code to see results here.';
                    document.querySelector('.content-indicator').style.backgroundColor = hasContent ? '#5cb85c' : '#888';
                    
                    // Update content indicator message
                    const contentIndicator = document.querySelector('.has-content');
                    if (hasContent && !contentIndicator) {
                        const indicator = document.createElement('div');
                        indicator.className = 'has-content';
                        indicator.textContent = 'Output available';
                        document.querySelector('.header').insertAdjacentElement('afterend', indicator);
                    } else if (!hasContent && contentIndicator) {
                        contentIndicator.remove();
                    }
                }
            });
            
            // Auto-refresh every 5 seconds
            setInterval(refreshOutput, 5000);
            
            // Initial refresh
            setTimeout(refreshOutput, 1000);
            
            // Notify the extension that the webview is ready
            vscode.postMessage({
                command: 'webviewReady'
            });
        </script>
    </body>
    </html>`;
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
        response = 'To run a regression in Stata, you can use the `regress` command. For example:\n\n```\nregress y x1 x2 x3\n```\n\nWould you like me to run this code for you?';
    } else if (query.toLowerCase().includes('graph')) {
        response = 'Stata has powerful graphing capabilities. You can create graphs using the `graph` command. For example:\n\n```\ngraph twoway scatter y x\n```\n\nWould you like me to run this code for you?';
    } else {
        response = 'I\'m not sure how to help with that specific query. Could you provide more details or ask about a specific Stata command?';
    }
    
    stataAgentChannel.appendLine(`Agent: ${response}`);
    return response;
}

// Get the HTML content for the agent webview
function getAgentWebviewContent() {
    return `<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Stata Agent</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                padding: 0;
                margin: 0;
                color: var(--vscode-editor-foreground);
                background-color: var(--vscode-editor-background);
            }
            .container {
                display: flex;
                flex-direction: column;
                height: 100vh;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
            .chat-container {
                flex: 1;
                overflow-y: auto;
                margin-bottom: 20px;
                border: 1px solid var(--vscode-panel-border);
                border-radius: 4px;
                padding: 10px;
            }
            .message {
                margin-bottom: 10px;
                padding: 8px 12px;
                border-radius: 4px;
                max-width: 80%;
            }
            .user-message {
                background-color: var(--vscode-button-background);
                color: var(--vscode-button-foreground);
                align-self: flex-end;
                margin-left: auto;
            }
            .agent-message {
                background-color: var(--vscode-editor-inactiveSelectionBackground);
                color: var(--vscode-editor-foreground);
            }
            .input-container {
                display: flex;
            }
            #user-input {
                flex: 1;
                padding: 8px;
                border: 1px solid var(--vscode-input-border);
                background-color: var(--vscode-input-background);
                color: var(--vscode-input-foreground);
                border-radius: 4px;
            }
            button {
                margin-left: 10px;
                padding: 8px 16px;
                background-color: var(--vscode-button-background);
                color: var(--vscode-button-foreground);
                border: none;
                border-radius: 4px;
                cursor: pointer;
            }
            button:hover {
                background-color: var(--vscode-button-hoverBackground);
            }
            pre {
                background-color: var(--vscode-textCodeBlock-background);
                padding: 10px;
                border-radius: 4px;
                overflow-x: auto;
            }
            code {
                font-family: 'Courier New', Courier, monospace;
            }
            .code-block {
                position: relative;
            }
            .run-code-button {
                position: absolute;
                top: 5px;
                right: 5px;
                padding: 2px 8px;
                font-size: 12px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="chat-container" id="chat-container">
                <div class="message agent-message">
                    Hello! I'm your Stata assistant. How can I help you today?
                </div>
            </div>
            <div class="input-container">
                <input type="text" id="user-input" placeholder="Ask a question about Stata...">
                <button id="send-button">Send</button>
            </div>
        </div>

        <script>
            const vscode = acquireVsCodeApi();
            const chatContainer = document.getElementById('chat-container');
            const userInput = document.getElementById('user-input');
            const sendButton = document.getElementById('send-button');

            // Send message when button is clicked
            sendButton.addEventListener('click', sendMessage);

            // Send message when Enter key is pressed
            userInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });

            // Function to send message to extension
            function sendMessage() {
                const text = userInput.value.trim();
                if (!text) return;

                // Add user message to chat
                addMessage(text, 'user');
                
                // Clear input
                userInput.value = '';
                
                // Send message to extension
                vscode.postMessage({
                    command: 'askAgent',
                    text: text
                });
            }

            // Function to add message to chat
            function addMessage(text, sender) {
                const messageDiv = document.createElement('div');
                messageDiv.className = \`message \${sender}-message\`;
                
                // Process markdown-like code blocks
                let processedText = text;
                if (sender === 'agent') {
                    const codeBlockRegex = /\`\`\`(.*?)\n([\s\S]*?)\`\`\`/g;
                    processedText = text.replace(codeBlockRegex, (match, language, code) => {
                        return \`<div class="code-block">
                            <button class="run-code-button">Run</button>
                            <pre><code>\${code}</code></pre>
                        </div>\`;
                    });
                }
                
                messageDiv.innerHTML = processedText;
                chatContainer.appendChild(messageDiv);
                
                // Add event listeners to run code buttons
                if (sender === 'agent') {
                    const runButtons = messageDiv.querySelectorAll('.run-code-button');
                    runButtons.forEach(button => {
                        button.addEventListener('click', (e) => {
                            const codeBlock = e.target.nextElementSibling;
                            const code = codeBlock.textContent;
                            vscode.postMessage({
                                command: 'runCode',
                                code: code
                            });
                        });
                    });
                }
                
                // Scroll to bottom
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }

            // Handle messages from the extension
            window.addEventListener('message', event => {
                const message = event.data;
                
                switch (message.command) {
                    case 'agentResponse':
                        addMessage(message.text, 'agent');
                        break;
                    case 'codeRun':
                        addMessage('Code has been executed. Check the Stata Output panel for results.', 'agent');
                        break;
                }
            });
        </script>
    </body>
    </html>`;
}

// Test the MCP server connection
async function testMcpServer() {
    const config = vscode.workspace.getConfiguration('stata-vscode');
    const host = config.get('mcpServerHost');
    const port = config.get('mcpServerPort');
    
    console.log(`[DEBUG] Testing MCP server connection to ${host}:${port}`);
    
    // Clear the output channel
    stataOutputChannel.clear();
    
    // Add a minimal header
    stataOutputChannel.appendLine(`=== TESTING MCP SERVER CONNECTION ===`);
    
    // Always show the output channel first
    stataOutputChannel.show(true);
    vscode.commands.executeCommand('workbench.action.output.focus');
    
    // Show a notification that we're testing
    vscode.window.showInformationMessage('Testing MCP server connection...');
    
    // Check if server is running
    stataOutputChannel.appendLine(`Checking if MCP server is running...`);
    const isRunning = await isMcpServerRunning(host, port);
    stataOutputChannel.appendLine(`Server running: ${isRunning ? 'YES ✓' : 'NO ✗'}`);
    console.log(`[DEBUG] MCP server running: ${isRunning}`);
    
    if (!isRunning) {
        const errorMessage = `MCP server is not running. Please start it manually.`;
        stataOutputChannel.appendLine(`\n❌ ERROR: ${errorMessage}`);
        stataOutputChannel.appendLine(`\nTo start the server, run:`);
        stataOutputChannel.appendLine(`cd /Applications/Stata/stata-vscode-extension && python3 mcp_server.py`);
        
        // Show the output
        stataOutputChannel.show(true);
        vscode.commands.executeCommand('workbench.action.output.focus');
        
        return;
    }
    
    // Try running a simple Stata command
    stataOutputChannel.appendLine(`\nRunning test command...`);
    
    try {
        // Run a simple command
        const testCommand = 'display "Hello from Stata!"';
        stataOutputChannel.appendLine(`Command: ${testCommand}`);
        
        // Send the command to the server
        const url = `http://${host}:${port}/api`;
        console.log(`[DEBUG] Sending command to ${url}`);
        
        const response = await axios.post(url, {
            command: 'run',
            args: {
                cmd: testCommand,
                quietly: false
            }
        });
        
        console.log(`[DEBUG] Response from MCP server: ${JSON.stringify(response.data)}`);
        
        // Check the response
        if (response.data.status === 'ok') {
            stataOutputChannel.appendLine(`\n=== STATA RESULT ===`);
            stataOutputChannel.appendLine(response.data.result || 'No result');
            stataOutputChannel.appendLine(`\n✅ TEST PASSED: MCP server is working correctly.`);
            
            // Show a success notification
            vscode.window.showInformationMessage('MCP server test passed! Server is working correctly.', 'View Details').then(selection => {
                if (selection === 'View Details') {
                    stataOutputChannel.show(true);
                    vscode.commands.executeCommand('workbench.action.output.focus');
                }
            });
        } else {
            stataOutputChannel.appendLine(`\n❌ ERROR: ${response.data.message || 'Unknown error'}`);
            stataOutputChannel.appendLine(`\n❌ TEST FAILED: MCP server returned an error.`);
            
            // Show an error notification
            vscode.window.showErrorMessage('MCP server test failed! Server returned an error.', 'View Details').then(selection => {
                if (selection === 'View Details') {
                    stataOutputChannel.show(true);
                    vscode.commands.executeCommand('workbench.action.output.focus');
                }
            });
        }
    } catch (error) {
        stataOutputChannel.appendLine(`\n❌ ERROR: ${error.message}`);
        stataOutputChannel.appendLine(`\n❌ TEST FAILED: Could not communicate with MCP server.`);
        console.log(`[DEBUG] Test error: ${error.message}`);
        console.log(`[DEBUG] Test error stack: ${error.stack}`);
        
        // Show an error notification
        vscode.window.showErrorMessage('MCP server test failed! Could not communicate with MCP server.', 'View Details').then(selection => {
            if (selection === 'View Details') {
                stataOutputChannel.show(true);
                vscode.commands.executeCommand('workbench.action.output.focus');
            }
        });
    }
    
    // Always show in output channel, especially in Cursor
    stataOutputChannel.show(true);
    vscode.commands.executeCommand('workbench.action.output.focus');
}

// Detect Stata path automatically
async function detectStataPath() {
    console.log(`[DEBUG] Detecting Stata path...`);
    
    // If we already detected it, return the cached path
    if (detectedStataPath) {
        return detectedStataPath;
    }
    
    const isWindows = process.platform === 'win32';
    const isMac = process.platform === 'darwin';
    
    let potentialPaths = [];
    
    if (isWindows) {
        // Common Stata installation paths on Windows
        potentialPaths = [
            'C:\\Program Files\\Stata18',
            'C:\\Program Files\\Stata17',
            'C:\\Program Files\\Stata16',
            'C:\\Program Files\\Stata15',
            'C:\\Program Files\\Stata',
            'C:\\Program Files (x86)\\Stata18',
            'C:\\Program Files (x86)\\Stata17',
            'C:\\Program Files (x86)\\Stata16',
            'C:\\Program Files (x86)\\Stata15',
            'C:\\Program Files (x86)\\Stata'
        ];
    } else if (isMac) {
        // Common Stata installation paths on Mac
        potentialPaths = [
            '/Applications/Stata',
            '/Applications/StataNow.app',
            '/Applications/Stata18.app',
            '/Applications/Stata17.app',
            '/Applications/Stata16.app',
            '/Applications/Stata15.app',
            '/Applications/Stata/StataMP.app',
            '/Applications/Stata/StataSE.app',
            '/Applications/Stata/StataBE.app'
        ];
    }
    
    console.log(`[DEBUG] Checking these potential Stata paths: ${potentialPaths.join(', ')}`);
    
    // Check each path
    for (const path of potentialPaths) {
        try {
            const exists = await fileExists(path);
            console.log(`[DEBUG] Checking path: ${path}, exists: ${exists}`);
            
            if (exists) {
                // Found Stata!
                detectedStataPath = path;
                console.log(`[DEBUG] Found Stata at: ${path}`);
                return path;
            }
        } catch (error) {
            console.log(`[DEBUG] Error checking path ${path}: ${error.message}`);
        }
    }
    
    console.log('[DEBUG] Stata path not detected automatically');
    return null;
}

// Command to detect and update Stata path
async function detectAndUpdateStataPath() {
    const path = await detectStataPath();
    
    if (path) {
        // Found Stata path
        vscode.window.showInformationMessage(`Stata detected at: ${path}`, 'Update Settings', 'Cancel')
            .then(selection => {
                if (selection === 'Update Settings') {
                    const config = vscode.workspace.getConfiguration('stata-vscode');
                    config.update('stataPath', path, vscode.ConfigurationTarget.Global)
                        .then(() => {
                            vscode.window.showInformationMessage(`Stata path updated to: ${path}`);
                        });
                }
            });
    } else {
        // Prompt user to manually specify path
        vscode.window.showErrorMessage(
            'Could not detect Stata automatically. Please specify the path in settings.',
            'Open Settings'
        ).then(selection => {
            if (selection === 'Open Settings') {
                vscode.commands.executeCommand('workbench.action.openSettings', 'stata-vscode.stataPath');
            }
        });
    }
}

// Helper function to check if a file/directory exists
async function fileExists(path) {
    try {
        await fs.promises.access(path, fs.constants.F_OK);
        return true;
    } catch (error) {
        return false;
    }
}

// Set up the MCP server configuration
async function setupMcpServer() {
    try {
        console.log('[DEBUG] Setting up MCP server configuration');
        
        // Get the extension path
        let extensionPath;
        try {
            // Try with the exact name from package.json
            const extension = vscode.extensions.getExtension('stata-vscode-extension');
            if (extension) {
                extensionPath = extension.extensionPath;
            } else {
                // Try with all available extensions
                const extensions = vscode.extensions.all;
                const stataExtension = extensions.find(ext => 
                    ext.id.toLowerCase().includes('stata') || 
                    (ext.packageJSON && ext.packageJSON.name && ext.packageJSON.name.toLowerCase().includes('stata'))
                );
                
                if (stataExtension) {
                    extensionPath = stataExtension.extensionPath;
                    console.log(`[DEBUG] Found Stata extension with ID: ${stataExtension.id}`);
                } else {
                    extensionPath = __dirname;
                    console.log(`[DEBUG] Using current directory as extension path: ${extensionPath}`);
                }
            }
        } catch (error) {
            console.log(`[DEBUG] Error getting extension path: ${error.message}`);
            extensionPath = __dirname;
        }
        
        console.log(`[DEBUG] Using extension path: ${extensionPath}`);
        
        // Get the path to the MCP server script
        const mcpServerPath = path.join(extensionPath, 'stata_mcp_server.py');

        // If the MCP server script doesn't exist in the extension directory, look for it in the parent directory
        if (!fs.existsSync(mcpServerPath)) {
            console.log(`[DEBUG] Source server file not found at ${mcpServerPath}`);
            
            // Look for it in other locations
            const alternateLocations = [
                path.join(extensionPath, '..', 'stata_mcp_server.py'),
                path.join(process.cwd(), 'stata_mcp_server.py')
            ];
            
            for (const loc of alternateLocations) {
                if (fs.existsSync(loc)) {
                    console.log(`[DEBUG] Found server file at alternate location: ${loc}`);
                    // Set this as the source path
                    mcpServerPath = loc;
                    break;
                }
            }
            
            if (!fs.existsSync(mcpServerPath)) {
                console.log(`[DEBUG] Server file not found in any location`);
                return;
            }
        }
        
        // Create target directory if it doesn't exist
        if (!fs.existsSync(path.join(os.homedir(), 'mcp'))) {
            console.log(`[DEBUG] Creating directory: ${path.join(os.homedir(), 'mcp')}`);
            fs.mkdirSync(path.join(os.homedir(), 'mcp'), { recursive: true });
        }
        
        // Copy the server file if it doesn't exist or is older than the source
        let shouldCopy = false;
        
        if (!fs.existsSync(path.join(os.homedir(), 'mcp', 'stata_mcp_server.py'))) {
            console.log(`[DEBUG] Target server file doesn't exist, copying`);
            shouldCopy = true;
        } else {
            const sourceStats = fs.statSync(mcpServerPath);
            const targetStats = fs.statSync(path.join(os.homedir(), 'mcp', 'stata_mcp_server.py'));
            
            if (sourceStats.mtime > targetStats.mtime) {
                console.log(`[DEBUG] Source file is newer, copying`);
                shouldCopy = true;
            }
        }
        
        if (shouldCopy) {
            console.log(`[DEBUG] Copying server file from ${mcpServerPath} to ${path.join(os.homedir(), 'mcp', 'stata_mcp_server.py')}`);
            fs.copyFileSync(mcpServerPath, path.join(os.homedir(), 'mcp', 'stata_mcp_server.py'));
            
            // Make the target file executable
            try {
                const isWindows = process.platform === 'win32';
                if (!isWindows) {
                    console.log(`[DEBUG] Making target file executable`);
                    fs.chmodSync(path.join(os.homedir(), 'mcp', 'stata_mcp_server.py'), '755');
                }
            } catch (error) {
                console.log(`[DEBUG] Error making file executable: ${error.message}`);
            }
        }
        
        // Update configuration if needed
        const config = vscode.workspace.getConfiguration('stata-vscode');
        const currentMcpPath = config.get('mcpServerPath');
        
        if (!currentMcpPath || currentMcpPath !== path.join(os.homedir(), 'mcp', 'stata_mcp_server.py')) {
            console.log(`[DEBUG] Updating MCP server path in settings to ${path.join(os.homedir(), 'mcp', 'stata_mcp_server.py')}`);
            await config.update('mcpServerPath', path.join(os.homedir(), 'mcp', 'stata_mcp_server.py'), vscode.ConfigurationTarget.Global);
        }
        
        console.log('[DEBUG] MCP server configuration completed successfully');
    } catch (error) {
        console.error(`[DEBUG] Error setting up MCP server configuration: ${error.message}`);
    }
}

module.exports = {
    activate,
    deactivate
}; 