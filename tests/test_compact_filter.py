#!/usr/bin/env python3
"""Test the compact mode filter with real Stata log output."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Read the test log file
log_path = os.path.join(os.path.dirname(__file__), 'test.log')
with open(log_path, 'r') as f:
    SAMPLE_OUTPUT = f.read()

# Import the filter function from the server
# We need to extract just the function, so let's copy it here for testing
import re

def apply_compact_mode_filter(output: str, filter_command_echo: bool = False) -> str:
    """Apply compact mode filtering to Stata output."""
    if not output:
        return output

    # Normalize line endings (Windows CRLF to LF) to ensure regex patterns match
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

    program_drop_pattern = re.compile(r'^\s*\.?\s*(capture\s+program\s+drop|cap\s+program\s+drop|cap\s+prog\s+drop|capt\s+program\s+drop|capt\s+prog\s+drop)\s+\w+', re.IGNORECASE)
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

    # Final cleanup: remove orphaned numbered lines with no content (e.g., "  2. " or "  41.")
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


if __name__ == "__main__":
    print("=" * 80)
    print("TEST: Compact mode filter on real Stata log")
    print("=" * 80)

    # Test with filter_command_echo=True (run_file mode)
    result = apply_compact_mode_filter(SAMPLE_OUTPUT, filter_command_echo=True)

    print(result)
    print()
    print("=" * 80)
    print(f"Original length: {len(SAMPLE_OUTPUT)} chars ({len(SAMPLE_OUTPUT.split(chr(10)))} lines)")
    print(f"Filtered length: {len(result)} chars ({len(result.split(chr(10)))} lines)")
    print(f"Reduction: {100 * (1 - len(result)/len(SAMPLE_OUTPUT)):.1f}%")
