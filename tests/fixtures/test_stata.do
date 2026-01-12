// Simple Stata test file
clear
set obs 100
gen x = rnormal()
gen y = 2*x + rnormal()
gen 行业代码 = 1
gen category = . /// 
if 行业代码 == 1
summarize
gen clss = 1 
regress y x
twoway (scatter y x,  name(graph1,replace) mcolor(blue)) ///
(scatter x y), ///
title("test") ///
legend(off)
graph export "test3a.png", name(graph1) replace 
graph export "test3.png", replace 


twoway (scatter y x, mcolor(blue)) ///
(line x y), ///
title("test") ///
legend(off)
graph export "test4.png", replace 



histogram x
graph box y
