* Quick streaming test
display "Line 1: Starting test"
display "Line 2: This is output"
display "Line 3: More output"

forvalues i = 1/5 {
    sleep 500
    display "Count: `i'"
}

display "Line 4: Test complete"
