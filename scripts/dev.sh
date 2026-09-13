#!/usr/bin/env bash
# Start the API, a worker, and the web app together, and stop all three on
# Ctrl-C.
#
# The API binds to localhost and has no auth. The web app proxies /api to it, so
# the browser talks to one origin and there is no CORS surface to widen.
#
# The worker is here because runs execute in a worker now, not inside the API.
# Without it a submitted run would sit in the queue, which the Status screen
# would tell you but only after you went looking.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PATH="$HOME/.local/bin:$PATH"; export PATH

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "api    -> http://127.0.0.1:8000/api/docs"
echo "web    -> http://127.0.0.1:5173"
echo "status -> http://127.0.0.1:5173/status"
echo

( cd "$ROOT" && uv run python -m dbsspeech serve ) &
( cd "$ROOT" && uv run python -m dbsspeech worker ) &
( cd "$ROOT/web" && npm run dev ) &
wait
