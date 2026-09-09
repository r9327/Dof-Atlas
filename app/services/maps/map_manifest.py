from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR, ROOT_DIR

MAP_CACHE_DIR = DATA_DIR / "cache" / "dofus_maps"
MAP_MANIFEST_PATH = MAP_CACHE_DIR / "manifest.json"
MAP_WORLDS_PATH = MAP_CACHE_DIR / "worlds.json"
MAP_IMAGES_DIR = MAP_CACHE_DIR / "images"
MAP_THUMBNAILS_DIR = MAP_CACHE_DIR / "thumbnails"
MAP_RAW_DIR = MAP_CACHE_DIR / "raw"

DEFAULT_WORLD_NAME = "Monde des Douze"
DEFAULT_WORLD_AREA = "Continent Amaknéen"

SUB_WORLD_NAMES: tuple[str, ...] = (
    "Incarnam",
    "Souterrain d'Astrub",
    "Labyrinthe du Minotoror",
    "Labyrinthe du Dragon Cochon",
    "Bibliothèque du Maître Corbac",
    "Cavernes des Givrefoux",
    "Canaux Méphitiques",
    "Entrailles de Brâkmar",
    "Village de la Canopée",
    "Château de Harebourg",
    "Enutrosor",
    "Srambad",
    "Xélorium",
    "Ecaflipus",
    "Profondeurs de Sufokia",
    "Pyramide Maudite",
    "Épaves Silencieuses",
    "Île de Pwâk",
    "Crouzkø",
    "Blessures de Guerre",
    "Royaume Corrompu",
    "Désert de Misère",
    "Galère de Servitude",
    "Wukin et Wukang",
    "Cauchemar",
    "Galeries d'Ereboria",
    "Caverne des Fungus",
    "Base Abyssale",
    "Osavora",
    "Dimension Obscure",
    "Sanctuaire des Dragoeufs",
    "Gouffre du Gigalodon",
    "Village des Brigandins",
    "Sanctuaire des Jardins éternels",
)

WORLD_MENU_NAMES: tuple[str, ...] = (DEFAULT_WORLD_NAME, *SUB_WORLD_NAMES)

VALID_MAP_SOURCES = {"local_dofus", "dofusdb_import", "generated_cache", "unknown"}
VALID_MAP_STATUSES = {"missing", "to_scan", "scanned", "image_ready", "needs_renderer"}


@dataclass(slots=True)
class MapEntry:
    id: str
    name: str
    world: str
    sub_world: str
    x: int | None = None
    y: int | None = None
    image_path: str | None = None
    source: str = "unknown"
    status: str = "missing"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MapEntry":
        source = str(payload.get("source") or "unknown")
        status = str(payload.get("status") or "missing")
        return cls(
            id=str(payload.get("id") or ""),
            name=str(payload.get("name") or ""),
            world=str(payload.get("world") or ""),
            sub_world=str(payload.get("sub_world") or ""),
            x=optional_int(payload.get("x")),
            y=optional_int(payload.get("y")),
            image_path=optional_image_path(payload.get("image_path")),
            source=source if source in VALID_MAP_SOURCES else "unknown",
            status=status if status in VALID_MAP_STATUSES else "missing",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "world": self.world,
            "sub_world": self.sub_world,
            "x": self.x,
            "y": self.y,
            "image_path": self.image_path,
            "source": self.source,
            "status": self.status,
        }


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def optional_image_path(value: Any) -> str | None:
    text = optional_str(value)
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        return None
    return text


def empty_manifest() -> dict[str, Any]:
    return {
        "version": 1,
        "complete": False,
        "maps": [],
        "metadata": {
            "source": "unknown",
            "status": "empty_cache",
            "note": "Extraction non exécutée. Les providers sont prêts, mais aucune donnée réelle n'a été importée.",
        },
    }


def worlds_payload() -> dict[str, Any]:
    return {
        "default_world": DEFAULT_WORLD_NAME,
        "excluded": [
            "Mappemondes",
            "Map monde",
            "Duty free",
            "Ecaflip City",
            "Domaine de Draconiros",
            "Temple céleste",
        ],
        "worlds": [
            {
                "name": DEFAULT_WORLD_NAME,
                "kind": "main",
                "default_area": DEFAULT_WORLD_AREA,
                "pinned": True,
            },
            *({"name": name, "kind": "sub_world"} for name in SUB_WORLD_NAMES),
        ],
    }


def ensure_cache_dirs() -> None:
    for path in (MAP_CACHE_DIR, MAP_IMAGES_DIR, MAP_THUMBNAILS_DIR, MAP_RAW_DIR):
        path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_manifest_file() -> bool:
    ensure_cache_dirs()
    if MAP_MANIFEST_PATH.exists():
        return False
    write_json(MAP_MANIFEST_PATH, empty_manifest())
    return True


def ensure_worlds_file() -> bool:
    ensure_cache_dirs()
    payload = worlds_payload()
    current = read_json(MAP_WORLDS_PATH, None)
    if current == payload:
        return False
    write_json(MAP_WORLDS_PATH, payload)
    return True


def ensure_cache_layout() -> None:
    ensure_cache_dirs()
    ensure_manifest_file()
    ensure_worlds_file()


def load_manifest() -> dict[str, Any]:
    return read_json(MAP_MANIFEST_PATH, empty_manifest())


def load_map_entries() -> list[MapEntry]:
    manifest = load_manifest()
    maps = manifest.get("maps", [])
    if not isinstance(maps, list):
        return []
    return [MapEntry.from_dict(row) for row in maps if isinstance(row, dict)]


def save_manifest(entries: list[MapEntry], *, source: str = "unknown", complete: bool = False) -> None:
    payload = empty_manifest()
    payload["complete"] = bool(complete)
    payload["metadata"] = {"source": source, "status": "ready" if entries else "empty_cache"}
    payload["maps"] = [entry.to_dict() for entry in entries]
    write_json(MAP_MANIFEST_PATH, payload)


def resolve_cache_path(path_text: str | None) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def image_exists(entry: MapEntry) -> bool:
    path = resolve_cache_path(entry.image_path)
    return bool(path and path.exists() and path.is_file())
