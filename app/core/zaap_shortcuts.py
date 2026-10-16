from __future__ import annotations

"""Lightweight Zaap shortcut reader shared by macro runtime and UI settings."""

from pathlib import Path
from typing import Any

from app.constants import ZAAP_SHORTCUTS_FILE
from app.core.json_store import read_json_resilient


def parse_unit_ratio(value: Any) -> float | None:
    try:
        ratio = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 0.0 <= ratio <= 1.0:
        return ratio
    return None


def zaap_ratios_from_payload(payload: dict[str, Any]) -> tuple[float, float] | None:
    button = payload.get("zaap_button")
    if not isinstance(button, dict):
        return None
    x_ratio = parse_unit_ratio(button.get("x_ratio"))
    y_ratio = parse_unit_ratio(button.get("y_ratio"))
    if x_ratio is None or y_ratio is None:
        return None
    return (x_ratio, y_ratio)


def update_zaap_shortcuts_field(path: Path, field: str, value: Any) -> None:
    """Atomically update one Zaap setting without overwriting its neighbours.

    Unlike an atomic replace alone, the coordinator lock also covers the
    read-modify-write operation across Atlas processes. Invalid existing JSON
    must never become a fresh empty settings document during a write.
    """
    from app.core.json_store import read_json_validated, write_json_atomic
    from app.core.progress_coordinator import coordinator_for

    if field not in {"zaap_favorites", "zaap_button"}:
        raise ValueError(f"Unsupported Zaap setting field: {field!r}")
    target = Path(path)
    coordinator = coordinator_for(target)
    with coordinator.lock:
        payload = read_json_validated(
            target,
            {},
            lambda raw: None if isinstance(raw, dict) else "Zaap settings root must be an object",
        )
        payload[field] = value
        write_json_atomic(target, payload)
        coordinator.mark_changed()


def read_zaap_button_ratios(payload: dict[str, Any] | None = None) -> tuple[float, float] | None:
    """Preserve the storage reader's non-profile JSON and ratio semantics."""
    if not isinstance(payload, dict):
        payload = read_json_resilient(ZAAP_SHORTCUTS_FILE, {})
    return zaap_ratios_from_payload(payload) if isinstance(payload, dict) else None
