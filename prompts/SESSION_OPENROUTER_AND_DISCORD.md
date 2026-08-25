# Session 1 — Wire OpenRouter + Discord IDs

Paste this whole file into a **new** Hermes chat (default bot / this Mac). Product language is **bot**. Do the work with Michael; do not invent keys or Discord snowflakes.

## Goal

Finish two fleet todos:

1. Live `OPENROUTER_API_KEY` so Ledger can read $ and Inbox / Chronos / Tasker can run on **paid DeepSeek only**.
2. Real Discord channel IDs in `docs/DISCORD_CHANNELS.md` (names already frozen).

## Authority

- `~/carrier_hermes/COST_MODEL.md`
- `~/carrier_hermes/docs/DISCORD_CHANNELS.md`
- `~/carrier_hermes/docs/INTER_AGENT_PROTOCOL.md` (Ledger API freeze)
- `~/carrier_hermes/scripts/api_watcher_heartbeat.sh`
- Never commit `.env` or tokens.

## Do this

### A. OpenRouter key

1. Check `~/.hermes/.env` for `OPENROUTER_API_KEY` **without printing the secret**. Report only: missing / commented / set (length only).
2. If missing or commented: walk Michael to https://openrouter.ai/keys. He pastes the key **into chat once**, or he edits `.env` himself. You may write it to `~/.hermes/.env` as `OPENROUTER_API_KEY=...` (uncomment if needed). Never echo it back. Never git-add `.env`.
3. Confirm specialists stay on **paid** `deepseek/deepseek-chat-v3-0324` — no `:free`.
4. Dry-run Ledger (must not print the key):

```bash
bash ~/carrier_hermes/scripts/api_watcher_heartbeat.sh
cat "$OBSIDIAN_VAULT_PATH/_agent/api_watcher/spend-state.json"
```

Expect `ok: true` and usage fields. If the key is absent, fail closed **without** setting `SPEND_HALT`.
5. Optional cheap ping (one word):

```bash
hermes -z "Reply with the single word PONG." --provider openrouter -m deepseek/deepseek-chat-v3-0324
```

6. Recopy heartbeat into cron scripts dir if you changed the repo copy:

```bash
cp -f ~/carrier_hermes/scripts/api_watcher_heartbeat.sh ~/.hermes/scripts/api_watcher_heartbeat.sh
```

### B. Discord IDs

Frozen names (do **not** invent IDs):

| Role | Channel |
|---|---|
| Inbound / Helm home | server default / DM as configured |
| Quill drafts | `#drafts` |
| Vigil + Ledger | `#alerts` |
| Scout tips | `#fleet` |

1. Ask Michael to open Discord → each channel → Copy Channel ID (Developer Mode). He can paste IDs or you may read them from an already-configured gateway if they are already in Hermes config — still confirm with him before writing.
2. Fill **only** IDs he provided into `~/carrier_hermes/docs/DISCORD_CHANNELS.md`.
3. Optional: if he has an `#alerts` webhook, set `CARRIER_ALERTS_WEBHOOK` in `~/.hermes/.env` (never commit).
4. Check current Discord gateway: Helm-only inbound. Do not turn Vigil/Ledger/other bots into user-facing Discord bots unless he asks.
5. Commit + push **only** the IDs file (and nothing secret):

```bash
cd ~/carrier_hermes
git add docs/DISCORD_CHANNELS.md
git commit -m "docs: fill Discord channel IDs for drafts/alerts/fleet"
git push origin main
```

Skip the commit if any ID cell is still empty.

## Done when

- [ ] spend-state.json `ok: true` **or** Michael declined to add a key and that is written down
- [ ] DeepSeek ping PONG **or** explicitly skipped
- [ ] DISCORD_CHANNELS.md has real IDs **or** Michael deferred and the file is unchanged
- [ ] No secrets in git

## Report back

Four lines: OpenRouter status, Ledger `ok`, Discord IDs filled (yes/no/which), commit SHA if any.
