#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pytest Configuration and Shared Fixtures

This module provides shared fixtures for all tests in the stata-mcp project.
Fixtures are organized by category: configuration, mocking, and integration.
"""

import os
import sys
import pytest
from typing import Generator, Optional
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture
def stata_path() -> str:
    """Get Stata installation path from environment or use default."""
    return os.environ.get('STATA_PATH', '/Applications/StataNow')


@pytest.fixture
def stata_edition() -> str:
    """Get Stata edition from environment or use default."""
    return os.environ.get('STATA_EDITION', 'mp')


@pytest.fixture
def skip_stata_tests() -> bool:
    """Check if Stata tests should be skipped."""
    return os.environ.get('SKIP_STATA_TESTS', 'false').lower() == 'true'


@pytest.fixture
def test_data_dir() -> str:
    """Get the test data/fixtures directory path."""
    return os.path.join(os.path.dirname(__file__), 'fixtures')


# =============================================================================
# Skip Conditions
# =============================================================================

@pytest.fixture
def requires_stata(stata_path: str, skip_stata_tests: bool):
    """Skip test if Stata is not available."""
    if skip_stata_tests:
        pytest.skip("SKIP_STATA_TESTS=true")
    if not os.path.exists(stata_path):
        pytest.skip(f"Stata not found at {stata_path}")


# =============================================================================
# Mock Fixtures (for unit tests without Stata)
# =============================================================================

@pytest.fixture
def mock_stata() -> Generator[MagicMock, None, None]:
    """
    Create a mock Stata module for unit tests.

    This mock simulates the pystata.stata interface without requiring
    an actual Stata installation.
    """
    mock = MagicMock()
    mock.run = MagicMock(return_value=None)
    mock.config = MagicMock()

    # Mock common responses
    mock.run.side_effect = lambda code, echo=True: None

    yield mock


@pytest.fixture
def mock_pystata(mock_stata: MagicMock) -> Generator[MagicMock, None, None]:
    """
    Mock the entire pystata module.

    Use this fixture when testing code that imports pystata.
    """
    with patch.dict('sys.modules', {'pystata': MagicMock(), 'pystata.stata': mock_stata}):
        yield mock_stata


# =============================================================================
# Session Manager Fixtures (for integration tests)
# =============================================================================

@pytest.fixture
def session_manager_config(stata_path: str, stata_edition: str) -> dict:
    """Get configuration for SessionManager."""
    return {
        'stata_path': stata_path,
        'stata_edition': stata_edition,
        'max_sessions': 4,
        'enabled': True,
    }


@pytest.fixture
def session_manager(
    requires_stata,
    session_manager_config: dict
) -> Generator:
    """
    Create a SessionManager instance for integration tests.

    This fixture automatically starts and stops the session manager.
    """
    from session_manager import SessionManager

    manager = SessionManager(**session_manager_config)

    if not manager.start():
        pytest.skip("Failed to start session manager")

    yield manager

    # Cleanup
    manager.stop()


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_stata_code() -> str:
    """Simple Stata code for testing."""
    return 'display "Hello from Stata: " 2+2'


@pytest.fixture
def sample_stata_output() -> str:
    """Expected output from sample Stata code."""
    return "Hello from Stata:  4"


@pytest.fixture
def sample_do_file(tmp_path) -> str:
    """Create a temporary .do file for testing."""
    do_file = tmp_path / "test_sample.do"
    do_file.write_text('display "Test output: " 1+1\n')
    return str(do_file)


@pytest.fixture
def long_running_do_file(tmp_path) -> str:
    """Create a .do file that takes a while to execute."""
    do_file = tmp_path / "test_long.do"
    do_file.write_text('sleep 3000\ndisplay "Done"\n')
    return str(do_file)


# =============================================================================
# Output Filter Fixtures
# =============================================================================

@pytest.fixture
def sample_stata_raw_output() -> str:
    """Sample raw Stata output with noise for filter testing."""
    return """
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
rep78           int     %8.0g                 Repair record 1978
headroom        float   %6.1f                 Headroom (in.)
trunk           int     %8.0g                 Trunk space (cu. ft.)
weight          int     %8.0gc                Weight (lbs.)
length          int     %8.0g                 Length (in.)
turn            int     %8.0g                 Turn circle (ft.)
displacement    int     %8.0g                 Displacement (cu. in.)
gear_ratio      float   %6.2f                 Gear ratio
foreign         byte    %8.0g      origin     Car origin
--------------------------------------------------------------------------------
Sorted by: foreign
"""


# =============================================================================
# API Testing Fixtures
# =============================================================================

@pytest.fixture
def api_base_url() -> str:
    """Base URL for API testing."""
    return "http://localhost:4000"


@pytest.fixture
def api_headers() -> dict:
    """Default headers for API requests."""
    return {
        "Content-Type": "application/json",
    }


# =============================================================================
# Utility Functions (not fixtures)
# =============================================================================

def stata_available() -> bool:
    """Check if Stata is available for testing."""
    stata_path = os.environ.get('STATA_PATH', '/Applications/StataNow')
    skip = os.environ.get('SKIP_STATA_TESTS', 'false').lower() == 'true'
    return not skip and os.path.exists(stata_path)


# Markers for conditional test execution
requires_stata_marker = pytest.mark.skipif(
    not stata_available(),
    reason="Stata not available"
)
