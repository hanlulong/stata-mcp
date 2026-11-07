#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility functions for Stata MCP Server

This module contains common utility functions used across the codebase,
extracted to reduce duplication and improve maintainability.
"""

import logging
import os
import platform
import re
from typing import List, Optional, Tuple


def normalize_path_for_platform(path: str) -> str:
    """
    Normalize a file path for the current platform.

    On Windows, converts forward slashes to backslashes.
    On all platforms, normalizes the path using os.path.normpath.

    Args:
        path: The file path to normalize

    Returns:
        Normalized path appropriate for the current platform

    Examples:
        >>> normalize_path_for_platform("C:/Users/test/file.do")
        'C:\\Users\\test\\file.do'  # On Windows
        >>> normalize_path_for_platform("/Users/test/file.do")
        '/Users/test/file.do'  # On macOS/Linux
    """
    if not path:
        return path

    normalized = os.path.normpath(path)

    # On Windows, convert forward slashes to backslashes
    if platform.system() == "Windows" and '/' in normalized:
        normalized = normalized.replace('/', '\\')

    return normalized


def get_windows_path_help_message() -> str:
    """
    Get a help message for Windows path issues.

    Returns a standardized error message explaining common Windows path
    problems and how to fix them.

    Returns:
        Help message string (empty on non-Windows platforms)
    """
    if platform.system() != "Windows":
        return ""

    return (
        "\n\nCommon Windows path issues:\n"
        "1. Make sure the file path uses correct separators (use \\ instead of /)\n"
        "2. Check if the file exists in the specified location\n"
        "3. If using relative paths, the current working directory is: " + os.getcwd()
    )


def is_windows() -> bool:
    """Check if running on Windows."""
    return platform.system() == "Windows"


def is_macos() -> bool:
    """Check if running on macOS."""
    return platform.system() == "Darwin"


def is_linux() -> bool:
    """Check if running on Linux."""
    return platform.system() == "Linux"


def get_stata_executable_name(edition: str = "mp") -> str:
    """
    Get the Stata executable name for the current platform.

    Args:
        edition: Stata edition (mp, se, be)

    Returns:
        Executable name appropriate for the platform
    """
    edition = edition.lower()

    if is_windows():
        edition_map = {
            "mp": "StataMP-64.exe",
            "se": "StataSE-64.exe",
            "be": "Stata-64.exe",
        }
        return edition_map.get(edition, "StataMP-64.exe")

    elif is_macos():
        edition_map = {
            "mp": "stata-mp",
            "se": "stata-se",
            "be": "stata",
        }
        return edition_map.get(edition, "stata-mp")

    else:  # Linux
        edition_map = {
            "mp": "stata-mp",
            "se": "stata-se",
            "be": "stata",
        }
        return edition_map.get(edition, "stata-mp")


def quote_path_for_stata(path: str) -> str:
    """
    Quote a path for use in Stata commands.

    Handles platform-specific quoting requirements.

    Args:
        path: The file path to quote

    Returns:
        Quoted path safe for use in Stata commands
    """
    # Normalize first
    path = normalize_path_for_platform(path)

    # Escape quotes if present
    if '"' in path:
        path = path.replace('"', '\\"')

    return f'"{path}"'


def ensure_directory_exists(path: str) -> bool:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists

    Returns:
        True if directory exists or was created, False on error
    """
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False


def is_single_line_condition(condition: Optional[str]) -> bool:
    """True if a Data Viewer ``if`` condition has no line breaks.

    The condition is pasted into ``keep if ...``; a line break would let it
    run a second Stata command. Rejects \\n, \\r and every other boundary
    str.splitlines() recognises.
    """
    if not condition:
        return True
    return condition.splitlines() == [condition]


# ---------------------------------------------------------------------------
# Do-file text transforms (cls filtering and graph auto-naming)
# ---------------------------------------------------------------------------

_CLS_LINE_RE = re.compile(r'^\s*cls\s*$', re.IGNORECASE)
_LINE_RE = re.compile(r'([^\r\n]*)(\r\n|\r|\n|$)')


def _split_lines_keep_endings(code: str) -> List[Tuple[str, str]]:
    """Split text into (line, ending) pairs, keeping \r\n, \r or \n endings."""
    parts = []
    pos = 0
    length = len(code)
    while pos < length:
        match = _LINE_RE.match(code, pos)
        body, ending = match.group(1), match.group(2)
        parts.append((body, ending))
        pos = match.end()
    return parts


def comment_out_cls_lines(code: str) -> Tuple[str, int]:
    """Comment out bare ``cls`` commands, which crash PyStata.

    A line consisting only of ``cls`` (any case, any surrounding whitespace)
    becomes ``* COMMENTED OUT BY MCP: <line>``. A ``cls`` that continues the
    previous line (which ends with ``///``) is part of that command and is left
    unchanged. Line endings and the trailing newline are preserved.

    Returns:
        (processed_code, number_of_lines_commented_out)
    """
    if not code:
        return code, 0
    out = []
    count = 0
    previous_continues = False
    for body, ending in _split_lines_keep_endings(code):
        if not previous_continues and _CLS_LINE_RE.match(body):
            out.append(f"* COMMENTED OUT BY MCP: {body}{ending}")
            count += 1
        else:
            out.append(body + ending)
        previous_continues = body.rstrip().endswith('///')
    return ''.join(out), count


def insert_graph_name(rest: str, graph_name: str) -> Optional[str]:
    """Add ``name(<graph_name>, replace)`` to the arguments of a graph command.

    ``rest`` is the text after the graph command word(s). The scan tracks
    parenthesis depth, double-quoted strings and (nested) compound quotes
    `"..."', and treats ``//`` (at the start or after whitespace) and ``/*``
    outside quotes as comments. The name option goes right after the first
    top-level comma; if there is none, ``, name(...)`` is appended at the end of
    the code, before trailing whitespace and any comment.

    Returns None (leave the line unchanged) when quotes or parentheses are
    unbalanced, because the option position cannot be determined safely.
    """
    depth = 0
    quotes = []  # stack of 'dq' ("...") and 'cq' (`"..."')
    comma_pos = None
    code_end = 0
    i = 0
    n = len(rest)
    while i < n:
        if quotes:
            if quotes[-1] == 'cq':
                if rest.startswith('`"', i):
                    quotes.append('cq')
                    i += 2
                    continue
                if rest.startswith('"\'', i):
                    quotes.pop()
                    i += 2
                    code_end = i
                    continue
            elif rest[i] == '"':
                quotes.pop()
                i += 1
                code_end = i
                continue
            i += 1
            continue

        ch = rest[i]
        if rest.startswith('`"', i):
            quotes.append('cq')
            i += 2
            continue
        if ch == '"':
            quotes.append('dq')
            i += 1
            continue
        if rest.startswith('/*', i):
            close = rest.find('*/', i + 2)
            if close == -1:
                break  # block comment runs to the end of the line
            i = close + 2
            continue
        if rest.startswith('//', i) and (i == 0 or rest[i - 1].isspace()):
            break  # line comment
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                logging.debug("Graph auto-naming skipped (unbalanced parentheses): %s", rest[:200])
                return None
        elif ch == ',' and depth == 0 and comma_pos is None:
            comma_pos = i
        if not ch.isspace():
            code_end = i + 1
        i += 1

    if quotes or depth != 0:
        logging.debug("Graph auto-naming skipped (unbalanced quotes or parentheses): %s", rest[:200])
        return None

    if comma_pos is not None:
        return f"{rest[:comma_pos + 1]} name({graph_name}, replace){rest[comma_pos + 1:]}"
    return f"{rest[:code_end]}, name({graph_name}, replace){rest[code_end:]}"


GRAPH_COMMAND_RE = re.compile(
    r'^(\s*)(scatter|histogram|twoway|kdensity|graph\s+(bar|box|dot|pie|matrix|hbar|hbox|combine))\s+(.*)$',
    re.IGNORECASE,
)
_HAS_NAME_OPTION_RE = re.compile(r'\bname\s*\(', re.IGNORECASE)
_DELIMIT_RE = re.compile(
    r'^\s*#d(?:e(?:l(?:i(?:m(?:i(?:t)?)?)?)?)?)?\s*(;|cr)(?=\s|$|//|/\*)',
    re.IGNORECASE,
)


def _block_comment_depth_after(line: str, depth: int) -> int:
    """Return the ``/* */`` nesting depth after scanning one line."""
    quotes = []
    i = 0
    n = len(line)
    while i < n:
        if depth > 0:
            if line.startswith('/*', i):
                depth += 1
                i += 2
            elif line.startswith('*/', i):
                depth -= 1
                i += 2
            else:
                i += 1
            continue
        if quotes:
            if quotes[-1] == 'cq':
                if line.startswith('`"', i):
                    quotes.append('cq')
                    i += 2
                    continue
                if line.startswith('"\'', i):
                    quotes.pop()
                    i += 2
                    continue
            elif line[i] == '"':
                quotes.pop()
            i += 1
            continue
        if line.startswith('`"', i):
            quotes.append('cq')
            i += 2
        elif line[i] == '"':
            quotes.append('dq')
            i += 1
        elif line.startswith('/*', i):
            depth += 1
            i += 2
        elif line.startswith('//', i) and (i == 0 or line[i - 1].isspace()):
            break
        else:
            i += 1
    return depth


def auto_name_graph_lines(lines: List[str], start_counter: int) -> Tuple[List[str], int]:
    """Give unnamed graph commands a unique ``name(graphN, replace)`` option.

    ``lines`` are logical lines (``///`` continuations already joined).
    Commands that already have ``name(`` are left alone. Naming is skipped
    while ``#delimit ;`` is in effect and inside ``/* ... */`` block comments,
    and for lines whose quotes or parentheses are unbalanced.

    Returns:
        (new_lines, last_counter_used)
    """
    counter = start_counter
    result = []
    semicolon_mode = False
    block_depth = 0
    for line in lines:
        line = str(line) if line is not None else ""
        if block_depth > 0:
            block_depth = _block_comment_depth_after(line, block_depth)
            result.append(line)
            continue

        delimit = _DELIMIT_RE.match(line)
        if delimit:
            semicolon_mode = delimit.group(1) == ';'
            result.append(line)
            continue

        new_line = line
        if not semicolon_mode:
            match = GRAPH_COMMAND_RE.match(line)
            if match and not _HAS_NAME_OPTION_RE.search(match.group(4) or ""):
                indent = match.group(1) or ""
                graph_cmd = match.group(2) or ""
                named = insert_graph_name(match.group(4) or "", f"graph{counter + 1}")
                if named is not None:
                    counter += 1
                    new_line = f"{indent}{graph_cmd} {named}"
        block_depth = _block_comment_depth_after(line, 0)
        result.append(new_line)
    return result, counter


# Platform-specific constants
PLATFORM = platform.system()
IS_WINDOWS = PLATFORM == "Windows"
IS_MACOS = PLATFORM == "Darwin"
IS_LINUX = PLATFORM == "Linux"
