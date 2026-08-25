# Integration — Consensus MCP (research papers)

**Status:** **ADOPT (draft)** — not production-enabled until Helm OAuth grant  
**Phase:** ECO MCP-01 (2026-08-25) — cards t_08b88b53 (Chart) / t_8ba4a9be (Mate)  
**Endpoint:** `https://mcp.consensus.app/mcp`  
**Eval artifacts:** `_agent/coding/mcp/POLICY.md`, `samples/consensus_recon.yaml`, Chart `MCP_CANDIDATES.md`

## Scope

| | |
|---|---|
| Allowed bot_ids | `research_agent` (Probe), `hermes_ai_explorer` (Chart) only |
| Denied | All Command/Lt/Ops/Knowledge writers, Mate, watchers, Helm domain MCP |
| Tools | Read-only paper search (`search`) — no write tools |
| Auth | OAuth via Hermes after Helm HANDSHAKE — **LockBox path**; never commit tokens |

## Why draft only

Permanent enablement needs operator OAuth on the named bot homes. Chart researched; Mate filed POLICY + samples and OSB throwaway smoke. DOC-01 documents the decision without flipping live configs.

## Sample shape (do not paste secrets)

Canonical draft: `_agent/coding/mcp/samples/consensus_recon.yaml` (`enabled: false` until grant).

```yaml
# bot_ids: [research_agent, hermes_ai_explorer] only
mcp_servers:
  consensus:
    enabled: false
    url: https://mcp.consensus.app/mcp
    auth: oauth
    tools:
      include:
        - search
```

## Related REJECT / DEFER (same pass)

| MCP | Verdict |
|---|---|
| Obsidian Local REST API MCP | **REJECT** fleet — keep OSB stdio MCP |
| Granola MCP | **DEFER** — browser OAuth only |
| Monarch as MCP | **DEFER** — Purse stays narrow terminal |
| OSB | **ADOPT** (existing) — see `integrations/obsidian-second-brain.md` + POLICY §2 |
| Todoist | **ADOPT keep + tighten** — Tasker only |

## Apply path

After Helm grant: Wrench issues verify packet → Mate enables on Probe/Chart only from sample → smoke → rollback if not approved permanent.
