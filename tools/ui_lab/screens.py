from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


@dataclass(slots=True)
class PreviewContext:
    sandbox_root: Path
    report_status: Callable[[str], None]
    scenario: str = "default"


def _build_encyclopedia_preview(context: PreviewContext, tab_name: str) -> "QWidget":
    """Build the canonical EncyclopediaPage with real providers and sandboxed writes."""

    from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
    from app.modules.encyclopedia.services import QuestGraphService
    from app.modules.encyclopedia.views import EncyclopediaPage
    from app.quest_catalog import QuestCatalog

    scratch = context.sandbox_root / "encyclopedia"
    scratch.mkdir(parents=True, exist_ok=True)

    catalog = QuestCatalog.load()
    quest_provider = QuestProvider(catalog=catalog)
    achievement_provider = AchievementProvider(quest_provider=quest_provider)
    # Product contract: rich Success detail sources are prepared before opening a detail.
    achievement_provider.load_all()
    guide_provider = GuideProvider(
        quest_provider=quest_provider,
        achievement_provider=achievement_provider,
    )
    guide_provider.load_all()
    graph = QuestGraphService(
        quest_provider,
        guide_provider=guide_provider,
        achievement_provider=achievement_provider,
    )

    page = EncyclopediaPage(
        status_callback=context.report_status,
        quest_provider=quest_provider,
        achievement_provider=achievement_provider,
        guide_provider=guide_provider,
        progress_path=scratch / "quest_progress.json",
        achievement_progress_path=scratch / "achievement_progress.json",
        guide_progress_path=scratch / "guide_progress.json",
        profile_path=scratch / "client_profiles.json",
        client_index_path=scratch / "client_index.json",
        owned_items_path=scratch / "craft_selection.json",
        quest_graph=graph,
        initial_tab=tab_name,
    )
    page.ensure_tab_loaded(tab_name)
    page.tabs.setCurrentIndex(page.tab_labels().index(tab_name))
    page.sync_tab_accent(tab_name)
    page.sync_search_visibility()
    return page


def create_guides_preview(context: PreviewContext) -> "QWidget":
    from app.modules.encyclopedia.constants import GUIDES_TAB

    page = _build_encyclopedia_preview(context, GUIDES_TAB)
    view = page.ensure_tab_loaded(GUIDES_TAB)
    if context.scenario == "guide_first":
        guides = list(getattr(view, "guides", ()) or ())
        if guides:
            view.select_guide(guides[0].id)
    return page


def create_quests_preview(context: PreviewContext) -> "QWidget":
    from app.modules.encyclopedia.constants import QUESTS_TAB

    page = _build_encyclopedia_preview(context, QUESTS_TAB)
    quest_page = page.quest_page
    if context.scenario == "detail_first" and quest_page is not None:
        quests = list(getattr(quest_page.catalog, "quests", ()) or ())
        if quests:
            quest_page.select_quest(int(quests[0].id), persist=False)
    return page


def create_achievements_preview(context: PreviewContext) -> "QWidget":
    from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB

    page = _build_encyclopedia_preview(context, ACHIEVEMENTS_TAB)
    view = page.ensure_tab_loaded(ACHIEVEMENTS_TAB)
    if context.scenario == "detail_first":
        achievements = list(getattr(view, "achievements", ()) or ())
        if achievements:
            view.select_achievement(int(achievements[0].id))
    return page


def create_home_preview(context: PreviewContext) -> "QWidget":
    """Instantiate the canonical HomePage; scenarios only drive real product APIs."""

    from app.pages.home_page import HomePage, _apply_saved_progress

    page = HomePage()
    if context.scenario == "saved_progress":
        page.set_character("ui-lab-character", "Personnage de prévisualisation")
        _apply_saved_progress(
            page,
            {
                "percent": 42,
                "chapter": "Chapitre de prévisualisation",
                "step": "Étape de prévisualisation",
                "zone": "[0, 0]",
                "guide_id": "guide_complet",
            },
        )
    return page
