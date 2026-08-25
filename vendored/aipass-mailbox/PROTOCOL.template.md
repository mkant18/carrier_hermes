# AIPass mailbox protocol (vault runtime)

Hybrid AIPass for Carrier Hermes. Library: `~/carrier_hermes/vendored/aipass-mailbox/mailbox.py`.

## Status values

- `unread` — not yet processed by recipient
- `read` — opened / in progress
- `folded` — done or deliberately ignored

## Required frontmatter

`from`, `to`, `mission`, `status`

## Conventions

- One message = one `.md` file in the recipient's `inbox/`.
- Authors may keep a copy in their `outbox/`.
- Artifact paths only under `_agent/` or approved vault paths — no secrets.
- Human (`michael`) receives mail only via Helm forwarding.

## Bot ids (to/from)

Use exact bot_id strings from `carrier_hermes/bots/README.md`.
