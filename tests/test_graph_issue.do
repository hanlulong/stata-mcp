* Test to reproduce the graph naming issue

clear all
set obs 10

gen x = _n
gen y1 = _n + rnormal()
gen y2 = _n + 2 + rnormal()

* This is what the MCP server is creating (INCORRECT - name inside plot spec)
* twoway (scatter y1 x, name(graph1, replace) mcolor(blue)) ///
*     (scatter y2 x, mcolor(red)), title("Test Graph")

* Let's test if this syntax actually works
twoway (scatter y1 x, mcolor(blue)) ///
    (scatter y2 x, mcolor(red) ), title("Test Graph - Wrong Syntax")

if _rc != 0 {
    di as error "ERROR: Graph with name() inside plot spec FAILED with return code: " _rc
}
else {
    di as text "Graph with name() inside plot spec succeeded"
    graph export "test_wrong.png", replace
}

di "TEST"

* Now test the CORRECT syntax (name at graph level)
twoway (scatter y1 x, mcolor(blue)) ///
    (scatter y2 x, mcolor(red)), title("Test Graph - Correct Syntax")

if _rc == 0 {
    di as text "Graph with name() at graph level succeeded"
    graph export "test_correct.png", replace
}
