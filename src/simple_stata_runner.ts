/**
 * Extremely Simple Stata Command Runner
 * This is a minimal script to run Stata commands directly without VS Code dependencies
 * It writes all output to a file so we can check exactly what's happening
 */

const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');

// Configuration
const MCP_HOST = 'localhost';
const MCP_PORT = 8766;
const OUTPUT_FILE = path.join(os.homedir(), 'stata_simple_output.txt');

// Create output file and initialize with timestamp
fs.writeFileSync(OUTPUT_FILE, `Simple Stata Runner started at ${new Date().toISOString()}\n\n`);

// Log function
function log(message) {
    const formattedMessage = `[${new Date().toLocaleTimeString()}] ${message}`;
    console.log(formattedMessage);
    fs.appendFileSync(OUTPUT_FILE, formattedMessage + '\n');
}

// Get command line argument
const command = process.argv[2];
if (!command) {
    log('ERROR: No command provided. Usage: node simple_stata_runner.js "your stata command"');
    process.exit(1);
}

log(`Preparing to run Stata command: ${command}`);

// Simple function to send a request to the MCP server
function sendRequest(apiCommand, args = {}) {
    return new Promise((resolve, reject) => {
        // Create the request data
        const requestData = JSON.stringify({
            command: apiCommand,
            args: args
        });
        
        log(`Sending request to MCP server: ${apiCommand} with args: ${JSON.stringify(args)}`);
        
        // Set up request options
        const options = {
            hostname: MCP_HOST,
            port: MCP_PORT,
            path: '/api',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(requestData)
            }
        };
        
        // Create the request
        const req = http.request(options, (res) => {
            let responseData = '';
            
            // Log response status
            log(`Response status: ${res.statusCode}`);
            
            // Collect response data
            res.on('data', (chunk) => {
                responseData += chunk;
            });
            
            // Process complete response
            res.on('end', () => {
                log(`Got complete response (${responseData.length} bytes)`);
                try {
                    const parsedData = JSON.parse(responseData);
                    log(`Parsed JSON response: ${JSON.stringify(parsedData)}`);
                    resolve(parsedData);
                } catch (e) {
                    log(`Error parsing response: ${e.message}`);
                    log(`Raw response: ${responseData}`);
                    reject(e);
                }
            });
        });
        
        // Handle request errors
        req.on('error', (e) => {
            log(`Request ERROR: ${e.message}`);
            reject(e);
        });
        
        // Send the request
        req.write(requestData);
        req.end();
    });
}

// Main execution function
async function executeCommand() {
    try {
        // Check status
        log('Checking server status...');
        const statusResponse = await sendRequest('status');
        
        // Initialize Stata if needed
        if (statusResponse.stata_status && !statusResponse.stata_status.initialized) {
            log('Stata not initialized, initializing...');
            const initResponse = await sendRequest('init', { edition: 'MP', splash: false });
            log(`Initialization result: ${JSON.stringify(initResponse)}`);
        } else {
            log('Stata already initialized');
        }
        
        // Execute the command
        log(`Executing command: ${command}`);
        const runResponse = await sendRequest('run', { cmd: command });
        
        // Log and display the results
        log(`Command execution status: ${runResponse.status}`);
        
        // Write the output to our file with clear markers
        fs.appendFileSync(OUTPUT_FILE, '\n======== COMMAND OUTPUT ========\n');
        if (runResponse.output) {
            fs.appendFileSync(OUTPUT_FILE, runResponse.output + '\n');
        } else {
            fs.appendFileSync(OUTPUT_FILE, '[no output]\n');
        }
        
        if (runResponse.result) {
            fs.appendFileSync(OUTPUT_FILE, '\n======== RESULT ========\n');
            fs.appendFileSync(OUTPUT_FILE, runResponse.result + '\n');
        }
        
        fs.appendFileSync(OUTPUT_FILE, '\n======== END OF OUTPUT ========\n');
        
        // Show results in console
        console.log('\nCommand Output:');
        console.log(runResponse.output || '[no output]');
        
        if (runResponse.result) {
            console.log('\nResult:');
            console.log(runResponse.result);
        }
        
        log(`Results saved to: ${OUTPUT_FILE}`);
        
    } catch (error) {
        log(`Error executing command: ${error.message}`);
        console.error('Error executing command:', error.message);
    }
}

// Run the command
executeCommand(); 