#!/usr/bin/env bash
# One-command local dev startup — no Docker required.
#
# Starts Postgres (via Homebrew), applies migrations, and runs the API + web
# app in the background so you can just open http://localhost:3000 and leave
# it running. Safe to re-run any time: skips anything already up.
#
# ---- One-time setup (do this once, not every time) ----
#   brew install postgresql@16
#   cd apps/api && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
#   cd apps/web && pnpm install
#   Copy apps/api/.env.example -> apps/api/.env (fill in your Clerk JWKS URL)
#   Copy apps/web/.env.local.example -> apps/web/.env.local (fill in your Clerk keys)
#   Optionally: brew install tesseract   (only needed for scanned-PDF/OCR uploads)
#
# ---- Every time after that ----
#   ./dev-up.sh      # start everything, then open http://localhost:3000
#   ./dev-down.sh    # stop the API/web when you're done (Postgres keeps running)

set -euo pipefail
cd "$(dirname "$0")"

RUN_DIR=".dev"
mkdir -p "$RUN_DIR"
API_LOG="$RUN_DIR/api.log"
WEB_LOG="$RUN_DIR/web.log"
API_PID="$RUN_DIR/api.pid"
WEB_PID="$RUN_DIR/web.pid"

is_running() {
  [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null
}

echo "==> Picxify dev environment"

# ---- Postgres ----
if ! command -v pg_isready >/dev/null 2>&1; then
  echo "!! Postgres not found on PATH. Install it once with: brew install postgresql@16"
  exit 1
fi
if ! pg_isready -q 2>/dev/null; then
  echo "-- starting Postgres (brew services)…"
  PG_FORMULA=$(brew list --formula 2>/dev/null | grep -m1 '^postgresql' || true)
  if [[ -z "$PG_FORMULA" ]]; then
    echo "!! No installed postgresql formula found. Install one: brew install postgresql@16"
    exit 1
  fi
  brew services start "$PG_FORMULA" >/dev/null
  for _ in $(seq 1 15); do
    pg_isready -q 2>/dev/null && break
    sleep 1
  done
fi
echo "   Postgres: up"

# Create the picxify role/database once (idempotent — ignores "already exists").
if ! psql -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='picxify'" 2>/dev/null | grep -q 1; then
  echo "-- creating the 'picxify' role/database…"
  createuser -s picxify 2>/dev/null || true
  createdb -O picxify picxify 2>/dev/null || true
  psql -d postgres -c "ALTER USER picxify WITH PASSWORD 'picxify';" >/dev/null 2>&1 || true
fi

# ---- API ----
if [[ ! -f apps/api/.env ]]; then
  echo "!! apps/api/.env is missing."
  echo "   Copy apps/api/.env.example -> apps/api/.env, fill in your Clerk JWKS URL, and re-run."
  exit 1
fi
if [[ ! -d apps/api/.venv ]]; then
  echo "!! apps/api/.venv is missing. One-time setup:"
  echo "   cd apps/api && python -m venv .venv && source .venv/bin/activate && pip install -e \".[dev]\""
  exit 1
fi
if ! grep -q "^STORAGE_BACKEND=local" apps/api/.env 2>/dev/null; then
  echo "STORAGE_BACKEND=local" >> apps/api/.env
  echo "   (added STORAGE_BACKEND=local to apps/api/.env — files land on disk, no MinIO/S3 needed)"
fi
if ! grep -q "^RUN_JOBS_INLINE=true" apps/api/.env 2>/dev/null; then
  echo "RUN_JOBS_INLINE=true" >> apps/api/.env
  echo "   (added RUN_JOBS_INLINE=true to apps/api/.env — parse/generate run in-process, no Redis/worker needed)"
fi

if is_running "$API_PID"; then
  echo "   API: already running (pid $(cat "$API_PID"))"
else
  echo "-- applying database migrations…"
  (cd apps/api && source .venv/bin/activate && alembic upgrade head)
  echo "-- starting API on :8000…"
  (
    cd apps/api
    source .venv/bin/activate
    nohup uvicorn app.main:app --port 8000 >"../../$API_LOG" 2>&1 &
    echo $! >"../../$API_PID"
  )
  sleep 1
  is_running "$API_PID" && echo "   API: pid $(cat "$API_PID"), logs at $API_LOG" \
    || { echo "!! API failed to start — check $API_LOG"; exit 1; }
fi

# ---- Web ----
if [[ ! -f apps/web/.env.local ]]; then
  echo "!! apps/web/.env.local is missing."
  echo "   Copy apps/web/.env.local.example -> apps/web/.env.local, fill in your Clerk keys, and re-run."
  exit 1
fi
if [[ ! -d apps/web/node_modules ]]; then
  echo "!! apps/web/node_modules is missing. One-time setup: cd apps/web && pnpm install"
  exit 1
fi

if is_running "$WEB_PID"; then
  echo "   Web: already running (pid $(cat "$WEB_PID"))"
else
  echo "-- starting web app on :3000…"
  (
    cd apps/web
    nohup pnpm dev >"../../$WEB_LOG" 2>&1 &
    echo $! >"../../$WEB_PID"
  )
  sleep 1
  is_running "$WEB_PID" && echo "   Web: pid $(cat "$WEB_PID"), logs at $WEB_LOG" \
    || { echo "!! Web failed to start — check $WEB_LOG"; exit 1; }
fi

echo ""
echo "==> Ready. Open http://localhost:3000"
echo "    API docs at http://localhost:8000/docs — logs in .dev/*.log"
echo "    Run ./dev-down.sh when you're done."
