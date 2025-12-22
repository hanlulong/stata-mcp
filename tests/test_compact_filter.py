#!/usr/bin/env python3
"""
Tests for the compact mode filter.

These tests verify the output filtering logic that reduces Stata output
for token-efficient AI consumption.
"""

import sys
import os
import re
import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# =============================================================================
# Sample Test Data
# =============================================================================

SAMPLE_STATA_OUTPUT = """
. sysuse auto
(1978 automobile data)

. describe

Contains data from /Applications/Stata/ado/base/a/auto.dta
 Observations:            74                  1978 automobile data
    Variables:            12                  13 Apr 2024 17:45
--------------------------------------------------------------------------------
Variable      Storage   Display    Value
    name         type    format    label      Variable label
--------------------------------------------------------------------------------
make            str18   %-18s                 Make and model
price           int     %8.0gc                Price
mpg             int     %8.0g                 Mileage (mpg)
--------------------------------------------------------------------------------
Sorted by: foreign

. summarize price

    Variable |        Obs        Mean    Std. dev.       Min        Max
-------------+---------------------------------------------------------
       price |         74    6165.257    2949.496       3291      15906
"""

SAMPLE_WITH_LOOP = """
. foreach var in mpg price weight {
  2.     summarize `var'
  3. }

    Variable |        Obs        Mean    Std. dev.       Min        Max
-------------+---------------------------------------------------------
         mpg |         74     21.2973    5.785503         12         41

    Variable |        Obs        Mean    Std. dev.       Min        Max
-------------+---------------------------------------------------------
       price |         74    6165.257    2949.496       3291      15906
"""

SAMPLE_WITH_PROGRAM = """
. capture program drop myprog

. program define myprog
  1.     args x
  2.     display `x' * 2
  3. end

. myprog 5
10
"""

SAMPLE_WITH_VERBOSE = """
. replace price = 5000 if price < 5000
(22 real changes made)

. gen newvar = .
(74 missing values generated)

. display "Done"
Done
"""


# =============================================================================
# Local copy of filter function for testing
# (This will be imported from output_filter.py after refactoring)
# =============================================================================

def apply_compact_mode_filter(output: str, filter_command_echo: bool = False) -> str:
    """Apply compact mode filtering to Stata output."""
    if not output:
        return output

    # Normalize line endings
    output = output.replace('\r\n', '\n').replace('\r', '\n')

    lines = output.split('\n')
    filtered_lines = []

    variable_list_count = 0
    in_variable_list = False

    # Patterns
    command_echo_pattern = re.compile(r'^\.\s*$|^\.\s+\S')
    numbered_line_pattern = re.compile(r'^\s*\d+\.\s')
    continuation_pattern = re.compile(r'^>\s')
    mcp_header_pattern = re.compile(r'^>>>\s+\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]')
    exec_time_pattern = re.compile(r'^\*\*\*\s+Execution completed in')
    final_output_pattern = re.compile(r'^Final output:\s*$')
    log_info_pattern = re.compile(r'^\s*(name:|log:|log type:|opened on:|closed on:|Log file saved to:)', re.IGNORECASE)
    capture_log_pattern = re.compile(r'^\.\s*capture\s+log\s+close', re.IGNORECASE)

    program_drop_pattern = re.compile(r'^\s*\.?\s*(capture\s+program\s+drop|cap\s+program\s+drop|cap\s+prog\s+drop)\s+\w+', re.IGNORECASE)
    program_define_pattern = re.compile(r'^\s*\.?\s*program\s+(define\s+)?(?!version|dir|drop|list|describe)\w+', re.IGNORECASE)
    mata_start_pattern = re.compile(r'^\s*(\d+\.)?\s*\.?\s*mata\s*:?\s*$|^-+\s*mata\s*\(', re.IGNORECASE)
    end_pattern = re.compile(r'^\s*(\d+\.)?\s*[.:]*\s*end\s*$', re.IGNORECASE)
    mata_separator_pattern = re.compile(r'^-{20,}$')

    loop_start_pattern = re.compile(r'^(\s*\d+\.)?\s*\.?\s*(foreach|forvalues|while)\s+.*\{\s*$', re.IGNORECASE)
    loop_end_pattern = re.compile(r'^\s*\d+\.\s*\}\s*$')

    # Verbose output patterns to filter (always)
    real_changes_pattern = re.compile(r'^\s*\([\d,]+\s+real\s+changes?\s+made\)\s*$', re.IGNORECASE)
    missing_values_pattern = re.compile(r'^\s*\([\d,]+\s+missing\s+values?\s+generated\)\s*$', re.IGNORECASE)

    smcl_pattern = re.compile(r'\{(txt|res|err|inp|com|bf|it|sf|hline|c\s+\||\-+|break|col\s+\d+|right|center|ul|/ul)\}')
    var_list_pattern = re.compile(r'^\s*(\d+\.\s+)?\w+\s+\w+\s+%')

    in_program_block = False
    in_mata_block = False
    in_loop_block = False
    program_end_depth = 0
    loop_brace_depth = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # Handle PROGRAM blocks
        if in_program_block:
            if mata_start_pattern.match(line):
                program_end_depth += 1
            if end_pattern.match(line):
                if program_end_depth > 0:
                    program_end_depth -= 1
                else:
                    in_program_block = False
            i += 1
            continue

        # Handle MATA blocks
        if in_mata_block:
            if end_pattern.match(line):
                in_mata_block = False
                if i + 1 < len(lines) and mata_separator_pattern.match(lines[i + 1]):
                    i += 1
            i += 1
            continue

        # Handle LOOP blocks
        if in_loop_block:
            if loop_start_pattern.match(line):
                loop_brace_depth += 1
                i += 1
                continue

            if loop_end_pattern.match(line):
                if loop_brace_depth > 0:
                    loop_brace_depth -= 1
                else:
                    in_loop_block = False
                i += 1
                continue

            # Filter code echoes but keep actual output
            if command_echo_pattern.match(line):
                i += 1
                continue
            if numbered_line_pattern.match(line):
                i += 1
                continue
            if continuation_pattern.match(line):
                i += 1
                continue

            # Filter verbose messages inside loops
            if real_changes_pattern.match(line):
                i += 1
                continue
            if missing_values_pattern.match(line):
                i += 1
                continue

            # Keep actual output
            line = smcl_pattern.sub('', line)
            if line.strip():
                filtered_lines.append(line)
            i += 1
            continue

        # Check for block starts
        if loop_start_pattern.match(line):
            in_loop_block = True
            loop_brace_depth = 0
            i += 1
            continue

        if program_drop_pattern.match(line):
            i += 1
            continue

        if program_define_pattern.match(line):
            in_program_block = True
            program_end_depth = 0
            i += 1
            continue

        if mata_start_pattern.match(line):
            in_mata_block = True
            i += 1
            continue

        # Filter verbose messages (always)
        if real_changes_pattern.match(line):
            i += 1
            continue
        if missing_values_pattern.match(line):
            i += 1
            continue

        # Command echo filtering
        if filter_command_echo:
            if mcp_header_pattern.match(line):
                i += 1
                continue
            if exec_time_pattern.match(line):
                i += 1
                continue
            if final_output_pattern.match(line):
                i += 1
                continue
            if log_info_pattern.match(line):
                i += 1
                continue
            if capture_log_pattern.match(line):
                i += 1
                continue
            if command_echo_pattern.match(line):
                i += 1
                continue
            if numbered_line_pattern.match(line):
                i += 1
                continue
            if continuation_pattern.match(line):
                i += 1
                continue

        # Clean up and keep the line
        line = smcl_pattern.sub('', line)
        leading_space = len(line) - len(line.lstrip())
        line_content = re.sub(r' {4,}', '  ', line.strip())
        line = ' ' * min(leading_space, 4) + line_content

        if var_list_pattern.match(line):
            if not in_variable_list:
                in_variable_list = True
                variable_list_count = 0
            variable_list_count += 1
            if variable_list_count > 100:
                if variable_list_count == 101:
                    filtered_lines.append("    ... (output truncated, showing first 100 variables)")
                i += 1
                continue
        else:
            in_variable_list = False
            variable_list_count = 0

        filtered_lines.append(line)
        i += 1

    # Final cleanup: remove orphaned numbered lines
    empty_numbered_line_pattern = re.compile(r'^\s*\d+\.\s*$')

    cleaned_lines = []
    for line in filtered_lines:
        if empty_numbered_line_pattern.match(line):
            continue
        cleaned_lines.append(line)

    # Collapse multiple blank lines
    result_lines = []
    prev_blank = False
    for line in cleaned_lines:
        is_blank = not line.strip()
        if is_blank:
            if not prev_blank:
                result_lines.append(line)
            prev_blank = True
        else:
            result_lines.append(line)
            prev_blank = False

    while result_lines and not result_lines[-1].strip():
        result_lines.pop()

    return '\n'.join(result_lines)


# =============================================================================
# Test Classes
# =============================================================================

class TestCompactModeFilter:
    """Tests for the compact mode filter function."""

    def test_empty_output(self):
        """Empty input should return empty output."""
        assert apply_compact_mode_filter("") == ""
        assert apply_compact_mode_filter(None) is None

    def test_basic_filtering(self):
        """Basic Stata output should be filtered correctly."""
        result = apply_compact_mode_filter(SAMPLE_STATA_OUTPUT)

        # Should contain data description
        assert "1978 automobile data" in result
        assert "Observations:" in result

        # Should contain summary statistics
        assert "6165.257" in result

    def test_command_echo_filtering(self):
        """Command echoes should be filtered when requested."""
        result = apply_compact_mode_filter(SAMPLE_STATA_OUTPUT, filter_command_echo=True)

        # Command echoes should be removed
        assert ". sysuse auto" not in result
        assert ". describe" not in result
        assert ". summarize price" not in result

        # But data should remain
        assert "1978 automobile data" in result

    def test_loop_filtering(self):
        """Loop blocks should be filtered, keeping only output."""
        result = apply_compact_mode_filter(SAMPLE_WITH_LOOP, filter_command_echo=True)

        # Loop syntax should be removed
        assert "foreach" not in result
        assert "summarize `var'" not in result
        assert "  2." not in result
        assert "  3." not in result

        # But output data should remain
        assert "21.2973" in result  # mpg mean
        assert "6165.257" in result  # price mean

    def test_program_block_filtering(self):
        """Program definitions should be filtered entirely."""
        result = apply_compact_mode_filter(SAMPLE_WITH_PROGRAM, filter_command_echo=True)

        # Program definition should be removed
        assert "program define" not in result
        assert "args x" not in result
        assert "display `x'" not in result

        # But program output should remain
        assert "10" in result

    def test_verbose_message_filtering(self):
        """Verbose messages like '(N real changes made)' should be filtered."""
        result = apply_compact_mode_filter(SAMPLE_WITH_VERBOSE)

        # Verbose messages should be removed
        assert "real changes made" not in result
        assert "missing values generated" not in result

        # But actual output should remain
        assert "Done" in result

    def test_multiple_blank_lines_collapsed(self):
        """Multiple consecutive blank lines should be collapsed to one."""
        input_text = "Line 1\n\n\n\n\nLine 2"
        result = apply_compact_mode_filter(input_text)

        # Should not have more than one consecutive blank line
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_trailing_blanks_removed(self):
        """Trailing blank lines should be removed."""
        input_text = "Output\n\n\n"
        result = apply_compact_mode_filter(input_text)

        assert result == "Output"

    def test_smcl_codes_removed(self):
        """SMCL formatting codes should be removed."""
        input_text = "{txt}Some text {res}result {err}error"
        result = apply_compact_mode_filter(input_text)

        assert "{txt}" not in result
        assert "{res}" not in result
        assert "{err}" not in result
        assert "Some text" in result

    def test_output_reduction(self):
        """Filtered output should be smaller than input."""
        result = apply_compact_mode_filter(SAMPLE_STATA_OUTPUT, filter_command_echo=True)

        # Should achieve meaningful reduction
        assert len(result) < len(SAMPLE_STATA_OUTPUT)


class TestFilterEdgeCases:
    """Tests for edge cases in the filter."""

    def test_windows_line_endings(self):
        """Windows CRLF line endings should be normalized."""
        input_text = "Line 1\r\nLine 2\r\n"
        result = apply_compact_mode_filter(input_text)

        assert "\r" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_mixed_line_endings(self):
        """Mixed line endings should all be normalized."""
        input_text = "Line 1\r\nLine 2\rLine 3\n"
        result = apply_compact_mode_filter(input_text)

        assert "\r" not in result

    def test_numbered_lines_orphaned(self):
        """Orphaned numbered lines (just '  2.') should be removed."""
        input_text = "  1. code here\n  2. \n  3. more code"
        result = apply_compact_mode_filter(input_text, filter_command_echo=True)

        # Numbered lines should be removed when filtering command echo
        assert "  2." not in result

    def test_excessive_whitespace_collapsed(self):
        """Excessive horizontal whitespace should be reduced."""
        input_text = "Column1       Column2              Column3"
        result = apply_compact_mode_filter(input_text)

        # Should not have more than 2 consecutive spaces
        assert "       " not in result


# =============================================================================
# Integration test (requires test log file)
# =============================================================================

@pytest.mark.skipif(
    not os.path.exists(os.path.join(os.path.dirname(__file__), 'fixtures', 'test_sample.log')),
    reason="Test log file not available"
)
class TestWithRealLogFile:
    """Tests using real Stata log files."""

    def test_real_log_filtering(self):
        """Test filtering with a real Stata log file."""
        log_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'test_sample.log')
        with open(log_path, 'r') as f:
            content = f.read()

        result = apply_compact_mode_filter(content, filter_command_echo=True)

        # Should achieve some reduction
        assert len(result) < len(content)


# =============================================================================
# Main (for standalone execution)
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
