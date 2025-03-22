#!/usr/bin/env node

/**
 * Extension functionality test script for Stata MCP Extension
 * 
 * This script tests the extension functionality by running various Stata commands
 * and validating the results.
 */

const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const axios = require('axios');

// Configuration
const config = {
    port: 4789, // Use a non-standard port for testing
    host: 'localhost',
    timeout: 30000, // 30 seconds
    testDataDir: path.join(__dirname, '..', 'test_samples')
};

// Create test data directory if it doesn't exist
if (!fs.existsSync(config.testDataDir)) {
    fs.mkdirSync(config.testDataDir, { recursive: true });
}

// Platform detection
const isWindows = process.platform === 'win32';
const isMacOS = process.platform === 'darwin';
const platformName = isWindows ? 'Windows' : isMacOS ? 'macOS' : 'Linux';

console.log(`=== Stata MCP Extension Functionality Test ===`);
console.log(`Testing on: ${platformName} (${os.release()})`);
console.log(`Testing server on: ${config.host}:${config.port}`);
console.log();

// Get extension directory
const extensionDir = path.resolve(__dirname, '..');
console.log(`Extension directory: ${extensionDir}`);

// Get venv Python
const venvPath = path.join(extensionDir, '.venv');
const venvBinDir = isWindows ? path.join(venvPath, 'Scripts') : path.join(venvPath, 'bin');
const venvPython = isWindows ? path.join(venvBinDir, 'python.exe') : path.join(venvBinDir, 'python');

// Create a simple test dataset
function createTestData() {
    console.log('\n=== Creating Test Data ===');
    
    const testDoFile = path.join(config.testDataDir, 'test.do');
    const testDataFile = path.join(config.testDataDir, 'auto.dta');
    
    // Create a test .do file
    const doFileContent = `
// Test Stata script for MCP extension
clear
sysuse auto, clear
describe
summarize price mpg
reg price mpg weight
save "${testDataFile}", replace
`;
    
    try {
        fs.writeFileSync(testDoFile, doFileContent);
        console.log(`✅ Created test .do file at: ${testDoFile}`);
        return testDoFile;
    } catch (err) {
        console.log(`❌ Failed to create test .do file: ${err.message}`);
        return null;
    }
}

// Start the server
async function startServer() {
    console.log('\n=== Starting MCP Server ===');
    
    // Kill any existing process on the port
    try {
        if (isWindows) {
            execSync(`FOR /F "tokens=5" %P IN ('netstat -ano ^| findstr :${config.port} ^| findstr LISTENING') DO taskkill /F /PID %P`);
        } else {
            execSync(`lsof -t -i:${config.port} | xargs -r kill -9`);
        }
        console.log(`✅ Killed any existing processes on port ${config.port}`);
    } catch (err) {
        // Ignore errors, it's just a precaution
    }
    
    // Start the server
    const serverScript = path.join(extensionDir, 'stata_mcp_server.py');
    const serverProcess = spawn(venvPython, [
        serverScript,
        '--port', config.port.toString(),
        '--host', config.host,
        '--log-level', 'INFO',
        '--force-port'
    ], {
        stdio: ['ignore', 'pipe', 'pipe'],
        detached: true
    });
    
    // Log server output
    serverProcess.stdout.on('data', (data) => {
        console.log(`[Server] ${data.toString().trim()}`);
    });
    
    serverProcess.stderr.on('data', (data) => {
        console.error(`[Server Error] ${data.toString().trim()}`);
    });
    
    // Handle server exit
    serverProcess.on('exit', (code) => {
        if (code !== null && code !== 0) {
            console.log(`❌ Server exited with code ${code}`);
        }
    });
    
    // Wait for the server to start
    console.log('Waiting for server to start...');
    let isRunning = false;
    const maxAttempts = 10;
    let attempts = 0;
    
    while (!isRunning && attempts < maxAttempts) {
        try {
            await new Promise(resolve => setTimeout(resolve, 1000));
            const response = await axios.get(`http://${config.host}:${config.port}/health`);
            if (response.status === 200) {
                console.log(`✅ Server is running on ${config.host}:${config.port}`);
                isRunning = true;
            }
        } catch (err) {
            attempts++;
            console.log(`Attempt ${attempts}/${maxAttempts}: Server not ready yet...`);
        }
    }
    
    if (!isRunning) {
        console.log(`❌ Failed to start server after ${maxAttempts} attempts`);
        return null;
    }
    
    return serverProcess;
}

// Test running a Stata command
async function testRunCommand(command) {
    console.log(`\n=== Testing Stata Command: ${command} ===`);
    
    try {
        const response = await axios.post(
            `http://${config.host}:${config.port}/v1/tools`,
            {
                tool: 'stata_run_selection',
                parameters: { selection: command }
            },
            {
                headers: { 'Content-Type': 'application/json' },
                timeout: config.timeout
            }
        );
        
        if (response.status === 200 && response.data.status === 'success') {
            console.log(`✅ Command executed successfully`);
            console.log('--- Output ---');
            console.log(response.data.result || '(No output)');
            return true;
        } else {
            console.log(`❌ Command failed: ${response.data.message || 'Unknown error'}`);
            return false;
        }
    } catch (err) {
        console.log(`❌ Error executing command: ${err.message}`);
        return false;
    }
}

// Test running a Stata selection
async function testRunSelection(selection) {
    console.log(`\n=== Testing Stata Selection ===`);
    console.log(selection);
    
    try {
        const response = await axios.post(
            `http://${config.host}:${config.port}/v1/tools`,
            {
                tool: 'stata_run_selection',
                parameters: { selection }
            },
            {
                headers: { 'Content-Type': 'application/json' },
                timeout: config.timeout
            }
        );
        
        if (response.status === 200 && response.data.status === 'success') {
            console.log(`✅ Selection executed successfully`);
            console.log('--- Output ---');
            console.log(response.data.result || '(No output)');
            return true;
        } else {
            console.log(`❌ Selection failed: ${response.data.message || 'Unknown error'}`);
            return false;
        }
    } catch (err) {
        console.log(`❌ Error executing selection: ${err.message}`);
        return false;
    }
}

// Test running a Stata .do file
async function testRunFile(filePath) {
    console.log(`\n=== Testing Stata Do File: ${filePath} ===`);
    
    try {
        const response = await axios.post(
            `http://${config.host}:${config.port}/v1/tools`,
            {
                tool: 'stata_run_file',
                parameters: { file_path: filePath }
            },
            {
                headers: { 'Content-Type': 'application/json' },
                timeout: config.timeout
            }
        );
        
        if (response.status === 200 && response.data.status === 'success') {
            console.log(`✅ Do file executed successfully`);
            console.log('--- Output ---');
            console.log(response.data.result || '(No output)');
            return true;
        } else {
            console.log(`❌ Do file failed: ${response.data.message || 'Unknown error'}`);
            return false;
        }
    } catch (err) {
        console.log(`❌ Error executing do file: ${err.message}`);
        return false;
    }
}

// Run the tests
async function runTests() {
    let serverProcess = null;
    let testsPassed = true;
    let testFile = null;
    
    try {
        // Create test data
        testFile = createTestData();
        if (!testFile) {
            console.log('❌ Cannot continue without test data');
            return false;
        }
        
        // Start server
        serverProcess = await startServer();
        if (!serverProcess) {
            console.log('❌ Cannot continue without server');
            return false;
        }
        
        // Wait a bit more to ensure the server is fully up
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        // Test commands
        const commandTests = [
            'display "Hello from Stata!"',
            'sysuse auto, clear',
            'summarize price mpg',
            'tabulate foreign'
        ];
        
        for (const cmd of commandTests) {
            const passed = await testRunCommand(cmd);
            testsPassed = testsPassed && passed;
        }
        
        // Test selection
        const selectionTest = `
// This is a multi-line Stata code selection
sysuse auto, clear
describe
summarize price
regress price mpg weight
`;
        
        const selectionPassed = await testRunSelection(selectionTest);
        testsPassed = testsPassed && selectionPassed;
        
        // Test do file
        const filePassed = await testRunFile(testFile);
        testsPassed = testsPassed && filePassed;
        
        return testsPassed;
    } finally {
        // Clean up
        if (serverProcess) {
            console.log('\n=== Cleaning Up ===');
            console.log('Shutting down server...');
            
            if (process.platform === 'win32') {
                execSync(`taskkill /pid ${serverProcess.pid} /f /t`);
            } else {
                process.kill(-serverProcess.pid);
            }
            
            console.log('✅ Server shut down');
        }
    }
}

// Run the tests and exit with appropriate code
runTests().then(success => {
    console.log('\n=== Test Summary ===');
    if (success) {
        console.log('✅ All functionality tests passed! The extension should work correctly.');
        process.exit(0);
    } else {
        console.log('❌ Some functionality tests failed. Please check the issues above.');
        process.exit(1);
    }
}).catch(err => {
    console.error(`\n❌ Error running tests: ${err.message}`);
    process.exit(1);
}); 