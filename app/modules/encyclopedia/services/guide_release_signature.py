"""Canonical Guide step digest shared by portable reward and route manifests."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def guide_step_identity_rows(guide: Any) -> list[tuple[str, str, str, int]]:
    """One authored step projection for release manifests and local route caches."""
    return [
        (
            str(getattr(step, "id", "") or ""),
            str(getattr(step, "step_type", "") or ""),
            str(getattr(step, "entity_id", "") or ""),
            int(getattr(step, "order", 0) or 0),
        )
        for step in getattr(guide, "required_steps", ()) or ()
    ]


def guide_steps_sha256(guide: Any) -> str:
    """Hash ordered, authored Guide step identities without user progress."""
    return hashlib.sha256(
        json.dumps(guide_step_identity_rows(guide), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
