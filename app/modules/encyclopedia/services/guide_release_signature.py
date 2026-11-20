"""Canonical Guide step digest shared by portable reward and route manifests."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def guide_steps_sha256(guide: Any) -> str:
    """Hash ordered, authored Guide step identities without user progress."""
    steps = [
        (
            str(getattr(step, "id", "") or ""),
            str(getattr(step, "step_type", "") or ""),
            str(getattr(step, "entity_id", "") or ""),
            int(getattr(step, "order", 0) or 0),
        )
        for step in getattr(guide, "required_steps", ()) or ()
    ]
    return hashlib.sha256(
        json.dumps(steps, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
