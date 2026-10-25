from __future__ import annotations


def main() -> int:
    import sys

    # The elevated capture process runs the same frozen EXE, not a Python
    # interpreter. Dispatch it before importing Qt or acquiring the GUI lock.
    if getattr(sys, "frozen", False) and sys.argv[1:2] == ["--atlas-capture-helper"]:
        from app.network.capture_helper import main as capture_main
        return int(capture_main(sys.argv[2:]))

    if getattr(sys, "frozen", False) and sys.argv[1:2] == ["--atlas-capture-smoke"]:
        # An isolated packaging smoke: verifies helper imports without UAC,
        # opening a capture socket or starting the GUI.
        from app.network.capture_helper import main as capture_main
        return 0 if callable(capture_main) else 2

    if sys.argv[1:2] == ["--atlas-package-smoke"]:
        from pathlib import Path
        import PySide6.QtWebEngineWidgets  # noqa: F401
        from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR
        from app.quest_catalog import QUEST_CATALOG_SOURCE_FILES
        if not DATA_DIR.is_dir() or not Path(sys.executable).is_file():
            return 3
        # This was missing from the earlier frozen Qt smoke: a GUI can open
        # while its required Doduda quest sources were never packaged.
        for _label, source in QUEST_CATALOG_SOURCE_FILES:
            file = RAW_QUEST_DATA_DIR / source
            if not file.is_file() or file.stat().st_size == 0:
                print(f"Missing frozen quest source: {file}", file=sys.stderr)
                return 4
        return 0

    if sys.argv[1:2] == ["--atlas-quest-smoke"]:
        # Exercise the real source parser, not just a directory existence check.
        from app.quest_catalog_details import ensure_lazy_catalog_cache
        count = ensure_lazy_catalog_cache()
        if count <= 0:
            print("Frozen quest catalogue is empty", file=sys.stderr)
            return 5
        print(f"VERIFIED: {count} frozen quests")
        return 0

    if sys.argv[1:2] == ["--atlas-domain-smoke"]:
        domain = sys.argv[2] if len(sys.argv) > 2 else ""
        if domain not in {"guide", "success"}:
            print("Unsupported Atlas domain smoke", file=sys.stderr)
            return 2
        # Certify the same disposable cache-domain builders used by startup.
        from app.startup_cache_domain_worker import run_domain
        result = run_domain(domain)
        tasks = result.get("tasks") or {}
        if domain == "guide":
            catalog = tasks.get("guide") or {}
            items = tasks.get("guide_items") or {}
            if int(catalog.get("guide_count") or 0) <= 0 or int(items.get("item_count") or 0) <= 0:
                print(f"Frozen Guide data incomplete: {tasks}", file=sys.stderr)
                return 6
        else:
            retained = tasks.get("success") or {}
            if int(retained.get("retained_count") or 0) <= 0:
                print(f"Frozen Success data incomplete: {tasks}", file=sys.stderr)
                return 7
        print(f"VERIFIED: frozen {domain} startup data")
        return 0

    if sys.argv[1:2] == ["--atlas-success-detail-smoke"]:
        from app.modules.encyclopedia.providers.achievement_provider import AchievementProvider
        provider = AchievementProvider()
        achievements = provider.load_all()
        candidate = next((item for item in achievements if item.reward_ids), None)
        if candidate is None or provider.get_detail_by_id(candidate.id) is None:
            print("Frozen Success rewards/detail unavailable", file=sys.stderr)
            return 8
        print(f"VERIFIED: frozen Success detail for ID {candidate.id}")
        return 0

    if sys.argv[1:2] == ["--atlas-craft-smoke"]:
        import sqlite3
        from app.craft_preload import build_compact_craft_preload
        from local_dofus_data.config import DEFAULT_CONFIG
        from local_dofus_data.compatibility_adapter import LocalCompatibilityAdapter
        ready = build_compact_craft_preload()
        if not ready.get("_prepared") or ready.get("errors") or not ready.get("jobs"):
            print(f"Frozen Craft preload failed: {ready.get('errors') or ready.get('_skipped_reason')}",
                  file=sys.stderr)
            return 9
        with sqlite3.connect(DEFAULT_CONFIG.sqlite_path) as db:
            item_count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            recipe_count = db.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
            ingredient_count = db.execute("SELECT COUNT(*) FROM recipe_ingredients").fetchone()[0]
            rows = db.execute(
                "SELECT i.name_fr FROM items i JOIN recipes r "
                "ON i.ankama_id=r.result_ankama_id "
                "WHERE i.name_fr<>'' ORDER BY r.id LIMIT 10"
            ).fetchall()
        if item_count < 1000 or recipe_count < 100 or ingredient_count < 100 or not rows:
            print("Frozen Craft catalog incomplete", file=sys.stderr)
            return 10
        adapter = LocalCompatibilityAdapter()
        try:
            results = adapter.search_craft_items(rows[0][0], limit=3)
            if not results:
                print("Frozen Craft search empty", file=sys.stderr)
                return 11
            ident = results[0].get("id_dofus") or results[0].get("ankama_id")
            recipe = adapter.get_recipe(ident)
            if not recipe:
                print("Frozen Craft recipe lookup failed", file=sys.stderr)
                return 12
        finally:
            adapter.close()
        print(f"VERIFIED: frozen Craft catalog {item_count} items, "
              f"{recipe_count} recipes, {ingredient_count} ingredients")
        return 0

    if sys.argv[1:2] == ["--atlas-map-state-smoke"]:
        from app.cartography.world_db import WORLD_DB_PATH, init_db, connection_scope
        from app.constants import USER_DATA_ROOT
        if USER_DATA_ROOT is None:
            print("Frozen map state requires a durable user directory", file=sys.stderr)
            return 13
        expected = USER_DATA_ROOT / "data" / "dofus_atlas_world.db"
        if WORLD_DB_PATH != expected:
            print(f"Map DB path not durable: {WORLD_DB_PATH}", file=sys.stderr)
            return 14
        init_db()
        with connection_scope() as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                print("Frozen map DB failed integrity check", file=sys.stderr)
                return 15
        print(f"VERIFIED: durable world map SQLite at {WORLD_DB_PATH}")
        return 0

    # A frozen executable is not a Python interpreter. It must explicitly
    # dispatch trusted workers instead of interpreting "-m module" as GUI args.
    if getattr(sys, "frozen", False) and sys.argv[1:2] == ["-m"]:
        import runpy

        worker = sys.argv[2] if len(sys.argv) >= 3 else ""
        permitted = {
            "app.craft_preload",
            "app.quest_catalog_details",
            "app.startup_cache_warmup",
            "app.startup_cache_domain_worker",
            "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
            "app.modules.encyclopedia.services.achievement_index_warmup",
            "app.modules.encyclopedia.providers.memory_bound_guide_provider",
            "app.modules.encyclopedia.providers.dofus_item_provider",
        }
        if worker not in permitted:
            print("Unsupported Atlas worker", file=sys.stderr)
            return 2
        sys.argv = [worker, *sys.argv[3:]]
        runpy.run_module(worker, run_name="__main__", alter_sys=True)
        return 0

    import main as app_main
    return int(app_main.main())


if __name__ == "__main__":
    raise SystemExit(main())
