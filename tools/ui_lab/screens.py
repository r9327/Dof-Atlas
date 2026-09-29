from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from unittest.mock import patch

if TYPE_CHECKING:
    from PySide6.QtWidgets import QAbstractScrollArea, QWidget


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


def _mark_scroll_target(root: "QWidget", area: "QAbstractScrollArea | None", fallback_name: str) -> None:
    if area is None:
        return
    name = str(area.objectName() or "").strip()
    if not name:
        name = fallback_name
        area.setObjectName(name)
    root.setProperty("uiLabCaptureScrollTarget", name)


class _EncyclopediaShellProxy:
    """Non-visual proxy used only to invoke AtlasWindow's real tab grouping logic."""

    def __init__(self, page: "QWidget", tab_name: str) -> None:
        self.page_widgets = {"Quetes": page}
        self.page_nav_group = {"Quetes": ""}
        self.pending_encyclopedia_tab = tab_name
        self.current_character_key = ""

    def refresh_nav_selection(self, _group: str) -> None:
        return


def _apply_product_encyclopedia_navigation(page: "QWidget", tab_name: str) -> None:
    """Run the exact AtlasWindow grouping/visibility path used by the product shell."""

    from main import AtlasWindow

    proxy = _EncyclopediaShellProxy(page, tab_name)
    AtlasWindow.finish_pending_encyclopedia_tab(proxy)
    if proxy.pending_encyclopedia_tab:
        raise RuntimeError(f"Navigation produit impossible vers {tab_name}")


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
    _apply_product_encyclopedia_navigation(page, tab_name)
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

    if getattr(view, "current_quest_id", None) is not None:
        detail = getattr(view, "quest_detail_view", None)
        _mark_scroll_target(page, getattr(detail, "center_scroll", None), "UiLabGuideQuestScroll")
    elif getattr(view, "detail_page", None) is not None:
        _mark_scroll_target(page, getattr(view, "center_scroll", None), "UiLabGuideOverviewScroll")
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
        detail = getattr(quest_page, "quest_detail_view", None)
        _mark_scroll_target(page, getattr(detail, "center_scroll", None), "UiLabQuestDetailScroll")
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
    if achievement_id is not None:
        if not view.select_achievement(achievement_id):
            raise ValueError(f"Succès introuvable ou non retenu pour la capture: {achievement_id}")
        _mark_scroll_target(page, getattr(view, "detail_scroll", None), "UiLabAchievementDetailScroll")
    return page


def _create_bestiary_preview(context: PreviewContext, tab_name: str) -> "QWidget":
    # These are currently canonical product placeholder tabs. The Lab deliberately
    # captures that real state instead of inventing a Bestiary implementation.
    return _build_encyclopedia_preview(context, tab_name)


def create_dungeons_preview(context: PreviewContext) -> "QWidget":
    return _create_bestiary_preview(context, "DONJONS")


def create_monsters_preview(context: PreviewContext) -> "QWidget":
    return _create_bestiary_preview(context, "MONSTRES")


def create_archmonsters_preview(context: PreviewContext) -> "QWidget":
    return _create_bestiary_preview(context, "ARCHIMONSTRES")


def create_wanted_preview(context: PreviewContext) -> "QWidget":
    return _create_bestiary_preview(context, "AVIS DE RECHERCHE")


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


class _NoopWindowEventWatcher:
    def __init__(self, *_args, **_kwargs) -> None:
        return

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def replace_tracked_hwnds(self, *_args, **_kwargs) -> None:
        return


def create_organizer_preview(context: PreviewContext) -> "QWidget":
    """Instantiate the real OrganizerPage with only persistence/OS watchers isolated."""

    import app.pages.organizer_page as organizer_module
    import app.storage as storage_module

    scratch = context.sandbox_root / "organizer"
    scratch.mkdir(parents=True, exist_ok=True)
    profile = scratch / "profiles.json"
    client_json = scratch / "clients.json"
    client_ini = scratch / "clients.ini"

    with (
        patch.multiple(
            organizer_module,
            PROFILE_FILE=profile,
            CLIENT_INDEX_JSON=client_json,
            CLIENT_INDEX_INI=client_ini,
            UnityWindowEventWatcher=_NoopWindowEventWatcher,
            scan_unity_sessions=lambda: [],
        ),
        patch.object(storage_module, "PROFILE_FILE", profile),
    ):
        page = organizer_module.OrganizerPage(
            context.report_status,
            lambda *_args, **_kwargs: None,
            stop_runtime_callback=lambda *_args, **_kwargs: None,
            launch_auto_group_callback=lambda *_args, **_kwargs: None,
            launch_travel_callback=lambda *_args, **_kwargs: None,
            launch_zaap_callback=lambda *_args, **_kwargs: None,
        )
    page.startup_scan_timer.stop()
    _mark_scroll_target(page, getattr(page, "sessions_area", None), "UiLabOrganizerSessionsScroll")
    return page


def _create_equipment_preview(context: PreviewContext, section: str) -> "QWidget":
    from app.pages.equipment_page import EquipmentPage

    page = EquipmentPage(context.report_status)
    setter = getattr(page, "set_section", None)
    if callable(setter):
        setter(section)
    # The actual product embeds a remote WebView. For deterministic skeleton
    # capture keep its real lightweight pre-WebEngine state instead of fetching
    # mutable external content during CI.
    page._web_start_scheduled = True
    return page


def create_equipment_pvm_preview(context: PreviewContext) -> "QWidget":
    return _create_equipment_preview(context, "PvM")


def create_equipment_pvp_preview(context: PreviewContext) -> "QWidget":
    return _create_equipment_preview(context, "PvP")


def create_equipment_builders_preview(context: PreviewContext) -> "QWidget":
    return _create_equipment_preview(context, "Builders")


def _product_placeholder(title: str, message: str, badge: str = "En travaux") -> "QWidget":
    from main import AtlasWindow

    return AtlasWindow.placeholder_page(None, title, message, badge=badge)


def create_almanax_preview(_context: PreviewContext) -> "QWidget":
    return _product_placeholder("Almanax", "Le module Almanax sera intégré ici.")


def create_tutorials_preview(_context: PreviewContext) -> "QWidget":
    return _product_placeholder("Tutoriels", "Les tutoriels seront intégrés ici.", badge="Tutoriels")


def create_dofus_noob_preview(_context: PreviewContext) -> "QWidget":
    return _product_placeholder(
        "Dofus Noob",
        "L'intégration des tutoriels Dofus Noob sera ajoutée ici.",
        badge="Tutoriels",
    )


def create_treasure_hunt_preview(_context: PreviewContext) -> "QWidget":
    return _product_placeholder("Chasse au trésor", "Le module Chasse au trésor sera intégré ici.")


def create_ocre_preview(_context: PreviewContext) -> "QWidget":
    return _product_placeholder("Ocre", "Le module Ocre sera intégré ici.")
