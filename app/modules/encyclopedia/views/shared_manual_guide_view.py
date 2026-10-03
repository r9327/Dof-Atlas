from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.modules.encyclopedia.views.guide_ultime_manual_view import (
    GuideUltimeManualCard,
    GuideUltimeManualView,
)


class SharedGuideManualCard(GuideUltimeManualCard):
    """Manual card with one visual preparation container instead of red row tiles."""

    def _add_line_section(
        self,
        root: QVBoxLayout,
        title: str,
        rows,
        object_name: str,
        section_key: str,
    ) -> None:
        if section_key != "prepare":
            super()._add_line_section(root, title, rows, object_name, section_key)
            return

        visible = [
            row
            for row in rows or []
            if isinstance(row, dict) and str(row.get("text") or "").strip()
        ]
        if not visible:
            return

        # The red semantic belongs to the whole preparation section. Individual
        # rows stay transparent so several items read as one coherent block.
        frame = QFrame()
        frame.setObjectName("GuideManualWarningSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        heading = QLabel(title)
        heading.setObjectName("GuideManualSectionTitle")
        layout.addWidget(heading)

        for row in visible:
            text = str(row.get("text") or "").strip()
            position = str(row.get("position") or "").strip()
            kind = str(row.get("kind") or "")
            prefix = "⚠ " if kind == "warning" else "• "

            row_widget = QFrame()
            row_widget.setObjectName("GuideManualLineRow")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(7)

            line = QLabel()
            self._set_clickable_text(
                line,
                self._format_line_html(
                    prefix,
                    position,
                    text,
                    self._npc_names(text),
                    self._resource_names,
                ),
            )
            line.setObjectName("GuideManualLine")
            line.setWordWrap(True)
            row_layout.addWidget(line, 1)
            layout.addWidget(row_widget)

        root.addWidget(frame)


class SharedGuideManualView(GuideUltimeManualView):
    """Canonical manual road-book renderer reusable by Guide Succès and Lanyel."""

    def _render_window(self, *, reset_scroll: bool = False) -> None:
        self._clear_cards()
        if not self.service.cards:
            return
        index = max(0, min(self.view_index, len(self.service.cards) - 1))
        card = self.service.cards[index]
        self._add_manual_order_choice(card)
        widget = SharedGuideManualCard(
            self.service,
            self.character_key,
            card,
            index,
        )
        widget.questRequested.connect(self._open_quest_from_card)
        self._set_validation_widget(widget.page_check)
        self.cards_layout.addWidget(widget)
        self.cards_layout.addStretch(1)
        self.rendered_card_count = 1
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < len(self.service.cards) - 1)
        self.guide_button.setToolTip(
            "Revenir à la fiche Guide active."
            if index != self.active_index
            else "Retour au choix des Guides."
        )
        if reset_scroll:
            self._reset_scroll_to_top()

    def _open_quest_from_card(self, quest_id: int, stage_id: str, index: int) -> None:
        navigator = self.navigate_entity
        if not callable(navigator):
            return
        guide_id = str(getattr(self.service, "guide_id", "") or "guide_complet")
        navigator(
            "quest",
            int(quest_id),
            source="guide_gps",
            guide_id=guide_id,
            guide_stage_id=str(stage_id or ""),
            guide_index=int(index),
        )


__all__ = ["SharedGuideManualCard", "SharedGuideManualView"]
