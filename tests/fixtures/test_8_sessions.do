* =============================================================================
* Long-running test file for stata-mcp 8 parallel sessions
* =============================================================================

* Capture session start
local start_time = c(current_time)
local session_marker = runiform() * 10000
display "=========================================="
display "SESSION MARKER: `session_marker'"
display "START TIME: `start_time'"
display "=========================================="

* Phase 1: Data generation
display _newline "PHASE 1: Generating large dataset..."
sleep 2000
clear
set obs 5000
gen id = _n
gen x1 = rnormal(0, 1)
gen x2 = rnormal(5, 2)
gen x3 = runiform()
gen group = ceil(runiform() * 10)
gen y = 3*x1 - 2*x2 + 5*x3 + rnormal(0, 1)
display "Dataset created with " _N " observations"

* Phase 2: Summary statistics
display _newline "PHASE 2: Computing summary statistics..."
sleep 1500
summarize x1 x2 x3 y

* Phase 3: Multiple regressions
display _newline "PHASE 3: Running multiple regressions..."
sleep 2000

display "--- Regression 1: Simple ---"
quietly regress y x1
display "R-squared: " e(r2)

display "--- Regression 2: Multiple ---"
quietly regress y x1 x2
display "R-squared: " e(r2)

display "--- Regression 3: Full model ---"
regress y x1 x2 x3

* Phase 4: Group analysis
display _newline "PHASE 4: Group-level analysis..."
sleep 1500
tabstat y, by(group) statistics(mean sd min max n)

* Phase 5: Bootstrap simulation
display _newline "PHASE 5: Running bootstrap simulation..."
sleep 2000
local boot_results = 0
forvalues b = 1/50 {
    quietly {
        preserve
        bsample
        regress y x1 x2 x3
        local boot_results = `boot_results' + e(r2)
        restore
    }
    if mod(`b', 10) == 0 {
        display "  Bootstrap iteration `b' complete"
    }
}
local avg_r2 = `boot_results' / 50
display "Average bootstrap R-squared: `avg_r2'"

* Phase 6: Monte Carlo
display _newline "PHASE 6: Monte Carlo simulation..."
sleep 1500
local mc_sum = 0
forvalues m = 1/100 {
    quietly {
        drop _all
        set obs 500
        gen x = rnormal()
        gen y = 2*x + rnormal()
        regress y x
        local mc_sum = `mc_sum' + _b[x]
    }
}
local mc_avg = `mc_sum' / 100
display "Monte Carlo average coefficient: `mc_avg'"

* Phase 7: Final pause and summary
display _newline "PHASE 7: Final processing..."
sleep 2000

* End timing
local end_time = c(current_time)
display _newline "=========================================="
display "SESSION MARKER: `session_marker'"
display "START TIME: `start_time'"
display "END TIME: `end_time'"
display "STATUS: COMPLETED SUCCESSFULLY"
display "=========================================="
