* Test whether graph export with name() parameter works better than without

clear all
set obs 20
gen x = _n
gen y = _n + rnormal()

di as text "=========================================="
di as text "TEST 1: graph export WITH name() parameter"
di as text "=========================================="
twoway scatter y x, name(mygraph1, replace) title("Graph 1")
di as text "Graph created with name(mygraph1), now exporting WITH name() param..."
graph export "test_with_name.png", name(mygraph1) replace
di as text "SUCCESS: Export with name() parameter completed"

di as text ""
di as text "=========================================="
di as text "TEST 2: graph export WITHOUT name() parameter"
di as text "=========================================="
twoway scatter y x, name(mygraph2, replace) title("Graph 2")
di as text "Graph created with name(mygraph2), now exporting WITHOUT name() param..."
graph export "test_without_name.png", replace
di as text "SUCCESS: Export without name() parameter completed"

di as text ""
di as text "ALL TESTS COMPLETED!"
