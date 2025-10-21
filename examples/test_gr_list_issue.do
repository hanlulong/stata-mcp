* Test to identify the exact issue with _gr_list and graph export
* This will help us understand what's causing the hang

clear all
set obs 20

gen x = _n
gen y = _n + rnormal()

di as text "=== TEST 1: Simple graph WITHOUT _gr_list on ==="
qui _gr_list off
twoway scatter y x, name(test1, replace) title("Test 1: _gr_list off")
di as text "Graph created successfully"
graph export "test1.png", replace width(800) height(600)
di as text "Graph exported successfully with _gr_list OFF"

di as text ""
di as text "=== TEST 2: Simple graph WITH _gr_list on ==="
qui _gr_list on
twoway scatter y x, name(test2, replace) title("Test 2: _gr_list on")
di as text "Graph created successfully"
di as text "Now attempting graph export with _gr_list ON..."
di as text "If this hangs, we found the issue!"
graph export "test2.png", replace width(800) height(600)
di as text "Graph exported successfully with _gr_list ON"

di as text ""
di as text "=== TEST 3: Graph export with explicit name() option ==="
graph export "test2_named.png", name(test2) replace width(800) height(600)
di as text "Named export succeeded with _gr_list ON"

di as text ""
di as text "=== TEST 4: Turn off _gr_list then export ==="
qui _gr_list off
graph export "test2_after_off.png", replace width(800) height(600)
di as text "Export after _gr_list OFF succeeded"

di as text ""
di as text "=== ALL TESTS COMPLETED SUCCESSFULLY ==="
