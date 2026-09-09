from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.modules.encyclopedia.models.achievement import AchievementCategory


class AchievementFilterPanel(QWidget):
    filtersChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("AchievementFilterPanel")
        self.categories: list[AchievementCategory] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(7)
        title = QLabel("Filtres")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        self.category_combo = QComboBox()
        self.subcategory_combo = QComboBox()
        self.min_level = QSpinBox()
        self.max_level = QSpinBox()
        self.state_combo = QComboBox()
        self.hide_completed = QCheckBox("Masquer les succès terminés")

        self.min_level.setRange(0, 999)
        self.max_level.setRange(0, 999)
        self.max_level.setValue(999)
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

        self.category_area = QScrollArea()
        self.category_area.setObjectName("CategoryProgressArea")
        self.category_area.setWidgetResizable(True)
        self.category_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.category_content = QWidget()
        self.category_layout = QVBoxLayout(self.category_content)
        self.category_layout.setContentsMargins(0, 0, 0, 0)
        self.category_layout.setSpacing(5)
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
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("Toutes", 0)
        for category in self.parent_categories():
            self.category_combo.addItem(category.name, category.id)
        self.category_combo.blockSignals(False)
        self.rebuild_subcategories()

    def set_category_cards(self, summaries: list[tuple[str, int, int]]) -> None:
        while self.category_layout.count():
            item = self.category_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for name, completed, total in summaries:
            card = QFrame()
            card.setObjectName("CategoryProgressCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(7, 6, 7, 6)
            layout.setSpacing(4)
            row = QHBoxLayout()
            label = QLabel(name)
            label.setObjectName("CompactLabel")
            count = QLabel(self._progress_text(completed, total))
            count.setObjectName("MutedLabel")
            row.addWidget(label, 1)
            row.addWidget(count)
            bar = QProgressBar()
            bar.setObjectName("EncyclopediaProgressBar")
            bar.setTextVisible(False)
            bar.setRange(0, 100)
            bar.setValue(int(round((completed / total) * 100)) if total else 0)
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
        self.subcategory_combo.blockSignals(True)
        self.subcategory_combo.clear()
        self.subcategory_combo.addItem("Toutes", 0)
        for category in self.categories:
            if parent_id and category.parent_id == parent_id:
                self.subcategory_combo.addItem(category.name, category.id)
        self.subcategory_combo.blockSignals(False)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("MutedLabel")
        return label

    @staticmethod
    def _progress_text(completed: int, total: int) -> str:
        percent = int(round((completed / total) * 100)) if total else 0
        return f"{completed}/{total} · {percent}%"
