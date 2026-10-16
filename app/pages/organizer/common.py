from __future__ import annotations

from pathlib import Path
from typing import Any

from app.constants import CLIENT_INDEX_JSON, DATA_DIR
from app.storage import normalize_key, read_json

CLASS_ICON_DIRS = (
    DATA_DIR / "images" / "classes",
    DATA_DIR / "images" / "breeds",
    DATA_DIR / "images" / "misc" / "classes",
)
CLASS_ICON_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg", ".ico")
SESSION_SLOT_COUNT = 8
WINDOW_EVENT_DEBOUNCE_MS = 80
RELEASE_RETRY_DELAYS_MS = (200, 500, 1000, 2000)
CARD_PADDING = 12
CARD_SPACING = 10
BUTTON_HEIGHT = 30
INPUT_HEIGHT = 32
KEY_BADGE_HEIGHT = 22
KEY_BADGE_MIN_WIDTH = 34
FAVORITE_CHIP_HEIGHT = 28
CHARACTER_SLOT_HEIGHT = 36
STOP_BUTTON_HEIGHT = 34

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
    return str((session or {}).get("nom", "")).strip()


def session_hwnd(session: dict[str, Any] | None) -> int:
    try:
        return int((session or {}).get("hwnd", 0))
    except (TypeError, ValueError):
        return 0


def session_pid(session: dict[str, Any] | None) -> int:
    try:
        return int((session or {}).get("pid", 0))
    except (TypeError, ValueError):
        return 0


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
    payload = read_json(CLIENT_INDEX_JSON, {"clients": []})
    clients = payload.get("clients", []) if isinstance(payload, dict) else []
    if not isinstance(clients, list):
        return None

    matches: set[str] = set()
    for client in clients:
        if not isinstance(client, dict):
            continue
        display_name = str(client.get("character_name") or "").strip()
        if normalize_key(display_name) != character_key:
            continue
        explicit_class = normalize_key(client.get("class_key"))
        if explicit_class in DOFUS_CLASS_DEFINITIONS:
            matches.add(explicit_class)
            continue
        inferred_class = dofus_class_key_from_window_name(client.get("name"))
        if inferred_class:
            matches.add(inferred_class)
    if len(matches) != 1:
        return None
    return next(iter(matches))


def class_icon_candidates(class_key: str) -> list[Path]:
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
    for directory in CLASS_ICON_DIRS:
        for stem in stems:
            for extension in CLASS_ICON_EXTENSIONS:
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
