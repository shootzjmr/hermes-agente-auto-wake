#!/usr/bin/env python3
"""
cleanup-stale-sessions.py
=========================

Closes Hermes sessions that have been "active" for more than 48 hours
without an ended_at timestamp. These are zombie sessions that cause the
"re-answering old messages" bug.

Strategy: set ended_at = started_at + 1 hour (assume the session actually
ended an hour after it started). This is non-destructive — if the row
already had an ended_at, we leave it alone.

No LLM. Pure SQL via Python's sqlite3 module.

Exit codes:
    0 — success (or no-op)
    1 — database error
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path.home() / ".hermes" / "state.db"
STALE_HOURS = 48


def main() -> int:
    if not DB_PATH.exists():
        print(f"state.db not found at {DB_PATH}", file=sys.stderr)
        return 1

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Inspect first
        # NOTE: started_at is stored as a Unix timestamp (REAL), not an ISO string.
        # We compute the cutoff in Python to avoid datetime() arithmetic quirks.
        import time
        cutoff = time.time() - (STALE_HOURS * 3600)

        cur.execute(
            """
            SELECT COUNT(*) AS n
            FROM sessions
            WHERE ended_at IS NULL
              AND started_at < ?
            """,
            (cutoff,),
        )
        before = cur.fetchone()["n"]

        if before == 0:
            print(f"no stale sessions older than {STALE_HOURS}h")
            conn.close()
            return 0

        # Update: set ended_at to started_at + 1h if it's NULL.
        # Use float arithmetic since started_at is a Unix timestamp.
        cur.execute(
            """
            UPDATE sessions
            SET ended_at = started_at + 3600
            WHERE ended_at IS NULL
              AND started_at < ?
            """,
            (cutoff,),
        )
        conn.commit()
        closed = cur.rowcount

        # Confirm
        cur.execute(
            """
            SELECT id, started_at, ended_at
            FROM sessions
            WHERE ended_at = started_at + 3600
              AND started_at < ?
            ORDER BY started_at DESC
            LIMIT 5
            """,
            (cutoff,),
        )
        sample = cur.fetchall()

        conn.close()

        print(f"closed {closed} stale session(s) older than {STALE_HOURS}h")
        for row in sample:
            print(f"  - {row['id']} started {row['started_at']}")
        return 0
    except sqlite3.Error as exc:
        print(f"sqlite error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())