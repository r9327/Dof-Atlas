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
from app.quest_catalog import array_value, doduda_rows, localized_name, read_json_file, text_for

DOFUS_TYPE_ID = 23
DOFUS_UNKNOWN_ICON = DATA_DIR / "encyclopedia" / "images" / "guides" / "dofus_unknown.svg"
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

    def load_all(self) -> list[DofusItem]:
        self._ensure_loaded()
        return list(self._items)

    def get_by_id(self, item_id: int | None) -> DofusItem | None:
        if item_id is None:
            return None
        self._ensure_loaded()
        return self._by_id.get(int(item_id))

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load()
        self._loaded = True

    def _load(self) -> None:
        """Keep monolithic Dofus JSON parsing outside Atlas' long-lived heap."""

        if bool(getattr(sys, "frozen", False)) or self.data_dir != RAW_QUEST_DATA_DIR:
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

    def _load_in_process(self) -> None:
        """Legacy extractor used only by the disposable helper or custom fixtures."""

        language = read_json_file(self.data_dir / "languages" / "fr.json", {"entries": {}})
        entries = language.get("entries", {}) if isinstance(language, dict) else {}
        if not isinstance(entries, dict):
            entries = {}
        item_payload = self._read_json(self.data_dir / "items.json", {})
        refs = (
            item_payload.get("references", {}).get("RefIds", [])
            if isinstance(item_payload, dict)
            else []
        )
        items: dict[int, dict[str, Any]] = {}
        item_refs: dict[int, dict[str, Any]] = {}
        for ref in refs if isinstance(refs, list) else ():
            if not isinstance(ref, dict):
                continue
            data = ref.get("data")
            if not isinstance(data, dict):
                continue
            rid = safe_int(ref.get("rid"))
            if rid is not None:
                item_refs[int(rid)] = data
            item_id = safe_int(data.get("id"))
            if item_id is not None:
                items[int(item_id)] = data
        item_types = doduda_rows(self.data_dir / "item_types.json")
        effects = doduda_rows(self.data_dir / "effects.json")
        type_row = item_types.get(DOFUS_TYPE_ID, {})
        type_name = text_for(entries, type_row.get("nameId"), "Dofus")
        dofus_items: list[DofusItem] = []
        for item_id, row in items.items():
            if safe_int(row.get("typeId")) != DOFUS_TYPE_ID:
                continue
            if item_id in EXCLUDED_DOFUS_ITEM_IDS:
                continue
            effect_rows = [
                item_refs.get(safe_int(ref.get("rid")))
                for ref in array_value(row.get("possibleEffects"))
                if isinstance(ref, dict)
            ]
            effect_labels = tuple(
                label
                for effect in effect_rows
                for label in [self._effect_label(effect, effects, entries)]
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


if __name__ == "__main__":
    if "--dump-compact" in sys.argv:
        raise SystemExit(_dump_compact_default_items())
