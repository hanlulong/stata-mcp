#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility functions for Stata MCP Server

This module contains common utility functions used across the codebase,
extracted to reduce duplication and improve maintainability.
"""

import os
import platform


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


# Platform-specific constants
PLATFORM = platform.system()
IS_WINDOWS = PLATFORM == "Windows"
IS_MACOS = PLATFORM == "Darwin"
IS_LINUX = PLATFORM == "Linux"
