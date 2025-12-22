#!/usr/bin/env python3
"""
Direct test of timeout functionality by calling run_stata_file directly
"""

import sys
import time
from pathlib import Path

# Add the src directory to Python path
TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from stata_mcp_server import run_stata_file

TEST_FILE = TESTS_DIR / "test_timeout.do"

def run_timeout_test(timeout_seconds, test_name):
    """Run a timeout test with specified duration (not a pytest test)."""
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"Timeout set to: {timeout_seconds} seconds ({timeout_seconds/60:.2f} minutes)")
    print(f"{'='*70}\n")

    start_time = time.time()
    result = run_stata_file(str(TEST_FILE), timeout=timeout_seconds)
    elapsed_time = time.time() - start_time

    print(f"\n{'='*70}")
    print(f"RESULTS for {test_name}:")
    print(f"Elapsed time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
    print(f"Expected timeout: {timeout_seconds} seconds")
    print(f"Timeout triggered: {'TIMEOUT' in result}")
    print(f"{'='*70}\n")

    # Print last 500 characters of result
    print("Last 500 characters of output:")
    print(result[-500:])
    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    # Test 1: 12 seconds (0.2 minutes) - should timeout quickly
    run_timeout_test(12, "Test 1: 12 second timeout (0.2 minutes)")

    # Wait a bit between tests
    print("\nWaiting 5 seconds before next test...\n")
    time.sleep(5)

    # Test 2: 30 seconds (0.5 minutes) - should also timeout
    run_timeout_test(30, "Test 2: 30 second timeout (0.5 minutes)")
