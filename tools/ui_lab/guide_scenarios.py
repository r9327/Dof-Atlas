from __future__ import annotations

from typing import Any

from tools.ui_lab.screens import PreviewContext, _mark_scroll_target
from tools.ui_lab.screens import create_guides_preview as create_base_guides_preview


GPS_SCENARIOS = {
    "gps_active",
    "gps_page",
    "gps_prepare",
    "gps_combat",
}


def _manual_sections(service: Any, character_key: str, card: dict[str, Any]) -> dict[str, Any]:
    getter = getattr(service, "manual_sections_for_card", None)
    sections = getter(character_key, card) if callable(getter) else {}
    return sections if isinstance(sections, dict) else {}


def _visible_rows(value: object) -> list[dict[str, Any]]:
    return [
        row
        for row in (value or [])
        if isinstance(row, dict) and str(row.get("text") or "").strip()
    ] if isinstance(value, (list, tuple)) else []


def _card_has_prepare(service: Any, character_key: str, card: dict[str, Any]) -> bool:
    return bool(_visible_rows(_manual_sections(service, character_key, card).get("prepare")))


def _card_has_combat(service: Any, character_key: str, card: dict[str, Any]) -> bool:
    sections = _manual_sections(service, character_key, card)
    if _visible_rows(sections.get("boss")):
        return True
    tokens = ("combat", "boss", "vaincre", "battre", "donjon", "capture")
    for rows in sections.values():
        for row in _visible_rows(rows):
            text = str(row.get("text") or "").casefold()
            if any(token in text for token in tokens):
                return True
    return False


def _find_card_index(service: Any, character_key: str, predicate, label: str) -> int:
    cards = list(getattr(service, "cards", ()) or ())
    for index, card in enumerate(cards):
        if isinstance(card, dict) and predicate(service, character_key, card):
            return index
    raise ValueError(f"Aucune fiche réelle du Guide Ultime avec {label} n'a été trouvée")


def _focus_section_later(manual_view: Any, object_name: str) -> None:
    """Focus the requested real widget after Qt has laid out the manual sheet."""

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QWidget

    def focus() -> None:
        scroll = getattr(manual_view, "scroll", None)
        target = manual_view.findChild(QWidget, object_name)
        if scroll is not None and target is not None:
            scroll.ensureWidgetVisible(target, 0, 100)

    QTimer.singleShot(0, focus)
    QTimer.singleShot(100, focus)


def create_guides_preview(context: PreviewContext):
    """Extend the normal Guide preview with real Guide Ultime GPS states."""

    page = create_base_guides_preview(context)
    if context.scenario not in GPS_SCENARIOS:
        return page

    from app.modules.encyclopedia.constants import GUIDES_TAB

    view = page.ensure_tab_loaded(GUIDES_TAB)
    if not view.select_guide("guide_complet"):
        raise RuntimeError("Le Guide Ultime réel n'est pas disponible pour la capture")

    manual_view = getattr(view, "guide_ultime_view", None)
    service = getattr(view, "guide_ultime_service", None)
    if manual_view is None or service is None or not bool(getattr(service, "available", False)):
        raise RuntimeError("La vue GPS réelle du Guide Ultime n'a pas été matérialisée")

    character_key = str(getattr(manual_view, "character_key", "") or "")
    if context.scenario == "gps_active":
        manual_view.go_active()
    elif context.scenario == "gps_page":
        raw_page = context.params.get("page", 1)
        try:
            page_number = int(raw_page)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Page Guide GPS invalide: {raw_page!r}") from exc
        total = len(getattr(service, "cards", ()) or ())
        if page_number < 1 or page_number > total:
            raise ValueError(f"Page Guide GPS hors plage: {page_number} (1..{total})")
        manual_view._show_index(page_number - 1)
    elif context.scenario == "gps_prepare":
        manual_view._show_index(
            _find_card_index(service, character_key, _card_has_prepare, "une section À PRÉPARER")
        )
        _focus_section_later(manual_view, "GuideManualResourceSection")
    elif context.scenario == "gps_combat":
        manual_view._show_index(
            _find_card_index(service, character_key, _card_has_combat, "un combat/boss")
        )
        _focus_section_later(manual_view, "GuideManualCombat")

    _mark_scroll_target(page, getattr(manual_view, "scroll", None), "UiLabGuideGpsScroll")
    return page
