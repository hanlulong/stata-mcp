#!/usr/bin/env node

/**
 * Script to install the required Python dependencies for the Stata MCP server.
 * Creates a virtual environment using Python 3.11 and installs dependencies.
 */

const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

console.log('Setting up Python environment for Stata MCP server...');

// Get the extension directory
const extensionDir = path.resolve(__dirname, '..');
const venvPath = path.join(extensionDir, '.venv');

// Define required packages
const requiredPackages = [
    'fastapi',
    'uvicorn',
    'fastapi-mcp',
    'pydantic'
];

// Get Python command based on platform
function getPythonCommand() {
    if (process.platform === 'win32') {
        try {
            // Check if Python 3.11 is available
            execSync('py -3.11 --version', { stdio: 'ignore' });
            return 'py -3.11';
        } catch (error) {
            try {
                // Check if any Python 3.x is available
                execSync('py -3 --version', { stdio: 'ignore' });
                return 'py -3';
            } catch (error) {
                return 'python';
            }
        }
    } else {
        try {
            // Check if python3 is available
            execSync('python3 --version', { stdio: 'ignore' });
            return 'python3';
        } catch (error) {
            return 'python';
        }
    }
}

// Create a virtual environment
function createVirtualEnv() {
    console.log(`Creating virtual environment at ${venvPath}...`);
    
    // Delete existing venv if it exists
    if (fs.existsSync(venvPath)) {
        console.log('Removing existing virtual environment...');
        try {
            if (process.platform === 'win32') {
                execSync(`rmdir /s /q "${venvPath}"`, { stdio: 'inherit' });
            } else {
                execSync(`rm -rf "${venvPath}"`, { stdio: 'inherit' });
            }
        } catch (error) {
            console.error(`Error removing existing venv: ${error.message}`);
        }
    }
    
    // Create venv
    const pythonCmd = getPythonCommand();
    console.log(`Using Python command: ${pythonCmd}`);
    
    return new Promise((resolve, reject) => {
        const createVenvProcess = spawn(
            pythonCmd, 
            ['-m', 'venv', venvPath], 
            { stdio: 'inherit', shell: true }
        );
        
        createVenvProcess.on('close', (code) => {
            if (code === 0) {
                console.log('Virtual environment created successfully.');
                resolve();
            } else {
                console.error(`Failed to create virtual environment. Exit code: ${code}`);
                reject(new Error(`Failed to create virtual environment. Exit code: ${code}`));
            }
        });
        
        createVenvProcess.on('error', (error) => {
            console.error(`Failed to create virtual environment: ${error.message}`);
            reject(error);
        });
    });
}

// Install packages in the virtual environment
function installPackages() {
    console.log('Installing required packages...');
    
    // Get path to pip executable in venv
    let pipPath;
    if (process.platform === 'win32') {
        pipPath = path.join(venvPath, 'Scripts', 'pip.exe');
    } else {
        pipPath = path.join(venvPath, 'bin', 'pip');
    }
    
    // Check if pip exists
    if (!fs.existsSync(pipPath)) {
        console.error(`Pip not found at ${pipPath}`);
        return Promise.reject(new Error('Pip not found in virtual environment'));
    }
    
    // Install each package
    const packageList = requiredPackages.join(' ');
    console.log(`Installing packages: ${packageList}`);
    
    return new Promise((resolve, reject) => {
        const installProcess = spawn(
            pipPath, 
            ['install', ...requiredPackages], 
            { stdio: 'inherit', shell: true }
        );
        
        installProcess.on('close', (code) => {
            if (code === 0) {
                console.log('Packages installed successfully.');
                resolve();
            } else {
                console.error(`Failed to install packages. Exit code: ${code}`);
                reject(new Error(`Failed to install packages. Exit code: ${code}`));
            }
        });
        
        installProcess.on('error', (error) => {
            console.error(`Failed to install packages: ${error.message}`);
            reject(error);
        });
    });
}

// Create a file that records the Python path of the venv to use
function createPythonPathFile() {
    // Get path to Python executable in venv
    let pythonPath;
    if (process.platform === 'win32') {
        pythonPath = path.join(venvPath, 'Scripts', 'python.exe');
    } else {
        pythonPath = path.join(venvPath, 'bin', 'python');
    }
    
    // Check if python exists
    if (!fs.existsSync(pythonPath)) {
        console.error(`Python not found at ${pythonPath}`);
        return false;
    }
    
    // Write path to file
    const pythonPathFile = path.join(extensionDir, '.python-path');
    fs.writeFileSync(pythonPathFile, pythonPath);
    console.log(`Python path saved to ${pythonPathFile}`);
    return true;
}

// Main function
async function main() {
    try {
        console.log('Setting up Python dependencies...');
        await createVirtualEnv();
        await installPackages();
        
        if (createPythonPathFile()) {
            console.log('Python dependencies setup complete.');
        } else {
            console.error('Failed to create Python path file.');
        }
    } catch (error) {
        console.error(`Error setting up Python dependencies: ${error.message}`);
        process.exit(1);
    }
}

// Run main function
main(); 