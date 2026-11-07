#!/usr/bin/env python3
"""Run Selection sends its code in a JSON body (large and non-ASCII selections).

These tests do not need Stata: the execution layer is replaced by stubs, and
TestClient is not used as a context manager, so the server lifespan (which
starts Stata) never runs.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import stata_mcp_server as server
from fastapi_mcp.openapi.convert import convert_openapi_to_mcp_tools


ASCII_SELECTION = ('display "x"\n' * 4000)[: 40 * 1024]  # 40 KiB
CJK_SELECTION = "* 中文注释\n" * 2000  # 30,000 bytes of UTF-8, over 20 KiB of it CJK
assert len(ASCII_SELECTION.encode("utf-8")) == 40 * 1024
assert len("中文注释".encode("utf-8")) * 2000 > 20 * 1024


class FakeSessionManager:
    def __init__(self):
        self.calls = []

    def execute(self, code, session_id=None, timeout=600.0):
        self.calls.append({"code": code, "session_id": session_id, "timeout": timeout})
        return {"status": "success", "output": f"ran {len(code)} chars"}


@pytest.fixture
def client():
    return TestClient(server.app, base_url="http://localhost:4000")


@pytest.fixture
def fake_sessions(monkeypatch):
    fake = FakeSessionManager()
    monkeypatch.setattr(server, "multi_session_enabled", True)
    monkeypatch.setattr(server, "session_manager", fake)
    return fake


@pytest.fixture
def fake_stream(monkeypatch):
    calls = []

    async def fake_selection_stream(selection, timeout=600, working_dir=None, session_id=None, execution_id=None):
        calls.append({
            "selection": selection,
            "timeout": timeout,
            "working_dir": working_dir,
            "session_id": session_id,
            "execution_id": execution_id,
        })
        yield f"data: received {len(selection)} chars\n\n"
        yield "data: *** Execution completed ***\n\n"

    monkeypatch.setattr(server, "stata_run_selection_stream", fake_selection_stream)
    return calls


def test_run_selection_openapi_uses_request_body():
    operation = server.app.openapi()["paths"]["/run_selection"]["post"]
    assert operation["operationId"] == "stata_run_selection"
    assert "requestBody" in operation
    assert not [p for p in operation.get("parameters", []) if p.get("in") == "query"]


def test_mcp_tool_arguments_are_unchanged():
    tools, operation_map = convert_openapi_to_mcp_tools(server.app.openapi())
    tool = next(t for t in tools if t.name == "stata_run_selection")
    properties = tool.inputSchema["properties"]
    for name in ("selection", "timeout", "session_id", "working_dir"):
        assert name in properties, name
    assert tool.inputSchema.get("required") == ["selection"]
    assert operation_map["stata_run_selection"]["method"] == "post"
    # The streaming routes stay out of the MCP tool list.
    assert all("stream" not in t.name for t in tools)


@pytest.mark.parametrize("selection", [ASCII_SELECTION, CJK_SELECTION], ids=["ascii-40KiB", "cjk-20KiB"])
def test_post_run_selection_accepts_large_body(client, fake_sessions, selection):
    response = client.post(
        "/run_selection",
        json={"selection": selection, "timeout": 30, "session_id": "s1"},
    )
    assert response.status_code == 200, response.text
    assert len(fake_sessions.calls) == 1
    call = fake_sessions.calls[0]
    assert selection in call["code"]
    assert call["session_id"] == "s1"
    assert call["timeout"] == 30.0


def test_post_run_selection_no_longer_reads_query_parameters(client, fake_sessions):
    response = client.post("/run_selection", params={"selection": 'display "hi"'})
    assert response.status_code == 422
    assert fake_sessions.calls == []


@pytest.mark.parametrize("selection", [ASCII_SELECTION, CJK_SELECTION], ids=["ascii-40KiB", "cjk-20KiB"])
def test_post_run_selection_stream_accepts_large_body(client, fake_stream, selection):
    response = client.post(
        "/run_selection/stream",
        json={
            "selection": selection,
            "timeout": 30,
            "execution_id": "selection-1730000000000-ab12cd34",
            "working_dir": "/tmp",
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert f"received {len(selection)} chars" in response.text
    assert fake_stream == [{
        "selection": selection,
        "timeout": 30,
        "working_dir": "/tmp",
        "session_id": None,
        "execution_id": "selection-1730000000000-ab12cd34",
    }]


def test_get_run_selection_stream_still_works(client, fake_stream):
    response = client.get(
        "/run_selection/stream",
        params={"selection": 'display "hi"', "timeout": "0", "execution_id": "selection-1"},
    )
    assert response.status_code == 200, response.text
    assert "received 12 chars" in response.text
    # Non-positive timeouts fall back to the default, as before.
    assert fake_stream[0]["timeout"] == 600
    assert fake_stream[0]["execution_id"] == "selection-1"
