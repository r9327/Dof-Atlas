from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import image_basename_from_url, normalize_text, repair_mojibake, safe_int, text_from_locale


RESOURCE_HINTS = {
    "ressource",
    "resource",
    "bois",
    "minerai",
    "alliage",
    "poisson",
    "cereale",
    "plante",
    "fleur",
    "etoffe",
    "cuir",
    "os",
    "pierre",
    "viande",
    "huile",
}
EQUIPMENT_HINTS = {
    "arme",
    "equipment",
    "weapon",
    "epee",
    "arc",
    "baguette",
    "baton",
    "dague",
    "pelle",
    "marteau",
    "hache",
    "amulette",
    "anneau",
    "botte",
    "ceinture",
    "cape",
    "coiffe",
    "bouclier",
    "trophée",
    "trophee",
    "dofus",
}
CONSUMABLE_HINTS = {"consommable", "consumable", "pain", "potion", "friandise", "viande comestible"}


def empty_bundle(source: str = "") -> dict[str, Any]:
    return {
        "source": source,
        "sources": [],
        "items": [],
        "resources": [],
        "equipment": [],
        "item_sets": [],
        "consumables": [],
        "recipes": [],
        "jobs": [],
        "spells": [],
        "classes": [],
        "monsters": [],
        "monster_families": [],
        "maps": [],
        "cells": [],
        "areas": [],
        "subareas": [],
        "interactive_elements": [],
        "texts": [],
        "image_assets": [],
        "effects": [],
        "item_effects": [],
        "monster_spells": [],
        "class_spells": [],
        "conditions": [],
        "raw_objects": [],
        "warnings": [],
        "errors": [],
    }


def merge_bundles(*bundles: dict[str, Any]) -> dict[str, Any]:
    merged = empty_bundle("merged")
    for bundle in bundles:
        for key, value in bundle.items():
            if key in {"source"}:
                continue
            if isinstance(merged.get(key), list) and isinstance(value, list):
                merged[key].extend(value)
    return merged


def object_fields(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    fields = raw.get("Fields") or raw.get("fields") or raw.get("_fields")
    if isinstance(fields, dict):
        return {**raw, **fields}
    return raw


def object_id(raw: dict[str, Any], fields: dict[str, Any] | None = None) -> int | None:
    fields = fields or raw
    for key in ("id", "Id", "ID", "ankama_id", "ankamaId", "gid", "GID", "objectId", "resultId"):
        value = fields.get(key, raw.get(key))
        parsed = safe_int(value)
        if parsed is not None:
            return parsed
    return None


def translated_name(fields: dict[str, Any], texts: dict[int, dict[str, str]] | None = None) -> tuple[str, str]:
    for key in ("name", "Name", "label", "title", "resultName"):
        if fields.get(key):
            value = fields[key]
            if isinstance(value, dict):
                return repair_mojibake(value.get("fr") or value.get("name") or ""), repair_mojibake(value.get("en") or "")
            return repair_mojibake(value), ""
    name_id = safe_int(fields.get("nameId") or fields.get("name_id"))
    if name_id is not None and texts:
        entry = texts.get(name_id) or {}
        return repair_mojibake(entry.get("fr", "")), repair_mojibake(entry.get("en", ""))
    return "", ""


def classify_item(row: dict[str, Any]) -> str:
    haystack = normalize_text(
        " ".join(
            repair_mojibake(row.get(key, ""))
            for key in ("category", "family", "type", "type_name", "item_type", "name_fr")
        )
    )
    if any(hint in haystack for hint in EQUIPMENT_HINTS):
        return "equipment"
    if any(hint in haystack for hint in CONSUMABLE_HINTS):
        return "consumable"
    if any(hint in haystack for hint in RESOURCE_HINTS):
        return "resource"
    return "item"


def normalize_legacy_item(raw: dict[str, Any], source: str = "legacy_cache") -> dict[str, Any]:
    ankama_id = safe_int(raw.get("id_dofus") or raw.get("ankama_id") or raw.get("gid") or raw.get("id"))
    image = raw.get("image") or raw.get("img") or ""
    image_name = image_basename_from_url(image)
    image_path = f"data/images/items/{image_name}" if image_name else ""
    row = {
        "ankama_id": ankama_id,
        "gid": safe_int(raw.get("gid") or raw.get("id_dofus")),
        "name_fr": repair_mojibake(raw.get("name", "")),
        "name_en": repair_mojibake(raw.get("name_en", "")),
        "category": repair_mojibake(raw.get("family", "")),
        "type": repair_mojibake(raw.get("type", "")),
        "family": repair_mojibake(raw.get("family", "")),
        "level": safe_int(raw.get("level")),
        "source": source,
        "image_path": image_path,
        "metadata_json": {"legacy": raw, "image_url": image},
    }
    row["normalized_category"] = classify_item(row)
    return row


def normalize_legacy_job(raw: dict[str, Any], source: str = "legacy_cache") -> dict[str, Any]:
    legacy = dict(raw)
    for key in ("image", "img", "image_url"):
        legacy.pop(key, None)
    return {
        "ankama_id": safe_int(raw.get("id_dofus") or raw.get("ankama_id") or raw.get("id")),
        "gid": safe_int(raw.get("gid") or raw.get("id_dofus")),
        "name_fr": repair_mojibake(raw.get("name", "")),
        "name_en": repair_mojibake(raw.get("name_en", "")),
        "type": "job",
        "category": "job",
        "level": safe_int(raw.get("level")),
        "is_recolt": bool(raw.get("is_recolt")) if raw.get("is_recolt") is not None else None,
        "source": source,
        "image_path": "",
        "metadata_json": {"legacy": legacy},
    }


def normalize_legacy_recipe(raw: dict[str, Any], source: str = "legacy_cache") -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result_id = safe_int(raw.get("result_id") or raw.get("resultId") or raw.get("id"))
    recipe = {
        "ankama_id": result_id,
        "result_ankama_id": result_id,
        "result_name_fr": repair_mojibake(raw.get("result_name") or raw.get("name") or ""),
        "result_name_en": repair_mojibake(raw.get("result_name_en") or ""),
        "job_id": safe_int(raw.get("job_id") or raw.get("jobId")),
        "job_name": repair_mojibake(raw.get("job_name") or ""),
        "level": safe_int(raw.get("level") or raw.get("resultLevel")),
        "source": source,
        "metadata_json": {"legacy": raw},
    }
    ingredients = []
    for ingredient in raw.get("ingredients") or []:
        image = ingredient.get("image") or ingredient.get("img") or ""
        image_name = image_basename_from_url(image)
        ingredients.append(
            {
                "ingredient_ankama_id": safe_int(ingredient.get("id") or ingredient.get("ankama_id")),
                "name_fr": repair_mojibake(ingredient.get("name", "")),
                "name_en": repair_mojibake(ingredient.get("name_en", "")),
                "quantity": safe_int(ingredient.get("quantity"), 1) or 1,
                "type": repair_mojibake(ingredient.get("type", "")),
                "level": safe_int(ingredient.get("level")),
                "source": source,
                "image_path": f"data/images/items/{image_name}" if image_name else "",
                "metadata_json": {"legacy": ingredient, "image_url": image},
            }
        )
    return recipe, ingredients


def normalize_recipe_index_entry(raw: dict[str, Any], source: str = "legacy_recipe_index") -> dict[str, Any]:
    result_id = safe_int(raw.get("result_id") or raw.get("resultId") or raw.get("id"))
    return {
        "ankama_id": result_id,
        "result_ankama_id": result_id,
        "result_name_fr": repair_mojibake(raw.get("name") or raw.get("result_name") or ""),
        "result_name_en": "",
        "job_id": safe_int(raw.get("job_id") or raw.get("jobId")),
        "job_name": "",
        "level": safe_int(raw.get("level") or raw.get("resultLevel")),
        "source": source,
        "metadata_json": {"index": raw},
    }


def normalize_d2o_item(raw: dict[str, Any], texts: dict[int, dict[str, str]] | None = None, source: str = "d2o") -> dict[str, Any]:
    fields = object_fields(raw)
    ankama_id = object_id(raw, fields)
    name_fr, name_en = translated_name(fields, texts)
    type_value = fields.get("type") or fields.get("typeId") or fields.get("itemTypeId") or fields.get("category")
    image_id = fields.get("iconId") or fields.get("skin") or fields.get("image")
    image_path = f"data/images/items/{safe_int(image_id)}.png" if safe_int(image_id) is not None else ""
    row = {
        "ankama_id": ankama_id,
        "gid": safe_int(fields.get("gid") or fields.get("GID") or ankama_id),
        "name_fr": name_fr,
        "name_en": name_en,
        "category": repair_mojibake(fields.get("category") or fields.get("family") or ""),
        "type": repair_mojibake(type_value or ""),
        "family": repair_mojibake(fields.get("family") or ""),
        "level": safe_int(fields.get("level") or fields.get("Level")),
        "source": source,
        "image_path": image_path,
        "metadata_json": {"raw": raw},
    }
    row["normalized_category"] = classify_item(row)
    return row


def normalize_api_item(raw: dict[str, Any], source: str = "api_static_import") -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    ankama_id = safe_int(raw.get("id") or raw.get("ankama_id") or raw.get("m_id"))
    if ankama_id is None:
        return None
    name_fr = text_from_locale(raw.get("name") or raw.get("resultName") or raw.get("title"))
    type_value = raw.get("type") or raw.get("itemType") or raw.get("typeName") or raw.get("typeId") or ""
    if isinstance(type_value, dict):
        type_value = text_from_locale(type_value.get("name") or type_value)
    family_value = raw.get("family") or raw.get("superType") or ""
    if not family_value and isinstance(raw.get("type"), dict):
        family_value = raw["type"].get("superType") or ""
    if isinstance(family_value, dict):
        family_value = text_from_locale(family_value.get("name") or family_value)
    image = raw.get("image") or raw.get("img") or ""
    if not image and safe_int(raw.get("iconId")) is not None:
        image = f"https://api.dofusdb.fr/img/items/{safe_int(raw.get('iconId'))}.png"
    image_name = image_basename_from_url(image)
    row = {
        "ankama_id": ankama_id,
        "gid": safe_int(raw.get("gid") or raw.get("GID") or ankama_id),
        "name_fr": name_fr,
        "name_en": text_from_locale({"en": (raw.get("name") or {}).get("en")} if isinstance(raw.get("name"), dict) else ""),
        "category": repair_mojibake(family_value),
        "type": repair_mojibake(type_value),
        "family": repair_mojibake(family_value),
        "level": safe_int(raw.get("level") or raw.get("resultLevel")),
        "source": source,
        "image_path": f"data/images/items/{image_name}" if image_name else "",
        "metadata_json": {"raw": raw, "image_url": image},
    }
    row["normalized_category"] = classify_item(row)
    return row


def normalize_item_set(raw: dict[str, Any], source: str = "api_static_import") -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    ankama_id = safe_int(raw.get("id") or raw.get("m_id") or raw.get("ankama_id"))
    if ankama_id is None:
        return None
    item_ids = []
    for item in raw.get("items") or raw.get("itemIds") or []:
        item_id = safe_int(item.get("id") if isinstance(item, dict) else item)
        if item_id is not None:
            item_ids.append(item_id)
    return {
        "ankama_id": ankama_id,
        "gid": safe_int(raw.get("gid") or raw.get("m_id") or ankama_id),
        "name_fr": text_from_locale(raw.get("name")),
        "name_en": text_from_locale({"en": (raw.get("name") or {}).get("en")} if isinstance(raw.get("name"), dict) else ""),
        "level": safe_int(raw.get("level")),
        "item_ids_json": item_ids,
        "effects_json": raw.get("effects") or raw.get("possibleEffects") or [],
        "source": source,
        "metadata_json": {"raw": raw},
    }


def normalize_named_entity(raw: dict[str, Any], entity_type: str, texts: dict[int, dict[str, str]] | None = None, source: str = "json") -> dict[str, Any]:
    fields = object_fields(raw)
    name_fr, name_en = translated_name(fields, texts)
    return {
        "ankama_id": object_id(raw, fields),
        "gid": safe_int(fields.get("gid") or fields.get("GID")),
        "name_fr": name_fr,
        "name_en": name_en,
        "type": repair_mojibake(fields.get("type") or entity_type),
        "category": entity_type,
        "level": safe_int(fields.get("level") or fields.get("Level")),
        "source": source,
        "image_path": "",
        "metadata_json": {"raw": raw},
    }


def normalize_monster(raw: dict[str, Any], source: str = "json") -> dict[str, Any]:
    row = normalize_named_entity(raw, "monster", source=source)
    race = raw.get("race") if isinstance(raw, dict) else None
    subareas = raw.get("subareas") if isinstance(raw, dict) else None
    row["family_id"] = safe_int((race or {}).get("id") if isinstance(race, dict) else raw.get("raceId"))
    area_id = None
    if isinstance(subareas, list) and subareas:
        first = subareas[0]
        if isinstance(first, dict):
            area_id = safe_int(first.get("areaId") or first.get("area_id"))
    row["area_id"] = area_id
    image = raw.get("img") or raw.get("image") or ""
    image_name = image_basename_from_url(image)
    if image_name:
        row["image_path"] = f"data/images/misc/{image_name}"
    return row


def normalize_monster_family_from_monster(raw: dict[str, Any], source: str = "json") -> dict[str, Any] | None:
    race = raw.get("race") if isinstance(raw, dict) else None
    if not isinstance(race, dict):
        return None
    row = normalize_named_entity(race, "monster_family", source=source)
    if row.get("ankama_id") is None:
        return None
    return row


def normalize_text_entry(raw_key: Any, raw_value: Any, source: str = "d2i") -> list[dict[str, Any]]:
    text_id = safe_int(raw_key)
    entries: list[dict[str, Any]] = []
    if isinstance(raw_value, dict):
        for lang, text in raw_value.items():
            entries.append(
                {
                    "text_id": text_id,
                    "lang": str(lang).replace("_FR", "").replace("fr_FR", "fr")[:8] or "fr",
                    "text": repair_mojibake(text),
                    "source": source,
                    "metadata_json": {"raw": raw_value},
                }
            )
    else:
        entries.append(
            {
                "text_id": text_id,
                "lang": "fr",
                "text": repair_mojibake(raw_value),
                "source": source,
                "metadata_json": {"raw": raw_value},
            }
        )
    return entries


def normalize_map(raw: dict[str, Any], source: str = "maps") -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    fields = object_fields(raw)
    map_id = safe_int(fields.get("mapId") or fields.get("MapId") or fields.get("id") or fields.get("Id"))
    if map_id is None:
        return None, [], []
    neighbours = {
        "left": safe_int(fields.get("LeftNeighbourId") or fields.get("leftNeighbourId") or fields.get("left")),
        "right": safe_int(fields.get("RightNeighbourId") or fields.get("rightNeighbourId") or fields.get("right")),
        "top": safe_int(fields.get("TopNeighbourId") or fields.get("topNeighbourId") or fields.get("top")),
        "bottom": safe_int(fields.get("BottomNeighbourId") or fields.get("bottomNeighbourId") or fields.get("bottom")),
    }
    row = {
        "map_id": map_id,
        "x": safe_int(fields.get("posX") or fields.get("x") or fields.get("X")),
        "y": safe_int(fields.get("posY") or fields.get("y") or fields.get("Y")),
        "area_id": safe_int(fields.get("areaId") or fields.get("AreaId")),
        "subarea_id": safe_int(fields.get("subAreaId") or fields.get("SubAreaId") or fields.get("subareaId")),
        "neighbours_json": {key: value for key, value in neighbours.items() if value is not None},
        "source": source,
        "metadata_json": {"raw": raw},
    }
    cells: list[dict[str, Any]] = []
    raw_cells = fields.get("Cells") or fields.get("cells") or []
    if isinstance(raw_cells, dict):
        raw_cells = [{"cell_id": key, **value} if isinstance(value, dict) else {"cell_id": key, "value": value} for key, value in raw_cells.items()]
    for index, cell in enumerate(raw_cells if isinstance(raw_cells, list) else []):
        if not isinstance(cell, dict):
            continue
        cell_id = safe_int(cell.get("cellId") or cell.get("cell_id") or cell.get("id") or index)
        cells.append(
            {
                "map_id": map_id,
                "cell_id": cell_id,
                "walkable": _bool_or_none(cell.get("walkable") if "walkable" in cell else cell.get("mov")),
                "los": _bool_or_none(cell.get("Los") if "Los" in cell else cell.get("los")),
                "source": source,
                "metadata_json": {"raw": cell},
            }
        )
    interactives: list[dict[str, Any]] = []
    raw_interactives = fields.get("interactiveElements") or fields.get("Interactives") or fields.get("interactive_elements") or []
    if isinstance(raw_interactives, dict):
        raw_interactives = raw_interactives.values()
    for element in raw_interactives if isinstance(raw_interactives, list) else []:
        if not isinstance(element, dict):
            continue
        interactives.append(
            {
                "ankama_id": object_id(element),
                "gid": safe_int(element.get("elementId") or element.get("gid")),
                "map_id": map_id,
                "cell_id": safe_int(element.get("cellId") or element.get("cell_id")),
                "name_fr": repair_mojibake(element.get("name", "")),
                "name_en": "",
                "type": repair_mojibake(element.get("type") or element.get("skill") or ""),
                "category": "interactive",
                "level": None,
                "source": source,
                "image_path": "",
                "metadata_json": {"raw": element},
            }
        )
    return row, cells, interactives


def bundle_from_records(records: list[Any], filename: str | Path, source: str) -> dict[str, Any]:
    bundle = empty_bundle(source)
    name = Path(filename).stem.casefold()
    for raw in records:
        if not isinstance(raw, dict):
            bundle["raw_objects"].append((source, name, "", str(filename), raw))
            continue
        if "item-set" in name or "item_set" in name or "itemsets" in name:
            row = normalize_item_set(raw, source=source)
            if row:
                bundle["item_sets"].append(row)
            else:
                bundle["raw_objects"].append((source, name, object_id(raw) or "", str(filename), raw))
        elif "item" in name:
            row = normalize_api_item(raw, source=source) if source == "api_static_import" or name.startswith("dofusdb_") else normalize_d2o_item(raw, source=source)
            if not row:
                bundle["raw_objects"].append((source, name, object_id(raw) or "", str(filename), raw))
                continue
            bundle["items"].append(row)
            _add_typed_item(bundle, row)
        elif "recipe" in name:
            recipe, ingredients = normalize_recipe_like(raw, source=source)
            if recipe:
                bundle["recipes"].append((recipe, ingredients))
                for related_item in recipe_related_items(raw, source=source):
                    bundle["items"].append({key: value for key, value in related_item.items() if key != "normalized_category"})
                    _add_typed_item(bundle, related_item)
                effect_rows, item_effect_rows, condition_rows = recipe_related_details(raw, source=source)
                bundle["effects"].extend(effect_rows)
                bundle["item_effects"].extend(item_effect_rows)
                bundle["conditions"].extend(condition_rows)
            else:
                bundle["raw_objects"].append((source, name, object_id(raw) or "", str(filename), raw))
        elif "job" in name or "profession" in name:
            bundle["jobs"].append(normalize_named_entity(raw, "job", source=source))
        elif "spell" in name:
            bundle["spells"].append(normalize_named_entity(raw, "spell", source=source))
        elif "breed" in name or "class" in name:
            bundle["classes"].append(normalize_named_entity(raw, "class", source=source))
            bundle["class_spells"].extend(normalize_class_spell_links(raw, source=source))
        elif "monster" in name and "race" not in name:
            bundle["monsters"].append(normalize_monster(raw, source=source))
            bundle["monster_spells"].extend(normalize_monster_spell_links(raw, source=source))
            family = normalize_monster_family_from_monster(raw, source=source)
            if family:
                bundle["monster_families"].append(family)
        elif "race" in name or "family" in name:
            bundle["monster_families"].append(normalize_named_entity(raw, "monster_family", source=source))
        elif "subarea" in name or "sub_area" in name:
            bundle["subareas"].append({**normalize_named_entity(raw, "subarea", source=source), "area_id": safe_int(object_fields(raw).get("areaId"))})
        elif "area" in name:
            bundle["areas"].append(normalize_named_entity(raw, "area", source=source))
        elif "map" in name:
            map_row, cells, interactives = normalize_map(raw, source=source)
            if map_row:
                bundle["maps"].append(map_row)
                bundle["cells"].extend(cells)
                bundle["interactive_elements"].extend(interactives)
        else:
            bundle["raw_objects"].append((source, name, object_id(raw) or "", str(filename), raw))
    return bundle


def normalize_recipe_like(raw: dict[str, Any], source: str = "json") -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    fields = object_fields(raw)
    result_id = safe_int(fields.get("resultId") or fields.get("result_id") or fields.get("resultItemId") or fields.get("result_ankama_id"))
    if result_id is None:
        return None, []
    result_name = text_from_locale(fields.get("resultName") or fields.get("name") or fields.get("result_name"))
    recipe = {
        "ankama_id": safe_int(fields.get("id") or result_id),
        "result_ankama_id": result_id,
        "result_name_fr": result_name,
        "result_name_en": "",
        "job_id": safe_int(fields.get("jobId") or fields.get("job_id")),
        "job_name": repair_mojibake(fields.get("jobName") or fields.get("job_name") or ""),
        "level": safe_int(fields.get("resultLevel") or fields.get("level")),
        "source": source,
        "metadata_json": {"raw": raw},
    }
    ingredient_ids = fields.get("ingredientIds") or fields.get("ingredient_ids") or []
    quantities = fields.get("quantities") or fields.get("ingredientQuantities") or []
    ingredient_items = fields.get("ingredients") or []
    ingredients: list[dict[str, Any]] = []
    for index, ingredient_id in enumerate(ingredient_ids if isinstance(ingredient_ids, list) else []):
        ingredient_item = ingredient_items[index] if isinstance(ingredient_items, list) and index < len(ingredient_items) else {}
        quantity = quantities[index] if isinstance(quantities, list) and index < len(quantities) else 1
        if isinstance(ingredient_item, dict):
            image = ingredient_item.get("image") or ingredient_item.get("img") or ""
            if not image and safe_int(ingredient_item.get("iconId")) is not None:
                image = f"https://api.dofusdb.fr/img/items/{safe_int(ingredient_item.get('iconId'))}.png"
            type_value = ingredient_item.get("type") or ""
            if isinstance(type_value, dict):
                type_value = type_value.get("name") or type_value
            name_value = ingredient_item.get("name") or str(ingredient_id)
            level_value = ingredient_item.get("level")
        else:
            image = ""
            type_value = ""
            name_value = str(ingredient_id)
            level_value = None
        image_name = image_basename_from_url(image)
        ingredients.append(
            {
                "ingredient_ankama_id": safe_int(ingredient_id),
                "name_fr": text_from_locale(name_value, str(ingredient_id)),
                "name_en": "",
                "quantity": safe_int(quantity, 1) or 1,
                "type": text_from_locale(type_value),
                "level": safe_int(level_value),
                "source": source,
                "image_path": f"data/images/items/{image_name}" if image_name else "",
                "metadata_json": {"raw": ingredient_item},
            }
        )
    return recipe, ingredients


def recipe_related_items(raw: dict[str, Any], source: str = "json") -> list[dict[str, Any]]:
    fields = object_fields(raw)
    related: list[dict[str, Any]] = []
    result = fields.get("result")
    if isinstance(result, dict):
        item = normalize_api_item(result, source=source)
        if item:
            related.append(item)
    ingredients = fields.get("ingredients") or []
    if isinstance(ingredients, list):
        for ingredient in ingredients:
            if isinstance(ingredient, dict):
                item = normalize_api_item(ingredient, source=source)
                if item:
                    related.append(item)
    return related


def recipe_related_details(raw: dict[str, Any], source: str = "json") -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    fields = object_fields(raw)
    effects: list[dict[str, Any]] = []
    item_effects: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []
    related_raw = []
    result = fields.get("result")
    if isinstance(result, dict):
        related_raw.append(result)
    ingredients = fields.get("ingredients") or []
    if isinstance(ingredients, list):
        related_raw.extend([item for item in ingredients if isinstance(item, dict)])
    for item_raw in related_raw:
        item_id = safe_int(item_raw.get("id") or item_raw.get("m_id"))
        item_effect_rows, effect_rows = normalize_item_effects(item_raw, item_id, source=source)
        condition_rows = normalize_item_conditions(item_raw, item_id, source=source)
        effects.extend(effect_rows)
        item_effects.extend(item_effect_rows)
        conditions.extend(condition_rows)
    return effects, item_effects, conditions


def normalize_monster_spell_links(raw: dict[str, Any], source: str = "json") -> list[dict[str, Any]]:
    monster_id = safe_int(raw.get("id") or raw.get("m_id") or raw.get("ankama_id"))
    spells = raw.get("spells") or raw.get("spellIds") or []
    grades = raw.get("spellGrades") or []
    rows: list[dict[str, Any]] = []
    if not isinstance(spells, list) or monster_id is None:
        return rows
    for index, spell in enumerate(spells):
        spell_id = safe_int(spell.get("id") if isinstance(spell, dict) else spell)
        if spell_id is None:
            continue
        grade_info = grades[index] if isinstance(grades, list) and index < len(grades) else ""
        rows.append(
            {
                "monster_ankama_id": monster_id,
                "spell_ankama_id": spell_id,
                "raw_order": index,
                "grade_info": repair_mojibake(grade_info),
                "source": source,
                "metadata_json": {"monster": monster_id, "spell": spell, "grade": grade_info},
            }
        )
    return rows


def normalize_class_spell_links(raw: dict[str, Any], source: str = "json") -> list[dict[str, Any]]:
    class_id = safe_int(raw.get("id") or raw.get("m_id") or raw.get("ankama_id"))
    spells = raw.get("breedSpellsId") or raw.get("spells") or raw.get("spellIds") or []
    rows: list[dict[str, Any]] = []
    if not isinstance(spells, list) or class_id is None:
        return rows
    for index, spell in enumerate(spells):
        spell_id = safe_int(spell.get("id") if isinstance(spell, dict) else spell)
        if spell_id is None:
            continue
        rows.append(
            {
                "class_ankama_id": class_id,
                "spell_ankama_id": spell_id,
                "raw_order": index,
                "source": source,
                "metadata_json": {"class": class_id, "spell": spell},
            }
        )
    return rows


def normalize_item_effects(raw_item: dict[str, Any], item_ankama_id: int | None, source: str = "json") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    item_effects: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    raw_effects = raw_item.get("effects") or raw_item.get("possibleEffects") or []
    if not isinstance(raw_effects, list):
        return item_effects, effects
    for index, raw_effect in enumerate(raw_effects):
        if not isinstance(raw_effect, dict):
            continue
        effect_id = safe_int(raw_effect.get("effectId") or raw_effect.get("baseEffectId") or raw_effect.get("id"))
        effects.append(
            {
                "ankama_id": effect_id,
                "name_fr": text_from_locale(raw_effect.get("description") or raw_effect.get("name") or ""),
                "name_en": "",
                "description_fr": text_from_locale(raw_effect.get("description") or ""),
                "description_en": "",
                "type": repair_mojibake(raw_effect.get("className") or raw_effect.get("type") or ""),
                "category": "effect",
                "source": source,
                "metadata_json": {"raw": raw_effect},
            }
        )
        item_effects.append(
            {
                "item_ankama_id": item_ankama_id,
                "effect_ankama_id": effect_id,
                "effect_name_fr": text_from_locale(raw_effect.get("description") or raw_effect.get("name") or ""),
                "value_int": safe_int(raw_effect.get("value")),
                "min_int": safe_int(raw_effect.get("from") or raw_effect.get("diceNum")),
                "max_int": safe_int(raw_effect.get("to") or raw_effect.get("diceSide")),
                "raw_order": safe_int(raw_effect.get("order"), index) or index,
                "source": source,
                "metadata_json": {"raw": raw_effect},
            }
        )
    return item_effects, effects


def normalize_item_conditions(raw_item: dict[str, Any], item_ankama_id: int | None, source: str = "json") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    keys = (
        "criterions",
        "criterionsTarget",
        "visibilityCriterion",
        "craftVisibleCriterion",
        "craftFeasibleCriterion",
        "craftConditionalCriterion",
    )
    for key in keys:
        expression = raw_item.get(key)
        if expression in (None, "", [], {}):
            continue
        rows.append(
            {
                "owner_type": "item",
                "owner_ankama_id": item_ankama_id,
                "condition_type": key,
                "expression": repair_mojibake(expression),
                "source": source,
                "metadata_json": {"raw": expression},
            }
        )
    return rows


def _add_typed_item(bundle: dict[str, Any], row: dict[str, Any]) -> None:
    category = row.get("normalized_category") or classify_item(row)
    clean = {key: value for key, value in row.items() if key != "normalized_category"}
    if category == "resource":
        bundle["resources"].append({**clean, "category": "resource", "job_id": None, "job_name": ""})
    elif category == "equipment":
        raw = (clean.get("metadata_json") or {}).get("raw") or {}
        bundle["equipment"].append({**clean, "category": "equipment", "set_id": safe_int(raw.get("itemSetId"))})
    elif category == "consumable":
        bundle["consumables"].append({**clean, "category": "consumable"})


def _bool_or_none(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).casefold()
    if text in {"1", "true", "yes", "oui"}:
        return True
    if text in {"0", "false", "no", "non"}:
        return False
    return None
