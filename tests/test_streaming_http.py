#!/usr/bin/env python3
"""
Integration test for the plain HTTP SSE streaming endpoint.

The test skips cleanly when no local server is available. If the server is
running, the assertions validate that the endpoint really streams text/event-
stream data and that the expected Stata output is observed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests


TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
SERVER_URL = os.environ.get("STATA_MCP_SERVER_URL", "http://localhost:4000")
TEST_FILE = FIXTURES_DIR / "test_streaming.do"
TIMEOUT = 60


def _require_running_server(base_url: str) -> dict:
    """Return health payload or skip if the local integration server is unavailable."""
    try:
        response = requests.get(f"{base_url}/health", timeout=3)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        pytest.skip(f"Integration server not available at {base_url}: {exc}")

    if not payload.get("stata_available", False):
        pytest.skip("Integration server is running, but Stata is not available")

    return payload


def test_streaming_http():
    """Verify that the SSE endpoint emits real streamed output."""
    if not TEST_FILE.exists():
        pytest.skip(f"Test fixture not found: {TEST_FILE}")

    _require_running_server(SERVER_URL)

    url = f"{SERVER_URL}/run_file/stream"
    params = {"file_path": str(TEST_FILE), "timeout": TIMEOUT}

    with requests.get(url, params=params, stream=True, timeout=TIMEOUT) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type

        lines = []
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            lines.append(line)
            if "Test complete!" in line:
                break

    assert lines, "Expected at least one streamed SSE line"
    assert any(line.startswith("data: ") for line in lines)

    joined_lines = "\n".join(lines)
    assert "Starting execution of test_streaming.do" in joined_lines
    assert "Iteration 1" in joined_lines
    assert "Test complete!" in joined_lines
