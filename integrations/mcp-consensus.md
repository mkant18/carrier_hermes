# Integration — Consensus MCP (research papers)

**Status:** **ADOPT (draft)** — not production-enabled until Helm OAuth grant  
**Phase:** ECO MCP-01 (2026-08-25)  
**Endpoint:** `https://mcp.consensus.app/mcp`  
**Eval artifact:** `_agent/coding/mcp/MCP_CANDIDATES.md`

## Scope

| | |
|---|---|
| Allowed bot_ids | `research_agent` (Probe), `hermes_ai_explorer` (Chart) only |
| Denied | All Command/Lt/Ops/Knowledge writers, Mate, watchers, Helm domain MCP |
| Tools | Read-only paper search (`search`) — no write tools |
| Auth | OAuth or enterprise Bearer via Hermes auth — **LockBox / Helm HANDSHAKE**; never commit tokens |

## Why draft only

Permanent enablement needs operator OAuth on the named bot homes. Chart evaluated the server and drafted YAML; Mate DOC pass documents the decision without flipping live configs.

## Sample shape (do not paste secrets)

```yaml
# bot_ids: [research_agent, hermes_ai_explorer] only
mcp_servers:
  consensus:
    enabled: true
    url: https://mcp.consensus.app/mcp
    auth: oauth
    # tools: prefer include [search] if schema exposes names
```

## Related REJECT / DEFER (same pass)

| MCP | Verdict |
|---|---|
| Obsidian Local REST API MCP | **REJECT** fleet — keep OSB stdio MCP |
| Granola MCP | **DEFER** — browser OAuth only |
| Monarch as MCP | **DEFER** — Purse stays narrow terminal |

## Apply path

After Helm grant: Wrench issues verify packet → Mate enables on Probe/Chart only → smoke from `_agent/coding/mcp/SMOKE_MCP.md` → rollback if not approved permanent.
