#!/usr/bin/env bash
# sync_carrier_commands_plugin.sh
# Sync the carrier-commands plugin from carrier_hermes/scripts/ into
# the chief_of_staff profile home. Run after any edit to __init__.py.
#
# Usage: bash ~/carrier_hermes/scripts/sync_carrier_commands_plugin.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/_carrier_commands_plugin.py"
DST="$HOME/.hermes/profiles/chief_of_staff/plugins/carrier-commands/__init__.py"

if [[ ! -f "$SRC" ]]; then
  echo "ERROR: source not found: $SRC" >&2
  exit 1
fi

cp "$SRC" "$DST"
echo "sync_carrier_commands_plugin: $SRC → $DST"
echo "Restart CoS gateway for changes to take effect:"
echo "  hermes -p chief_of_staff gateway restart"
