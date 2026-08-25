#!/usr/bin/env bash
# Usage: spend_halt.sh {check|set|clear} [reason]
set -euo pipefail
HALT_PATH="${CARRIER_SPEND_HALT:-$HOME/.hermes/carrier/SPEND_HALT}"
mkdir -p "$(dirname "$HALT_PATH")"
cmd="${1:-check}"
case "$cmd" in
  check)
    if [[ -f "$HALT_PATH" ]]; then
      echo "HALTED"
      cat "$HALT_PATH"
      exit 11
    fi
    echo "OPEN"
    exit 0
    ;;
  set)
    reason="${2:-unspecified}"
    printf 'halted_at=%s\nreason=%s\nby=api_watcher\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >"$HALT_PATH"
    echo "SET $HALT_PATH"
    ;;
  clear)
    rm -f "$HALT_PATH"
    echo "CLEARED"
    ;;
  *)
    echo "usage: $0 check|set|clear [reason]" >&2
    exit 2
    ;;
esac
