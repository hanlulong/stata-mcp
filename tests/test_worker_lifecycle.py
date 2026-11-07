#!/usr/bin/env python3
"""
Regression tests for Issue #69: worker processes orphaned on window close/reload.

These tests do not need a Stata installation. The end-to-end test runs the real
worker_process() against a stub ``pystata`` package so the worker reaches its
command loop, then kills the parent with SIGKILL (as the port-reclaim code does)
and checks that the worker and its resource_tracker exit on their own.
"""

from __future__ import annotations

import asyncio
import json
import os
import selectors
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import stata_worker  # noqa: E402
from session_manager import SessionManager  # noqa: E402

# Parent process used by the end-to-end test. It plays the role of
# stata_mcp_server.py: spawn one worker, wait for it to be ready, report PIDs,
# then idle until it gets killed.
FAKE_SERVER = textwrap.dedent(
    """
    import json
    import multiprocessing
    import sys
    import time

    src_dir, fake_stata, graphs_dir = sys.argv[1:4]
    sys.path.insert(0, src_dir)
    import stata_worker

    if __name__ == "__main__":
        multiprocessing.set_start_method("spawn", force=True)
        command_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        stop_event = multiprocessing.Event()
        worker = multiprocessing.Process(
            target=stata_worker.worker_process,
            args=("orphan-test", command_queue, result_queue, fake_stata, "mp", 30,
                  stop_event, graphs_dir),
        )
        worker.start()
        init = result_queue.get(timeout=60)
        from multiprocessing import resource_tracker
        tracker_pid = getattr(resource_tracker._resource_tracker, "_pid", None)
        print(json.dumps({"status": init.get("status"), "error": init.get("error"),
                          "worker_pid": worker.pid, "tracker_pid": tracker_pid}),
              flush=True)
        time.sleep(600)
    """
)


def _make_fake_stata(root: Path) -> Path:
    """Create a stub Stata tree whose utilities/pystata satisfies initialize_stata()."""
    pkg = root / "utilities" / "pystata"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "config.py").write_text("stlib = None\n\ndef init(edition):\n    pass\n")
    (pkg / "stata.py").write_text("def run(cmd, quietly=False, **kwargs):\n    pass\n")
    return root


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_exit(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.2)
    return not _pid_alive(pid)


def _read_line(stream, timeout: float) -> str:
    sel = selectors.DefaultSelector()
    sel.register(stream, selectors.EVENT_READ)
    try:
        if not sel.select(timeout):
            return ""
        return stream.readline()
    finally:
        sel.close()


def test_parent_process_alive_without_multiprocessing_parent():
    # The pytest process has no multiprocessing parent, so there is nothing to
    # watch and the probe must not report the parent as gone.
    assert stata_worker.parent_process_alive() is True


def test_parent_process_alive_ignores_probe_errors(monkeypatch):
    def broken():
        raise OSError("probe failed")

    monkeypatch.setattr(stata_worker.multiprocessing, "parent_process", broken)
    assert stata_worker.parent_process_alive() is True


def test_session_manager_stop_does_not_wait_for_cleanup_interval():
    manager = SessionManager(stata_path="/nonexistent", enabled=True)
    manager._check_sessions = lambda: None
    manager._cleanup_thread = threading.Thread(target=manager._cleanup_loop, daemon=True)
    manager._cleanup_thread.start()
    time.sleep(0.2)  # let the loop reach its 60 s wait

    start = time.monotonic()
    manager.stop()
    elapsed = time.monotonic() - start

    assert not manager._cleanup_thread.is_alive()
    assert elapsed < 2.0


def test_lifespan_shutdown_stops_worker_sessions(monkeypatch):
    import stata_mcp_server as server

    class FakeSessionManager:
        stopped = False

        def stop(self):
            self.stopped = True

    fake = FakeSessionManager()
    monkeypatch.setattr(server, "session_manager", fake)

    async def run_lifespan():
        async with server.lifespan(server.app):
            pass

    asyncio.run(run_lifespan())
    assert fake.stopped


@pytest.mark.skipif(sys.platform == "win32", reason="uses POSIX signals to probe PIDs")
def test_worker_exits_when_server_process_is_killed(tmp_path):
    fake_stata = _make_fake_stata(tmp_path / "fake_stata")
    graphs_dir = tmp_path / "graphs"
    script = tmp_path / "fake_server.py"
    script.write_text(FAKE_SERVER)
    env = dict(os.environ, TMPDIR=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")

    server = subprocess.Popen(
        [sys.executable, str(script), str(SRC_DIR), str(fake_stata), str(graphs_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=env,
    )
    worker_pid = tracker_pid = None
    try:
        line = _read_line(server.stdout, timeout=90)
        assert line, "fake server did not report a ready worker"
        info = json.loads(line)
        assert info["status"] == "ready", info.get("error")
        worker_pid = info["worker_pid"]
        tracker_pid = info["tracker_pid"]

        # While the server is alive, an idle worker must keep running.
        time.sleep(2.5)
        assert _pid_alive(worker_pid)

        # SIGKILL skips every shutdown handler in the server, like the
        # port-reclaim path in kill_process_on_port().
        server.kill()
        server.wait(timeout=10)

        assert _wait_for_exit(worker_pid, timeout=15), "worker outlived its server"
        if tracker_pid:
            assert _wait_for_exit(tracker_pid, timeout=15), "resource_tracker outlived the worker"
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=10)
        for pid in (worker_pid, tracker_pid):
            if pid and _pid_alive(pid):
                os.kill(pid, signal.SIGKILL)
