from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.views import EncyclopediaPage
from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage as EncyclopediaPageImpl
from app.modules.encyclopedia.views.deferred_achievement_guides_view import DeferredAchievementGuidesView
from app.modules.encyclopedia.views.achievements_view import AchievementsView
from app.modules.encyclopedia.views.related_preload_state import (
    RelatedPreloadGate,
    RelatedPreloadState,
)
from app.modules.encyclopedia.constants import (
    ACHIEVEMENTS_TAB,
    ENCYCLOPEDIA_TABS,
    GUIDES_TAB,
    QUESTS_TAB,
)
from app.pages.lazy_quests_page import LazyQuestsPage
from app.pages.quests_page import HIERARCHY_ID_ROLE, HIERARCHY_KIND_ROLE
from app.quest_catalog import QuestAchievementSeries, QuestCatalog, QuestRecord
from app.storage import KEY_SESSION_ORDER


def quest(quest_id: int, name: str, category: str, criterion: str = "") -> QuestRecord:
    return QuestRecord(
        id=quest_id,
        name=name,
        category=category,
        level_min=quest_id,
        level_max=quest_id,
        start_criterion=criterion,
    )


def catalog_fixture() -> QuestCatalog:
    return QuestCatalog(
        [
            quest(1, "Première A", "Zone test"),
            quest(2, "Deuxième A", "Zone test", "Qf=1"),
            quest(3, "Première B", "Zone test"),
            quest(4, "Deuxième B", "Zone test", "Qf=3"),
        ],
        achievement_series=(
            QuestAchievementSeries(10, "Suite A", "Zone test", 0, (1, 2)),
            QuestAchievementSeries(20, "Suite B", "Zone test", 1, (3, 4)),
        ),
    )


class LazyQuestsPagePerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def build_page(self, root: Path) -> LazyQuestsPage:
        profile = root / "profiles.json"
        client_index = root / "clients.json"
        profile.write_text(
            json.dumps({KEY_SESSION_ORDER: ["alpha", "", "", "", "", "", "", ""]}),
            encoding="utf-8",
        )
        client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
        return LazyQuestsPage(
            lambda _text: None,
            catalog=catalog_fixture(),
            progress_path=root / "progress.json",
            achievement_progress_path=root / "achievement_progress.json",
            profile_path=profile,
            client_index_path=client_index,
            owned_items_path=root / "owned_items.json",
        )

    def test_initial_tree_build_keeps_series_and_quest_rows_lazy(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(Path(temporary))

            self.assertEqual(page.series_items, {})
            self.assertEqual(page.quest_tree_items, {})
            self.assertEqual(page._loaded_category_names, set())
            self.assertEqual(page._loaded_series_ids, set())
            self.assertGreater(page.hierarchy_tree.topLevelItemCount(), 0)
            for item in page.category_items.values():
                self.assertEqual(item.childCount(), 1)
                self.assertEqual(item.child(0).data(0, HIERARCHY_KIND_ROLE), "placeholder")

            page.deleteLater()
            self.app.processEvents()

    def test_expanding_category_then_series_materializes_only_requested_level(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(Path(temporary))
            category = page.category_items["Zone test"]

            category.setExpanded(True)
            self.app.processEvents()
            self.assertEqual(page._loaded_category_names, {"Zone test"})
            self.assertEqual(set(page.series_items), {"achievement:10", "achievement:20"})
            self.assertEqual(page.quest_tree_items, {})

            first = page.series_items["achievement:10"]
            second = page.series_items["achievement:20"]
            first.setExpanded(True)
            self.app.processEvents()

            self.assertEqual(page._loaded_series_ids, {"achievement:10"})
            self.assertEqual(first.childCount(), 2)
            self.assertEqual(
                [first.child(index).data(0, HIERARCHY_ID_ROLE) for index in range(first.childCount())],
                [1, 2],
            )
            self.assertEqual(set(page.quest_tree_items), {1, 2})
            self.assertEqual(second.childCount(), 1)
            self.assertEqual(second.child(0).data(0, HIERARCHY_KIND_ROLE), "placeholder")

            first.setExpanded(False)
            first.setExpanded(True)
            self.app.processEvents()
            self.assertEqual(first.childCount(), 2)
            self.assertEqual(len(page.quest_tree_items[1]), 1)
            self.assertEqual(len(page.quest_tree_items[2]), 1)

            page.deleteLater()
            self.app.processEvents()

    def test_selecting_quest_loads_target_category_and_series_and_keeps_navigation_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(Path(temporary))

            page.select_quest(3, persist=False, series_id="achievement:20")
            self.app.processEvents()

            self.assertEqual(page.active_series_id, "achievement:20")
            self.assertEqual(page.selected_quest_id, 3)
            self.assertEqual(page._loaded_category_names, {"Zone test"})
            self.assertIn("achievement:20", page._loaded_series_ids)
            self.assertNotIn("achievement:10", page._loaded_series_ids)
            current = page.hierarchy_tree.currentItem()
            self.assertIsNotNone(current)
            self.assertEqual(current.data(0, HIERARCHY_KIND_ROLE), "quest")
            self.assertEqual(current.data(0, HIERARCHY_ID_ROLE), 3)
            self.assertEqual(page.quest_detail_view.context.ordered_quest_ids, (3, 4))

            page.deleteLater()
            self.app.processEvents()

    def test_search_text_is_cached_until_related_context_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(Path(temporary))
            row = page.catalog.by_id[1]

            first = page.quest_search_text(row)
            self.assertIn(1, page._quest_search_text_cache)
            second = page.quest_search_text(row)
            self.assertEqual(first, second)
            self.assertEqual(len(page._quest_search_text_cache), 1)

            page.update_related_context(graph=object())
            self.assertEqual(page._quest_search_text_cache, {})

            page.deleteLater()
            self.app.processEvents()

    def test_public_encyclopedia_export_builds_lazy_quests_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profiles.json"
            client_index = root / "clients.json"
            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: ["alpha", "", "", "", "", "", "", ""]}),
                encoding="utf-8",
            )
            client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
            provider = QuestProvider(catalog=catalog_fixture())
            page = EncyclopediaPage(
                lambda _text: None,
                quest_provider=provider,
                progress_path=root / "progress.json",
                achievement_progress_path=root / "achievement_progress.json",
                guide_progress_path=root / "guide_progress.json",
                profile_path=profile,
                client_index_path=client_index,
                owned_items_path=root / "owned_items.json",
                initial_tab=QUESTS_TAB,
            )

            self.assertIsInstance(page.quest_page, LazyQuestsPage)
            self.assertEqual(page.quest_page.series_items, {})
            self.assertEqual(page.quest_page.quest_tree_items, {})

            page.deleteLater()
            self.app.processEvents()

    def test_guide_achievement_link_targets_success_tab(self):
        page = SimpleNamespace(
            navigate_to_guide=Mock(return_value=True),
            navigate_to_achievement_tab=Mock(return_value=True),
            navigate_to_achievement_context=Mock(return_value=True),
        )

        self.assertTrue(
            EncyclopediaPageImpl.navigate_to_entity(
                page,
                "achievement",
                1385,
                source="guide",
                guide_id="dofus_turquoise",
            )
        )

        page.navigate_to_achievement_tab.assert_called_once_with(1385)
        page.navigate_to_achievement_context.assert_not_called()

    def test_guide_quest_link_keeps_guide_context(self):
        guide_view = SimpleNamespace(
            current_guide_id="dofus_turquoise",
            select_guide=Mock(return_value=True),
            show_quest_detail=Mock(return_value=True),
        )
        page = SimpleNamespace(
            navigate_to_guide=Mock(return_value=True),
            navigate_to_achievement_tab=Mock(return_value=True),
            navigate_to_achievement_context=Mock(return_value=True),
            quest_provider=SimpleNamespace(get_quest=Mock(return_value=object())),
            ensure_guides_view=Mock(return_value=guide_view),
        )

        self.assertTrue(
            EncyclopediaPageImpl.navigate_to_entity(
                page,
                "quest",
                1653,
                source="guide",
                guide_id="dofus_turquoise",
            )
        )

        guide_view.select_guide.assert_not_called()
        guide_view.show_quest_detail.assert_called_once_with(1653)

    def test_achievement_quest_link_targets_quests_tab(self):
        global_search = Mock()
        global_search.text.return_value = "ancienne recherche globale"
        quest_search = Mock()
        quest_search.text.return_value = "ancienne recherche"
        quest_page = SimpleNamespace(
            search=quest_search,
            selected_quest_id=None,
        )
        quest_page.select_quest = Mock(
            side_effect=lambda quest_id: setattr(quest_page, "selected_quest_id", int(quest_id))
        )
        tabs = Mock()
        page = SimpleNamespace(
            navigate_to_guide=Mock(return_value=True),
            navigate_to_achievement_tab=Mock(return_value=True),
            navigate_to_achievement_context=Mock(return_value=True),
            quest_provider=SimpleNamespace(get_quest=Mock(return_value=object())),
            quest_page=quest_page,
            search=global_search,
            tabs=tabs,
            ensure_tab_loaded=Mock(),
        )

        self.assertTrue(
            EncyclopediaPageImpl.navigate_to_entity(
                page,
                "quest",
                1653,
                source="achievement_link",
                achievement_id=1385,
            )
        )

        tabs.setCurrentIndex.assert_called_once_with(ENCYCLOPEDIA_TABS.index(QUESTS_TAB))
        quest_page.select_quest.assert_called_once_with(1653)
        self.assertEqual(quest_page.selected_quest_id, 1653)
        global_search.clear.assert_called_once_with()
        quest_search.clear.assert_called_once_with()
        page.ensure_tab_loaded.assert_not_called()

    def test_quests_links_keep_guide_and_success_destinations(self):
        page = SimpleNamespace(
            navigate_to_guide=Mock(return_value=True),
            navigate_to_achievement_tab=Mock(return_value=True),
            navigate_to_achievement_context=Mock(return_value=True),
        )

        self.assertTrue(
            EncyclopediaPageImpl.navigate_to_entity(
                page,
                "guide",
                "dofus_turquoise",
                source="quests",
            )
        )
        self.assertTrue(
            EncyclopediaPageImpl.navigate_to_entity(
                page,
                "achievement",
                1385,
                source="quests",
            )
        )

        page.navigate_to_guide.assert_called_once_with("dofus_turquoise")
        page.navigate_to_achievement_tab.assert_called_once_with(1385)
        page.navigate_to_achievement_context.assert_not_called()

    def test_success_guide_link_targets_guide(self):
        page = SimpleNamespace(
            navigate_to_guide=Mock(return_value=True),
            navigate_to_achievement_tab=Mock(return_value=True),
            navigate_to_achievement_context=Mock(return_value=True),
        )

        self.assertTrue(
            EncyclopediaPageImpl.navigate_to_entity(
                page,
                "guide",
                "dofus_turquoise",
                source="achievement_link",
                achievement_id=1385,
            )
        )

        page.navigate_to_guide.assert_called_once_with("dofus_turquoise")
        page.navigate_to_achievement_tab.assert_not_called()
        page.navigate_to_achievement_context.assert_not_called()

    def test_stable_successes_constructor_does_not_load_provider(self):
        provider = Mock()
        provider.quest_provider = Mock()
        view = AchievementsView(
            lambda _text: None,
            provider=provider,
            progress_service=Mock(),
            quest_provider=provider.quest_provider,
            quest_graph=Mock(),
            quest_progress_service=Mock(),
            defer_runtime=True,
        )

        provider.load_retained.assert_not_called()
        self.assertFalse(view._runtime_ready)
        self.assertEqual(view.list_widget.count(), 1)

        view.deleteLater()
        self.app.processEvents()

    def test_successes_runtime_uses_existing_widget_without_index_swap(self):
        stable_view = object()
        page = SimpleNamespace(
            _pending_lazy_tab="",
            ensure_achievements_view=Mock(return_value=stable_view),
            _activate_loaded_tab=Mock(),
            status_callback=Mock(),
            request_achievement_runtime=Mock(),
        )

        EncyclopediaPageImpl._start_full_achievement_runtime(page)

        page.ensure_achievements_view.assert_called_once_with()
        page._activate_loaded_tab.assert_called_once_with(ACHIEVEMENTS_TAB)
        page.request_achievement_runtime.assert_called_once_with()

    def test_success_target_pending_contract_cold_and_ready(self):
        for ready in (False, True):
            with self.subTest(ready=ready):
                tabs = Mock()
                open_pending = Mock()
                start_runtime = Mock()
                page = SimpleNamespace(
                    _pending_achievement_id=None,
                    _pending_lazy_tab="",
                    _achievement_ready=ready,
                    tabs=tabs,
                    tab_labels=lambda: list(ENCYCLOPEDIA_TABS),
                    open_pending_lazy_tab=open_pending,
                    _start_full_achievement_runtime=start_runtime,
                )

                self.assertTrue(EncyclopediaPageImpl.navigate_to_achievement_tab(page, 1385))

                self.assertEqual(page._pending_achievement_id, 1385)
                self.assertEqual(page._pending_lazy_tab, ACHIEVEMENTS_TAB)
                tabs.setCurrentIndex.assert_called_once_with(
                    ENCYCLOPEDIA_TABS.index(ACHIEVEMENTS_TAB)
                )
                if ready:
                    open_pending.assert_called_once_with()
                    start_runtime.assert_not_called()
                else:
                    start_runtime.assert_called_once_with()
                    open_pending.assert_not_called()

    def test_pending_success_target_is_consumed_once(self):
        success_index = ENCYCLOPEDIA_TABS.index(ACHIEVEMENTS_TAB)
        tabs = Mock()
        tabs.currentIndex.return_value = success_index
        success_view = SimpleNamespace(show_achievement=Mock())
        page = SimpleNamespace(
            _pending_lazy_tab=ACHIEVEMENTS_TAB,
            _guide_runtime_ready=True,
            _achievement_ready=True,
            quest_page=None,
            _pending_guide_id="",
            _pending_achievement_context_id=None,
            _pending_achievement_id=1385,
            tabs=tabs,
            tab_labels=lambda: list(ENCYCLOPEDIA_TABS),
            ensure_achievements_view=Mock(return_value=success_view),
            ensure_guides_view=Mock(),
            ensure_tab_loaded=Mock(),
            sync_tab_accent=Mock(),
            sync_search_visibility=Mock(),
            sync_character_to_children=Mock(),
            status_callback=Mock(),
        )

        EncyclopediaPageImpl.open_pending_lazy_tab(page)
        EncyclopediaPageImpl.open_pending_lazy_tab(page)

        self.assertEqual(page._pending_lazy_tab, "")
        self.assertIsNone(page._pending_achievement_id)
        tabs.setCurrentIndex.assert_called_once_with(success_index)
        success_view.show_achievement.assert_called_once_with(1385)

    def test_stable_guide_view_constructor_does_not_load_catalogues(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider = Mock()
            quest_provider = Mock()
            achievement_provider = Mock()
            view = DeferredAchievementGuidesView(
                lambda _text: None,
                provider=provider,
                quest_provider=quest_provider,
                achievement_provider=achievement_provider,
                achievement_progress_service=Mock(),
                guide_progress_service=Mock(),
                quest_progress_path=Path(temporary) / "quest_progress.json",
                defer_runtime=True,
            )

            provider.load_all.assert_not_called()
            quest_provider.get_catalog.assert_not_called()
            self.assertFalse(view._runtime_ready)
            self.assertEqual(view.stack.count(), 1)

            view.deleteLater()
            self.app.processEvents()

    def test_guide_tab_delegates_to_canonical_runtime_handler(self):
        page = SimpleNamespace(_on_tab_changed_indexed_runtime=Mock())
        index = ENCYCLOPEDIA_TABS.index(GUIDES_TAB)

        EncyclopediaPageImpl.on_tab_changed(page, index)

        page._on_tab_changed_indexed_runtime.assert_called_once_with(index)

    def test_guide_ultime_navigation_is_preserved_until_runtime_finishes(self):
        tabs = Mock()
        page = SimpleNamespace(
            _pending_guide_id="",
            _pending_lazy_tab="",
            _guide_runtime_ready=False,
            tabs=tabs,
            tab_labels=lambda: list(ENCYCLOPEDIA_TABS),
            open_pending_lazy_tab=Mock(),
            _start_full_guide_runtime=Mock(),
        )

        self.assertTrue(EncyclopediaPageImpl.navigate_to_guide(page, "guide_complet"))

        self.assertEqual(page._pending_guide_id, "guide_complet")
        self.assertEqual(page._pending_lazy_tab, GUIDES_TAB)
        tabs.setCurrentIndex.assert_called_once_with(ENCYCLOPEDIA_TABS.index(GUIDES_TAB))
        page._start_full_guide_runtime.assert_called_once_with()
        page.open_pending_lazy_tab.assert_not_called()

    def test_empty_guide_navigation_is_rejected_without_starting_runtime(self):
        page = SimpleNamespace(
            _start_full_guide_runtime=Mock(),
            open_pending_lazy_tab=Mock(),
        )

        self.assertFalse(EncyclopediaPageImpl.navigate_to_guide(page, ""))

        page._start_full_guide_runtime.assert_not_called()
        page.open_pending_lazy_tab.assert_not_called()

    def test_guide_worker_failure_reaches_a_terminal_visible_state(self):
        error = RuntimeError("catalogue cassé")
        gate = SimpleNamespace(mark_failed=Mock())
        stable_view = SimpleNamespace(show_runtime_error=Mock())
        page = SimpleNamespace(
            _related_preload_started=True,
            _related_preload_gate=gate,
            status_callback=Mock(),
            ensure_guides_view=Mock(return_value=stable_view),
            sync_search_visibility=Mock(),
        )

        EncyclopediaPageImpl.collect_related_preload(page, error)

        self.assertFalse(page._related_preload_started)
        gate.mark_failed.assert_called_once_with()
        page.ensure_guides_view.assert_called_once_with()
        stable_view.show_runtime_error.assert_called_once_with("catalogue cassé")
        page.status_callback.assert_called_once_with(
            "Chargement Guide impossible : catalogue cassé"
        )
        page.sync_search_visibility.assert_called_once_with()

    def test_failed_guide_runtime_retries_and_reloads_provider(self):
        gate = RelatedPreloadGate()
        self.assertTrue(gate.begin())
        gate.mark_failed()

        guide_provider = Mock()
        guide_provider.reload.return_value = [object()]
        page = SimpleNamespace(
            _pending_lazy_tab="",
            _guide_runtime_ready=False,
            _related_preload_started=False,
            _achievement_load_started=False,
            _achievement_ready=False,
            _related_preload_gate=gate,
            quest_provider=SimpleNamespace(get_catalog=Mock(return_value=object())),
            service=SimpleNamespace(
                guide_provider=guide_provider,
                achievement_provider=Mock(),
            ),
            current_character_key="",
            quest_progress_path=Path("quest_progress.json"),
            guide_progress_service=SimpleNamespace(path=Path("guide_progress.json")),
            achievement_progress_service=SimpleNamespace(
                path=Path("achievement_progress.json")
            ),
            _build_guide_progress_snapshot=Mock(return_value={}),
            guideRuntimeFinished=SimpleNamespace(emit=Mock()),
            open_pending_lazy_tab=Mock(),
            status_callback=Mock(),
        )

        def run_thread(*, target, **_kwargs):
            return SimpleNamespace(start=target)

        with patch(
            "app.modules.encyclopedia.views.encyclopedia_page._warm_guide_ultime_runtime_cache"
        ) as warm_cache, patch(
            "app.modules.encyclopedia.views.encyclopedia_page.Thread",
            side_effect=run_thread,
        ):
            EncyclopediaPageImpl.request_related_preload(page, GUIDES_TAB)

        self.assertEqual(gate.state, RelatedPreloadState.LOADING)
        guide_provider.reload.assert_called_once_with()
        guide_provider.load_all.assert_not_called()
        warm_cache.assert_called_once_with(
            page.quest_provider,
            quest_progress_path=page.quest_progress_path,
            achievement_progress_path=page.achievement_progress_service.path,
            guide_progress_path=page.guide_progress_service.path,
        )
        page.guideRuntimeFinished.emit.assert_called_once()

    def test_guide_hydration_keeps_rich_detail_unbuilt(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider = Mock()
            provider.load_all.return_value = [SimpleNamespace(id="guide-test")]
            quest_provider = Mock()
            quest_provider.get_catalog.return_value = SimpleNamespace(by_id={})
            achievement_provider = Mock()
            achievement_provider._loaded = False
            achievement_progress_service = Mock()
            achievement_progress_service.path = Path(temporary) / "achievement_progress.json"
            guide_progress_service = Mock()
            guide_progress_service.path = Path(temporary) / "guide_progress.json"
            view = DeferredAchievementGuidesView(
                lambda _text: None,
                provider=provider,
                quest_provider=quest_provider,
                achievement_provider=achievement_provider,
                achievement_progress_service=achievement_progress_service,
                guide_progress_service=guide_progress_service,
                quest_progress_path=Path(temporary) / "quest_progress.json",
                defer_runtime=True,
            )
            view.refresh_home = Mock()

            self.assertTrue(view.hydrate_runtime(graph=Mock()))

            self.assertTrue(view._runtime_ready)
            self.assertIsNone(view.detail_page)
            view.refresh_home.assert_called_once_with()
            view.deleteLater()
            self.app.processEvents()

    def test_success_hydration_skips_progress_already_computed_by_worker(self):
        provider = Mock()
        provider.quest_provider = Mock()
        provider.load_retained.return_value = [SimpleNamespace(id=1)]
        view = AchievementsView(
            lambda _text: None,
            provider=provider,
            progress_service=Mock(),
            quest_provider=provider.quest_provider,
            quest_graph=Mock(),
            quest_progress_service=Mock(),
            defer_runtime=True,
        )
        view.sync_automatic_progress = Mock()
        view.populate_categories = Mock()
        view.refresh = Mock()

        self.assertTrue(view.hydrate_runtime(progress_synchronized=True))

        view.sync_automatic_progress.assert_not_called()
        view.populate_categories.assert_called_once_with()
        view.refresh.assert_called_once_with()
        view.deleteLater()
        self.app.processEvents()

    def test_cold_success_refresh_never_wakes_provider_on_qt_thread(self):
        provider = Mock()
        provider.quest_provider = Mock()
        quest_progress_service = Mock()
        view = AchievementsView(
            lambda _text: None,
            provider=provider,
            progress_service=Mock(),
            quest_provider=provider.quest_provider,
            quest_graph=Mock(),
            quest_progress_service=quest_progress_service,
            defer_runtime=True,
        )
        view.sync_automatic_progress = Mock()

        view.refresh_external_progress()

        quest_progress_service.refresh_if_changed.assert_not_called()
        view.sync_automatic_progress.assert_not_called()
        provider.load_retained.assert_not_called()
        view.deleteLater()
        self.app.processEvents()

    def test_guide_overview_does_not_request_rich_success_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider = Mock()
            quest_provider = Mock()
            achievement_provider = Mock()
            achievement_provider._loaded = False
            view = DeferredAchievementGuidesView(
                lambda _text: None,
                provider=provider,
                quest_provider=quest_provider,
                achievement_provider=achievement_provider,
                achievement_progress_service=Mock(),
                guide_progress_service=Mock(),
                quest_progress_path=Path(temporary) / "quest_progress.json",
                defer_runtime=True,
            )
            requested = Mock()
            view.achievementRuntimeRequested.connect(requested)

            with patch(
                "app.modules.encyclopedia.views.guides_view.GuidesView.select_guide",
                return_value=True,
            ):
                self.assertTrue(view.select_guide("dofus_cawotte"))

            requested.assert_not_called()
            view.deleteLater()
            self.app.processEvents()

    def test_preloaded_providers_do_not_mark_a_cold_guide_widget_ready(self):
        achievement_provider = SimpleNamespace(_loaded=True)
        guide_provider = SimpleNamespace(_loaded=True)
        gate = RelatedPreloadGate()
        page = SimpleNamespace(
            service=SimpleNamespace(
                achievement_provider=None,
                guide_provider=None,
            ),
            _achievement_provider_supplied=False,
            _guide_provider_supplied=False,
            _quest_graph=None,
            _guide_progress_by_guide={},
            _guide_progress_character_key="",
            quest_page=None,
            guides_view=None,
            _achievement_ready=False,
            _guide_runtime_ready=False,
            _related_ready=False,
            _related_preload_gate=gate,
            _related_data_ready_callback=None,
            open_pending_lazy_tab=Mock(),
        )

        EncyclopediaPageImpl.apply_preloaded_related_data(
            page,
            achievement_provider=achievement_provider,
            guide_provider=guide_provider,
            quest_graph=Mock(),
        )

        self.assertTrue(page._achievement_ready)
        self.assertFalse(page._guide_runtime_ready)
        self.assertFalse(page._related_ready)
        self.assertEqual(gate.state, RelatedPreloadState.IDLE)
        page.open_pending_lazy_tab.assert_not_called()

    def test_success_render_batches_stay_within_small_qt_budget(self):
        from app.modules.encyclopedia.views import achievements_view

        self.assertLessEqual(achievements_view._RESULT_BATCH_SIZE, 16)

    def test_success_categories_are_all_collapsed_after_hydration(self):
        provider = Mock()
        provider.quest_provider = Mock()
        provider.get_retained_categories.return_value = [
            SimpleNamespace(id=1, name="Quêtes"),
            SimpleNamespace(id=2, name="Donjons"),
        ]
        provider.get_subcategories.return_value = []
        provider.get_by_category.return_value = []
        view = AchievementsView(
            lambda _text: None,
            provider=provider,
            progress_service=Mock(),
            quest_provider=provider.quest_provider,
            quest_graph=Mock(),
            quest_progress_service=Mock(),
            defer_runtime=True,
        )

        view.populate_categories()

        self.assertEqual(view.category_tree.topLevelItemCount(), 2)
        self.assertFalse(view.category_tree.topLevelItem(0).isExpanded())
        self.assertFalse(view.category_tree.topLevelItem(1).isExpanded())
        view.deleteLater()
        self.app.processEvents()

    def test_empty_guide_provider_recovers_from_fresh_canonical_provider(self):
        gate = RelatedPreloadGate()
        empty_provider = Mock()
        empty_provider.load_all.return_value = []
        empty_provider.guides_dir = Path("broken-guides")
        empty_provider.dofus_item_provider = Mock()
        empty_provider.include_drafts = False
        recovered_provider = Mock()
        recovered_provider.reload.return_value = [SimpleNamespace(id="dofus_cawotte")]
        page = SimpleNamespace(
            _pending_lazy_tab="",
            _guide_runtime_ready=False,
            _related_preload_started=False,
            _achievement_load_started=False,
            _achievement_ready=False,
            _related_preload_gate=gate,
            quest_provider=SimpleNamespace(get_catalog=Mock(return_value=object())),
            service=SimpleNamespace(
                guide_provider=empty_provider,
                achievement_provider=Mock(),
            ),
            current_character_key="",
            quest_progress_path=Path("quest_progress.json"),
            guide_progress_service=SimpleNamespace(path=Path("guide_progress.json")),
            achievement_progress_service=SimpleNamespace(
                path=Path("achievement_progress.json")
            ),
            _build_guide_progress_snapshot=Mock(return_value={}),
            guideRuntimeFinished=SimpleNamespace(emit=Mock()),
            open_pending_lazy_tab=Mock(),
            status_callback=Mock(),
        )

        def run_thread(*, target, **_kwargs):
            return SimpleNamespace(start=target)

        with (
            patch(
                "app.modules.encyclopedia.views.encyclopedia_page.Thread",
                side_effect=run_thread,
            ),
            patch(
                "app.modules.encyclopedia.views.encyclopedia_page.GuideProvider",
                return_value=recovered_provider,
            ),
            patch(
                "app.modules.encyclopedia.views.encyclopedia_page.QuestGraphService",
                return_value=Mock(),
            ),
        ):
            EncyclopediaPageImpl.request_related_preload(page, GUIDES_TAB)

        recovered_provider.reload.assert_called_once_with()
        payload = page.guideRuntimeFinished.emit.call_args.args[0]
        self.assertIs(payload.guide_provider, recovered_provider)


if __name__ == "__main__":
    unittest.main()
