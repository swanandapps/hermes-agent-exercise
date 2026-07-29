#!/usr/bin/env bash
#
# Start everything: Hermes gateway + FastAPI relay + React UI.
#
#   ./dev.sh                 # single mode
#   ./dev.sh handoff         # Researcher -> Writer (only where that mode exists)
#   MODEL=ollama ./dev.sh    # any overlay in config/
#
# Ctrl-C stops all three. The profile is re-synced first, because it lives outside
# git (~/.hermes/profiles/) and a branch switch does NOT update it — demoing handoff
# against a stale single-mode profile fails silently, which is a bad way to find out.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

MODE="${1:-single}"
MODEL_OVERRIDE="${MODEL:-}"        # remember it: .env is sourced below and would win otherwise
GATEWAY_PORT=8642
BACKEND_PORT=8000
UI_PORT=5173

# ── environment ──────────────────────────────────────────────────────────────
[[ -f .env ]] || { echo "✗ No .env — copy .env.example and add your keys."; exit 1; }
set -a; source .env; set +a
# An explicit MODEL= on the command line beats whatever .env says.
export MODEL="${MODEL_OVERRIDE:-${MODEL:-fast}}"

[[ -d .venv ]] || { echo "✗ No .venv — python -m venv .venv && pip install -r requirements.txt"; exit 1; }
source .venv/bin/activate

# The relay authenticates to the gateway with API_SERVER_KEY, which the gateway itself
# generates and keeps in the PROFILE's .env — not this repo's. Read it from there so
# there is one copy: a duplicate in ./.env rots the day the key is rotated, and the
# failure it produces ("Illegal header value b'Bearer '") points at the network.
PROFILE_ENV="${HERMES_HOME:-$HOME/.hermes/profiles/hermes-exercise}/.env"
if [[ -z "${API_SERVER_KEY:-}" && -f "$PROFILE_ENV" ]]; then
  # Sourced in a subshell rather than parsed: the file is shell syntax, so quoting is
  # its problem, not ours.
  export API_SERVER_KEY="$(set -a; . "$PROFILE_ENV"; printf '%s' "${API_SERVER_KEY:-}")"
fi
if [[ -z "${API_SERVER_KEY:-}" ]]; then
  echo "✗ API_SERVER_KEY not found in $PROFILE_ENV"
  echo "  The relay cannot authenticate to the gateway without it. Start the gateway"
  echo "  once (hermes -p hermes-exercise gateway run) to have it generated."
  exit 1
fi

# ── ports ────────────────────────────────────────────────────────────────────
# A stale listener is worse than a missing one: the request succeeds, against the
# wrong process, and nothing in the UI says so.
for port in $GATEWAY_PORT $BACKEND_PORT $UI_PORT; do
  if lsof -ti tcp:"$port" >/dev/null 2>&1; then
    echo "  port $port busy — stopping what's on it"
    lsof -ti tcp:"$port" | xargs kill -9 2>/dev/null || true
  fi
done
sleep 1

# ── profile ──────────────────────────────────────────────────────────────────
if [[ "$MODE" == "handoff" && ! -f agents/researcher/config.handoff.yaml ]]; then
  echo "✗ handoff mode does not exist on this branch (no config.handoff.yaml)."; exit 1
fi
if [[ -f agents/researcher/config.handoff.yaml ]]; then
  python -c "import run; run._sync_profile('$MODE')"
else
  python -c "import run; run._sync_profile()"   # branch has one mode only
fi

# ── shutdown ─────────────────────────────────────────────────────────────────
PIDS=()
cleanup() {
  echo ""; echo "stopping…"
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  # npm spawns vite as a child, so killing the shell we launched leaves the node
  # process holding the port. Clear the ports themselves.
  for port in $GATEWAY_PORT $BACKEND_PORT $UI_PORT; do
    lsof -ti tcp:"$port" 2>/dev/null | xargs kill -9 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "stopped."
}
trap cleanup EXIT INT TERM

wait_for() {  # url, name, seconds
  local waited=0
  until curl -fs -m 3 "$1" >/dev/null 2>&1; do
    sleep 1; waited=$((waited + 1))
    if (( waited > $3 )); then echo "✗ $2 did not come up in $3s"; exit 1; fi
  done
  echo "  ✓ $2"
}

mkdir -p .logs

# ── 1. the agent ─────────────────────────────────────────────────────────────
echo "starting  (mode=$MODE  model=$MODEL)"
hermes -p hermes-exercise gateway run --replace > .logs/gateway.log 2>&1 &
PIDS+=($!)
wait_for "http://127.0.0.1:$GATEWAY_PORT/health" "gateway  :$GATEWAY_PORT" 90

# ── 2. the relay ─────────────────────────────────────────────────────────────
uvicorn backend.app:app --port "$BACKEND_PORT" > .logs/backend.log 2>&1 &
PIDS+=($!)
wait_for "http://127.0.0.1:$BACKEND_PORT/api/config" "backend  :$BACKEND_PORT" 30

# ── 3. the UI ────────────────────────────────────────────────────────────────
[[ -d frontend/node_modules ]] || (cd frontend && npm install --silent)
(cd frontend && npm run dev -- --port "$UI_PORT") > .logs/frontend.log 2>&1 &
PIDS+=($!)
# Vite binds localhost as IPv6 (::1) — a 127.0.0.1 probe would never succeed.
wait_for "http://localhost:$UI_PORT" "UI       :$UI_PORT" 60

echo ""
echo "  →  http://localhost:$UI_PORT"
echo "     logs in .logs/   ·   Ctrl-C to stop everything"
echo ""
wait
