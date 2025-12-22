* Test script to verify log file location and working directory
* This script tests that:
* 1. The .do file executes in its workspace directory
* 2. Log files are saved to the configured location (not necessarily workspace)

* Display current working directory
display "Current working directory:"
pwd

* Create a test file in the current directory to verify we're in the workspace
file open testfile using "test_output.txt", write replace
file write testfile "This file should be created in the workspace directory" _n
file write testfile "where the .do file is located" _n
file close testfile

* Display current directory again
display "After creating test file, working directory is:"
pwd

* Show that we can reference files with relative paths
display "Test file should exist at: test_output.txt"

* Simple test commands
display "Test completed successfully!"
display "Check:"
display "  1. This output should appear in the log file"
display "  2. test_output.txt should be created in the workspace"
display "  3. Log file location depends on your settings"
