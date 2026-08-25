# Obsidian Second Brain ↔ Carrier Hermes

Wire Michael's vault and the [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) stack into Hermes without violating Trust Level 0.

## Canonical vault

```text
OBSIDIAN_VAULT_PATH=/Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN
```

Also set in `~/.hermes/.env` so every profile inherits it.

## Two integration paths (use both)

| Path | What it is | Use for |
|---|---|---|
| **Native Hermes skills** | Built via `obsidian-second-brain` Hermes adapter → `~/.hermes/skills/obsidian-second-brain/` | Playbooks (ingest patterns, health, research helpers) |
| **MCP server** | `integrations/obsidian-mcp-server/server.py` via stdio | Bounded tools: search, read, health, backlinks, validate |

## Trust Level 0 policy (fleet)

Vault `CLAUDE.md` rules:

- READ any note
- WRITE only `_agent/**`
- Never edit/move/delete outside `_agent/`

**MCP tool filter for Hermes (recommended):**

- **Allow:** `obsidian_search`, `obsidian_read_note`, `obsidian_validate_note`, `obsidian_backlinks`, `obsidian_vault_health`, `obsidian_list_skills`, `obsidian_get_skill`
- **Exclude writes that target Inbox:** `obsidian_save_note`, `obsidian_capture`, `obsidian_update_note` until Trust Level is raised

Profiles that write: use file tools under `$OBSIDIAN_VAULT_PATH/_agent/...` only.

## Install skills (from OSB repo)

```bash
OSB_ROOT="$HOME/obsidian-second-brain"
cd "$OSB_ROOT"
bash scripts/build.sh --platform hermes   # if dist/hermes missing or stale

mkdir -p ~/.hermes/skills/obsidian-second-brain
cp -R dist/hermes/skills/.     ~/.hermes/skills/obsidian-second-brain/
cp -R dist/hermes/references   ~/.hermes/skills/obsidian-second-brain/references
cp -R dist/hermes/scripts      ~/.hermes/skills/obsidian-second-brain/scripts
cp -f dist/hermes/pyproject.toml ~/.hermes/skills/obsidian-second-brain/ 2>/dev/null || true
# optional scheduled blueprints (do not auto-arm):
# cp -R dist/hermes/optional-skills/. ~/.hermes/skills/obsidian-second-brain/
```

Python helpers must run as:

```bash
uv run --directory "$HOME/.hermes/skills/obsidian-second-brain" -m scripts.research.<name>
```

(not bare `uv run` from the vault cwd).

## Install MCP (Hermes)

```bash
export OBSIDIAN_VAULT_PATH="/Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN"

# Prefer hermes CLI when available:
hermes mcp add obsidian-second-brain \
  --command uv \
  --arg run --arg --with --arg 'mcp<2' \
  --arg python \
  --arg "$HOME/obsidian-second-brain/integrations/obsidian-mcp-server/server.py" \
  --env "OBSIDIAN_VAULT_PATH=$OBSIDIAN_VAULT_PATH"
```

Or patch `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  obsidian-second-brain:
    enabled: true
    command: uv
    args:
      - run
      - --with
      - mcp<2
      - python
      - /Users/michaelkanter/obsidian-second-brain/integrations/obsidian-mcp-server/server.py
    env:
      OBSIDIAN_VAULT_PATH: /Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN
    tools:
      exclude:
        - obsidian_save_note
        - obsidian_capture
        - obsidian_update_note
```

Verify:

```bash
hermes mcp list
hermes mcp test obsidian-second-brain
```

## Profiles that use OSB

| Profile | Access |
|---|---|
| vault_librarian (**Librarian**) | Query-out: OSB read/health + `_agent/librarian/` |
| obsidian_archivist (**Clerk**) | Intake-in: stage `_agent/archivist/`; OSB write tools **only** when intake enabled |
| hermes_ai_explorer (**Scout**) | Read vault + write `_agent/explorer/` |
| email_drafter (**Quill**) | May read People/ / contacts; write `_agent/drafts/` only |
| chief_of_staff (**Helm**) | No vault file tools; routes Librarian vs Clerk |
| research_agent (**Probe**) | Write `_agent/research/`; Clerk files keepers |

## _agent tree (create if missing)

```bash
VAULT="$OBSIDIAN_VAULT_PATH"
mkdir -p "$VAULT/_agent"/{email,drafts,calendar,todoist,research,watcher,api_watcher,librarian,archivist,explorer,state,audit,mailbox}
```

## Optional OSB crons

Do **not** arm OSB nightly/morning agents until Trust Level allows Inbox writes. Prefer explorer + librarian reports under `_agent/` first.
