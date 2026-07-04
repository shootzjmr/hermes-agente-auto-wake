#!/usr/bin/env python3
"""
send-telegram.py
================

Thin wrapper around `hermes send --to telegram` so cron/auto-wake actions
can pipe alerts without knowing about the hermes CLI shape.

Usage:
    python3 send-telegram.py "your message"
    echo "msg" | python3 send-telegram.py

Exit codes:
    0 — sent successfully
    1 — message empty
    2 — hermes send failed
    3 — hermes binary not found
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERMES_BIN = shutil.which("hermes") or "/usr/local/bin/hermes"


def main() -> int:
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
    else:
        message = sys.stdin.read()

    message = message.strip()
    if not message:
        print("empty message, nothing to send", file=sys.stderr)
        return 1

    if not Path(HERMES_BIN).exists():
        print(f"hermes binary not found at {HERMES_BIN}", file=sys.stderr)
        return 3

    try:
        result = subprocess.run(
            [HERMES_BIN, "send", "--to", "telegram", message],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            # Forward hermes's confirmation line
            if result.stdout.strip():
                print(result.stdout.strip())
            return 0
        print(f"hermes send failed (rc={result.returncode}): {result.stderr.strip()}", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print("hermes send timed out after 30s", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"OS error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())