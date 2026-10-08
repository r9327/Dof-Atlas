from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL_MAIN = ROOT / "main.py"
EQUIPMENT = ROOT / "app" / "pages" / "equipment_page.py"
ENCYCLOPEDIA_FACADE = ROOT / "app" / "modules" / "encyclopedia" / "views" / "__init__.py"
ENCYCLOPEDIA_PAGE = ROOT / "app" / "modules" / "encyclopedia" / "views" / "encyclopedia_page.py"
GUIDE_CATALOG_VIEW = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "views"
    / "guide_catalog_view.py"
)
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
STARTUP_CACHE_WARMUP = ROOT / "app" / "startup_cache_warmup.py"
STARTUP_CACHE_DOMAIN_WORKER = ROOT / "app" / "startup_cache_domain_worker.py"
NETWORK_BRIDGE = ROOT / "app" / "ui" / "network_bridge.py"
NETWORK_COORDINATOR = ROOT / "app" / "network" / "application_coordinator.py"
WINDOWS_LAUNCHER = ROOT / "DOFUS.bat"
PHASE8_MEMORY_WORKFLOW = ROOT / ".github" / "workflows" / "phase8-memory-benchmark.yml"
QUESTS_PAGE_IMPL = ROOT / "app" / "pages" / "_quests_page_impl.py"
GUIDES_VIEW = ROOT / "app" / "modules" / "encyclopedia" / "views" / "guides_view.py"
GUIDE_MANUAL_CORE = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "services"
    / "guide_ultime_manual_runtime_core.py"
)


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


def test_encyclopedia_service_keeps_success_and_guide_providers_cold() -> None:
    source = ENCYCLOPEDIA_SERVICE.read_text(encoding="utf-8")
    runtime_imports = source.split("if TYPE_CHECKING:", 1)[0]
    assert "providers.memory_bound_guide_provider import" not in runtime_imports
    assert "providers.guide_provider import" not in runtime_imports
    assert "self._achievement_provider = achievement_provider" in source
    assert "self._guide_provider = guide_provider" in source
    assert "def peek_achievement_provider" in source
    assert "def peek_guide_provider" in source
    assert "AchievementProvider(quest_provider=self.quest_provider)" in source


def test_quest_graph_does_not_import_success_provider_for_safe_int() -> None:
    source = (
        ROOT / "app" / "modules" / "encyclopedia" / "services" / "quest_graph_service.py"
    ).read_text(encoding="utf-8")
    assert "providers.achievement_provider import safe_int" not in source
    assert "def safe_int(" in source


def test_encyclopedia_quest_surface_defers_success_and_guide_widgets() -> None:
    source = ENCYCLOPEDIA_PAGE.read_text(encoding="utf-8")
    facade = ENCYCLOPEDIA_FACADE.read_text(encoding="utf-8")
    runtime_imports = source.split("if TYPE_CHECKING:", 1)[0]
    assert "views.achievements_view import AchievementsView" not in runtime_imports
    assert "views.deferred_achievement_guides_view import" not in runtime_imports
    assert "pages.progressive_quests_page import ProgressiveQuestsPage" not in runtime_imports
    loader = facade[
        facade.index("def _load_encyclopedia_page_class"):
        facade.index("class _LazyEncyclopediaPageMeta")
    ]
    assert "_ensure_guide_view_loaded()" not in loader
    assert "_resolve_achievements_view_type" in source
    assert "_resolve_guides_view_type" in source
    assert "_resolve_progressive_quests_page_type" in source


def test_quests_surface_avoids_eager_widget_barrel_import() -> None:
    source = QUESTS_PAGE_IMPL.read_text(encoding="utf-8")
    runtime_imports = source.split("if TYPE_CHECKING:", 1)[0]
    assert "from app.modules.encyclopedia.widgets import" not in runtime_imports
    assert "widgets.dashboard import" in runtime_imports
    assert "widgets.detail_panel import DetailPanel" in runtime_imports
    assert "widgets.quest_widgets import QUEST_ID_ROLE, QuestListModel" in runtime_imports
    assert "widgets.quest_detail_view import" not in runtime_imports


def test_guide_catalog_surface_defers_rich_guide_module_until_selection() -> None:
    catalog_source = GUIDE_CATALOG_VIEW.read_text(encoding="utf-8")
    assert "views.guides_view" not in catalog_source
    assert "manual_route_guides_view" not in catalog_source
    assert "deferred_achievement_guides_view" not in catalog_source
    assert "guide_catalog_route_stats" not in catalog_source
    assert "guide_catalog_hints" in catalog_source
    assert "GuideListModel" in catalog_source
    assert "GuideCardDelegate" in catalog_source
    assert "guideRequested = Signal(str)" in catalog_source

    page_source = ENCYCLOPEDIA_PAGE.read_text(encoding="utf-8")
    catalog_resolver = page_source[
        page_source.index("def _resolve_guide_catalog_view_type"):
        page_source.index("def _resolve_guides_view_type")
    ]
    assert "guide_catalog_view import GuideCatalogView" in catalog_resolver
    assert "_ensure_guide_view_loaded" not in catalog_resolver

    catalogue_factory = page_source[
        page_source.index("def ensure_guides_view"):
        page_source.index("def ensure_full_guides_view")
    ]
    assert "_resolve_guide_catalog_view_type()" in catalogue_factory
    assert "_resolve_guides_view_type()" not in catalogue_factory
    assert "guideRequested.connect(self.navigate_to_guide)" in catalogue_factory

    full_factory = page_source[
        page_source.index("def ensure_full_guides_view"):
        page_source.index("def open_pending_lazy_tab")
    ]
    assert "_resolve_guides_view_type()" in full_factory
    assert "defer_runtime=not self._guide_runtime_ready" in full_factory

    restore_source = MEMORY_PAGE.read_text(encoding="utf-8")
    assert "super().ensure_full_guides_view()" in restore_source

    guide_card_source = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "widgets"
        / "guide_card.py"
    ).read_text(encoding="utf-8")
    assert "dofus_item_provider" not in guide_card_source

    hint_source = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "guide_catalog_hints.py"
    ).read_text(encoding="utf-8")
    assert "guide_quest_view_model" not in hint_source
    assert '"dofus_sylvestre": 237' in hint_source


def test_quest_catalog_defers_rich_detail_view_until_selection() -> None:
    base = (ROOT / "app" / "pages" / "_quests_page_impl.py").read_text(encoding="utf-8")
    canonical = (ROOT / "app" / "pages" / "quests_page.py").read_text(encoding="utf-8")
    runtime_imports = base.split("if TYPE_CHECKING:", 1)[0]
    assert "widgets.quest_detail_view import QuestDetailView" not in runtime_imports
    assert "guide_quest_view_model import" not in runtime_imports
    assert 'kwargs.setdefault("defer_detail_view", True)' in canonical
    assert "def _ensure_quest_detail_view" in base
    assert "QuestDetailDeferred" in base


def test_success_progress_sync_streams_compact_rows() -> None:
    provider_source = MEMORY_ACHIEVEMENT_PROVIDER.read_text(encoding="utf-8")
    progress_source = (
        ROOT / "app" / "modules" / "encyclopedia" / "services" / "progress_service.py"
    ).read_text(encoding="utf-8")
    assert "iter_progress_achievement_ids" in progress_source
    assert "progress_row_by_id" in progress_source
    assert "streaming_progress" in progress_source
    assert "progress_achievement(aid)" in progress_source
    sync = progress_source[
        progress_source.index("def sync_from_quest_progress"):
        progress_source.index("def _alignment_main_quest_ids")
    ]
    assert "guide_path_profiles import ORDER_QUEST_IDS" not in sync
    assert "ALIGNMENT_ORDER_QUEST_IDS" in sync
    assert "with ACHIEVEMENT_COMPACT_CACHE.open(\"rb\") as stream:" in provider_source


def test_success_catalog_keeps_alignment_route_profiles_cold() -> None:
    source = (
        ROOT / "app" / "modules" / "encyclopedia" / "views" / "achievements_view.py"
    ).read_text(encoding="utf-8")
    runtime_imports = source.split("def _alignment_order_achievement_ranks", 1)[0]
    assert "guide_path_profiles import ORDER_QUEST_IDS" not in runtime_imports
    assert "achievement_catalog_policy import (" not in runtime_imports
    assert "def _order_quest_ids" in source
    initializer = source[
        source.index("def _initialize_achievements_view"):
        source.index("def show_runtime_loading")
    ]
    assert "if defer_runtime" in initializer
    assert "quest_graph or QuestGraphService" in initializer


def test_success_list_materializes_only_visible_batches() -> None:
    source = (
        ROOT / "app" / "modules" / "encyclopedia" / "views" / "achievements_view.py"
    ).read_text(encoding="utf-8")
    provider = MEMORY_ACHIEVEMENT_PROVIDER.read_text(encoding="utf-8")
    assert "_INITIAL_RESULT_ROWS = 16" in source
    assert "verticalScrollBar().valueChanged.connect" in source
    assert "def _maybe_render_more_achievement_rows" in source
    assert 'getattr(self.provider, "catalogue_ids", None)' in source
    assert 'getattr(self.provider, "catalogue_row_by_id", None)' in source
    assert "def catalogue_ids(" in provider
    assert "def catalogue_row_by_id(" in provider

    refresh = source[
        source.index("def refresh(self)"):
        source.index("def _apply_pending_achievement_selection")
    ]
    assert "self._achievement_pending_rows = [" in refresh
    assert "int(achievement.id)" in refresh
    assert "self.provider.get_by_category" not in refresh

    render = source[
        source.index("def _render_next_achievement_batch"):
        source.index("def _maybe_render_more_achievement_rows")
    ]
    assert "self.list_widget.count() < _INITIAL_RESULT_ROWS" in render
    assert "catalogue_row_by_id" in render


def test_achievement_sync_uses_compact_alignment_guide_ids() -> None:
    source = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "progress_service.py"
    ).read_text(encoding="utf-8")
    helper = source[
        source.index("def _alignment_main_quest_ids"):
        source.index("def save", source.index("def _alignment_main_quest_ids"))
    ]
    assert 'getattr(guide_provider, "progress_quest_ids_for", None)' in helper
    compact_pos = helper.index("compact_ids(guide_id)")
    detail_pos = helper.index("guide_provider.get_by_id(guide_id)")
    assert compact_pos < detail_pos


def test_guide_home_worker_keeps_quest_catalogue_and_graph_cold() -> None:
    source = ENCYCLOPEDIA_PAGE.read_text(encoding="utf-8")

    request = source[
        source.index("def request_related_preload"):
        source.index("def collect_related_preload")
    ]
    worker = request[
        request.index("def worker()"):
        request.index("self.guideRuntimeFinished.emit")
    ]
    assert "quest_provider.get_catalog()" not in worker
    assert "QuestGraphService(" not in worker
    assert "_build_guide_progress_snapshot(" in worker

    snapshot = source[
        source.index("def _build_guide_progress_snapshot"):
        source.index("def _build_quests_page_progressive")
    ]
    assert 'getattr(guide_provider, "progress_quest_ids_for", None)' in snapshot
    assert "QuestProgressService(" in snapshot
    assert "completed_quest_ids(" in snapshot
    assert "GuideProgressCalculator(" not in snapshot
    assert "QuestCatalog" not in snapshot

    payload = source[
        source.index("class _GuideStagePayload"):
        source.index("class _AchievementStagePayload")
    ]
    assert "QuestGraphService | None" in payload


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
        "_finish_in_process_catalogue",
        "_load_disposable_worker_fast",
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
    compact_builder = source[
        source.index("def _build_compact_cache("):
        source.index("def _dump_default_detail(")
    ]
    assert "provider._load_disposable_worker_fast()" in compact_builder
    assert "provider._load_in_process()" not in compact_builder
    fast_loader = source[
        source.index("def _load_disposable_worker_fast("):
        source.index("def _install_compact_rows(")
    ]
    assert '"quest_details_v1" / "source_offsets"' in fast_loader
    assert "self._sources = QuestSources(shared_source_offsets)" in fast_loader


def test_guide_same_character_assignment_does_not_rerender_route() -> None:
    source = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "views"
        / "guide_ultime_generated_view.py"
    ).read_text(encoding="utf-8")
    setter = source[
        source.index("def set_character_key"):
        source.index("def refresh_external_progress", source.index("def set_character_key"))
    ]
    assert "if normalized == self.character_key" in setter
    assert "return" in setter


def test_guide_render_uses_compact_quest_evidence_not_rich_steps() -> None:
    provider = (
        ROOT / "app" / "modules" / "encyclopedia" / "providers" / "quest_provider.py"
    ).read_text(encoding="utf-8")
    manual = (
        ROOT / "app" / "modules" / "encyclopedia" / "views" / "guide_ultime_manual_view.py"
    ).read_text(encoding="utf-8")
    assert "def guide_evidence" in provider
    resource_start = manual.index("def _clickable_resource_names")
    combat_start = manual.index("def _quest_combat_targets", resource_start)
    assert "quest_items_from_objectives" not in manual[resource_start:combat_start]
    combat_end = manual.index("@classmethod", combat_start)
    assert ".steps" not in manual[combat_start:combat_end]
    assert 'evidence = getattr(provider, "guide_evidence"' in manual


def test_shared_manual_card_does_not_materialize_lines_before_sections() -> None:
    source = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "views"
        / "shared_manual_guide_view.py"
    ).read_text(encoding="utf-8")
    constructor = source[
        source.index("class SharedGuideManualCard"):
        source.index("def _render_window", source.index("class SharedGuideManualCard"))
    ]
    section_pos = constructor.index('section_provider = getattr(service, "manual_sections_for_card"')
    line_pos = constructor.index('line_provider = getattr(service, "manual_lines_for_card"')
    assert section_pos < line_pos
    assert "Do not call" in constructor


def test_guide_navigation_materializes_only_one_chapter_at_a_time() -> None:
    source = GUIDES_VIEW.read_text(encoding="utf-8")
    initializer = source[
        source.index("def _ensure_chapters_initialized"):
        source.index("@staticmethod", source.index("def _ensure_chapters_initialized"))
    ]
    assert "self.expanded_chapters[guide.id] = {selected[1].id}" in initializer
    assert "for chapter in part.chapters" in initializer
    assert "self.expanded_chapters[guide.id] = (" in initializer

    toggle = source[
        source.index("def toggle_chapter"):
        source.index("def step_for_quest", source.index("def toggle_chapter"))
    ]
    assert "opened.add(" not in toggle
    assert "self.expanded_chapters[guide.id] = {str(chapter_id)}" in toggle

    detail = source[
        source.index("def show_quest_detail"):
        source.index("def open_quest_from_guide", source.index("def show_quest_detail"))
    ]
    assert "self.expanded_chapters[guide.id] = {series_ref[1].id}" in detail


def test_guide_manual_runtime_keeps_only_visible_authored_stage_hot() -> None:
    core = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "guide_ultime_manual_runtime_core.py"
    ).read_text(encoding="utf-8")
    conditions = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "guide_ultime_manual_conditions.py"
    ).read_text(encoding="utf-8")
    runtime = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "guide_ultime_manual_runtime_service.py"
    ).read_text(encoding="utf-8")

    assert "def _stage_to_compact_card" in core
    assert "card = self._stage_to_compact_card(" in core
    assert "if self.compact_runtime" in core
    assert 'card["manual_source_file"] = filename' in core
    assert 'card["manual_stage_position"] = int(stage_position)' in core
    assert "def _hydrate_manual_card_source" in core
    assert 'previous.pop("manual_stage_data", None)' in core
    assert '"_hydrate_manual_card_source"' in conditions
    assert "dict(card) if self.compact_runtime else copy.deepcopy(card)" in runtime


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


def test_encyclopedia_preload_workers_do_not_capture_parent_payloads() -> None:
    source = SHELL_MAIN.read_text(encoding="utf-8")
    runner = source[
        source.index("def _run_preload_module_status("):
        source.index("def build_quest_related_preload(")
    ]
    quest_warmup = source[
        source.index("def _warm_quest_catalogue("):
        source.index("def build_quest_preload(")
    ]
    craft_builder = source[
        source.index("def build_craft_preload("):
        source.index("def _run_preload_module_status(")
    ]
    assert "QProcess" not in runner
    assert "subprocess.run(" in runner
    assert "subprocess.DEVNULL" in runner
    assert "capture_output=True" not in runner
    assert "subprocess.PIPE" not in runner
    assert "os.spawnve(" not in runner
    assert '"creationflags"' in runner
    assert "CREATE_NO_WINDOW" in runner
    assert "_run_preload_module_json" not in runner
    assert "_run_preload_module_result(" in quest_warmup
    assert "_run_preload_module_result(" in craft_builder
    assert runner.count("_run_preload_module_status(") >= 4


def test_launcher_prewarms_reconstructible_caches_before_long_lived_atlas() -> None:
    shell = SHELL_MAIN.read_text(encoding="utf-8")
    warmup = STARTUP_CACHE_WARMUP.read_text(encoding="utf-8")
    domain_worker = STARTUP_CACHE_DOMAIN_WORKER.read_text(encoding="utf-8")
    launcher = WINDOWS_LAUNCHER.read_text(encoding="utf-8")
    workflow = PHASE8_MEMORY_WORKFLOW.read_text(encoding="utf-8")

    assert (
        'STARTUP_CACHE_WARMUP_TOKEN_ENV = "DOFUS_ATLAS_CACHE_WARMUP_TOKEN"'
        in shell
    )
    assert "def _startup_cache_warmup_payload" in shell
    assert "def _startup_cache_warmup_stamp" in shell
    assert "def _await_startup_cache_warmup" in shell
    awaiter = shell[
        shell.index("def _await_startup_cache_warmup"):
        shell.index("def _warm_encyclopedia_compact_stores")
    ]
    assert "_startup_cache_warmup_stamp()" in awaiter
    assert "stamp != last_stamp" in awaiter
    assert awaiter.count("_startup_cache_warmup_payload()") == 1
    assert "sleep(0.25)" in awaiter
    assert 'in {"ready", "failed"}' in awaiter
    quest_warmup = shell[
        shell.index("def _warm_quest_catalogue"):
        shell.index("def build_quest_preload")
    ]
    assert "_await_startup_cache_warmup()" in quest_warmup
    assert 'prewarmed.get("status") or "") == "ready"' in quest_warmup
    assert "prewarmed_count > 0" in quest_warmup
    encyclopedia_warmup = shell[
        shell.index("def _warm_encyclopedia_compact_stores"):
        shell.index("def build_quest_related_preload")
    ]
    assert "_await_startup_cache_warmup()" in encyclopedia_warmup
    assert 'prewarmed.get("encyclopedia_ready")' in encyclopedia_warmup
    assert "_run_preload_module_status(" in encyclopedia_warmup

    assert '_DOMAIN_ORDER = ("guide", "quest", "success")' in warmup
    assert '"app.startup_cache_domain_worker"' in warmup
    assert "STARTUP_CACHE_MANIFEST" in warmup
    assert "startup_cache_manifest_v1.json" in warmup
    assert "def _source_stamp(" in warmup
    assert "def _artifact_stamp(" in warmup
    assert "def _quest_artifact_stamp(" in warmup
    assert "sqlite3.connect(" in warmup
    assert "def _cached_domain_result(" in warmup
    assert '"mode": mode' in warmup
    assert '"encyclopedia_ready": encyclopedia_ready' in warmup
    assert '"status": "running"' in warmup
    assert '"status": "ready"' in warmup
    assert '"status": "failed"' in warmup
    assert "startup_cache_warmup_v1.json" in warmup

    assert '"guide": _guide_domain' in domain_worker
    assert '"quest": _quest_domain' in domain_worker
    assert '"success": _success_domain' in domain_worker
    assert "_build_compact_guide_cache" in domain_worker
    assert "_build_manual_runtime_compact_cache_in_worker" in domain_worker
    assert "_build_guide_items_index" in domain_worker
    assert "ensure_lazy_catalog_cache()" in domain_worker
    assert "_build_compact_cache" in domain_worker
    assert "write_achievement_name_index()" in domain_worker
    assert "subprocess.run(" not in domain_worker

    assert "DOFUS_ATLAS_CACHE_WARMUP_TOKEN" in launcher
    assert "-m app.startup_cache_warmup --token" in launcher
    assert "start \"\" /b" in launcher
    assert "DOFUS_ATLAS_CACHE_WARMUP_TOKEN" in workflow
    assert "Start-Process" in workflow
    assert "app.startup_cache_warmup" in workflow
    assert "warmup.cold.json" in workflow
    assert "warmup.hot.json" in workflow
    assert '$hotPayload.domains.$domain.mode -ne "reused"' in workflow
    assert "$hotPayload.elapsed_ms -gt 5000.0" in workflow


def test_manual_guide_route_is_precompiled_inside_existing_guide_worker() -> None:
    shell = SHELL_MAIN.read_text(encoding="utf-8")
    core = GUIDE_MANUAL_CORE.read_text(encoding="utf-8")
    worker = MEMORY_GUIDE_PROVIDER.read_text(encoding="utf-8")

    assert 'app.guide_manual_preload' not in shell
    assert "MANUAL_RUNTIME_COMPACT_CACHE" in core
    assert "restore_manual_runtime_compact_cache(self)" in core
    assert "_build_manual_runtime_compact_cache_in_worker" in worker
    assert "write_manual_runtime_compact_cache(service)" in worker
    assert "compact_runtime=True" in worker
    assert "use_disk_cache=False" in worker


def test_quests_keep_success_and_guide_progress_engines_lazy() -> None:
    shell = ENCYCLOPEDIA_PAGE.read_text(encoding="utf-8")
    quests = QUESTS_PAGE_IMPL.read_text(encoding="utf-8")

    runtime_imports = shell.split("if TYPE_CHECKING:", 1)[0]
    assert "AchievementProgressService," not in runtime_imports
    assert "GuideProgressService," not in runtime_imports
    assert "lazy_achievement_progress_service" in shell
    assert "lazy_guide_progress_service" in shell
    assert "AchievementProgressService," not in quests.split("if TYPE_CHECKING:", 1)[0]
    assert "lazy_achievement_progress_service" in quests


def test_disk_only_preload_does_not_import_home_encyclopedia_runtime() -> None:
    shell = SHELL_MAIN.read_text(encoding="utf-8")
    home = (
        ROOT / "app" / "pages" / "home_page.py"
    ).read_text(encoding="utf-8")

    apply_home = shell[
        shell.index("def apply_home_preload_update"):
        shell.index("def apply_encyclopedia_preload_update")
    ]
    assert "if not any(" in apply_home
    assert '("catalog", "guide_provider", "achievement_provider")' in apply_home
    assert apply_home.index("if not any(") < apply_home.index(
        "self.home_page.apply_encyclopedia_context"
    )

    apply_context = home[
        home.index("def apply_encyclopedia_context"):
        home.index("def release_encyclopedia_context")
    ]
    early_return = (
        "if catalog is None and guide_provider is None and "
        "achievement_provider is None:"
    )
    assert early_return in apply_context
    assert apply_context.index(early_return) < apply_context.index(
        "from app.modules.encyclopedia.providers import"
    )


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
        source.index("def release_reconstructible_page")
    ]
    assert "QApplication.sendPostedEvents(None, QEvent.DeferredDelete)" in cleanup
    assert "gc.collect()" in cleanup
    assert "SetProcessWorkingSetSize" not in cleanup
    home_switch = source[
        source.index('if name == "Home":'):
        source.index('elif name == "Quetes":')
    ]
    assert "self._schedule_owned_callback(0, self.collect_released_page_cycles)" in home_switch


def test_preload_retry_reuses_one_qtimer_per_task() -> None:
    source = SHELL_MAIN.read_text(encoding="utf-8")
    init = source[
        source.index("self.preload_state_lock = Lock()"):
        source.index("self.pending_page_name =")
    ]
    assert "self.preload_retry_timers: dict[str, QTimer] = {}" in init
    assert "self.preload_retry_priority: dict[str, bool] = {}" in init

    helper = source[
        source.index("def _schedule_preload_retry("):
        source.index("def build_top_nav(")
    ]
    assert "self.preload_retry_timers.get(key)" in helper
    assert "self.preload_retry_timers[key] = timer" in helper
    assert "if not timer.isActive()" in helper
    assert "timer.deleteLater" not in helper

    preload = source[
        source.index("def start_preload("):
        source.index("def collect_preload_result(")
    ]
    assert preload.count("self._schedule_preload_retry(") >= 3
    assert "lambda target=task, priority=user_requested: self.start_preload(" not in preload

    collector = source[
        source.index("def collect_preload_result("):
        source.index("def merge_preload_result(")
    ]
    assert "if self.preload_queue.empty():" in collector
    assert collector.index("if self.preload_queue.empty():") < collector.index("while True:")


def test_idle_shell_keeps_macro_runtime_cold_without_clients() -> None:
    source = SHELL_MAIN.read_text(encoding="utf-8")

    start = source[
        source.index("def start_runtime"):
        source.index("def stop_runtime")
    ]
    cold_gate = "if not self._runtime_client_mapping_signature():"
    assert cold_gate in start
    assert start.index(cold_gate) < start.index("self._ensure_runtime().start()")

    refresh = source[
        source.index("def _refresh_runtime_hotkeys_for_client_mapping"):
        source.index("def open_encyclopedia_tab")
    ]
    assert "if runtime is None:" in refresh
    assert "if not desired:" in refresh
    assert "runtime = self._ensure_runtime()" in refresh


def test_idle_network_poll_does_not_drain_empty_queues() -> None:
    bridge = NETWORK_BRIDGE.read_text(encoding="utf-8")
    coordinator = NETWORK_COORDINATOR.read_text(encoding="utf-8")

    poll = bridge[
        bridge.index("def _poll(self)"):
        bridge.index("def _emit_pending_progress")
    ]
    assert "if not self.coordinator.has_pending_ui_events():" in poll
    assert poll.index("has_pending_ui_events") < poll.index("drain_statuses")

    gate = coordinator[
        coordinator.index("def has_pending_ui_events"):
        coordinator.index("def stop(")
    ]
    assert "not self._statuses.empty()" in gate
    assert "not self._results.empty()" in gate
    assert "if self._statuses.empty():" in gate
    assert "if self._results.empty():" in gate


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


def test_home_release_clears_loaded_manual_guide_bundle_cache_without_importing_it() -> None:
    source = MEMORY_PAGE.read_text(encoding="utf-8")
    helper = source[
        source.index("def _clear_reconstructible_manual_guide_cache"):
        source.index("def _release_runtime_providers")
    ]
    assert "sys.modules.get" in helper
    assert "guide_ultime_manual_runtime_core" in helper
    assert "clear_manual_bundle_cache" in helper
    assert "guide_ultime_manual_route" in helper
    assert "clear_manual_route_cache" in helper
    assert "guide_auto_validation_contract" in helper
    assert "clear_auto_validation_contract_cache" in helper
    assert "from app.modules.encyclopedia.services.guide_ultime" not in helper

    release = source[
        source.index("def _release_runtime_providers"):
        source.index("def prepare_external_tab_navigation")
    ]
    assert "self._clear_reconstructible_manual_guide_cache()" in release


def test_atlas_manual_guide_disables_bundle_copy_and_wrapper_duplicate_snapshots() -> None:
    view_source = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "views"
        / "manual_route_guides_view.py"
    ).read_text(encoding="utf-8")
    assert "cache_manual_bundle=False" in view_source

    core_source = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "guide_ultime_manual_runtime_core.py"
    ).read_text(encoding="utf-8")
    uncached_load = core_source[
        core_source.index("def _load_manual_preview_uncached"):
        core_source.index("def _load_manual_preview(self)")
    ]
    chapter_loop = uncached_load.index("for chapter_meta in chapters:")
    chapter_memo = uncached_load.index("chapter_memo:")
    assert chapter_loop < chapter_memo

    load = core_source[
        core_source.index("def _load_manual_preview(self)"):
        core_source.index("def manual_audit")
    ]
    assert "if not self.cache_manual_bundle:" in load
    assert "self._load_manual_preview_uncached()" in load

    wrapper_source = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "guide_ultime_manual_runtime_service.py"
    ).read_text(encoding="utf-8")
    stage = wrapper_source[
        wrapper_source.index("def _stage_to_card"):
        wrapper_source.index("def _raw_stage_lines")
    ]
    assert "copy.deepcopy(stage)" not in stage
    assert "copy.deepcopy(chapter_preparation" not in stage

    runtime_open = view_source[
        view_source.index("def ensure_guide_ultime_view"):
        view_source.index("def ensure_catalog_manual_view")
    ]
    assert "build_route_auto_validation_contract" not in runtime_open
    assert "service.auto_validation_contract = None" in runtime_open

    core_stage = core_source[
        core_source.index("def _stage_to_card"):
        core_source.index("def manual_sections_for_card")
    ]
    assert '"manual_stage_data": stage' in core_stage
    assert '"manual_chapter_preparation": chapter_preparation or []' in core_stage
    assert '"manual_stage_data": copy.deepcopy(stage)' not in core_stage
    assert '"manual_lines": [] if bool(getattr(self, "compact_runtime", False)) else lines' in core_stage
    assert '"manual_has_lines": bool(lines)' in core_stage
    assert '"manual_search_text": manual_search_text' in core_stage

    assert "compact_runtime=True" in runtime_open

    conditions_source = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "guide_ultime_manual_conditions.py"
    ).read_text(encoding="utf-8")
    success_index = conditions_source[
        conditions_source.index("def _manual_achievement_name_index"):
        conditions_source.index("def _manual_order_gate_for_card_uncached")
    ]
    assert "compact_name_index" in success_index
    assert success_index.index("compact_name_index") < success_index.index("provider.load_all")

    manual_lines = conditions_source[
        conditions_source.index("def manual_lines_for_card"):
        conditions_source.index("def card_automatic_values")
    ]
    assert "_manual_base_lines_cache" in manual_lines
    assert "manual_has_lines" in manual_lines
    assert "self._stage_lines(" in manual_lines


def test_guide_auto_validation_uses_streamed_success_name_index_first() -> None:
    provider = MEMORY_ACHIEVEMENT_PROVIDER.read_text(encoding="utf-8")
    compact_names = provider[
        provider.index("def compact_name_index"):
        provider.index("def retained_count")
    ]
    assert "ACHIEVEMENT_COMPACT_CACHE.open" in compact_names
    assert 'row.get("kind") != "achievement"' in compact_names
    assert "read_json_file" not in compact_names
    assert "doduda_rows" not in compact_names

    contract = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "guide_auto_validation_contract.py"
    ).read_text(encoding="utf-8")
    index = contract[
        contract.index("def _achievement_index("):
        contract.index("def _quantified_hints")
    ]
    compact_pos = index.index("compact_name_index")
    raw_pos = index.index("read_json_file")
    assert compact_pos < raw_pos


def test_guide_manual_runtime_uses_sqlite_quest_name_index_before_catalogue() -> None:
    provider = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "providers"
        / "quest_provider.py"
    ).read_text(encoding="utf-8")
    compact = provider[
        provider.index("def compact_name_index"):
        provider.index("def list_quests")
    ]
    assert "load_quest_name_index" in compact
    assert "get_catalog()" not in compact

    details = (ROOT / "app" / "quest_catalog_details.py").read_text(encoding="utf-8")
    index = details[
        details.index("def load_quest_name_index"):
        details.index("class NetworkQuestRecord")
    ]
    assert 'SELECT id, name FROM quests ORDER BY id' in index
    assert "load_lazy_catalog(" not in index

    runtime = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "guide_ultime_manual_runtime_core.py"
    ).read_text(encoding="utf-8")
    builder = runtime[
        runtime.index("def _build_quest_name_index"):
        runtime.index("def _load_manual_preview_uncached")
    ]
    compact_pos = builder.index("compact_name_index")
    fallback_pos = builder.index("provider.list_quests()")
    assert compact_pos < fallback_pos


def test_success_catalogue_keeps_rich_objectives_out_of_resident_rows() -> None:
    source = MEMORY_ACHIEVEMENT_PROVIDER.read_text(encoding="utf-8")
    assert '"objectives": []' in source
    assert '"progress_objectives": [' in source
    assert "def progress_objectives_for" in source
    assert "def progress_catalogue" in source
    assert "def iter_progress_achievement_ids" in source
    assert "def progress_row_by_id" in source
    assert "def count_by_category" in source
    assert "while len(self._compact_summary_cache) > 32" in source
    assert "_DUMP_DETAIL_FLAG" in source

    assert "ACHIEVEMENT_COMPACT_CACHE" in source
    assert "external_start" in source
    assert "def _load_from_compact_cache" in source
    compact_load = source[
        source.index("def _load_from_compact_cache"):
        source.index("def _load_from_compact_subprocess")
    ]
    assert "self._achievements = []" in compact_load
    assert "self._compact_retained_ids = retained_ids" in compact_load
    assert "self._compact_external_index = offsets" in compact_load


def test_guide_home_uses_virtualized_delegate_instead_of_widget_forest() -> None:
    source = (
        ROOT / "app" / "modules" / "encyclopedia" / "views" / "guides_view.py"
    ).read_text(encoding="utf-8")
    home = source[
        source.index("def build_home_page"):
        source.index("def build_detail_page")
    ]
    refresh = source[
        source.index("def _refresh_home_uncached"):
        source.index("def _initial_home_progress_uncached")
    ]
    assert "QListView()" in home
    assert "GuideCardDelegate" in home
    assert "GuideHomeCard(" not in refresh
    loading = source[
        source.index("def _show_runtime_loading"):
        source.index("def hydrate_runtime")
    ]
    assert "clear_layout(self.home_layout)" not in loading
    assert "self.home_list.setVisible(False)" in loading
    assert "self.home_empty.setVisible(True)" in loading

    provider = MEMORY_GUIDE_PROVIDER.read_text(encoding="utf-8")
    assert "def get_guides_for_entity" in provider
    install = provider[
        provider.index("def _install_summaries"):
        provider.index("def _summary_from_compact_row")
    ]
    assert "self._by_entity = defaultdict(list)" in install
    assert "for entity_key, guide_ids in by_entity_ids.items()" not in install


def test_guide_home_defers_quest_runtime_until_needed() -> None:
    source = (
        ROOT / "app" / "modules" / "encyclopedia" / "views" / "guides_view.py"
    ).read_text(encoding="utf-8")

    hydrate = source[
        source.index("def hydrate_runtime"):
        source.index("def _ensure_progress_runtime")
    ]
    assert "self.quest_provider.get_catalog()" not in hydrate
    assert "QuestGraphService(" not in hydrate

    progress_runtime = source[
        source.index("def _ensure_progress_runtime"):
        source.index("def _ensure_detail_runtime")
    ]
    assert "self.quest_provider.get_catalog()" in progress_runtime
    assert "GuideProgressCalculator(" in progress_runtime

    detail_runtime = source[
        source.index("def _ensure_detail_runtime"):
        source.index("def _ensure_detail_page")
    ]
    assert "QuestGraphService(" in detail_runtime
    assert "eager=False" in detail_runtime

    detail_page = source[
        source.index("def _ensure_detail_page"):
        source.index("def build_home_page")
    ]
    assert "self._ensure_detail_runtime()" in detail_page


def test_guide_home_thumbnails_use_bounded_encyclopedia_cache() -> None:
    source = (
        ROOT / "app" / "modules" / "encyclopedia" / "widgets" / "guide_card.py"
    ).read_text(encoding="utf-8")
    assert "ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled" in source
    assert "QIcon(" not in source


def test_guide_home_reads_sparse_compact_rows_without_runtime_worker() -> None:
    provider = MEMORY_GUIDE_PROVIDER.read_text(encoding="utf-8")
    loader = provider[
        provider.index("def _load(self)"):
        provider.index("def _load_from_compact_cache")
    ]
    assert "_load_from_compact_cache()" in loader
    assert "_DUMP_HOME_FLAG" not in provider
    assert "_load_home_from_compact_subprocess" not in provider


def test_guide_compact_home_rows_skip_rich_entity_decode() -> None:
    source = MEMORY_GUIDE_PROVIDER.read_text(encoding="utf-8")
    assert "_GUIDE_COMPACT_SCHEMA = 2" in source

    summary = source[
        source.index("def _summary_payload"):
        source.index("def _entity_index_payload")
    ]
    assert '"progress_quest_ids"' in summary
    assert '"steps": [' not in summary
    assert '"entity_keys"' not in summary

    loader = source[
        source.index("def _load_from_compact_cache"):
        source.index("def _load_from_compact_subprocess")
    ]
    filter_pos = loader.index('\'"kind":"guide"\' not in line')
    decode_pos = loader.index("row = json.loads(line)")
    assert filter_pos < decode_pos

    entity_lookup = source[
        source.index("def get_guides_for_entity"):
        source.index("def _progress_quest_ids_from_row")
    ]
    assert '\'"kind":"entity_index"\' not in line' in entity_lookup
    assert 'row.get("kind") != "entity_index"' in entity_lookup


def test_guide_home_summary_stays_metadata_only() -> None:
    provider = MEMORY_GUIDE_PROVIDER.read_text(encoding="utf-8")
    summary = provider[
        provider.index("def _summary_from_compact_row"):
        provider.index("def _summary_from_payload")
    ]
    assert "GuideStep(" not in summary
    assert "GuideSection(" not in summary
    assert "EntityRef(" not in summary
    assert "dofus_item_provider.get_by_id" not in summary
    assert "def progress_quest_ids_for" in provider

    calculator = (
        ROOT
        / "app"
        / "modules"
        / "encyclopedia"
        / "services"
        / "guide_progress_calculator.py"
    ).read_text(encoding="utf-8")
    assert "def quest_ids_progress" in calculator


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
    load_in_process = source[
        source.index("def _load_in_process("):
        source.index("def _effect_label(")
    ]
    assert "extra_item_ids" in load_in_process
    assert "extra_rows" in load_in_process
    assert load_in_process.count("_iter_doduda_refs(items_path)") == 1
    assert "effect_candidates" in load_in_process
    assert "del effect_candidates" in load_in_process
    guide_builder = source[
        source.index("def _build_guide_items_index("):
        source.index("def _ensure_guide_items_index_cli(")
    ]
    assert "_load_in_process(extra_item_ids=requested)" in guide_builder
    assert "_iter_doduda_refs" not in guide_builder
    assert "SelectedJsonValueMapping" not in guide_builder


class MemoryPolicyContractUnittest(unittest.TestCase):
    """Expose pytest-style memory policy contracts to Doctor's unittest runner."""

    def test_memory_policy_contracts(self) -> None:
        test_equipment_runtime_does_not_embed_qt_webengine()
        test_encyclopedia_public_facade_routes_to_memory_bound_page()
        test_encyclopedia_runtime_constructs_provider_through_memory_facade()
        test_encyclopedia_quest_surface_defers_success_and_guide_widgets()
        test_quests_surface_avoids_eager_widget_barrel_import()
        test_guide_catalog_surface_defers_rich_guide_module_until_selection()
        test_quest_catalog_defers_rich_detail_view_until_selection()
        test_success_progress_sync_streams_compact_rows()
        test_success_catalog_keeps_alignment_route_profiles_cold()
        test_success_list_materializes_only_visible_batches()
        test_achievement_sync_uses_compact_alignment_guide_ids()
        test_guide_home_worker_keeps_quest_catalogue_and_graph_cold()
        test_guide_catalog_defers_detail_and_manual_engines()
        test_memory_bound_page_hibernates_widgets_and_reconstructible_runtime()
        test_achievement_provider_releases_reconstructible_source_maps()
        test_services_facade_keeps_progress_runtime_lazy()
        test_related_index_warmup_runs_outside_long_lived_atlas_process()
        test_dofus_item_extraction_does_not_parse_monolithic_sources_in_parent()
        test_guide_name_resolution_uses_prebuilt_index_without_nested_worker()
        test_guide_provider_releases_reconstructible_catalogue()
        test_encyclopedia_preload_workers_do_not_capture_parent_payloads()
        test_launcher_prewarms_reconstructible_caches_before_long_lived_atlas()
        test_disk_only_preload_does_not_import_home_encyclopedia_runtime()
        test_quest_preload_keeps_all_rich_catalogues_off_heap()
        test_craft_preload_and_runtime_are_sqlite_bounded()
        test_home_release_collects_deleted_widget_cycles_without_working_set_trim()
        test_preload_retry_reuses_one_qtimer_per_task()
        test_idle_shell_keeps_macro_runtime_cold_without_clients()
        test_idle_network_poll_does_not_drain_empty_queues()
        test_background_related_preload_keeps_runtime_imports_out_of_parent()
        test_shell_announces_explicit_encyclopedia_tab_before_showing_page()
        test_memory_page_prefers_explicit_tab_over_hidden_current_tab()
        test_home_release_clears_loaded_manual_guide_bundle_cache_without_importing_it()
        test_atlas_manual_guide_disables_bundle_copy_and_wrapper_duplicate_snapshots()
        test_guide_auto_validation_uses_streamed_success_name_index_first()
        test_guide_manual_runtime_uses_sqlite_quest_name_index_before_catalogue()
        test_success_catalogue_keeps_rich_objectives_out_of_resident_rows()
        test_guide_home_uses_virtualized_delegate_instead_of_widget_forest()
        test_guide_home_defers_quest_runtime_until_needed()
        test_guide_home_thumbnails_use_bounded_encyclopedia_cache()
        test_guide_home_reads_sparse_compact_rows_without_runtime_worker()
        test_guide_compact_home_rows_skip_rich_entity_decode()
        test_guide_home_summary_stays_metadata_only()
        test_guide_compact_worker_never_loads_dofus_item_corpus()
        test_dofus_item_worker_streams_monolithic_doduda_sources()
