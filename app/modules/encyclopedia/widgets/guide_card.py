from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from app.modules.encyclopedia.models import Guide
from app.modules.encyclopedia.providers.dofus_item_provider import DOFUS_UNKNOWN_ICON
from app.ui.theme import PALETTE

GUIDE_ID_ROLE = Qt.UserRole + 11
GUIDE_ROLE = Qt.UserRole + 12
GUIDE_PROGRESS_ROLE = Qt.UserRole + 13
GUIDE_GROUP_ROLE = Qt.UserRole + 14


class GuideListModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.guides: list[Guide] = []
        self.entries: list[Guide | str] = []
        self.progress_by_guide: dict[str, tuple[int, int, str]] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self.entries):
            return None
        entry = self.entries[index.row()]
        if isinstance(entry, str):
            if role in (Qt.DisplayRole, GUIDE_GROUP_ROLE):
                return entry
            if role == Qt.SizeHintRole:
                return QSize(280, 28)
            return None
        guide = entry
        done, total, state = self.progress_by_guide.get(guide.id, (0, 0, "Non commencé"))
        percent = int(round((done / total) * 100)) if total else 0
        if role == Qt.DisplayRole:
            levels = self._level_text(guide)
            label = guide.category_label or guide.category
            status = " • Partiel" if guide.completeness_status == "partial" else ""
            return f"{guide.title}\n{label}{status}\n{levels}\n{done} / {total} {self._progress_word(guide, total)}                 {percent} %"
        if role == Qt.DecorationRole:
            if guide.image_path and Path(guide.image_path).exists():
                return QIcon(guide.image_path)
            if DOFUS_UNKNOWN_ICON.exists():
                return QIcon(str(DOFUS_UNKNOWN_ICON))
        if role == Qt.ToolTipRole:
            return guide.description or guide.title
        if role == GUIDE_ID_ROLE:
            return guide.id
        if role == GUIDE_ROLE:
            return guide
        if role == GUIDE_PROGRESS_ROLE:
            return done, total, state, percent
        if role == Qt.SizeHintRole:
            return QSize(280, 84)
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        entry = self.entries[index.row()]
        if isinstance(entry, str):
            return Qt.ItemIsEnabled
        return super().flags(index)

    def set_guides(self, guides: list[Guide]) -> None:
        self.beginResetModel()
        self.guides = list(guides)
        self.entries = self._grouped_entries(self.guides)
        self.endResetModel()

    def set_progress(self, progress_by_guide: dict[str, tuple[int, int, str]]) -> None:
        self.progress_by_guide = dict(progress_by_guide)
        if self.entries:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.entries) - 1, 0), [Qt.DisplayRole])

    def row_for_guide(self, guide_id: str) -> int:
        for row, entry in enumerate(self.entries):
            if isinstance(entry, Guide) and entry.id == str(guide_id):
                return row
        return -1

    @staticmethod
    def _grouped_entries(guides: list[Guide]) -> list[Guide | str]:
        entries: list[Guide | str] = []
        current_category = ""
        for guide in guides:
            if guide.category != current_category:
                current_category = guide.category
                entries.append((guide.category_label or guide.category).upper())
            entries.append(guide)
        return entries

    @staticmethod
    def _level_text(guide: Guide) -> str:
        if guide.recommended_level_min is None and guide.recommended_level_max is None:
            return "niveau ?"
        if guide.recommended_level_min == guide.recommended_level_max:
            return f"niveau {guide.recommended_level_min}"
        if guide.recommended_level_min is None:
            return f"niveau <= {guide.recommended_level_max}"
        if guide.recommended_level_max is None:
            return f"niveau >= {guide.recommended_level_min}"
        return f"niveau {guide.recommended_level_min}-{guide.recommended_level_max}"

    @staticmethod
    def _progress_word(guide: Guide, total: int) -> str:
        required = list(guide.required_steps)
        if total and required and all(step.step_type == "quest" for step in required):
            return "quête" if total == 1 else "quêtes"
        return "étape" if total == 1 else "étapes"


class GuideCardDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        guide = index.data(GUIDE_ROLE)
        group_label = index.data(GUIDE_GROUP_ROLE)
        if isinstance(group_label, str) and not isinstance(guide, Guide):
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            rect = option.rect.adjusted(6, 4, -6, -2)
            font = QFont(option.font)
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(PALETTE["TEXT_MUTED"]))
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, group_label)
            painter.setPen(QPen(QColor(PALETTE["BORDER"]), 1))
            painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
            painter.restore()
            return
        if not isinstance(guide, Guide):
            super().paint(painter, option, index)
            return

        done, total, state, percent = index.data(GUIDE_PROGRESS_ROLE) or (0, 0, "Non commencé", 0)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        rect = option.rect.adjusted(3, 3, -3, -3)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        fill = QColor(
            PALETTE["PANEL_ACTIVE"]
            if selected
            else PALETTE["PANEL_HOVER"]
            if hovered
            else PALETTE["PANEL_2"]
        )
        border = QColor(PALETTE["GREEN"] if selected else PALETTE["BORDER"])
        painter.setPen(QPen(border, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 6, 6)
        if selected:
            painter.fillRect(
                rect.left(),
                rect.top() + 5,
                3,
                rect.height() - 10,
                QColor(PALETTE["GREEN"]),
            )

        icon_rect = rect.adjusted(10, 15, 0, 0)
        icon_rect.setWidth(48)
        icon_rect.setHeight(48)
        icon = index.data(Qt.DecorationRole)
        if isinstance(icon, QIcon):
            painter.drawPixmap(icon_rect, icon.pixmap(48, 48))

        text_left = icon_rect.right() + 10
        text_right = rect.right() - 10
        y = rect.top() + 8
        title_font = QFont(option.font)
        title_font.setBold(True)
        title_font.setPointSize(10)
        painter.setFont(title_font)
        painter.setPen(QColor(PALETTE["TEXT"]))
        painter.drawText(text_left, y, text_right - text_left, 18, Qt.AlignLeft | Qt.AlignVCenter, guide.title)

        meta_font = QFont(option.font)
        meta_font.setPointSize(8)
        painter.setFont(meta_font)
        painter.setPen(QColor(PALETTE["TEXT_MUTED"]))
        y += 18
        label = guide.category_label or guide.category
        status = " • Partiel" if guide.completeness_status == "partial" else ""
        painter.drawText(
            text_left,
            y,
            text_right - text_left,
            16,
            Qt.AlignLeft | Qt.AlignVCenter,
            f"{label}{status}",
        )

        y += 15
        painter.drawText(text_left, y, text_right - text_left, 14, Qt.AlignLeft | Qt.AlignVCenter, GuideListModel._level_text(guide))

        y += 15
        painter.setPen(QColor(PALETTE["TEXT_SOFT"]))
        painter.drawText(text_left, y, text_right - text_left - 50, 15, Qt.AlignLeft | Qt.AlignVCenter, f"{done} / {total} {GuideListModel._progress_word(guide, total)}")
        painter.drawText(text_right - 48, y, 48, 15, Qt.AlignRight | Qt.AlignVCenter, f"{percent} %")

        bar_rect = option.rect.adjusted(text_left, 72, -10, -7)
        painter.setPen(QPen(QColor(PALETTE["BORDER_SOFT"]), 1))
        painter.setBrush(QColor(PALETTE["SIDEBAR"]))
        painter.drawRoundedRect(bar_rect, 3, 3)
        if total:
            chunk = bar_rect.adjusted(1, 1, -1, -1)
            chunk.setWidth(max(0, int(chunk.width() * percent / 100)))
            painter.setPen(Qt.NoPen)
            painter.setBrush(
                QColor(PALETTE["GREEN"] if state == "Terminé" else PALETTE["YELLOW"])
            )
            painter.drawRoundedRect(chunk, 3, 3)
        painter.restore()

    def sizeHint(self, option, index: QModelIndex) -> QSize:
        if isinstance(index.data(GUIDE_GROUP_ROLE), str):
            return QSize(option.rect.width(), 28)
        return QSize(option.rect.width(), 84)
