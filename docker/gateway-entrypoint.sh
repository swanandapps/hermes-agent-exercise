#!/usr/bin/env bash
# Prepare the Hermes profile from this repo's config, then hand over to the gateway.
#
# Runs on every container start, which is deliberate: the profile lives on a volume
# and survives restarts, so config edits in the repo have to be re-applied or the
# running agent silently drifts from the source. (We hit exactly that drift while
# developing — see docs/performance.md.)
set -euo pipefail

MODE="${HERMES_MODE:-handoff}"

echo "[entrypoint] MODEL=${MODEL:-openrouter}  mode=${MODE}  HERMES_HOME=${HERMES_HOME}"

# Fail loudly and early on a missing key rather than 40s later inside a model call.
case "${MODEL:-openrouter}" in
  openrouter|llama|fast)
    [ -n "${OPENROUTER_API_KEY:-}" ] || { echo "[entrypoint] ERROR: OPENROUTER_API_KEY is not set"; exit 1; } ;;
  openai)
    [ -n "${OPENAI_API_KEY:-}" ]     || { echo "[entrypoint] ERROR: OPENAI_API_KEY is not set"; exit 1; } ;;
esac
[ -n "${TRADE_GOV_API_KEY:-}" ] || echo "[entrypoint] WARNING: TRADE_GOV_API_KEY unset — screen_party will fail"

mkdir -p "${HERMES_HOME}"

# Write the two files Hermes actually reads (SOUL.md, config.yaml), merged from this
# repo's overlays. Same code path as local `python run.py`, so container and laptop
# cannot diverge.
python -c "import run; run._sync_profile('${MODE}')"
echo "[entrypoint] profile synced"

# The gateway's HTTP API is opt-in. Bind 0.0.0.0 because in a container 127.0.0.1
# would only be reachable from inside the container itself.
export API_SERVER_ENABLED=true
export API_SERVER_HOST=0.0.0.0
export API_SERVER_PORT=8642

exec hermes gateway run
