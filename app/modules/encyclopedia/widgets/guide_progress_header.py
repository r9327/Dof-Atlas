from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QToolButton, QVBoxLayout

from app.modules.encyclopedia.models import Guide
from app.modules.encyclopedia.providers.dofus_item_provider import DOFUS_UNKNOWN_ICON
from app.storage import AtlasButton


class GuideProgressHeader(QFrame):
    hideCompletedChanged = Signal(bool)
    toggleSectionsRequested = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideProgressHeader")
        self.sections_expanded = True
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        root.addLayout(top)

        self.image = QToolButton()
        self.image.setObjectName("GuideHeaderImage")
        self.image.setFixedSize(82, 82)
        self.image.setIconSize(QSize(74, 74))
        self.image.setFocusPolicy(Qt.NoFocus)
        top.addWidget(self.image)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(4)
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
        progress_row.setContentsMargins(0, 2, 0, 0)
        progress_row.setSpacing(8)
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

        self.progress = QProgressBar()
        self.progress.setObjectName("EncyclopediaProgressBar")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        content.addWidget(self.progress)

        reward = QHBoxLayout()
        reward.setContentsMargins(0, 2, 0, 0)
        reward.setSpacing(6)
        self.reward_image = QToolButton()
        self.reward_image.setObjectName("GuideRewardImage")
        self.reward_image.setFixedSize(36, 36)
        self.reward_image.setIconSize(QSize(30, 30))
        self.reward_image.setFocusPolicy(Qt.NoFocus)
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
        percent = int(round((completed / total) * 100)) if total else 0
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
        required = list(guide.required_steps)
        if total and required and all(step.step_type == "quest" for step in required):
            return "quête" if total == 1 else "quêtes"
        return "étape" if total == 1 else "étapes"
