from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QToolButton, QVBoxLayout

from app.core.numbers import clamped_percent
from app.modules.encyclopedia.models import Guide
from app.modules.encyclopedia.providers.dofus_item_provider import DOFUS_UNKNOWN_ICON
from app.modules.encyclopedia.services.guide_progress_wording import guide_progress_noun
from app.ui.components import AtlasButton, configure_unity_progress_bar, configure_unity_tool_button
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

GUIDE_HEADER_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["guide_header"]


class GuideProgressHeader(QFrame):
    hideCompletedChanged = Signal(bool)
    toggleSectionsRequested = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideProgressHeader")
        self.sections_expanded = True
        root = QVBoxLayout(self)
        root.setContentsMargins(*GUIDE_HEADER_GEOMETRY["outer_margins"])
        root.setSpacing(GUIDE_HEADER_GEOMETRY["outer_spacing"])

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(GUIDE_HEADER_GEOMETRY["top_spacing"])
        root.addLayout(top)

        self.image = configure_unity_tool_button(
            QToolButton(), object_name="GuideHeaderImage",
            box=GUIDE_HEADER_GEOMETRY["cover_box"],
            icon_size=GUIDE_HEADER_GEOMETRY["cover_artwork"], focus_policy=Qt.NoFocus,
        )
        top.addWidget(self.image)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(GUIDE_HEADER_GEOMETRY["content_spacing"])
        top.addLayout(content, 1)

        self.title = QLabel("")
        self.title.setObjectName("DetailTitle")
        self.title.setWordWrap(True)
        self.meta = QLabel("")
        self.meta.setObjectName("MutedLabel")
        self.meta.setWordWrap(True)
        self.description = QLabel("")
        self.description.setObjectName("CompactLabel")
        self.description.setWordWrap(True)
        content.addWidget(self.title)
        content.addWidget(self.meta)
        content.addWidget(self.description)

        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(*GUIDE_HEADER_GEOMETRY["secondary_row_margins"])
        progress_row.setSpacing(GUIDE_HEADER_GEOMETRY["progress_spacing"])
        self.progress_label = QLabel("Progression")
        self.progress_label.setObjectName("PanelTitle")
        self.progress_text = QLabel("")
        self.progress_text.setObjectName("MutedLabel")
        self.progress_percent = QLabel("")
        self.progress_percent.setObjectName("CompactLabel")
        progress_row.addWidget(self.progress_label)
        progress_row.addWidget(self.progress_text, 1)
        progress_row.addWidget(self.progress_percent)
        content.addLayout(progress_row)

        self.progress = configure_unity_progress_bar(
            QProgressBar(), object_name="EncyclopediaProgressBar",
        )
        content.addWidget(self.progress)

        reward = QHBoxLayout()
        reward.setContentsMargins(*GUIDE_HEADER_GEOMETRY["secondary_row_margins"])
        reward.setSpacing(GUIDE_HEADER_GEOMETRY["reward_spacing"])
        self.reward_image = configure_unity_tool_button(
            QToolButton(), object_name="GuideRewardImage",
            box=GUIDE_HEADER_GEOMETRY["reward_box"],
            icon_size=GUIDE_HEADER_GEOMETRY["reward_artwork"], focus_policy=Qt.NoFocus,
        )
        self.reward_label = QLabel("")
        self.reward_label.setObjectName("MutedLabel")
        self.reward_label.setWordWrap(True)
        reward.addWidget(self.reward_image)
        reward.addWidget(self.reward_label, 1)
        content.addLayout(reward)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self.hide_completed_button = AtlasButton("Masquer les terminées")
        self.hide_completed_button.setObjectName("GuideHideCompletedToggle")
        self.hide_completed_button.setCheckable(True)
        self.hide_completed_button.toggled.connect(self._on_hide_completed_toggled)
        self.toggle_sections_button = AtlasButton("Tout réduire")
        self.toggle_sections_button.setObjectName("SecondaryButton")
        self.toggle_sections_button.clicked.connect(self.toggle_sections)
        actions.addWidget(self.hide_completed_button)
        actions.addWidget(self.toggle_sections_button)
        actions.addStretch(1)
        root.addLayout(actions)

    def set_guide(self, guide: Guide, completed: int, total: int) -> None:
        self.title.setText(guide.title)
        self.meta.setText(self._meta_text(guide))
        self.description.setText(guide.description)
        percent = clamped_percent(completed, total)
        self.progress_text.setText(f"{completed} / {total} {self._progress_word(guide, total)}")
        self.progress_percent.setText(f"{percent} %")
        self.progress.setValue(percent)
        self._set_icon(self.image, self._guide_image(guide))

        if guide.reward_item is not None:
            self.reward_label.setText(f"Récompense principale\n{guide.reward_item.name} • Niveau réel de l’objet {guide.reward_item.level or '?'}")
            self._set_icon(self.reward_image, guide.reward_item.image_path)
            self.reward_image.setVisible(True)
            self.reward_label.setVisible(True)
        else:
            self.reward_label.setText("Récompense principale\nNon renseignée dans les données locales")
            self._set_icon(self.reward_image, "")
            self.reward_image.setVisible(False)

    def hide_completed(self) -> bool:
        return self.hide_completed_button.isChecked()

    def sync_hide_completed_label(self) -> None:
        checked = self.hide_completed_button.isChecked()
        self.hide_completed_button.setText("✓ Terminées masquées" if checked else "Masquer les terminées")
        self.hide_completed_button.style().unpolish(self.hide_completed_button)
        self.hide_completed_button.style().polish(self.hide_completed_button)

    def _on_hide_completed_toggled(self, checked: bool) -> None:
        self.sync_hide_completed_label()
        self.hideCompletedChanged.emit(checked)

    def toggle_sections(self) -> None:
        self.sections_expanded = not self.sections_expanded
        self.toggle_sections_button.setText("Tout réduire" if self.sections_expanded else "Tout développer")
        self.toggleSectionsRequested.emit(self.sections_expanded)

    @staticmethod
    def _guide_image(guide: Guide) -> str:
        if guide.image_path and Path(guide.image_path).exists():
            return guide.image_path
        if guide.illustration_item is not None and guide.illustration_item.image_path:
            return guide.illustration_item.image_path
        return str(DOFUS_UNKNOWN_ICON) if DOFUS_UNKNOWN_ICON.exists() else ""

    @staticmethod
    def _set_icon(button: QToolButton, image_path: str) -> None:
        button.setIcon(QIcon(image_path) if image_path and Path(image_path).exists() else QIcon())

    @staticmethod
    def _meta_text(guide: Guide) -> str:
        levels = []
        if guide.recommended_level_min is not None:
            levels.append(str(guide.recommended_level_min))
        if guide.recommended_level_max is not None and guide.recommended_level_max != guide.recommended_level_min:
            levels.append(str(guide.recommended_level_max))
        level_text = "Niveau recommandé " + "–".join(levels) if levels else "Niveau recommandé non précisé"
        status = " • Partiel" if guide.completeness_status == "partial" else ""
        return f"Guide {guide.category_label or guide.category}{status} • {level_text}"

    @staticmethod
    def _progress_word(guide: Guide, total: int) -> str:
        return guide_progress_noun(guide, total)
