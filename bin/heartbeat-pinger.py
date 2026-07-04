#!/usr/bin/env python3
"""
heartbeat-pinger.py
===================

Simple proof-of-life ticker. Runs every 60 seconds via cron.
Touches ~/.hermes/.heartbeat and updates its mtime to "now".

The auto-wake watcher reads this file's mtime to decide if Hermes
is alive (fresh heartbeat) or zombie (stale heartbeat).

NO LLM. NO state. NO side effects beyond touching one file.

Usage:
    python3 heartbeat-pinger.py

Cron (every minute):
    * * * * * /usr/bin/python3 /root/.hermes/bin/heartbeat-pinger.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HEARTBEAT_FILE = Path.home() / ".hermes" / ".heartbeat"
LOG_FILE = Path.home() / ".hermes" / "logs" / "heartbeat.log"


def main() -> int:
    try:
        HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        # Touch file + update mtime to now
        HEARTBEAT_FILE.touch(exist_ok=True)
        os.utime(HEARTBEAT_FILE, (now, now))

        # Optional log line (debug only, not noisy)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} heartbeat OK\n")

        return 0
    except OSError as exc:
        # Don't spam stderr — the watcher will detect zombie and alert
        sys.stderr.write(f"[heartbeat-pinger] {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())