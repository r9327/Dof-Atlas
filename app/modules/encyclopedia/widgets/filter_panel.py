from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.numbers import clamped_percent
from app.modules.encyclopedia.models.achievement import AchievementCategory
from app.ui.components import (
    AtlasComboBox, configure_unity_progress_bar, configure_unity_scroll_area,
    configure_unity_number_spinbox, clear_unity_widget_layout,
)
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX


FILTER_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["achievement_filters"]


class AchievementFilterPanel(QWidget):
    filtersChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("AchievementFilterPanel")
        self.categories: list[AchievementCategory] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(*FILTER_GEOMETRY["page_margins"])
        root.setSpacing(FILTER_GEOMETRY["page_spacing"])
        title = QLabel("Filtres")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        self.category_combo = AtlasComboBox()
        self.subcategory_combo = AtlasComboBox()
        self.min_level = configure_unity_number_spinbox(
            QSpinBox(), minimum=0, maximum=999, value=0,
        )
        self.max_level = configure_unity_number_spinbox(
            QSpinBox(), minimum=0, maximum=999, value=999,
        )
        self.state_combo = AtlasComboBox()
        self.hide_completed = QCheckBox("Masquer les succès terminés")

        self.state_combo.addItems(["Tous", "Terminés", "Non terminés"])

        for label, widget in (
            ("Catégorie", self.category_combo),
            ("Sous-catégorie", self.subcategory_combo),
            ("Niveau minimum", self.min_level),
            ("Niveau maximum", self.max_level),
            ("État", self.state_combo),
        ):
            root.addWidget(self._label(label))
            root.addWidget(widget)
        root.addWidget(self.hide_completed)

        self.category_area = configure_unity_scroll_area(QScrollArea())
        self.category_area.setObjectName("CategoryProgressArea")
        self.category_content = QWidget()
        self.category_layout = QVBoxLayout(self.category_content)
        self.category_layout.setContentsMargins(0, 0, 0, 0)
        self.category_layout.setSpacing(FILTER_GEOMETRY["category_spacing"])
        self.category_area.setWidget(self.category_content)
        root.addWidget(self._label("Progression catégories"))
        root.addWidget(self.category_area, 1)

        self.category_combo.currentIndexChanged.connect(self.rebuild_subcategories)
        self.category_combo.currentIndexChanged.connect(self.filtersChanged)
        self.subcategory_combo.currentIndexChanged.connect(self.filtersChanged)
        self.min_level.valueChanged.connect(self.filtersChanged)
        self.max_level.valueChanged.connect(self.filtersChanged)
        self.state_combo.currentIndexChanged.connect(self.filtersChanged)
        self.hide_completed.toggled.connect(self.filtersChanged)

    def set_categories(self, categories: list[AchievementCategory]) -> None:
        self.categories = list(categories)
        with QSignalBlocker(self.category_combo):
            self.category_combo.clear()
            self.category_combo.addItem("Toutes", 0)
            for category in self.parent_categories():
                self.category_combo.addItem(category.name, category.id)
        self.rebuild_subcategories()

    def set_category_cards(self, summaries: list[tuple[str, int, int]]) -> None:
        clear_unity_widget_layout(self.category_layout, detach_widgets=False)
        for name, completed, total in summaries:
            card = QFrame()
            card.setObjectName("CategoryProgressCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(*FILTER_GEOMETRY["card_margins"])
            layout.setSpacing(FILTER_GEOMETRY["card_spacing"])
            row = QHBoxLayout()
            label = QLabel(name)
            label.setObjectName("CompactLabel")
            count = QLabel(self._progress_text(completed, total))
            count.setObjectName("MutedLabel")
            row.addWidget(label, 1)
            row.addWidget(count)
            bar = configure_unity_progress_bar(
                QProgressBar(), object_name="EncyclopediaProgressBar",
            )
            bar.setValue(clamped_percent(completed, total))
            layout.addLayout(row)
            layout.addWidget(bar)
            self.category_layout.addWidget(card)
        self.category_layout.addStretch(1)

    def filters(self) -> dict[str, object]:
        return {
            "category_id": int(self.category_combo.currentData() or 0),
            "subcategory_id": int(self.subcategory_combo.currentData() or 0),
            "min_level": int(self.min_level.value()),
            "max_level": int(self.max_level.value()),
            "state": self.state_combo.currentText(),
            "hide_completed": bool(self.hide_completed.isChecked()),
        }

    def parent_categories(self) -> list[AchievementCategory]:
        return [
            category
            for category in self.categories
            if category.parent_id == 0
        ]

    def rebuild_subcategories(self) -> None:
        parent_id = int(self.category_combo.currentData() or 0)
        with QSignalBlocker(self.subcategory_combo):
            self.subcategory_combo.clear()
            self.subcategory_combo.addItem("Toutes", 0)
            for category in self.categories:
                if parent_id and category.parent_id == parent_id:
                    self.subcategory_combo.addItem(category.name, category.id)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("MutedLabel")
        return label

    @staticmethod
    def _progress_text(completed: int, total: int) -> str:
        percent = clamped_percent(completed, total)
        return f"{completed}/{total} · {percent}%"
