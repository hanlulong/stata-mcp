#!/usr/bin/env node

/**
 * Platform compatibility test script for Stata MCP Extension
 * 
 * This script tests various aspects of the extension to verify compatibility with
 * the current platform (Windows, macOS, or Linux)
 */

const { spawnSync, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

// Platform-specific information
const platform = process.platform;
const isWindows = platform === 'win32';
const isMacOS = platform === 'darwin';
const isLinux = !isWindows && !isMacOS;
const platformName = isWindows ? 'Windows' : isMacOS ? 'macOS' : 'Linux';

console.log(`=== Stata MCP Extension Platform Test ===`);
console.log(`Testing on: ${platformName} (${os.release()})`);
console.log(`Node.js: ${process.version}`);
console.log(`Architecture: ${os.arch()}`);
console.log();

// Get extension directory
const extensionDir = path.resolve(__dirname, '..');
console.log(`Extension directory: ${extensionDir}`);

// Check for virtual environment
const venvPath = path.join(extensionDir, '.venv');
const venvBinDir = isWindows ? path.join(venvPath, 'Scripts') : path.join(venvPath, 'bin');
const venvPython = isWindows ? path.join(venvBinDir, 'python.exe') : path.join(venvBinDir, 'python');
const venvPip = isWindows ? path.join(venvBinDir, 'pip.exe') : path.join(venvBinDir, 'pip');

function checkVenv() {
    console.log('\n=== Virtual Environment ===');
    
    if (fs.existsSync(venvPath)) {
        console.log(`✅ Virtual environment exists at: ${venvPath}`);
    } else {
        console.log(`❌ Virtual environment not found at: ${venvPath}`);
        return false;
    }
    
    if (fs.existsSync(venvPython)) {
        try {
            const output = execSync(`"${venvPython}" --version`, { encoding: 'utf8' });
            console.log(`✅ Python version: ${output.trim()}`);
        } catch (err) {
            console.log(`❌ Failed to get Python version: ${err.message}`);
            return false;
        }
    } else {
        console.log(`❌ Python executable not found in virtual environment`);
        return false;
    }
    
    return true;
}

function checkDependencies() {
    console.log('\n=== Python Dependencies ===');
    
    const requiredPackages = ['fastapi', 'uvicorn', 'fastapi_mcp', 'pydantic'];
    
    for (const pkg of requiredPackages) {
        try {
            // Handle the case for fastapi_mcp differently since it might not have a __version__ attribute
            if (pkg === 'fastapi_mcp') {
                const cmd = `"${venvPython}" -c "import ${pkg}; print(f'${pkg} is installed')"`;
                const output = execSync(cmd, { encoding: 'utf8' });
                console.log(`✅ ${output.trim()}`);
            } else {
                const cmd = `"${venvPython}" -c "import ${pkg}; print(f'${pkg} version: {${pkg}.__version__}')"`;
                const output = execSync(cmd, { encoding: 'utf8' });
                console.log(`✅ ${output.trim()}`);
            }
        } catch (err) {
            console.log(`❌ Package '${pkg}' not found or couldn't be imported`);
            return false;
        }
    }
    
    return true;
}

function checkServerScript() {
    console.log('\n=== MCP Server Script ===');
    
    const serverScript = path.join(extensionDir, 'stata_mcp_server.py');
    
    if (fs.existsSync(serverScript)) {
        console.log(`✅ Server script found at: ${serverScript}`);
    } else {
        console.log(`❌ Server script not found at: ${serverScript}`);
        return false;
    }
    
    // Check if executable
    try {
        fs.accessSync(serverScript, fs.constants.X_OK);
        console.log('✅ Server script is executable');
    } catch (err) {
        console.log('⚠️ Server script is not executable, but this may be OK on some platforms');
    }
    
    return true;
}

function findStata() {
    console.log('\n=== Stata Installation ===');
    
    let possiblePaths = [];
    
    if (isWindows) {
        const programFiles = process.env.ProgramFiles || 'C:\\Program Files';
        const programFilesX86 = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)';
        
        possiblePaths = [
            path.join(programFiles, 'Stata18'),
            path.join(programFiles, 'Stata17'),
            path.join(programFiles, 'Stata16'),
            path.join(programFilesX86, 'Stata18'),
            path.join(programFilesX86, 'Stata17'),
            path.join(programFilesX86, 'Stata16')
        ];
    } else if (isMacOS) {
        possiblePaths = [
            '/Applications/Stata18',
            '/Applications/Stata17',
            '/Applications/Stata16',
            '/Applications/Stata'
        ];
    } else if (isLinux) {
        possiblePaths = [
            '/usr/local/stata18',
            '/usr/local/stata17',
            '/usr/local/stata16',
            '/usr/local/stata'
        ];
    }
    
    for (const p of possiblePaths) {
        if (fs.existsSync(p)) {
            console.log(`✅ Stata found at: ${p}`);
            return p;
        }
    }
    
    console.log(`❌ Stata not found in common locations`);
    return null;
}

function testPort(port) {
    console.log(`\n=== Testing Port ${port} ===`);
    
    // Check if port is available
    try {
        const cmd = isWindows 
            ? `netstat -ano | findstr :${port} | findstr LISTENING`
            : `lsof -i:${port} | grep LISTEN`;
        
        const output = execSync(cmd, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
        
        if (output.trim()) {
            console.log(`❌ Port ${port} is in use`);
            console.log(`Process using port: ${output.trim()}`);
            return false;
        }
    } catch (err) {
        // If command fails, it usually means no process is using the port
        console.log(`✅ Port ${port} appears to be available`);
        return true;
    }
    
    return false;
}

function testServerStart() {
    console.log('\n=== Testing Server Startup ===');
    
    const testPort = 4567; // Use a non-standard port for testing
    const startServerScript = path.join(__dirname, 'start-server.js');
    
    if (!fs.existsSync(startServerScript)) {
        console.log(`❌ Start server script not found at: ${startServerScript}`);
        return false;
    }
    
    console.log('Starting server process...');
    const serverProcess = spawnSync('node', [
        startServerScript, 
        '--port', testPort.toString(),
        '--log-level', 'DEBUG'
    ], {
        cwd: extensionDir,
        stdio: 'inherit',
        timeout: 10000 // 10 second timeout
    });
    
    if (serverProcess.status !== 0) {
        console.log(`❌ Server failed to start with exit code: ${serverProcess.status}`);
        return false;
    }
    
    console.log('✅ Server started successfully');
    return true;
}

function checkNodeDependencies() {
    console.log('\n=== Node.js Dependencies ===');
    
    try {
        const packageJson = JSON.parse(fs.readFileSync(path.join(extensionDir, 'package.json'), 'utf8'));
        const dependencies = packageJson.dependencies || {};
        
        console.log('Required Node.js dependencies:');
        for (const [pkg, version] of Object.entries(dependencies)) {
            console.log(`  - ${pkg}: ${version}`);
            
            try {
                require.resolve(pkg);
                console.log(`    ✅ Package can be loaded`);
            } catch (err) {
                console.log(`    ❌ Package failed to load: ${err.message}`);
            }
        }
    } catch (err) {
        console.log(`❌ Failed to check Node.js dependencies: ${err.message}`);
        return false;
    }
    
    return true;
}

// Run the tests
let testsPassed = true;

testsPassed = checkVenv() && testsPassed;
testsPassed = checkDependencies() && testsPassed;
testsPassed = checkServerScript() && testsPassed;
testsPassed = findStata() !== null && testsPassed;
testsPassed = testPort(4000) && testsPassed;
testsPassed = checkNodeDependencies() && testsPassed;
// testsPassed = testServerStart() && testsPassed; // Uncomment this for a full test

// Summary
console.log('\n=== Test Summary ===');
if (testsPassed) {
    console.log('✅ All tests passed! The extension should work on this platform.');
} else {
    console.log('❌ Some tests failed. Please check the issues above.');
}

process.exit(testsPassed ? 0 : 1); 