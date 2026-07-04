# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-04

### Added
- Initial release
- `heartbeat-pinger.py` — Layer 1: proof-of-life ticker (1 min)
- `auto-wake.py` — Layer 2: watcher with HEALTHY/ZOMBIE/DEEP_ZOMBIE/DEAD decision tree (5 min)
- `send-telegram.py` — wrapper around `hermes send --to telegram` for alerts
- `cleanup-stale-sessions.py` — closes Hermes sessions active > 48h
- `check-disk-space.py` — warns when free disk < 10 GB
- `audit-memory-size.py` — warns when MEMORY/USER near char limits
- `restart-hermes-daemon.py` — systemd restart for DEEP_ZOMBIE/DEAD recovery
- 4 systemd units (2 × .timer, 2 × .service)
- `test_auto_wake.py` — 9/9 unit tests, stdlib only
- GitHub Actions CI workflow
- README with architecture diagram, install instructions, design rationale

### Notes
- Requires Python 3.8+
- Tested on Proxmox LXC + Debian 12
- First public release; published via `publish-skill-to-github` skill