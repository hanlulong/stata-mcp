// Simple Stata test file
clear
set obs 100
gen x = rnormal()
gen y = 2*x + rnormal()
gen 行业代码 = 1
gen category = . if 行业代码 == 1
summarize
regress y x
scatter y x
histogram x
graph box y
graph box x
graph export "test.pdf", replace 