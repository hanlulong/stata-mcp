#!/usr/bin/env node

/**
 * Post-installation script for Stata MCP extension
 * Creates a virtual environment and installs required Python dependencies
 * This runs automatically after the extension is installed
 */

const { spawn, execSync, exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

console.log('Stata MCP Extension: Post-installation setup starting...');
console.log('Setting up Python environment for Stata MCP server...');

// Get the extension directory
let extensionDir;

// Try multiple methods to determine the extension directory
if (process.env.VSCODE_EXTENSION_PATH) {
    // Running from VSCode extensions directory
    extensionDir = process.env.VSCODE_EXTENSION_PATH;
    console.log(`Using VSCODE_EXTENSION_PATH: ${extensionDir}`);
} else if (process.env.VSCODE_CWD) {
    // Try using VSCode working directory
    extensionDir = process.env.VSCODE_CWD;
    console.log(`Using VSCODE_CWD: ${extensionDir}`);
} else {
    // Determine based on the script location
    extensionDir = path.resolve(__dirname, '..');
    console.log(`Using script directory: ${extensionDir}`);
    
    // Check if we're in the development directory or installed extension
    const packageJson = path.join(extensionDir, 'package.json');
    if (fs.existsSync(packageJson)) {
        try {
            const pkgContent = JSON.parse(fs.readFileSync(packageJson, 'utf8'));
            if (pkgContent.name === 'stata-mcp') {
                console.log('Detected correct extension directory from package.json');
            } else {
                console.log(`Warning: package.json found but name is not stata-mcp: ${pkgContent.name}`);
            }
        } catch (e) {
            console.log(`Warning: Error parsing package.json: ${e.message}`);
        }
    } else {
        console.log(`Warning: package.json not found at ${packageJson}`);
    }
}

// Log detected paths
console.log(`Script directory: ${__dirname}`);
console.log(`Extension directory detected as: ${extensionDir}`);
console.log(`Current directory: ${process.cwd()}`);

// Create a specialized check for VS Code extensions
if (process.platform === 'win32') {
    // Windows VS Code and Cursor paths
    const username = process.env.USERNAME || process.env.USER;
    if (username) {
        // Try VS Code paths
        const vscodePathOptions = [
            `C:\\Users\\${username}\\.vscode\\extensions\\deepecon.stata-mcp-0.0.1`,
            `C:\\Users\\${username}\\AppData\\Local\\Programs\\Microsoft VS Code\\resources\\app\\extensions\\deepecon.stata-mcp-0.0.1`,
            // Cursor paths
            `C:\\Users\\${username}\\.cursor\\extensions\\deepecon.stata-mcp-0.0.1`
        ];
        
        for (const potentialPath of vscodePathOptions) {
            if (fs.existsSync(potentialPath)) {
                console.log(`Found extension directory at ${potentialPath}`);
                extensionDir = potentialPath;
                break;
            }
        }
    }
} else if (process.platform === 'darwin') {
    // macOS VS Code and Cursor paths
    const home = process.env.HOME;
    if (home) {
        const macPathOptions = [
            `${home}/.vscode/extensions/deepecon.stata-mcp-0.0.1`,
            `${home}/Library/Application Support/Code/User/extensions/deepecon.stata-mcp-0.0.1`,
            `${home}/.cursor/extensions/deepecon.stata-mcp-0.0.1`
        ];
        
        for (const potentialPath of macPathOptions) {
            if (fs.existsSync(potentialPath)) {
                console.log(`Found extension directory at ${potentialPath}`);
                extensionDir = potentialPath;
                break;
            }
        }
    }
} else if (process.platform === 'linux') {
    // Linux VS Code and Cursor paths
    const home = process.env.HOME;
    if (home) {
        const linuxPathOptions = [
            `${home}/.vscode/extensions/deepecon.stata-mcp-0.0.1`,
            `${home}/.vscode-server/extensions/deepecon.stata-mcp-0.0.1`,
            `${home}/.cursor/extensions/deepecon.stata-mcp-0.0.1`
        ];
        
        for (const potentialPath of linuxPathOptions) {
            if (fs.existsSync(potentialPath)) {
                console.log(`Found extension directory at ${potentialPath}`);
                extensionDir = potentialPath;
                break;
            }
        }
    }
}

const venvPath = path.join(extensionDir, '.venv');

// Create marker files to indicate setup is in progress
const setupInProgressFile = path.join(extensionDir, '.setup-in-progress');
fs.writeFileSync(setupInProgressFile, new Date().toISOString());

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
    
    // Write path to file (use absolute path)
    const pythonPathFile = path.join(extensionDir, '.python-path');
    fs.writeFileSync(pythonPathFile, pythonPath);
    console.log(`Python path saved to ${pythonPathFile}: ${pythonPath}`);
    
    // Also create a backup copy in case something modifies the original
    const backupPythonPathFile = path.join(extensionDir, '.python-path.backup');
    fs.writeFileSync(backupPythonPathFile, pythonPath);
    
    return true;
}

// Create a verification script in the virtual environment
function createVerificationScript() {
    console.log('Creating verification script...');
    
    // Path to verification script
    const verificationScriptPath = path.join(venvPath, 'verify_packages.py');
    
    // Script content to verify packages are installed
    const scriptContent = `
#!/usr/bin/env python
import sys
import platform

print("Python verification script")
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")
print(f"Platform: {platform.system()} {platform.release()}")

packages = ['fastapi', 'uvicorn', 'fastapi_mcp', 'pydantic']
missing = []

for package in packages:
    try:
        __import__(package)
        print(f"Package {package} is installed")
    except ImportError:
        missing.append(package)
        print(f"Package {package} is NOT installed")

if missing:
    print(f"ERROR: Missing packages: {', '.join(missing)}")
    sys.exit(1)
else:
    print("All packages successfully verified")
    
with open("${path.join(extensionDir, '.packages-verified')}", "w") as f:
    f.write("packages verified\\n")
`.trim();
    
    // Write the verification script
    fs.writeFileSync(verificationScriptPath, scriptContent);
    
    // Make it executable on Unix-like systems
    if (process.platform !== 'win32') {
        try {
            fs.chmodSync(verificationScriptPath, '755');
        } catch (error) {
            console.error(`Error making verification script executable: ${error.message}`);
        }
    }
    
    return verificationScriptPath;
}

// Run the verification script to ensure packages are installed correctly
function verifyPackages() {
    console.log('Verifying installed packages...');
    
    const verificationScriptPath = createVerificationScript();
    
    // Get path to Python executable in venv
    let pythonPath;
    if (process.platform === 'win32') {
        pythonPath = path.join(venvPath, 'Scripts', 'python.exe');
    } else {
        pythonPath = path.join(venvPath, 'bin', 'python');
    }
    
    return new Promise((resolve, reject) => {
        const verifyProcess = spawn(
            pythonPath,
            [verificationScriptPath],
            { stdio: 'inherit', shell: true }
        );
        
        verifyProcess.on('close', (code) => {
            if (code === 0) {
                console.log('Package verification successful.');
                resolve();
            } else {
                console.error(`Package verification failed. Exit code: ${code}`);
                reject(new Error(`Package verification failed. Exit code: ${code}`));
            }
        });
        
        verifyProcess.on('error', (error) => {
            console.error(`Error running verification script: ${error.message}`);
            reject(error);
        });
    });
}

// Main function
async function main() {
    try {
        console.log('Setting up Python dependencies...');
        
        // Make a notification the user can see
        if (process.platform === 'win32') {
            // On Windows, show a notification using powershell
            try {
                exec('powershell -Command "[reflection.assembly]::loadwithpartialname(\'System.Windows.Forms\'); ' +
                     '[System.Windows.Forms.MessageBox]::Show(\'Setting up Python environment for Stata MCP extension. This may take a few minutes.\', ' +
                     '\'Stata MCP Extension\', \'OK\', [System.Windows.Forms.MessageBoxIcon]::Information)"');
            } catch (e) {
                // Ignore errors, this is just a nice-to-have
            }
        } else if (process.platform === 'darwin') {
            // On macOS, try to use osascript
            try {
                exec('osascript -e \'display notification "This may take a few minutes" with title "Stata MCP Extension" subtitle "Setting up Python environment"\'');
            } catch (e) {
                // Ignore errors, this is just a nice-to-have
            }
        }
        
        await createVirtualEnv();
        await installPackages();
        
        if (createPythonPathFile()) {
            console.log('Python path file created successfully.');
            
            // Verify packages were installed correctly
            await verifyPackages();
            
            // Create a completion marker file
            const completionFile = path.join(extensionDir, '.setup-complete');
            fs.writeFileSync(completionFile, new Date().toISOString());
            
            // Remove the in-progress marker
            if (fs.existsSync(setupInProgressFile)) {
                fs.unlinkSync(setupInProgressFile);
            }
            
            console.log('Python dependencies setup complete.');
            
            // Show completion notification
            if (process.platform === 'win32') {
                try {
                    exec('powershell -Command "[reflection.assembly]::loadwithpartialname(\'System.Windows.Forms\'); ' +
                         '[System.Windows.Forms.MessageBox]::Show(\'Python environment setup complete! Stata MCP extension is ready to use.\', ' +
                         '\'Stata MCP Extension\', \'OK\', [System.Windows.Forms.MessageBoxIcon]::Information)"');
                } catch (e) {
                    // Ignore errors
                }
            } else if (process.platform === 'darwin') {
                try {
                    exec('osascript -e \'display notification "Stata MCP extension is ready to use" with title "Setup Complete" subtitle "Python environment ready"\'');
                } catch (e) {
                    // Ignore errors
                }
            }
        } else {
            console.error('Failed to create Python path file.');
        }
    } catch (error) {
        console.error(`Error setting up Python dependencies: ${error.message}`);
        
        // Create error marker file with details
        const errorFile = path.join(extensionDir, '.setup-error');
        fs.writeFileSync(errorFile, `${new Date().toISOString()}\n${error.message}\n${error.stack || ''}`);
        
        // Remove the in-progress marker
        if (fs.existsSync(setupInProgressFile)) {
            fs.unlinkSync(setupInProgressFile);
        }
        
        process.exit(1);
    }
}

// Run main function
main(); 