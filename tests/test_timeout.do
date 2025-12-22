* Test script for timeout functionality
* This script will run for approximately 2 minutes to test timeout handling

display "Starting long-running test at: " c(current_time)
display "This script will loop for about 2 minutes"
display "Use this to test timeout at 12 seconds (0.2 min) and 30 seconds (0.5 min)"
display ""

* Create a simple dataset
clear
set obs 100
gen x = _n

* Loop that will take a long time
local iter = 70
display "Running `iter' iterations with 1 second pause each..."
display ""

forvalues i = 1(1)`iter' {
    * Pause for 1 second
    sleep 1000

    di `i'
    * Do some computation to simulate work
    * summarize x

    * Display progress every 10 iterations
    if mod(`i', 10) == 0 {
        display "Progress: Completed iteration `i' of `iterations' at " c(current_time)
    }
}

display ""
display "Test completed successfully at: " c(current_time)
display "If you see this message, the script ran to completion without timeout"