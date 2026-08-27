# Spec A: Helm Approval Cards via Discord

**Pattern source:** OpenMausBot `server/auto-approve.ts` + `contracts.ts` (`request.opened` / `request.resolved` events)  
**Assignee:** coding_lt  
**Priority:** 2 (blocked on human review)

---

## Problem

Helm and fleet bots can currently execute irreversible actions (git push, email send, file delete, Discord DMs to external users) without any human gate. A misrouted task, prompt injection, or bot hallucination could cause unrecoverable damage silently.

## Proposed Solution

Before executing any irreversible action, a bot pauses itself and posts an **approval card** to a designated Discord channel (`#fleet-approvals`). The human responds with ✅ or ❌ button clicks. The bot resumes or aborts based on the response.

---

## Trigger Classification

Borrow OpenMausBot's two-tier classification system directly:

**Tier 1 — Always requires approval (DESTRUCTIVE):**
- `git push --force*` or `git reset --hard`
- `rm -rf` or `rm -r -f` or `sudo rm`
- `DROP TABLE` / `DROP DATABASE` / `TRUNCATE TABLE`
- `shutdown` / `reboot` / `halt`
- `dd of=/dev/` / `diskutil erase` / `mkfs`
- Fork bombs (`:(){...}:` pattern)

**Tier 2 — Always requires approval (SENSITIVE):**
- Reading `.env`, `.ssh/`, `id_rsa`, `id_ed25519`, `authorized_keys`
- Reading `.aws/credentials`, `.netrc`, `.npmrc`, `.pypirc`
- Reading `credentials.json` or service account files

**Tier 3 — Requires approval in specific contexts (FLEET-SPECIFIC additions):**
- `email send` / SMTP calls to external addresses
- Discord DM to non-bot users
- File deletion outside `C:/Users/micha/carrier_hermes/` worktrees
- Any HTTP POST to external endpoints (except known-safe list: Discord API, GitHub API)
- Kanban task creation with `block_kind=None` (auto-unblocked tasks bypass human review)

---

## Data Model

```python
@dataclass
class ApprovalRequest:
    request_id: str          # uuid4
    bot_id: str              # which fleet bot is asking
    task_id: str             # kanban task context
    tool: str                # "bash", "git", "email_send", etc.
    summary: str             # human-readable action description (≤500 chars)
    tier: Literal["destructive", "sensitive", "fleet"]
    matched_rule: str        # the regex/rule that triggered escalation
    created_at: int          # unix timestamp
    expires_at: int          # created_at + 300 (5-minute timeout)
    discord_message_id: str  # message ID of the approval card
    outcome: Literal["pending", "allowed", "denied", "timeout"] = "pending"
    decided_by: str | None = None   # Discord user ID who clicked
    decided_at: int | None = None
```

---

## Flow

```
1. Bot is about to execute action X
2. Pre-action guard checks action against DESTRUCTIVE + SENSITIVE + FLEET regexes
3. If match:
   a. Bot does NOT execute X
   b. Bot calls approval_service.request(tool, summary) → returns request_id
   c. Approval service posts Discord embed to #fleet-approvals:
        Title: "⚠️ Approval Required — {bot_display_name}"
        Fields: Bot, Action, Tool, Tier, Task context
        Components: [✅ Allow (once)] [❌ Deny]
        Footer: "Expires in 5 minutes · request_id={request_id}"
   d. Bot blocks (polls approval DB every 5s, or waits on asyncio.Event)
4. Human clicks Allow or Deny in Discord
5. Discord interaction webhook fires → approval service records outcome
6. Bot resumes or logs denial and stops the task
7. If no response in 5 minutes → auto-deny (fail-closed)
```

---

## Key Design Decisions (from OpenMausBot)

- **Fail-closed by default:** no human = deny. `unavailable` is the safe state.
- **allowed-once semantics:** approval covers exactly this action, not a standing grant. Persistent "always allow" is a separate explicit step the user takes in settings (not yet scoped for carrier_hermes).
- **Approval key granularity:** Shell commands are keyed by program, not tool (`Bash:git` not `Bash`), so approving `git status` doesn't approve `git push --force`.
- **Separation of concerns:** The guard runs in the bot process; the approval service is a lightweight Flask sidecar that Helm owns; Discord interaction routing is Helm's existing bot infrastructure.

---

## Storage

Approval requests stored in a new SQLite table in the kanban DB:

```sql
CREATE TABLE IF NOT EXISTS approval_requests (
    request_id   TEXT PRIMARY KEY,
    bot_id       TEXT NOT NULL,
    task_id      TEXT,
    tool         TEXT NOT NULL,
    summary      TEXT NOT NULL,
    tier         TEXT NOT NULL,
    matched_rule TEXT NOT NULL,
    created_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL,
    discord_message_id TEXT,
    outcome      TEXT NOT NULL DEFAULT 'pending',
    decided_by   TEXT,
    decided_at   INTEGER
);
```

---

## Integration Points

- **carrier_hermes/scripts/approval_guard.py** — pre-action classification function
- **carrier_hermes/bots/helm/approval_service.py** — Flask sidecar, Discord interaction handler
- **Helm's existing Discord bot** — registers `/api/interactions` endpoint for button callbacks
- **kanban DB** — `approval_requests` table for persistence and timeout watchdog
- **Cron:** `approval-timeout-watchdog` — scans `pending` requests past `expires_at`, sets `timeout` + `outcome=denied`

---

## Out of Scope (this spec)

- Voice-mode approval (OpenMausBot supports "out loud" approval — skip for now)
- Standing grants ("always allow Bash:git") — future
- Multi-person approval quorum — future
