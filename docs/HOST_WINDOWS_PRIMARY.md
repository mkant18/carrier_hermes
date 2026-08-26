# Host: Windows Primary (`MKs_PC`)

> Machine-specific record for the Carrier Hermes **primary** runtime host.
> No secrets. See `~/.hermes/carrier/HOST_ROLE.json` for the role marker.

## Role

| Field | Value |
|---|---|
| Role | **primary** |
| Platform | windows (Windows 11) |
| Host marker | `C:\Users\micha\AppData\Local\hermes\carrier\HOST_ROLE.json` (role=primary) |
| Mac | secondary / fallback — production gateway + crons must be **disabled** there |

## Paths

| What | Path |
|---|---|
| Hermes native home | `C:\Users\micha\AppData\Local\hermes\` |
| `~/.hermes` junction | `C:\Users\micha\.hermes` → same dir |
| carrier_hermes repo | `C:\Users\micha\carrier_hermes\` |
| Default `.env` | `C:\Users\micha\AppData\Local\hermes\.env` |
| Helm gateway `.env` | `…\hermes\profiles\chief_of_staff\.env` (holds `DISCORD_BOT_TOKEN` only) |
| Obsidian vault | `C:\Users\micha\Documents\Obsidian Vault\` |
| Hermes venv Python | `…\hermes\hermes-agent\venv\Scripts\python.exe` (has PyYAML; system `python3` does NOT) |
| Windows shims | `…\hermes\carrier\winshim\` (`python3`, `pgrep`, `pkill` — for repo `.sh` scripts) |

## Known Windows deviations (and how they're handled)

1. **`$HOME` / `pwd` yield MSYS `/c/Users/...`** which native Python/git misread as `C:\c\Users\...`.
   Fleet scripts now normalize `ROOT`/`SCRIPT_DIR`/`REPO_ROOT` to native form via `cygpath -m`
   (fallback: `/c/` → `C:/`). Touched: `smoke_fleet.sh`, `smoke_github_auth.sh`, `fleet_signal.sh`.
2. **No `pgrep` / `pkill`** in Git Bash. `apply_bot_matrix.sh` runs with `…\carrier\winshim` on PATH,
   which provides PowerShell/`taskkill`-backed shims. `watcher_heartbeat.sh` (Vigil) now uses a
   portable process check (PowerShell CIM fallback) and — critically — **never alarms when the
   check tool itself is missing**, so it can't set a false `DISPATCH_LOCK` every tick.
3. **System `python3` lacks PyYAML.** Use the Hermes venv Python for fleet scripts.
4. **`fcntl` is POSIX-only.** `lockbox_verify_grant.py` imports it optionally; replay-prevention
   still holds because the guarantee comes from `os.O_EXCL` (atomic on NTFS), not the advisory lock.
5. **No systemd/launchd.** Gateways persist via **Startup-folder VBS** login items
   (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Hermes_Gateway_<bot>.vbs`).
   Scheduled-Task install needs UAC; the Startup-folder fallback is used and survives reboot on login.

## Gateway topology (single-Discord-gateway rule)

- **Helm (`chief_of_staff`)** is the ONLY Discord-connected gateway (Carrier Ops app, `#command`).
- **Vigil / Ledger / Sonar / Chart** run **scheduler-only** gateways (`platforms=NONE`, no Discord)
  so their crons fire. They post to Discord via **First Watch REST** (`fleet_signal.sh` /
  `alert_signal.sh`), never a WebSocket gateway.
- `gateway_guard.sh` asserts on `gateway_state.json`'s `platforms.discord.state`, so a scheduler
  gateway is not mistaken for a rogue Discord gateway.

## Cron schedule (this host only)

| Job | Bot | Schedule | Mode |
|---|---|---|---|
| vigil-heartbeat | subscription_watcher | every 5m | no_agent script |
| ledger-heartbeat | api_watcher | every 10m | no_agent script |
| sonar-daily | passive_watch | `0 8 * * *` | no_agent script |
| chart-synthesis | hermes_ai_explorer | `0 9 * * 1,4` | agent (cheap DeepSeek) |

## Daily-use commands

```bash
hermes gateway list                       # Helm should be ✓ running (Discord)
bash "$LOCALAPPDATA/hermes/carrier/run_smoke.sh"   # full fleet smoke
"$LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe" \
  ~/carrier_hermes/scripts/billing_guard.py        # billing PASS check
```
