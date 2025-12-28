#!/usr/bin/env node

/**
 * Script to setup Python environment using uv
 * Using this simplified approach:
 * 1. Check if uv is installed
 * 2. If not installed, try to install it automatically
 * 3. If installation fails, prompt user to install manually
 * 4. Create Python 3.11 virtual environment with uv
 * 5. Install dependencies and setup the environment
 */

const { execSync, exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

// Extension directory
const extensionDir = __dirname ? path.dirname(__dirname) : process.cwd();

// File to store Python path
const pythonPathFile = path.join(extensionDir, '.python-path');
const uvPathFile = path.join(extensionDir, '.uv-path');
const setupCompleteFile = path.join(extensionDir, '.setup-complete');

console.log('Checking for UV and setting up Python environment...');
console.log(`Extension directory: ${extensionDir}`);

// Execute a command as a promise
function execPromise(command) {
    return new Promise((resolve, reject) => {
        exec(command, { maxBuffer: 1024 * 1024 * 10 }, (error, stdout, stderr) => {
            if (error) {
                error.stdout = stdout;
                error.stderr = stderr;
                reject(error);
            } else {
                resolve(stdout);
            }
        });
    });
}

// Helper function to check if a file is executable
function isExecutable(filePath) {
    try {
        fs.accessSync(filePath, fs.constants.X_OK);
        return true;
    } catch (err) {
        return false;
    }
}

// Function to display UV installation instructions based on platform
function promptUvInstallation() {
    console.log('\n==================================================');
    console.log('MANUAL UV INSTALLATION REQUIRED');
    console.log('==================================================');
    console.log('Please install UV manually using one of the following commands:');
    
    if (process.platform === 'win32') {
        console.log('\nFor Windows (run in PowerShell as Administrator):');
        console.log('powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"');
    } else {
        console.log('\nFor macOS/Linux:');
        console.log('Option 1 (may require sudo): curl -LsSf https://astral.sh/uv/install.sh | sudo sh');
        console.log('Option 2 (user install): curl -LsSf https://astral.sh/uv/install.sh | sh');
    }
    
    console.log('\nAfter installation:');
    console.log('1. Restart your IDE completely');
    console.log('2. Verify UV is installed by running "uv --version" in a terminal');
    console.log('3. The extension will use UV automatically when restarted');
    console.log('==================================================');
}

// Check if UV is installed
function isUvInstalled() {
    console.log('\n========== CHECKING FOR UV ==========');
    
    // Default response object
    const result = { installed: false, path: null };
    
    // First check if we have a saved path
    if (fs.existsSync(uvPathFile)) {
        const savedPath = fs.readFileSync(uvPathFile, 'utf8').trim();
        console.log(`Found saved UV path: ${savedPath}`);
        
        // Validate that the saved path is compatible with current platform
        const isWin32 = process.platform === 'win32';
        const pathHasBackslash = savedPath.includes('\\');
        
        if ((isWin32 && !pathHasBackslash) || (!isWin32 && pathHasBackslash)) {
            console.log(`Warning: Saved UV path is not compatible with current platform (${process.platform}). Ignoring saved path.`);
            try {
                fs.unlinkSync(uvPathFile);
                console.log(`Removed incompatible saved path file: ${uvPathFile}`);
            } catch (error) {
                console.warn(`Failed to remove saved path file: ${error.message}`);
            }
        } else if (fs.existsSync(savedPath) && isExecutable(savedPath)) {
            console.log(`Verified UV at saved path: ${savedPath}`);
            return { installed: true, path: savedPath };
        } else {
            console.log(`Saved UV path doesn't exist or is not executable: ${savedPath}`);
            try {
                fs.unlinkSync(uvPathFile);
                console.log(`Removed invalid saved path file: ${uvPathFile}`);
            } catch (error) {
                console.warn(`Failed to remove saved path file: ${error.message}`);
            }
        }
    }
    
    // Try running 'uv --version' to see if it's in PATH
    try {
        const version = execSync('uv --version', { stdio: 'pipe' }).toString().trim();
        console.log(`Found UV in PATH: version ${version}`);
        
        // Get the actual path to the UV executable
        let uvPath = 'uv'; // Default if we can't determine the actual path
        
        try {
            if (process.platform === 'win32') {
                const pathOutput = execSync('where uv', { stdio: 'pipe' }).toString().trim().split('\n')[0];
                uvPath = pathOutput;
            } else {
                const pathOutput = execSync('which uv', { stdio: 'pipe' }).toString().trim();
                uvPath = pathOutput;
            }
            console.log(`UV full path: ${uvPath}`);
            
            // Save the path for future use
            fs.writeFileSync(uvPathFile, uvPath, { encoding: 'utf8' });
            console.log(`Saved UV path to ${uvPathFile}`);
        } catch (pathError) {
            console.log(`Could not determine UV path: ${pathError.message}`);
        }
        
        return { installed: true, path: uvPath };
    } catch (error) {
        console.log('UV not found in PATH');
        
        // Check in common install locations
        const homeDir = os.homedir();
        const commonPaths = [];
        
        if (process.platform === 'win32') {
            commonPaths.push(
                path.join(homeDir, '.local', 'bin', 'uv.exe'),  // Common install location
                path.join(homeDir, '.cargo', 'bin', 'uv.exe'),
                path.join(homeDir, 'AppData', 'Local', 'uv', 'uv.exe'),
                path.join(homeDir, 'AppData', 'Local', 'Programs', 'uv', 'uv.exe'),
                path.join('C:', 'ProgramData', 'uv', 'uv.exe')
            );
        } else {
            commonPaths.push(
                path.join(homeDir, '.cargo', 'bin', 'uv'),
                path.join(homeDir, '.local', 'bin', 'uv'),
                '/usr/local/bin/uv',
                '/opt/homebrew/bin/uv',
                '/opt/local/bin/uv',
                '/usr/bin/uv'
            );
        }
        
        console.log('Checking common installation locations...');
        for (const uvPath of commonPaths) {
            console.log(`Checking ${uvPath}...`);
            if (fs.existsSync(uvPath) && isExecutable(uvPath)) {
                console.log(`Found UV at: ${uvPath}`);
                
                // Verify it works
                try {
                    const version = execSync(`"${uvPath}" --version`, { stdio: 'pipe' }).toString().trim();
                    console.log(`Verified UV at ${uvPath}: version ${version}`);
                    
                    // Save the path for future use
                    fs.writeFileSync(uvPathFile, uvPath, { encoding: 'utf8' });
                    console.log(`Saved UV path to ${uvPathFile}`);
                    
                    return { installed: true, path: uvPath };
                } catch (verifyError) {
                    console.log(`Found UV at ${uvPath} but verification failed: ${verifyError.message}`);
                }
            }
        }
        
        console.log('UV not found in any common installation locations');
        return result;
    }
}

// Install UV
async function installUv() {
    console.log('\n========== INSTALLING UV ==========');
    console.log(`Installing uv on ${process.platform}...`);
    
    try {
        let installCommand;
        
        if (process.platform === 'win32') {
            installCommand = 'powershell -ExecutionPolicy ByPass -Command "& {irm https://astral.sh/uv/install.ps1 | iex}"';
        } else {
            // Try to create the target directory with proper permissions first
            try {
                fs.mkdirSync(path.join(os.homedir(), '.local', 'bin'), { recursive: true });
            } catch (err) {
                console.log(`Note: Could not ensure ~/.local/bin exists: ${err.message}`);
            }
            
            // Use the user-level install (no sudo)
            installCommand = 'curl -LsSf https://astral.sh/uv/install.sh | sh';
        }
        
        console.log(`Running: ${installCommand}`);
        
        try {
            const stdout = await execPromise(installCommand);
            console.log(`Installation output: ${stdout}`);
            
            // Check if installation was successful
            const uvInfo = isUvInstalled();
            
            if (uvInfo.installed) {
                console.log(`UV successfully installed at: ${uvInfo.path}`);
                return uvInfo;
            } else {
                // Try alternative installation if the first method failed
                console.log('First installation method failed, trying alternative...');
                
                if (process.platform === 'win32') {
                    // Alternative Windows installation using direct download
                    const tempDir = path.join(os.tmpdir(), 'uv-installer');
                    try {
                        if (!fs.existsSync(tempDir)) {
                            fs.mkdirSync(tempDir, { recursive: true });
                        }
                        
                        const downloadCommand = 'powershell -Command "& {Invoke-WebRequest -Uri https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip -OutFile uv.zip}"';
                        await execPromise(`cd "${tempDir}" && ${downloadCommand}`);
                        
                        await execPromise(`cd "${tempDir}" && powershell -Command "& {Expand-Archive -Path uv.zip -DestinationPath .}""`);
                        
                        const userBinDir = path.join(os.homedir(), '.local', 'bin');
                        if (!fs.existsSync(userBinDir)) {
                            fs.mkdirSync(userBinDir, { recursive: true });
                        }
                        
                        fs.copyFileSync(path.join(tempDir, 'uv.exe'), path.join(userBinDir, 'uv.exe'));
                        console.log(`Copied UV to ${path.join(userBinDir, 'uv.exe')}`);
                        
                        // Check installation again
                        return isUvInstalled();
                    } catch (altError) {
                        console.error(`Alternative installation failed: ${altError.message}`);
                        console.error('Please install UV manually.');
                        promptUvInstallation();
                        return { installed: false, path: null };
                    }
                } else {
                    // Alternative macOS/Linux installation - download binary directly
                    let platform = 'unknown';
                    let arch = process.arch;
                    
                    if (process.platform === 'darwin') {
                        platform = 'apple-darwin';
                        // Handle ARM vs Intel Mac
                        arch = process.arch === 'arm64' ? 'aarch64' : 'x86_64';
                    } else if (process.platform === 'linux') {
                        platform = 'unknown-linux-gnu';
                        // Handle ARM vs x86
                        arch = process.arch === 'arm64' ? 'aarch64' : 'x86_64';
                    }
                    
                    if (platform !== 'unknown') {
                        const binaryName = `uv-${arch}-${platform}`;
                        const downloadUrl = `https://github.com/astral-sh/uv/releases/latest/download/${binaryName}.tar.gz`;
                        
                        const tempDir = path.join(os.tmpdir(), 'uv-installer');
                        try {
                            if (!fs.existsSync(tempDir)) {
                                fs.mkdirSync(tempDir, { recursive: true });
                            }
                            
                            await execPromise(`cd "${tempDir}" && curl -L ${downloadUrl} -o uv.tar.gz`);
                            await execPromise(`cd "${tempDir}" && tar xzf uv.tar.gz`);
                            
                            const userBinDir = path.join(os.homedir(), '.local', 'bin');
                            if (!fs.existsSync(userBinDir)) {
                                fs.mkdirSync(userBinDir, { recursive: true });
                            }
                            
                            fs.copyFileSync(path.join(tempDir, 'uv'), path.join(userBinDir, 'uv'));
                            fs.chmodSync(path.join(userBinDir, 'uv'), '755'); // Make executable
                            console.log(`Copied UV to ${path.join(userBinDir, 'uv')}`);
                            
                            // Update PATH for the current process
                            process.env.PATH = `${userBinDir}:${process.env.PATH}`;
                            
                            // Check installation again
                            return isUvInstalled();
                        } catch (altError) {
                            console.error(`Alternative installation failed: ${altError.message}`);
                            console.error('Please install UV manually.');
                            promptUvInstallation();
                            return { installed: false, path: null };
                        }
                    } else {
                        console.error(`Unsupported platform: ${process.platform}`);
                        promptUvInstallation();
                        return { installed: false, path: null };
                    }
                }
            }
        } catch (installError) {
            console.error(`Installation script failed: ${installError.message}`);
            console.error(`stdout: ${installError.stdout || 'none'}`);
            console.error(`stderr: ${installError.stderr || 'none'}`);
            console.error('Failed to install uv. Please install it manually.');
            promptUvInstallation();
            return { installed: false, path: null };
        }
    } catch (error) {
        console.error(`Failed to install uv: ${error.message}`);
        promptUvInstallation();
        return { installed: false, path: null };
    }
}

// Setup Python with UV
async function setupPythonWithUv() {
    console.log('\n========== SETTING UP PYTHON WITH UV ==========');
    
    // Check if uv is installed or install it
    let uvInfo = isUvInstalled();
    
    if (!uvInfo.installed) {
        console.log('uv not found, attempting to install...');
        uvInfo = await installUv();
        
        if (!uvInfo.installed) {
            console.error('Failed to install uv. Cannot proceed with Python setup.');
            promptUvInstallation();
            return false;
        }
    }
    
    console.log(`Using uv at: ${uvInfo.path}`);
    
    // Create a Python virtual environment
    const venvPath = path.join(extensionDir, '.venv');
    console.log(`Setting up Python virtual environment at: ${venvPath}`);
    
    // First clean up any existing venv
    if (fs.existsSync(venvPath)) {
        console.log(`Removing existing venv at ${venvPath}`);
        try {
            await execPromise(`${process.platform === 'win32' ? 'rmdir /s /q' : 'rm -rf'} "${venvPath}"`);
            console.log('Successfully removed existing venv');
        } catch (error) {
            console.warn(`Warning: Failed to remove existing venv: ${error.message}`);
            // Continue anyway, we'll try to work with the existing venv
        }
    }
    
    console.log(`Creating a new venv at ${venvPath}`);
    
    // Create venv with uv
    try {
        const uvCmd = uvInfo.path === 'uv' ? 'uv' : `"${uvInfo.path}"`;
        const createVenvCmd = `${uvCmd} venv "${venvPath}" --python 3.11`;
        console.log(`Running: ${createVenvCmd}`);
        
        await execPromise(createVenvCmd);
        console.log('Successfully created Python virtual environment with uv');
        
        // Install dependencies using uv instead of pip
        const requirementsPath = path.join(extensionDir, 'src', 'requirements.txt');
        if (fs.existsSync(requirementsPath)) {
            console.log('Installing Python dependencies using uv...');
            
            try {
                // Determine Python executable path based on platform
                const pythonPath = process.platform === 'win32'
                    ? path.join(venvPath, 'Scripts', 'python.exe')
                    : path.join(venvPath, 'bin', 'python');
                    
                // Install dependencies using uv pip instead of regular pip
                const installCmd = `${uvCmd} pip install --python "${pythonPath}" -r "${requirementsPath}"`;
                console.log(`Running: ${installCmd}`);
                
                await execPromise(installCmd);
                console.log('Successfully installed Python dependencies with uv');
                
                // Verify Python path and write to file
                if (fs.existsSync(pythonPath)) {
                    try {
                        // Create Python path file
                        fs.writeFileSync(pythonPathFile, pythonPath, { encoding: 'utf8' });
                        console.log(`Python path saved to ${pythonPathFile}`);
                        
                        // Create setup complete marker
                        fs.writeFileSync(setupCompleteFile, new Date().toISOString(), { encoding: 'utf8' });
                        console.log(`Setup complete marker created at ${setupCompleteFile}`);
                        
                        return true;
                    } catch (error) {
                        console.error(`Error writing setup files: ${error.message}`);
                        promptUvInstallation();
                        return false;
                    }
                } else {
                    console.error(`Python executable not found at expected path: ${pythonPath}`);
                    promptUvInstallation();
                    return false;
                }
            } catch (error) {
                console.error(`Error installing Python dependencies with uv: ${error.message}`);
                promptUvInstallation();
                return false;
            }
        } else {
            console.log('No requirements.txt found. Skipping dependency installation.');
            
            // Verify Python path exists even without requirements
            const pythonPath = process.platform === 'win32'
                ? path.join(venvPath, 'Scripts', 'python.exe')
                : path.join(venvPath, 'bin', 'python');
                
            if (fs.existsSync(pythonPath)) {
                // Create Python path file
                fs.writeFileSync(pythonPathFile, pythonPath, { encoding: 'utf8' });
                console.log(`Python path saved to ${pythonPathFile}`);
                
                // Create setup complete marker
                fs.writeFileSync(setupCompleteFile, new Date().toISOString(), { encoding: 'utf8' });
                console.log(`Setup complete marker created at ${setupCompleteFile}`);
                
                return true;
            } else {
                console.error(`Python executable not found at expected path: ${pythonPath}`);
                promptUvInstallation();
                return false;
            }
        }
    } catch (error) {
        console.error(`Error creating venv with uv: ${error.message}`);
        promptUvInstallation();
        return false;
    }
}

// Main function
async function main() {
    console.log(`Running Python setup in ${extensionDir}`);
    
    // Clean up any existing .uv-path when packaging the extension
    if (process.env.NODE_ENV === 'production' && fs.existsSync(uvPathFile)) {
        console.log(`Removing .uv-path in production mode: ${uvPathFile}`);
        try {
            fs.unlinkSync(uvPathFile);
        } catch (error) {
            console.warn(`Failed to remove .uv-path in production mode: ${error.message}`);
        }
    }
    
    // If setup is already complete and recent, skip
    if (fs.existsSync(setupCompleteFile) && fs.existsSync(pythonPathFile)) {
        const setupTime = new Date(fs.readFileSync(setupCompleteFile, 'utf8'));
        const now = new Date();
        const hoursSinceSetup = (now - setupTime) / (1000 * 60 * 60);
        
        if (hoursSinceSetup < 24) {  // Only use cache for 24 hours
            const pythonPath = fs.readFileSync(pythonPathFile, 'utf8').trim();
            
            if (fs.existsSync(pythonPath) && isExecutable(pythonPath)) {
                console.log(`Python setup already complete (${hoursSinceSetup.toFixed(2)} hours ago)`);
                console.log(`Using cached Python path: ${pythonPath}`);
                return 0;
            }
        }
    }
    
    try {
        // STEP 1: Check for UV installation
        let uvInfo = isUvInstalled();
        
        // STEP 2: If UV not found, try to install it
        if (!uvInfo.installed) {
            console.log('UV not found, attempting installation...');
            uvInfo = await installUv();
            
            // STEP 3: If installation fails, prompt user with manual instructions
            if (!uvInfo.installed) {
                console.error('Failed to install UV automatically.');
                promptUvInstallation();
                return 1;
            }
        }
        
        console.log(`UV found at: ${uvInfo.path}`);
        
        // STEP 4: Setup Python virtual environment with UV
        const success = await setupPythonWithUv();
        
        if (success) {
            console.log('\nSetup completed successfully!');
            return 0;
        } else {
            console.error('\nSetup failed: Failed to setup Python with UV');
            return 1;
        }
    } catch (error) {
        console.error(`\nSetup failed: ${error.message}`);
        return 1;
    }
}

// Run the main function
main().then(exitCode => {
    process.exit(exitCode);
}).catch(error => {
    console.error(`Unhandled exception: ${error.message}`);
    process.exit(1);
}); 