#!/usr/bin/env bash
# Stops the API and web dev servers started by dev-up.sh.
# Postgres is left running (it's a background system service via Homebrew,
# not something dev-up.sh started fresh) — stop it separately if you want:
#   brew services stop postgresql@16

set -uo pipefail
cd "$(dirname "$0")"
RUN_DIR=".dev"

stop_pid() {
  local name="$1" pidfile="$2"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    kill "$(cat "$pidfile")" 2>/dev/null
    rm -f "$pidfile"
    echo "   $name: stopped"
  else
    rm -f "$pidfile"
    echo "   $name: not running"
  fi
}

echo "==> Stopping Picxify dev servers"
stop_pid "API" "$RUN_DIR/api.pid"
stop_pid "Web" "$RUN_DIR/web.pid"
echo ""
echo "Postgres is left running. To stop it too: brew services stop <your postgresql formula>"
echo "If a port is still stuck (rare — pnpm/next can leave a child process):"
echo "  lsof -ti:3000 | xargs kill    # web"
echo "  lsof -ti:8000 | xargs kill    # api"
