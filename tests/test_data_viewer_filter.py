#!/usr/bin/env python3
"""Data Viewer filter conditions must stay on one line (no second command)."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import stata_mcp_server as server
from utils import is_single_line_condition


@pytest.mark.parametrize(
    "condition, expected",
    [
        (None, True),
        ("", True),
        ("price > 5000 & mpg < 30", True),
        ('make == "AMC Concord"', True),
        ("price>1\nshell x", False),
        ("price>1\rshell x", False),
        ("price>1\r\nshell x", False),
        ("price>1\n", False),
        ("price>1 shell x", False),
    ],
)
def test_is_single_line_condition(condition, expected):
    assert is_single_line_condition(condition) is expected


def test_view_data_rejects_multiline_condition_before_touching_stata(monkeypatch):
    class Boom:
        def get_data(self, *args, **kwargs):  # pragma: no cover - must not be reached
            raise AssertionError("session manager was called")

    monkeypatch.setattr(server, "multi_session_enabled", True)
    monkeypatch.setattr(server, "session_manager", Boom())
    client = TestClient(server.app, base_url="http://localhost:4000")
    response = client.get("/view_data?if_condition=price%3E1%0Ashell%20x")
    assert response.status_code == 400
    assert response.json() == {"status": "error", "message": "Filter condition must be a single line"}


def test_worker_get_data_also_checks_condition():
    import inspect
    import stata_worker

    source = inspect.getsource(stata_worker)
    assert "elif not is_single_line_condition(if_condition):" in source
