#!/usr/bin/env bash
# start_gateway.sh — Clean-room gateway start for chief_of_staff (Bash version)
#
# PURPOSE: Starts the Hermes gateway in a child-context-free environment.
# ROOT CAUSE FIXED: When Hermes spawns a gateway from inside a Hermes session,
# the child process inherits HERMES_DELEGATED_CHILD_CONTEXT=1, which causes
# kanban_db.py to raise PermissionError on any kanban mutation, breaking the
# dispatcher permanently.
#
# USAGE:
#   bash start_gateway.sh [--profile chief_of_staff] [--wait 10]
#
# EXIT:  0 = gateway started and healthy
#        1 = failed (see gateway_watchdog.log)

set -euo pipefail

# --- Defaults ----------------------------------------------------------------
PROFILE="chief_of_staff"
WAIT_SECONDS=10

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile) PROFILE="$2"; shift 2 ;;
        --wait)    WAIT_SECONDS="$2"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# --- Paths -------------------------------------------------------------------
HERMES_HOME="${LOCALAPPDATA:-$HOME/AppData/Local}/hermes"
LOG_DIR="$HERMES_HOME/carrier/logs"
LOG_FILE="$LOG_DIR/gateway_watchdog.log"
LOCK_FILE="$HERMES_HOME/kanban/.dispatcher.lock"
GW_LOG="$HERMES_HOME/profiles/$PROFILE/logs/gateway.log"
GW_PID_FILE="$HERMES_HOME/profiles/$PROFILE/gateway.pid"
GW_STATE_FILE="$HERMES_HOME/profiles/$PROFILE/gateway_state.json"

mkdir -p "$LOG_DIR"

# --- Logging helper ----------------------------------------------------------
log() {
    local level="${2:-INFO}"
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    local line="[$ts] [$level] [start_gateway] $1"
    echo "$line"
    echo "$line" >> "$LOG_FILE"
}

log "=== start_gateway.sh BEGIN (profile=$PROFILE) ==="

# --- Step 1: Scrub poisoned environment variables ----------------------------
log "Clearing child-context env vars"
unset HERMES_DELEGATED_CHILD_CONTEXT || true
unset HERMES_IS_CHILD                 || true
unset HERMES_CHILD_SESSION_ID         || true
export HERMES_DELEGATED_CHILD_CONTEXT=""
export HERMES_IS_CHILD=""
export HERMES_CHILD_SESSION_ID=""
# Belt-and-suspenders: empty string prevents inheritance even if unset fails
log "Child-context env vars cleared."

# --- Step 2: Check for existing live gateway ---------------------------------
log "Checking for existing gateway process..."
if [[ -f "$GW_PID_FILE" ]]; then
    existing_pid=$(cat "$GW_PID_FILE" 2>/dev/null | tr -d '[:space:]')
    if [[ "$existing_pid" =~ ^[0-9]+$ ]]; then
        if kill -0 "$existing_pid" 2>/dev/null; then
            log "Gateway already running (PID $existing_pid). Exiting clean." "WARN"
            exit 0
        else
            log "Stale PID file (PID $existing_pid not alive). Continuing." "WARN"
        fi
    fi
fi

# --- Step 3: Remove stale dispatcher lock ------------------------------------
if [[ -f "$LOCK_FILE" ]]; then
    lock_content=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    lock_pid=""
    # Try JSON first, then plain integer
    if command -v python3 &>/dev/null; then
        lock_pid=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('pid',''))" <<< "$lock_content" 2>/dev/null || echo "")
    fi
    if [[ -z "$lock_pid" ]] && [[ "$lock_content" =~ ^[0-9]+$ ]]; then
        lock_pid="$lock_content"
    fi

    lock_owner_alive=false
    if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
        lock_owner_alive=true
    fi

    if [[ "$lock_owner_alive" == "false" ]]; then
        log "Removing stale dispatcher lock (owner PID ${lock_pid:-unknown} not running): $LOCK_FILE" "WARN"
        rm -f "$LOCK_FILE"
        log "Stale lock removed."
    else
        log "Dispatcher lock held by live PID $lock_pid — not removing."
    fi
fi

# --- Step 4: Launch gateway in clean env ------------------------------------
log "Launching: hermes -p $PROFILE gateway start"
env -u HERMES_DELEGATED_CHILD_CONTEXT \
    -u HERMES_IS_CHILD \
    -u HERMES_CHILD_SESSION_ID \
    hermes -p "$PROFILE" gateway start \
    >> "$LOG_FILE" 2>&1 &

GW_LAUNCH_PID=$!
log "Launched (background PID $GW_LAUNCH_PID). Waiting ${WAIT_SECONDS}s..."

# --- Step 5: Poll gateway log for startup confirmation ----------------------
deadline=$(( $(date +%s) + WAIT_SECONDS ))
healthy=false

while [[ $(date +%s) -lt $deadline ]]; do
    if [[ -f "$GW_LOG" ]]; then
        if tail -50 "$GW_LOG" 2>/dev/null | grep -qiE \
            "(gateway.*started|discord.*connected|telegram.*connected|platforms.*connected|gateway_state.*running)"; then
            healthy=true
            break
        fi
    fi
    sleep 0.5
done

if [[ "$healthy" == "true" ]]; then
    log "=== Gateway HEALTHY — startup confirmed in gateway.log ===" "SUCCESS"
    exit 0
else
    log "=== Gateway did NOT confirm healthy within ${WAIT_SECONDS}s — check $GW_LOG ===" "ERROR"
    exit 1
fi
