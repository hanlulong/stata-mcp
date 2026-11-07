* Graph auto-naming and cls filtering cases.
* Run with Run File, and also select all + Run Selection. Expected: no r(198),
* no r(111), and the graph viewer shows graph1..graph11 plus the named graph
* "mine" (the #delimit ; graph and the commented-out graph are not renamed).
* Unbalanced-quote lines are covered by tests/test_graph_preprocess.py only,
* because Stata itself rejects them.

sysuse auto, clear
cls
  CLS
display "cls"

* 1: comma inside a function call
scatter price mpg if inrange(mpg, 20, 30)
* 2: comma inside a function call, then real options
histogram price if inlist(rep78, 3, 4), frequency
* 3: commas only inside parenthesised plots
twoway (scatter price mpg, mcolor(red)) (lfit price mpg)
* 4: comma inside a // comment
histogram price // distribution, by origin
* 5: comma inside a string option
scatter price mpg, title("a, b")
* 6: comma inside a string in the if condition
generate str8 s = cond(foreign, "a, b", "c")
scatter price mpg if s == "a, b"
* 7: // inside a string is not a comment
scatter price mpg, title("http://x")
* 8: compound quotes
scatter price mpg, title(`"He said "a, b""')
* 9: || twoway with options on the first plot
twoway scatter price mpg, mcolor(red) || lfit price mpg
* 10: by()
scatter price mpg, by(foreign)
* already named: left alone
scatter price mpg, name(mine, replace)
* 11: options continued on the next line
scatter price mpg, ///
    title("continued, line")

#delimit ;
twoway (scatter price mpg)
       (lfit price mpg), legend(off);
#delimit cr

/*
scatter price weight
*/
