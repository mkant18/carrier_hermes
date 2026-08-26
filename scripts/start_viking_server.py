#!/usr/bin/env python3
"""
start_viking_server.py - Start the OpenViking FastAPI server for carrier_hermes.

This script starts a FastAPI/uvicorn server that proxies the full 15-tool
OpenViking MCP surface. The carrier-viking plugin will automatically use this
server when it's running at localhost:1933.

Architecture:
  - If OpenViking is installed from source (C:/Users/micha/OpenViking), it
    uses the real OpenViking server.
  - If not available, it starts a carrier-viking local FastAPI server that
    wraps the SQLite+BM25 implementation.

Usage:
  python scripts/start_viking_server.py

Logs to: C:/Users/micha/AppData/Local/hermes/carrier/logs/viking.log
Port: 1933
"""

import logging
import os
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
HERMES_HOME = Path.home() / "AppData" / "Local" / "hermes"
CARRIER_HOME = HERMES_HOME / "carrier"
LOG_PATH = CARRIER_HOME / "logs" / "viking.log"
MEMORY_ROOT = CARRIER_HOME / "viking_memory"
VIKING_CONFIG = CARRIER_HOME / "viking_config.yaml"
OPENVIKING_SRC = Path.home() / "OpenViking"

# ── Create required directories ─────────────────────────────────────────────────
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
MEMORY_ROOT.mkdir(parents=True, exist_ok=True)

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
    ],
)
logger = logging.getLogger("carrier.viking.server")

# ── Set environment for carrier-viking plugin ──────────────────────────────────
os.environ["VIKING_MEMORY_DB_PATH"] = str(MEMORY_ROOT / "memories.db")
os.environ.setdefault("HERMES_BOT_ID", "carrier-server")


def try_real_openviking() -> bool:
    """Attempt to start the real OpenViking server from source."""
    if not OPENVIKING_SRC.exists():
        return False

    logger.info("Found OpenViking source at %s — attempting to start real server", OPENVIKING_SRC)

    # Add OpenViking to Python path
    if str(OPENVIKING_SRC) not in sys.path:
        sys.path.insert(0, str(OPENVIKING_SRC))

    try:
        from openviking.server import run_server  # type: ignore
        logger.info("Starting real OpenViking server on port 1933...")
        run_server(port=1933, config_path=str(VIKING_CONFIG))
        return True
    except ImportError as e:
        logger.warning("OpenViking server import failed (Rust extension required): %s", e)
        return False
    except Exception as e:
        logger.warning("OpenViking server startup failed: %s", e)
        return False


def start_local_fastapi_server():
    """
    Start the local carrier-viking FastAPI server.
    Provides the full 15-tool MCP surface backed by SQLite+BM25.
    """
    logger.info("Starting carrier-viking local FastAPI server on port 1933")

    try:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel
    except ImportError as e:
        logger.error("FastAPI/uvicorn not available: %s", e)
        sys.exit(1)

    # Import carrier-viking plugin
    plugin_path = HERMES_HOME / "plugins" / "carrier-viking"
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path.parent))

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "carrier_viking",
            str(plugin_path / "__init__.py"),
        )
        assert spec is not None and spec.loader is not None, "Failed to load carrier_viking spec"
        viking = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(viking)  # type: ignore[union-attr]
    except Exception as e:
        logger.error("Failed to load carrier-viking plugin: %s", e)
        sys.exit(1)

    app = FastAPI(
        title="carrier-viking OpenViking-compatible memory server",
        description="Persistent memory for carrier_hermes bots. Full 15-tool surface.",
        version="2.0.0",
    )

    # Health endpoint (required by watchdog + client)
    @app.get("/health")
    async def health_check():
        return JSONResponse({
            "status": "ok",
            "server": "carrier-viking-local",
            "port": 1933,
            "backend": "bm25" if viking._HAS_BM25 else "tfidf",
            "db_path": str(viking._db_path()),
        })

    # Generic tool dispatcher for MCP proxy calls
    class ToolRequest(BaseModel):
        model_config = {"extra": "allow"}

    def _make_endpoint(fn, fn_name: str):
        async def endpoint(req: ToolRequest):
            kwargs = req.model_dump(exclude_none=True)
            try:
                result = fn(**kwargs)
                return JSONResponse(result)
            except Exception as e:
                logger.exception("Tool %s error: %s", fn_name, e)
                return JSONResponse({"error": str(e)}, status_code=500)
        endpoint.__name__ = f"tool_{fn_name}"
        return endpoint

    # Register all 15 tools
    tool_map = {
        "remember":         viking.remember,
        "recall":           viking.recall,
        "forget":           viking.forget,
        "list_memories":    viking.list_memories,
        "viking_stats":     viking.viking_stats,
        "record_experience": viking.record_experience,
        "commit_session":   viking.commit_session,
        "search_memories":  viking.search_memories,
        "find":             viking.find,
        "search":           viking.search,
        "read":             viking.read,
        "write":            viking.write,
        "edit":             viking.edit,
        "list_uris":        viking.list_uris,
        "tree":             viking.tree,
        "add_resource":     viking.add_resource,
        "grep":             viking.grep,
        "glob":             viking.glob,
        "list_watches":     viking.list_watches,
        "cancel_watch":     viking.cancel_watch,
        "health":           viking.health,
    }

    for name, fn in tool_map.items():
        endpoint = _make_endpoint(fn, name)
        app.add_api_route(
            f"/mcp/tools/{name}",
            endpoint,
            methods=["POST"],
            name=name,
            summary=f"Viking tool: {name}",
        )

    logger.info("carrier-viking server ready. Tools: %s", sorted(tool_map.keys()))
    logger.info("Health: http://localhost:1933/health")
    logger.info("Logging to: %s", LOG_PATH)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=1933,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("carrier-viking server starting up...")
    logger.info("Memory root: %s", MEMORY_ROOT)
    logger.info("Config: %s", VIKING_CONFIG)

    # Try real OpenViking first, fall back to local FastAPI
    if not try_real_openviking():
        start_local_fastapi_server()
