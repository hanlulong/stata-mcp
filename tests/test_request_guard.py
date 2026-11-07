#!/usr/bin/env python3
"""Local-request guard: cross-site and DNS-rebinding requests get 403.

The TestClient is not used as a context manager, so the lifespan (and Stata)
never starts. Blocked requests never reach a route handler.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import stata_mcp_server as server


@pytest.fixture
def client():
    return TestClient(server.app, base_url="http://localhost:4000")


@pytest.fixture(autouse=True)
def default_guard_config(monkeypatch):
    monkeypatch.setattr(server, "GUARD_BIND_HOST", "localhost")
    monkeypatch.setattr(server, "GUARD_EXTRA_HOSTS", set())


PROTECTED = [
    ("POST", "/run_selection?selection=display%201"),
    ("GET", "/run_selection/stream?selection=display%201"),
    ("GET", "/run_file?file_path=/tmp/x.do"),
    ("GET", "/run_file/stream?file_path=/tmp/x.do"),
    ("GET", "/interactive?code=display%201"),
    ("POST", "/v1/tools"),
    ("GET", "/sessions"),
    ("POST", "/mcp-streamable"),
]

ATTACKS = {
    "evil-origin": {"origin": "https://evil.example"},
    "rebinding-host": {"host": "attacker.example:4000"},
    "cross-site-no-origin": {"sec-fetch-site": "cross-site", "sec-fetch-mode": "no-cors"},
    "null-origin": {"origin": "null"},
}


@pytest.mark.parametrize("method, path", PROTECTED)
@pytest.mark.parametrize("attack", sorted(ATTACKS))
def test_attacks_are_blocked(client, method, path, attack):
    response = client.request(method, path, headers=ATTACKS[attack], json={} if method == "POST" else None)
    assert response.status_code == 403
    assert "local-request guard" in response.text
    assert response.headers["content-type"].startswith("text/plain")


def test_cross_site_navigation_to_interactive_is_blocked(client):
    # Browser-mode /interactive runs ?code= on load, so a top-level navigation
    # from another site must be stopped by the guard itself.
    response = client.get(
        "/interactive?code=display%201",
        headers={"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate"},
    )
    assert response.status_code == 403


def test_same_site_from_non_loopback_host_is_treated_as_cross_site(client, monkeypatch):
    monkeypatch.setattr(server, "GUARD_EXTRA_HOSTS", {"devbox.lan"})
    response = client.get("/sessions", headers={"host": "devbox.lan:4000", "sec-fetch-site": "same-site"})
    assert response.status_code == 403


@pytest.mark.parametrize("host", ["localhost:4000", "127.0.0.1:4000", "[::1]:4000"])
def test_loopback_hosts_pass(client, host):
    response = client.get("/health", headers={"host": host})
    assert response.status_code != 403


def test_node_fetch_shape_passes(client):
    # Node's fetch sends sec-fetch-mode: cors with no Origin and no Sec-Fetch-Site.
    response = client.get("/health", headers={"sec-fetch-mode": "cors"})
    assert response.status_code != 403


def test_mcp_inspector_origins_pass(client):
    response = client.get(
        "/health", headers={"origin": "http://localhost:6274", "sec-fetch-site": "same-site"}
    )
    assert response.status_code != 403
    # An allowed Origin skips the Sec-Fetch-Site check (127.0.0.1 vs localhost).
    response = client.get(
        "/health", headers={"origin": "http://127.0.0.1:6274", "sec-fetch-site": "cross-site"}
    )
    assert response.status_code != 403


def test_typed_url_navigation_to_interactive_passes_with_frame_headers(client):
    response = client.get(
        "/interactive", headers={"sec-fetch-site": "none", "sec-fetch-mode": "navigate"}
    )
    assert response.status_code != 403
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("content-security-policy") == "frame-ancestors 'none'"


def test_cross_site_navigation_to_graph_image_passes(client):
    response = client.get(
        "/graphs/x.png", headers={"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate"}
    )
    assert response.status_code != 403


def test_cross_site_fetch_of_graph_image_is_blocked(client):
    response = client.get(
        "/graphs/x.png", headers={"sec-fetch-site": "cross-site", "sec-fetch-mode": "no-cors"}
    )
    assert response.status_code == 403


def test_allowed_host_passes_after_configuring(client):
    server.configure_request_guard("localhost", ["code.example.com"])
    response = client.get("/health", headers={"host": "code.example.com"})
    assert response.status_code != 403
    response = client.get(
        "/health", headers={"host": "code.example.com", "origin": "https://code.example.com"}
    )
    assert response.status_code != 403
    response = client.get("/health", headers={"host": "other.example.com"})
    assert response.status_code == 403


def test_bind_host_is_accepted(client):
    server.configure_request_guard("0.0.0.0", [])
    response = client.get("/health", headers={"host": "0.0.0.0:4000"})
    assert response.status_code != 403


def test_blocked_request_log_omits_query_string(client, caplog):
    with caplog.at_level("WARNING"):
        client.post("/run_selection?selection=SECRET_CODE", headers={"origin": "https://evil.example"})
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "Blocked by local-request guard" in messages
    assert "/run_selection" in messages
    assert "SECRET_CODE" not in messages
    assert "stata-vscode.allowedHosts" in messages


def test_websocket_scope_is_closed_with_policy_violation():
    sent = []

    async def app(scope, receive, send):  # pragma: no cover - must not be reached
        raise AssertionError("guarded app was called")

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "websocket",
        "path": "/ws",
        "headers": [(b"host", b"localhost:4000"), (b"origin", b"https://evil.example")],
    }
    asyncio.run(server.LocalRequestGuardMiddleware(app)(scope, receive, send))
    assert sent == [{"type": "websocket.close", "code": 1008}]


def test_lifespan_scope_passes_through():
    called = []

    async def app(scope, receive, send):
        called.append(scope["type"])

    asyncio.run(server.LocalRequestGuardMiddleware(app)({"type": "lifespan"}, None, None))
    assert called == ["lifespan"]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("localhost:4000", "localhost"),
        ("LOCALHOST", "localhost"),
        ("localhost.:4000", "localhost"),
        ("127.0.0.1:4000", "127.0.0.1"),
        ("[::1]:4000", "::1"),
        ("[::1]", "::1"),
        ("::1", "::1"),
        ("code.example.com", "code.example.com"),
        ("", None),
        (None, None),
        ("[::1", None),
        ("localhost:abc", None),
    ],
)
def test_parse_host_header(value, expected):
    assert server.parse_host_header(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("http://localhost:6274", "localhost"),
        ("https://evil.example", "evil.example"),
        ("http://[::1]:3000", "::1"),
        ("HTTP://LOCALHOST", "localhost"),
        ("null", None),
        ("vscode-webview://abc123", None),
        ("file://", None),
        ("http://localhost:notaport", None),
        ("", None),
    ],
)
def test_parse_origin_header(value, expected):
    assert server.parse_origin_header(value) == expected


def test_internal_client_uses_loopback_host():
    with open(server.__file__, "r", encoding="utf-8") as f:
        source = f.read()
    assert "http://apiserver" not in source
    assert 'base_url="http://localhost"' in source


def test_in_process_mcp_client_passes_guard():
    # fastapi_mcp calls the REST routes through httpx.ASGITransport; the
    # Host it sends comes from base_url.
    import httpx

    async def call(base_url):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app), base_url=base_url
        ) as http_client:
            return (await http_client.get("/health")).status_code

    assert asyncio.run(call("http://localhost")) == 200
    assert asyncio.run(call("http://apiserver")) == 403
