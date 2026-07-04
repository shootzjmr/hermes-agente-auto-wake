#!/usr/bin/env python3
"""
auto-wake.py
============

Watcher that detects when Hermes has gone zombie (heartbeat stale)
and triggers corrective actions. Runs every 5 minutes via cron.

Decision tree:
    delta < 600s (10min)   → HEALTHY, exit 0
    600s ≤ delta < 1800s   → ZOMBIE, run cleanup + audit actions
    1800s ≤ delta < 3600s  → DEEP_ZOMBIE, run actions + Telegram WARN
    delta ≥ 3600s          → DEAD, Telegram CRITICAL + disable self to avoid spam

Actions are simple scripts in ~/.hermes/bin/auto-wake-actions/ that
return exit 0 (ok) or non-zero (problem). Failed actions escalate to
Telegram via the notify_telegram() helper.

NO LLM in this script. All reasoning happens in the action scripts
(if they need it). This script is the scheduler.

Usage:
    python3 auto-wake.py                # normal run
    python3 auto-wake.py --dry-run      # log only, no actions
    python3 auto-wake.py --status       # print current state, exit

Cron (every 5 min):
    */5 * * * * /usr/bin/python3 /root/.hermes/bin/auto-wake.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

HEARTBEAT_FILE = Path.home() / ".hermes" / ".heartbeat"
STATE_FILE = Path.home() / ".hermes" / "logs" / "auto-wake-state.json"
LOG_FILE = Path.home() / ".hermes" / "logs" / "auto-wake.log"
ACTIONS_DIR = Path.home() / ".hermes" / "bin" / "auto-wake-actions"
TELEGRAM_BOT = Path.home() / ".hermes" / "bin" / "send-telegram.py"

# Thresholds (seconds)
HEALTHY_MAX = 600        # 10 min
DEEP_ZOMBIE_MIN = 1800   # 30 min
DEAD_MIN = 3600          # 60 min

# Don't re-run an action more than once per this many seconds (per state file)
ACTION_COOLDOWN = 1800   # 30 min


class Health(Enum):
    HEALTHY = "healthy"
    ZOMBIE = "zombie"
    DEEP_ZOMBIE = "deep_zombie"
    DEAD = "dead"
    UNKNOWN = "unknown"  # heartbeat file missing


@dataclass
class WatcherState:
    last_status: str = "unknown"
    last_run: float = 0.0
    last_actions: dict[str, float] | None = None  # action_name -> last run ts

    def to_dict(self) -> dict:
        return {
            "last_status": self.last_status,
            "last_run": self.last_run,
            "last_actions": self.last_actions or {},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WatcherState":
        return cls(
            last_status=data.get("last_status", "unknown"),
            last_run=float(data.get("last_run", 0.0)),
            last_actions=data.get("last_actions", {}) or {},
        )


def load_state() -> WatcherState:
    if not STATE_FILE.exists():
        return WatcherState()
    try:
        return WatcherState.from_dict(json.loads(STATE_FILE.read_text()))
    except (json.JSONDecodeError, OSError):
        return WatcherState()


def save_state(state: WatcherState) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state.to_dict(), indent=2))


def log(msg: str) -> None:
    """Append a timestamped line to the watcher log."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with LOG_FILE.open("a") as f:
        f.write(f"{ts} {msg}\n")


def detect_health() -> tuple[Health, float]:
    """Return (health, heartbeat_age_seconds)."""
    if not HEARTBEAT_FILE.exists():
        return Health.UNKNOWN, float("inf")
    age = time.time() - HEARTBEAT_FILE.stat().st_mtime
    if age < HEALTHY_MAX:
        return Health.HEALTHY, age
    if age < DEEP_ZOMBIE_MIN:
        return Health.ZOMBIE, age
    if age < DEAD_MIN:
        return Health.DEEP_ZOMBIE, age
    return Health.DEAD, age


def run_action(action_name: str, state: WatcherState) -> tuple[int, str]:
    """Run a single action script. Returns (exit_code, stdout+stderr)."""
    script = ACTIONS_DIR / f"{action_name}.py"
    if not script.exists():
        return 127, f"action script not found: {script}"

    # Cooldown: skip if we ran it recently
    last = state.last_actions.get(action_name, 0.0)
    if time.time() - last < ACTION_COOLDOWN:
        return 0, f"cooldown (last run {int(time.time() - last)}s ago)"

    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = (result.stdout + result.stderr).strip()
        state.last_actions[action_name] = time.time()
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return 124, "timeout after 60s"
    except OSError as exc:
        return 126, str(exc)


def notify_telegram(message: str) -> bool:
    """Send a message to the configured Telegram home channel."""
    if not TELEGRAM_BOT.exists():
        log(f"no telegram bot at {TELEGRAM_BOT}; skipping alert")
        return False
    try:
        subprocess.run(
            [sys.executable, str(TELEGRAM_BOT), message],
            timeout=30,
            check=False,
        )
        return True
    except (subprocess.TimeoutExpired, OSError) as exc:
        log(f"telegram notify failed: {exc}")
        return False


def actions_for_health(health: Health) -> list[str]:
    """Map health → list of action script basenames to run."""
    if health == Health.HEALTHY:
        return []
    if health == Health.ZOMBIE:
        return ["cleanup-stale-sessions", "check-disk-space"]
    if health == Health.DEEP_ZOMBIE:
        # Deeper inspection + try to restart the daemon
        return [
            "cleanup-stale-sessions",
            "check-disk-space",
            "audit-memory-size",
            "restart-hermes-daemon",
        ]
    if health == Health.DEAD:
        # Even DEAD: try to restart as last resort
        return [
            "cleanup-stale-sessions",
            "check-disk-space",
            "restart-hermes-daemon",
        ]
    if health == Health.UNKNOWN:
        return ["cleanup-stale-sessions"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes auto-wake watcher")
    parser.add_argument("--dry-run", action="store_true", help="log only, no actions")
    parser.add_argument("--status", action="store_true", help="print current state and exit")
    args = parser.parse_args()

    state = load_state()

    if args.status:
        health, age = detect_health()
        print(f"heartbeat: {HEARTBEAT_FILE}")
        print(f"exists:    {HEARTBEAT_FILE.exists()}")
        print(f"age:       {age:.0f}s" if age != float('inf') else "age:       infinite (no file)")
        print(f"health:    {health.value}")
        print(f"last_run:  {time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(state.last_run)) if state.last_run else 'never'}")
        print(f"actions:   {state.last_actions}")
        return 0

    health, age = detect_health()
    log(f"tick: health={health.value} age={age:.0f}s")

    if health == Health.HEALTHY:
        state.last_status = health.value
        state.last_run = time.time()
        save_state(state)
        return 0

    # DEAD: alert and disable self to avoid spam loop
    if health == Health.DEAD:
        if state.last_status != "dead":
            msg = f"🔴 Hermes DEAD: no heartbeat for {age/60:.1f} min"
            log(msg)
            if not args.dry_run:
                notify_telegram(msg)
        state.last_status = "dead"
        state.last_run = time.time()
        save_state(state)
        return 0

    # DEEP_ZOMBIE: alert + run deeper actions
    if health == Health.DEEP_ZOMBIE:
        if state.last_status not in ("deep_zombie", "dead"):
            msg = f"⚠️ Hermes DEEP ZOMBIE: no heartbeat for {age/60:.1f} min"
            log(msg)
            if not args.dry_run:
                notify_telegram(msg)

    # Run actions
    actions = actions_for_health(health)
    failed: list[str] = []
    for action in actions:
        if args.dry_run:
            log(f"dry-run: would run {action}")
            continue
        rc, output = run_action(action, state)
        if rc != 0:
            failed.append(f"{action}({rc})")
            log(f"action {action} FAILED: rc={rc} output={output[:200]}")
        else:
            log(f"action {action} OK: {output[:200]}")

    if failed:
        msg = f"🟡 Auto-wake: {len(failed)} action(s) failed: {', '.join(failed)}"
        if not args.dry_run:
            notify_telegram(msg)

    state.last_status = health.value
    state.last_run = time.time()
    save_state(state)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())