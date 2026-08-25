#!/usr/bin/env bash
# Helm preflight: refuse if DISPATCH_LOCK or SPEND_HALT.
set -euo pipefail
ROOT="${CARRIER_HERMES_ROOT:-$HOME/carrier_hermes}"
fail=0
if ! bash "$ROOT/scripts/dispatch_lock.sh" check >/tmp/carrier_lock_out 2>&1; then
  echo "REFUSE DISPATCH_LOCK"
  cat /tmp/carrier_lock_out
  fail=1
fi
if ! bash "$ROOT/scripts/spend_halt.sh" check >/tmp/carrier_halt_out 2>&1; then
  echo "REFUSE SPEND_HALT"
  cat /tmp/carrier_halt_out
  fail=1
fi
if [[ "$fail" -eq 1 ]]; then
  exit 12
fi
echo "PREFLIGHT_OK"
exit 0
