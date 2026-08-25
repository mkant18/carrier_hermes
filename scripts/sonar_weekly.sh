#!/usr/bin/env bash
# Sonar weekly forced digest — no_agent trigger to generate weekly baseline digest even without diff.
set -euo pipefail
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPTS_DIR/sonar_heartbeat.sh" ]]; then
  exec bash "$SCRIPTS_DIR/sonar_heartbeat.sh" --force
elif [[ -f "$HOME/.hermes/scripts/sonar_heartbeat.sh" ]]; then
  exec bash "$HOME/.hermes/scripts/sonar_heartbeat.sh" --force
elif [[ -f "$HOME/carrier_hermes/scripts/sonar_heartbeat.sh" ]]; then
  exec bash "$HOME/carrier_hermes/scripts/sonar_heartbeat.sh" --force
else
  echo "sonar_heartbeat.sh not found" >&2
  exit 1
fi
