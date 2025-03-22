
// Test Stata script for MCP extension
clear
sysuse auto, clear
describe
summarize price mpg
reg price mpg weight
save "/Users/hanlulong/Dropbox/Programs/stata-mcp/test_samples/auto.dta", replace
