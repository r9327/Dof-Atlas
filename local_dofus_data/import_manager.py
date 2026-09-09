from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig, ensure_directories
from .api_static_importer import ApiStaticImporter
from .d2data_importer import D2DataImporter
from .d2i_importer import D2IImporter
from .d2o_importer import D2OImporter
from .data_store import DataStore
from .existing_cache_importer import ExistingCacheImporter
from .export_tools import export_all
from .image_organizer import ImageOrganizer
from .json_importer import JsonImporter
from .map_importer import MapImporter
from .normalizer import empty_bundle, merge_bundles
from .reports import build_summary, write_import_report
from .source_registry import SourceRegistry
from .utils import now_iso
from .validators import Validator
from .zaap_importer import ZaapImporter


def run_import(
    full: bool = False,
    offline: bool = True,
    config: LocalDataConfig = DEFAULT_CONFIG,
    with_static_api: bool = False,
    recipe_page_limit: int = 500,
    recipe_max_pages: int | None = None,
    static_api_scope: str = "recipes",
) -> dict[str, Any]:
    ensure_directories(config)
    started_at = now_iso()
    store = DataStore(config=config)
    store.initialize()
    registry = SourceRegistry(store)
    registry.register("local_sqlite", config.sqlite_path, name="Local SQLite", status="ok")

    bundles: list[dict[str, Any]] = []
    importers = [
        ("d2data", D2DataImporter(config).import_directory),
        ("d2o_export", D2OImporter(config).import_directory),
        ("d2i_export", D2IImporter(config).import_directory),
        ("maps_export", MapImporter(config).import_directory),
        ("json_local", JsonImporter(config).import_directory),
        ("legacy_cache", ExistingCacheImporter(config).import_cache),
    ]

    for source_name, importer in importers:
        try:
            bundle = importer()
            bundles.append(bundle)
        except Exception as exc:
            bundle = empty_bundle(source_name)
            bundle["errors"].append(f"{source_name}: {exc}")
            bundles.append(bundle)

    if with_static_api and not offline:
        try:
            bundles.append(ApiStaticImporter(config).fetch_static_data(scope=static_api_scope, limit=recipe_page_limit, max_pages=recipe_max_pages))
        except Exception as exc:
            bundle = empty_bundle("api_static_import")
            bundle["errors"].append(f"api_static_import: {exc}")
            bundles.append(bundle)

    bundle = merge_bundles(*bundles)
    counts = apply_bundle(store, bundle, registry)
    zaap_report = ZaapImporter(config=config, store=store).build(online=bool(with_static_api and not offline))
    image_counts = ImageOrganizer(config=config, store=store).organize(move_unreferenced=False)
    validation = Validator(store).run_all()
    export_counts = export_all(store, config)
    summary = build_summary(store, config)
    finished_at = now_iso()

    report = {
        "source": "full_import" if full else "offline_import",
        "offline": offline,
        "with_static_api": bool(with_static_api and not offline),
        "started_at": started_at,
        "finished_at": finished_at,
        "counts": counts,
        "zaaps": {"count": zaap_report.get("count", 0), "online_import": zaap_report.get("online_import", False)},
        "image_index": image_counts,
        "exports": export_counts,
        "validation": validation,
        "summary": summary,
        "warnings": bundle.get("warnings", []) + validation.get("warnings", []),
        "errors": bundle.get("errors", []),
    }
    status = "ok" if not report["errors"] else "warning"
    store.insert_import_report(
        {
            "source": report["source"],
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "counts_json": counts,
            "warnings_json": report["warnings"],
            "errors_json": report["errors"],
        }
    )
    write_import_report(report, config)
    store.close()
    return report


def apply_bundle(store: DataStore, bundle: dict[str, Any], registry: SourceRegistry | None = None) -> dict[str, int]:
    registry = registry or SourceRegistry(store)
    counts = {
        "sources": 0,
        "items": 0,
        "resources": 0,
        "equipment": 0,
        "item_sets": 0,
        "consumables": 0,
        "recipes": 0,
        "recipe_ingredients": 0,
        "jobs": 0,
        "spells": 0,
        "classes": 0,
        "monsters": 0,
        "monster_families": 0,
        "maps": 0,
        "cells": 0,
        "areas": 0,
        "subareas": 0,
        "interactive_elements": 0,
        "texts": 0,
        "effects": 0,
        "item_effects": 0,
        "monster_spells": 0,
        "class_spells": 0,
        "conditions": 0,
        "raw_objects": 0,
    }

    for source in bundle.get("sources", []):
        registry.register(
            source.get("type", "unknown"),
            source.get("path", ""),
            name=source.get("name"),
            status=source.get("status", "ok"),
            version=source.get("version", ""),
            metadata=source.get("metadata_json") or {},
        )
        counts["sources"] += 1

    table_map = [
        ("items", "items", "ankama_id"),
        ("resources", "resources", "ankama_id"),
        ("equipment", "equipment", "ankama_id"),
        ("item_sets", "item_sets", "ankama_id"),
        ("consumables", "consumables", "ankama_id"),
        ("jobs", "jobs", "ankama_id"),
        ("spells", "spells", "ankama_id"),
        ("classes", "classes", "ankama_id"),
        ("monsters", "monsters", "ankama_id"),
        ("monster_families", "monster_families", "ankama_id"),
        ("areas", "areas", "ankama_id"),
        ("subareas", "subareas", "ankama_id"),
        ("interactive_elements", "interactive_elements", "ankama_id"),
        ("effects", "effects", "ankama_id"),
        ("maps", "maps", "map_id"),
    ]
    for bundle_key, table, conflict in table_map:
        for row in bundle.get(bundle_key, []):
            if not isinstance(row, dict):
                continue
            if conflict == "ankama_id" and row.get("ankama_id") is None:
                continue
            if conflict == "map_id" and row.get("map_id") is None:
                continue
            try:
                store.upsert_entity(table, row, conflict_column=conflict)
                counts[bundle_key] += 1
            except Exception as exc:
                bundle.setdefault("warnings", []).append(f"upsert {table} ignore: {exc}")

    for recipe_entry in bundle.get("recipes", []):
        if isinstance(recipe_entry, tuple):
            recipe, ingredients = recipe_entry
        elif isinstance(recipe_entry, dict):
            recipe, ingredients = recipe_entry, []
        else:
            continue
        if not recipe.get("result_ankama_id"):
            continue
        try:
            recipe_id = store.upsert_entity("recipes", recipe, conflict_column="result_ankama_id")
            if ingredients:
                store.replace_recipe_ingredients(recipe_id, ingredients)
                counts["recipe_ingredients"] += len(ingredients)
            counts["recipes"] += 1
        except Exception as exc:
            bundle.setdefault("warnings", []).append(f"upsert recipe ignore: {exc}")

    for cell in bundle.get("cells", []):
        if not isinstance(cell, dict) or cell.get("map_id") is None or cell.get("cell_id") is None:
            continue
        try:
            _upsert_cell(store, cell)
            counts["cells"] += 1
        except Exception as exc:
            bundle.setdefault("warnings", []).append(f"upsert cell ignore: {exc}")

    for text in bundle.get("texts", []):
        if not isinstance(text, dict):
            continue
        try:
            _upsert_text(store, text)
            counts["texts"] += 1
        except Exception as exc:
            bundle.setdefault("warnings", []).append(f"upsert text ignore: {exc}")

    for item_effect in bundle.get("item_effects", []):
        if not isinstance(item_effect, dict) or item_effect.get("item_ankama_id") is None:
            continue
        try:
            _upsert_item_effect(store, item_effect)
            counts["item_effects"] += 1
        except Exception as exc:
            bundle.setdefault("warnings", []).append(f"upsert item_effect ignore: {exc}")

    for condition in bundle.get("conditions", []):
        if not isinstance(condition, dict) or not condition.get("expression"):
            continue
        try:
            _upsert_condition(store, condition)
            counts["conditions"] += 1
        except Exception as exc:
            bundle.setdefault("warnings", []).append(f"upsert condition ignore: {exc}")

    for monster_spell in bundle.get("monster_spells", []):
        if not isinstance(monster_spell, dict):
            continue
        try:
            _upsert_monster_spell(store, monster_spell)
            counts["monster_spells"] += 1
        except Exception as exc:
            bundle.setdefault("warnings", []).append(f"upsert monster_spell ignore: {exc}")

    for class_spell in bundle.get("class_spells", []):
        if not isinstance(class_spell, dict):
            continue
        try:
            _upsert_class_spell(store, class_spell)
            counts["class_spells"] += 1
        except Exception as exc:
            bundle.setdefault("warnings", []).append(f"upsert class_spell ignore: {exc}")

    for raw in bundle.get("raw_objects", []):
        try:
            source, object_type, object_id, path, payload = raw
            store.upsert_raw_object(source, object_type, object_id, path, payload)
            counts["raw_objects"] += 1
        except Exception as exc:
            bundle.setdefault("warnings", []).append(f"raw object ignore: {exc}")

    return counts


def _upsert_cell(store: DataStore, row: dict[str, Any]) -> None:
    prepared = store._prepare_row(row)
    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO cells(map_id, cell_id, walkable, los, source, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(map_id, cell_id) DO UPDATE SET
                walkable=excluded.walkable,
                los=excluded.los,
                source=excluded.source,
                metadata_json=excluded.metadata_json
            """,
            (
                prepared.get("map_id"),
                prepared.get("cell_id"),
                prepared.get("walkable"),
                prepared.get("los"),
                prepared.get("source", ""),
                prepared.get("metadata_json", "{}"),
            ),
        )


def _upsert_text(store: DataStore, row: dict[str, Any]) -> None:
    prepared = store._prepare_row(row)
    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO texts(text_id, lang, text, source, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(text_id, lang) DO UPDATE SET
                text=excluded.text,
                source=excluded.source,
                metadata_json=excluded.metadata_json
            """,
            (
                prepared.get("text_id"),
                prepared.get("lang", "fr"),
                prepared.get("text", ""),
                prepared.get("source", ""),
                prepared.get("metadata_json", "{}"),
            ),
        )


def _upsert_item_effect(store: DataStore, row: dict[str, Any]) -> None:
    prepared = store._prepare_row(row)
    effect_row = None
    if prepared.get("effect_ankama_id") is not None:
        effect_row = store.query_one("SELECT id FROM effects WHERE ankama_id=?", (prepared.get("effect_ankama_id"),))
    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO item_effects(item_ankama_id, effect_id, effect_ankama_id, effect_name_fr, value_int, min_int, max_int, raw_order, source, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_ankama_id, effect_ankama_id, raw_order) DO UPDATE SET
                effect_id=excluded.effect_id,
                effect_name_fr=excluded.effect_name_fr,
                value_int=excluded.value_int,
                min_int=excluded.min_int,
                max_int=excluded.max_int,
                source=excluded.source,
                metadata_json=excluded.metadata_json
            """,
            (
                prepared.get("item_ankama_id"),
                effect_row.get("id") if effect_row else prepared.get("effect_id"),
                prepared.get("effect_ankama_id"),
                prepared.get("effect_name_fr", ""),
                prepared.get("value_int"),
                prepared.get("min_int"),
                prepared.get("max_int"),
                prepared.get("raw_order", 0),
                prepared.get("source", ""),
                prepared.get("metadata_json", "{}"),
            ),
        )


def _upsert_condition(store: DataStore, row: dict[str, Any]) -> None:
    prepared = store._prepare_row(row)
    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO conditions(owner_type, owner_ankama_id, condition_type, expression, source, metadata_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_type, owner_ankama_id, condition_type, expression) DO UPDATE SET
                source=excluded.source,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                prepared.get("owner_type", ""),
                prepared.get("owner_ankama_id"),
                prepared.get("condition_type", ""),
                prepared.get("expression", ""),
                prepared.get("source", ""),
                prepared.get("metadata_json", "{}"),
                now_iso(),
            ),
        )


def _upsert_monster_spell(store: DataStore, row: dict[str, Any]) -> None:
    prepared = store._prepare_row(row)
    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO monster_spells(monster_ankama_id, spell_ankama_id, raw_order, grade_info, source, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(monster_ankama_id, spell_ankama_id, raw_order) DO UPDATE SET
                grade_info=excluded.grade_info,
                source=excluded.source,
                metadata_json=excluded.metadata_json
            """,
            (
                prepared.get("monster_ankama_id"),
                prepared.get("spell_ankama_id"),
                prepared.get("raw_order", 0),
                prepared.get("grade_info", ""),
                prepared.get("source", ""),
                prepared.get("metadata_json", "{}"),
            ),
        )


def _upsert_class_spell(store: DataStore, row: dict[str, Any]) -> None:
    prepared = store._prepare_row(row)
    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO class_spells(class_ankama_id, spell_ankama_id, raw_order, source, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(class_ankama_id, spell_ankama_id, raw_order) DO UPDATE SET
                source=excluded.source,
                metadata_json=excluded.metadata_json
            """,
            (
                prepared.get("class_ankama_id"),
                prepared.get("spell_ankama_id"),
                prepared.get("raw_order", 0),
                prepared.get("source", ""),
                prepared.get("metadata_json", "{}"),
            ),
        )


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Import local Dofus data into SQLite")
    parser.add_argument("--full", action="store_true", help="run every local importer and export JSON")
    parser.add_argument("--offline", action="store_true", help="do not use external APIs")
    parser.add_argument("--with-static-api", action="store_true", help="fetch controlled public static API data into data/raw before import")
    parser.add_argument("--static-api-scope", choices=("recipes", "items", "bestiary", "all"), default="recipes", help="which public static API collections to fetch")
    parser.add_argument("--recipe-page-limit", type=int, default=500, help="DofusDB recipe page size for --with-static-api")
    parser.add_argument("--recipe-max-pages", type=int, default=None, help="limit DofusDB pages for cautious sync/testing")
    args = parser.parse_args(argv)
    offline = args.offline or not args.with_static_api
    report = run_import(
        full=args.full,
        offline=offline,
        with_static_api=args.with_static_api,
        recipe_page_limit=args.recipe_page_limit,
        recipe_max_pages=args.recipe_max_pages,
        static_api_scope=args.static_api_scope,
    )
    console = {
        "sqlite": str(DEFAULT_CONFIG.sqlite_path),
        "counts": report["counts"],
        "image_index": report["image_index"],
        "exports": report["exports"],
        "warnings": len(report["warnings"]),
        "errors": report["errors"],
    }
    print(json.dumps(console, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
