// Simple Stata test file
clear
set obs 100
gen x = rnormal()
gen y = 2*x + rnormal()
gen 行业代码 = 1
gen category = . if 行业代码 == 1
summarize
gen clss = 1 
regress y x
twoway (scatter y x, mcolor(blue)) ///
(scatter x y), ///
title("test") ///
legend(off)
graph export "test3.pdf", replace 


twoway (scatter y x, mcolor(blue)) ///
(scatter x y), ///
title("test") ///
legend(off)
graph export "test4.pdf", replace 



histogram x
graph box y
