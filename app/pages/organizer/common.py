from __future__ import annotations

from pathlib import Path
from typing import Any

from app.constants import CLIENT_INDEX_JSON, DATA_DIR
from app.core.numbers import exact_native_integer
from app.storage import normalize_key, read_json
from app.ui.unity_palette import UNITY_ORGANIZER_METRICS_PX

CLASS_ICON_DIRS = (
    DATA_DIR / "images" / "classes",
    DATA_DIR / "images" / "breeds",
    DATA_DIR / "images" / "misc" / "classes",
)
CLASS_ICON_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg", ".ico")
SESSION_SLOT_COUNT = 8
# Separate physical slot placement from the shared compact character order.
KEY_SESSION_SLOT_ASSIGNMENTS = "__organizer_slot_assignments__"
WINDOW_EVENT_DEBOUNCE_MS = 80
RELEASE_RETRY_DELAYS_MS = (200, 500, 1000, 2000)
CARD_PADDING = UNITY_ORGANIZER_METRICS_PX["card_padding"]
CARD_SPACING = UNITY_ORGANIZER_METRICS_PX["card_spacing"]
BUTTON_HEIGHT = UNITY_ORGANIZER_METRICS_PX["button_height"]
INPUT_HEIGHT = UNITY_ORGANIZER_METRICS_PX["input_height"]
KEY_BADGE_HEIGHT = UNITY_ORGANIZER_METRICS_PX["key_badge_height"]
KEY_BADGE_MIN_WIDTH = UNITY_ORGANIZER_METRICS_PX["key_badge_min_width"]
FAVORITE_CHIP_HEIGHT = UNITY_ORGANIZER_METRICS_PX["favorite_chip_height"]
CHARACTER_SLOT_HEIGHT = UNITY_ORGANIZER_METRICS_PX["character_slot_height"]
STOP_BUTTON_HEIGHT = UNITY_ORGANIZER_METRICS_PX["stop_button_height"]

DOFUS_CLASS_DEFINITIONS = {
    "feca": {"id": 1, "label": "Feca", "aliases": ("feca", "féca")},
    "osamodas": {"id": 2, "label": "Osamodas", "aliases": ("osamodas",)},
    "enutrof": {"id": 3, "label": "Enutrof", "aliases": ("enutrof",)},
    "sram": {"id": 4, "label": "Sram", "aliases": ("sram",)},
    "xelor": {"id": 5, "label": "Xelor", "aliases": ("xelor", "xélor")},
    "ecaflip": {"id": 6, "label": "Ecaflip", "aliases": ("ecaflip",)},
    "eniripsa": {"id": 7, "label": "Eniripsa", "aliases": ("eniripsa",)},
    "iop": {"id": 8, "label": "Iop", "aliases": ("iop",)},
    "cra": {"id": 9, "label": "Cra", "aliases": ("cra", "crâ")},
    "sadida": {"id": 10, "label": "Sadida", "aliases": ("sadida",)},
    "sacrieur": {"id": 11, "label": "Sacrieur", "aliases": ("sacrieur",)},
    "pandawa": {"id": 12, "label": "Pandawa", "aliases": ("pandawa",)},
    "roublard": {"id": 13, "label": "Roublard", "aliases": ("roublard",)},
    "zobal": {"id": 14, "label": "Zobal", "aliases": ("zobal",)},
    "steamer": {"id": 15, "label": "Steamer", "aliases": ("steamer",)},
    "eliotrope": {"id": 16, "label": "Eliotrope", "aliases": ("eliotrope", "éliotrope")},
    "huppermage": {"id": 17, "label": "Huppermage", "aliases": ("huppermage",)},
    "ouginak": {"id": 18, "label": "Ouginak", "aliases": ("ouginak",)},
    "forgelance": {"id": 20, "label": "Forgelance", "aliases": ("forgelance",)},
}


def empty_session_slot() -> dict[str, Any]:
    return {"nom": "", "hwnd": 0, "_empty_slot": True}


def client_slot_hotkey_key(slot_index: int) -> str:
    return f"__raccourci_personnage_{max(1, int(slot_index) + 1)}__"


def session_name(session: dict[str, Any] | None) -> str:
    raw = (session or {}).get("nom", "")
    # A null/corrupt native title is not the character literally named
    # "None". Do not offer it as an Auto-groupe invitation.
    return raw.strip() if isinstance(raw, str) else ""


def _validated_session_number(raw: Any, maximum: int) -> int:
    # The Organizer's public missing-window sentinel remains zero.
    return exact_native_integer(raw, maximum) or 0


def session_hwnd(session: dict[str, Any] | None) -> int:
    return _validated_session_number(
        (session or {}).get("hwnd", 0), 2**64 - 1,
    )


def session_pid(session: dict[str, Any] | None) -> int:
    return _validated_session_number(
        (session or {}).get("pid", 0), 2**32 - 1,
    )


def session_is_empty(session: dict[str, Any] | None) -> bool:
    return bool((session or {}).get("_empty_slot")) or not session_name(session) or session_hwnd(session) <= 0


def session_is_detected(session: dict[str, Any] | None) -> bool:
    return bool(session_name(session) and session_hwnd(session) > 0 and not (session or {}).get("_empty_slot"))


def dofus_class_key_from_window_name(value: Any) -> str | None:
    tokens = set(normalize_key(value).split("_"))
    if not tokens:
        return None
    for class_key, definition in DOFUS_CLASS_DEFINITIONS.items():
        for alias in definition["aliases"]:
            if normalize_key(alias) in tokens:
                return class_key
    return None


def dofus_class_key_for_character_name(value: Any) -> str | None:
    character_key = normalize_key(value)
    if not character_key:
        return None
    return class_key_from_client_index(value, read_json(CLIENT_INDEX_JSON, {"clients": []}))


def client_class_candidates(payload: object) -> dict[str, set[str]]:
    """One cosmetic metadata projection for direct and cached class lookup."""
    candidates: dict[str, set[str]] = {}
    clients = payload.get("clients", []) if isinstance(payload, dict) else []
    for client in clients if isinstance(clients, list) else []:
        if not isinstance(client, dict):
            continue
        name = normalize_key(client.get("character_name"))
        if not name:
            continue
        class_key = normalize_key(client.get("class_key"))
        if class_key not in DOFUS_CLASS_DEFINITIONS:
            class_key = dofus_class_key_from_window_name(client.get("name")) or ""
        if class_key:
            candidates.setdefault(name, set()).add(class_key)
    return candidates


def class_key_from_client_index(value: Any, payload: object) -> str | None:
    """Resolve only unambiguous class metadata from an explicit index."""
    character_key = normalize_key(value)
    if not character_key:
        return None
    matches = client_class_candidates(payload).get(character_key, set())
    return next(iter(matches)) if len(matches) == 1 else None


def class_icon_candidates(
    class_key: str, *, directories=None, extensions=None,
) -> list[Path]:
    directories = CLASS_ICON_DIRS if directories is None else directories
    extensions = CLASS_ICON_EXTENSIONS if extensions is None else extensions
    definition = DOFUS_CLASS_DEFINITIONS.get(class_key)
    if not definition:
        return []
    class_id = definition["id"]
    stems: list[str] = []
    for value in (class_key, definition["label"], *definition["aliases"]):
        key = normalize_key(value)
        if key and key not in stems:
            stems.append(key)
    stems.extend([f"symbol_{class_id}", f"logo_transparent_{class_id}", f"class_{class_key}"])
    candidates: list[Path] = []
    for directory in directories:
        for stem in stems:
            for extension in extensions:
                candidates.append(directory / f"{stem}{extension}")
    return candidates


def class_icon_path_for_window_name(value: Any) -> Path | None:
    class_key = dofus_class_key_from_window_name(value) or dofus_class_key_for_character_name(value)
    if not class_key:
        return None
    for path in class_icon_candidates(class_key):
        if path.exists():
            return path
    return None
