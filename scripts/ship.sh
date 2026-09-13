#!/bin/bash
# Bring the deployment up on this machine, in order, stopping at the first failure:
#
#   bash scripts/ship.sh up       start the API and worker, check health
#   bash scripts/ship.sh admin    create the first account (prompts for a password)
#   bash scripts/ship.sh funnel   publish https://<this machine>.<tailnet>.ts.net
#   bash scripts/ship.sh status   what is running, and where
#
# Needs: the image built (docker compose -f docker/compose.yml build), your user
# in the docker group (log out and in after usermod, or run this through
# `newgrp docker`), and docker/.env filled in from docker/.env.example.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker/compose.yml)
# Where the host publishes the API, from docker/.env (defaults match compose.yml).
BIND=$(grep -E '^BIND=' docker/.env 2>/dev/null | cut -d= -f2); BIND=${BIND:-127.0.0.1}
PORT=$(grep -E '^PORT=' docker/.env 2>/dev/null | cut -d= -f2); PORT=${PORT:-8000}
URL="http://${BIND}:${PORT}"

case "${1:-}" in
  up)
    # The container runs as uid 10001; what it writes to must let it.
    setfacl -R -m u:10001:rwX -m d:u:10001:rwX derivatives runs var configs
    "${COMPOSE[@]}" up -d
    sleep 15
    "${COMPOSE[@]}" ps
    echo "--- health"
    curl -s -m 5 "$URL/api/health"; echo
    curl -s -m 5 -o /dev/null -w "front end: HTTP %{http_code} (%{content_type}) at $URL\n" "$URL/"
    ;;
  admin)
    # Interactive on purpose: the password is typed, never on a command line.
    "${COMPOSE[@]}" exec api python -m dbsspeech users add \
      --name "${2:-garrett}" --email "${3:-garrettthrash54@gmail.com}" --role admin
    ;;
  funnel)
    # Public HTTPS on the internet, proxied to the API on localhost. The first
    # run prints a link to enable Funnel and HTTPS certificates on the tailnet
    # (a one-time click in the admin console); run it again after that.
    tailscale funnel --bg "$PORT"
    tailscale funnel status
    ;;
  status)
    "${COMPOSE[@]}" ps
    tailscale funnel status || true
    ;;
  *)
    sed -n 2,8p "$0"; exit 2 ;;
esac
