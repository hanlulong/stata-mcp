* Test script to verify keep-alive logging works
* This will run for about 3 minutes to test frequent logging

display "Starting keep-alive test at: " c(current_time)
display "This script will run for 3 minutes to test if logging keeps connection alive"
display ""

clear
set obs 100
gen x = _n

* Loop for 180 seconds (3 minutes)
local iterations = 180
display "Running `iterations' iterations with 1 second pause each..."
display ""

forvalues i = 1/`iterations' {
    * Pause for 1 second
    sleep 1000

    * Do some computation
    quietly summarize x

    * Display progress every 30 iterations (every 30 seconds)
    if mod(`i', 30) == 0 {
        display "Progress: Completed iteration `i' of `iterations' at " c(current_time)
        display "  Expected to see server log message around this time!"
    }
}

display ""
display "Test completed successfully at: " c(current_time)
display "Check server logs - you should see progress logging every 20-30 seconds!"
