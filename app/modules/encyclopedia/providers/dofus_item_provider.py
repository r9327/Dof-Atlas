from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR, ROOT_DIR
from app.modules.encyclopedia.models import DofusItem
from app.modules.encyclopedia.providers.achievement_provider import safe_int
from app.quest_catalog import array_value, localized_name, text_for
from app.quest_source_index import QuestSources, SelectedJsonValueMapping

DOFUS_TYPE_ID = 23
DOFUS_UNKNOWN_ICON = DATA_DIR / "encyclopedia" / "images" / "guides" / "dofus_unknown.svg"
GUIDE_ITEMS_INDEX = ROOT_DIR / ".cache" / "dofus_atlas" / "guide_items_index_v1.json"
_GUIDE_ITEMS_INDEX_SCHEMA = 1
_GUIDE_ITEM_KEYS = frozenset({"item_id", "reward_item_id", "illustration_item_id"})


def _guide_item_source_signature(data_dir: Path) -> list[list[object]]:
    paths = [
        data_dir / "items.json",
        data_dir / "item_types.json",
        data_dir / "effects.json",
        data_dir / "languages" / "fr.json",
    ]
    guides_dir = DATA_DIR / "encyclopedia" / "guides"
    if guides_dir.is_dir():
        paths.extend(sorted(guides_dir.glob("*.json")))
    signature: list[list[object]] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            signature.append([str(path.relative_to(ROOT_DIR)), -1, -1])
            continue
        try:
            label = str(path.relative_to(ROOT_DIR))
        except ValueError:
            label = str(path)
        signature.append([label.replace("\\", "/"), int(stat.st_size), int(stat.st_mtime_ns)])
    return signature


def _compact_item_payload(item: DofusItem) -> dict[str, object]:
    payload = asdict(item)
    raw = payload.get("raw")
    if isinstance(raw, dict):
        payload["raw"] = {
            key: raw[key]
            for key in ("id", "typeId", "nameId", "descriptionId", "iconId", "level")
            if key in raw
        }
    return payload


def _read_guide_items_index(
    *,
    data_dir: Path = RAW_QUEST_DATA_DIR,
    path: Path = GUIDE_ITEMS_INDEX,
) -> dict[int, dict[str, Any]] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("schema_version") or 0) != _GUIDE_ITEMS_INDEX_SCHEMA:
        return None
    if payload.get("source_signature") != _guide_item_source_signature(data_dir):
        return None
    rows = payload.get("items")
    if not isinstance(rows, dict):
        return None
    result: dict[int, dict[str, Any]] = {}
    for raw_id, row in rows.items():
        try:
            item_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if isinstance(row, dict):
            result[item_id] = row
    return result


def ensure_guide_items_index(
    *,
    data_dir: Path = RAW_QUEST_DATA_DIR,
    path: Path = GUIDE_ITEMS_INDEX,
) -> int:
    """Build the Guide-only item store during preload, never on Guide open."""

    cached = _read_guide_items_index(data_dir=data_dir, path=path)
    if cached is not None:
        return len(cached)
    if bool(getattr(sys, "frozen", False)):
        return 0
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.modules.encyclopedia.providers.dofus_item_provider",
            "--build-guide-index",
            str(path),
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=True,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("La génération de guide_items_index n'a produit aucun résultat")
    payload = json.loads(lines[-1])
    return max(0, int(payload.get("item_count") or 0))


def _collect_guide_item_ids() -> set[int]:
    guides_dir = DATA_DIR / "encyclopedia" / "guides"
    result: set[int] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in _GUIDE_ITEM_KEYS:
                    item_id = safe_int(child)
                    if item_id is not None:
                        result.add(int(item_id))
                elif key == "item_ids" and isinstance(child, list):
                    for raw_id in child:
                        item_id = safe_int(raw_id)
                        if item_id is not None:
                            result.add(int(item_id))
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    if guides_dir.is_dir():
        for guide_path in sorted(guides_dir.glob("*.json")):
            try:
                walk(json.loads(guide_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                continue
    return result

def _iter_doduda_refs(path: Path):
    """Yield bounded Doduda RefIds rows without a Python character-by-character scan."""

    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as stream:
        prefix = ""
        while True:
            chunk = stream.read(262144)
            if not chunk:
                return
            prefix += chunk
            marker = prefix.find('"RefIds"')
            if marker < 0:
                # RefIds lives near the header. Retain overlap for split keys.
                prefix = prefix[-32:]
                continue
            array_start = prefix.find("[", marker)
            if array_start < 0:
                continue
            buffer = prefix[array_start + 1 :]
            break

        offset = 0
        while True:
            while offset < len(buffer) and buffer[offset] in " \t\r\n,":
                offset += 1
            if offset >= len(buffer):
                buffer = stream.read(262144)
                offset = 0
                if not buffer:
                    return
                continue
            if buffer[offset] == "]":
                return

            try:
                # CPython's native JSON scanner decodes a single entry at once.
                # Unlike json.load, this never holds the full RefIds array.
                value, offset = decoder.raw_decode(buffer, offset)
            except json.JSONDecodeError as exc:
                chunk = stream.read(262144)
                if not chunk:
                    raise ValueError("Incomplete Doduda RefIds entry") from exc
                buffer = buffer[offset:] + chunk
                offset = 0
                continue

            if offset >= 262144:
                buffer = buffer[offset:]
                offset = 0
            if isinstance(value, dict):
                yield value


EXCLUDED_DOFUS_ITEM_IDS = frozenset(
    {
        7113,   # Dofawa
        15235,  # Dotruche
        20286,  # Dofus Argente Scintillant
        20833,  # Dofus Cacao
        20987,  # Dofus Cacao
        21186,  # Ancienne variante technique du Dofus Vulbis
        29134,  # Ancienne variante technique du Dofus Sylvestre
        29135,  # Dofus Verdoyant
        30356,  # Jyfus
    }
)


class DofusItemProvider:
    def __init__(self, data_dir: Path = RAW_QUEST_DATA_DIR) -> None:
        self.data_dir = data_dir
        self._loaded = False
        self._items: list[DofusItem] = []
        self._by_id: dict[int, DofusItem] = {}
        self._guide_index_rows: dict[int, dict[str, Any]] | None = None

    def load_all(self) -> list[DofusItem]:
        self._ensure_loaded()
        return list(self._items)

    def get_by_id(self, item_id: int | None) -> DofusItem | None:
        """Resolve one Guide item from the compact preload store."""

        if item_id is None:
            return None
        item_id = int(item_id)
        cached = self._by_id.get(item_id)
        if cached is not None:
            return cached
        if self._loaded:
            return None

        default_data_dir = Path(RAW_QUEST_DATA_DIR).resolve(strict=False)
        current_data_dir = Path(self.data_dir).resolve(strict=False)
        if current_data_dir == default_data_dir:
            row = self._guide_index_row(item_id)
            item = self._item_from_compact_row(row) if row is not None else None
            if item is None:
                # The compact index is the normal fast path. If preload was
                # skipped or the reconstructible index is stale, keep Guide
                # functional through the bounded byte-offset reader.
                item = self._load_one(item_id)
        else:
            # Focused tests/custom catalogues keep the generic indexed reader.
            item = self._load_one(item_id)
        if item is None:
            return None

        self._by_id[item_id] = item
        while len(self._by_id) > 32:
            oldest_id = next(iter(self._by_id))
            self._by_id.pop(oldest_id, None)
        return item

    def _guide_index_row(self, item_id: int) -> dict[str, Any] | None:
        if self._guide_index_rows is None:
            self._guide_index_rows = _read_guide_items_index(
                data_dir=self.data_dir,
                path=GUIDE_ITEMS_INDEX,
            ) or {}
        return self._guide_index_rows.get(int(item_id))

    @staticmethod
    def _item_from_compact_row(row: dict[str, Any] | None) -> DofusItem | None:
        if not isinstance(row, dict):
            return None
        item_id = safe_int(row.get("id"))
        if item_id is None:
            return None
        return DofusItem(
            id=int(item_id),
            original_id=safe_int(row.get("original_id"), int(item_id)) or int(item_id),
            name=str(row.get("name") or ""),
            level=safe_int(row.get("level")),
            type_id=safe_int(row.get("type_id"), 0) or 0,
            type_name=str(row.get("type_name") or ""),
            description=str(row.get("description") or ""),
            icon_id=safe_int(row.get("icon_id")),
            image_path=str(row.get("image_path") or ""),
            effects=tuple(str(value) for value in (row.get("effects") or ())),
            guide_id=str(row.get("guide_id") or ""),
            raw=dict(row.get("raw") or {}),
        )

    def _load_one(self, item_id: int) -> DofusItem | None:
        """Read one item through byte-offset indexes prepared by preload."""

        sources = QuestSources(ROOT_DIR / ".cache" / "dofus_atlas" / "achievement_sources_v1")
        try:
            items = sources.rows(self.data_dir / "items.json")
            try:
                row = items[int(item_id)]
            except KeyError:
                return None
            if not isinstance(row, dict):
                return None

            type_id = safe_int(row.get("typeId"), 0) or 0
            type_row: dict[str, Any] = {}
            try:
                candidate = sources.rows(self.data_dir / "item_types.json")[type_id]
                if isinstance(candidate, dict):
                    type_row = candidate
            except KeyError:
                pass

            entries = sources.mapping(
                self.data_dir / "languages" / "fr.json",
                "entries",
                required=True,
            )
            icon_id = safe_int(row.get("iconId"))
            return DofusItem(
                id=int(item_id),
                original_id=int(item_id),
                name=localized_name(row, entries, f"Objet {item_id}"),
                level=safe_int(row.get("level")),
                type_id=type_id,
                type_name=text_for(entries, type_row.get("nameId"), ""),
                description=text_for(entries, row.get("descriptionId"), ""),
                icon_id=icon_id,
                image_path=self._image_for_icon(icon_id),
                effects=(),
                raw={"id": int(item_id), "typeId": type_id},
            )
        finally:
            sources.close()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load()
        self._loaded = True

    def _load(self) -> None:
        """Keep monolithic Dofus JSON parsing outside Atlas' long-lived heap."""

        default_data_dir = Path(RAW_QUEST_DATA_DIR).resolve(strict=False)
        current_data_dir = Path(self.data_dir).resolve(strict=False)
        if current_data_dir == default_data_dir:
            compact_rows = _read_guide_items_index(
                data_dir=self.data_dir,
                path=GUIDE_ITEMS_INDEX,
            )
            if compact_rows:
                items = [
                    item
                    for row in compact_rows.values()
                    if (item := self._item_from_compact_row(row)) is not None
                    and item.type_id == DOFUS_TYPE_ID
                ]
                self._items = sorted(items, key=lambda item: (item.level or 0, item.name, item.id))
                self._by_id = {item.id: item for item in self._items}
                return

        main_spec = getattr(sys.modules.get("__main__"), "__spec__", None)
        main_name = str(getattr(main_spec, "name", "") or "")
        nested_compact_worker = "--dump-compact" in sys.argv and main_name != __name__
        if (
            bool(getattr(sys, "frozen", False))
            or self.data_dir != RAW_QUEST_DATA_DIR
            or nested_compact_worker
        ):
            # A compact provider worker is already disposable. Spawning another
            # Python process here only stacks both RSS values in the process tree.
            self._load_in_process()
            return

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.modules.encyclopedia.providers.dofus_item_provider",
                "--dump-compact",
            ],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=90,
            check=True,
        )
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("L'extraction des Dofus n'a produit aucun résultat")
        try:
            rows = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Résultat de l'extraction des Dofus invalide: {lines[-1]!r}"
            ) from exc
        if not isinstance(rows, list):
            raise RuntimeError("Résultat de l'extraction des Dofus invalide")

        items: list[DofusItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            items.append(
                DofusItem(
                    id=int(row["id"]),
                    original_id=int(row.get("original_id", row["id"])),
                    name=str(row.get("name") or ""),
                    level=safe_int(row.get("level")),
                    type_id=int(row.get("type_id", DOFUS_TYPE_ID)),
                    type_name=str(row.get("type_name") or "Dofus"),
                    description=str(row.get("description") or ""),
                    icon_id=safe_int(row.get("icon_id")),
                    image_path=str(row.get("image_path") or ""),
                    effects=tuple(str(value) for value in (row.get("effects") or ())),
                    guide_id=str(row.get("guide_id") or ""),
                    raw=dict(row.get("raw") or {}),
                )
            )
        self._items = sorted(items, key=lambda item: (item.level or 0, item.name, item.id))
        self._by_id = {item.id: item for item in self._items}

    def _load_in_process(
        self,
        *,
        extra_item_ids: set[int] | None = None,
    ) -> dict[int, DofusItem]:
        """Extract Dofus rows and optional Guide items in the same source pass."""

        # items.json is the largest source used here. Scan one RefIds entry at
        # a time so neither Atlas nor its disposable worker holds the monolithic
        # JSON text/object graph in memory. Guide warmup can request its handful
        # of extra items here so it never scans the source a third time.
        items_path = self.data_dir / "items.json"
        extra_ids = {int(value) for value in (extra_item_ids or ())}
        extra_rows: dict[int, dict[str, Any]] = {}
        dofus_rows: dict[int, dict[str, Any]] = {}
        effect_rids: set[int] = set()
        # Effect instances live in the same RefIds stream as items. Keep only
        # four scalar fields per candidate so one bounded pass can serve both
        # item discovery and later Dofus effect rendering.
        effect_candidates: dict[int, tuple[int, int, int, int]] = {}
        for ref in _iter_doduda_refs(items_path):
            data = ref.get("data")
            if not isinstance(data, dict):
                continue

            rid = safe_int(ref.get("rid"))
            effect_id = safe_int(data.get("effectId"))
            if rid is not None and effect_id is not None:
                effect_candidates[int(rid)] = (
                    int(effect_id),
                    safe_int(data.get("diceNum"), 0) or 0,
                    safe_int(data.get("diceSide"), 0) or 0,
                    safe_int(data.get("value"), 0) or 0,
                )

            item_id = safe_int(data.get("id"))
            if item_id is None:
                continue
            item_id = int(item_id)
            if item_id in extra_ids:
                extra_rows[item_id] = dict(data)
            if safe_int(data.get("typeId")) != DOFUS_TYPE_ID:
                continue
            if item_id in EXCLUDED_DOFUS_ITEM_IDS:
                continue
            dofus_rows[item_id] = dict(data)
            for effect_ref in array_value(data.get("possibleEffects")):
                if not isinstance(effect_ref, dict):
                    continue
                effect_rid = safe_int(effect_ref.get("rid"))
                if effect_rid is not None:
                    effect_rids.add(int(effect_rid))

        effect_instances: dict[int, dict[str, Any]] = {}
        for rid in effect_rids:
            compact = effect_candidates.get(int(rid))
            if compact is None:
                continue
            effect_id, dice_num, dice_side, value = compact
            effect_instances[int(rid)] = {
                "effectId": effect_id,
                "diceNum": dice_num,
                "diceSide": dice_side,
                "value": value,
            }
        del effect_candidates

        needed_type_ids = {DOFUS_TYPE_ID}
        needed_type_ids.update(
            safe_int(row.get("typeId"), 0) or 0
            for row in extra_rows.values()
        )
        type_rows: dict[int, dict[str, Any]] = {}
        for ref in _iter_doduda_refs(self.data_dir / "item_types.json"):
            data = ref.get("data")
            if not isinstance(data, dict):
                continue
            type_id = safe_int(data.get("id"))
            if type_id is None or int(type_id) not in needed_type_ids:
                continue
            type_rows[int(type_id)] = dict(data)
            if len(type_rows) >= len(needed_type_ids):
                break
        type_row = type_rows.get(DOFUS_TYPE_ID, {})

        needed_effect_ids = {
            effect_id
            for effect in effect_instances.values()
            if (effect_id := safe_int(effect.get("effectId"))) is not None
        }
        effect_rows: dict[int, dict[str, Any]] = {}
        if needed_effect_ids:
            for ref in _iter_doduda_refs(self.data_dir / "effects.json"):
                data = ref.get("data")
                if not isinstance(data, dict):
                    continue
                effect_id = safe_int(data.get("id"))
                if effect_id is not None and int(effect_id) in needed_effect_ids:
                    effect_rows[int(effect_id)] = dict(data)
                    if len(effect_rows) >= len(needed_effect_ids):
                        break
        # Reuse the durable language byte-offset cache produced by preload and
        # decode only translations referenced by the selected Dofus/effects.
        needed_entry_ids: set[str] = set()
        for row in (*dofus_rows.values(), *extra_rows.values()):
            for field in ("nameId", "descriptionId"):
                ident = safe_int(row.get(field))
                if ident is not None:
                    needed_entry_ids.add(str(ident))
        for row in type_rows.values():
            type_name_id = safe_int(row.get("nameId"))
            if type_name_id is not None:
                needed_entry_ids.add(str(type_name_id))
        for row in effect_rows.values():
            ident = safe_int(row.get("descriptionId"))
            if ident is not None:
                needed_entry_ids.add(str(ident))

        language_entries = SelectedJsonValueMapping(
            self.data_dir / "languages" / "fr.json",
            "entries",
            needed_entry_ids,
            required=True,
        )
        entries: dict[str, Any] = {
            ident: language_entries[ident]
            for ident in needed_entry_ids
            if ident in language_entries
        }
        language_entries.close()

        type_name = text_for(entries, type_row.get("nameId"), "Dofus")
        dofus_items: list[DofusItem] = []
        for item_id, row in dofus_rows.items():
            effect_rows_for_item = [
                effect_instances.get(int(rid))
                for effect_ref in array_value(row.get("possibleEffects"))
                if isinstance(effect_ref, dict)
                and (rid := safe_int(effect_ref.get("rid"))) is not None
            ]
            effect_labels = tuple(
                label
                for effect in effect_rows_for_item
                for label in [self._effect_label(effect, effect_rows, entries)]
                if label
            )
            icon_id = safe_int(row.get("iconId"))
            dofus_items.append(
                DofusItem(
                    id=item_id,
                    original_id=item_id,
                    name=localized_name(row, entries, f"Dofus {item_id}"),
                    level=safe_int(row.get("level")),
                    type_id=DOFUS_TYPE_ID,
                    type_name=type_name,
                    description=text_for(entries, row.get("descriptionId"), ""),
                    icon_id=icon_id,
                    image_path=self._image_for_icon(icon_id),
                    effects=effect_labels,
                    raw=dict(row),
                )
            )
        self._items = sorted(dofus_items, key=lambda item: (item.level or 0, item.name, item.id))
        self._by_id = {item.id: item for item in self._items}

        extra_items: dict[int, DofusItem] = {}
        for item_id, row in extra_rows.items():
            if item_id in dofus_rows:
                continue
            type_id = safe_int(row.get("typeId"), 0) or 0
            type_data = type_rows.get(type_id, {})
            icon_id = safe_int(row.get("iconId"))
            extra_items[item_id] = DofusItem(
                id=item_id,
                original_id=item_id,
                name=localized_name(row, entries, f"Objet {item_id}"),
                level=safe_int(row.get("level")),
                type_id=type_id,
                type_name=text_for(entries, type_data.get("nameId"), ""),
                description=text_for(entries, row.get("descriptionId"), ""),
                icon_id=icon_id,
                image_path=self._image_for_icon(icon_id),
                effects=(),
                raw={"id": item_id, "typeId": type_id},
            )
        return extra_items

    def _effect_label(
        self,
        effect: dict[str, Any] | None,
        effect_rows: dict[int, dict[str, Any]],
        entries: dict[str, Any],
    ) -> str:
        if not isinstance(effect, dict):
            return ""
        effect_id = safe_int(effect.get("effectId"))
        row = effect_rows.get(effect_id or -1, {})
        template = text_for(entries, row.get("descriptionId"), "")
        if not template:
            return ""
        dice = safe_int(effect.get("diceNum"), 0) or safe_int(effect.get("value"), 0) or 0
        side = safe_int(effect.get("diceSide"), 0) or 0
        return (
            template.replace("#1", str(dice))
            .replace("#2", str(side))
            .replace("#3", str(effect_id or ""))
            .replace("{{~1~2 à }}", " à " if side else "")
            .strip()
        )

    def _image_for_icon(self, icon_id: int | None) -> str:
        if icon_id is None:
            return str(DOFUS_UNKNOWN_ICON) if DOFUS_UNKNOWN_ICON.exists() else ""
        for folder in ("items", "resources", "archive/unmatched"):
            root = DATA_DIR / "images" / folder
            if not root.exists():
                continue
            for suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
                path = root / f"{icon_id}{suffix}"
                if path.exists():
                    return str(path)
        return str(DOFUS_UNKNOWN_ICON) if DOFUS_UNKNOWN_ICON.exists() else ""

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default


def _dump_compact_default_items() -> int:
    provider = DofusItemProvider(RAW_QUEST_DATA_DIR)
    provider._load_in_process()
    print(json.dumps([asdict(item) for item in provider._items], ensure_ascii=False))
    return 0


def _build_guide_items_index(path: Path) -> int:
    provider = DofusItemProvider(RAW_QUEST_DATA_DIR)
    requested = _collect_guide_item_ids()
    extra_items = provider._load_in_process(extra_item_ids=requested)
    items: dict[int, DofusItem] = {item.id: item for item in provider._items}
    items.update(extra_items)

    payload = {
        "schema_version": _GUIDE_ITEMS_INDEX_SCHEMA,
        "source_signature": _guide_item_source_signature(RAW_QUEST_DATA_DIR),
        "items": {
            str(item_id): _compact_item_payload(item)
            for item_id, item in sorted(items.items())
        },
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    print(
        json.dumps(
            {"item_count": len(items), "path": str(path)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


def _ensure_guide_items_index_cli() -> int:
    cached = _read_guide_items_index(data_dir=RAW_QUEST_DATA_DIR, path=GUIDE_ITEMS_INDEX)
    if cached is not None:
        print(json.dumps({"item_count": len(cached), "path": str(GUIDE_ITEMS_INDEX)}, ensure_ascii=False, separators=(",", ":")))
        return 0
    return _build_guide_items_index(GUIDE_ITEMS_INDEX)


if __name__ == "__main__":
    if "--ensure-guide-index" in sys.argv:
        raise SystemExit(_ensure_guide_items_index_cli())
    if "--build-guide-index" in sys.argv:
        try:
            target = Path(sys.argv[sys.argv.index("--build-guide-index") + 1])
        except (ValueError, IndexError):
            raise SystemExit(2)
        raise SystemExit(_build_guide_items_index(target))
    if "--dump-compact" in sys.argv:
        raise SystemExit(_dump_compact_default_items())


__all__ = [
    "DOFUS_UNKNOWN_ICON",
    "DofusItemProvider",
    "GUIDE_ITEMS_INDEX",
    "ensure_guide_items_index",
]
