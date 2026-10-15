from __future__ import annotations


def main() -> int:
    import sys

    if sys.argv[1:2] == ["--atlas-package-smoke"]:
        from pathlib import Path
        import PySide6.QtWebEngineWidgets  # noqa: F401
        from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR
        from app.quest_catalog import QUEST_CATALOG_SOURCE_FILES
        from app.modules.encyclopedia.providers.achievement_provider import _DETAIL_SOURCE_FILES
        from app.modules.encyclopedia.providers.memory_bound_achievement_provider import _ACHIEVEMENT_COMPACT_SOURCES
        if not DATA_DIR.is_dir() or not Path(sys.executable).is_file():
            return 3
        # A working Qt window and Quest catalogue are insufficient: the real
        # startup also builds the compact Success cache using dungeon sources.
        required = {source for _label, source in QUEST_CATALOG_SOURCE_FILES}
        required.update(_ACHIEVEMENT_COMPACT_SOURCES)
        required.update(_DETAIL_SOURCE_FILES)
        for source in sorted(required):
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
