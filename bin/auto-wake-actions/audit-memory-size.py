#!/usr/bin/env python3
"""
audit-memory-size.py
====================

Reports size of MEMORY.md and USER.md and warns if either approaches
the char_limit set in config.yaml. Suggests rotation if needed.

No LLM. Pure stdlib.

Exit codes:
    0 — OK (both well below limits)
    1 — WARN (one or both within 20% of limit)
    2 — CRITICAL (one or both over limit)
"""

from __future__ import annotations

from pathlib import Path

MEMORY_FILE = Path.home() / ".hermes" / "memories" / "MEMORY.md"
USER_FILE = Path.home() / ".hermes" / "memories" / "USER.md"

# Approximate limits (chars) — read from config in future, hardcoded for now
MEMORY_LIMIT = 10_000
USER_LIMIT = 8_000


def check_file(path: Path, limit: int, label: str) -> tuple[int, int]:
    if not path.exists():
        print(f"{label}: MISSING ({path})")
        return 0, 0
    content = path.read_text()
    size = len(content)
    pct = (size / limit) * 100 if limit else 0
    status = "OK"
    if size > limit:
        status = "OVER"
    elif pct > 80:
        status = "WARN"
    print(f"{label}: {size} chars ({pct:.0f}% of {limit}) — {status}")
    return size, limit


def main() -> int:
    print(f"memory audit @ {MEMORY_FILE.parent}")
    mem_size, mem_limit = check_file(MEMORY_FILE, MEMORY_LIMIT, "MEMORY.md")
    user_size, user_limit = check_file(USER_FILE, USER_LIMIT, "USER.md  ")

    rc = 0
    if mem_size > mem_limit or user_size > user_limit:
        rc = 2
    elif (mem_size / mem_limit > 0.8) or (user_size / user_limit > 0.8):
        rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())