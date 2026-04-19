#!/usr/bin/env python3
"""
Integration test for MCP HTTP notifications.

This test is intentionally skip-based when the local integration prerequisites
are absent. If a server is available, the assertions are real and verify that
log and progress notifications are delivered through the MCP HTTP transport.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest
import requests


TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
DEFAULT_SERVER_URL = os.environ.get("STATA_MCP_SERVER_URL", "http://localhost:4000")
DEFAULT_STREAMABLE_URL = os.environ.get("STATA_MCP_STREAMABLE_URL", f"{DEFAULT_SERVER_URL}/mcp-streamable")
DEFAULT_TEST_FILE = FIXTURES_DIR / "test_streaming.do"


class NotificationMonitor:
    """Collect log and progress callbacks emitted by the MCP client."""

    def __init__(self):
        self.log_messages: list[dict[str, str]] = []
        self.progress_updates: list[dict[str, float | str | None]] = []

    async def logging_callback(self, params):
        self.log_messages.append(
            {
                "level": str(getattr(params, "level", "")),
                "data": str(getattr(params, "data", "")),
            }
        )

    async def progress_callback(self, progress, total, message):
        self.progress_updates.append(
            {
                "progress": progress,
                "total": total,
                "message": message,
            }
        )


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


async def _run_notification_probe(
    streamable_url: str,
    test_file: Path,
) -> tuple[NotificationMonitor, object]:
    """Execute a file through MCP HTTP and capture notification callbacks."""
    pytest.importorskip("mcp")
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    monitor = NotificationMonitor()

    async with streamablehttp_client(streamable_url) as (read_stream, write_stream, _session_info):
        async with ClientSession(
            read_stream,
            write_stream,
            logging_callback=monitor.logging_callback,
        ) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tool_names = {tool.name for tool in tools_result.tools}
            assert "stata_run_file" in tool_names

            result = await session.call_tool(
                "stata_run_file",
                arguments={
                    "file_path": str(test_file),
                    "timeout": 60,
                },
                read_timeout_seconds=timedelta(seconds=90),
                progress_callback=monitor.progress_callback,
            )

    return monitor, result


@pytest.mark.asyncio
async def test_notifications():
    """Verify MCP logging and progress notifications when a local server is available."""
    if not DEFAULT_TEST_FILE.exists():
        pytest.skip(f"Test fixture not found: {DEFAULT_TEST_FILE}")

    _require_running_server(DEFAULT_SERVER_URL)

    monitor, result = await _run_notification_probe(DEFAULT_STREAMABLE_URL, DEFAULT_TEST_FILE)

    assert not result.isError
    assert monitor.log_messages, "Expected at least one MCP log notification"
    assert monitor.progress_updates, "Expected at least one MCP progress notification"

    joined_logs = "\n".join(message["data"] for message in monitor.log_messages)
    assert "Starting Stata execution" in joined_logs
    assert "Execution completed" in joined_logs

    progress_messages = [str(update["message"]) for update in monitor.progress_updates if update["message"]]
    assert any("Starting Stata execution" in message for message in progress_messages)

    text_chunks = [content.text for content in result.content if hasattr(content, "text")]
    combined_result = "\n".join(text_chunks)
    assert "Test complete!" in combined_result
