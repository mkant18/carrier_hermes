# OpenMausBot Install Guide

## Download

Installer saved to: `C:/Users/micha/Downloads/OpenMausBot-setup.exe`

Download URL:
```
https://github.com/milind-soni/openmausbot-releases/releases/latest/download/OpenMausBot-setup.exe
```

## Installation Steps (Manual — run as user)

1. **Run the installer** (double-click or Run As Administrator):
   ```
   C:\Users\micha\Downloads\OpenMausBot-setup.exe
   ```

2. **Accept defaults** for install path (usually `C:\Program Files\OpenMausBot\`).

3. **Launch OpenMausBot** from the Start menu or desktop shortcut.

4. **Point it at your pre-configured bot profiles**:
   - In OpenMausBot settings → "Bot Profiles Directory"
   - Set path to: `C:\Users\micha\.openmausbot\bots\`

5. **Verify each bot loads** — all 20 carrier fleet bots are pre-configured.

## Pre-Configured Bots

Carrier fleet bots are written to `C:\Users\micha\.openmausbot\bots\` following
the `InstanceConfig` schema from `server/contracts.ts`.

| Bot ID | Role | Model |
|---|---|---|
| chief_of_staff | Commander | grok-4.5 (xAI) |
| marshal | Senior Lieutenant | claude-sonnet-4-6 |
| coding_lt | Coding Lieutenant | claude-sonnet-4-6 |
| ops_lt | Ops Lieutenant | claude-sonnet-4-6 |
| knowledge_lt | Knowledge Lieutenant | claude-sonnet-4-6 |
| maintenance_lt | Maintenance Lieutenant | ollama/qwen2.5:7b |
| firstmate | Coding Worker | ollama/qwen2.5:7b |
| git_yeoman | Git Worker | ollama/qwen2.5:7b |
| subscription_watcher | Billing Watcher | ollama/qwen2.5:7b |
| api_watcher | API Watcher | ollama/qwen2.5:7b |
| lockbox | Secrets Worker | ollama/qwen2.5:7b |
| passive_watch | Passive Monitor | ollama/qwen2.5:7b |
| research_agent | Research Worker | ollama/qwen2.5:7b |
| hermes_ai_explorer | AI Explorer | ollama/qwen2.5:7b |
| todoist_manager | Task Manager | ollama/qwen2.5:7b |
| email_reader | Email Reader | ollama/qwen2.5:7b |
| email_drafter | Email Drafter | ollama/qwen2.5:7b |
| calendar_manager | Calendar Manager | ollama/qwen2.5:7b |
| finance_reader | Finance Reader | ollama/qwen2.5:7b |
| obsidian_archivist | Vault Archivist | ollama/qwen2.5:7b |

## Docker Fleet

After running the installer, start the VM fleet:
```bash
cd C:/Users/micha/carrier_hermes
docker compose -f docker/docker-compose.carrier-infrastructure.yml up -d
docker compose -f docker/docker-compose.carrier-fleet.yml up -d
```

⚠️ **Docker Desktop must be running** before starting the fleet.

## Notes

- Do NOT run the installer automatically — run it manually when ready.
- Bot configs are at `C:\Users\micha\.openmausbot\bots\<bot_id>.json`
- Approval gate requires `DISCORD_FLEET_BOT_TOKEN` from Doppler.
- VM manager script: `scripts/carrier_vm_manager.py`
