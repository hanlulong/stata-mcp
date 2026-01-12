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
let debugMode = false;

// Execution tracking for stop functionality
let isExecuting = false;
let currentExecutionFile = null;
let currentStreamAbortController = null;  // AbortController for active stream

// Configuration cache
let configCache = null;
let configCacheTime = 0;
const CONFIG_CACHE_TTL = 5000; // 5 seconds

// Platform detection (cache once)
const IS_WINDOWS = process.platform === 'win32';
const IS_MAC = process.platform === 'darwin';
const IS_LINUX = !IS_WINDOWS && !IS_MAC;

// File path constants
const FILE_PATHS = {
    PYTHON_PATH: '.python-path',
    PYTHON_PATH_BACKUP: '.python-path.backup',
    SETUP_IN_PROGRESS: '.setup-in-progress',
    SETUP_ERROR: '.setup-error',
    SETUP_COMPLETE: '.setup-complete',
    UV_PATH: '.uv-path',
    LOG_FILE: 'stata_mcp_server.log'
};

// Configuration getter with caching
function getConfig() {
    const now = Date.now();
    if (!configCache || (now - configCacheTime) > CONFIG_CACHE_TTL) {
        configCache = vscode.workspace.getConfiguration('stata-vscode');
        configCacheTime = now;
    }
    return configCache;
}

// Centralized logging utilities
const Logger = {
    info: (message) => {
        stataOutputChannel.appendLine(message);
        if (debugMode) console.log(`[DEBUG] ${message}`);
    },
    error: (message) => {
        stataOutputChannel.appendLine(message);
        console.error(`[ERROR] ${message}`);
    },
    debug: (message) => {
        if (debugMode) {
            stataOutputChannel.appendLine(`[DEBUG] ${message}`);
            console.log(`[DEBUG] ${message}`);
        }
    },
    mcpServer: (message) => {
        const output = message.toString().trim();
        // Skip empty output
        if (!output) return;
        // Show output without prefix
        stataOutputChannel.appendLine(output);
        console.log(output);
    },
    mcpServerError: (message) => {
        const output = message.toString().trim();
        // Filter out Java initialization messages (informational, not errors)
        if (output.includes('Picked up _JAVA_OPTIONS') ||
            output.includes('Picked up JAVA_TOOL_OPTIONS')) {
            // Silently ignore Java options messages
            return;
        }
        stataOutputChannel.appendLine(`[MCP Server Error] ${output}`);
        console.error(`[MCP Server Error] ${output}`);
    }
};

// File path utilities
const FileUtils = {
    getExtensionFilePath: (filename) => {
        const extensionPath = globalContext.extensionPath || __dirname;
        return path.join(extensionPath, filename);
    },
    
    checkFileExists: (filePath) => {
        try {
            return fs.existsSync(filePath);
        } catch (error) {
            Logger.error(`Error checking file ${filePath}: ${error.message}`);
            return false;
        }
    },
    
    readFileContent: (filePath) => {
        try {
            return fs.readFileSync(filePath, 'utf8').trim();
        } catch (error) {
            Logger.error(`Error reading file ${filePath}: ${error.message}`);
            return null;
        }
    },
    
    writeFileContent: (filePath, content) => {
        try {
            fs.writeFileSync(filePath, content);
            return true;
        } catch (error) {
            Logger.error(`Error writing file ${filePath}: ${error.message}`);
            return false;
        }
    }
};

// Error handling utilities
const ErrorHandler = {
    pythonNotFound: () => {
        const pyMsg = IS_WINDOWS 
            ? "Python not found. Please install Python 3.11 from python.org and add it to your PATH."
            : "Python not found. Please install Python 3.11.";
        Logger.error(pyMsg);
        vscode.window.showErrorMessage(pyMsg);
    },
    
    serverStartFailed: (error) => {
        Logger.error(`Failed to start MCP server: ${error.message}`);
        if (error.code === 'ENOENT') {
            ErrorHandler.pythonNotFound();
        } else {
            vscode.window.showErrorMessage(`Failed to start MCP server: ${error.message}`);
        }
    },
    
    serverExited: (code, signal) => {
        Logger.info(`MCP server process exited with code ${code} and signal ${signal}`);
        if (code !== 0 && code !== null) {
            vscode.window.showErrorMessage(`MCP server exited with code ${code}`);
        }
        mcpServerRunning = false;
        updateStatusBar();
    }
};

// Python environment utilities
const PythonUtils = {
    getSystemPythonCommand: () => IS_WINDOWS ? 'py' : 'python3',
    
    getVenvPythonPath: () => {
        const extensionPath = globalContext.extensionPath || __dirname;
        return IS_WINDOWS 
            ? path.join(extensionPath, '.venv', 'Scripts', 'python.exe')
            : path.join(extensionPath, '.venv', 'bin', 'python');
    },
    
    getPythonCommand: () => {
        const pythonPathFile = FileUtils.getExtensionFilePath(FILE_PATHS.PYTHON_PATH);
        const backupPythonPathFile = FileUtils.getExtensionFilePath(FILE_PATHS.PYTHON_PATH_BACKUP);
        
        // Check primary Python path file
        if (FileUtils.checkFileExists(pythonPathFile)) {
            const pythonCommand = FileUtils.readFileContent(pythonPathFile);
            if (pythonCommand && FileUtils.checkFileExists(pythonCommand)) {
                Logger.debug(`Using virtual environment Python: ${pythonCommand}`);
                return pythonCommand;
            }
            Logger.debug(`Python path ${pythonCommand} does not exist`);
            
            // Try backup path
            if (FileUtils.checkFileExists(backupPythonPathFile)) {
                const backupCommand = FileUtils.readFileContent(backupPythonPathFile);
                if (backupCommand && FileUtils.checkFileExists(backupCommand)) {
                    Logger.debug(`Using backup Python path: ${backupCommand}`);
                    return backupCommand;
                }
            }
        }
        
        // Fall back to system Python
        return PythonUtils.getSystemPythonCommand();
    }
};

// Server utilities
const ServerUtils = {
    async isPortInUse(port) {
        return new Promise((resolve) => {
            const server = net.createServer();
            server.listen(port, () => {
                server.once('close', () => resolve(false));
                server.close();
            });
            server.on('error', () => resolve(true));
        });
    },
    
    async killProcessOnPort(port) {
        try {
            if (IS_WINDOWS) {
                try {
                    await exec(`FOR /F "tokens=5" %P IN ('netstat -ano ^| findstr :${port} ^| findstr LISTENING') DO taskkill /F /PID %P`);
                    Logger.info(`Killed existing server process. Waiting for port to be released...`);
                } catch (error) {
                    if (error.code === 1 && error.cmd && error.cmd.includes('findstr')) {
                        Logger.info(`No existing process found on port ${port}`);
                    } else {
                        Logger.error(`Error killing existing server: ${error.message}`);
                    }
                }
            } else {
                try {
                    await exec(`lsof -t -i:${port} | xargs -r kill -9`);
                    Logger.info(`Killed existing server process. Waiting for port to be released...`);
                } catch (error) {
                    Logger.info(`No existing process found on port ${port}`);
                }
            }
            // Wait for port to be released
            await new Promise(resolve => setTimeout(resolve, 5000));
        } catch (error) {
            Logger.error(`Error in port cleanup: ${error.message}`);
        }
    }
};

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    console.log('Stata extension activated');
    globalContext = context;
    
    // Get debug mode from settings
    const config = getConfig();
    debugMode = config.get('debugMode') || false;

    // Create output channels (don't show on startup to avoid stealing focus from terminal)
    stataOutputChannel = vscode.window.createOutputChannel('Stata');
    Logger.info('Stata extension activated.');
    
    stataAgentChannel = vscode.window.createOutputChannel('Stata Agent');
    
    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = "$(beaker) Stata";
    statusBarItem.tooltip = "Stata Integration";
    statusBarItem.command = 'stata-vscode.showOutput';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    Logger.info(`Extension path: ${context.extensionPath || __dirname}`);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('stata-vscode.runSelection', runSelection),
        vscode.commands.registerCommand('stata-vscode.runFile', runFile),
        vscode.commands.registerCommand('stata-vscode.stopExecution', stopExecution),
        vscode.commands.registerCommand('stata-vscode.showInteractive', runInteractive),
        vscode.commands.registerCommand('stata-vscode.showOutput', showOutput),
        vscode.commands.registerCommand('stata-vscode.showOutputWebview', showStataOutputWebview),
        vscode.commands.registerCommand('stata-vscode.testMcpServer', testMcpServer),
        vscode.commands.registerCommand('stata-vscode.detectStataPath', detectAndUpdateStataPath),
        vscode.commands.registerCommand('stata-vscode.askAgent', askAgent),
        vscode.commands.registerCommand('stata-vscode.viewData', viewStataData)
    );

    // Auto-detect Stata path
    detectStataPath().then(path => {
        if (path) {
            const userPath = config.get('stataPath');
            if (!userPath) {
                config.update('stataPath', path, vscode.ConfigurationTarget.Global)
                    .then(() => {
                        Logger.debug(`Automatically set Stata path to: ${path}`);
                        Logger.info(`Detected Stata installation: ${path}`);
                    });
            }
        }
    });

    // Register event handlers
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(handleConfigurationChange),
        vscode.window.onDidChangeActiveTextEditor(checkActiveEditorIsStata)
    );

    checkActiveEditorIsStata(vscode.window.activeTextEditor);
    
    // Check Python dependencies
    const pythonPathFile = FileUtils.getExtensionFilePath(FILE_PATHS.PYTHON_PATH);
    if (!FileUtils.checkFileExists(pythonPathFile)) {
        // Show output panel during first-time setup and steal focus so user sees installation progress
        stataOutputChannel.show(false);
        Logger.info('Setting up Python dependencies during extension activation...');
        installDependencies();
    } else {
        // Check if auto-start is enabled (default: true)
        const autoStartServer = config.get('autoStartServer') !== false;
        if (autoStartServer) {
            startMcpServer();
        } else {
            Logger.info('Auto-start server is disabled. Server will start on first Stata command.');
            updateStatusBar();
        }
    }
}

function deactivate() {
    if (mcpServerProcess) {
        mcpServerProcess.kill();
        mcpServerRunning = false;
    }
}

// Clear configuration cache when settings change
function handleConfigurationChange(event) {
    if (event.affectsConfiguration('stata-vscode')) {
        configCache = null; // Clear cache
        
        // Update debug mode setting
        const config = getConfig();
        const newDebugMode = config.get('debugMode') || false;
        const debugModeChanged = newDebugMode !== debugMode;
        debugMode = newDebugMode;
        
        if (debugModeChanged) {
            Logger.info(`Debug mode ${debugMode ? 'enabled' : 'disabled'}`);
        }
        
        // Settings that require server restart
        if (event.affectsConfiguration('stata-vscode.mcpServerPort') ||
            event.affectsConfiguration('stata-vscode.mcpServerHost') ||
            event.affectsConfiguration('stata-vscode.stataPath') ||
            event.affectsConfiguration('stata-vscode.debugMode') ||
            event.affectsConfiguration('stata-vscode.stataEdition') ||
            event.affectsConfiguration('stata-vscode.logFileLocation') ||
            event.affectsConfiguration('stata-vscode.customLogDirectory') ||
            event.affectsConfiguration('stata-vscode.resultDisplayMode') ||
            event.affectsConfiguration('stata-vscode.maxOutputTokens') ||
            event.affectsConfiguration('stata-vscode.multiSession') ||
            event.affectsConfiguration('stata-vscode.maxSessions') ||
            event.affectsConfiguration('stata-vscode.sessionTimeout')) {

            if (mcpServerRunning && mcpServerProcess) {
                Logger.info('Configuration changed, restarting MCP server...');
                mcpServerProcess.kill();
                mcpServerRunning = false;
                updateStatusBar();
                startMcpServer();
            }
        }
    }
}

// Update status bar
function updateStatusBar(state = null) {
    // State can be: null (auto-detect), 'running', 'stopping'
    if (state === 'running' || (state === null && isExecuting)) {
        statusBarItem.text = "$(sync~spin) Stata: Running...";
        statusBarItem.tooltip = `Executing: ${currentExecutionFile || 'command'}\nClick to stop`;
        statusBarItem.command = 'stata-vscode.stopExecution';
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    } else if (state === 'stopping') {
        statusBarItem.text = "$(sync~spin) Stata: Stopping...";
        statusBarItem.tooltip = "Stopping execution...";
        statusBarItem.command = undefined;
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    } else if (mcpServerRunning) {
        statusBarItem.text = "$(beaker) Stata: Connected";
        statusBarItem.tooltip = "Stata MCP Server is connected";
        statusBarItem.command = 'stata-vscode.showOutput';
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    } else {
        statusBarItem.text = "$(beaker) Stata: Disconnected";
        statusBarItem.tooltip = "Stata MCP Server is not connected";
        statusBarItem.command = 'stata-vscode.showOutput';
        statusBarItem.backgroundColor = undefined;
    }
}

// Check if active editor is a Stata file
function checkActiveEditorIsStata(editor) {
    if (!editor) return;
    
    const doc = editor.document;
    const isStataFile = doc.fileName.toLowerCase().endsWith('.do') || 
                       doc.fileName.toLowerCase().endsWith('.ado') || 
                       doc.fileName.toLowerCase().endsWith('.mata') || 
                       doc.languageId === 'stata';
    
    if (isStataFile) {
        statusBarItem.show();
    } else {
        const config = getConfig();
        const alwaysShowStatusBar = config.get('alwaysShowStatusBar');
        if (!alwaysShowStatusBar) {
            statusBarItem.hide();
        }
    }
}

// Install Python dependencies
function installDependencies() {
    const checkPythonScriptPath = FileUtils.getExtensionFilePath('src/check-python.js');
    Logger.info('Setting up Python environment...');
    
    try {
        const installProcess = childProcess.fork(checkPythonScriptPath, [], {
            stdio: 'pipe',
            shell: true
        });
        
        installProcess.stdout?.on('data', (data) => {
            Logger.info(`[Python Setup] ${data.toString().trim()}`);
        });
        
        installProcess.stderr?.on('data', (data) => {
            Logger.error(`[Python Setup Error] ${data.toString().trim()}`);
        });
        
        installProcess.on('exit', (code) => {
            if (code === 0) {
                Logger.info('Python environment setup successfully');
                vscode.window.showInformationMessage('Stata MCP server Python environment setup successfully.');
                
                if (mcpServerProcess) {
                    mcpServerProcess.kill();
                    mcpServerProcess = null;
                    mcpServerRunning = false;
                    updateStatusBar();
                }
                
                setTimeout(() => {
                    Logger.info('Starting MCP server with configured Python environment...');
                    startMcpServer();
                }, 3000);
            } else {
                Logger.error(`Failed to set up Python environment. Exit code: ${code}`);
                vscode.window.showErrorMessage('Failed to set up Python environment for Stata MCP server. Please check the output panel for details.');
            }
        });
        
        installProcess.on('error', (error) => {
            Logger.error(`Error setting up Python environment: ${error.message}`);
            vscode.window.showErrorMessage(`Error setting up Python environment: ${error.message}`);
        });
    } catch (error) {
        Logger.error(`Error running Python setup script: ${error.message}`);
        vscode.window.showErrorMessage(`Error setting up Python environment: ${error.message}`);
    }
}

// Simplified stub functions for the remaining functionality
// (These would contain the remaining logic from the original file, 
// but using the new utilities and avoiding redundancy)

async function startMcpServer() {
    const config = getConfig();
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;
    const forcePort = config.get('forcePort') || false;

    // Get Stata path and edition
    let stataPath = config.get('stataPath');
    const stataEdition = config.get('stataEdition') || 'mp';
    const logFileLocation = config.get('logFileLocation') || 'extension';
    const customLogDirectory = config.get('customLogDirectory') || '';
    const resultDisplayMode = config.get('resultDisplayMode') || 'compact';
    const maxOutputTokens = config.get('maxOutputTokens') || 10000;
    const multiSession = config.get('multiSession') !== false;  // Default to true
    const maxSessions = config.get('maxSessions') || 100;
    const sessionTimeout = config.get('sessionTimeout') || 3600;

    Logger.info(`Using Stata edition: ${stataEdition}`);
    Logger.info(`Log file location: ${logFileLocation}`);
    Logger.info(`Result display mode: ${resultDisplayMode}`);
    Logger.info(`Max output tokens: ${maxOutputTokens}`);
    Logger.info(`Multi-session mode: ${multiSession ? 'enabled' : 'disabled'}`);
    if (multiSession) {
        Logger.info(`Max sessions: ${maxSessions}`);
        Logger.info(`Session timeout: ${sessionTimeout}s`);
    }
    
    if (!stataPath) {
        stataPath = await detectStataPath();
        if (stataPath) {
            await config.update('stataPath', stataPath, vscode.ConfigurationTarget.Global);
        } else {
            const result = await vscode.window.showErrorMessage(
                'Stata path not set. The extension needs to know where Stata is installed.',
                'Detect Automatically', 'Set Manually'
            );
            
            if (result === 'Detect Automatically') {
                await detectAndUpdateStataPath();
                stataPath = config.get('stataPath');
            } else if (result === 'Set Manually') {
                vscode.commands.executeCommand('workbench.action.openSettings', 'stata-vscode.stataPath');
            }
            
            if (!stataPath) {
                vscode.window.showErrorMessage('Stata path is required for the extension to work.');
                return;
            }
        }
    }
    
    Logger.info(`Using Stata path: ${stataPath}`);

    // Check server health
    let serverHealthy = false;
    let stataInitialized = false;
    
    try {
        const healthResponse = await axios.get(`http://${host}:${port}/health`, { timeout: 1000 });
        if (healthResponse.status === 200) {
            serverHealthy = true;
            if (healthResponse.data && healthResponse.data.stata_available === true) {
                stataInitialized = true;
                Logger.debug(`Server reports Stata as available, initialization confirmed`);
            } else {
                Logger.info(`Server reports Stata as unavailable`);
                Logger.debug(`Server reports Stata as unavailable`);
            }
        }
    } catch (error) {
        serverHealthy = false;
        // Debug only - this is called repeatedly during startup polling
        Logger.debug(`Server health check failed: ${error.message}`);
    }
    
    if (serverHealthy && stataInitialized) {
        Logger.info(`MCP server already running on ${host}:${port} with Stata initialized`);
        mcpServerRunning = true;
        updateStatusBar();

        // Server is already running - don't reveal output panel to keep terminal visible
        // Logs are written and viewable via "Stata: Show Output" command
        return;
    }

    if (serverHealthy && !stataInitialized) {
        Logger.info(`Server is running but Stata is not properly initialized. Forcing restart...`);
        await ServerUtils.killProcessOnPort(port);
    }

    // If server is not healthy, check if port is in use and kill any existing process
    // This handles the case where a previous server didn't shut down properly
    if (!serverHealthy) {
        const portInUse = await ServerUtils.isPortInUse(port);
        if (portInUse) {
            Logger.info(`Port ${port} is in use but server is not responding. Killing existing process...`);
            await ServerUtils.killProcessOnPort(port);
            // Wait a moment for the port to be released
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
    }

    // Don't reveal output panel during startup to keep terminal visible
    // Logs are written and viewable via "Stata: Show Output" command

    try {
        const extensionPath = globalContext.extensionPath || __dirname;
        Logger.info(`Extension path: ${extensionPath}`);
        
        // Find server script
        const possibleServerPaths = [
            FileUtils.getExtensionFilePath('src/stata_mcp_server.py'),
            FileUtils.getExtensionFilePath('stata_mcp_server.py')
        ];
        
        let mcpServerPath = null;
        for (const p of possibleServerPaths) {
            if (FileUtils.checkFileExists(p)) {
                mcpServerPath = p;
                break;
            }
        }

        if (!mcpServerPath) {
            const error = 'MCP server script not found. Please check your installation.';
            Logger.error(`Error: ${error}`);
            vscode.window.showErrorMessage(error);
            return;
        }

        Logger.info(`Server script found at: ${mcpServerPath}`);
            
        // Check setup status
        const setupInProgressFile = FileUtils.getExtensionFilePath(FILE_PATHS.SETUP_IN_PROGRESS);
        const setupErrorFile = FileUtils.getExtensionFilePath(FILE_PATHS.SETUP_ERROR);
        
        if (FileUtils.checkFileExists(setupInProgressFile)) {
            const setupStartTime = FileUtils.readFileContent(setupInProgressFile);
            const setupStartDate = new Date(setupStartTime);
            const currentTime = new Date();
            const minutesSinceStart = (currentTime - setupStartDate) / (1000 * 60);
            
            if (minutesSinceStart < 10) {
                Logger.info(`Python dependency setup is in progress (started ${Math.round(minutesSinceStart)} minutes ago)`);
                vscode.window.showInformationMessage('Stata MCP extension is still setting up Python dependencies. Please wait a moment and try again.');
                return;
            } else {
                Logger.info('Python dependency setup seems to be stuck. Attempting to restart setup.');
                fs.unlinkSync(setupInProgressFile);
            }
        }

        if (FileUtils.checkFileExists(setupErrorFile)) {
            const errorDetails = FileUtils.readFileContent(setupErrorFile);
            if (errorDetails) {
                Logger.info(`Previous Python dependency setup failed: ${errorDetails}`);
            } else {
                Logger.info('Previous Python dependency setup failed. Details not available.');
            }
        }

        const pythonCommand = PythonUtils.getPythonCommand();
        
        // Determine log file path based on user preference
        let logFile;
        if (logFileLocation === 'extension') {
            // Create logs directory if it doesn't exist
            const logsDir = FileUtils.getExtensionFilePath('logs');
            if (!FileUtils.checkFileExists(logsDir)) {
                try {
                    require('fs').mkdirSync(logsDir, { recursive: true });
                    Logger.info(`Created logs directory: ${logsDir}`);
                } catch (error) {
                    Logger.error(`Failed to create logs directory: ${error.message}`);
                }
            }
            logFile = path.join(logsDir, FILE_PATHS.LOG_FILE);
        } else {
            // For workspace and custom, we'll use the default for server log, 
            // but the do file logs will be handled by the server based on settings
            logFile = FileUtils.getExtensionFilePath(FILE_PATHS.LOG_FILE);
        }
        
        // Get log level based on debug mode setting
        const logLevel = debugMode ? 'DEBUG' : 'INFO';

        // Get workspace root for workspace-based log file location
        const workspaceFolders = vscode.workspace.workspaceFolders;
        const workspaceRoot = workspaceFolders && workspaceFolders.length > 0
            ? workspaceFolders[0].uri.fsPath
            : null;

        // Prepare command
        let args = [];
        let cmdString;

        if (IS_WINDOWS) {
            const scriptDir = path.dirname(mcpServerPath);
            cmdString = `"${pythonCommand}" -m stata_mcp_server --host ${host} --port ${port}`;

            if (forcePort) cmdString += ' --force-port';
            if (stataPath) cmdString += ` --stata-path "${stataPath}"`;
            cmdString += ` --log-file "${logFile}" --stata-edition ${stataEdition} --log-level ${logLevel}`;
            cmdString += ` --log-file-location ${logFileLocation}`;
            if (customLogDirectory) cmdString += ` --custom-log-directory "${customLogDirectory}"`;
            if (workspaceRoot) cmdString += ` --workspace-root "${workspaceRoot}"`;
            cmdString += ` --result-display-mode ${resultDisplayMode} --max-output-tokens ${maxOutputTokens}`;
            if (multiSession) {
                cmdString += ` --multi-session --max-sessions ${maxSessions} --session-timeout ${sessionTimeout}`;
            }

            Logger.info(`Starting server with command: ${cmdString}`);

            const options = { cwd: scriptDir, windowsHide: true };
            mcpServerProcess = childProcess.exec(cmdString, options);
        } else {
            args.push(mcpServerPath, '--host', host, '--port', port.toString());
            if (forcePort) args.push('--force-port');
            if (stataPath) args.push('--stata-path', stataPath);
            args.push('--log-file', logFile, '--stata-edition', stataEdition, '--log-level', logLevel);
            args.push('--log-file-location', logFileLocation);
            if (customLogDirectory) args.push('--custom-log-directory', customLogDirectory);
            if (workspaceRoot) args.push('--workspace-root', workspaceRoot);
            args.push('--result-display-mode', resultDisplayMode, '--max-output-tokens', maxOutputTokens.toString());
            if (multiSession) {
                args.push('--multi-session', '--max-sessions', maxSessions.toString(), '--session-timeout', sessionTimeout.toString());
            }
            
            cmdString = `${pythonCommand} ${args.join(' ')}`;
            Logger.info(`Starting server with command: ${cmdString}`);
            
            const options = {
                cwd: path.dirname(mcpServerPath),
                detached: true,
                shell: false,
                stdio: 'pipe',
                windowsHide: true
            };
            
            mcpServerProcess = spawn(pythonCommand, args, options);
        }

        // Set up process handlers
        if (mcpServerProcess.stdout) {
            mcpServerProcess.stdout.on('data', Logger.mcpServer);
        }
        
        if (mcpServerProcess.stderr) {
            mcpServerProcess.stderr.on('data', Logger.mcpServerError);
        }

        mcpServerProcess.on('error', ErrorHandler.serverStartFailed);
        mcpServerProcess.on('exit', ErrorHandler.serverExited);

        // Wait for server to start
        let serverRunning = false;
        const maxAttempts = 30;
        const checkInterval = 500;
        
        for (let i = 0; i < maxAttempts; i++) {
            await new Promise(resolve => setTimeout(resolve, checkInterval));
            
            if (await isServerRunning(host, port)) {
                serverRunning = true;
                break;
            }
        }
        
        if (serverRunning) {
            mcpServerRunning = true;
            Logger.info(`MCP server started successfully on ${host}:${port}`);

            autoUpdateGlobalMcpConfig();
        } else {
            Logger.info(`MCP server failed to start within 15 seconds`);
            vscode.window.showErrorMessage('Failed to start MCP server. Check the Stata output panel for details.');
        }

        updateStatusBar();

    } catch (error) {
        Logger.error(`Error starting MCP server: ${error.message}`);
        vscode.window.showErrorMessage(`Error starting MCP server: ${error.message}`);
    }
}

async function isServerRunning(host, port) {
    return new Promise(async (resolve) => {
        const maxAttempts = 30;
        let attempts = 0;
        
        async function checkServer() {
            try {
                const healthResponse = await axios.get(`http://${host}:${port}/health`, { timeout: 1000 });
                
                if (healthResponse.status === 200) {
                    if (healthResponse.data && healthResponse.data.stata_available === true) {
                        Logger.debug(`Stata is properly initialized`);
                        resolve(true);
                        return;
                    } else {
                        Logger.debug(`Server responded but Stata is not available`);
                    }
                }
            } catch (error) {
                // Debug only - this is called repeatedly during startup polling
                Logger.debug(`Server health check failed: ${error.message}`);
            }
            
            attempts++;
            if (attempts < maxAttempts) {
                setTimeout(checkServer, 500);
            } else {
                resolve(false);
            }
        }
        
        checkServer();
    });
}

async function runSelection() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor');
        return;
    }

    const selection = editor.selection;
    let text;

    if (selection.isEmpty) {
        const line = editor.document.lineAt(selection.active.line);
        text = line.text;
    } else {
        text = editor.document.getText(selection);
    }

    if (!text.trim()) {
        vscode.window.showErrorMessage('No text selected or current line is empty');
        return;
    }

    // Get the current file's directory to set as working directory
    const filePath = editor.document.uri.fsPath;
    const fileDir = filePath ? path.dirname(filePath) : null;

    await executeStataCode(text, 'run_selection', fileDir);
}

async function runFile() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor');
        return;
    }

    const filePath = editor.document.uri.fsPath;

    if (!filePath.toLowerCase().endsWith('.do')) {
        vscode.window.showErrorMessage('Not a Stata .do file');
        return;
    }

    await executeStataFile(filePath);
}

async function stopExecution() {
    if (!isExecuting) {
        return; // Silently ignore if no execution running
    }

    const config = getConfig();
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;

    try {
        updateStatusBar('stopping');

        // Abort the active stream first to stop receiving data
        if (currentStreamAbortController) {
            currentStreamAbortController.abort();
            currentStreamAbortController = null;
        }

        // Send stop request to server
        const response = await axios.post(
            `http://${host}:${port}/stop_execution`,
            {},
            { timeout: 10000 }
        );

        if (response.data.status === 'stopped' || response.data.status === 'stop_requested') {
            Logger.debug(`Execution stopped (${response.data.method || 'unknown'})`);
        } else if (response.data.status === 'no_execution') {
            Logger.debug('No execution was running on server');
        }
        // No user-facing messages for clean stops
    } catch (error) {
        Logger.error(`Error stopping execution: ${error.message}`);
        // Only show error if it's a real failure, not just "no execution"
        if (!error.message.includes('ECONNREFUSED')) {
            vscode.window.showErrorMessage(`Failed to stop execution: ${error.message}`);
        }
    } finally {
        isExecuting = false;
        currentExecutionFile = null;
        currentStreamAbortController = null;
        updateStatusBar();
    }
}

let interactivePanel = null; // Global reference to interactive window

async function runInteractive() {
    console.log('[runInteractive] Command triggered - opening browser');
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor');
        return;
    }

    const filePath = editor.document.uri.fsPath;

    if (!filePath.toLowerCase().endsWith('.do')) {
        vscode.window.showErrorMessage('Not a Stata .do file');
        return;
    }

    // Execute the file and capture output
    const config = getConfig();
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;

    if (!await isServerRunning(host, port)) {
        await startMcpServer();
        if (!await isServerRunning(host, port)) {
            vscode.window.showErrorMessage('Failed to connect to MCP server');
            return;
        }
    }

    // Get selected text or use full file
    const selection = editor.selection;
    let codeToRun = '';
    let urlParams = '';

    if (!selection.isEmpty) {
        // Use selected code
        codeToRun = editor.document.getText(selection);
        const encodedCode = encodeURIComponent(codeToRun);
        urlParams = `code=${encodedCode}`;
        console.log('[runInteractive] Using selected code');
    } else {
        // Use full file
        const encodedFilePath = encodeURIComponent(filePath);
        urlParams = `file=${encodedFilePath}`;
        console.log('[runInteractive] Using full file:', filePath);
    }

    // Open the interactive webpage in the system's default browser
    // Using direct system commands to bypass VS Code's Simple Browser
    const url = `http://${host}:${port}/interactive?${urlParams}`;
    console.log('[runInteractive] Opening URL in system browser:', url);

    try {
        let openCommand;
        if (IS_MAC) {
            // macOS: use 'open' command with proper URL escaping
            // Single quotes prevent shell interpretation of special chars
            openCommand = `open '${url.replace(/'/g, "'\\''")}'`;
        } else if (IS_WINDOWS) {
            // Windows: use 'start' command
            openCommand = `start "" "${url}"`;
        } else {
            // Linux: use 'xdg-open' command
            openCommand = `xdg-open '${url.replace(/'/g, "'\\''")}'`;
        }

        console.log('[runInteractive] Executing command:', openCommand);
        exec(openCommand, (error) => {
            if (error) {
                console.error('[runInteractive] Error opening browser:', error);
                vscode.window.showErrorMessage(`Failed to open browser: ${error.message}`);
            } else {
                console.log('[runInteractive] Browser opened successfully');
            }
        });

        vscode.window.showInformationMessage('Stata Interactive Window opened in your browser!');
    } catch (error) {
        console.error('[runInteractive] Error:', error);
        vscode.window.showErrorMessage(`Failed to open browser: ${error.message}`);
    }
}

async function showInteractiveWindow(filePath, output, graphs, host, port) {
    // Create or reuse interactive panel
    if (!interactivePanel) {
        interactivePanel = vscode.window.createWebviewPanel(
            'stataInteractive',
            'Stata Interactive Window',
            { viewColumn: vscode.ViewColumn.Active, preserveFocus: false },
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: []
            }
        );

        // Reset panel reference when closed
        interactivePanel.onDidDispose(() => {
            interactivePanel = null;
        });

        // Handle messages from webview (command execution)
        interactivePanel.webview.onDidReceiveMessage(
            async message => {
                switch (message.command) {
                    case 'runCommand':
                        try {
                            const config = getConfig();
                            const cmdHost = config.get('mcpServerHost') || 'localhost';
                            const cmdPort = config.get('mcpServerPort') || 4000;
                            const cmdTimeout = config.get('runSelectionTimeout') || 600;  // Default 600 seconds

                            const response = await axios.post(
                                `http://${cmdHost}:${cmdPort}/v1/tools`,
                                {
                                    tool: 'run_selection',
                                    parameters: { selection: message.text, skip_filter: true }
                                },
                                { headers: { 'Content-Type': 'application/json' }, timeout: cmdTimeout * 1000 }
                            );

                            if (response.status === 200 && response.data.status === 'success') {
                                const result = response.data.result || 'Command executed';
                                const cmdGraphs = parseGraphsFromOutput(result);

                                interactivePanel.webview.postMessage({
                                    command: 'commandResult',
                                    executedCommand: message.text,
                                    result: result,
                                    graphs: cmdGraphs.map(g => ({
                                        name: g.name,
                                        url: `http://${cmdHost}:${cmdPort}/graphs/${encodeURIComponent(g.name)}`
                                    }))
                                });
                            } else {
                                interactivePanel.webview.postMessage({
                                    command: 'error',
                                    text: response.data.message || 'Command failed'
                                });
                            }
                        } catch (error) {
                            interactivePanel.webview.postMessage({
                                command: 'error',
                                text: error.message
                            });
                        }
                        break;
                }
            },
            undefined,
            []
        );
    }

    // Reveal the panel
    interactivePanel.reveal(vscode.ViewColumn.Active);

    // Generate HTML content
    const fileName = path.basename(filePath);
    const graphsHtml = graphs.map(graph => {
        const graphUrl = `http://${host}:${port}/graphs/${encodeURIComponent(graph.name)}`;
        return `
            <div class="graph-container">
                <h3>${graph.name}</h3>
                <img src="${graphUrl}" alt="${graph.name}"
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                <div class="error" style="display:none;">Failed to load graph: ${graph.name}</div>
            </div>
        `;
    }).join('');

    interactivePanel.webview.html = getInteractiveWindowHtml(fileName, output, graphsHtml);
}

function getInteractiveWindowHtml(fileName, output, graphsHtml) {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src http://localhost:* http://127.0.0.1:* https://*; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
    <title>Stata Interactive Window</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
        }
        .header {
            border-bottom: 2px solid var(--vscode-panel-border);
            padding-bottom: 15px;
            margin-bottom: 20px;
        }
        .header h1 {
            margin: 0;
            font-size: 24px;
            color: var(--vscode-foreground);
        }
        .header .file-name {
            color: var(--vscode-descriptionForeground);
            font-size: 14px;
            margin-top: 5px;
        }
        .section {
            margin-bottom: 30px;
        }
        .section-title {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 10px;
            color: var(--vscode-foreground);
            border-left: 4px solid var(--vscode-activityBarBadge-background);
            padding-left: 10px;
        }
        .output-container {
            background-color: var(--vscode-terminal-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 4px;
            padding: 15px;
            font-family: 'Courier New', Consolas, monospace;
            font-size: 13px;
            white-space: pre-wrap;
            overflow-x: auto;
            max-height: 500px;
            overflow-y: auto;
        }
        .graph-container {
            background-color: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 4px;
            padding: 20px;
            margin-bottom: 20px;
            text-align: center;
        }
        .graph-container h3 {
            margin-top: 0;
            margin-bottom: 15px;
            color: var(--vscode-foreground);
        }
        .graph-container img {
            max-width: 100%;
            height: auto;
            border: 1px solid var(--vscode-panel-border);
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .error {
            color: var(--vscode-errorForeground);
            background-color: var(--vscode-inputValidation-errorBackground);
            padding: 10px;
            border-radius: 4px;
            margin-top: 10px;
        }
        .no-graphs {
            color: var(--vscode-descriptionForeground);
            font-style: italic;
            padding: 20px;
            text-align: center;
        }
        .command-input-section {
            position: sticky;
            bottom: 0;
            background-color: var(--vscode-editor-background);
            border-top: 2px solid var(--vscode-panel-border);
            padding: 15px;
            margin-top: 20px;
        }
        .command-input-container {
            display: flex;
            gap: 10px;
        }
        #command-input {
            flex: 1;
            background-color: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            border-radius: 4px;
            padding: 8px 12px;
            font-family: 'Courier New', Consolas, monospace;
            font-size: 13px;
        }
        #command-input:focus {
            outline: 1px solid var(--vscode-focusBorder);
        }
        #run-button {
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 4px;
            padding: 8px 20px;
            cursor: pointer;
            font-weight: 600;
        }
        #run-button:hover {
            background-color: var(--vscode-button-hoverBackground);
        }
        #run-button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .command-hint {
            color: var(--vscode-descriptionForeground);
            font-size: 12px;
            margin-top: 8px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Stata Interactive Window</h1>
        <div class="file-name">File: ${fileName}</div>
    </div>

    <div class="section">
        <div class="section-title">Output</div>
        <div class="output-container" id="output-container">${escapeHtml(output)}</div>
    </div>

    <div class="section">
        <div class="section-title">Graphs</div>
        <div id="graphs-container">${graphsHtml || '<div class="no-graphs">No graphs generated</div>'}</div>
    </div>

    <div class="command-input-section">
        <div class="section-title">Execute Stata Command</div>
        <div class="command-input-container">
            <input type="text" id="command-input" placeholder="Enter Stata command (e.g., summarize, list, scatter y x)..." />
            <button id="run-button">Run</button>
        </div>
        <div class="command-hint">Press Enter to execute</div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const commandInput = document.getElementById('command-input');
        const runButton = document.getElementById('run-button');
        const outputContainer = document.getElementById('output-container');
        const graphsContainer = document.getElementById('graphs-container');

        runButton.addEventListener('click', executeCommand);
        commandInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') executeCommand();
        });

        function executeCommand() {
            const command = commandInput.value.trim();
            if (!command) return;
            runButton.disabled = true;
            runButton.textContent = 'Running...';
            vscode.postMessage({ command: 'runCommand', text: command });
            commandInput.value = '';
        }

        window.addEventListener('message', event => {
            const message = event.data;
            if (message.command === 'commandResult') {
                // Create a new cell for this command/output pair
                const cell = document.createElement('div');
                cell.className = 'output-cell';
                cell.style.borderLeft = '3px solid var(--vscode-activityBarBadge-background)';
                cell.style.paddingLeft = '10px';
                cell.style.marginBottom = '15px';

                const cmd = document.createElement('div');
                cmd.textContent = '> ' + message.executedCommand;
                cmd.style.color = 'var(--vscode-terminal-ansiBrightBlue)';
                cmd.style.fontWeight = 'bold';
                cmd.style.marginBottom = '10px';
                cell.appendChild(cmd);

                const res = document.createElement('div');
                res.textContent = message.result;
                res.style.whiteSpace = 'pre-wrap';
                cell.appendChild(res);

                outputContainer.appendChild(cell);
                outputContainer.scrollTop = outputContainer.scrollHeight;

                // Add graphs if any
                if (message.graphs && message.graphs.length > 0) {
                    const graphsHtml = message.graphs.map(g =>
                        \`<div class="graph-container"><h3>\${g.name}</h3>
                        <img src="\${g.url}" alt="\${g.name}"></div>\`).join('');
                    graphsContainer.innerHTML += graphsHtml;
                }
            } else if (message.command === 'error') {
                const cell = document.createElement('div');
                cell.className = 'error';
                cell.textContent = 'Error: ' + message.text;
                cell.style.marginBottom = '15px';
                outputContainer.appendChild(cell);
                outputContainer.scrollTop = outputContainer.scrollHeight;
            }
            runButton.disabled = false;
            runButton.textContent = 'Run';
            commandInput.focus();
        });

        commandInput.focus();
    </script>
</body>
</html>`;
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

async function executeStataCode(code, toolName = 'run_command', workingDir = null) {
    const config = getConfig();
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;
    const runSelectionTimeout = config.get('runSelectionTimeout') || 600;  // Default 600 seconds

    if (!await isServerRunning(host, port)) {
        await startMcpServer();
        if (!await isServerRunning(host, port)) {
            vscode.window.showErrorMessage('Failed to connect to MCP server');
            return;
        }
    }

    stataOutputChannel.show(false);  // Steal focus when running Stata commands
    Logger.debug(`Executing Stata code: ${code}`);

    // Clear graph display before Run Selection to show fresh results
    if (toolName === 'run_selection') {
        allGraphs = {};
        if (graphViewerPanel) {
            updateGraphViewerPanel(host, port);
        }
    }

    const paramName = toolName === 'run_selection' ? 'selection' : 'command';

    try {
        const requestBody = {
            tool: toolName,
            parameters: {
                [paramName]: code,
                working_dir: workingDir
            }
        };
        
        const response = await axios.post(
            `http://${host}:${port}/v1/tools`,
            requestBody,
            {
                headers: { 'Content-Type': 'application/json' },
                timeout: runSelectionTimeout * 1000  // Convert seconds to milliseconds
            }
        );
        
        if (response.status === 200) {
            const result = response.data;

            if (result.status === 'success') {
                const outputContent = result.result || 'Command executed successfully (no output)';
                // Don't clear output channel - preserve previous logs for run_selection
                stataOutputChannel.appendLine(outputContent);
                stataOutputChannel.show(false);  // Steal focus when running Stata commands

                // Parse and display any graphs (VS Code only, not for MCP calls)
                const autoDisplayGraphs = config.get('autoDisplayGraphs', true);
                if (autoDisplayGraphs) {
                    const graphs = parseGraphsFromOutput(outputContent);
                    if (graphs.length > 0) {
                        await displayGraphs(graphs, host, port);
                    }
                }

                return outputContent;
            } else {
                const errorMessage = result.message || 'Unknown error';
                stataOutputChannel.appendLine(`Error: ${errorMessage}`);
                stataOutputChannel.show(false);  // Steal focus on errors
                vscode.window.showErrorMessage(`Stata error: ${errorMessage}`);
                return null;
            }
        } else {
            const errorMessage = `HTTP error: ${response.status}`;
            stataOutputChannel.appendLine(errorMessage);
            stataOutputChannel.show(false);  // Steal focus on errors
            vscode.window.showErrorMessage(errorMessage);
            return null;
        }
    } catch (error) {
        Logger.debug(`Error executing Stata code: ${error.message}`);
        const errorMessage = `Error executing Stata code: ${error.message}`;
        stataOutputChannel.appendLine(errorMessage);
        stataOutputChannel.show(false);  // Steal focus on errors
        vscode.window.showErrorMessage(errorMessage);
        return null;
    }
}

async function executeStataFile(filePath) {
    // Check if already executing
    if (isExecuting) {
        vscode.window.showWarningMessage('A Stata execution is already in progress. Please wait or stop it first.');
        return;
    }

    const config = getConfig();
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;
    const runFileTimeout = config.get('runFileTimeout') || 600;
    const workingDirOption = config.get('workingDirectory') || 'dofile';
    const customWorkingDir = config.get('customWorkingDirectory') || '';

    // Set execution state
    isExecuting = true;
    currentExecutionFile = filePath;
    updateStatusBar('running');

    stataOutputChannel.show(false);  // Steal focus when running Stata commands
    Logger.debug(`Executing Stata file: ${filePath}`);
    Logger.debug(`Using timeout: ${runFileTimeout} seconds`);
    Logger.debug(`Working directory option: ${workingDirOption}`);

    // Determine actual working directory based on setting
    let workingDir = null;
    const fileDir = path.dirname(filePath);

    switch (workingDirOption) {
        case 'dofile':
            workingDir = fileDir;
            break;
        case 'parent':
            workingDir = path.dirname(fileDir);
            break;
        case 'workspace':
            // Get VS Code workspace root
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (workspaceFolders && workspaceFolders.length > 0) {
                workingDir = workspaceFolders[0].uri.fsPath;
            } else {
                // Fall back to dofile directory if no workspace
                workingDir = fileDir;
                Logger.debug('No workspace folder found, falling back to dofile directory');
            }
            break;
        case 'extension':
            // Use logs folder in extension directory
            const extensionPath = globalContext.extensionPath || __dirname;
            workingDir = path.join(extensionPath, 'logs');
            break;
        case 'custom':
            if (customWorkingDir && customWorkingDir.trim()) {
                workingDir = customWorkingDir.trim();
            } else {
                // Fall back to dofile directory if custom not specified
                workingDir = fileDir;
                Logger.debug('Custom working directory not specified, falling back to dofile directory');
            }
            break;
        case 'none':
            workingDir = null;  // Don't change directory
            break;
        default:
            workingDir = fileDir;
    }

    Logger.debug(`Resolved working directory: ${workingDir || '(none - keep current)'}`);

    if (!await isServerRunning(host, port)) {
        await startMcpServer();
        if (!await isServerRunning(host, port)) {
            const errorMessage = 'Failed to connect to MCP server';
            stataOutputChannel.appendLine(errorMessage);
            stataOutputChannel.show(false);  // Steal focus on errors
            vscode.window.showErrorMessage(errorMessage);
            // Cleanup on early exit
            isExecuting = false;
            currentExecutionFile = null;
            updateStatusBar();
            return;
        }
    }

    try {
        // Use streaming endpoint for real-time output display
        Logger.debug(`Executing via /run_file/stream: ${filePath}`);
        stataOutputChannel.clear();
        stataOutputChannel.show(false);  // Show output panel

        // Build query parameters
        const params = new URLSearchParams({
            file_path: filePath,
            timeout: runFileTimeout.toString()
        });
        if (workingDir) {
            params.append('working_dir', workingDir);
        }

        // Use streaming endpoint for real-time output display
        const streamUrl = `http://${host}:${port}/run_file/stream?${params.toString()}`;
        Logger.debug(`Stream URL: ${streamUrl}`);

        // Use axios with responseType 'stream' for SSE
        let fullOutput = '';
        let hasError = false;

        // Create AbortController to allow cancellation when stop is pressed
        currentStreamAbortController = new AbortController();

        const response = await axios.get(streamUrl, {
            responseType: 'stream',
            timeout: (runFileTimeout * 1000) + 10000,
            signal: currentStreamAbortController.signal
        });

        // Process the SSE stream
        await new Promise((resolve, reject) => {
            let buffer = '';

            response.data.on('data', (chunk) => {
                buffer += chunk.toString();

                // Normalize line endings (Windows uses \r\n, Mac/Linux use \n)
                buffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

                // Process complete SSE messages
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';  // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.substring(6);  // Remove 'data: ' prefix

                        // Skip status messages, show actual output
                        if (data.startsWith('Starting execution') ||
                            data.startsWith('Executing...') ||
                            data.startsWith('*** Execution')) {
                            // Status message - could show in status bar
                            Logger.debug(`Stream status: ${data}`);
                        } else if (data.startsWith('Error:') || data.startsWith('ERROR:')) {
                            hasError = true;
                            stataOutputChannel.appendLine(data);
                            fullOutput += data + '\n';
                        } else if (data.trim()) {
                            // Actual Stata output - display in real-time
                            stataOutputChannel.appendLine(data);
                            fullOutput += data + '\n';
                        }
                    }
                }
            });

            response.data.on('end', () => {
                // Process any remaining buffer
                if (buffer.startsWith('data: ')) {
                    const data = buffer.substring(6);
                    if (data.trim() && !data.startsWith('Starting') && !data.startsWith('Executing') && !data.startsWith('***')) {
                        stataOutputChannel.appendLine(data);
                        fullOutput += data + '\n';
                    }
                }
                resolve();
            });

            response.data.on('error', (err) => {
                reject(err);
            });
        });

        if (hasError) {
            vscode.window.showErrorMessage('Stata execution completed with errors');
        }

        // Parse and display any graphs
        const autoDisplayGraphs = config.get('autoDisplayGraphs', true);
        if (autoDisplayGraphs && fullOutput) {
            const graphs = parseGraphsFromOutput(fullOutput);
            if (graphs.length > 0) {
                await displayGraphs(graphs, host, port);
            }
        }

        return fullOutput || 'File executed successfully';

    } catch (error) {
        // Check if this was an intentional abort (user clicked Stop)
        if (error.code === 'ERR_CANCELED' || error.name === 'CanceledError' || error.message?.includes('canceled')) {
            Logger.debug('Execution was stopped by user');
            stataOutputChannel.appendLine('\n--- Execution stopped by user ---');
            // No error message for intentional stop
            return null;
        }

        Logger.debug(`Error executing Stata file: ${error.message}`);
        const errorMessage = `Error executing Stata file: ${error.message}`;
        stataOutputChannel.appendLine(errorMessage);
        stataOutputChannel.show(false);  // Steal focus on errors
        vscode.window.showErrorMessage(errorMessage);
        return null;
    } finally {
        // Always cleanup execution state
        isExecuting = false;
        currentExecutionFile = null;
        if (currentStreamAbortController) {
            currentStreamAbortController = null;
        }
        updateStatusBar();
    }
}

function showStataOutputWebview(content = null) {
    if (!stataOutputWebviewPanel) {
        stataOutputWebviewPanel = vscode.window.createWebviewPanel(
            'stataOutput',
            'Stata Output',
            vscode.ViewColumn.Two,
            { enableScripts: true }
        );
        
        stataOutputWebviewPanel.onDidDispose(
            () => { stataOutputWebviewPanel = null; },
            null,
            globalContext.subscriptions
        );
    }
    
    if (content) {
        const htmlContent = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;')
            .replace(/\n/g, '<br>');
        
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
            <body>${htmlContent}</body>
            </html>
        `;
    }
    
    stataOutputWebviewPanel.reveal(vscode.ViewColumn.Two);
}

// Global variable for data viewer panel
let dataViewerPanel = null;

async function viewStataData() {
    Logger.info('View Stata Data command triggered');

    const config = getConfig();
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;

    try {
        // Call the server endpoint to get data
        Logger.debug(`Fetching data from http://${host}:${port}/view_data`);
        const response = await axios.get(`http://${host}:${port}/view_data`);

        if (response.data.status === 'error') {
            vscode.window.showErrorMessage(`Error viewing data: ${response.data.message}`);
            stataOutputChannel.appendLine(`Error: ${response.data.message}`);
            return;
        }

        // Create or reuse webview panel
        if (!dataViewerPanel) {
            dataViewerPanel = vscode.window.createWebviewPanel(
                'stataDataViewer',
                'Data Editor (Browse)',
                { viewColumn: vscode.ViewColumn.Active, preserveFocus: false },
                {
                    enableScripts: true,
                    retainContextWhenHidden: true
                }
            );

            dataViewerPanel.onDidDispose(
                () => { dataViewerPanel = null; },
                null,
                globalContext.subscriptions
            );

            // Handle messages from webview
            dataViewerPanel.webview.onDidReceiveMessage(
                async message => {
                    if (message.command === 'applyFilter') {
                        const ifCondition = message.condition;
                        Logger.info(`Applying filter: ${ifCondition}`);

                        try {
                            const filterResponse = await axios.get(
                                `http://${host}:${port}/view_data?if_condition=${encodeURIComponent(ifCondition)}`
                            );

                            if (filterResponse.data.status === 'error') {
                                dataViewerPanel.webview.postMessage({
                                    command: 'filterError',
                                    message: filterResponse.data.message
                                });
                            } else {
                                const { data, columns, rows, index, dtypes } = filterResponse.data;
                                dataViewerPanel.webview.html = getStataDataViewerHtml(data, columns, index, dtypes, rows, ifCondition);
                                Logger.info(`Filtered data: ${rows} observations`);
                            }
                        } catch (error) {
                            Logger.error(`Filter error: ${error.message}`);
                            dataViewerPanel.webview.postMessage({
                                command: 'filterError',
                                message: error.message
                            });
                        }
                    }
                },
                undefined,
                globalContext.subscriptions
            );
        }

        const { data, columns, rows, index, dtypes } = response.data;

        // If no data, show empty message
        if (!data || data.length === 0) {
            dataViewerPanel.webview.html = getEmptyDataViewerHtml();
            dataViewerPanel.reveal(vscode.ViewColumn.Active);
            return;
        }

        // Create the Stata-like data viewer HTML
        dataViewerPanel.webview.html = getStataDataViewerHtml(data, columns, index, dtypes, rows);
        dataViewerPanel.reveal(vscode.ViewColumn.Active);

        Logger.info(`Data viewer displayed: ${rows} observations, ${columns.length} variables`);
        stataOutputChannel.appendLine(`Data viewer opened: ${rows} observations, ${columns.length} variables`);

    } catch (error) {
        const errorMessage = `Failed to view data: ${error.message}`;
        Logger.error(errorMessage);
        vscode.window.showErrorMessage(errorMessage);
        stataOutputChannel.appendLine(errorMessage);

        if (error.code === 'ECONNREFUSED') {
            const startServer = await vscode.window.showErrorMessage(
                'MCP server is not running. Do you want to start it?',
                'Yes', 'No'
            );

            if (startServer === 'Yes') {
                await startMcpServer();
            }
        }
    }
}

function getEmptyDataViewerHtml() {
    return `<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Data Editor</title>
        <style>
            body {
                margin: 0;
                padding: 40px;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #ffffff;
                text-align: center;
            }
            .empty-message {
                color: #666;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <div class="empty-message">
            <p><strong>No data currently loaded</strong></p>
            <p>Load a dataset in Stata to view it here.</p>
        </div>
    </body>
    </html>`;
}

function getStataDataViewerHtml(data, columns, index, dtypes, totalRows, ifCondition = '') {
    // Escape data for safe JSON embedding
    const dataJson = JSON.stringify(data);
    const columnsJson = JSON.stringify(columns);
    const indexJson = JSON.stringify(index);
    const dtypesJson = JSON.stringify(dtypes);
    const ifConditionEscaped = ifCondition.replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    return `<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Data Editor (Browse)</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #ffffff;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                height: 100vh;
            }

            .toolbar {
                background: #f8f9fa;
                border-bottom: 1px solid #dee2e6;
                padding: 10px 16px;
                display: flex;
                align-items: center;
                gap: 12px;
                font-size: 13px;
                color: #212529;
                min-height: 40px;
            }

            .toolbar-label {
                font-weight: 600;
                font-size: 14px;
            }

            .filter-section {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-left: auto;
            }

            .filter-label {
                font-weight: 600;
                font-size: 13px;
            }

            #filter-input {
                padding: 6px 10px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 13px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                min-width: 300px;
                background: #ffffff;
            }

            #filter-input:focus {
                outline: none;
                border-color: #007acc;
                box-shadow: 0 0 0 3px rgba(0, 122, 204, 0.1);
            }

            .filter-button {
                padding: 6px 14px;
                background: #0e639c;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-weight: 600;
                font-size: 13px;
            }

            .filter-button:hover {
                background: #1177bb;
            }

            .filter-button:disabled {
                background: #999;
                cursor: not-allowed;
            }

            .clear-filter-button {
                padding: 6px 14px;
                background: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-weight: 600;
                font-size: 13px;
            }

            .clear-filter-button:hover {
                background: #5a6268;
            }

            .filter-error {
                color: #dc3545;
                font-size: 12px;
                margin-left: 8px;
            }

            .filter-active {
                background: #d1ecf1;
                color: #0c5460;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                font-family: 'Consolas', 'Monaco', monospace;
            }

            .grid-container {
                flex: 1;
                overflow: auto;
                position: relative;
                background: #ffffff;
            }

            .data-grid {
                display: grid;
                border: 1px solid #dee2e6;
                font-size: 13px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'SF Pro Text', sans-serif;
                background: #ffffff;
            }

            .cell {
                border-right: 1px solid #dee2e6;
                border-bottom: 1px solid #dee2e6;
                padding: 8px 12px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                background: #ffffff;
                min-height: 32px;
                display: flex;
                align-items: center;
                color: #000000;
                font-weight: 500;
            }

            .header-cell {
                background: #f8f9fa;
                color: #000000;
                font-weight: 700;
                font-size: 13px;
                position: sticky;
                top: 0;
                z-index: 10;
                padding: 10px 12px;
                border-right: 1px solid #dee2e6;
                border-bottom: 2px solid #adb5bd;
                text-align: center;
                cursor: default;
                user-select: none;
                min-height: 36px;
            }

            .index-cell {
                background: #f8f9fa;
                font-weight: 700;
                font-size: 13px;
                color: #000000;
                position: sticky;
                left: 0;
                z-index: 5;
                text-align: right;
                border-right: 2px solid #adb5bd;
                padding: 8px 12px;
            }

            .corner-cell {
                background: #f8f9fa;
                position: sticky;
                left: 0;
                top: 0;
                z-index: 15;
                border-right: 2px solid #adb5bd;
                border-bottom: 2px solid #adb5bd;
            }

            .cell:hover:not(.header-cell):not(.index-cell):not(.corner-cell) {
                background: #e9ecef;
                outline: 2px solid #0d6efd;
                outline-offset: -2px;
            }

            .selected-cell {
                background: #cfe2ff !important;
                outline: 2px solid #0d6efd !important;
                outline-offset: -2px;
            }

            .numeric {
                text-align: right;
            }

            .string {
                text-align: left;
            }

            .null-value {
                color: #6c757d !important;
                font-style: italic;
            }

            .data-cell {
                color: #000000 !important;
            }

            ::-webkit-scrollbar {
                width: 16px;
                height: 16px;
            }

            ::-webkit-scrollbar-track {
                background: #f0f0f0;
            }

            ::-webkit-scrollbar-thumb {
                background: #c0c0c0;
                border: 2px solid #f0f0f0;
                border-radius: 2px;
            }

            ::-webkit-scrollbar-thumb:hover {
                background: #a0a0a0;
            }
        </style>
    </head>
    <body>
        <div class="toolbar">
            <span class="toolbar-label">Data Editor (Browse)</span>
            <span>|</span>
            <span id="data-info"></span>
            ${ifCondition ? `<span class="filter-active">Filter: if ${ifConditionEscaped}</span>` : ''}
            <div class="filter-section">
                <span class="filter-label">if</span>
                <input type="text" id="filter-input" placeholder="e.g., price > 5000 & mpg < 30" value="${ifConditionEscaped}" />
                <button class="filter-button" id="apply-filter-btn">Apply</button>
                ${ifCondition ? '<button class="clear-filter-button" id="clear-filter-btn">Clear</button>' : ''}
                <span id="filter-error" class="filter-error"></span>
            </div>
        </div>
        <div class="grid-container">
            <div class="data-grid" id="dataGrid"></div>
        </div>

        <script>
            const vscode = acquireVsCodeApi();
            const data = ${dataJson};
            const columns = ${columnsJson};
            const indexData = ${indexJson};
            const dtypes = ${dtypesJson};
            const totalRows = ${totalRows};
            const currentFilter = '${ifCondition.replace(/'/g, "\\'")}';

            // Filter functionality
            const filterInput = document.getElementById('filter-input');
            const applyFilterBtn = document.getElementById('apply-filter-btn');
            const clearFilterBtn = document.getElementById('clear-filter-btn');
            const filterError = document.getElementById('filter-error');

            applyFilterBtn.addEventListener('click', applyFilter);
            filterInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') applyFilter();
            });

            if (clearFilterBtn) {
                clearFilterBtn.addEventListener('click', () => {
                    vscode.postMessage({
                        command: 'applyFilter',
                        condition: ''
                    });
                });
            }

            function applyFilter() {
                const condition = filterInput.value.trim();
                filterError.textContent = '';
                applyFilterBtn.disabled = true;
                applyFilterBtn.textContent = 'Applying...';

                vscode.postMessage({
                    command: 'applyFilter',
                    condition: condition
                });
            }

            // Listen for error messages
            window.addEventListener('message', event => {
                const message = event.data;
                if (message.command === 'filterError') {
                    filterError.textContent = 'Error: ' + message.message;
                    applyFilterBtn.disabled = false;
                    applyFilterBtn.textContent = 'Apply';
                }
            });

            // Update info bar
            document.getElementById('data-info').textContent =
                totalRows + ' observations, ' + columns.length + ' variables';

            // Calculate grid dimensions
            const numCols = columns.length + 1; // +1 for index column
            const numRows = data.length + 1; // +1 for header row

            // Set up grid template
            const grid = document.getElementById('dataGrid');
            grid.style.gridTemplateColumns = 'minmax(80px, auto) ' + 'minmax(140px, 1fr) '.repeat(columns.length);

            // Create corner cell
            const cornerCell = document.createElement('div');
            cornerCell.className = 'cell header-cell corner-cell';
            cornerCell.textContent = '';
            grid.appendChild(cornerCell);

            // Create header row
            columns.forEach(col => {
                const headerCell = document.createElement('div');
                headerCell.className = 'cell header-cell';
                headerCell.textContent = col;
                headerCell.title = col + ' (' + (dtypes[col] || 'unknown') + ')';
                grid.appendChild(headerCell);
            });

            // Create data rows
            data.forEach((row, rowIdx) => {
                // Index column
                const indexCell = document.createElement('div');
                indexCell.className = 'cell index-cell';
                indexCell.textContent = indexData[rowIdx] !== undefined ? indexData[rowIdx] : rowIdx;
                grid.appendChild(indexCell);

                // Data columns
                row.forEach((value, colIdx) => {
                    const cell = document.createElement('div');
                    const dtype = dtypes[columns[colIdx]] || '';
                    const isNumeric = dtype.includes('int') || dtype.includes('float');

                    cell.className = 'cell data-cell ' + (isNumeric ? 'numeric' : 'string');

                    // Check for Stata missing values (very large numbers > 8.9e+307)
                    const isStataMissing = typeof value === 'number' &&
                                         (value === null ||
                                          value === undefined ||
                                          !isFinite(value) ||
                                          Math.abs(value) > 8.98e+307);

                    if (value === null || value === undefined || isStataMissing) {
                        cell.textContent = '.';
                        cell.classList.add('null-value');
                    } else if (typeof value === 'number') {
                        // Format numbers
                        if (Number.isInteger(value)) {
                            cell.textContent = value.toString();
                        } else {
                            cell.textContent = value.toFixed(6).replace(/\.?0+$/, '');
                        }
                    } else {
                        cell.textContent = value.toString();
                    }

                    cell.title = cell.textContent;

                    // Click handler for cell selection
                    cell.addEventListener('click', function() {
                        document.querySelectorAll('.selected-cell').forEach(c => {
                            c.classList.remove('selected-cell');
                        });
                        this.classList.add('selected-cell');
                    });

                    grid.appendChild(cell);
                });
            });
        </script>
    </body>
    </html>`;
}

async function testMcpServer() {
    const config = getConfig();
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;
    
    try {
        const testCommand = "di \"Hello from Stata MCP Server!\"";
        const testResponse = await axios.post(
            `http://${host}:${port}/v1/tools`,
            {
                tool: "stata_run_selection",
                parameters: { selection: testCommand }
            },
            { headers: { 'Content-Type': 'application/json' } }
        );
        
        if (testResponse.status === 200) {
            vscode.window.showInformationMessage(`MCP server is running properly`);
            
            let result = "No result returned";
            if (testResponse.data && typeof testResponse.data === 'object') {
                result = testResponse.data.result || "No result in response data";
            } else if (testResponse.data) {
                result = String(testResponse.data);
            }
            
            stataOutputChannel.appendLine('Test Command Result:');
            stataOutputChannel.appendLine(result);
            stataOutputChannel.show(false);  // Steal focus when user explicitly tests server
            return true;
        } else {
            vscode.window.showErrorMessage(`MCP server returned status: ${testResponse.status}`);
            return false;
        }
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to connect to MCP server: ${error.message}`);
        
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

async function askAgent() {
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

        agentWebviewPanel.webview.onDidReceiveMessage(
            async message => {
                if (message.command === 'askAgent') {
                    const response = await getAgentResponse(message.text);
                    agentWebviewPanel.webview.postMessage({ command: 'agentResponse', text: response });
                } else if (message.command === 'runCode') {
                    await executeStataCode(message.code, 'run_selection');
                    agentWebviewPanel.webview.postMessage({ command: 'codeRun' });
                }
            },
            undefined,
            globalContext.subscriptions
        );

        agentWebviewPanel.onDidDispose(
            () => { agentWebviewPanel = null; },
            null,
            globalContext.subscriptions
        );

        agentWebviewPanel.webview.html = getAgentWebviewContent();
    } else {
        agentWebviewPanel.reveal();
    }
}

async function getAgentResponse(query) {
    stataAgentChannel.appendLine(`User: ${query}`);
    
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

function getAgentWebviewContent() {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stata Agent</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; display: flex; flex-direction: column; height: 100vh; }
        #conversation { flex-grow: 1; overflow-y: auto; border: 1px solid #ddd; padding: 10px; margin-bottom: 10px; }
        .user-message { background-color: #e6f7ff; padding: 8px 12px; border-radius: 12px; margin: 5px 0; max-width: 80%; align-self: flex-end; }
        .agent-message { background-color: #f0f0f0; padding: 8px 12px; border-radius: 12px; margin: 5px 0; max-width: 80%; }
        #input-area { display: flex; }
        #user-input { flex-grow: 1; padding: 10px; margin-right: 5px; }
        button { padding: 10px 15px; background-color: #0078d4; color: white; border: none; cursor: pointer; }
        button:hover { background-color: #005a9e; }
        pre { background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }
        code { font-family: 'Courier New', monospace; }
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
            
            addAgentMessage('Hello! I am your Stata assistant. How can I help you today?');
            
            sendButton.addEventListener('click', sendMessage);
            userInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
            
            window.addEventListener('message', event => {
                const message = event.data;
                switch (message.command) {
                    case 'agentResponse': addAgentMessage(message.text); break;
                    case 'codeRun': addAgentMessage('Code executed in Stata.'); break;
                }
            });
            
            function sendMessage() {
                const text = userInput.value.trim();
                if (text) {
                    addUserMessage(text);
                    vscode.postMessage({ command: 'askAgent', text: text });
                    if (text.toLowerCase().startsWith('run:')) {
                        const code = text.substring(4).trim();
                        vscode.postMessage({ command: 'runCode', code: code });
                    }
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
                
                if (text.includes('\`\`\`')) {
                    const parts = text.split('\`\`\`');
                    for (let i = 0; i < parts.length; i++) {
                        if (i % 2 === 0) {
                            const textNode = document.createTextNode(parts[i]);
                            div.appendChild(textNode);
                        } else {
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
</html>`;
}

function autoUpdateGlobalMcpConfig() {
    const config = getConfig();
    const host = config.get('mcpServerHost') || 'localhost';
    const port = config.get('mcpServerPort') || 4000;
    
    try {
        const homeDir = os.homedir();
        const mcpConfigDir = path.join(homeDir, '.cursor');
        const mcpConfigPath = path.join(mcpConfigDir, 'mcp.json');
        
        Logger.info(`Checking MCP configuration at ${mcpConfigPath}`);
        
        if (!FileUtils.checkFileExists(mcpConfigDir)) {
            fs.mkdirSync(mcpConfigDir, { recursive: true });
            Logger.info(`Created directory: ${mcpConfigDir}`);
        }
        
        let mcpConfig = { mcpServers: {} };
        let configChanged = false;
        
        if (FileUtils.checkFileExists(mcpConfigPath)) {
            try {
                const configContent = FileUtils.readFileContent(mcpConfigPath);
                mcpConfig = JSON.parse(configContent);
                mcpConfig.mcpServers = mcpConfig.mcpServers || {};
                
                const currentConfig = mcpConfig.mcpServers["stata-mcp"];
                const correctUrl = `http://${host}:${port}/mcp`;
                
                if (!currentConfig || currentConfig.url !== correctUrl || currentConfig.transport !== "sse") {
                    Logger.info(`Updating stata-mcp configuration to ${correctUrl}`);
                    mcpConfig.mcpServers["stata-mcp"] = {
                        url: correctUrl,
                        transport: "sse"
                    };
                    configChanged = true;
                } else {
                    Logger.info(`stata-mcp configuration is already correct`);
                }
            } catch (error) {
                Logger.info(`Error reading MCP config: ${error.message}`);
                mcpConfig = { mcpServers: {} };
                mcpConfig.mcpServers["stata-mcp"] = {
                    url: `http://${host}:${port}/mcp`,
                    transport: "sse"
                };
                configChanged = true;
            }
        } else {
            Logger.info(`Creating new MCP configuration`);
            mcpConfig.mcpServers["stata-mcp"] = {
                url: `http://${host}:${port}/mcp`,
                transport: "sse"
            };
            configChanged = true;
        }
        
        if (configChanged) {
            FileUtils.writeFileContent(mcpConfigPath, JSON.stringify(mcpConfig, null, 2));
            Logger.info(`Updated MCP configuration at ${mcpConfigPath}`);
        }
        
        return true;
    } catch (error) {
        Logger.info(`Error updating MCP config: ${error.message}`);
        Logger.debug(`Error updating MCP config: ${error.message}`);
        return false;
    }
}

async function detectStataPath() {
    if (detectedStataPath) return detectedStataPath;
    
    let possiblePaths = [];
    
    if (IS_WINDOWS) {
        const programFiles = process.env.ProgramFiles || 'C:\\Program Files';
        const programFilesX86 = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)';
        possiblePaths = [
            path.join(programFiles, 'Stata19'),
            path.join(programFiles, 'Stata18'),
            path.join(programFiles, 'Stata17'),
            path.join(programFilesX86, 'Stata19'),
            path.join(programFilesX86, 'Stata18'),
            path.join(programFilesX86, 'Stata17')
        ];
    } else if (IS_MAC) {
        possiblePaths = [
            '/Applications/Stata19',
            '/Applications/Stata18',
            '/Applications/Stata17',
            '/Applications/StataNow',
            '/Applications/Stata'
        ];
    } else if (IS_LINUX) {
        possiblePaths = [
            '/usr/local/stata19',
            '/usr/local/stata18',
            '/usr/local/stata17',
            '/usr/local/stata'
        ];
    }
    
    for (const p of possiblePaths) {
        if (FileUtils.checkFileExists(p)) {
            Logger.debug(`Found Stata at: ${p}`);
            detectedStataPath = p;
            return p;
        }
    }
    
    return null;
}

async function detectAndUpdateStataPath() {
    const path = await detectStataPath();
    
    if (path) {
        const config = getConfig();
        await config.update('stataPath', path, vscode.ConfigurationTarget.Global);
        vscode.window.showInformationMessage(`Stata path detected and set to: ${path}`);
        return path;
    } else {
        vscode.window.showErrorMessage('Could not detect Stata installation path. Please set it manually in settings.');
        vscode.commands.executeCommand('workbench.action.openSettings', 'stata-vscode.stataPath');
        return null;
    }
}

function showOutput(content) {
    if (content) stataOutputChannel.append(content);
    stataOutputChannel.show(false);  // Steal focus when user explicitly requests output
}

// Graph display functionality
function parseGraphsFromOutput(output) {
    const graphs = [];

    Logger.debug(`Parsing output for graphs. Output length: ${output ? output.length : 0}`);

    // Normalize line endings to \n (Windows uses \r\n, Mac/Linux use \n)
    // Also handle standalone \r (old Mac format) just in case
    const normalizedOutput = output ? output.replace(/\r\n/g, '\n').replace(/\r/g, '\n') : '';

    // Look for the GRAPHS DETECTED section in the output
    const graphSectionRegex = /={60}\nGRAPHS DETECTED: (\d+) graph\(s\) created\n={60}\n((?:\s*•\s+.+\n?)+)/;
    const match = normalizedOutput.match(graphSectionRegex);

    if (match) {
        Logger.debug(`Found GRAPHS DETECTED section. Match: ${match[0]}`);
        const graphLines = match[2].trim().split('\n');
        Logger.debug(`Graph lines: ${JSON.stringify(graphLines)}`);

        for (const line of graphLines) {
            // Extract graph name and path from lines like "  • graph1: /path/to/graph.png"
            const graphMatch = line.match(/•\s+(.+):\s+(.+)/);
            if (graphMatch) {
                const name = graphMatch[1].trim();
                // Normalize path to forward slashes (Windows paths may have backslashes)
                const path = graphMatch[2].trim().replace(/\\/g, '/');
                Logger.debug(`Matched graph line: name="${name}", path="${path}"`);
                graphs.push({
                    name: name,
                    path: path
                });
            } else {
                Logger.debug(`Failed to match graph line: "${line}"`);
            }
        }
    } else {
        Logger.debug(`No GRAPHS DETECTED section found in output`);
        // Log a sample of output to help debug (first 500 chars)
        if (normalizedOutput && normalizedOutput.length > 0) {
            const sample = normalizedOutput.substring(0, 500);
            Logger.debug(`Output sample (first 500 chars): ${sample}`);
            // Check if there's any mention of graphs in the output
            if (normalizedOutput.includes('GRAPHS') || normalizedOutput.includes('graph')) {
                Logger.debug(`Output contains 'GRAPHS' or 'graph' but regex didn't match`);
            }
        }
    }

    Logger.debug(`Parsed ${graphs.length} graph(s)`);
    return graphs;
}

// Global variable for graph viewer panel
let graphViewerPanel = null;
let allGraphs = {}; // Store all graphs by name to accumulate them

async function displayGraphs(graphs, host, port) {
    if (!graphs || graphs.length === 0) {
        return;
    }

    const config = getConfig();
    const displayMethod = config.get('graphDisplayMethod') || 'vscode';

    if (displayMethod === 'vscode') {
        Logger.info(`Displaying ${graphs.length} graph(s) in VS Code webview`);
        displayGraphsInVSCode(graphs, host, port);
    } else {
        Logger.info(`Displaying ${graphs.length} graph(s) in external browser`);
        displayGraphsInBrowser(graphs, host, port);
    }
}

function displayGraphsInVSCode(graphs, host, port) {
    // Create or reuse graph viewer panel
    if (!graphViewerPanel) {
        graphViewerPanel = vscode.window.createWebviewPanel(
            'stataGraphViewer',
            'Stata Graphs',
            { viewColumn: vscode.ViewColumn.Beside, preserveFocus: false },
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                enableCommandUris: true
            }
        );

        graphViewerPanel.onDidDispose(
            () => {
                graphViewerPanel = null;
                allGraphs = {}; // Clear graphs when panel is closed
            },
            null,
            globalContext.subscriptions
        );

        // Handle messages from webview
        graphViewerPanel.webview.onDidReceiveMessage(
            message => {
                if (message.command === 'clearGraphs') {
                    allGraphs = {};
                    updateGraphViewerPanel(host, port);
                }
            },
            undefined,
            globalContext.subscriptions
        );
    }

    // Add new graphs to the collection (or update existing ones)
    const timestamp = Date.now();
    graphs.forEach((graph, index) => {
        allGraphs[graph.name] = {
            ...graph,
            timestamp: timestamp,
            index: index  // Preserve order within batch
        };
    });

    updateGraphViewerPanel(host, port);
    graphViewerPanel.reveal(vscode.ViewColumn.Beside);

    Logger.info(`Displayed ${graphs.length} graph(s) in VS Code webview (total: ${Object.keys(allGraphs).length})`);
}

function updateGraphViewerPanel(host, port) {
    if (!graphViewerPanel) return;

    // Display: last graph at top (duplicated), then all graphs in order
    // e.g., for 4 graphs: graph4, graph1, graph2, graph3, graph4 (5 figures total)
    const allGraphsArray = Object.values(allGraphs);

    // Group by batch (timestamp) and sort batches by timestamp desc
    const batches = {};
    allGraphsArray.forEach(g => {
        const ts = g.timestamp;
        if (!batches[ts]) batches[ts] = [];
        batches[ts].push(g);
    });

    // Build final array: for each batch, last graph first, then all in order
    const graphsArray = [];
    const sortedTimestamps = Object.keys(batches).sort((a, b) => b - a);  // Newest batch first

    for (const ts of sortedTimestamps) {
        const batchGraphs = batches[ts].sort((a, b) => a.index - b.index);  // Sort by index
        if (batchGraphs.length > 1) {
            // Multiple graphs: Add last graph first at top as "Last Graph", then all graphs in order
            const lastGraph = batchGraphs[batchGraphs.length - 1];
            graphsArray.push({ ...lastGraph, displayName: 'Last Graph' });
            batchGraphs.forEach(g => graphsArray.push(g));
        } else if (batchGraphs.length === 1) {
            // Single graph: Just show it once (no need for separate "Last Graph")
            graphsArray.push(batchGraphs[0]);
        }
    }

    // Generate HTML for graphs with timestamps to force reload
    const graphsHtml = graphsArray.map(graph => {
        const graphUrl = `http://${host}:${port}/graphs/${encodeURIComponent(graph.name)}?t=${graph.timestamp}`;
        const displayName = graph.displayName || graph.name;
        return `
            <div class="graph-container" data-graph-name="${escapeHtml(graph.name)}">
                <h3>${escapeHtml(displayName)}</h3>
                <img src="${graphUrl}" alt="${escapeHtml(graph.name)}"
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                <div class="error" style="display:none;">Failed to load graph: ${escapeHtml(graph.name)}</div>
            </div>
        `;
    }).join('');

    graphViewerPanel.webview.html = getGraphViewerHtml(graphsHtml, graphsArray.length);
}

function displayGraphsInBrowser(graphs, host, port) {
    for (const graph of graphs) {
        try {
            // Open each graph in external browser
            const graphUrl = `http://${host}:${port}/graphs/${encodeURIComponent(graph.name)}`;
            console.log(`[displayGraphs] Opening graph in system browser: ${graphUrl}`);

            let openCommand;
            if (IS_MAC) {
                openCommand = `open '${graphUrl.replace(/'/g, "'\\''")}'`;
            } else if (IS_WINDOWS) {
                openCommand = `start "" "${graphUrl}"`;
            } else {
                openCommand = `xdg-open '${graphUrl.replace(/'/g, "'\\''")}'`;
            }

            exec(openCommand, (error) => {
                if (error) {
                    console.error('[displayGraphs] Error opening browser:', error);
                    vscode.window.showErrorMessage(`Failed to open graph ${graph.name}: ${error.message}`);
                } else {
                    console.log(`[displayGraphs] Graph ${graph.name} opened successfully`);
                }
            });

            Logger.info(`Opened graph in external browser: ${graph.name}`);
        } catch (error) {
            Logger.error(`Error displaying graph ${graph.name}: ${error.message}`);
        }
    }
}

function getGraphViewerHtml(graphsHtml, graphCount) {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src http://localhost:* http://127.0.0.1:* https://*; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
    <title>Stata Graphs</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
        }
        .header {
            border-bottom: 2px solid var(--vscode-panel-border);
            padding-bottom: 15px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header-left h1 {
            margin: 0;
            font-size: 24px;
            color: var(--vscode-foreground);
        }
        .header-left .graph-count {
            color: var(--vscode-descriptionForeground);
            font-size: 14px;
            margin-top: 5px;
        }
        .clear-button {
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            transition: background-color 0.2s;
        }
        .clear-button:hover {
            background-color: var(--vscode-button-hoverBackground);
        }
        .graph-container {
            background-color: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 4px;
            padding: 20px;
            margin-bottom: 20px;
            text-align: center;
        }
        .graph-container h3 {
            margin-top: 0;
            margin-bottom: 15px;
            color: var(--vscode-foreground);
            font-size: 16px;
        }
        .graph-container img {
            max-width: 100%;
            height: auto;
            border: 1px solid var(--vscode-panel-border);
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .error {
            color: var(--vscode-errorForeground);
            background-color: var(--vscode-inputValidation-errorBackground);
            padding: 10px;
            border-radius: 4px;
            margin-top: 10px;
        }
        .no-graphs {
            color: var(--vscode-descriptionForeground);
            font-style: italic;
            padding: 20px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <h1>Stata Graphs</h1>
            <div class="graph-count">${graphCount} graph(s) displayed</div>
        </div>
        <button class="clear-button" onclick="clearGraphs()">Clear All</button>
    </div>
    <div id="graphs-container">
        ${graphsHtml || '<div class="no-graphs">No graphs to display</div>'}
    </div>
    <script>
        const vscode = acquireVsCodeApi();

        function clearGraphs() {
            vscode.postMessage({ command: 'clearGraphs' });
        }
    </script>
</body>
</html>`;
}

module.exports = {
    activate,
    deactivate
}; 