from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


@dataclass(slots=True)
class PreviewContext:
    sandbox_root: Path
    report_status: Callable[[str], None]
    scenario: str = "default"
    params: dict[str, Any] = field(default_factory=dict)


def _int_param(context: PreviewContext, name: str) -> int | None:
    value = context.params.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Paramètre UI Lab invalide {name}={value!r}") from exc


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
    quest_id = _int_param(context, "quest_id")
    requested_guide_id = str(context.params.get("guide_id") or "").strip()

    if context.scenario in {"guide_first", "target"}:
        guide_id = requested_guide_id
        if not guide_id and quest_id is not None:
            candidates = view.provider.get_guides_for_entity("quest", quest_id)
            if candidates:
                guide_id = candidates[0].id
        if not guide_id and context.scenario == "guide_first":
            guides = list(getattr(view, "guides", ()) or ())
            if guides:
                guide_id = guides[0].id
        if not guide_id:
            raise ValueError("Le scénario Guides 'target' requiert guide_id ou quest_id")
        if not view.select_guide(guide_id):
            raise ValueError(f"Guide introuvable pour la capture: {guide_id}")
        if quest_id is not None and not view.show_quest_detail(quest_id):
            raise ValueError(f"Quête {quest_id} absente du guide {guide_id}")
    return page


def create_quests_preview(context: PreviewContext) -> "QWidget":
    from app.modules.encyclopedia.constants import QUESTS_TAB

    page = _build_encyclopedia_preview(context, QUESTS_TAB)
    quest_page = page.quest_page
    if quest_page is None:
        raise RuntimeError("La vraie page Quêtes n'a pas été chargée")

    quest_id = _int_param(context, "quest_id")
    if context.scenario == "detail_first" and quest_id is None:
        quests = list(getattr(quest_page.catalog, "quests", ()) or ())
        if quests:
            quest_id = int(quests[0].id)
    if context.scenario == "target" and quest_id is None:
        raise ValueError("Le scénario Quêtes 'target' requiert quest_id")
    if quest_id is not None:
        if quest_id not in quest_page.catalog.by_id:
            raise ValueError(f"Quête introuvable pour la capture: {quest_id}")
        quest_page.select_quest(quest_id, persist=False)
    return page


def create_achievements_preview(context: PreviewContext) -> "QWidget":
    from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB

    page = _build_encyclopedia_preview(context, ACHIEVEMENTS_TAB)
    view = page.ensure_tab_loaded(ACHIEVEMENTS_TAB)
    achievement_id = _int_param(context, "achievement_id")
    if context.scenario == "detail_first" and achievement_id is None:
        achievements = list(getattr(view, "achievements", ()) or ())
        if achievements:
            achievement_id = int(achievements[0].id)
    if context.scenario == "target" and achievement_id is None:
        raise ValueError("Le scénario Succès 'target' requiert achievement_id")
    if achievement_id is not None and not view.select_achievement(achievement_id):
        raise ValueError(f"Succès introuvable ou non retenu pour la capture: {achievement_id}")
    return page


def create_home_preview(context: PreviewContext) -> "QWidget":
    """Instantiate the canonical HomePage; scenarios only drive real product APIs."""

    from app.pages.home_page import HomePage, _apply_saved_progress

    page = HomePage()
    if context.scenario == "saved_progress":
        params = context.params
        page.set_character(
            str(params.get("character_key") or "ui-lab-character"),
            str(params.get("character_label") or "Personnage de prévisualisation"),
        )
        try:
            percent = int(params.get("percent", 42))
        except (TypeError, ValueError) as exc:
            raise ValueError("Le paramètre Home 'percent' doit être entier") from exc
        _apply_saved_progress(
            page,
            {
                "percent": percent,
                "chapter": str(params.get("chapter") or "Chapitre de prévisualisation"),
                "step": str(params.get("step") or "Étape de prévisualisation"),
                "zone": str(params.get("zone") or "[0, 0]"),
                "guide_id": str(params.get("guide_id") or "guide_complet"),
            },
        )
    return page
