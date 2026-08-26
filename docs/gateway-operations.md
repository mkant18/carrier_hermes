# Gateway Operations Guide

This document covers the root cause of the Hermes gateway poisoning bug, safe restart procedures, watchdog setup, and common failure modes.

---

## The Poisoning Problem

### Root Cause

When the Hermes gateway is started from **within** an active Hermes session (e.g., `hermes -p chief_of_staff gateway start` typed into a chat that itself runs inside Hermes), the child process inherits the parent session's environment variables, including:

| Variable | Value | Effect |
|---|---|---|
| `HERMES_DELEGATED_CHILD_CONTEXT` | `1` | Makes `kanban_db.py` raise `PermissionError` on **any** kanban mutation |
| `HERMES_IS_CHILD` | `1` | Secondary child-context flag; same effect in some code paths |
| `HERMES_CHILD_SESSION_ID` | `<session-id>` | Propagates child session ID, compounding context confusion |

### What Breaks

With `HERMES_DELEGATED_CHILD_CONTEXT=1`, the dispatcher cannot:
- Create or update tasks
- Acquire the dispatch lock
- Mark tasks as `running`, `done`, or `failed`

The fleet appears to run, but **no tasks ever dispatch**. The gateway process is alive but completely neutered.

### Why It's Hard to Notice

The gateway starts successfully, connects to Discord/Telegram, and looks healthy in `gateway_state.json`. Logs show it ticking. Only when you try to create or check a task do you notice nothing is moving.

---

## The Orphan Lock Problem

The dispatcher lock lives at:
```
C:\Users\micha\AppData\Local\hermes\kanban\.dispatcher.lock
```

If the gateway crashes uncleanly (power loss, `taskkill /F`, OOM), the lock file is not removed. The next gateway startup sees the lock, assumes another dispatcher is running, and backs off — leaving the fleet dead until the lock is manually deleted.

**Board-level lock** (also affected):
```
C:\Users\micha\AppData\Local\hermes\kanban\boards\carrier\kanban.db.dispatch.lock
```

---

## Self-Healing System

### Components

| File | Purpose |
|---|---|
| `scripts/start_gateway.ps1` | PowerShell wrapper: clears env vars, removes stale locks, starts gateway cleanly |
| `scripts/start_gateway.sh` | Bash version of same (for WSL / MSYS2 / cron) |
| `scripts/carrier_gateway_watchdog.py` | Cron watchdog: detects poisoning, tick failures, and dead gateways; auto-restarts |
| `scripts/clear_gateway_lock.py` | One-shot lock cleanup utility |
| `scripts/install_gateway_watchdog.ps1` | Installs `HermesGatewayWatchdog` Windows Scheduled Task |

### Watchdog Logic

```
Every 5 minutes:
  1. Read gateway_state.json → get PID
  2. Is PID alive?
     No  → clear locks, run start_gateway.ps1
  3. Inspect PID environment (psutil):
     HERMES_DELEGATED_CHILD_CONTEXT=1?
     HERMES_IS_CHILD=1?
     → YES: kill gateway, clear locks, restart
  4. Scan last 200 lines of gateway.log:
     tick_failure / PermissionError / dispatcher error?
     → YES: kill gateway, clear locks, restart
  5. All checks pass → print GATEWAY_HEALTHY (hash-suppressed, zero LLM cost)
```

### Output Contract

The watchdog prints exactly one line to stdout per run:

| Output | Meaning |
|---|---|
| `GATEWAY_HEALTHY` | All checks passed — gateway running clean |
| `GATEWAY_RESTARTED` | Unhealthy gateway killed and restarted |
| `GATEWAY_DOWN` | Restart attempted but gateway still not healthy |

Hermes cron hash-suppresses `GATEWAY_HEALTHY` runs (zero LLM tokens when nothing changes).

---

## Setup: First-Time Installation

### 1. Copy watchdog to Hermes scripts directory

```powershell
Copy-Item `
  "C:\Users\micha\carrier_hermes\scripts\carrier_gateway_watchdog.py" `
  "$env:LOCALAPPDATA\hermes\scripts\carrier_gateway_watchdog.py"
```

### 2. Register Hermes cron job

In a Hermes session:
```
Register cron: name=Gateway Health Watchdog, script=carrier_gateway_watchdog.py,
schedule=every 5 minutes, no_agent=True, deliver=local
```

### 3. Install Windows Scheduled Task (belt-and-suspenders)

```powershell
powershell -ExecutionPolicy Bypass -File `
  "C:\Users\micha\carrier_hermes\scripts\install_gateway_watchdog.ps1"
```

This installs `HermesGatewayWatchdog` — runs every 5 minutes and at system startup (with a 2-minute boot delay).

### 4. Verify

```powershell
# Check task is registered
Get-ScheduledTask -TaskName "HermesGatewayWatchdog"

# Force a run now
Start-ScheduledTask -TaskName "HermesGatewayWatchdog"

# Check watchdog log
Get-Content "$env:LOCALAPPDATA\hermes\carrier\logs\gateway_watchdog.log" -Tail 30
```

---

## Safe Gateway Restart Procedure (Manual)

Use this when the gateway is misbehaving and you want to restart it correctly.

### Option A: Use the wrapper script (recommended)

```powershell
powershell -ExecutionPolicy Bypass -File `
  "C:\Users\micha\carrier_hermes\scripts\start_gateway.ps1"
```

This automatically:
- Clears `HERMES_DELEGATED_CHILD_CONTEXT`, `HERMES_IS_CHILD`, `HERMES_CHILD_SESSION_ID`
- Removes stale locks
- Starts the gateway
- Waits 10 seconds and checks `gateway.log` for success

### Option B: Manual steps

```powershell
# 1. Stop the gateway
hermes -p chief_of_staff gateway stop

# 2. Wait for it to die
Start-Sleep -Seconds 3

# 3. Clear env vars in your current shell
$env:HERMES_DELEGATED_CHILD_CONTEXT = $null
$env:HERMES_IS_CHILD = $null
$env:HERMES_CHILD_SESSION_ID = $null

# 4. Clear stale locks
python "C:\Users\micha\carrier_hermes\scripts\clear_gateway_lock.py" --board all

# 5. Start fresh
hermes -p chief_of_staff gateway start
```

### Option C: From Bash / WSL

```bash
bash C:/Users/micha/carrier_hermes/scripts/start_gateway.sh --profile chief_of_staff
```

---

## Diagnosing a Poisoned Gateway

### Check if the gateway process is poisoned

```python
import psutil, os

HERMES_HOME = os.path.expandvars(r"%LOCALAPPDATA%\hermes")
pid_file = rf"{HERMES_HOME}\profiles\chief_of_staff\gateway.pid"
pid = int(open(pid_file).read().strip())

proc = psutil.Process(pid)
env = proc.environ()
print("HERMES_DELEGATED_CHILD_CONTEXT:", env.get("HERMES_DELEGATED_CHILD_CONTEXT", "NOT SET"))
print("HERMES_IS_CHILD:", env.get("HERMES_IS_CHILD", "NOT SET"))
```

If `HERMES_DELEGATED_CHILD_CONTEXT` is `1`, the gateway is poisoned. Kill it and use `start_gateway.ps1` to restart cleanly.

### Check the dispatcher lock

```bash
python C:/Users/micha/carrier_hermes/scripts/clear_gateway_lock.py --board all
```

Expected output:
- `LOCK_NOT_FOUND` — no lock (normal when dispatcher is idle)
- `LOCK_HELD_BY_PID_N` — lock is valid and owner is alive (normal during dispatch)
- `LOCK_CLEARED` — lock was stale and has been removed

### Check gateway.log for errors

```bash
tail -100 "$LOCALAPPDATA/hermes/profiles/chief_of_staff/logs/gateway.log"
```

Look for:
- `PermissionError` — child context poisoning
- `tick_failure` — dispatcher stuck
- `dispatcher.*error` — generic dispatcher problems

---

## Common Failure Modes

### Problem: "Dispatcher won't pick up tasks"

**Symptoms:** Tasks sit in `ready` state, nothing moves.

**Cause A — Poisoning:**
- Gateway has `HERMES_DELEGATED_CHILD_CONTEXT=1`
- **Fix:** Run `start_gateway.ps1`

**Cause B — Stale lock:**
- `kanban/.dispatcher.lock` exists but owner is dead
- **Fix:** `python clear_gateway_lock.py --board all`

**Cause C — DISPATCH_LOCK file:**
- `C:\Users\micha\AppData\Local\hermes\carrier\DISPATCH_LOCK` leftover from maintenance
- **Fix:** `Remove-Item "$env:LOCALAPPDATA\hermes\carrier\DISPATCH_LOCK"`

---

### Problem: "Gateway started from within Hermes chat — now broken"

**Symptoms:** Gateway appears running, Discord connected, but no kanban mutations work.

**Cause:** Child context inherited from parent Hermes session.

**Fix:**
```powershell
hermes -p chief_of_staff gateway stop
powershell -ExecutionPolicy Bypass -File C:\Users\micha\carrier_hermes\scripts\start_gateway.ps1
```

**Prevention:** Always use `start_gateway.ps1` to start the gateway — never `hermes gateway start` directly from within a Hermes session.

---

### Problem: "Watchdog keeps restarting gateway every 5 minutes"

**Symptoms:** `gateway_watchdog.log` shows repeated `GATEWAY_RESTARTED`.

**Cause:** Gateway keeps inheriting child context (something is relaunching it via a Hermes session).

**Fix:**
1. Check what is launching the gateway: `hermes -p chief_of_staff gateway logs`
2. Ensure the Windows Scheduled Task (HermesGatewayWatchdog) is the gateway launcher, not a manual session
3. Remove any conflicting cron job that calls `hermes gateway start` directly

---

### Problem: "install_gateway_watchdog.ps1 fails with permissions error"

**Cause:** Task Scheduler requires at least Interactive logon (no admin needed, but must be current user).

**Fix:**
```powershell
# Verify you're running as yourself, not an elevated/different account
whoami

# Run without elevation:
powershell -ExecutionPolicy Bypass -File install_gateway_watchdog.ps1
```

---

## Architecture Reference

```
carrier_hermes/scripts/
├── start_gateway.ps1          ← PowerShell clean-start wrapper
├── start_gateway.sh           ← Bash clean-start wrapper
├── carrier_gateway_watchdog.py ← Cron watchdog (no_agent, zero LLM)
├── clear_gateway_lock.py      ← Lock cleanup utility
└── install_gateway_watchdog.ps1 ← Task Scheduler installer

%LOCALAPPDATA%\hermes\
├── scripts\
│   └── carrier_gateway_watchdog.py  ← deployed watchdog (cron reads from here)
├── kanban\
│   └── .dispatcher.lock             ← global dispatcher lock (can go stale)
├── kanban\boards\carrier\
│   └── kanban.db.dispatch.lock      ← carrier board lock
└── profiles\chief_of_staff\
    ├── gateway.pid                  ← gateway process PID
    ├── gateway_state.json           ← gateway health state
    └── logs\
        └── gateway.log              ← gateway runtime log (watchdog reads tail)
```

---

## Cron Job Reference

The watchdog is registered in Hermes cron:

```
name:     Gateway Health Watchdog
script:   carrier_gateway_watchdog.py
schedule: every 5 minutes
no_agent: true
deliver:  local
```

`no_agent=true` means the script runs verbatim — zero LLM tokens. Stable `GATEWAY_HEALTHY` output is hash-suppressed (no agent launched, no cost).

The Windows Scheduled Task (`HermesGatewayWatchdog`) provides a second layer — it runs even if the Hermes cron scheduler itself is down.
