#!/usr/bin/env node

/**
 * Script to clear port 4000 by killing any process using it
 */
const { execSync } = require('child_process');

const PORT = 4000;
const isWindows = process.platform === 'win32';

console.log(`Checking for processes using port ${PORT}...`);

try {
    if (isWindows) {
        // Windows command to find and kill processes on a port
        try {
            const output = execSync(`netstat -ano | findstr :${PORT} | findstr LISTENING`, { stdio: 'pipe' })
                .toString()
                .trim();
            
            if (output) {
                console.log(`Found processes using port ${PORT}:`);
                console.log(output);
                
                // Extract PIDs and kill them
                output.split('\n').forEach(line => {
                    const match = line.match(/LISTENING\s+(\d+)/);
                    if (match) {
                        const pid = match[1];
                        try {
                            console.log(`Killing process with PID: ${pid}`);
                            execSync(`taskkill /PID ${pid} /F`, { stdio: 'inherit' });
                        } catch (e) {
                            console.error(`Failed to kill process ${pid}: ${e.message}`);
                        }
                    }
                });
            } else {
                console.log(`No processes found using port ${PORT}`);
            }
        } catch (e) {
            // If findstr command fails, it usually means no processes found
            console.log(`No processes found using port ${PORT}`);
        }
    } else {
        // macOS and Linux command to find and kill processes on a port
        try {
            console.log(`Executing: lsof -ti:${PORT}`);
            const pids = execSync(`lsof -ti:${PORT}`, { stdio: 'pipe' }).toString().trim();
            
            if (pids) {
                console.log(`Found processes using port ${PORT}: ${pids}`);
                console.log(`Executing: kill -9 ${pids}`);
                execSync(`kill -9 ${pids}`, { stdio: 'inherit' });
                console.log(`Killed processes: ${pids}`);
            } else {
                console.log(`No processes found using port ${PORT}`);
            }
        } catch (e) {
            // If lsof command fails, it usually means no processes found
            console.log(`No processes found using port ${PORT}`);
        }
    }
    
    console.log(`Port ${PORT} should now be available`);
} catch (error) {
    console.error(`Error clearing port: ${error.message}`);
    process.exit(1);
} 