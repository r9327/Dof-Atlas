from __future__ import annotations

GUIDES_TAB = "GUIDES"
ACHIEVEMENTS_TAB = "SUCCÈS"
QUESTS_TAB = "QUÊTES"
DUNGEONS_TAB = "DONJONS"
MONSTERS_TAB = "MONSTRES"
ARCHMONSTERS_TAB = "ARCHIMONSTRES"
WANTED_TAB = "AVIS DE RECHERCHE"

GUIDE_TABS: tuple[str, ...] = (GUIDES_TAB, QUESTS_TAB, ACHIEVEMENTS_TAB)
BESTIARY_TABS: tuple[str, ...] = (DUNGEONS_TAB, MONSTERS_TAB, ARCHMONSTERS_TAB, WANTED_TAB)
ENCYCLOPEDIA_TABS: tuple[str, ...] = (*GUIDE_TABS, *BESTIARY_TABS)


def encyclopedia_tab_group(label: str) -> str:
    if label in GUIDE_TABS:
        return "Encyclopédie"
    if label in BESTIARY_TABS:
        return "Bestiaire"
    return ""


def encyclopedia_visible_tabs(label: str, available: tuple[str, ...]) -> tuple[str, ...]:
    group = GUIDE_TABS if label in GUIDE_TABS else BESTIARY_TABS if label in BESTIARY_TABS else available
    return tuple(tab for tab in available if tab in group)

DEFAULT_TAB = QUESTS_TAB
