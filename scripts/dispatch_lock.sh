#!/usr/bin/env bash
# Usage: dispatch_lock.sh {check|set|clear} [reason]
set -euo pipefail
LOCK_PATH="${CARRIER_DISPATCH_LOCK:-$HOME/.hermes/carrier/DISPATCH_LOCK}"
mkdir -p "$(dirname "$LOCK_PATH")"
cmd="${1:-check}"
case "$cmd" in
  check)
    if [[ -f "$LOCK_PATH" ]]; then
      echo "LOCKED"
      cat "$LOCK_PATH"
      exit 10
    fi
    echo "OPEN"
    exit 0
    ;;
  set)
    reason="${2:-unspecified}"
    printf 'locked_at=%s\nreason=%s\nby=subscription_watcher\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >"$LOCK_PATH"
    echo "SET $LOCK_PATH"
    ;;
  clear)
    rm -f "$LOCK_PATH"
    echo "CLEARED"
    ;;
  *)
    echo "usage: $0 check|set|clear [reason]" >&2
    exit 2
    ;;
esac
