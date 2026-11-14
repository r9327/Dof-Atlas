from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QToolButton

from app.modules.encyclopedia.providers import (
    AchievementProvider, GuideProvider, QuestProvider,
)
from app.modules.encyclopedia.services.guide_progress_service import (
    GuideProgressService,
)
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)
from app.modules.encyclopedia.services.guide_imported_manual_runtime_service import (
    ImportedSourceManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_trusted_source_package import (
    GuidePackageEntry, GuideTrustedSourcePackage,
)
from app.modules.encyclopedia.views.manual_route_guides_view import (
    ManualRouteGuidesView,
)
from app.modules.encyclopedia.views.shared_manual_guide_view import (
    SharedGuideManualView, _PreparationNeed,
)
from tests.test_guide_imported_manual_runtime_service import _source_route
from tests.test_guide_trusted_source_package import TEST_HEAD, TEST_SOURCE
from tests.test_guide_ultime_manual_ui_navigation import _FakeParticipantService


class ImportedSourceRouterQtTests(unittest.TestCase):
    """Existing Guide router and shared Qt reader; never a live guide export."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.quests = QuestProvider()
        cls.achievements = AchievementProvider(quest_provider=cls.quests)
        cls.provider = GuideProvider(
            quest_provider=cls.quests, achievement_provider=cls.achievements,
        )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.progress_path = root / "guide_progress.json"
        self.progress = GuideProgressService(self.progress_path)
        self.achievement_progress = AchievementProgressService(
            root / "achievement_progress.json"
        )
        from app.modules.encyclopedia.services.quest_progress_service import (
            QuestProgressService,
        )
        self.quest_progress = QuestProgressService(root / "quest_progress.json")
        self.service = ImportedSourceManualRuntimeService(
            self.quest_progress,
            self.achievement_progress,
            self.progress,
            route=_source_route(),
        )
        self.approved = False
        self.authorization_calls: list[str] = []
        self.messages: list[str] = []

        def approve(guide_id: str, route: dict) -> bool:
            self.authorization_calls.append(guide_id)
            self.assertEqual(route["id"], guide_id)
            return self.approved

        self.view = ManualRouteGuidesView(
            self.messages.append,
            provider=self.provider,
            quest_provider=self.quests,
            achievement_provider=self.achievements,
            achievement_progress_service=self.achievement_progress,
            guide_progress_service=self.progress,
            quest_progress_path=root / "quest_progress.json",
            profile_path=root / "profiles.json",
            client_index_path=root / "clients.json",
            character_key="character:1",
            defer_runtime=True,
            imported_source_services={self.service.guide_id: self.service},
            imported_source_authorizer=approve,
        )
        self.view.guide_participant_service = _FakeParticipantService()
        self.addCleanup(self._close_view)

    def _close_view(self) -> None:
        self.view.close()
        self.view.deleteLater()
        QApplication.processEvents()

    def test_encyclopedia_shell_forwards_authorized_sources_only_on_guide_open(self):
        from app.modules.encyclopedia.views.encyclopedia_page import (
            EncyclopediaPage,
        )
        from app.modules.encyclopedia.constants import DUNGEONS_TAB

        root = Path(self.tmp.name)
        with self.assertRaisesRegex(ValueError, "independent authorizer"):
            orphan = EncyclopediaPage(
                self.messages.append,
                quest_provider=self.quests,
                achievement_provider=self.achievements,
                guide_provider=self.provider,
                progress_path=root / "quest_progress.json",
                achievement_progress_path=root / "achievements.json",
                guide_progress_path=self.progress_path,
                profile_path=root / "profiles.json",
                client_index_path=root / "clients.json",
                imported_source_services={self.service.guide_id: self.service},
            )
            orphan.close()

        shell = EncyclopediaPage(
            self.messages.append,
            quest_provider=self.quests,
            achievement_provider=self.achievements,
            guide_provider=self.provider,
            progress_path=root / "quest_progress.json",
            achievement_progress_path=root / "achievements.json",
            guide_progress_path=self.progress_path,
            profile_path=root / "profiles.json",
            client_index_path=root / "clients.json",
            imported_source_services={self.service.guide_id: self.service},
            imported_source_authorizer=lambda _key, _route: self.approved,
            quest_graph=object(),  # Synthetic: no Doduda quest data in Phase 0.
            initial_tab=DUNGEONS_TAB,  # Lazy slot; do not load the Quest catalogue.
        )
        try:
            # No Guide source service is constructed or fetched at Home.
            self.assertIsNone(shell.guides_view)
            self.assertFalse(self.progress_path.exists())
            shell.current_character_key = "character:1"
            reader = shell.ensure_full_guides_view()
            self.assertIs(reader._imported_source_services[self.service.guide_id], self.service)
            self.assertFalse(reader.select_guide(self.service.guide_id))
            self.assertIsNone(reader.current_guide_id)
            self.approved = True
            self.assertTrue(reader.select_guide(self.service.guide_id))
            self.assertIsInstance(reader.stack.currentWidget(), SharedGuideManualView)
            self.assertFalse(self.progress_path.exists())
        finally:
            shell.close()
            shell.deleteLater()
            QApplication.processEvents()

    def test_encyclopedia_forwards_lazy_factory_without_home_hydration(self):
        from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
        from app.modules.encyclopedia.constants import DUNGEONS_TAB
        root = Path(self.tmp.name)
        factory_calls = []

        def build_source():
            factory_calls.append("selected")
            return ImportedSourceManualRuntimeService(
                self.quest_progress, self.achievement_progress, self.progress,
                route=_source_route("fictional-shell"),
            )

        guide_id = "source_guide:fictional-shell"
        with self.assertRaisesRegex(ValueError, "independent authorizer"):
            EncyclopediaPage(
                self.messages.append,
                imported_source_factories={guide_id: build_source},
            )
        self.assertFalse(factory_calls)
        shell = EncyclopediaPage(
            self.messages.append,
            quest_provider=self.quests,
            achievement_provider=self.achievements,
            guide_provider=self.provider,
            progress_path=root / "quest_progress.json",
            achievement_progress_path=root / "achievements.json",
            guide_progress_path=self.progress_path,
            profile_path=root / "profiles.json",
            client_index_path=root / "clients.json",
            imported_source_factories={guide_id: build_source},
            imported_source_authorizer=lambda _id, _route: self.approved,
            quest_graph=object(),
            initial_tab=DUNGEONS_TAB,
        )
        try:
            self.assertFalse(factory_calls)
            self.assertIsNone(shell.guides_view)
            reader = shell.ensure_full_guides_view()
            self.assertFalse(factory_calls)
            self.assertIn(guide_id, reader._imported_source_factories)
            reader.current_character_key = "character:1"
            self.approved = True
            self.assertTrue(reader.select_guide(guide_id))
            self.assertEqual(factory_calls, ["selected"])
            reader.show_home()
            self.assertNotIn(guide_id, reader._loaded_imported_source_services)
            self.assertFalse(self.progress_path.exists())
        finally:
            shell.close()
            shell.deleteLater()
            QApplication.processEvents()

    def test_missing_registry_and_untrusted_registration_never_select_source(self):
        with self.assertRaisesRegex(ValueError, "independent authorizer"):
            ManualRouteGuidesView(
                self.messages.append,
                imported_source_services={self.service.guide_id: self.service},
            )
        with self.assertRaisesRegex(ValueError, "Mismatched"):
            ManualRouteGuidesView(
                self.messages.append,
                imported_source_services={
                    "source_guide:another-fictitious-guide": self.service,
                },
                imported_source_authorizer=lambda *_: True,
            )
        self.approved = True
        self.view._imported_source_services.clear()
        self.assertFalse(self.view.select_guide(self.service.guide_id))
        self.assertEqual(self.view.state, self.view.CATALOG)
        self.assertEqual(self.view.stack.currentWidget(), self.view.home_page)
        self.assertFalse(self.progress_path.exists())

    def test_denied_source_cannot_fall_through_to_legacy_or_load_cached_route(self):
        self.assertFalse(self.view.select_guide(self.service.guide_id))
        self.assertEqual(self.view.state, self.view.CATALOG)
        self.assertIsNone(self.view.current_guide_id)
        self.assertEqual(self.view.stack.currentWidget(), self.view.home_page)
        self.assertFalse(self.view._catalog_manual_services)
        self.assertFalse(self.view._catalog_manual_views)
        self.assertIsNone(self.view.guide_ultime_view)
        self.assertFalse(self.progress_path.exists())
        self.assertTrue(any("non certifié" in text for text in self.messages))

    def test_authorized_source_uses_same_shared_reader_and_is_lazy(self):
        self.assertFalse(self.view._catalog_manual_views)
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        reader = self.view.stack.currentWidget()
        self.assertIsInstance(reader, SharedGuideManualView)
        self.assertIs(self.view._catalog_manual_views[self.service.guide_id], reader)
        self.assertEqual(self.view.current_guide_id, self.service.guide_id)
        self.assertEqual(self.view.state, self.view.GUIDE_OVERVIEW)
        self.assertIsNone(self.view.guide_ultime_view)
        self.assertNotIn("dofus_sylvestre", self.view._catalog_manual_services)
        self.assertEqual(reader.nav_page_label.text(), "Page 1 / 2")
        self.assertEqual(self.service.route_sheet_progress("character:1"), (0, 2))
        self.assertFalse(self.progress_path.exists())
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        self.assertIs(self.view.stack.currentWidget(), reader)

    def test_switching_source_guides_releases_old_qt_reader_without_progress_write(self):
        next_service = ImportedSourceManualRuntimeService(
            self.quest_progress,
            self.achievement_progress,
            self.progress,
            route=_source_route("fictional-next"),
        )
        next_service.set_authorization_guard(self.view._imported_source_authorizer)
        self.view._imported_source_services[next_service.guide_id] = next_service
        self.approved = True
        baseline = self.view.stack.count()

        self.assertTrue(self.view.select_guide(self.service.guide_id))
        first = self.view.stack.currentWidget()
        self.assertEqual(self.view.stack.count(), baseline + 1)

        self.assertTrue(self.view.select_guide(next_service.guide_id))
        second = self.view.stack.currentWidget()
        self.assertIsInstance(second, SharedGuideManualView)
        self.assertIsNot(second, first)
        self.assertEqual(self.view.stack.count(), baseline + 1)
        self.assertEqual(self.view.stack.indexOf(first), -1)
        self.assertNotIn(self.service.guide_id, self.view._catalog_manual_views)
        self.assertNotIn(self.service.guide_id, self.view._catalog_manual_services)
        self.assertIs(self.view._catalog_manual_views[next_service.guide_id], second)

        self.assertTrue(self.view.select_guide(self.service.guide_id))
        self.assertEqual(self.view.stack.count(), baseline + 1)
        self.assertIsNot(self.view.stack.currentWidget(), first)
        self.assertEqual(self.view.stack.indexOf(second), -1)
        self.assertFalse(self.progress_path.exists())

        # This lifecycle test does not require the separately shipped
        # Quest catalogue; keep the real Home state transition and cache
        # release while isolating only the unrelated catalogue data load.
        with patch.object(self.view, "refresh_home") as refresh_home:
            self.view.show_home()
        refresh_home.assert_called_once_with()
        self.assertEqual(self.view.stack.count(), baseline)
        self.assertFalse(any(
            key.startswith("source_guide:") for key in self.view._catalog_manual_views
        ))
        self.assertFalse(self.progress_path.exists())

    def test_lazy_source_factory_only_loads_on_select_and_releases_on_home(self):
        calls = []

        def make_source():
            calls.append("load")
            return ImportedSourceManualRuntimeService(
                self.quest_progress, self.achievement_progress, self.progress,
                route=_source_route("fictional-lazy"),
            )

        lazy_key = "source_guide:fictional-lazy"
        self.view._imported_source_factories[lazy_key] = make_source
        self.assertEqual(calls, [])
        self.assertFalse(self.view.select_guide(lazy_key))
        self.assertEqual(calls, ["load"])
        self.assertFalse(self.view._loaded_imported_source_services)
        self.assertFalse(self.progress_path.exists())

        self.approved = True
        self.assertTrue(self.view.select_guide(lazy_key))
        self.assertEqual(calls, ["load", "load"])
        self.assertIsInstance(self.view.stack.currentWidget(), SharedGuideManualView)
        self.assertTrue(self.view.select_guide(lazy_key))
        self.assertEqual(calls, ["load", "load"])
        # This lifecycle test does not require the separately shipped
        # Quest catalogue; keep the real Home state transition and cache
        # release while isolating only the unrelated catalogue data load.
        with patch.object(self.view, "refresh_home") as refresh_home:
            self.view.show_home()
        refresh_home.assert_called_once_with()
        self.assertNotIn(lazy_key, self.view._loaded_imported_source_services)
        self.assertNotIn(lazy_key, self.view._catalog_manual_views)
        self.assertFalse(self.progress_path.exists())
        self.assertTrue(self.view.select_guide(lazy_key))
        self.assertEqual(calls, ["load", "load", "load"])

    def test_factory_owned_runtime_cannot_write_after_home_disposal(self):
        guide_id = "source_guide:fictional-retired"
        self.view._imported_source_factories[guide_id] = (
            lambda: ImportedSourceManualRuntimeService(
                self.quest_progress, self.achievement_progress, self.progress,
                route=_source_route("fictional-retired"),
            )
        )
        self.approved = True
        self.assertTrue(self.view.select_guide(guide_id))
        old_service = self.view._loaded_imported_source_services[guide_id]
        self.assertTrue(old_service.can_write_progress())
        # This lifecycle test does not require the separately shipped
        # Quest catalogue; keep the real Home state transition and cache
        # release while isolating only the unrelated catalogue data load.
        with patch.object(self.view, "refresh_home") as refresh_home:
            self.view.show_home()
        refresh_home.assert_called_once_with()
        self.assertNotIn(guide_id, self.view._loaded_imported_source_services)
        self.assertFalse(old_service.can_write_progress())
        with self.assertRaisesRegex(RuntimeError, "retired"):
            old_service.set_authorization_guard(self.view._imported_source_authorizer)
        old_service.set_page_checked("character:1", old_service.cards[0], 0, True)
        self.assertFalse(self.progress_path.exists())
        self.assertTrue(self.view.select_guide(guide_id))
        new_service = self.view._loaded_imported_source_services[guide_id]
        self.assertIsNot(new_service, old_service)
        self.assertTrue(new_service.can_write_progress())

    def test_failed_source_factory_is_invoked_only_once_per_selection(self):
        key = "source_guide:fictional-unavailable"
        attempted = []

        def broken():
            attempted.append(key)
            raise RuntimeError("Synthetic source bundle unavailable")

        self.view._imported_source_factories[key] = broken
        baseline = self.view.stack.count()
        self.assertFalse(self.view.select_guide(key))
        self.assertEqual(attempted, [key])
        self.assertEqual(self.view.stack.count(), baseline)
        self.assertNotIn(key, self.view._catalog_manual_views)
        self.assertNotIn(key, self.view._loaded_imported_source_services)
        self.assertFalse(self.progress_path.exists())

    def test_revocation_between_reader_creation_and_selection_evicts_reader(self):
        self.approved = True
        guide_id = self.service.guide_id
        original_ensure = self.view.ensure_imported_source_manual_view

        def revoke_after_creation(candidate_id):
            reader = original_ensure(candidate_id)
            self.assertIsNotNone(reader)
            self.approved = False
            return reader

        baseline = self.view.stack.count()
        self.view.ensure_imported_source_manual_view = revoke_after_creation
        self.assertFalse(self.view.select_guide(guide_id))
        self.assertIsNone(self.view.current_guide_id)
        self.assertIs(self.view.stack.currentWidget(), self.view.home_page)
        self.assertEqual(self.view.stack.count(), baseline)
        self.assertNotIn(guide_id, self.view._catalog_manual_views)
        self.assertNotIn(guide_id, self.view._catalog_manual_services)
        self.assertFalse(self.progress_path.exists())

    def test_denied_other_source_leaves_current_reader_untouched(self):
        next_service = ImportedSourceManualRuntimeService(
            self.quest_progress, self.achievement_progress, self.progress,
            route=_source_route("fictional-denied"),
        )
        next_service.set_authorization_guard(lambda *_: False)
        self.view._imported_source_services[next_service.guide_id] = next_service
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        original = self.view.stack.currentWidget()
        baseline = self.view.stack.count()

        self.assertFalse(self.view.select_guide(next_service.guide_id))
        self.assertEqual(self.view.current_guide_id, self.service.guide_id)
        self.assertIs(self.view.stack.currentWidget(), original)
        self.assertEqual(self.view.stack.count(), baseline)
        self.assertNotIn(next_service.guide_id, self.view._catalog_manual_views)
        self.assertFalse(self.progress_path.exists())

    def test_lazy_factory_invalid_service_and_source_id_fail_closed(self):
        key = "source_guide:fictional-wrong"
        self.view._imported_source_factories[key] = lambda: self.service
        self.approved = True
        self.assertFalse(self.view.select_guide(key))
        self.assertNotIn(key, self.view._loaded_imported_source_services)
        self.assertFalse(self.progress_path.exists())

        with self.assertRaisesRegex(ValueError, "independent authorizer"):
            ManualRouteGuidesView(
                self.messages.append,
                imported_source_factories={"source_guide:fictional-lazy": lambda: self.service},
            )
        with self.assertRaisesRegex(ValueError, "exactly one runtime owner"):
            ManualRouteGuidesView(
                self.messages.append,
                imported_source_services={self.service.guide_id: self.service},
                imported_source_factories={self.service.guide_id: lambda: self.service},
                imported_source_authorizer=lambda *_: True,
            )

    def test_attested_package_witness_revocation_closes_shared_source_reader(self):
        key = "source_guide:fictional-packaged"
        route = _source_route("fictional-packaged")
        root = Path(self.tmp.name)
        payload = json.dumps(route, sort_keys=True).encode("utf-8")
        (root / "fictional-packaged.json").write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        valid = {"allowed": True}
        witness_calls = []

        def witness(guide_id, file_sha, source_sha, head_sha, receipt):
            witness_calls.append((guide_id, file_sha, source_sha, head_sha, receipt))
            return (valid["allowed"] and guide_id == key
                    and file_sha == digest and source_sha == TEST_SOURCE
                    and head_sha == TEST_HEAD and receipt == "synthetic-only")

        package = GuideTrustedSourcePackage(
            root,
            {key: GuidePackageEntry(
                key, "fictional-packaged.json", digest,
                TEST_SOURCE, TEST_HEAD, "synthetic-only",
            )},
            build_head_sha=TEST_HEAD, witness=witness,
        )
        self.view._imported_source_factories.update(
            package.factories(
                self.quest_progress, self.achievement_progress, self.progress,
            )
        )
        self.view._imported_source_authorizer = package.authorize
        self.assertFalse(package._loaded)
        self.assertFalse(self.progress_path.exists())

        self.assertTrue(self.view.select_guide(key))
        self.assertIsInstance(self.view.stack.currentWidget(), SharedGuideManualView)
        self.assertGreaterEqual(len(witness_calls), 2)
        self.assertFalse(self.progress_path.exists())

        valid["allowed"] = False
        self.view.refresh_external_progress()
        self.assertIsNone(self.view.current_guide_id)
        self.assertEqual(self.view.stack.currentWidget(), self.view.home_page)
        self.assertNotIn(key, self.view._catalog_manual_views)
        self.assertNotIn(key, self.view._loaded_imported_source_services)
        self.assertFalse(self.progress_path.exists())

        # Reauthorize a fresh reader, then mutate its installed bytes:
        # refresh must also evict the now-invalid reader without any writes.
        valid["allowed"] = True
        self.assertTrue(self.view.select_guide(key))
        packaged = root / "fictional-packaged.json"
        packaged.write_bytes(payload + b" ")
        self.view.refresh_external_progress()
        self.assertIsNone(self.view.current_guide_id)
        self.assertIs(self.view.stack.currentWidget(), self.view.home_page)
        self.assertNotIn(key, self.view._catalog_manual_views)
        self.assertNotIn(key, self.view._loaded_imported_source_services)
        self.assertFalse(self.progress_path.exists())

    def test_shared_validation_uses_source_id_and_does_not_touch_other_guides(self):
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        reader = self.view.stack.currentWidget()
        reader._show_index(0)
        QApplication.processEvents()
        reader.validation_layout.itemAt(0).widget().click()
        QApplication.processEvents()
        self.assertTrue(self.service.page_checked("character:1", self.service.cards[0]))
        self.assertFalse(self.service.page_checked("character:2", self.service.cards[0]))
        self.assertEqual(self.service.route_sheet_progress("character:1"), (1, 2))
        self.assertFalse(self.progress.manual_steps("character:1", "guide_ultime_v5"))
        self.assertFalse(self.progress.manual_steps(
            "character:1", "catalog_manual:dofus_sylvestre"
        ))
        self.view.set_character_key("character:2")
        reader._show_index(0)
        # The header intentionally describes the selected participant team,
        # not the character merely browsing the guide.
        self.assertEqual(reader.route_progress_label.text(), "50 %")
        self.view.guide_participant_service.save_selected_keys(("character:2",))
        reader.refresh(reset_to_active=True)
        reader._show_index(0)
        self.assertEqual(reader.route_progress_label.text(), "0 %")
        self.assertFalse(self.service.page_checked("character:2", self.service.cards[0]))

    def test_authorized_source_uses_atomic_shared_team_progress_and_undo(self):
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        self.view.guide_participant_service.save_selected_keys(
            ("character:1", "character:2")
        )
        reader = self.view.stack.currentWidget()
        reader.refresh(reset_to_active=True)
        reader._show_index(0)
        QApplication.processEvents()
        reader.validation_layout.itemAt(0).widget().click()
        QApplication.processEvents()
        self.assertTrue(self.service.page_checked("character:1", self.service.cards[0]))
        self.assertTrue(self.service.page_checked("character:2", self.service.cards[0]))
        self.assertEqual(self.service.route_sheet_progress("character:1"), (1, 2))
        self.assertEqual(self.service.route_sheet_progress("character:2"), (1, 2))
        self.assertFalse(self.progress.manual_steps("character:1", "guide_ultime_v5"))
        # Undo only the selected second participant, preserving first.
        self.view.guide_participant_service.save_selected_keys(("character:2",))
        reader.refresh(reset_to_active=True)
        reader._show_index(0)
        QApplication.processEvents()
        undo = reader.validation_layout.itemAt(0).widget()
        self.assertEqual(undo.text(), "Annuler validation")
        undo.click()
        QApplication.processEvents()
        self.assertTrue(self.service.page_checked("character:1", self.service.cards[0]))
        self.assertFalse(self.service.page_checked("character:2", self.service.cards[0]))

    def test_guide_specific_prerequisite_disables_validation_without_order_prompt(self):
        self.service.cards[0]["hard_runtime_gates"] = [
            {"kind": "alignment", "expected": "Bonta"}
        ]
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        reader = self.view.stack.currentWidget()
        reader._show_index(0)
        QApplication.processEvents()
        button = reader.validation_layout.itemAt(0).widget()
        self.assertFalse(button.isEnabled())
        self.assertEqual(button.text(), "Prérequis à vérifier")
        self.assertIn("prérequis", button.toolTip())
        self.assertFalse(self.progress_path.exists())
        self.assertFalse(self.service.manual_order_choice_blocking(
            "character:1", self.service.cards[1],
        ))

    def test_revocation_between_render_and_click_blocks_atomic_team_write(self):
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        reader = self.view.stack.currentWidget()
        reader._show_index(0)
        QApplication.processEvents()
        button = reader.validation_layout.itemAt(0).widget()
        self.assertTrue(button.isEnabled())
        # A trusted release can be revoked after this button was rendered.
        self.approved = False
        button.click()
        QApplication.processEvents()
        self.assertFalse(self.progress_path.exists())
        self.assertFalse(self.service.page_checked("character:1", self.service.cards[0]))
        refreshed = reader.validation_layout.itemAt(0).widget()
        self.assertFalse(refreshed.isEnabled())
        self.assertIn("non autorisé", refreshed.toolTip())
        self.service.set_page_checked("character:1", self.service.cards[0], 0, True)
        self.assertFalse(self.progress_path.exists())

    def test_source_preparation_ready_respects_revocation_and_atomic_team_progress(self):
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        self.view.guide_participant_service.save_selected_keys(
            ("character:1", "character:2")
        )
        reader = self.view.stack.currentWidget()
        reader.refresh(reset_to_active=True)
        need = _PreparationNeed(
            item_key="fictional-preparation-item",
            item_id=None,
            name="Ressource fictive",
            category="Ressources",
            required_by_character=(("character:1", 1), ("character:2", 1)),
        )
        # Hold the Python owner: Qt destroys child widgets if the temporary
        # parent frame goes out of scope before the assertions.
        row = reader._preparation_row(need)
        ready = row.findChild(QToolButton, "GuidePreparationReady")
        self.assertIsNotNone(ready)
        self.assertTrue(ready.isEnabled())
        # Approval can disappear AFTER this checkbox was rendered.
        self.approved = False
        ready.click()
        QApplication.processEvents()
        self.assertFalse(self.progress_path.exists())
        denied_row = reader._preparation_row(need)
        disabled = denied_row.findChild(QToolButton, "GuidePreparationReady")
        self.assertIsNotNone(disabled)
        self.assertFalse(disabled.isEnabled())
        self.assertIn("non autorisé", disabled.toolTip())

        self.approved = True
        reader._set_need_ready(need, True)
        key = reader._ready_progress_key(need)
        for character in ("character:1", "character:2"):
            self.assertTrue(self.progress.is_manual_step_completed(
                character, self.service.progress_id, key,
            ))
        self.assertFalse(self.progress.manual_steps(
            "character:1", "guide_ultime_v5"
        ))

        # Revocation must also block the undo path, preserving both entries.
        self.approved = False
        reader._set_need_ready(need, False)
        for character in ("character:1", "character:2"):
            self.assertTrue(self.progress.is_manual_step_completed(
                character, self.service.progress_id, key,
            ))

    def test_revoked_authorization_blocks_reopen_and_exits_on_refresh(self):
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        reader = self.view.stack.currentWidget()
        self.approved = False
        self.assertFalse(self.view.select_guide(self.service.guide_id))
        # An immediately revoked route is also hidden, not left on screen.
        self.assertEqual(self.view.stack.currentWidget(), self.view.home_page)
        self.assertIsNone(self.view.current_guide_id)
        # Revocation also disposes the cached source reader; no stale Qt route.
        self.assertNotIn(self.service.guide_id, self.view._catalog_manual_views)
        self.assertEqual(self.view.stack.indexOf(reader), -1)
        self.view.refresh_external_progress()
        self.assertEqual(self.view.state, self.view.CATALOG)
        self.assertIsNone(self.view.current_guide_id)
        self.assertEqual(self.view.stack.currentWidget(), self.view.home_page)
        self.assertFalse(self.progress_path.exists())


if __name__ == "__main__":
    unittest.main()
