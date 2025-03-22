/**
 * Context Menu for Running Stata Commands
 * This script adds "Run in Stata" to the context menu of .do files
 */

const vscode = require('vscode');
const { runStataCommand, LOG_FILE } = require('./direct_runner');
const fs = require('fs');
const path = require('path');
const os = require('os');
const child_process = require('child_process');

// Log file for debugging
const logFile = path.join(os.tmpdir(), 'stata_context_extension.log');

// Log function for debugging
function log(message) {
    const timestamp = new Date().toISOString();
    const logMessage = `[${timestamp}] ${message}\n`;
    try {
        fs.appendFileSync(logFile, logMessage);
    } catch (err) {
        console.error('Failed to write to log file:', err);
    }
}

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    console.log('Stata Context Menu extension activated');
    
    // Initialize log file
    try {
        fs.writeFileSync(logFile, `Stata Context Menu extension activated at ${new Date().toISOString()}\n`);
        log('Log file initialized');
    } catch (err) {
        console.error('Failed to initialize log file:', err);
    }
    
    // Register command to run selected text in Stata
    const disposable = vscode.commands.registerCommand('stata-context.runSelection', async () => {
        try {
            log('Command stata-context.runSelection invoked');
            
            // Get the active editor
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showErrorMessage('No active editor');
                log('Error: No active editor');
                return;
            }
            
            // Get the selected text or current line
            let text;
            if (editor.selection.isEmpty) {
                const line = editor.document.lineAt(editor.selection.active.line);
                text = line.text;
                log(`Using current line: ${text}`);
            } else {
                text = editor.document.getText(editor.selection);
                log(`Using selection (${text.length} chars)`);
            }
            
            // Trim the text
            text = text.trim();
            
            // Check if there's any text to run
            if (!text) {
                vscode.window.showErrorMessage('No text to run');
                log('Error: No text to run');
                return;
            }
            
            // Show a notification about what's being run
            const displayText = text.length > 50 ? text.substring(0, 47) + '...' : text;
            vscode.window.showInformationMessage(`Running Stata command: ${displayText}`);
            log(`Showing notification for command: ${displayText}`);
            
            // APPROACH 1: Use VS Code's integrated terminal (more persistent)
            // Force creation of a new terminal
            const terminal = vscode.window.createTerminal({
                name: 'Stata Direct Output',
                hideFromUser: false
            });
            
            // Ensure terminal is visible
            terminal.show(true);
            log('Created and showed terminal');
            
            // Write command to the terminal - first clear it
            terminal.sendText('clear || cls || echo -e "\\033c"', true); // Try different clear commands for compatibility
            
            // Show header and command
            terminal.sendText(`echo "===== STATA COMMAND (${new Date().toLocaleTimeString()}) ====="`, true);
            terminal.sendText(`echo "${text.replace(/"/g, '\\"').replace(/\$/g, '\\$')}"`, true);
            terminal.sendText(`echo "----------------------------------------"`, true);
            
            // APPROACH 2: Also run a direct terminal command as backup
            // Create a temporary script file to run the command
            const tmpScriptPath = path.join(os.tmpdir(), 'stata_run_cmd.sh');
            const tmpOutputPath = path.join(os.tmpdir(), 'stata_output.txt');
            
            // Create shell script to run the command
            const scriptContent = `#!/bin/bash
echo "===== RUNNING STATA COMMAND =====" > "${tmpOutputPath}"
echo "${text.replace(/"/g, '\\"')}" >> "${tmpOutputPath}"
echo "------------------------------" >> "${tmpOutputPath}"

# Run the command using node.js
cd "${path.dirname(logFile)}"
node -e "
const {runStataCommand} = require('${path.join('/Applications/Stata/stata-vscode-extension', 'direct_runner.js')}');
runStataCommand('${text.replace(/'/g, "\\'")}')
  .then(response => {
    const fs = require('fs');
    fs.appendFileSync('${tmpOutputPath}', '\\n===== COMMAND OUTPUT =====\\n');
    if (response.status === 'ok') {
      fs.appendFileSync('${tmpOutputPath}', response.output || 'Command executed successfully');
      if (response.result) {
        fs.appendFileSync('${tmpOutputPath}', '\\n\\n===== RESULT =====\\n');
        fs.appendFileSync('${tmpOutputPath}', response.result);
      }
      fs.appendFileSync('${tmpOutputPath}', '\\n\\n===== COMMAND COMPLETED SUCCESSFULLY =====\\n');
    } else {
      fs.appendFileSync('${tmpOutputPath}', '\\nERROR: ' + (response.message || 'Unknown error') + '\\n');
      fs.appendFileSync('${tmpOutputPath}', '\\n===== COMMAND FAILED =====\\n');
    }
  })
  .catch(error => {
    require('fs').appendFileSync('${tmpOutputPath}', '\\nFailed to run command: ' + error.message + '\\n');
  });
"

# Wait for the output file to be updated with results
sleep 1

# Show the output
echo ""
echo "STATA EXECUTION RESULTS (saved to ${tmpOutputPath}):"
echo "-------------------------------------------------------"
cat "${tmpOutputPath}"
echo "-------------------------------------------------------"
`;
            
            // Write script to temp file
            fs.writeFileSync(tmpScriptPath, scriptContent);
            fs.chmodSync(tmpScriptPath, '755'); // Make executable
            
            log(`Created script at ${tmpScriptPath}`);
            
            // Run the command in the terminal
            terminal.sendText(`bash "${tmpScriptPath}"`, true);
            log('Sent bash script to terminal');
            
            // Run the Stata command directly as well
            log(`Running Stata command: ${text}`);
            runStataCommand(text).then(response => {
                log(`Got response: ${JSON.stringify(response)}`);
                
                // Display the result in the terminal
                if (response.status === 'ok') {
                    terminal.sendText(`echo ""`, true);
                    terminal.sendText(`echo "===== COMMAND OUTPUT ====="`, true);
                    
                    if (response.output) {
                        // Split output by lines and echo each line to avoid escaping issues
                        const lines = response.output.split('\n');
                        for (const line of lines) {
                            terminal.sendText(`echo "${line.replace(/"/g, '\\"').replace(/\$/g, '\\$')}"`, true);
                        }
                    } else {
                        terminal.sendText(`echo "[No output returned]"`, true);
                    }
                    
                    if (response.result) {
                        terminal.sendText(`echo ""`, true);
                        terminal.sendText(`echo "===== RESULT ====="`, true);
                        
                        // Split result by lines and echo each line
                        const resultLines = response.result.split('\n');
                        for (const line of resultLines) {
                            terminal.sendText(`echo "${line.replace(/"/g, '\\"').replace(/\$/g, '\\$')}"`, true);
                        }
                    }
                    
                    terminal.sendText(`echo ""`, true);
                    terminal.sendText(`echo "===== COMMAND COMPLETED SUCCESSFULLY ====="`, true);
                    
                    // Show a success notification
                    vscode.window.showInformationMessage(
                        `Stata command executed successfully. Results are shown in the terminal.`,
                        'Focus Terminal'
                    ).then(selection => {
                        if (selection === 'Focus Terminal') {
                            terminal.show(true);
                        }
                    });
                    
                    log('Command completed successfully, output shown in terminal');
                    
                } else {
                    // Error output
                    terminal.sendText(`echo ""`, true);
                    terminal.sendText(`echo "===== ERROR ====="`, true);
                    terminal.sendText(`echo "Error: ${(response.message || 'Unknown error').replace(/"/g, '\\"')}"`, true);
                    terminal.sendText(`echo ""`, true);
                    terminal.sendText(`echo "===== COMMAND FAILED ====="`, true);
                    
                    // Show an error notification
                    vscode.window.showErrorMessage(
                        `Error running Stata command: ${response.message || "Unknown error"}`,
                        'Focus Terminal'
                    ).then(selection => {
                        if (selection === 'Focus Terminal') {
                            terminal.show(true);
                        }
                    });
                    
                    log(`Command failed: ${response.message || 'Unknown error'}`);
                }
                
                // Also show the output in a separate output file option
                terminal.sendText(`echo ""`, true);
                terminal.sendText(`echo "Output also available in file: ${tmpOutputPath}"`, true);
                
                // Create a clickable status bar item
                const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
                statusBarItem.text = "$(terminal) View Stata Output";
                statusBarItem.tooltip = "Click to show Stata output terminal";
                statusBarItem.command = {
                    title: 'Show Stata Output Terminal',
                    command: 'workbench.action.terminal.focus'
                };
                statusBarItem.show();
                
                // Auto-dispose after 30 seconds
                setTimeout(() => {
                    statusBarItem.dispose();
                }, 30000);
                
            }).catch(error => {
                log(`Error running command: ${error.message}\n${error.stack}`);
                
                terminal.sendText(`echo ""`, true);
                terminal.sendText(`echo "===== ERROR RUNNING COMMAND ====="`, true);
                terminal.sendText(`echo "Error: ${error.message.replace(/"/g, '\\"')}"`, true);
                terminal.sendText(`echo "See log file for details: ${logFile.replace(/"/g, '\\"')}"`, true);
                
                vscode.window.showErrorMessage(`Error: ${error.message}`, 'View Log').then(selection => {
                    if (selection === 'View Log') {
                        vscode.workspace.openTextDocument(logFile).then(doc => {
                            vscode.window.showTextDocument(doc);
                        });
                    }
                });
            });
            
        } catch (error) {
            log(`Caught error: ${error.message}\n${error.stack}`);
            console.error(`Error in context menu command:`, error);
            
            vscode.window.showErrorMessage(`Error: ${error.message}`, 'View Log').then(selection => {
                if (selection === 'View Log') {
                    vscode.workspace.openTextDocument(logFile).then(doc => {
                        vscode.window.showTextDocument(doc);
                    });
                }
            });
        }
    });
    
    context.subscriptions.push(disposable);
    log('Extension activated and ready');
}

function deactivate() {
    log('Extension deactivated');
}

module.exports = {
    activate,
    deactivate
}; 