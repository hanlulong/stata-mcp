#!/usr/bin/env node

/**
 * Script to start the Stata MCP server.
 * This is a cross-platform alternative to using bash scripts.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

// Default options
const defaultOptions = {
    port: 4000,
    host: 'localhost',
    stataPath: '',
    logLevel: 'INFO',
    forcePort: false
};

// Parse command line arguments
const args = process.argv.slice(2);
const options = { ...defaultOptions };

for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--port' && i + 1 < args.length) {
        options.port = parseInt(args[i + 1], 10);
        i++;
    } else if (arg === '--host' && i + 1 < args.length) {
        options.host = args[i + 1];
        i++;
    } else if (arg === '--stata-path' && i + 1 < args.length) {
        options.stataPath = args[i + 1];
        i++;
    } else if (arg === '--log-level' && i + 1 < args.length) {
        options.logLevel = args[i + 1].toUpperCase();
        i++;
    } else if (arg === '--force-port') {
        options.forcePort = true;
    } else if (arg === '--help') {
        console.log(`
Usage: node start-server.js [options]

Options:
  --port PORT           Port to run the server on (default: 4000)
  --host HOST           Host to bind to (default: localhost)
  --stata-path PATH     Path to Stata installation
  --log-level LEVEL     Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  --force-port          Force the specified port, killing any process using it
  --help                Show this help message
        `);
        process.exit(0);
    }
}

// Try to find the server script
const extensionDir = path.resolve(__dirname, '..');
const possibleServerPaths = [
    path.join(extensionDir, 'stata_mcp_server.py'),
    path.join(extensionDir, 'scripts', 'stata_mcp_server.py')
];

let serverScript = null;
for (const p of possibleServerPaths) {
    if (fs.existsSync(p)) {
        serverScript = p;
        break;
    }
}

if (!serverScript) {
    console.error('Error: Cannot find stata_mcp_server.py script.');
    process.exit(1);
}

// Determine Python command based on platform
const isPythonInstalled = (cmd) => {
    try {
        require('child_process').execSync(`${cmd} --version`, { stdio: 'ignore' });
        return true;
    } catch (e) {
        return false;
    }
};

// Check for virtual environment Python first
const venvPythonPath = path.join(extensionDir, '.venv', 'bin', 'python');
let pythonCmd = '';

if (fs.existsSync(venvPythonPath)) {
    pythonCmd = venvPythonPath;
    console.log('Using Python from virtual environment');
} else if (process.platform === 'win32') {
    // Check for Python 3.11 specifically
    if (isPythonInstalled('python3.11')) {
        pythonCmd = 'python3.11';
    } else if (isPythonInstalled('python')) {
        pythonCmd = 'python';
    } else if (isPythonInstalled('py')) {
        pythonCmd = 'py';
    }
} else {
    // On Unix systems (macOS, Linux)
    if (isPythonInstalled('python3.11')) {
        pythonCmd = 'python3.11';
    } else if (isPythonInstalled('python3')) {
        pythonCmd = 'python3';
    } else if (isPythonInstalled('python')) {
        pythonCmd = 'python';
    }
}

if (!pythonCmd) {
    console.error('Error: Python not found. Please install Python 3.11 and make sure it is in your PATH.');
    process.exit(1);
}

// Build command arguments
const cmdArgs = [serverScript, '--port', options.port.toString(), '--host', options.host, '--log-level', options.logLevel];

if (options.stataPath) {
    cmdArgs.push('--stata-path', options.stataPath);
}

if (options.forcePort) {
    cmdArgs.push('--force-port');
}

console.log(`Starting Stata MCP server with command: ${pythonCmd} ${cmdArgs.join(' ')}`);

// Spawn the process
const serverProcess = spawn(pythonCmd, cmdArgs, {
    cwd: path.dirname(serverScript),
    stdio: 'inherit',
    detached: false
});

// Handle process events
serverProcess.on('error', (err) => {
    console.error(`Failed to start server: ${err.message}`);
    process.exit(1);
});

// Don't let the script exit immediately
process.stdin.resume();

// Handle clean shutdown
const cleanup = () => {
    if (serverProcess) {
        console.log('Shutting down Stata MCP server...');
        if (process.platform === 'win32') {
            spawn('taskkill', ['/pid', serverProcess.pid, '/f', '/t']);
        } else {
            serverProcess.kill('SIGINT');
        }
    }
    process.exit(0);
};

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup); 