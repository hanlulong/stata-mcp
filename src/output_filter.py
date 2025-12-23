#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Output Filtering Module for Stata MCP Server

This module provides functions for filtering and processing Stata output
to reduce token usage when communicating with AI models.

Key features:
- Compact mode filtering removes verbose output (programs, mata, loops)
- Token limit checking with automatic file saving
- SMCL formatting tag removal
- Multiple blank line compression
- Break message deduplication
"""

import os
import re
import time
import tempfile
import logging
from typing import Tuple, Optional


def deduplicate_break_messages(output: str) -> str:
    """Remove duplicate --Break-- messages from Stata output.

    When Stata is interrupted, it may output the break message multiple times
    (e.g., once for each nested command level). This function collapses multiple
    occurrences into a single break message.

    Args:
        output: Stata output that may contain duplicate break messages

    Returns:
        Output with duplicate break messages removed
    """
    if not output or '--Break--' not in output:
        return output

    # Pattern matches --Break-- followed by r(1); with optional whitespace
    # We want to keep only the first occurrence
    break_pattern = r'(--Break--\s*\n\s*r\(1\);\s*\n?)+'

    # Replace multiple occurrences with a single one
    output = re.sub(break_pattern, '--Break--\nr(1);\n', output)

    return output


def apply_compact_mode_filter(output: str, filter_command_echo: bool = False) -> str:
    """Apply compact mode filtering to Stata output to reduce token usage.

    Filters out (always):
    - Program definitions (capture program drop through end)
    - Mata blocks (mata: through end)
    - Loop code echoes (foreach/forvalues/while) - keeps actual output only
    - SMCL formatting tags
    - Compresses multiple spaces and blank lines
    - Truncates long variable lists (>100 items)

    Filters out (only when filter_command_echo=True, i.e., for run_file):
    - Command echo lines (lines starting with ". " that echo Stata commands)
    - Line continuation markers ("> " for multi-line commands)
    - Log header/footer lines (log type, opened on, Log file saved, etc.)
    - MCP execution header lines (">>> [timestamp] do 'filepath'")

    Args:
        output: Raw Stata output string
        filter_command_echo: Whether to filter command echo lines (for run_file only)

    Returns:
        Filtered output string
    """
    if not output:
        return output

    # Normalize line endings (Windows CRLF to LF) to ensure regex patterns match
    output = output.replace('\r\n', '\n').replace('\r', '\n')

    lines = output.split('\n')
    filtered_lines = []

    # State tracking for variable list truncation
    variable_list_count = 0
    in_variable_list = False

    # Patterns for command echo lines (redundant - LLM already knows the commands)
    command_echo_pattern = re.compile(r'^\.\s*$|^\.\s+\S')
    numbered_line_pattern = re.compile(r'^\s*\d+\.\s')
    continuation_pattern = re.compile(r'^>\s')
    mcp_header_pattern = re.compile(r'^>>>\s+\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]')
    exec_time_pattern = re.compile(r'^\*\*\*\s+Execution completed in')
    final_output_pattern = re.compile(r'^Final output:\s*$')
    log_info_pattern = re.compile(
        r'^\s*(name:|log:|log type:|opened on:|closed on:|Log file saved to:)',
        re.IGNORECASE
    )
    capture_log_pattern = re.compile(r'^\.\s*capture\s+log\s+close', re.IGNORECASE)

    # Patterns for program/mata/loop blocks
    program_drop_pattern = re.compile(
        r'^\s*\.?\s*(capture\s+program\s+drop|cap\s+program\s+drop|cap\s+prog\s+drop|'
        r'capt\s+program\s+drop|capt\s+prog\s+drop)\s+\w+',
        re.IGNORECASE
    )
    program_define_pattern = re.compile(
        r'^\s*\.?\s*program\s+(define\s+)?(?!version|dir|drop|list|describe)\w+',
        re.IGNORECASE
    )
    mata_start_pattern = re.compile(
        r'^\s*(\d+\.)?\s*\.?\s*mata\s*:?\s*$|^-+\s*mata\s*\(',
        re.IGNORECASE
    )
    end_pattern = re.compile(r'^\s*(\d+\.)?\s*[.:]*\s*end\s*$', re.IGNORECASE)
    mata_separator_pattern = re.compile(r'^-{20,}$')

    # Loop patterns
    loop_start_pattern = re.compile(
        r'^(\s*\d+\.)?\s*\.?\s*(foreach|forvalues|while)\s+.*\{\s*$',
        re.IGNORECASE
    )
    loop_end_pattern = re.compile(r'^\s*\d+\.\s*\}\s*$')

    # Verbose output patterns to filter (always)
    real_changes_pattern = re.compile(
        r'^\s*\([\d,]+\s+real\s+changes?\s+made\)\s*$',
        re.IGNORECASE
    )
    missing_values_pattern = re.compile(
        r'^\s*\([\d,]+\s+missing\s+values?\s+generated\)\s*$',
        re.IGNORECASE
    )

    # SMCL formatting tags
    smcl_pattern = re.compile(
        r'\{(txt|res|err|inp|com|bf|it|sf|hline|c\s+\||\-+|break|col\s+\d+|right|center|ul|/ul)\}'
    )
    # Variable list detection
    var_list_pattern = re.compile(r'^\s*(\d+\.\s+)?\w+\s+\w+\s+%')

    # Track block state
    in_program_block = False
    in_mata_block = False
    in_loop_block = False
    program_end_depth = 0
    loop_brace_depth = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # Handle PROGRAM blocks (filter entirely)
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

        # Handle MATA blocks (filter entirely)
        if in_mata_block:
            if end_pattern.match(line):
                in_mata_block = False
                if i + 1 < len(lines) and mata_separator_pattern.match(lines[i + 1]):
                    i += 1
            i += 1
            continue

        # Handle LOOP blocks (filter code echoes, keep actual output)
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

            # Inside loop: filter code echoes but keep actual output
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

            # This line is actual output inside the loop - keep it
            line = smcl_pattern.sub('', line)
            if line.strip():
                filtered_lines.append(line)
            i += 1
            continue

        # Check for block starts (when not inside any block)
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

        # Command echo filtering (only when filter_command_echo=True)
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

        # Clean up and keep the line (preserve spacing for table alignment)
        line = smcl_pattern.sub('', line)

        # Track variable lists and truncate after 100 items
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

    # Collapse multiple consecutive blank lines to single blank line
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

    # Remove trailing blank lines
    while result_lines and not result_lines[-1].strip():
        result_lines.pop()

    return '\n'.join(result_lines)


def check_token_limit_and_save(
    output: str,
    max_output_tokens: int,
    extension_path: Optional[str] = None,
    original_log_path: Optional[str] = None
) -> Tuple[str, bool]:
    """Check if output exceeds token limit and save to file if needed.

    Args:
        output: The output string to check
        max_output_tokens: Maximum allowed tokens (0 = unlimited)
        extension_path: Path to extension directory for saving logs
        original_log_path: Optional path to original log file for context

    Returns:
        Tuple of (output_or_message, was_truncated)
        If truncated, returns a message with file path instead of content
    """
    # If unlimited (0), return as-is
    if max_output_tokens <= 0:
        return output, False

    # Estimate tokens (roughly 4 chars per token)
    estimated_tokens = len(output) / 4

    if estimated_tokens <= max_output_tokens:
        return output, False

    # Output exceeds limit - save to file and return path
    try:
        # Determine save location with fallback options
        logs_dir = None
        tried_paths = []

        # Try extension path first
        if extension_path and extension_path.strip():
            candidate = os.path.join(extension_path, 'logs')
            tried_paths.append(candidate)
            try:
                os.makedirs(candidate, exist_ok=True)
                # Test if writable
                test_file = os.path.join(candidate, '.write_test')
                with open(test_file, 'w') as f:
                    f.write('test')
                os.unlink(test_file)
                logs_dir = candidate
            except (OSError, IOError):
                logging.debug(f"Cannot use extension logs dir: {candidate}")

        # Fall back to temp directory
        if not logs_dir:
            candidate = os.path.join(tempfile.gettempdir(), 'stata_mcp_logs')
            tried_paths.append(candidate)
            try:
                os.makedirs(candidate, exist_ok=True)
                logs_dir = candidate
            except (OSError, IOError):
                logging.debug(f"Cannot use temp logs dir: {candidate}")

        # Last resort: current directory
        if not logs_dir:
            logs_dir = os.getcwd()
            tried_paths.append(logs_dir)

        # Generate unique filename
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_filename = f"stata_output_{timestamp}.log"
        log_path = os.path.join(logs_dir, log_filename)

        # Save the full output
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(output)

        # Return message with path
        actual_tokens = int(estimated_tokens)
        message = (
            f"Output exceeded token limit ({actual_tokens} tokens > {max_output_tokens} max).\n"
            f"Full output saved to: {log_path}\n\n"
            f"Please investigate the log file for complete results.\n"
            f"You can read this file to see the full Stata output."
        )

        # Include a preview (first ~1000 chars)
        preview_chars = min(1000, len(output))
        if preview_chars > 0:
            preview = output[:preview_chars]
            if len(output) > preview_chars:
                preview += "\n... [truncated]"
            message += f"\n\n--- Preview ---\n{preview}"

        logging.info(f"Output exceeded token limit ({actual_tokens} tokens). Saved to: {log_path}")
        return message, True

    except Exception as e:
        logging.error(f"Failed to save large output to file: {e}")
        # Fall back to truncating inline
        max_chars = max_output_tokens * 4
        truncated = output[:max_chars] + f"\n\n... [Output truncated at {max_output_tokens} tokens]"
        return truncated, True


def process_mcp_output(
    output: str,
    result_display_mode: str = 'full',
    max_output_tokens: int = 0,
    extension_path: Optional[str] = None,
    log_path: Optional[str] = None,
    for_mcp: bool = True,
    filter_command_echo: bool = False
) -> str:
    """Process output for MCP returns, applying compact mode and token limits.

    Args:
        output: Raw Stata output
        result_display_mode: 'compact' or 'full'
        max_output_tokens: Maximum tokens (0 = unlimited)
        extension_path: Path to extension directory
        log_path: Optional path to original log file
        for_mcp: Whether this is for MCP return (applies filters) or VS Code display
        filter_command_echo: Whether to filter command echo lines

    Returns:
        Processed output string
    """
    if not for_mcp:
        # For VS Code extension, return full output
        return output

    # Apply compact mode filtering if enabled
    if result_display_mode == 'compact':
        output = apply_compact_mode_filter(output, filter_command_echo=filter_command_echo)

    # Check token limit and save if needed
    output, _ = check_token_limit_and_save(
        output,
        max_output_tokens,
        extension_path,
        log_path
    )

    return output
