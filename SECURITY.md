# Security policy

If you discover a security vulnerability in this project, please report it
privately by emailing shootzjmr@users.noreply.github.com.

Please do NOT open a public GitHub issue for security problems.

## Scope

This project is a watchdog / auto-recovery system. It:

- Reads `~/.hermes/.heartbeat` (a file it owns)
- Reads/writes `~/.hermes/state.db` (SQLite, local)
- May restart the `hermes-gateway` systemd service
- May send a Telegram message to your configured HOME channel

It does NOT:

- Send data to external services you didn't explicitly configure
- Read or transmit files outside `~/.hermes/`
- Require root (works under any user, as long as `~/.hermes/` is writable)
- Phone home

## Out of scope

The wrapper `send-telegram.py` uses your existing `hermes send` CLI. Whatever
credentials `hermes` already has are used — this skill does NOT add or modify
credentials.

## Audit

All scripts use `Path.home()` and never embed absolute paths or tokens.
No `.env` files are committed (see `.gitignore`).