#!/usr/bin/env python3
"""
wire_osb_mcp.py — wire the obsidian-second-brain MCP server into the Carrier
Hermes fleet with the correct per-home tool policy (integrations/obsidian-second-brain.md).

Read-only homes get the 5 write tools EXCLUDED. Clerk (obsidian_archivist) is the
only home with write tools enabled (used under trust_override: intake_enabled).

Idempotent: rewrites the mcp_servers.obsidian-second-brain block each run.
Never prints secrets. Uses the Hermes venv python (has PyYAML).

Usage:
  <venv-python> wire_osb_mcp.py
"""
from __future__ import annotations
import os
from pathlib import Path
import yaml

HOME = Path(r"C:\Users\micha\AppData\Local\hermes")
PROFILES = HOME / "profiles"
VAULT = os.environ.get("OBSIDIAN_VAULT_PATH", r"C:\Users\micha\Documents\Obsidian Vault")
SERVER = r"C:\Users\micha\obsidian-second-brain\integrations\obsidian-mcp-server\server.py"

WRITE_TOOLS = [
    "obsidian_save_note",
    "obsidian_capture",
    "obsidian_update_note",
    "obsidian_replace_text",
    "obsidian_move_note",
]

# Homes that read the vault via OSB MCP (write tools excluded).
READ_ONLY = ["vault_librarian", "hermes_ai_explorer", "chief_of_staff",
             "knowledge_lt", "email_drafter", "research_agent"]
# Clerk: full write tools on this home only (intake gate).
WRITE_HOME = ["obsidian_archivist"]


def server_block(exclude_writes: bool) -> dict:
    block = {
        "enabled": True,
        "command": "uv",
        "args": [
            "run", "--no-project", "--with", "mcp<2",
            "python", SERVER,
        ],
        "env": {"OBSIDIAN_VAULT_PATH": VAULT},
    }
    if exclude_writes:
        block["tools"] = {"exclude": list(WRITE_TOOLS)}
    return block


def wire(profile: str, exclude_writes: bool):
    cfg_path = PROFILES / profile / "config.yaml"
    cfg = {}
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    mcp = cfg.setdefault("mcp_servers", {})
    mcp["obsidian-second-brain"] = server_block(exclude_writes)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False), encoding="utf-8")
    mode = "READ-ONLY (writes excluded)" if exclude_writes else "READ+WRITE (Clerk intake)"
    print(f"  {profile:20} {mode}")


def main():
    print(f"vault:  {VAULT}\nserver: {SERVER}\n")
    for p in READ_ONLY:
        wire(p, exclude_writes=True)
    for p in WRITE_HOME:
        wire(p, exclude_writes=False)
    print("\nOSB MCP wired. Restart affected serve/gateway to load.")


if __name__ == "__main__":
    main()
