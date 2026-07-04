#!/usr/bin/env python3
"""
check-disk-space.py
===================

Reports free disk space on the root filesystem and warns if below threshold.
Used by auto-wake.py to detect when the vault or session DB is running out of room.

No LLM. Pure stdlib.

Exit codes:
    0 — OK (>= 10 GB free)
    1 — WARN (< 10 GB free)
    2 — CRITICAL (< 5 GB free)
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

WARN_GB = 10
CRITICAL_GB = 5


def main() -> int:
    target = Path("/")
    try:
        usage = shutil.disk_usage(target)
    except OSError as exc:
        print(f"disk_usage error: {exc}", file=sys.stderr)
        return 1

    free_gb = usage.free / (1024 ** 3)
    used_pct = (usage.used / usage.total) * 100

    print(f"path:    {target}")
    print(f"total:   {usage.total / (1024**3):.1f} GB")
    print(f"used:    {usage.used / (1024**3):.1f} GB ({used_pct:.1f}%)")
    print(f"free:    {free_gb:.1f} GB")

    if free_gb < CRITICAL_GB:
        print(f"🚨 CRITICAL: less than {CRITICAL_GB} GB free", file=sys.stderr)
        return 2
    if free_gb < WARN_GB:
        print(f"⚠️ WARN: less than {WARN_GB} GB free", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())