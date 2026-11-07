#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for temporary graph artifact helpers."""

import asyncio
import os
import time

import pytest

from graph_artifacts import (
    build_graph_record,
    cleanup_graph_batches,
    create_batch_context,
    find_latest_graph_by_name,
    generate_execution_id,
    get_graphs_root,
    is_safe_id,
    load_batch_manifest,
    normalize_graph_path,
    resolve_batch_graph_path,
    write_batch_manifest,
)


def test_get_graphs_root_prefers_env(monkeypatch, tmp_path):
    env_root = tmp_path / "env-graphs"
    monkeypatch.setenv("STATA_MCP_GRAPHS_DIR", str(env_root))

    resolved = get_graphs_root(configured_root=None, extension_path=str(tmp_path / "extension"))

    assert resolved == os.path.abspath(str(env_root))


def test_normalize_graph_path_replaces_backslashes():
    assert normalize_graph_path(r"C:\graphs\batch\graph1.png") == "C:/graphs/batch/graph1.png"


def test_manifest_round_trip_and_latest_lookup(tmp_path):
    graphs_root = str(tmp_path / "graphs-root")

    old_batch = create_batch_context(graphs_root, execution_id="exec-old", source="test")
    old_graph_file = os.path.join(old_batch["batch_dir"], "graph1.png")
    with open(old_graph_file, "wb") as handle:
        handle.write(b"old")
    old_record = build_graph_record(old_batch, "graph1", old_graph_file, order_in_batch=0)
    write_batch_manifest(old_batch, [old_record])

    time.sleep(0.01)

    new_batch = create_batch_context(graphs_root, execution_id="exec-new", source="test")
    new_graph_file = os.path.join(new_batch["batch_dir"], "graph1.png")
    with open(new_graph_file, "wb") as handle:
        handle.write(b"new")
    new_record = build_graph_record(new_batch, "graph1", new_graph_file, order_in_batch=0)
    manifest_path = write_batch_manifest(new_batch, [new_record])

    loaded_manifest = load_batch_manifest(new_batch["batch_dir"])
    resolved = find_latest_graph_by_name(graphs_root, "graph1")

    assert manifest_path.endswith("manifest.json")
    assert loaded_manifest is not None
    assert loaded_manifest["batchId"] == "exec-new"
    assert resolved is not None
    assert resolved["path"] == os.path.realpath(new_graph_file)
    assert resolved["manifest"]["batchId"] == "exec-new"


def test_cleanup_graph_batches_keeps_requested_batch_and_latest(tmp_path):
    graphs_root = str(tmp_path / "graphs-root")
    kept_batch_ids = []

    for index in range(4):
        batch = create_batch_context(graphs_root, execution_id=f"exec-{index}", source="test")
        graph_file = os.path.join(batch["batch_dir"], f"graph{index}.png")
        with open(graph_file, "wb") as handle:
            handle.write(str(index).encode("ascii"))
        record = build_graph_record(batch, f"graph{index}", graph_file, order_in_batch=index)
        write_batch_manifest(batch, [record])
        os.utime(batch["batch_dir"], (time.time() + index, time.time() + index))
        kept_batch_ids.append(batch["batch_id"])

    removed = cleanup_graph_batches(
        graphs_root,
        keep_batch_ids=[kept_batch_ids[1]],
        keep_latest=1
    )

    assert kept_batch_ids[0] in removed
    assert os.path.isdir(os.path.join(graphs_root, kept_batch_ids[1]))
    assert os.path.isdir(os.path.join(graphs_root, kept_batch_ids[3]))
    assert not os.path.exists(os.path.join(graphs_root, kept_batch_ids[0]))


def test_resolve_batch_graph_path_rejects_traversal_and_directory_target(tmp_path):
    graphs_root = str(tmp_path / "graphs-root")
    batch = create_batch_context(graphs_root, execution_id="exec-safe", source="test")
    graph_file = os.path.join(batch["batch_dir"], "graph1.png")
    with open(graph_file, "wb") as handle:
        handle.write(b"png")

    valid_path = resolve_batch_graph_path(graphs_root, batch["batch_id"], "graph1.png")
    traversal_path = resolve_batch_graph_path(graphs_root, batch["batch_id"], "../outside.png")
    directory_target = resolve_batch_graph_path(graphs_root, batch["batch_id"], ".")

    assert valid_path == os.path.realpath(graph_file)
    assert traversal_path is None
    assert directory_target is None


def _plant_secret(tmp_path):
    graphs_root = tmp_path / "graphs-root"
    graphs_root.mkdir()
    secret_dir = tmp_path / "secretdir"
    secret_dir.mkdir()
    (secret_dir / "secret.txt").write_text("TOP-SECRET-CONTENT")
    return str(graphs_root), str(secret_dir)


@pytest.mark.parametrize(
    "batch_id",
    [
        "/abs/secretdir",
        "../secretdir",
        "..%2Fsecretdir",  # what the route sees after Starlette's single decode
        "C:\\x",
        "",
        "a" * 129,
        "exec-1\n",
    ],
)
def test_resolve_batch_graph_path_rejects_unsafe_batch_ids(tmp_path, batch_id):
    graphs_root, secret_dir = _plant_secret(tmp_path)
    if batch_id == "/abs/secretdir":
        batch_id = secret_dir
    assert resolve_batch_graph_path(graphs_root, batch_id, "secret.txt") is None


def test_resolve_batch_graph_path_accepts_valid_batch_id(tmp_path):
    graphs_root, _ = _plant_secret(tmp_path)
    batch_id = "selection-1730000000000-ab12cd34"
    os.makedirs(os.path.join(graphs_root, batch_id))
    graph_file = os.path.join(graphs_root, batch_id, "graph1.png")
    with open(graph_file, "wb") as handle:
        handle.write(b"png")
    assert resolve_batch_graph_path(graphs_root, batch_id, "graph1.png") == os.path.realpath(graph_file)
    assert is_safe_id("a" * 128)


def test_resolve_batch_graph_path_rejects_symlinked_batch_dir(tmp_path):
    graphs_root, secret_dir = _plant_secret(tmp_path)
    link = os.path.join(graphs_root, "exec-link")
    try:
        os.symlink(secret_dir, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    assert resolve_batch_graph_path(graphs_root, "exec-link", "secret.txt") is None


def test_create_batch_context_replaces_unsafe_execution_id(tmp_path):
    graphs_root = str(tmp_path / "graphs-root")
    batch = create_batch_context(graphs_root, execution_id="../x", source="test")
    assert batch["batch_id"] != "../x"
    assert is_safe_id(batch["batch_id"])
    assert batch["execution_id"] == batch["batch_id"]
    assert not os.path.exists(str(tmp_path / "x"))
    assert os.path.dirname(batch["batch_dir"]) == os.path.abspath(graphs_root)


def test_create_batch_context_keeps_generated_ids():
    assert is_safe_id(generate_execution_id("selection-stream"))
    # Same shape as the extension's createExecutionId().
    assert is_safe_id("interactive-selection-1730000000000-k3j9x0ab")


def _raw_asgi_get(app, path, raw_path):
    """Call the app with an exact ASGI scope (TestClient normalizes %25 escapes)."""
    status = {}
    body = bytearray()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": raw_path,
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"localhost:4000")],
        "client": ("127.0.0.1", 50000),
        "server": ("localhost", 4000),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
        elif message["type"] == "http.response.body":
            body.extend(message.get("body", b""))

    asyncio.run(app(scope, receive, send))
    return status.get("code"), bytes(body)


def test_graph_route_does_not_serve_files_outside_graphs_root(tmp_path, monkeypatch):
    import stata_mcp_server as server

    graphs_root, _ = _plant_secret(tmp_path)
    monkeypatch.setattr(server, "get_effective_graphs_root", lambda: graphs_root)
    # The request line /graphs/batch/..%252Fsecretdir/secret.txt, as uvicorn
    # hands it to the app (path decoded once).
    status, body = _raw_asgi_get(
        server.app,
        "/graphs/batch/..%2Fsecretdir/secret.txt",
        b"/graphs/batch/..%252Fsecretdir/secret.txt",
    )
    assert b"TOP-SECRET-CONTENT" not in body
    assert status == 400
