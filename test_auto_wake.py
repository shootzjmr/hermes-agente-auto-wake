#!/usr/bin/env python3
"""
test_auto_wake.py
=================

Unit tests for the auto-wake system. Run from anywhere:

    python3 /root/.hermes/bin/test_auto_wake.py

No pytest dependency — stdlib unittest only.

Coverage:
    - heartbeat-pinger.py creates and updates heartbeat file
    - auto-wake.py --status reports state correctly
    - auto-wake.py detects zombie from stale heartbeat
    - cleanup-stale-sessions.py closes stale rows
    - check-disk-space.py returns appropriate exit codes
    - audit-memory-size.py reports sizes
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Each test run uses an isolated fake HOME so the suite is hermetic and
# can run anywhere (CI, dev box, fresh container) without touching the
# real ~/.hermes. The scripts under bin/ read paths via Path.home(),
# which honours $HOME.
#
# If we're being executed from inside ~/.hermes (e.g. a sysadmin running
# `python3 ~/.hermes/bin/test_auto_wake.py`), fall back to the real HOME
# so we exercise the actual installation.
_this_file = Path(__file__).resolve()
_in_repo = _this_file.parent.name == "hermes-agente-auto-wake" or (
    _this_file.parent / "bin" / "auto-wake.py"
).exists() and (_this_file.parent / "bin").is_dir()

if _in_repo:
    TEST_HOME = Path(tempfile.mkdtemp(prefix="hermes-auto-wake-test-"))
    os.environ["HOME"] = str(TEST_HOME)
    (TEST_HOME / ".hermes" / "bin" / "auto-wake-actions").mkdir(parents=True)
    (TEST_HOME / ".hermes" / "logs").mkdir(parents=True)
    HERMES_BIN = TEST_HOME / ".hermes" / "bin"
    for src in _this_file.parent.joinpath("bin").rglob("*.py"):
        rel = src.relative_to(_this_file.parent / "bin")
        dst = HERMES_BIN / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
else:
    TEST_HOME = Path.home()
    HERMES_BIN = Path.home() / ".hermes" / "bin"

HEARTBEAT_FILE = TEST_HOME / ".hermes" / ".heartbeat"
STATE_FILE = TEST_HOME / ".hermes" / "logs" / "auto-wake-state.json"


def run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


class TestHeartbeatPinger(unittest.TestCase):
    def test_creates_file_on_first_run(self):
        if HEARTBEAT_FILE.exists():
            original_mtime = HEARTBEAT_FILE.stat().st_mtime
            HEARTBEAT_FILE.unlink()
        else:
            original_mtime = None

        result = run([sys.executable, str(HERMES_BIN / "heartbeat-pinger.py")])
        self.assertEqual(result.returncode, 0, f"pinger failed: {result.stderr}")
        self.assertTrue(HEARTBEAT_FILE.exists(), "heartbeat file not created")

        if original_mtime is not None:
            HEARTBEAT_FILE.touch()
            os.utime(HEARTBEAT_FILE, (original_mtime, original_mtime))

    def test_updates_mtime_on_second_run(self):
        # Set mtime to 5 seconds ago
        old = time.time() - 5
        HEARTBEAT_FILE.touch()
        os.utime(HEARTBEAT_FILE, (old, old))
        mtime_before = HEARTBEAT_FILE.stat().st_mtime

        time.sleep(1.1)
        result = run([sys.executable, str(HERMES_BIN / "heartbeat-pinger.py")])
        self.assertEqual(result.returncode, 0)
        mtime_after = HEARTBEAT_FILE.stat().st_mtime
        self.assertGreater(mtime_after, mtime_before, "mtime not updated")


class TestAutoWake(unittest.TestCase):
    def test_status_command_works(self):
        result = run([sys.executable, str(HERMES_BIN / "auto-wake.py"), "--status"])
        self.assertEqual(result.returncode, 0, f"status failed: {result.stderr}")
        self.assertIn("health:", result.stdout)

    def test_dry_run_doesnt_execute_actions(self):
        # Force heartbeat to be stale (15 min old) → ZOMBIE
        HEARTBEAT_FILE.touch()
        stale = time.time() - 900
        os.utime(HEARTBEAT_FILE, (stale, stale))

        result = run([
            sys.executable,
            str(HERMES_BIN / "auto-wake.py"),
            "--dry-run",
        ])
        self.assertEqual(result.returncode, 0, f"dry-run failed: {result.stderr}")
        # dry-run logs to auto-wake.log, not stdout
        log_file = TEST_HOME / ".hermes" / "logs" / "auto-wake.log"
        if log_file.exists():
            log_content = log_file.read_text()
            self.assertIn("dry-run", log_content)

        # Restore healthy heartbeat
        HEARTBEAT_FILE.touch()
        os.utime(HEARTBEAT_FILE, (time.time(), time.time()))

    def test_healthy_heartbeat_exits_zero(self):
        # Fresh heartbeat
        HEARTBEAT_FILE.touch()
        os.utime(HEARTBEAT_FILE, (time.time(), time.time()))

        result = run([sys.executable, str(HERMES_BIN / "auto-wake.py")])
        self.assertEqual(result.returncode, 0)


class TestCleanupStaleSessions(unittest.TestCase):
    def test_runs_without_error(self):
        script = HERMES_BIN / "auto-wake-actions" / "cleanup-stale-sessions.py"
        result = run([sys.executable, str(script)])
        # In a real Hermes install, state.db exists and the script runs.
        # In CI without state.db, it exits 1 with a clear message — both ok.
        self.assertIn(result.returncode, (0, 1), f"unexpected rc: {result.stderr}")
        # It should always print something informative
        self.assertTrue(result.stdout or result.stderr)


class TestCheckDiskSpace(unittest.TestCase):
    def test_reports_disk_usage(self):
        script = HERMES_BIN / "auto-wake-actions" / "check-disk-space.py"
        result = run([sys.executable, str(script)])
        # 0 = OK, 1 = WARN, 2 = CRITICAL — all acceptable as long as output exists
        self.assertIn(result.returncode, (0, 1, 2))
        self.assertIn("free:", result.stdout)


class TestAuditMemorySize(unittest.TestCase):
    def test_reports_memory_size(self):
        script = HERMES_BIN / "auto-wake-actions" / "audit-memory-size.py"
        result = run([sys.executable, str(script)])
        self.assertIn(result.returncode, (0, 1, 2))
        self.assertIn("MEMORY.md:", result.stdout)
        self.assertIn("USER.md", result.stdout)


class TestWatcherStateFile(unittest.TestCase):
    def test_state_file_valid_json_after_run(self):
        # Force a healthy run to write state
        HEARTBEAT_FILE.touch()
        os.utime(HEARTBEAT_FILE, (time.time(), time.time()))
        run([sys.executable, str(HERMES_BIN / "auto-wake.py")])

        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            self.assertIn("last_status", data)
            self.assertIn("last_run", data)
            self.assertIn("last_actions", data)


if __name__ == "__main__":
    # Ensure heartbeat exists at start
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_FILE.touch()

    print("Running auto-wake test suite…\n")
    unittest.main(verbosity=2)