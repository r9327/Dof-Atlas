"""Bounded, privacy-minimal local evidence for real Unity validation.

No packet payloads, window titles, character names, IDs, handles, PIDs,
tokens, filesystem paths or credentials are permitted in this journal.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.constants import LOG_DIR

_LOCK = threading.RLock()
_LAST: dict[str, str] = {}
_MAX_BYTES = 512 * 1024
_FIELDS = {
    "organizer_sessions": {
        "detected": int, "verified": int, "unverified": int,
        "primary": bool, "classes_verified": int,
    },
    "organizer_favorite": {
        "selected": bool, "rejected": bool, "verified": bool,
        "detected": int,
    },
    "network_status": {
        "running": bool, "calibrating": bool, "reason": str,
        "mapping_present": bool, "catchup_ready": bool,
        "completed": int, "journal_observed": int, "journal_verified": int,
    },
    "network_progress": {
        "changed": int, "activated": bool,
    },
    "shell_characters": {
        "known": int, "connected": int, "with_verified_class": int,
    },
}
_REASON_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


def record_validation(event: str, /, **fields: object) -> None:
    """Write changed, allowlisted status only; failure never blocks Atlas."""
    schema = _FIELDS.get(event)
    if schema is None:
        return
    values: dict[str, object] = {}
    for key, expected in schema.items():
        raw = fields.get(key)
        if expected is bool:
            values[key] = raw is True
        elif expected is int:
            values[key] = min(100000, max(0, raw)) if type(raw) is int else 0
        else:
            text = str(raw or "").lower()
            values[key] = text if _REASON_PATTERN.fullmatch(text) else "unclassified"
    snapshot = json.dumps({"event": event, **values}, sort_keys=True, separators=(",", ":"))
    with _LOCK:
        if _LAST.get(event) == snapshot:
            return
        path = Path(LOG_DIR) / "atlas_validation.jsonl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size >= _MAX_BYTES:
                path.replace(path.with_suffix(".jsonl.old"))
            entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "schema": 1, "event": event, **values}
            with path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
        except OSError:
            return
        _LAST[event] = snapshot
