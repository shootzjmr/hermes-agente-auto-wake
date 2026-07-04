#!/usr/bin/env python3
"""
restart-hermes-daemon.py
========================

Restarts the hermes-gateway systemd service. Used by auto-wake.py when
Hermes has been zombie/deep_zombie for multiple consecutive ticks (i.e.
the pinger can't recover on its own).

The script checks `systemctl is-active` first to avoid restart loops
if the daemon is healthy.

Exit codes:
    0 — service restarted successfully (or was already active and ok)
    1 — systemctl not available or not running as root
    2 — restart failed (service still down after 10s)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

SERVICE_NAME = "hermes-gateway"
GRACE_SECONDS = 10


def run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def main() -> int:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        print("systemctl not found", file=sys.stderr)
        return 1

    # Check current state
    state = run([systemctl, "is-active", SERVICE_NAME])
    state_str = state.stdout.strip() or "unknown"

    print(f"service: {SERVICE_NAME}")
    print(f"state:   {state_str}")

    if state_str == "active":
        print("already active, no restart needed")
        return 0

    # Restart
    print(f"restarting {SERVICE_NAME}...")
    result = run([systemctl, "restart", SERVICE_NAME])
    if result.returncode != 0:
        print(f"systemctl restart failed: {result.stderr}", file=sys.stderr)
        return 2

    # Wait for service to come up
    deadline = time.time() + GRACE_SECONDS
    while time.time() < deadline:
        check = run([systemctl, "is-active", SERVICE_NAME])
        if check.stdout.strip() == "active":
            uptime = run([systemctl, "show", SERVICE_NAME, "--property=ActiveEnterTimestamp", "--value"])
            print(f"✅ {SERVICE_NAME} active again (entered: {uptime.stdout.strip()})")
            return 0
        time.sleep(1)

    # Timed out
    final = run([systemctl, "is-active", SERVICE_NAME])
    print(f"❌ {SERVICE_NAME} did not become active within {GRACE_SECONDS}s (state: {final.stdout.strip()})", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())