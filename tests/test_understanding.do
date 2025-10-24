* Comprehensive test to verify understanding of the PNG export hang issue
* Based on findings:
* - PNG export hangs with _gr_list on and inline=False
* - PDF export works fine
* - After PDF export, PNG export also works

clear all
set obs 20
gen x = _n
gen y = _n + rnormal()

di as text "=========================================="
di as text "TEST 1: PDF export FIRST (should work)"
di as text "=========================================="
twoway scatter y x, name(graph1, replace) title("Graph 1")
di as text "Graph 1 created, now exporting to PDF..."
graph export "test_understanding_1.pdf", replace
di as text "SUCCESS: PDF export completed"

di as text ""
di as text "=========================================="
di as text "TEST 2: PNG export AFTER PDF (should work)"
di as text "=========================================="
twoway scatter y x, name(graph2, replace) title("Graph 2")
di as text "Graph 2 created, now exporting to PNG..."
graph export "test_understanding_2.png", replace
di as text "SUCCESS: PNG export completed after PDF"

di as text ""
di as text "=========================================="
di as text "TEST 3: Another PNG export (should work)"
di as text "=========================================="
twoway scatter y x, name(graph3, replace) title("Graph 3")
di as text "Graph 3 created, now exporting to PNG..."
graph export "test_understanding_3.png", replace
di as text "SUCCESS: Second PNG export completed"

di as text ""
di as text "=========================================="
di as text "ALL TESTS PASSED!"
di as text "=========================================="
di as text "This confirms:"
di as text "1. PDF export works with _gr_list on"
di as text "2. PNG export works AFTER a PDF export"
di as text "3. Subsequent PNG exports also work"
