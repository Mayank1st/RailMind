#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# RailMind — SSH tunnel to the VM Postgres (localhost:5433 -> VM Postgres 5432).
#
# The VM's Postgres is NOT exposed to the internet — only reachable over SSH.
# This opens localhost:5433 so the app/alembic can reach it with APP_ENV=prod.
#
# Connection details (host / user / key / forward) live in your LOCAL
# ~/.ssh/config under the `railmind-db` alias — intentionally NOT in this
# committed file, so no infra details leak into the repo. One-time setup
# (see project README → "Local vs Prod"):
#
#   Host railmind-db
#       HostName <your-vm-host>
#       User <your-ssh-user>
#       IdentityFile ~/.ssh/<your-key>
#       LocalForward 5433 localhost:5432
#       ServerAliveInterval 30
#       ServerAliveCountMax 3
#       ExitOnForwardFailure yes
#
# Then, with the tunnel up:
#   scripts/db-tunnel.sh                 # start (default); no-op if already up
#   APP_ENV=prod alembic upgrade head
#   APP_ENV=prod fastapi dev app/main.py
#
# Commands:  start (default) | status | stop | watch (foreground, auto-reconnect)
# Override the ssh alias with:  RAILMIND_DB_SSH=<alias-or-user@host>
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SSH_ALIAS="${RAILMIND_DB_SSH:-railmind-db}"
LOCAL_PORT=5433

is_up() { lsof -iTCP:"$LOCAL_PORT" -sTCP:LISTEN -n >/dev/null 2>&1; }

require_alias() {
  if ! ssh -G "$SSH_ALIAS" 2>/dev/null | grep -q '^localforward '; then
    echo "❌ SSH alias '$SSH_ALIAS' has no LocalForward configured." >&2
    echo "   Add a 'railmind-db' Host to ~/.ssh/config (see this file's header /" >&2
    echo "   README → 'Local vs Prod'), or set RAILMIND_DB_SSH. Aborting." >&2
    exit 1
  fi
}

case "${1:-start}" in
  status)
    is_up && echo "✅ tunnel UP   — localhost:${LOCAL_PORT} -> VM Postgres" \
          || echo "❌ tunnel DOWN — run: scripts/db-tunnel.sh"
    ;;
  stop)
    pkill -f "ssh.* ${SSH_ALIAS}\b" 2>/dev/null && echo "tunnel stopped" \
      || echo "no tunnel was running"
    ;;
  watch)
    require_alias
    echo "watching tunnel (auto-reconnect on drop; Ctrl-C to quit)…"
    while true; do
      ssh -N "$SSH_ALIAS" || true
      echo "$(date '+%H:%M:%S') tunnel dropped — reconnecting in 3s…"
      sleep 3
    done
    ;;
  start)
    require_alias
    if is_up; then echo "tunnel already UP on localhost:${LOCAL_PORT}"; exit 0; fi
    ssh -f -N "$SSH_ALIAS"
    is_up && echo "✅ tunnel started on localhost:${LOCAL_PORT}" \
          || { echo "❌ failed to start tunnel"; exit 1; }
    ;;
  *)
    echo "usage: $0 [start|status|stop|watch]" >&2; exit 2
    ;;
esac
