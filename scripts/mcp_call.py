#!/usr/bin/env python3
"""
mcp_call.py — invoke a single MCP tool through a Hermes profile's configured
MCP server, over stdio, and print the JSON result. Fills the gap that
`hermes mcp` has no `call` subcommand.

It reads the server definition (command/args/env + tools.exclude) straight from
the profile's config.yaml, so the SAME server config and the SAME tool-exclusion
policy the agent sees are enforced here: a call to an excluded tool is refused.

Usage:
  mcp_call.py --profile vault_librarian --server obsidian-second-brain \
      --tool obsidian_search --args '{"query":"Harvard Law","limit":3}'

  # list the tools available to that home (after exclusions):
  mcp_call.py --profile vault_librarian --server obsidian-second-brain --list

Requires the `mcp` client lib (present in the Hermes venv). Run with the Hermes
venv python. No secrets printed.
"""
from __future__ import annotations
import argparse, asyncio, json, os, sys
from pathlib import Path
import yaml

HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))


def load_server(profile: str, server: str) -> tuple[dict, set[str]]:
    cfg_path = HOME / "profiles" / profile / "config.yaml"
    if not cfg_path.exists():
        # fall back to default home config
        cfg_path = HOME / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    servers = (cfg.get("mcp_servers") or {})
    if server not in servers:
        raise SystemExit(f"mcp_call: server '{server}' not configured on profile '{profile}'")
    s = servers[server]
    if s.get("enabled") is False:
        raise SystemExit(f"mcp_call: server '{server}' is disabled on '{profile}'")
    excluded = set(((s.get("tools") or {}).get("exclude")) or [])
    return s, excluded


async def run(server_def: dict, excluded: set[str], tool: str | None, args: dict, do_list: bool):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command = server_def.get("command")
    cmd_args = list(server_def.get("args") or [])
    env = dict(os.environ)
    env.update({k: str(v) for k, v in (server_def.get("env") or {}).items()})

    params = StdioServerParameters(command=command, args=cmd_args, env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            available = [t.name for t in tools.tools if t.name not in excluded]

            if do_list:
                print(json.dumps({"profile_tools": available,
                                  "excluded": sorted(excluded)}, indent=2))
                return

            if tool is None:
                raise SystemExit("mcp_call: --tool required (or use --list)")
            if tool in excluded:
                raise SystemExit(f"mcp_call: tool '{tool}' is EXCLUDED on this profile (policy) — refusing")
            if tool not in [t.name for t in tools.tools]:
                raise SystemExit(f"mcp_call: tool '{tool}' not found; available: {available}")

            result = await session.call_tool(tool, args)
            # Collect text content blocks
            out = []
            for block in result.content:
                txt = getattr(block, "text", None)
                out.append(txt if txt is not None else str(block))
            print("\n".join(out))


def main():
    ap = argparse.ArgumentParser(description="Call an MCP tool through a Hermes profile's server config")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--server", required=True)
    ap.add_argument("--tool")
    ap.add_argument("--args", default="{}", help="JSON object of tool arguments")
    ap.add_argument("--list", action="store_true", help="list tools available to this profile")
    a = ap.parse_args()

    try:
        args = json.loads(a.args)
        if not isinstance(args, dict):
            raise ValueError("must be a JSON object")
    except Exception as e:
        raise SystemExit(f"mcp_call: --args must be a JSON object: {e}")

    server_def, excluded = load_server(a.profile, a.server)
    asyncio.run(run(server_def, excluded, a.tool, args, a.list))


if __name__ == "__main__":
    main()
