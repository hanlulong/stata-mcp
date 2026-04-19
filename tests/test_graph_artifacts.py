#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for temporary graph artifact helpers."""

import os
import time

from graph_artifacts import (
    build_graph_record,
    cleanup_graph_batches,
    create_batch_context,
    find_latest_graph_by_name,
    get_graphs_root,
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
