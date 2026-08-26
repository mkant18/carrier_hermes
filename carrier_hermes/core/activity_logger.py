from __future__ import annotations
import dataclasses
import json
import logging
import os
from pathlib import Path
from carrier_hermes.core.event_bus import HelmEventBus

logger = logging.getLogger("carrier_hermes.activity_logger")

LOG_ROOT = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "logs" / "activity"


class ActivityLogger:
    """Logs every RuntimeEvent as a JSON line to per-thread activity logs."""

    def __init__(self, bus: HelmEventBus, log_root: Path | None = None) -> None:
        self._root = Path(log_root) if log_root else LOG_ROOT
        bus.subscribe(["*"], self._handle)

    def _handle(self, event) -> None:
        try:
            thread_id = getattr(event, "thread_id", "unknown")
            self._root.mkdir(parents=True, exist_ok=True)
            log_path = self._root / f"{thread_id}.jsonl"
            row = dataclasses.asdict(event)
            row.pop("raw", None)  # don't log raw provider bytes
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except Exception as exc:
            logger.warning("ActivityLogger: failed to write log: %s", exc)
