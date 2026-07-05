#!/usr/bin/env python3
"""Fast regressions for issue-fix contracts that do not require Stata."""

from __future__ import annotations

import inspect
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import stata_mcp_server as server
import stata_worker
import session_manager
from output_filter import apply_compact_mode_filter


def test_windows_port_lookup_does_not_exclude_ipv6_listeners():
    with open(server.__file__, "r", encoding="utf-8") as f:
        source = f.read()
    # "-p tcp" on Windows netstat means IPv4 TCP only and would miss IPv6
    # listeners; the parser itself keeps only TCP rows.
    assert '"netstat -ano"' in source
    assert "netstat -ano -p tcp" not in source


def test_compact_filter_strips_mcp_log_header_from_selection_output():
    output = (
        "-------------------------------------------------------------------\n"
        "      name:  __mcp_log\n"
        "       log:  /var/folders/9p/T/stata_run_default\n"
        "> _7505d64a54_74609fe5bb_1783282613268.log\n"
        "  log type:  text\n"
        " opened on:   5 Jul 2026, 16:16:53\n"
        "\n"
        ". display 2+3\n"
        "5\n"
        "\n"
        ". capture log close __mcp_log\n"
    )

    filtered = apply_compact_mode_filter(output, filter_command_echo=False)

    assert "__mcp_log" not in filtered
    assert "opened on" not in filtered
    assert "log type" not in filtered
    assert "stata_run_default" not in filtered
    assert "_7505d64a54" not in filtered  # wrapped header path fragment
    assert ". display 2+3" in filtered  # user command echo is preserved
    assert "5" in filtered


@pytest.mark.asyncio
async def test_run_file_endpoint_cleans_up_processed_temp_file(monkeypatch, tmp_path):
    do_file = tmp_path / "analysis.do"
    do_file.write_text('display "hello"\n', encoding="utf-8")
    processed_file = tmp_path / "processed.do"
    processed_file.write_text('display "hello"\n', encoding="utf-8")

    class FakeSessionManager:
        def execute_file(self, file_path, **kwargs):
            return {"status": "success", "output": "ok", "extra": {"graphs": []}}

    monkeypatch.setattr(server, "multi_session_enabled", True)
    monkeypatch.setattr(server, "session_manager", FakeSessionManager())
    monkeypatch.setattr(server, "preprocess_do_file_for_graphs", lambda file_path: str(processed_file))
    monkeypatch.setattr(
        server,
        "get_log_file_path",
        lambda file_path, base_name, session_id=None: str(tmp_path / "analysis_mcp.log"),
    )

    response = await server.stata_run_file_endpoint(str(do_file), timeout=5)

    assert response.status_code == 200
    assert not processed_file.exists()


def test_windows_netstat_parser_matches_exact_local_port_without_localized_state():
    output = """
  TCP    127.0.0.1:4000       0.0.0.0:0          ABHOREN        1234
  TCP    127.0.0.1:4000       127.0.0.1:60000    VERBUNDEN      5555
  TCP    127.0.0.1:40000      0.0.0.0:0          ABHOREN        9999
  TCP    127.0.0.1:3000       127.0.0.1:4000     ABHOREN        8888
  TCP    [::]:4000            [::]:0             ABHOREN        1234
  UDP    0.0.0.0:4000         *:*                               7777
"""

    assert server.windows_listening_port_pids_from_netstat(output, 4000) == ["1234"]


def test_stream_fallback_strips_log_footer_and_filters_selection_markers():
    output = """
header ignored
__STATA_MCP_OUTPUT_START__
displayed result
__STATA_MCP_OUTPUT_END__

Log file saved to: /tmp/stata_selection_abc_mcp.log
"""

    assert server.stream_fallback_lines(output, selection_markers=True) == ["displayed result"]


def test_data_viewer_max_rows_is_clamped_in_server_and_worker():
    assert server.normalize_data_viewer_max_rows(0) == server.MIN_DATA_VIEWER_ROWS
    assert server.normalize_data_viewer_max_rows("not-a-number") == 10000
    assert server.normalize_data_viewer_max_rows(999999999) == server.MAX_DATA_VIEWER_ROWS

    assert stata_worker.normalize_data_viewer_max_rows(0) == stata_worker.MIN_DATA_VIEWER_ROWS
    assert stata_worker.normalize_data_viewer_max_rows(999999999) == stata_worker.MAX_DATA_VIEWER_ROWS


def test_mcp_log_is_reopened_after_user_log_close_all():
    code = 'display "before"\ncapture log close _all\ndisplay "after"\n'
    protected = server.protect_mcp_log_from_close_all(code, "/tmp/mcp.log")
    lines = protected.splitlines()

    close_index = lines.index("capture log close _all")
    assert lines[close_index + 1] == f"capture log close {server.MCP_LOG_NAME}"
    assert lines[close_index + 2] == f'log using "/tmp/mcp.log", append text name({server.MCP_LOG_NAME})'
    assert 'display "after"' in protected

    worker_protected = stata_worker.protect_mcp_log_from_close_all(code, "/tmp/mcp.log")
    assert f'log using "/tmp/mcp.log", append text name({stata_worker.MCP_LOG_NAME})' in worker_protected


def test_session_id_log_suffix_cannot_escape_log_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "log_file_location", "custom")
    monkeypatch.setattr(server, "custom_log_directory", str(tmp_path))

    log_path = server.get_log_file_path(
        "/tmp/source/analysis.do",
        "analysis",
        "../nested/session",
    )

    assert os.path.dirname(log_path) == str(tmp_path)
    assert os.path.basename(log_path).startswith("analysis_nested_session_")
    assert os.path.basename(log_path).endswith("_mcp.log")
    assert server.log_session_suffix("a/b") != server.log_session_suffix("a_b")
    assert session_manager.safe_log_session_suffix("../nested/session").startswith("_nested_session_")
    assert session_manager.safe_log_session_suffix("a/b") != session_manager.safe_log_session_suffix("a_b")


def test_custom_log_directory_must_be_directory(monkeypatch, tmp_path):
    custom_file = tmp_path / "not_a_directory"
    custom_file.write_text("not a dir", encoding="utf-8")
    do_file = tmp_path / "analysis.do"
    do_file.write_text('display "hello"\n', encoding="utf-8")

    monkeypatch.setattr(server, "log_file_location", "custom")
    monkeypatch.setattr(server, "custom_log_directory", str(custom_file))

    log_path = server.get_log_file_path(str(do_file), "analysis")

    assert os.path.dirname(log_path) == str(tmp_path)
    assert os.path.basename(log_path) == "analysis_mcp.log"


def test_worker_file_tokens_are_safe_and_collision_resistant():
    assert "/" not in stata_worker.safe_file_token("../nested/session")
    assert "\\" not in stata_worker.safe_file_token(r"..\\nested\\session")
    assert stata_worker.safe_file_token("a/b") != stata_worker.safe_file_token("a_b")
    with open(stata_worker.__file__, "r", encoding="utf-8") as f:
        worker_source = f.read()
    with open(session_manager.__file__, "r", encoding="utf-8") as f:
        manager_source = f.read()
    assert 'tempfile.mkdtemp(prefix=f"stata_worker_{safe_worker_id}_")' in worker_source
    assert "worker_process_id = safe_log_session_suffix(session_id).lstrip" in manager_source


def test_start_server_forwards_custom_log_location_options():
    start_server_path = os.path.join(os.path.dirname(__file__), "..", "src", "start-server.js")
    with open(start_server_path, "r", encoding="utf-8") as f:
        source = f.read()

    assert "--log-file-location ${options.logFileLocation}" in source
    assert "--custom-log-directory \"${stripTrailingBackslash(options.customLogDirectory)}\"" in source
    assert "args.push('--log-file-location')" in source
    assert "args.push('--custom-log-directory')" in source
    assert "function stripTrailingBackslash" in source
    assert "].join(' | ')" in source
    assert "replace(/(?<!^[A-Za-z]:)\\\\+$/, '')" in source


def test_extension_uses_pipeline_port_lookup_and_raw_data_viewer_value():
    extension_path = os.path.join(os.path.dirname(__file__), "..", "src", "extension.js")
    with open(extension_path, "r", encoding="utf-8") as f:
        source = f.read()

    assert "].join(' | ')" in source
    assert "normalizeDataViewerMaxRows(config.get('dataViewerMaxRows'))" in source
    assert "replace(/(?<!^[A-Za-z]:)\\\\+$/, '')" in source


def test_normal_execution_wrappers_use_named_mcp_log_not_close_all():
    checked_sources = [
        inspect.getsource(server.run_stata_command),
        inspect.getsource(server.run_stata_file),
        inspect.getsource(stata_worker.worker_process),
    ]

    for source in checked_sources:
        assert "capture log close _all" not in source
        assert "mcp_log_using_command" in source or "name({MCP_LOG_NAME})" in source
        assert "capture log close {MCP_LOG_NAME}" in source


def test_mcp_native_progress_uses_session_specific_log_path():
    with open(server.__file__, "r", encoding="utf-8") as f:
        source = f.read()
    assert 'get_log_file_path(effective_path, base_name, arguments_dict.get("session_id"))' in source


@pytest.mark.asyncio
async def test_single_session_selection_timeout_returns_error(monkeypatch):
    def slow_selection(*args, **kwargs):
        time.sleep(0.2)
        return "too late"

    monkeypatch.setattr(server, "run_stata_selection", slow_selection)

    result = await server.run_stata_selection_with_timeout("sleep", timeout=0.01)

    assert "timed out" in result


@pytest.mark.asyncio
async def test_file_stream_passes_monitored_log_to_single_session_runner(monkeypatch, tmp_path):
    do_file = tmp_path / "analysis.do"
    do_file.write_text('display "hello"\n', encoding="utf-8")
    monitored_log = tmp_path / "analysis_mcp.log"
    captured = {}

    monkeypatch.setattr(server, "multi_session_enabled", False)
    monkeypatch.setattr(server, "session_manager", None)
    monkeypatch.setattr(
        server,
        "get_log_file_path",
        lambda file_path, base_name, session_id=None: str(monitored_log),
    )

    def fake_run_stata_file(file_path, **kwargs):
        captured["file_path"] = file_path
        captured.update(kwargs)
        return "Final output\n\nLog file saved to: /tmp/temp_mcp.log", []

    monkeypatch.setattr(server, "run_stata_file", fake_run_stata_file)

    chunks = []
    async for chunk in server.stata_run_file_stream(
        str(do_file),
        timeout=5,
        working_dir=server.NO_WORKING_DIR_SENTINEL,
        execution_id="test-exec",
    ):
        chunks.append(chunk)

    assert captured["file_path"] == str(do_file)
    assert captured["log_file"] == str(monitored_log)
    assert captured["working_dir"] == server.NO_WORKING_DIR_SENTINEL

    joined = "".join(chunks)
    assert "data: Final output" in joined
    assert "temp_mcp.log" not in joined
    assert "*** Execution completed ***" in joined


@pytest.mark.asyncio
async def test_file_stream_preserves_no_cd_sentinel_for_multi_session_worker(monkeypatch, tmp_path):
    do_file = tmp_path / "analysis.do"
    do_file.write_text('display "hello"\n', encoding="utf-8")
    processed_file = tmp_path / "processed.do"
    processed_file.write_text('display "hello"\n', encoding="utf-8")
    monitored_log = tmp_path / "analysis_s1_mcp.log"
    captured = {}

    class FakeSessionManager:
        def execute_file(self, file_path, **kwargs):
            captured["file_path"] = file_path
            captured.update(kwargs)
            return {
                "status": "success",
                "output": "Worker final\n\nLog file saved to: /tmp/processed_mcp.log",
                "extra": {"graphs": []},
            }

    monkeypatch.setattr(server, "multi_session_enabled", True)
    monkeypatch.setattr(server, "session_manager", FakeSessionManager())
    monkeypatch.setattr(server, "preprocess_do_file_for_graphs", lambda file_path: str(processed_file))
    monkeypatch.setattr(
        server,
        "get_log_file_path",
        lambda file_path, base_name, session_id=None: str(monitored_log),
    )

    chunks = []
    async for chunk in server.stata_run_file_stream(
        str(do_file),
        timeout=5,
        working_dir=server.NO_WORKING_DIR_SENTINEL,
        session_id="s1",
        execution_id="test-exec",
    ):
        chunks.append(chunk)

    assert captured["file_path"] == str(processed_file)
    assert captured["log_file"] == str(monitored_log)
    assert captured["working_dir"] == server.NO_WORKING_DIR_SENTINEL
    assert captured["session_id"] == "s1"
    assert not processed_file.exists()

    joined = "".join(chunks)
    assert "data: Worker final" in joined
    assert "processed_mcp.log" not in joined
