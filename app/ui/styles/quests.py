from __future__ import annotations

from app.ui.theme import render_theme_template


_QUEST_HIERARCHY_STYLE = """
QTreeWidget#QuestHierarchyTree {
    background: @BG;
    border: none;
    color: @TEXT_MUTED;
    outline: none;
}
QTreeWidget#QuestHierarchyTree::item {
    min-height: 24px;
    padding: 1px 3px;
}
QTreeWidget#QuestHierarchyTree::item:hover {
    background: @PANEL_HOVER;
}
QTreeWidget#QuestHierarchyTree::item:selected {
    background: @PANEL_ACTIVE;
    color: @TEXT;
}
"""

_QUEST_ITEM_ROW_STYLE = """
QFrame#GuideItemRow[state="done"],
QFrame#GuideQuestItemRow[state="done"],
QFrame#QuestItemRow[state="done"] {
    background: @PANEL_ACTIVE;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
}
QToolButton#GuideItemIcon[state="todo"] {
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
}
QToolButton#GuideItemIcon[state="done"] {
    background: @PANEL_ACTIVE;
    border: 1px solid @GREEN;
    border-radius: @RADIUS_XS;
}
"""


def quest_hierarchy_stylesheet(base_style: str = "") -> str:
    local = render_theme_template(_QUEST_HIERARCHY_STYLE)
    return f"{base_style}\n{local}" if base_style else local


def quest_item_row_stylesheet() -> str:
    return render_theme_template(_QUEST_ITEM_ROW_STYLE)


__all__ = ["quest_hierarchy_stylesheet", "quest_item_row_stylesheet"]
