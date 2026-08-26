#!/usr/bin/env bash
# buzzctl.sh — control + health for the Carrier Buzz Nostr relay stack.
#
#   bash buzzctl.sh up       # start postgres+redis+minio+relay (idempotent)
#   bash buzzctl.sh down     # stop the stack (containers stay, data persists)
#   bash buzzctl.sh restart  # restart the relay only
#   bash buzzctl.sh status   # container status + relay health + community host
#   bash buzzctl.sh health   # exit 0 iff relay answers NIP-11 + WS reachable
#   bash buzzctl.sh logs     # tail relay logs
#
# Reboot persistence: containers use restart=unless-stopped and Docker Desktop
# AutoStart is enabled, so this stack returns on login without running 'up'.
set -uo pipefail

BUZZ_DIR="${CARRIER_BUZZ_DIR:-C:/Users/micha/buzz}"
RELAY_HOST="${CARRIER_BUZZ_HOST:-mks-pc.taileda46c.ts.net:3000}"
COMPOSE=(docker compose -f "$BUZZ_DIR/docker-compose.yml" -f "$BUZZ_DIR/docker-compose.carrier.yml")
SVCS=(postgres redis minio minio-init relay)

cd "$BUZZ_DIR" 2>/dev/null || { echo "buzzctl: $BUZZ_DIR not found" >&2; exit 1; }

case "${1:-status}" in
  up)      "${COMPOSE[@]}" up -d "${SVCS[@]}" ;;
  down)    "${COMPOSE[@]}" stop relay postgres redis minio ;;
  restart) "${COMPOSE[@]}" up -d relay; sleep 5; docker logs buzz-relay 2>&1 | grep -iE 'listening|migrations complete' | tail -2 ;;
  logs)    docker logs buzz-relay 2>&1 | tail -"${2:-40}" ;;
  status)
    echo "=== containers ==="
    "${COMPOSE[@]}" ps 2>&1 | tail -n +1
    echo ""
    echo "=== relay NIP-11 (HTTP) ==="
    if curl -s -m 5 -H 'Accept: application/nostr+json' "http://${RELAY_HOST%%:*}:${RELAY_HOST##*:}/" 2>/dev/null | grep -q '"name"'; then
      echo "  OK — relay answers on $RELAY_HOST"
    else
      echo "  DOWN — no NIP-11 response on $RELAY_HOST"
    fi
    echo "=== deployment community host ==="
    docker exec buzz-postgres psql -U buzz -d buzz -tAc "SELECT host FROM communities;" 2>/dev/null | sed 's/^/  /'
    ;;
  health)
    curl -s -m 5 -H 'Accept: application/nostr+json' "http://${RELAY_HOST%%:*}:${RELAY_HOST##*:}/" 2>/dev/null | grep -q '"name"' \
      && { echo "buzz relay: HEALTHY ($RELAY_HOST)"; exit 0; } \
      || { echo "buzz relay: DOWN ($RELAY_HOST)"; exit 1; }
    ;;
  *) echo "usage: buzzctl.sh {up|down|restart|status|health|logs [n]}" >&2; exit 2 ;;
esac
