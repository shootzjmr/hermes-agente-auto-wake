# hermes-agente-auto-wake

> Self-monitoring + auto-recovery system for [Hermes Agent](https://github.com/hermes-agent).
> Detects when the Hermes daemon goes zombie (no heartbeat) and triggers corrective actions
> (cleanup stale sessions, check disk, audit memory, restart daemon, Telegram alert).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-9%2F9-brightgreen.svg)](#tests)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)

## What it does

A 3-layer system that watches over your Hermes Agent daemon:

```
┌─────────────────────────────────────────┐
│ Layer 1: HEARTBEAT PINGER               │
│ Every 1 min via systemd timer           │
│ Touches ~/.hermes/.heartbeat            │
│ (proof-of-life, no LLM)                 │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ Layer 2: WATCHER                        │
│ Every 5 min via systemd timer           │
│ Reads heartbeat mtime                   │
│ Decides: HEALTHY/ZOMBIE/DEEP_ZOMBIE/DEAD│
│ Triggers actions                        │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ Layer 3: ACTIONS                        │
│ cleanup-stale-sessions.py               │
│ check-disk-space.py                     │
│ audit-memory-size.py                    │
│ restart-hermes-daemon.py                │
│ (each returns 0/non-0, escalates to TG) │
└─────────────────────────────────────────┘
```

## Health states

| State | Heartbeat age | Watcher behavior |
|---|---|---|
| **HEALTHY** | < 10 min | Exit 0, no-op |
| **ZOMBIE** | 10–30 min | Run cleanup + check-disk |
| **DEEP_ZOMBIE** | 30–60 min | + audit + Telegram WARN + restart attempt |
| **DEAD** | ≥ 60 min | Telegram CRITICAL + self-disable (anti-spam) |

## Install

```bash
git clone https://github.com/shootzjmr/hermes-agente-auto-wake.git
cd hermes-agente-auto-wake

# Copy scripts to your Hermes bin
mkdir -p ~/.hermes/bin/auto-wake-actions
cp bin/heartbeat-pinger.py ~/.hermes/bin/
cp bin/auto-wake.py ~/.hermes/bin/
cp bin/send-telegram.py ~/.hermes/bin/
cp -r bin/auto-wake-actions/* ~/.hermes/bin/auto-wake-actions/
chmod +x ~/.hermes/bin/heartbeat-pinger.py ~/.hermes/bin/auto-wake.py
chmod +x ~/.hermes/bin/send-telegram.py
chmod +x ~/.hermes/bin/auto-wake-actions/*.py

# Copy tests
cp test_auto_wake.py ~/.hermes/bin/

# Install systemd units (symlinks from your repo to /etc/systemd/system)
mkdir -p ~/.hermes/etc/systemd
cp systemd/* ~/.hermes/etc/systemd/
for u in hermes-heartbeat-pinger hermes-auto-wake; do
  for t in timer service; do
    sudo ln -sf ~/.hermes/etc/systemd/${u}.${t} /etc/systemd/system/${u}.${t}
  done
done
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-heartbeat-pinger.timer hermes-auto-wake.timer

# Patch your ~/.hermes/config.yaml — add this section:
# auto_wake:
#   enabled: true
#   heartbeat_interval_seconds: 60
#   watch_interval_seconds: 300
#   zombie_threshold_seconds: 600
#   deep_zombie_threshold_seconds: 1800
#   dead_threshold_seconds: 3600
#   action_cooldown_seconds: 1800
#   alert_channel: telegram
#   actions_dir: ~/.hermes/bin/auto-wake-actions/

# Verify
systemctl list-timers hermes-*
python3 ~/.hermes/bin/test_auto_wake.py   # should print "Ran 9 tests ... OK"
```

## Usage

```bash
# Check current status
python3 ~/.hermes/bin/auto-wake.py --status

# Dry run (logs only, no actions, no Telegram)
python3 ~/.hermes/bin/auto-wake.py --dry-run

# Force a zombie scenario for debugging
touch -d "20 minutes ago" ~/.hermes/.heartbeat
python3 ~/.hermes/bin/auto-wake.py --dry-run

# Send a test Telegram alert
python3 ~/.hermes/bin/send-telegram.py "🟢 Auto-wake installed and working"
```

## Tests

```bash
python3 test_auto_wake.py
```

9/9 tests, stdlib-only (`unittest`, no `pytest` dependency).

## File layout

```
hermes-agente-auto-wake/
├── README.md
├── LICENSE
├── bin/
│   ├── heartbeat-pinger.py        # Layer 1: touch ~/.hermes/.heartbeat
│   ├── auto-wake.py               # Layer 2: watcher + decision tree
│   ├── send-telegram.py           # Wrapper around `hermes send --to telegram`
│   └── auto-wake-actions/
│       ├── cleanup-stale-sessions.py
│       ├── check-disk-space.py
│       ├── audit-memory-size.py
│       └── restart-hermes-daemon.py
├── systemd/
│   ├── hermes-heartbeat-pinger.timer
│   ├── hermes-heartbeat-pinger.service
│   ├── hermes-auto-wake.timer
│   └── hermes-auto-wake.service
├── test_auto_wake.py
└── .github/
    └── workflows/
        └── tests.yml              # CI: run tests on every push/PR
```

## Configuration

All thresholds live in `~/.hermes/config.yaml` under the `auto_wake:` key:

| Key | Default | Purpose |
|---|---|---|
| `enabled` | `true` | Master switch |
| `heartbeat_interval_seconds` | `60` | Pinger frequency |
| `watch_interval_seconds` | `300` | Watcher frequency |
| `zombie_threshold_seconds` | `600` | Age that triggers ZOMBIE |
| `deep_zombie_threshold_seconds` | `1800` | Age that triggers DEEP_ZOMBIE |
| `dead_threshold_seconds` | `3600` | Age that triggers DEAD |
| `action_cooldown_seconds` | `1800` | Don't re-run same action within 30 min |
| `alert_channel` | `telegram` | Notification channel |

## Design decisions

- **Stdlib only** — zero deps beyond Python 3.8+, works anywhere Hermes does
- **Cooldown per action, not global** — one failure doesn't block others
- **DEAD self-disables** — prevents Telegram spam loops on extended crashes
- **Actions return rc** — the watcher decides escalation, not the actions themselves
- **SQLite via Python** — no `sqlite3` CLI dependency (Proxmox LXC doesn't ship it)
- **`Path.home()` everywhere** — portable to any user, not hardcoded `/root`

## License

MIT — see [LICENSE](LICENSE).

## Author

[shootzjmr](https://github.com/shootzjmr) — built for the [Hermes Agent](https://github.com/hermes-agent) ecosystem.
Self-published via the `publish-skill-to-github` skill on 2026-07-04.