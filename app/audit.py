"""Append-only audit trail. There is no update path and no delete path, by design.

The audit file IS the governance claim: every petition and every owner decision is
a new line, never a mutation of an old one. `PATCH /petition/{id}` appends a
*decision event*; it does not rewrite the request. That is why history cannot be
laundered here -- the code that could rewrite it does not exist. (Jim verifies this.)
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_AUDIT_PATH = Path(__file__).resolve().parents[1] / "data" / "audit.jsonl"
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_event(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append one immutable event; return it (with id + timestamp). Never overwrites."""
    event = {
        "audit_id": "aud_" + uuid.uuid4().hex[:12],
        "kind": kind,
        "timestamp": _now(),
        **payload,
    }
    _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    with _LOCK:
        # open in append mode only; there is deliberately no code path that seeks or truncates.
        with open(_AUDIT_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    return event


def read_all() -> list[dict[str, Any]]:
    """Return every event, newest first. Read-only."""
    if not _AUDIT_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    with open(_AUDIT_PATH, "r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                events.append(json.loads(raw))
    events.reverse()
    return events
