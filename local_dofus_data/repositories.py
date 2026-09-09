from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig
from .data_store import DataStore
from .utils import normalize_text


def _decode_json_fields(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    decoded = dict(row)
    for key in list(decoded):
        if key.endswith("_json") and isinstance(decoded[key], str):
            try:
                decoded[key] = json.loads(decoded[key])
            except Exception:
                decoded[key] = {}
    return decoded


def _legacy_item(row: dict[str, Any] | None, config: LocalDataConfig = DEFAULT_CONFIG) -> dict[str, Any] | None:
    if not row:
        return None
    image_path = row.get("image_path") or ""
    return {
        "id": row.get("id"),
        "id_dofus": row.get("ankama_id"),
        "ankama_id": row.get("ankama_id"),
        "gid": row.get("gid") or row.get("ankama_id"),
        "name": row.get("name_fr") or row.get("name_en") or "",
        "name_fr": row.get("name_fr") or "",
        "name_en": row.get("name_en") or "",
        "type": row.get("type") or "",
        "family": row.get("family") or row.get("category") or "",
        "category": row.get("category") or "",
        "level": row.get("level"),
        "image": _legacy_image_url_or_path(image_path),
        "image_path": image_path,
        "source": row.get("source") or "",
    }


def _legacy_image_url_or_path(image_path: str) -> str:
    if not image_path:
        return ""
    name = Path(image_path).name
    return f"local://items/{name}"


class BaseRepository:
    table = ""

    def __init__(self, store: DataStore | None = None, config: LocalDataConfig = DEFAULT_CONFIG):
        self.store = store or DataStore(config=config)
        self.config = config
        self.store.initialize()

    def get_by_id(self, entity_id: int) -> dict[str, Any] | None:
        return _decode_json_fields(self.store.query_one(f"SELECT * FROM {self.table} WHERE id=?", (entity_id,)))

    def get_by_ankama_id(self, ankama_id: int) -> dict[str, Any] | None:
        return _decode_json_fields(self.store.query_one(f"SELECT * FROM {self.table} WHERE ankama_id=?", (ankama_id,)))

    def search_by_name(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        needle = normalize_text(query)
        if not needle:
            return []
        rows = self.store.query_all(
            f"SELECT * FROM {self.table} WHERE name_fr LIKE ? OR name_en LIKE ? ORDER BY level IS NULL, level, name_fr LIMIT ?",
            (f"%{query}%", f"%{query}%", limit * 4),
        )
        filtered = []
        for row in rows:
            haystack = normalize_text(f"{row.get('name_fr', '')} {row.get('name_en', '')}")
            if needle in haystack:
                filtered.append(_decode_json_fields(row))
            if len(filtered) >= limit:
                break
        return [row for row in filtered if row]

    def list_by_type(self, type_name: str, limit: int = 500) -> list[dict[str, Any]]:
        return [_decode_json_fields(row) for row in self.store.query_all(f"SELECT * FROM {self.table} WHERE type LIKE ? ORDER BY level, name_fr LIMIT ?", (f"%{type_name}%", limit))]

    def list_by_level_range(self, min_level: int = 0, max_level: int = 999, limit: int = 1000) -> list[dict[str, Any]]:
        return [_decode_json_fields(row) for row in self.store.query_all(f"SELECT * FROM {self.table} WHERE COALESCE(level,0) BETWEEN ? AND ? ORDER BY level, name_fr LIMIT ?", (min_level, max_level, limit))]

    def get_image_path(self, ankama_id: int) -> str:
        row = self.store.query_one(f"SELECT image_path FROM {self.table} WHERE ankama_id=?", (ankama_id,))
        return row.get("image_path", "") if row else ""


class ItemRepository(BaseRepository):
    table = "items"

    def legacy_list(self, craftable_only: bool = False, limit: int = 20000) -> list[dict[str, Any]]:
        sql = "SELECT i.* FROM items i"
        params: tuple[Any, ...] = ()
        if craftable_only:
            sql += " JOIN recipes r ON r.result_ankama_id = i.ankama_id"
        sql += " WHERE i.name_fr!='' ORDER BY i.level IS NULL, i.level, i.name_fr LIMIT ?"
        params = (limit,)
        return [item for item in (_legacy_item(row, self.config) for row in self.store.query_all(sql, params)) if item]

    def search_legacy(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        return [item for item in (_legacy_item(row, self.config) for row in self.search_by_name(query, limit)) if item]


class ResourceRepository(BaseRepository):
    table = "resources"

    def list_by_job(self, job: int | str, limit: int = 1000) -> list[dict[str, Any]]:
        if isinstance(job, int):
            rows = self.store.query_all("SELECT * FROM resources WHERE job_id=? ORDER BY level, name_fr LIMIT ?", (job, limit))
        else:
            rows = self.store.query_all("SELECT * FROM resources WHERE job_name LIKE ? ORDER BY level, name_fr LIMIT ?", (f"%{job}%", limit))
        return [_decode_json_fields(row) for row in rows]


class RecipeRepository:
    def __init__(self, store: DataStore | None = None, config: LocalDataConfig = DEFAULT_CONFIG):
        self.store = store or DataStore(config=config)
        self.config = config
        self.store.initialize()

    def get_by_result_item(self, item_id: int) -> dict[str, Any] | None:
        recipe = self.store.query_one("SELECT * FROM recipes WHERE result_ankama_id=? OR result_item_id=?", (item_id, item_id))
        return _decode_json_fields(recipe)

    def list_by_job(self, job: int | str, limit: int = 1000) -> list[dict[str, Any]]:
        if isinstance(job, int):
            rows = self.store.query_all("SELECT * FROM recipes WHERE job_id=? ORDER BY level, result_name_fr LIMIT ?", (job, limit))
        else:
            rows = self.store.query_all("SELECT * FROM recipes WHERE job_name LIKE ? ORDER BY level, result_name_fr LIMIT ?", (f"%{job}%", limit))
        return [_decode_json_fields(row) for row in rows]

    def list_by_level_range(self, min_level: int = 0, max_level: int = 999, limit: int = 1000) -> list[dict[str, Any]]:
        rows = self.store.query_all("SELECT * FROM recipes WHERE COALESCE(level,0) BETWEEN ? AND ? ORDER BY level, result_name_fr LIMIT ?", (min_level, max_level, limit))
        return [_decode_json_fields(row) for row in rows]

    def find_by_ingredient(self, ingredient_id_or_name: int | str, limit: int = 1000) -> list[dict[str, Any]]:
        if isinstance(ingredient_id_or_name, int):
            rows = self.store.query_all(
                """
                SELECT r.* FROM recipes r
                JOIN recipe_ingredients ri ON ri.recipe_id=r.id
                WHERE ri.ingredient_ankama_id=?
                ORDER BY r.level, r.result_name_fr LIMIT ?
                """,
                (ingredient_id_or_name, limit),
            )
        else:
            rows = self.store.query_all(
                """
                SELECT r.* FROM recipes r
                JOIN recipe_ingredients ri ON ri.recipe_id=r.id
                WHERE ri.name_fr LIKE ?
                ORDER BY r.level, r.result_name_fr LIMIT ?
                """,
                (f"%{ingredient_id_or_name}%", limit),
            )
        return [_decode_json_fields(row) for row in rows]

    def get_ingredients_for_item(self, item_id: int) -> list[dict[str, Any]]:
        recipe = self.get_by_result_item(item_id)
        if not recipe:
            return []
        rows = self.store.query_all("SELECT * FROM recipe_ingredients WHERE recipe_id=? ORDER BY id", (recipe["id"],))
        return [_decode_json_fields(row) for row in rows]

    def build_shopping_list(self, items_with_quantities: list[dict[str, Any]] | dict[int, int]) -> list[dict[str, Any]]:
        pairs: list[tuple[int, int]] = []
        if isinstance(items_with_quantities, dict):
            pairs = [(int(item_id), int(quantity)) for item_id, quantity in items_with_quantities.items()]
        else:
            for entry in items_with_quantities:
                item_id = entry.get("id_dofus") or entry.get("ankama_id") or entry.get("id")
                quantity = entry.get("quantity", 1)
                if item_id is not None:
                    pairs.append((int(item_id), max(1, int(quantity))))
        aggregate: dict[tuple[int | None, str], dict[str, Any]] = {}
        for item_id, item_quantity in pairs:
            for ingredient in self.get_ingredients_for_item(item_id):
                key = (ingredient.get("ingredient_ankama_id"), ingredient.get("name_fr") or "")
                target = aggregate.setdefault(
                    key,
                    {
                        "id": ingredient.get("ingredient_ankama_id"),
                        "name": ingredient.get("name_fr") or "",
                        "quantity": 0,
                        "type": ingredient.get("type") or "",
                        "level": ingredient.get("level"),
                        "image_path": ingredient.get("image_path") or "",
                    },
                )
                target["quantity"] += int(ingredient.get("quantity") or 1) * item_quantity
        return sorted(aggregate.values(), key=lambda row: (row.get("name") or "").casefold())


class ItemSetRepository(BaseRepository):
    table = "item_sets"

    def get_items_for_set(self, set_id: int) -> list[dict[str, Any]]:
        rows = self.store.query_all(
            """
            SELECT * FROM items
            WHERE COALESCE(json_extract(metadata_json, '$.raw.itemSetId'), -1)=?
            ORDER BY level IS NULL, level, name_fr
            """,
            (set_id,),
        )
        return [_decode_json_fields(row) for row in rows]

    def get_set_for_item(self, item_id: int) -> dict[str, Any] | None:
        item = self.store.query_one("SELECT metadata_json FROM items WHERE ankama_id=? OR id=?", (item_id, item_id))
        item = _decode_json_fields(item)
        raw = ((item or {}).get("metadata_json") or {}).get("raw") or {}
        set_id = raw.get("itemSetId")
        if set_id in (None, "", -1):
            return None
        item_set = self.get_by_ankama_id(int(set_id))
        if not item_set:
            item_set = {
                "ankama_id": int(set_id),
                "name_fr": f"Panoplie {set_id}",
                "name_en": "",
                "level": None,
                "item_ids_json": [],
                "effects_json": [],
            }
        item_set["items"] = self.get_items_for_set(int(set_id))
        return item_set


class JobRepository(BaseRepository):
    table = "jobs"

    def list_all(self) -> list[dict[str, Any]]:
        return [_decode_json_fields(row) for row in self.store.query_all("SELECT * FROM jobs ORDER BY name_fr")]

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        row = self.store.query_one("SELECT * FROM jobs WHERE name_fr LIKE ? OR name_en LIKE ? LIMIT 1", (name, name))
        return _decode_json_fields(row)


class SpellRepository(BaseRepository):
    table = "spells"

    def list_by_class(self, class_id: int) -> list[dict[str, Any]]:
        rows = self.store.query_all(
            """
            SELECT s.* FROM spells s
            JOIN class_spells cs ON cs.spell_ankama_id = s.ankama_id
            WHERE cs.class_ankama_id=?
            ORDER BY cs.raw_order, s.level, s.name_fr
            """,
            (class_id,),
        )
        if rows:
            return [_decode_json_fields(row) for row in rows]
        return [_decode_json_fields(row) for row in self.store.query_all("SELECT * FROM spells WHERE class_id=? ORDER BY level, name_fr", (class_id,))]


class MonsterRepository(BaseRepository):
    table = "monsters"

    def list_by_area(self, area_id: int) -> list[dict[str, Any]]:
        return [_decode_json_fields(row) for row in self.store.query_all("SELECT * FROM monsters WHERE area_id=? ORDER BY name_fr", (area_id,))]

    def list_spells(self, monster_id: int) -> list[dict[str, Any]]:
        rows = self.store.query_all(
            """
            SELECT s.*, ms.grade_info, ms.raw_order
            FROM monster_spells ms
            LEFT JOIN spells s ON s.ankama_id = ms.spell_ankama_id
            WHERE ms.monster_ankama_id=?
            ORDER BY ms.raw_order, s.name_fr
            """,
            (monster_id,),
        )
        return [_decode_json_fields(row) for row in rows]


class MapRepository:
    def __init__(self, store: DataStore | None = None, config: LocalDataConfig = DEFAULT_CONFIG):
        self.store = store or DataStore(config=config)
        self.config = config
        self.store.initialize()

    def get_by_map_id(self, map_id: int) -> dict[str, Any] | None:
        return _decode_json_fields(self.store.query_one("SELECT * FROM maps WHERE map_id=?", (map_id,)))

    def get_by_position(self, x: int, y: int) -> list[dict[str, Any]]:
        return [_decode_json_fields(row) for row in self.store.query_all("SELECT * FROM maps WHERE x=? AND y=? ORDER BY map_id", (x, y))]

    def list_by_area(self, area_id: int) -> list[dict[str, Any]]:
        return [_decode_json_fields(row) for row in self.store.query_all("SELECT * FROM maps WHERE area_id=? OR subarea_id=? ORDER BY map_id", (area_id, area_id))]

    def get_cells(self, map_id: int) -> list[dict[str, Any]]:
        return [_decode_json_fields(row) for row in self.store.query_all("SELECT * FROM cells WHERE map_id=? ORDER BY cell_id", (map_id,))]

    def get_neighbours(self, map_id: int) -> dict[str, Any]:
        row = self.get_by_map_id(map_id)
        return row.get("neighbours_json", {}) if row else {}

    def get_interactives_if_known(self, map_id: int) -> list[dict[str, Any]]:
        return [_decode_json_fields(row) for row in self.store.query_all("SELECT * FROM interactive_elements WHERE map_id=? ORDER BY cell_id", (map_id,))]


class TextRepository:
    def __init__(self, store: DataStore | None = None, config: LocalDataConfig = DEFAULT_CONFIG):
        self.store = store or DataStore(config=config)
        self.config = config
        self.store.initialize()

    def get_text(self, text_id: int, lang: str = "fr") -> str:
        row = self.store.query_one("SELECT text FROM texts WHERE text_id=? AND lang=? LIMIT 1", (text_id, lang))
        return row.get("text", "") if row else ""

    def search_text(self, query: str, lang: str = "fr", limit: int = 50) -> list[dict[str, Any]]:
        return self.store.query_all("SELECT * FROM texts WHERE lang=? AND text LIKE ? LIMIT ?", (lang, f"%{query}%", limit))


class ImageRepository:
    def __init__(self, store: DataStore | None = None, config: LocalDataConfig = DEFAULT_CONFIG):
        self.store = store or DataStore(config=config)
        self.config = config
        self.store.initialize()

    def get_image_for_item(self, item_id: int) -> str:
        row = self.store.query_one("SELECT image_path FROM items WHERE ankama_id=? OR id=?", (item_id, item_id))
        return row.get("image_path", "") if row else ""

    def get_image_for_resource(self, resource_id: int) -> str:
        row = self.store.query_one("SELECT image_path FROM resources WHERE ankama_id=? OR id=?", (resource_id, resource_id))
        return row.get("image_path", "") if row else ""

    def search_missing_images(self, limit: int = 500) -> list[dict[str, Any]]:
        return self.store.query_all("SELECT ankama_id, name_fr, type FROM items WHERE image_path='' AND name_fr!='' LIMIT ?", (limit,))
