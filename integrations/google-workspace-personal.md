# Personal Gmail + Calendar (Inbox / Chronos)

**Scope:** Michael's **personal** Google account only. Never firm / Paul Weiss mail.

**Owners after wire-up**

| Surface | Bot | Callsign | Access |
|---|---|---|---|
| Gmail read / triage | `email_reader` | **Inbox** | `gmail search`, `gmail get`, `gmail labels` only |
| Calendar read + write | `calendar_manager` | **Chronos** | `calendar list/create/delete` |
| Classification / dispatch | `chief_of_staff` | Helm | **No** permanent mail/calendar domain tools |

**Non-owners:** Helm, Quill, Tasker, Mate, Purse, vault bots — do not hold Gmail/Calendar as a home surface.

## Stack

- Hermes skill: `google-workspace` (shared under `~/.hermes/skills/productivity/google-workspace`)
- Symlinked into:
  - `~/.hermes/profiles/email_reader/skills/productivity/google-workspace`
  - `~/.hermes/profiles/calendar_manager/skills/productivity/google-workspace`
- OAuth token (shared): `~/.hermes/google_token.json` (symlinked into both profile homes)
- Client secret: `~/.hermes/google_client_secret.json` (Desktop OAuth client; not a secret-in-git path)
- Fleet gate CLI: `scripts/gapi_fleet.py` — **blocks send/reply/forward**
- OAuth helper (no `gmail.send` scope): `scripts/google_personal_oauth.py`
- One-shot wire: `scripts/wire_google_personal.sh`

## Hard rules

1. **No mail send path** anywhere on the fleet (SOUL + `gapi_fleet.py` + OAuth scopes).
2. Personal account only.
3. Never paste tokens / client secrets into Discord, Kanban, or result packets.
4. Chronos does **not** own Todoist (Tasker does). Inbox does **not** draft or send (Quill drafts; human sends).

## OAuth (Michael, once)

```bash
PY="$HOME/.hermes/hermes-agent/venv/bin/python"
OAUTH="$HOME/carrier_hermes/scripts/google_personal_oauth.py"

$PY $OAUTH --auth-url
# open URL → personal Google only → copy full localhost:1 redirect URL
$PY $OAUTH --auth-code 'PASTE_URL_OR_CODE'
$PY $OAUTH --check
$PY $OAUTH --sync-profiles
bash "$HOME/carrier_hermes/scripts/wire_google_personal.sh"
```

Browser error on `http://localhost:1` after consent is expected.

## Agent usage

```bash
# From Inbox home (HERMES_HOME set by hermes -p email_reader)
python ~/carrier_hermes/scripts/gapi_fleet.py inbox gmail search 'is:unread' --max 10
python ~/carrier_hermes/scripts/gapi_fleet.py inbox gmail get MESSAGE_ID

# From Chronos home
python ~/carrier_hermes/scripts/gapi_fleet.py chronos calendar list
```

Direct `google_api.py gmail send` is out of policy even if the upstream skill documents it; agents must use `gapi_fleet.py`.

## Apply matrix note

`scripts/apply_bot_matrix.sh` leaves **terminal** enabled for `email_reader` and `calendar_manager` so the skill CLI can run. SOUL + `gapi_fleet.py` keep the surface narrow (no send, no Todoist MCP, no broad browse).
