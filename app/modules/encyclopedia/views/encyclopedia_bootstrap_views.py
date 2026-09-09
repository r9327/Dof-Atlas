from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Thread

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QProgressBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.background_work import background_io_priority
from app.constants import RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.achievement_catalog_policy import RETAINED_TOP_CATEGORY_IDS
from app.modules.encyclopedia.providers.guide_provider import (
    GUIDE_CATALOG_FILE,
    GUIDES_DIR,
)
from app.quest_catalog import doduda_rows, normalize_text, read_json_file, text_for


_GUIDE_ID_ROLE = Qt.UserRole + 701
_ACHIEVEMENT_ID_ROLE = Qt.UserRole + 702
_JSON_STRING_RE = re.compile(r'"title"\s*:\s*("(?:\\.|[^"\\])*")')


class GuideIndexView(QWidget):
    """Tiny Guide catalogue: catalog.json plus only each file's header bytes."""

    guideRequested = Signal(str)

    def __init__(self, guides_dir: Path = GUIDES_DIR, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideIndexView")
        self.guides_dir = Path(guides_dir)
        self._rows: list[tuple[str, str, str, int]] = []
        self._title_by_id: dict[str, str] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.search = QLineEdit()
        self.search.setObjectName("EncyclopediaSearch")
        self.search.setPlaceholderText("Rechercher un guide...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._render)
        root.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setObjectName("GuideIndexTree")
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tree.itemClicked.connect(self._on_item_clicked)
        root.addWidget(self.tree, 1)

        self.status = QLabel("")
        self.status.setObjectName("MutedLabel")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setVisible(False)
        root.addWidget(self.status)

        self._load_index()
        self._render()

    def _load_index(self) -> None:
        payload = self._read_json(self.guides_dir / GUIDE_CATALOG_FILE, {})
        if not isinstance(payload, dict):
            return
        category_labels = {
            str(row.get("id") or ""): str(row.get("label") or row.get("id") or "")
            for row in payload.get("categories", [])
            if isinstance(row, dict)
        }
        rows: list[tuple[str, str, str, int]] = []
        for entry in payload.get("guides", []):
            if not isinstance(entry, dict) or entry.get("enabled") is False:
                continue
            guide_id = str(entry.get("id") or "").strip()
            file_name = str(entry.get("file") or "").strip()
            if not guide_id or not file_name:
                continue
            category_id = str(entry.get("category") or "").strip()
            category = category_labels.get(category_id, category_id or "Guides")
            title = self._read_title_header(self.guides_dir / file_name, guide_id)
            try:
                order = int(entry.get("order") or 0)
            except (TypeError, ValueError):
                order = 0
            rows.append((guide_id, title, category, order))
            self._title_by_id[guide_id] = title
        self._rows = sorted(
            rows,
            key=lambda row: (normalize_text(row[2]), row[3], normalize_text(row[1]), row[0]),
        )

    @staticmethod
    def _read_json(path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return default

    @staticmethod
    def _fallback_title(guide_id: str) -> str:
        text = str(guide_id or "").replace("_", " ").strip()
        return text[:1].upper() + text[1:] if text else "Guide"

    @classmethod
    def _read_title_header(cls, path: Path, guide_id: str) -> str:
        try:
            with path.open("r", encoding="utf-8") as stream:
                header = stream.read(16 * 1024)
        except (OSError, UnicodeError):
            return cls._fallback_title(guide_id)
        match = _JSON_STRING_RE.search(header)
        if match is None:
            return cls._fallback_title(guide_id)
        try:
            value = json.loads(match.group(1))
        except (TypeError, ValueError, json.JSONDecodeError):
            value = ""
        return str(value or cls._fallback_title(guide_id)).strip()

    def set_search_text(self, text: str) -> None:
        value = str(text or "")
        if self.search.text() == value:
            return
        self.search.setText(value)

    def _render(self) -> None:
        query = normalize_text(self.search.text())
        tokens = [token for token in query.split("_") if token]
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            parents: dict[str, QTreeWidgetItem] = {}
            for guide_id, title, category, _order in self._rows:
                haystack = normalize_text(f"{title} {category} {guide_id}")
                if tokens and not all(token in haystack for token in tokens):
                    continue
                parent = parents.get(category)
                if parent is None:
                    parent = QTreeWidgetItem([category])
                    parent.setData(0, _GUIDE_ID_ROLE, "")
                    self.tree.addTopLevelItem(parent)
                    parents[category] = parent
                child = QTreeWidgetItem([title])
                child.setData(0, _GUIDE_ID_ROLE, guide_id)
                child.setToolTip(0, title)
                parent.addChild(child)
            for parent in parents.values():
                parent.setExpanded(True)
        finally:
            self.tree.blockSignals(False)

    def _on_item_clicked(self, item: QTreeWidgetItem) -> None:
        guide_id = str(item.data(0, _GUIDE_ID_ROLE) or "")
        if guide_id:
            self.guideRequested.emit(guide_id)

    def set_loading(self, guide_id: str) -> None:
        title = self._title_by_id.get(str(guide_id), self._fallback_title(str(guide_id)))
        self.status.setText(f"{title}…")
        self.status.setVisible(True)


class AchievementIndexView(QWidget):
    """Responsive Successes catalogue that never loads rich achievement payloads.

    Only achievements.json, achievement_categories.json and the French language
    table are read, on a low-priority background thread. Objectives, rewards,
    monsters, dungeons, items, spells and other documentary sources stay cold
    until the player explicitly selects one success.
    """

    achievementRequested = Signal(int)
    indexReady = Signal(object)

    def __init__(self, data_dir: Path = RAW_QUEST_DATA_DIR, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AchievementIndexView")
        self.data_dir = Path(data_dir)
        self._rows: list[tuple[int, str, str, str, int, int, int]] = []
        self._name_by_id: dict[int, str] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.search = QLineEdit()
        self.search.setObjectName("EncyclopediaSearch")
        self.search.setPlaceholderText("Rechercher un succès...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._render)
        root.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setObjectName("AchievementIndexTree")
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tree.itemClicked.connect(self._on_item_clicked)
        root.addWidget(self.tree, 1)

        self.status = QLabel("Chargement de la liste des succès…")
        self.status.setObjectName("MutedLabel")
        self.status.setAlignment(Qt.AlignCenter)
        root.addWidget(self.status)

        self.indexReady.connect(self._apply_rows)
        Thread(
            target=self._load_index_worker,
            name="DofusAtlasAchievementIndex",
            daemon=True,
        ).start()

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def _top_category_id(category_id: int, categories: dict[int, dict]) -> int:
        current = int(category_id)
        seen: set[int] = set()
        while current > 0 and current not in seen:
            seen.add(current)
            row = categories.get(current, {})
            parent = AchievementIndexView._safe_int(row.get("parentId"), 0)
            if parent <= 0:
                return current
            current = parent
        return int(category_id)

    def _load_index_worker(self) -> None:
        rows: list[tuple[int, str, str, str, int, int, int]] = []
        try:
            with background_io_priority():
                language = read_json_file(
                    self.data_dir / "languages" / "fr.json",
                    {"entries": {}},
                )
                entries = language.get("entries", {}) if isinstance(language, dict) else {}
                if not isinstance(entries, dict):
                    entries = {}
                achievements = doduda_rows(self.data_dir / "achievements.json")
                categories = doduda_rows(self.data_dir / "achievement_categories.json")

                category_names = {
                    int(category_id): text_for(
                        entries,
                        row.get("nameId"),
                        f"Catégorie {category_id}",
                    )
                    for category_id, row in categories.items()
                }
                retained = set(int(value) for value in RETAINED_TOP_CATEGORY_IDS)
                for achievement_id, row in achievements.items():
                    source_category_id = self._safe_int(row.get("categoryId"), 0)
                    top_category_id = self._top_category_id(source_category_id, categories)
                    if top_category_id not in retained:
                        continue
                    name = text_for(
                        entries,
                        row.get("nameId"),
                        f"Succès {achievement_id}",
                    )
                    top_name = category_names.get(top_category_id, f"Catégorie {top_category_id}")
                    sub_name = category_names.get(source_category_id, top_name)
                    level = self._safe_int(row.get("level"), 0)
                    points = self._safe_int(row.get("points"), 0)
                    order = self._safe_int(row.get("order"), 0)
                    rows.append(
                        (
                            int(achievement_id),
                            str(name),
                            str(top_name),
                            str(sub_name),
                            level,
                            points,
                            order,
                        )
                    )
                rows.sort(
                    key=lambda item: (
                        RETAINED_TOP_CATEGORY_IDS.index(
                            next(
                                (
                                    category_id
                                    for category_id in RETAINED_TOP_CATEGORY_IDS
                                    if normalize_text(category_names.get(category_id, "")) == normalize_text(item[2])
                                ),
                                RETAINED_TOP_CATEGORY_IDS[-1],
                            )
                        ),
                        normalize_text(item[3]),
                        item[6],
                        normalize_text(item[1]),
                        item[0],
                    )
                )
        except Exception:
            rows = []
        try:
            self.indexReady.emit(rows)
        except RuntimeError:
            pass

    def _apply_rows(self, rows: object) -> None:
        self._rows = list(rows) if isinstance(rows, list) else []
        self._name_by_id = {int(row[0]): str(row[1]) for row in self._rows}
        self.status.setText("" if self._rows else "Aucun succès disponible.")
        self.status.setVisible(not bool(self._rows))
        self._render()

    def _render(self) -> None:
        query = normalize_text(self.search.text())
        tokens = [token for token in query.split("_") if token]
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            top_items: dict[str, QTreeWidgetItem] = {}
            sub_items: dict[tuple[str, str], QTreeWidgetItem] = {}
            for achievement_id, name, top_name, sub_name, level, points, _order in self._rows:
                haystack = normalize_text(f"{name} {top_name} {sub_name} {achievement_id}")
                if tokens and not all(token in haystack for token in tokens):
                    continue
                top = top_items.get(top_name)
                if top is None:
                    top = QTreeWidgetItem([top_name])
                    top.setData(0, _ACHIEVEMENT_ID_ROLE, None)
                    self.tree.addTopLevelItem(top)
                    top_items[top_name] = top
                key = (top_name, sub_name)
                parent = sub_items.get(key)
                if parent is None:
                    parent = QTreeWidgetItem([sub_name])
                    parent.setData(0, _ACHIEVEMENT_ID_ROLE, None)
                    top.addChild(parent)
                    sub_items[key] = parent
                meta: list[str] = []
                if level > 0:
                    meta.append(f"Niv. {level}")
                if points > 0:
                    meta.append(f"{points} pts")
                label = name if not meta else f"{name}  ·  {' · '.join(meta)}"
                child = QTreeWidgetItem([label])
                child.setData(0, _ACHIEVEMENT_ID_ROLE, int(achievement_id))
                child.setToolTip(0, name)
                parent.addChild(child)
            for top in top_items.values():
                top.setExpanded(True)
        finally:
            self.tree.blockSignals(False)

    def _on_item_clicked(self, item: QTreeWidgetItem) -> None:
        achievement_id = item.data(0, _ACHIEVEMENT_ID_ROLE)
        if achievement_id is not None:
            self.achievementRequested.emit(int(achievement_id))

    def set_loading(self, achievement_id: int) -> None:
        name = self._name_by_id.get(int(achievement_id), f"Succès {int(achievement_id)}")
        self.status.setText(f"{name}…")
        self.status.setVisible(True)


class EncyclopediaWarmupView(QWidget):
    """Neutral responsive shell while a requested heavy provider loads."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EncyclopediaWarmupView")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        heading = QLabel(str(title or "Encyclopédie"))
        heading.setObjectName("GuideSectionTitle")
        heading.setAlignment(Qt.AlignCenter)
        root.addStretch(1)
        root.addWidget(heading)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        progress.setMaximumWidth(360)
        root.addWidget(progress, 0, Qt.AlignHCenter)
        root.addStretch(1)


__all__ = ["AchievementIndexView", "EncyclopediaWarmupView", "GuideIndexView"]
