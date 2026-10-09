from __future__ import annotations

"""Offscreen, opt-in real Guide/Success deferred-UI lifecycle scenario.

No catalog hydration, no user profile edits, no application start and no
background worker; used only via Doctor's explicit runtime-trace command.
"""
from tempfile import TemporaryDirectory
from pathlib import Path
from tools.atlas_doctor_lib.runtime_observation import active_observer


def main() -> None:
    observer = active_observer()
    if observer is None:
        raise RuntimeError("Run through Doctor runtime-trace, never app startup")
    from PySide6.QtWidgets import QApplication
    from shiboken6 import delete, isValid
    from app.modules.encyclopedia.views.guides_view import GuidesView
    from app.modules.encyclopedia.views.achievements_view import AchievementsView
    from app.pages.quests_page import QuestsPage
    from app.quest_catalog import QuestCatalog, QuestRecord
    from app.modules.encyclopedia.providers.quest_provider import QuestProvider
    from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService

    application = QApplication.instance() or QApplication([])
    statuses: list[str] = []
    with TemporaryDirectory(prefix="doctor-ui-smoke-") as folder:
        temp = Path(folder)
        # No production data providers are hydrated in deferred mode.
        guide = GuidesView(
            statuses.append, provider=object(), quest_provider=object(),
            achievement_provider=object(), achievement_progress_service=object(),
            guide_progress_service=object(), quest_progress_path=temp / "quests.json",
            achievement_progress_path=temp / "success.json",
            guide_progress_path=temp / "guides.json", defer_runtime=True,
        )
        if guide._runtime_ready or guide.detail_page is not None:
            raise AssertionError("Guide eagerly hydrated rich data/detail")
        if guide.home_empty.text() != "Chargement des guides…":
            raise AssertionError("Guide deferred shell unavailable")
        observer.watch(guide, label="guides-deferred", kind="qwidget")
        observer.watch_qt_destroyed(guide, label="guides-deferred")
        success = AchievementsView(
            statuses.append, provider=object(), progress_service=object(),
            quest_provider=object(), quest_progress_service=object(),
            defer_runtime=True,
        )
        if success._runtime_ready or success.achievements:
            raise AssertionError("Success view hydrated catalog in deferred mode")
        observer.watch(success, label="success-deferred", kind="qwidget")
        observer.watch_qt_destroyed(success, label="success-deferred")
        # A single synthetic quest exercises real hierarchy/search without
        # loading the 1,976-item production catalog or writing player progress.
        quest = QuestRecord(id=991234, name="Mission Doctor Atlas",
                            category="Diagnostic", level_min=1, level_max=1,
                            start_criterion="")
        empty_catalog = QuestCatalog([quest])
        quest_provider = QuestProvider(catalog=empty_catalog)
        quest_graph = QuestGraphService(quest_provider, eager=False)
        quests = QuestsPage(
            statuses.append, catalog=empty_catalog, quest_provider=quest_provider,
            graph=quest_graph, achievement_progress_service=object(),
            progress_path=temp / "quest_progress.json",
            profile_path=temp / "profiles.json",
            client_index_path=temp / "clients.json",
            owned_items_path=temp / "items.json",
            defer_detail_view=True,
        )
        if quests.quest_detail_view is not None or len(quests.catalog.quests) != 1:
            raise AssertionError("Quest smoke initialized rich detail or external catalog")
        quests.search.setText("Mission Doctor")
        matches = quests.matching_quests()
        if [row.id for row in matches] != [quest.id]:
            raise AssertionError("Real Quests search did not return the synthetic quest")
        if quests.quest_detail_view is not None:
            raise AssertionError("Search unexpectedly initialized rich Quest detail")
        quests.search.clear()
        observer.watch(quests, label="quests-empty", kind="qwidget")
        observer.watch_qt_destroyed(quests, label="quests-empty")
        observer.snapshot_watches(label="deferred-created")
        observer.snapshot_qt_objects(label="deferred-created")
        delete(quests)
        delete(success)
        delete(guide)
        if isValid(quests) or isValid(success) or isValid(guide):
            raise AssertionError("A deferred Qt widget remained valid after deletion")
        observer.snapshot_watches(label="deferred-destroyed")
        observer.snapshot_qt_objects(label="deferred-destroyed")
    if not application:
        raise AssertionError("Qt application unavailable")


if __name__ == "__main__":
    main()
