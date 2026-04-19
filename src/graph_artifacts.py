#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers for temporary graph artifact storage and routing."""

import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_GRAPH_BATCH_KEEP_COUNT = 2
DEFAULT_GRAPH_STORAGE_ENV = "STATA_MCP_GRAPHS_DIR"
MANIFEST_FILENAME = "manifest.json"


def normalize_graph_path(file_path: str) -> str:
    return file_path.replace("\\", "/")


def get_graphs_root(configured_root: Optional[str] = None, extension_path: Optional[str] = None) -> str:
    root = configured_root or os.environ.get(DEFAULT_GRAPH_STORAGE_ENV)
    if root:
        return os.path.abspath(root)
    if extension_path:
        return os.path.join(os.path.abspath(extension_path), "graphs")
    return os.path.join(tempfile.gettempdir(), "stata_mcp_graphs")


def ensure_graphs_root(graphs_root: str) -> str:
    os.makedirs(graphs_root, exist_ok=True)
    return os.path.abspath(graphs_root)


def generate_execution_id(prefix: str = "exec") -> str:
    return f"{prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"


def create_batch_context(
    graphs_root: str,
    execution_id: Optional[str] = None,
    source: str = "execution"
) -> Dict[str, Any]:
    resolved_root = ensure_graphs_root(graphs_root)
    execution_id = execution_id or generate_execution_id()
    batch_id = execution_id
    batch_dir = os.path.join(resolved_root, batch_id)
    os.makedirs(batch_dir, exist_ok=True)
    return {
        "execution_id": execution_id,
        "batch_id": batch_id,
        "batch_dir": batch_dir,
        "graphs_root": resolved_root,
        "source": source,
        "created_at": int(time.time() * 1000)
    }


def build_graph_record(
    batch_context: Dict[str, Any],
    logical_name: str,
    file_path: str,
    order_in_batch: int,
    graph_format: str = "png"
) -> Dict[str, Any]:
    filename = os.path.basename(file_path)
    artifact_id = f"{batch_context['batch_id']}-{uuid.uuid4().hex[:8]}"
    normalized_path = normalize_graph_path(file_path)
    return {
        "artifactId": artifact_id,
        "executionId": batch_context["execution_id"],
        "batchId": batch_context["batch_id"],
        "name": logical_name,
        "logicalName": logical_name,
        "displayName": logical_name,
        "path": normalized_path,
        "filename": filename,
        "format": graph_format,
        "orderInBatch": order_in_batch,
        "browserPath": f"/graphs/batch/{batch_context['batch_id']}/{filename}"
    }


def write_batch_manifest(batch_context: Dict[str, Any], graphs: List[Dict[str, Any]]) -> str:
    manifest = {
        "executionId": batch_context["execution_id"],
        "batchId": batch_context["batch_id"],
        "source": batch_context.get("source", "execution"),
        "createdAt": batch_context["created_at"],
        "graphs": graphs
    }
    manifest_path = os.path.join(batch_context["batch_dir"], MANIFEST_FILENAME)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=True, indent=2)
    return manifest_path


def load_batch_manifest(batch_dir: str) -> Optional[Dict[str, Any]]:
    manifest_path = os.path.join(batch_dir, MANIFEST_FILENAME)
    if not os.path.exists(manifest_path):
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logging.warning(f"Failed to read graph manifest {manifest_path}: {exc}")
        return None


def list_batch_dirs(graphs_root: str) -> List[str]:
    if not graphs_root or not os.path.isdir(graphs_root):
        return []

    batch_dirs = []
    for entry in os.scandir(graphs_root):
        if entry.is_dir():
            batch_dirs.append(entry.path)
    batch_dirs.sort(key=lambda item: os.path.getmtime(item), reverse=True)
    return batch_dirs


def cleanup_graph_batches(
    graphs_root: str,
    keep_batch_ids: Optional[Iterable[str]] = None,
    keep_latest: int = DEFAULT_GRAPH_BATCH_KEEP_COUNT
) -> List[str]:
    keep_ids = {batch_id for batch_id in (keep_batch_ids or []) if batch_id}
    removed = []

    for index, batch_dir in enumerate(list_batch_dirs(graphs_root)):
        batch_id = os.path.basename(batch_dir)
        if batch_id in keep_ids or index < keep_latest:
            continue
        try:
            shutil.rmtree(batch_dir, ignore_errors=False)
            removed.append(batch_id)
        except Exception as exc:
            logging.warning(f"Failed to remove stale graph batch {batch_dir}: {exc}")

    return removed


def resolve_batch_graph_path(graphs_root: str, batch_id: str, filename: str) -> Optional[str]:
    if not batch_id or not filename:
        return None
    batch_dir = os.path.join(graphs_root, batch_id)
    file_path = os.path.realpath(os.path.join(batch_dir, filename))
    real_batch_dir = os.path.realpath(batch_dir)
    try:
        common_path = os.path.commonpath([real_batch_dir, file_path])
    except ValueError:
        return None

    if os.path.normcase(common_path) != os.path.normcase(real_batch_dir):
        return None
    if os.path.normcase(file_path) == os.path.normcase(real_batch_dir):
        return None
    return file_path


def find_latest_graph_by_name(graphs_root: str, graph_name: str) -> Optional[Dict[str, Any]]:
    normalized_graph_name = graph_name[:-4] if graph_name.endswith(".png") else graph_name

    for batch_dir in list_batch_dirs(graphs_root):
        manifest = load_batch_manifest(batch_dir)
        if not manifest:
            continue
        for graph in manifest.get("graphs", []):
            logical_name = graph.get("logicalName") or graph.get("name")
            if logical_name == normalized_graph_name:
                resolved_path = resolve_batch_graph_path(
                    graphs_root,
                    manifest.get("batchId", ""),
                    graph.get("filename", "")
                )
                if resolved_path and os.path.exists(resolved_path):
                    return {
                        "path": resolved_path,
                        "graph": graph,
                        "manifest": manifest
                    }

    return None
