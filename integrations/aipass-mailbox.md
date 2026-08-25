# AIPass hybrid — bot-to-bot mailbox (Carrier Hermes)

## What AIPass means here

**Not** `pip install aipass`, **not** `.trinity/`, **not** `.ai_mail.local/`, **not** AIPass Hub cloud API.

**Yes** the carrier_ops **HYBRID AIPass** decision:

| Piece | Path | Role |
|---|---|---|
| Protocol library | `vendored/aipass-mailbox/mailbox.py` | File message format (frontmatter + body) |
| Runtime mailboxes | `$OBSIDIAN_VAULT_PATH/_agent/mailbox/<bot_id>/{inbox,outbox}/` | Per-bot in/out |
| Protocol doc | `_agent/mailbox/PROTOCOL.md` (created at setup) | Conventions |

Upstream concepts: [AIOSAI/AIPass](https://github.com/AIOSAI/AIPass) mail design — reimplemented in-tree (see `vendored/aipass-mailbox/PROVENANCE.md`).

## Why it exists next to Kanban / Hermes Bot Mode

| Channel | Best for |
|---|---|
| Hermes Bot Mode + job packets / Kanban | Durable assigned work, tool-scoped workers |
| **AIPass mailbox** | Async bot→bot reports, handoffs, “run finished — please intake”, CFO alerts without burning a full CoS turn |
| Discord | Human-facing only |

AIPass is the **blackboard mail** layer so bots do not need free-form multiplayer chat, and so **Clerk** can pull post-run packages from many bots’ outboxes.

## Message shape

Filename: `<utc>-<from>-<slug>.md`  
Frontmatter: `from`, `to`, `mission`, `status` (`unread` \| `read` \| `folded`)  
Body sections (conventional): `## REPORT`, `## OPEN DECISIONS`, `## DIVERGENCES`, optional `## ARTIFACTS` (paths).

## Directory layout

```text
$OBSIDIAN_VAULT_PATH/_agent/mailbox/
  PROTOCOL.md
  chief_of_staff/{inbox,outbox}/
  subscription_watcher/{inbox,outbox}/
  api_watcher/{inbox,outbox}/
  firstmate/{inbox,outbox}/
  hermes_ai_explorer/{inbox,outbox}/
  email_reader/{inbox,outbox}/
  email_drafter/{inbox,outbox}/
  calendar_manager/{inbox,outbox}/
  todoist_manager/{inbox,outbox}/
  vault_librarian/{inbox,outbox}/
  obsidian_archivist/{inbox,outbox}/
  research_agent/{inbox,outbox}/
  michael/{inbox}/          # optional human-facing drops via CoS only
```

## Rules

1. Bots write **only** to their own `outbox/` and read **only** their own `inbox/` (plus CoS may read any for orchestration).
2. Delivering mail = write into **recipient** `inbox/` (or CoS copies/moves). Prefer helper script `scripts/aipass_send.py`.
3. `to: chief_of_staff` for escalations; `to: obsidian_archivist` for intake candidates after runs.
4. Status lifecycle: unread → read → folded (done/archived).
5. No secrets in mailbox bodies (use paths to redacted `_agent/` artifacts).
6. Mail is not a send-email channel. No external SMTP.

## Helm (CoS) duties

- On job complete: ensure worker dropped result packet **and** optional AIPass outbox note if another bot must act (e.g. Tasker after Chronos, Clerk after Probe).
- Drain own inbox each turn (or cron): convert unread mail into Kanban/bot jobs.
- Clerk: after multi-bot runs, CoS may batch `to: obsidian_archivist` with artifact paths.

## Ledger / Vigil

May post `to: chief_of_staff` mail on budget/stall events in addition to Discord + lock files (mail is durable audit).

## Setup snippet

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Desktop/Existing Folders/OBSIDIAN}"
BOTS=(chief_of_staff subscription_watcher api_watcher firstmate hermes_ai_explorer
      email_reader email_drafter calendar_manager todoist_manager vault_librarian
      obsidian_archivist research_agent michael)
for b in "${BOTS[@]}"; do
  mkdir -p "$VAULT/_agent/mailbox/$b/inbox" "$VAULT/_agent/mailbox/$b/outbox"
done
cp -n ~/carrier_hermes/vendored/aipass-mailbox/PROTOCOL.template.md \
  "$VAULT/_agent/mailbox/PROTOCOL.md" 2>/dev/null || true
```

## Python usage

```python
import sys
sys.path.insert(0, str(Path.home() / "carrier_hermes/vendored/aipass-mailbox"))
import mailbox as aipass
# write Message to recipient inbox path...
```

Sender: `scripts/aipass_send.py` (stdlib `mailbox` clash — load `aipass_mailbox` via importlib).
