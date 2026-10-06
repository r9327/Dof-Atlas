from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL_MAIN = ROOT / "main.py"
EQUIPMENT = ROOT / "app" / "pages" / "equipment_page.py"
ENCYCLOPEDIA_FACADE = ROOT / "app" / "modules" / "encyclopedia" / "views" / "__init__.py"
ENCYCLOPEDIA_PAGE = ROOT / "app" / "modules" / "encyclopedia" / "views" / "encyclopedia_page.py"
ENCYCLOPEDIA_SERVICE = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "services"
    / "encyclopedia_service.py"
)
PROVIDER_FACADE = ROOT / "app" / "modules" / "encyclopedia" / "providers" / "__init__.py"
DOFUS_ITEM_PROVIDER = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "providers"
    / "dofus_item_provider.py"
)
INDEXED_GUIDE_PROVIDER = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "providers"
    / "indexed_guide_provider.py"
)
MEMORY_PAGE = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "views"
    / "memory_bound_encyclopedia_page.py"
)
MEMORY_GUIDE_PROVIDER = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "providers"
    / "memory_bound_guide_provider.py"
)
MEMORY_ACHIEVEMENT_PROVIDER = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "providers"
    / "memory_bound_achievement_provider.py"
)
RELATED_DATA = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "services"
    / "related_data_service.py"
)
SERVICES_FACADE = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "services"
    / "__init__.py"
)
CRAFT_PAGE = ROOT / "app" / "pages" / "craft_page.py"
CRAFT_PRELOAD = ROOT / "app" / "craft_preload.py"


def test_equipment_runtime_does_not_embed_qt_webengine() -> None:
    source = EQUIPMENT.read_text(encoding="utf-8")
    assert "QtWebEngine" not in source
    assert "QWebEngine" not in source
    assert "QDesktopServices.openUrl" in source
    assert "HUZOUNET_URL" in source


def test_encyclopedia_public_facade_routes_to_memory_bound_page() -> None:
    source = ENCYCLOPEDIA_FACADE.read_text(encoding="utf-8")
    assert "memory_bound_encyclopedia_page" in source
    assert "MemoryBoundEncyclopediaPage as RealEncyclopediaPage" in source


def test_encyclopedia_runtime_constructs_provider_through_memory_facade() -> None:
    source = ENCYCLOPEDIA_SERVICE.read_text(encoding="utf-8")
    assert "from app.modules.encyclopedia.providers import AchievementProvider, QuestProvider" in source
    assert "providers.achievement_provider import AchievementProvider" not in source


def test_encyclopedia_quest_surface_defers_success_and_guide_widgets() -> None:
    source = ENCYCLOPEDIA_PAGE.read_text(encoding="utf-8")
    facade = ENCYCLOPEDIA_FACADE.read_text(encoding="utf-8")
    runtime_imports = source.split("if TYPE_CHECKING:", 1)[0]
    assert "views.achievements_view import AchievementsView" not in runtime_imports
    assert "views.deferred_achievement_guides_view import" not in runtime_imports
    assert "pages.progressive_quests_page import ProgressiveQuestsPage" not in runtime_imports
    loader = facade[
        facade.index("def _load_encyclopedia_page_class"):
        facade.index("class _LazyEncyclopediaPageMeta"),
    ]
    assert "_ensure_guide_view_loaded()" not in loader
    assert "_resolve_achievements_view_type" in source
    assert "_resolve_guides_view_type" in source
    assert "_resolve_progressive_quests_page_type" in source


def test_quest_catalog_defers_rich_detail_view_until_selection() -> None:
    base = (ROOT / "app" / "pages" / "_quests_page_impl.py").read_text(encoding="utf-8")
    canonical = (ROOT / "app" / "pages" / "quests_page.py").read_text(encoding="utf-8")
    runtime_imports = base.split("if TYPE_CHECKING:", 1)[0]
    assert "widgets.quest_detail_view import QuestDetailView" not in runtime_imports
    assert "guide_quest_view_model import" not in runtime_imports
    assert 'kwargs.setdefault("defer_detail_view", True)' in canonical
    assert "def _ensure_quest_detail_view" in base
    assert "QuestDetailDeferred" in base


def test_guide_catalog_defers_detail_and_manual_engines() -> None:
    guide_source = (
        ROOT / "app" / "modules" / "encyclopedia" / "views" / "guides_view.py"
    ).read_text(encoding="utf-8")
    manual_source = (
        ROOT / "app" / "modules" / "encyclopedia" / "views" / "manual_route_guides_view.py"
    ).read_text(encoding="utf-8")
    achievement_source = (
        ROOT / "app" / "modules" / "encyclopedia" / "views" / "achievements_view.py"
    ).read_text(encoding="utf-8")

    guide_runtime_imports = guide_source.split("if TYPE_CHECKING:", 1)[0]
    manual_runtime_imports = manual_source.split("if TYPE_CHECKING:", 1)[0]
    assert "guide_quest_view_model import" not in guide_runtime_imports
    assert "guide_ultime_manual_view import" not in guide_runtime_imports
    assert "guide_ultime_manual_runtime_service import" not in guide_runtime_imports
    assert "guide_auto_validation_contract import" not in guide_runtime_imports
    assert "guide_catalog_manual_runtime_service import" not in manual_runtime_imports
    assert "shared_manual_guide_view import" not in manual_runtime_imports
    assert "achievement_detail_widget import" not in achievement_source.split(
        "_achievement_detail_widget_type", 1
    )[0]
    assert "achievement_entity_section import" not in achievement_source.split(
        "_achievement_entity_row_type", 1
    )[0]


def test_memory_bound_page_hibernates_widgets_and_reconstructible_runtime() -> None:
    source = MEMORY_PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {
        "hibernate_heavy_views",
        "_hibernate_achievements",
        "_hibernate_guides",
        "_release_runtime_providers",
        "_clear_reconstructible_image_cache",
        "prepare_external_tab_navigation",
        "_collect_achievement_runtime",
        "collect_related_preload",
        "ensure_achievements_view",
        "ensure_guides_view",
        "hideEvent",
        "showEvent",
        "on_tab_changed",
    } <= method_names
    assert "release_catalogue" in source
    assert "RelatedPreloadGate()" in source
    assert "_achievement_ready = False" in source
    assert "_guide_runtime_ready = False" in source
    assert "pending_encyclopedia_tab" in source
    assert "_memory_release_runtime_when_idle = False" in source
    assert "ENCYCLOPEDIA_IMAGE_SERVICE" in source
    assert 'sys.modules.get("app.modules.encyclopedia.services.image_service")' in source
    assert "deleteLater()" in source


def test_achievement_provider_releases_reconstructible_source_maps() -> None:
    facade = PROVIDER_FACADE.read_text(encoding="utf-8")
    source = MEMORY_ACHIEVEMENT_PROVIDER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert "memory_bound_achievement_provider" in facade
    assert "MemoryBoundAchievementProvider as RealAchievementProvider" in facade
    assert {
        "_reset_sources",
        "release_catalogue",
        "_trim_catalogue_payload",
        "_load",
        "prepare_detail_sources",
        "get_detail_by_id",
    } <= method_names
    assert "QuestSources(" in source
    assert "self._entries = None" in source
    assert "self._image_indexes.clear()" in source
    assert "_compact_achievement_dict" in source
    assert "_compact_objective_dict" in source
    assert "_DUMP_DETAIL_FLAG" in source
    assert "_dump_default_detail" in source
    assert '"raw"' in source


def test_services_facade_keeps_progress_runtime_lazy() -> None:
    source = SERVICES_FACADE.read_text(encoding="utf-8")
    assert "from app.modules.encyclopedia.services.guide_progress_service import" not in source
    assert "from app.modules.encyclopedia.services.guide_progress_calculator import" not in source
    assert "from app.modules.encyclopedia.services.memory_bound_achievement_progress_service import" not in source
    assert "from app.modules.encyclopedia.services.quest_progress_service import" not in source
    assert '"AchievementProgressService": (' in source
    assert '"GuideProgressCalculator": (' in source
    assert '"GuideProgressService": (' in source
    assert '"QuestProgressService": (' in source


def test_related_index_warmup_runs_outside_long_lived_atlas_process() -> None:
    source = RELATED_DATA.read_text(encoding="utf-8")
    assert "subprocess.run" in source
    assert "achievement_index_warmup" in source
    assert "sys.executable" in source
    assert "QuestSources(" not in source
    assert ".read_bytes()" not in source
    assert 'sys.executable, "-c"' not in source
    assert '"--ensure-compact-cache"' in source
    assert '"--ensure-guide-index"' in source
    assert "QuestGraphService(" not in source
    assert "QuestProvider(catalog=" not in source
    assert "quest_graph=None" in source
    assert "_CACHED_CATALOG = catalog_id" in source

    assert "_run_compact_preload_worker" in source
    assert "memory_bound_achievement_provider" in source
    assert "memory_bound_guide_provider" in source
    assert "dofus_item_provider" in source



def test_dofus_item_extraction_does_not_parse_monolithic_sources_in_parent() -> None:
    source = DOFUS_ITEM_PROVIDER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert {"_load", "_load_one", "_load_in_process", "_dump_compact_default_items"} <= method_names
    assert "QuestSources(" in source
    assert "while len(self._by_id) > 32" in source
    assert "GUIDE_ITEMS_INDEX" in source
    get_by_id = source[source.index("def get_by_id"):source.index("def _guide_index_row")]
    assert "_guide_index_row" in get_by_id
    assert "_load_in_process" not in get_by_id
    assert "QuestSources(" not in get_by_id
    assert "gc.collect()" not in source


def test_guide_name_resolution_uses_prebuilt_index_without_nested_worker() -> None:
    source = INDEXED_GUIDE_PROVIDER.read_text(encoding="utf-8")
    resolver = source[
        source.index("def _achievement_name_index"):
        source.index("def _drop_nested_raw")
    ]
    assert "achievement_names.json" in source
    assert "subprocess.run" not in resolver
    assert "achievement_index_warmup" not in resolver

def test_guide_provider_releases_reconstructible_catalogue() -> None:
    source = MEMORY_GUIDE_PROVIDER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert {"release_catalogue", "release_detail_cache", "_load"} <= method_names
    assert "self._loaded = False" in source
    assert "self._detail_entries = {}" in source

    assert "GUIDE_COMPACT_CACHE" in source
    assert "def _load_from_compact_cache" in source
    load_method = source[source.index("def _load(self)"):source.index("def _load_from_compact_cache")]
    assert "_guide_compact_cache_valid" in load_method


def test_quest_preload_keeps_all_rich_catalogues_off_heap() -> None:
    source = SHELL_MAIN.read_text(encoding="utf-8")
    preload = source[
        source.index("def build_quest_preload("):
        source.index("def build_preload_payload()")
    ]
    assert "AchievementProvider(" not in preload
    assert "_resolve_quest_provider()" not in preload
    assert "_warm_quest_catalogue()" in preload
    assert '"catalog": None' in preload


def test_craft_preload_and_runtime_are_sqlite_bounded() -> None:
    shell = SHELL_MAIN.read_text(encoding="utf-8")
    preload = CRAFT_PRELOAD.read_text(encoding="utf-8")
    page = CRAFT_PAGE.read_text(encoding="utf-8")

    builder = shell[
        shell.index("def build_craft_preload("):
        shell.index("def build_quest_related_preload(")
    ]
    assert '"app.craft_preload"' in builder
    assert "list_craft_items" not in builder
    assert '"_lazy_items": True' in preload
    assert "list_craft_items" not in preload
    assert "list_resources" not in preload
    assert "search_craft_items" in page
    assert "def release_runtime" in page
    assert 'release_reconstructible_page("Craft"' in shell


def test_home_release_collects_deleted_widget_cycles_without_working_set_trim() -> None:
    source = SHELL_MAIN.read_text(encoding="utf-8")
    assert "def collect_released_page_cycles" in source
    cleanup = source[
        source.index("def collect_released_page_cycles"):
        source.index("def release_reconstructible_page"),
    ]
    assert "QApplication.sendPostedEvents(None, QEvent.DeferredDelete)" in cleanup
    assert "gc.collect()" in cleanup
    assert "SetProcessWorkingSetSize" not in cleanup
    home_switch = source[
        source.index('if name == "Home":'):
        source.index('elif name == "Quetes":'),
    ]
    assert "self._schedule_owned_callback(0, self.collect_released_page_cycles)" in home_switch


def test_background_related_preload_keeps_runtime_imports_out_of_parent() -> None:
    source = SHELL_MAIN.read_text(encoding="utf-8")
    related = source[
        source.index("def build_quest_related_preload("):
        source.index("def build_guide_progress_preload(")
    ]
    cold_start = related.index("if catalog is None:")
    runtime_import = related.index(
        "from app.modules.encyclopedia.services import build_related_encyclopedia_data"
    )
    cold_path = related[cold_start:runtime_import]
    assert "_warm_encyclopedia_compact_stores()" in cold_path
    assert "return payload" in cold_path

    collector = source[
        source.index("def collect_preload_result("):
        source.index("def merge_preload_result(")
    ]
    assert "from app.quest_catalog import QuestCatalog" not in collector
    home_switch = source[
        source.index('if name == "Home":'):
        source.index('elif name == "Quetes":')
    ]
    assert 'release_reconstructible_page("Quetes"' in home_switch


def test_shell_encyclopedia_factory_avoids_eager_related_type_imports() -> None:
    source = SHELL_MAIN.read_text(encoding="utf-8")
    factory = source[
        source.index("def create_encyclopedia_page("):
        source.index("def on_encyclopedia_related_data_ready(")
    ]
    assert "AchievementProvider" not in factory
    assert "GuideProvider" not in factory
    assert "QuestGraphService" not in factory
    assert "QuestCatalog" not in factory


def test_shell_announces_explicit_encyclopedia_tab_before_showing_page() -> None:
    source = SHELL_MAIN.read_text(encoding="utf-8")
    method = source[source.index("def open_encyclopedia_tab"):source.index("def finish_pending_encyclopedia_tab")]
    prepare = method.index("prepare_external_tab_navigation")
    show = method.index('self.show_page("Quetes")')
    assert prepare < show
    assert "prepare_navigation(label)" in method


def test_memory_page_prefers_explicit_tab_over_hidden_current_tab() -> None:
    source = MEMORY_PAGE.read_text(encoding="utf-8")
    assert 'label = self._memory_pending_tab_label or self.tabs.tabText(index)' in source
    assert 'if label and label == self._memory_pending_tab_label:' in source


def test_success_catalogue_keeps_rich_objectives_out_of_resident_rows() -> None:
    source = MEMORY_ACHIEVEMENT_PROVIDER.read_text(encoding="utf-8")
    assert '"objectives": []' in source
    assert '"progress_objectives": [' in source
    assert "def progress_objectives_for" in source
    assert "def progress_catalogue" in source
    assert "def count_by_category" in source
    assert "while len(self._compact_summary_cache) > 32" in source
    assert "_DUMP_DETAIL_FLAG" in source

    assert "ACHIEVEMENT_COMPACT_CACHE" in source
    assert "external_start" in source
    assert "def _load_from_compact_cache" in source
    assert "retained_only=True" in source


def test_guide_compact_worker_never_loads_dofus_item_corpus() -> None:
    source = MEMORY_GUIDE_PROVIDER.read_text(encoding="utf-8")
    assert "class _CompactGuideNoopItemProvider" in source
    assert "dofus_item_provider=_CompactGuideNoopItemProvider()" in source
    dump = source[source.index("def _dump_compact_default_guides"):]
    assert "DofusItemProvider(" not in dump


def test_dofus_item_worker_streams_monolithic_doduda_sources() -> None:
    source = DOFUS_ITEM_PROVIDER.read_text(encoding="utf-8")
    assert "def _iter_doduda_refs" in source
    assert '_iter_doduda_refs(items_path)' in source
    assert 'self._read_json(self.data_dir / "items.json"' not in source
    assert 'doduda_rows(self.data_dir / "item_types.json")' not in source
    assert 'doduda_rows(self.data_dir / "effects.json")' not in source


class MemoryPolicyContractUnittest(unittest.TestCase):
    """Expose pytest-style memory policy contracts to Doctor's unittest runner."""

    def test_memory_policy_contracts(self) -> None:
        test_equipment_runtime_does_not_embed_qt_webengine()
        test_encyclopedia_public_facade_routes_to_memory_bound_page()
        test_encyclopedia_runtime_constructs_provider_through_memory_facade()
        test_encyclopedia_quest_surface_defers_success_and_guide_widgets()
        test_quest_catalog_defers_rich_detail_view_until_selection()
        test_guide_catalog_defers_detail_and_manual_engines()
        test_memory_bound_page_hibernates_widgets_and_reconstructible_runtime()
        test_achievement_provider_releases_reconstructible_source_maps()
        test_services_facade_keeps_progress_runtime_lazy()
        test_related_index_warmup_runs_outside_long_lived_atlas_process()
        test_dofus_item_extraction_does_not_parse_monolithic_sources_in_parent()
        test_guide_name_resolution_uses_prebuilt_index_without_nested_worker()
        test_guide_provider_releases_reconstructible_catalogue()
        test_quest_preload_keeps_all_rich_catalogues_off_heap()
        test_craft_preload_and_runtime_are_sqlite_bounded()
        test_home_release_collects_deleted_widget_cycles_without_working_set_trim()
        test_background_related_preload_keeps_runtime_imports_out_of_parent()
        test_shell_announces_explicit_encyclopedia_tab_before_showing_page()
        test_memory_page_prefers_explicit_tab_over_hidden_current_tab()
        test_success_catalogue_keeps_rich_objectives_out_of_resident_rows()
        test_guide_compact_worker_never_loads_dofus_item_corpus()
        test_dofus_item_worker_streams_monolithic_doduda_sources()
