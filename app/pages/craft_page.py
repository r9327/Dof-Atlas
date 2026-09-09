from __future__ import annotations

import difflib
from datetime import datetime
from typing import Any

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import local_data_cache
from app.constants import (
    CRAFT_SELECTION_FILE,
    HARVEST_ASSET_REPORT,
    HARVEST_JOBS,
    JOB_ORDER,
    JOB_RESOURCE_GROUPS,
    LEVELING_FILE,
)
from app.storage import (
    IconCache,
    canonical_job_name,
    display_path,
    existing_route_path,
    item_id,
    local_image_path,
    normalize_key,
    read_json,
    route_path_for,
    short_label,
    write_json,
)
from app.ui.components import AtlasButton


def quantity_spinbox(value: int, maximum: int = 999) -> QSpinBox:
    spinbox = QSpinBox()
    spinbox.setObjectName("QuantitySpinBox")
    spinbox.setRange(1, maximum)
    spinbox.setValue(max(1, min(maximum, int(value or 1))))
    spinbox.setMinimumWidth(86)
    spinbox.setMaximumWidth(86)
    spinbox.setAlignment(Qt.AlignCenter)
    spinbox.setToolTip("Quantité")
    return spinbox


class CraftResourceDialog(QDialog):
    def __init__(self, resources: dict[str, dict[str, Any]], missing: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.resources = resources
        self.icon_cache = IconCache(26)
        self.resource_checks: list[QCheckBox] = []
        self.setObjectName("CraftResourceDialog")
        self.setWindowTitle("Ressources craft")
        self.resize(500, 540)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Ressources craft")
        title.setObjectName("DialogTitle")
        header.addWidget(title, 1)
        count = QLabel(f"{len(resources)} ressource(s)")
        count.setObjectName("DialogSubtitle")
        count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(count)
        root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(6)
        select_all = AtlasButton("Tout sélectionner")
        select_all.setObjectName("SecondaryButton")
        select_all.clicked.connect(lambda: self.set_all_checked(True))
        unselect_all = AtlasButton("Tout désélectionner")
        unselect_all.setObjectName("SecondaryButton")
        unselect_all.clicked.connect(lambda: self.set_all_checked(False))
        toolbar.addWidget(select_all)
        toolbar.addWidget(unselect_all)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        list_layout = QVBoxLayout(content)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(5)
        if not resources:
            empty = QLabel("Aucune ressource à afficher pour cette sélection.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(160)
            list_layout.addWidget(empty)
        for name, info in sorted(resources.items(), key=lambda pair: pair[0].casefold()):
            row = QFrame()
            row.setObjectName("ListRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 5, 8, 5)
            layout.setSpacing(8)
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            self.resource_checks.append(checkbox)
            quantity = quantity_spinbox(int(info.get("quantity") or 1), maximum=999999)
            quantity.valueChanged.connect(lambda value, resource_name=name: self.set_resource_quantity(resource_name, value))
            multiplier = QLabel("x")
            multiplier.setObjectName("MutedLabel")
            icon = QLabel()
            icon.setFixedSize(28, 28)
            icon.setAlignment(Qt.AlignCenter)
            item_info = info.get("item") if isinstance(info.get("item"), dict) else {"name": name, "image_path": info.get("image_path", "")}
            resource_icon = self.icon_cache.icon_for_item(item_info).pixmap(24, 24)
            if not resource_icon.isNull():
                icon.setPixmap(resource_icon)
            label = QPushButton(name)
            label.setObjectName("ResourceNameButton")
            label.setFlat(True)
            label.setCursor(Qt.PointingHandCursor)
            label.clicked.connect(lambda _checked=False, text=name: QApplication.clipboard().setText(text))
            layout.addWidget(checkbox)
            layout.addWidget(quantity)
            layout.addWidget(multiplier)
            layout.addWidget(icon)
            layout.addWidget(label, 1)
            list_layout.addWidget(row)
        list_layout.addStretch(1)
        area.setWidget(content)
        root.addWidget(area, 1)
        if missing:
            label = QLabel("Sans recette : " + ", ".join(missing[:8]))
            label.setObjectName("WarningLabel")
            label.setWordWrap(True)
            root.addWidget(label)
        footer = QHBoxLayout()
        footer.addStretch(1)
        close = AtlasButton("Fermer")
        close.setObjectName("PrimaryActionButton")
        close.setFixedWidth(120)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)

    def set_resource_quantity(self, name: str, value: int) -> None:
        if name in self.resources:
            self.resources[name]["quantity"] = max(1, int(value or 1))

    def set_all_checked(self, checked: bool) -> None:
        for checkbox in self.resource_checks:
            checkbox.setChecked(checked)


class ItemSetDialog(QDialog):
    def __init__(self, item_set: dict[str, Any] | None, add_callback, parent: QWidget | None = None):
        super().__init__(parent)
        self.item_set = item_set or {}
        self.add_callback = add_callback
        self.icon_cache = IconCache(28)
        self.setWindowTitle("Panoplie")
        self.resize(390, 460)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        root = QVBoxLayout(self)
        if not item_set:
            empty = QLabel("Aucune panoplie connue pour cet équipement.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            root.addWidget(empty, 1)
            close = AtlasButton("Fermer")
            close.clicked.connect(self.accept)
            root.addWidget(close)
            return

        name = item_set.get("name_fr") or item_set.get("name_en") or f"Panoplie {item_set.get('ankama_id', '')}"
        title = QLabel(str(name))
        title.setObjectName("PageTitle")
        root.addWidget(title)
        root.addWidget(QLabel(f"{len(item_set.get('items', []))} objet(s) connus"))

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        rows = QVBoxLayout(content)
        for item in item_set.get("items", [])[:24]:
            row = QFrame()
            row.setObjectName("ListRow")
            layout = QHBoxLayout(row)
            icon = QLabel()
            icon.setPixmap(self.icon_cache.icon_for_item(item).pixmap(28, 28))
            layout.addWidget(icon)
            layout.addWidget(QLabel(f"{item.get('name', 'Objet')}  Lvl {item.get('level', '?')}"), 1)
            add = AtlasButton("+")
            add.setMaximumWidth(42)
            add.clicked.connect(lambda _checked=False, target=item: self.add_callback(target, 1))
            layout.addWidget(add)
            rows.addWidget(row)
        rows.addStretch(1)
        area.setWidget(content)
        root.addWidget(area, 1)

        add_set = AtlasButton("Ajouter la panoplie")
        add_set.clicked.connect(self.add_whole_set)
        root.addWidget(add_set)

    def add_whole_set(self) -> None:
        for item in self.item_set.get("items", []):
            self.add_callback(item, 1)
        self.accept()


class LevelingDialog(QDialog):
    def __init__(self, job_name: str, guide: dict[str, Any], find_item_callback, add_craft_callback, parent: QWidget | None = None):
        super().__init__(parent)
        self.find_item_callback = find_item_callback
        self.add_craft_callback = add_craft_callback
        self.icon_cache = IconCache(28)
        self.setObjectName("LevelingDialog")
        self.setWindowTitle(f"{job_name} 0-200")
        self.resize(660, 560)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)
        title = QLabel(f"{job_name} 0-200")
        title.setObjectName("DialogTitle")
        root.addWidget(title)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        rows = QVBoxLayout(content)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(5)
        entries = guide.get("entries") or []
        if not entries:
            empty = QLabel("Aucun guide leveling local pour ce métier.")
            empty.setAlignment(Qt.AlignCenter)
            rows.addWidget(empty)
        for entry in entries:
            craft = entry.get("craft") or {}
            item = self.find_item_callback(craft.get("name", ""))
            row = QFrame()
            row.setObjectName("ListRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 5, 8, 5)
            layout.setSpacing(8)
            icon = QLabel()
            icon.setFixedSize(30, 30)
            icon.setAlignment(Qt.AlignCenter)
            if item:
                icon.setPixmap(self.icon_cache.icon_for_item(item).pixmap(28, 28))
            layout.addWidget(icon)
            level = QLabel(str(entry.get("level_range", "")))
            level.setObjectName("LevelBadge")
            level.setFixedWidth(88)
            level.setAlignment(Qt.AlignCenter)
            layout.addWidget(level)
            recipe = QLabel(f"{craft.get('quantity', 1)} x {craft.get('name', '')}")
            recipe.setObjectName("CompactLabel")
            recipe.setWordWrap(False)
            layout.addWidget(recipe, 1)
            add = AtlasButton("+")
            add.setObjectName("PrimaryActionButton")
            add.setFixedSize(38, 28)
            add.clicked.connect(lambda _checked=False, target=craft: self.add_craft_callback(target))
            layout.addWidget(add)
            rows.addWidget(row)
        rows.addStretch(1)
        area.setWidget(content)
        root.addWidget(area, 1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        close = AtlasButton("Fermer")
        close.setObjectName("SecondaryButton")
        close.setFixedWidth(110)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)


class RouteImageLabel(QLabel):
    def __init__(self, zoom_callback, parent: QWidget | None = None):
        super().__init__(parent)
        self.zoom_callback = zoom_callback
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(230)

    def wheelEvent(self, event) -> None:
        delta = 1 if event.angleDelta().y() > 0 else -1
        self.zoom_callback(delta)
        event.accept()


class RouteDialog(QDialog):
    def __init__(self, job_name: str, item: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.job_name = job_name
        self.item = item
        self.step = 1
        self.zoom = 1.0
        self.setWindowTitle(f"{job_name} - {item.get('name', 'Ressource')}")
        self.resize(560, 420)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        root = QVBoxLayout(self)
        title = QLabel(f"{job_name} - {item.get('name', 'Ressource')}")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        controls = QHBoxLayout()
        self.step_label = QLabel("Etape 1")
        controls.addWidget(self.step_label)
        controls.addStretch(1)
        previous = AtlasButton("<")
        next_button = AtlasButton(">")
        previous.clicked.connect(lambda: self.change_step(-1))
        next_button.clicked.connect(lambda: self.change_step(1))
        controls.addWidget(previous)
        controls.addWidget(next_button)
        root.addLayout(controls)
        self.image = RouteImageLabel(self.change_zoom)
        self.image.setObjectName("EmbeddedHost")
        root.addWidget(self.image, 1)
        self.refresh_image()

    def change_step(self, delta: int) -> None:
        target = max(1, self.step + delta)
        if delta > 0 and existing_route_path(self.job_name, self.item.get("name", ""), target) is None:
            return
        self.step = target
        self.refresh_image()

    def change_zoom(self, delta: int) -> None:
        self.zoom = max(0.45, min(3.0, self.zoom + (0.15 * delta)))
        self.refresh_image()

    def refresh_image(self) -> None:
        self.step_label.setText(f"Etape {self.step}")
        path = existing_route_path(self.job_name, self.item.get("name", ""), self.step)
        if not path:
            expected = route_path_for(self.job_name, self.item.get("name", ""), self.step)
            self.image.setPixmap(QPixmap())
            self.image.setText(
                "Capture manquante.\n\n"
                "Aucune capture locale n'est disponible pour cette route.\n"
                f"Chemin local attendu :\n{expected}"
            )
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.image.setPixmap(QPixmap())
            self.image.setText("Capture illisible.")
            return
        box = self.image.size()
        scaled = pixmap.scaled(
            max(180, int(box.width() * self.zoom)),
            max(160, int(box.height() * self.zoom)),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.image.setText("")
        self.image.setPixmap(scaled)


class CraftPage(QWidget):
    def __init__(self, status_callback, parent: QWidget | None = None, preload: dict[str, Any] | None = None):
        super().__init__(parent)
        self.status_callback = status_callback
        self.preload = preload if isinstance(preload, dict) else {}
        self.icon_cache = IconCache(32)
        self.items: list[dict[str, Any]] = []
        self.items_by_name: dict[str, dict[str, Any]] = {}
        self.item_lookup_cache: dict[str, dict[str, Any] | None] = {}
        self.selection: dict[int, dict[str, Any]] = {}
        self.guides: dict[str, Any] = {}
        self.jobs: list[dict[str, Any]] = []
        self.selected_job = ""
        self.category = "equipment"
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.refresh_results)
        self.jobs_resize_timer = QTimer(self)
        self.jobs_resize_timer.setSingleShot(True)
        self.jobs_resize_timer.timeout.connect(self.refresh_jobs)
        self.resource_dialog: CraftResourceDialog | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        title = QLabel("Craft")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.global_scroll = QScrollArea()
        self.global_scroll.setWidgetResizable(True)
        self.global_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.global_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_content = QWidget()
        content_root = QVBoxLayout(scroll_content)
        content_root.setContentsMargins(4, 4, 4, 4)
        content_root.setSpacing(6)
        self.global_scroll.setWidget(scroll_content)
        root.addWidget(self.global_scroll, 1)

        main_split = QVBoxLayout()
        main_split.setSpacing(6)
        content_root.addLayout(main_split, 1)

        self.craft_body_narrow = False
        self.craft_body = QGridLayout()
        self.craft_body.setSpacing(6)
        main_split.addLayout(self.craft_body, 1)

        self.craft_left_panel = QFrame()
        self.craft_left_panel.setObjectName("CraftPanel")
        self.craft_left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        left = QVBoxLayout(self.craft_left_panel)
        left.setContentsMargins(8, 8, 8, 8)
        left.setSpacing(6)
        category_row = QHBoxLayout()
        category_row.setSpacing(4)
        left.addLayout(category_row)
        self.category_buttons: dict[str, QPushButton] = {}
        for key, label in (("equipment", "Équipement"), ("trophy_prysma", "Trophée / Prysmaradite"), ("resource", "Ressource craftable")):
            button = AtlasButton(label)
            button.setMaximumHeight(28)
            button.clicked.connect(lambda _checked=False, k=key: self.set_category(k))
            self.category_buttons[key] = button
            category_row.addWidget(button)
        self.search = QLineEdit()
        self.search.setObjectName("CraftSearch")
        self.search.setPlaceholderText("Rechercher un item...")
        self.search.setMaximumWidth(360)
        self.search.textChanged.connect(lambda _text: self.search_timer.start(120))
        left.addWidget(self.search)
        self.results = QListWidget()
        self.results.setIconSize(QSize(30, 30))
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.setTextElideMode(Qt.ElideRight)
        self.results.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results.itemDoubleClicked.connect(self.add_result_item)
        self.results.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results.customContextMenuRequested.connect(self.open_result_menu)
        left.addWidget(self.results, 1)

        self.craft_right_panel = QFrame()
        self.craft_right_panel.setObjectName("CraftPanel")
        self.craft_right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right = QVBoxLayout(self.craft_right_panel)
        right.setContentsMargins(8, 8, 8, 8)
        right.setSpacing(6)
        selection_header = QHBoxLayout()
        selection_title = QLabel("Sélection")
        selection_title.setObjectName("PanelTitle")
        selection_header.addWidget(selection_title)
        selection_header.addStretch(1)
        clear_button = AtlasButton("Vider")
        clear_button.setObjectName("SecondaryButton")
        clear_button.setMaximumWidth(58)
        selection_header.addWidget(clear_button)
        right.addLayout(selection_header)
        self.selection_list = QListWidget()
        self.selection_list.setIconSize(QSize(24, 24))
        self.selection_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.selection_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.selection_list.setTextElideMode(Qt.ElideRight)
        right.addWidget(self.selection_list, 1)
        craft_button = AtlasButton("Lancer le Craft")
        craft_button.setObjectName("PrimaryActionButton")
        craft_button.setFixedHeight(34)
        craft_button.setMinimumWidth(180)
        right.addWidget(craft_button, alignment=Qt.AlignHCenter)
        clear_button.clicked.connect(self.clear_selection)
        craft_button.clicked.connect(self.show_resources)
        self.apply_craft_body_layout(force=True)

        self.jobs_panel = QFrame()
        self.jobs_panel.setObjectName("CraftPanel")
        jobs_root = QVBoxLayout(self.jobs_panel)
        jobs_root.setContentsMargins(8, 8, 8, 8)
        jobs_root.setSpacing(6)
        self.job_buttons_layout = QGridLayout()
        self.job_buttons_layout.setSpacing(4)
        jobs_root.addLayout(self.job_buttons_layout)
        self.job_actions_layout = QHBoxLayout()
        self.job_actions_layout.setSpacing(4)
        jobs_root.addLayout(self.job_actions_layout)
        self.job_content = QWidget()
        self.job_grid = QGridLayout(self.job_content)
        self.job_grid.setContentsMargins(0, 0, 0, 0)
        self.job_grid.setSpacing(4)
        jobs_root.addWidget(self.job_content, 1)
        main_split.addWidget(self.jobs_panel, 1)

        self.load_items()
        self.load_leveling_guides()
        self.load_jobs()
        self.load_selection()
        self.update_category_buttons()
        self.refresh_results()
        self.refresh_selection()
        self.refresh_jobs()
        QTimer.singleShot(0, self.apply_craft_body_layout)

    def restyle_button(self, button: QPushButton) -> None:
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self.clear_layout(child_layout)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.apply_craft_body_layout()
        if hasattr(self, "jobs_resize_timer"):
            self.jobs_resize_timer.start(120)

    def craft_view_width(self) -> int:
        if hasattr(self, "global_scroll") and self.global_scroll.viewport() is not None:
            return max(0, self.global_scroll.viewport().width())
        return max(0, self.width())

    def apply_craft_body_layout(self, force: bool = False) -> None:
        if not hasattr(self, "craft_body"):
            return
        narrow = self.craft_view_width() < 720
        if not force and narrow == self.craft_body_narrow:
            return
        self.craft_body_narrow = narrow
        self.craft_body.removeWidget(self.craft_left_panel)
        self.craft_body.removeWidget(self.craft_right_panel)
        if narrow:
            self.craft_body.addWidget(self.craft_left_panel, 0, 0)
            self.craft_body.addWidget(self.craft_right_panel, 1, 0)
            self.craft_body.setColumnStretch(0, 1)
            self.craft_body.setColumnStretch(1, 0)
            self.craft_body.setRowStretch(0, 1)
            self.craft_body.setRowStretch(1, 1)
            self.results.setMinimumHeight(170)
            self.selection_list.setMinimumHeight(150)
        else:
            self.craft_body.addWidget(self.craft_left_panel, 0, 0)
            self.craft_body.addWidget(self.craft_right_panel, 0, 1)
            self.craft_body.setColumnStretch(0, 3)
            self.craft_body.setColumnStretch(1, 2)
            self.craft_body.setRowStretch(0, 1)
            self.craft_body.setRowStretch(1, 0)
            self.results.setMinimumHeight(0)
            self.selection_list.setMinimumHeight(0)

    def job_button_column_count(self) -> int:
        width = max(220, self.jobs_panel.width() if hasattr(self, "jobs_panel") else self.craft_view_width())
        return max(2, min(8, width // 104))

    def resource_column_count(self) -> int:
        width = max(170, self.job_content.width() or self.craft_view_width())
        return max(3, min(12, width // 62))

    def set_category(self, category: str) -> None:
        self.category = category
        self.update_category_buttons()
        self.refresh_results()

    def update_category_buttons(self) -> None:
        for key, button in self.category_buttons.items():
            button.setObjectName("ActiveButton" if key == self.category else "SecondaryButton")
            self.restyle_button(button)

    def category_for_item(self, item: dict[str, Any]) -> str:
        text = normalize_key(" ".join(str(item.get(key, "")) for key in ("name", "type", "family", "category")))
        if any(token in text for token in ("trophee", "prysma", "prysmaradite")):
            return "trophy_prysma"
        equipment = ("arme", "coiffe", "cape", "ceinture", "anneau", "collier", "amulette", "botte", "bouclier", "dofus")
        if any(token in text for token in equipment):
            return "equipment"
        return "resource"

    def load_items(self) -> None:
        preloaded_items = self.preload.get("items")
        if isinstance(preloaded_items, list):
            self.items = [dict(item) for item in preloaded_items if isinstance(item, dict)]
        elif local_data_cache is None:
            self.items = []
            self.status_callback("Module local_data_cache indisponible.")
            return
        else:
            try:
                self.items = local_data_cache.list_craft_items()
            except Exception as exc:
                self.items = []
                self.status_callback(f"Chargement craft impossible: {exc}")
        for item in self.items:
            item["_search_name"] = normalize_key(item.get("name"))
            item["_craft_category"] = self.category_for_item(item)
        self.items_by_name = {
            normalize_key(item.get("name")): item
            for item in self.items
            if item.get("name")
        }
        lookup_items = self.preload.get("lookup_items", [])
        if not isinstance(lookup_items, list):
            lookup_items = []
        for item in lookup_items:
            if not isinstance(item, dict):
                continue
            key = normalize_key(item.get("name"))
            if key:
                self.items_by_name.setdefault(key, item)
                self.item_lookup_cache[key] = item

    def refresh_results(self) -> None:
        query = normalize_key(self.search.text())
        self.results.clear()
        if len(query) < 2:
            return
        count = 0
        for item in self.items:
            if item.get("_craft_category") != self.category:
                continue
            if query and query not in item.get("_search_name", ""):
                continue
            entry = QListWidgetItem(self.icon_cache.icon_for_item(item), f"{item.get('name', 'Objet')} | Lvl {item.get('level', '?')} | {item.get('type', '')}")
            entry.setData(Qt.UserRole, item)
            self.results.addItem(entry)
            count += 1
            if count >= 80:
                break

    def open_result_menu(self, position: QPoint) -> None:
        entry = self.results.itemAt(position)
        if not entry:
            return
        self.results.setCurrentItem(entry)
        item = entry.data(Qt.UserRole)
        menu = QMenu(self)
        add_action = menu.addAction("Ajouter")
        set_action = None
        if item and item.get("_craft_category") == "equipment":
            set_action = menu.addAction("Voir la panoplie")
        action = menu.exec(self.results.viewport().mapToGlobal(position))
        if action == add_action:
            self.add_item(item, 1)
        elif set_action is not None and action == set_action:
            self.open_item_set(item)

    def open_item_set(self, item: dict[str, Any]) -> None:
        ident = item_id(item)
        if ident is None or not hasattr(local_data_cache, "get_item_set_for_item"):
            self.status_callback("Panoplie indisponible pour cet objet.")
            return
        try:
            item_set = local_data_cache.get_item_set_for_item(ident)
        except Exception as exc:
            self.status_callback(f"Lecture panoplie impossible: {exc}")
            item_set = None
        dialog = ItemSetDialog(item_set, self.add_item, self)
        dialog.exec()

    def add_result_item(self, entry: QListWidgetItem | None) -> None:
        if not entry:
            return
        item = entry.data(Qt.UserRole)
        self.add_item(item, 1)

    def add_item(self, item: dict[str, Any], quantity: int = 1) -> None:
        ident = item_id(item)
        if ident is None:
            self.status_callback(f"Objet ignore: ID local invalide ({item.get('name', 'Objet')}).")
            return
        if ident not in self.selection:
            self.selection[ident] = {"item": item, "quantity": 0}
        self.selection[ident]["quantity"] = max(1, int(self.selection[ident]["quantity"]) + int(quantity or 1))
        self.save_selection()
        self.refresh_selection()
        self.status_callback(f"Ajoute: {item.get('name', 'Objet')}")

    def remove_selected(self) -> None:
        entry = self.selection_list.currentItem()
        if not entry:
            return
        ident = entry.data(Qt.UserRole)
        self.remove_selection_item(ident)

    def remove_selection_item(self, ident: int) -> None:
        self.selection.pop(ident, None)
        self.save_selection()
        self.refresh_selection()

    def change_selection_quantity(self, ident: int, delta: int) -> None:
        row = self.selection.get(ident)
        if not row:
            return
        row["quantity"] = max(1, min(999, int(row.get("quantity") or 1) + delta))
        self.save_selection()
        self.refresh_selection()

    def set_selection_quantity(self, ident: int, value: int) -> None:
        row = self.selection.get(ident)
        if not row:
            return
        row["quantity"] = max(1, min(999, int(value or 1)))
        self.save_selection()

    def clear_selection(self) -> None:
        self.selection.clear()
        self.save_selection()
        self.refresh_selection()
        self.status_callback("Sélection vidée.")

    def refresh_selection(self) -> None:
        self.selection_list.clear()
        for ident, row in sorted(self.selection.items(), key=lambda pair: str(pair[1]["item"].get("name", "")).casefold()):
            item = row["item"]
            entry = QListWidgetItem()
            entry.setData(Qt.UserRole, ident)
            entry.setSizeHint(QSize(240, 46))
            self.selection_list.addItem(entry)
            widget = QFrame()
            widget.setObjectName("SelectionRow")
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(4, 2, 4, 2)
            icon = QLabel()
            icon.setPixmap(self.icon_cache.icon_for_item(item).pixmap(24, 24))
            layout.addWidget(icon)
            label = QLabel(str(item.get("name", "Objet")))
            label.setWordWrap(False)
            layout.addWidget(label, 1)
            qty = quantity_spinbox(int(row["quantity"]))
            delete = AtlasButton("x")
            delete.setMaximumWidth(30)
            qty.valueChanged.connect(lambda value, target=ident: self.set_selection_quantity(target, value))
            delete.clicked.connect(lambda _checked=False, target=ident: self.remove_selection_item(target))
            layout.addWidget(qty)
            layout.addWidget(delete)
            self.selection_list.setItemWidget(entry, widget)

    def save_selection(self) -> None:
        payload = {
            "items": [
                {
                    "item_id": ident,
                    "ankama_id": ident,
                    "name": row["item"].get("name", ""),
                    "quantity": row["quantity"],
                }
                for ident, row in self.selection.items()
            ]
        }
        write_json(CRAFT_SELECTION_FILE, payload)

    def load_selection(self) -> None:
        preloaded_selection = self.preload.get("selection")
        if isinstance(preloaded_selection, dict):
            for ident, row in preloaded_selection.items():
                try:
                    item_id_value = int(ident)
                except (TypeError, ValueError):
                    continue
                item = row.get("item") if isinstance(row, dict) else None
                if isinstance(item, dict):
                    self.selection[item_id_value] = {
                        "item": item,
                        "quantity": max(1, int(row.get("quantity") or 1)),
                    }
            return
        payload = read_json(CRAFT_SELECTION_FILE, {"items": []})
        rows = payload.get("items") if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return
        for row in rows:
            try:
                ident = int(row.get("ankama_id") or row.get("item_id"))
            except (TypeError, ValueError):
                continue
            try:
                item = local_data_cache.get_item(ident)
            except Exception:
                item = None
            if not item:
                continue
            self.selection[ident] = {"item": item, "quantity": max(1, int(row.get("quantity") or 1))}

    def load_leveling_guides(self) -> None:
        payload = self.preload.get("guides")
        if not isinstance(payload, dict):
            payload = read_json(LEVELING_FILE, {"source": "gamosaurus", "offline_runtime": True, "guides": {}})
        self.guides = payload if isinstance(payload, dict) else {"guides": {}}

    def load_jobs(self) -> None:
        jobs: list[dict[str, Any]] = []
        preloaded_jobs = self.preload.get("jobs")
        if isinstance(preloaded_jobs, list):
            jobs = [dict(job) for job in preloaded_jobs if isinstance(job, dict)]
        elif hasattr(local_data_cache, "list_jobs"):
            try:
                jobs = local_data_cache.list_jobs()
            except Exception:
                jobs = []
        seen = {normalize_key(job.get("name")) for job in jobs}
        for name in list(JOB_RESOURCE_GROUPS.keys()) + list((self.guides.get("guides") or {}).keys()):
            key = normalize_key(name)
            if key and key not in seen:
                jobs.append({"name": name, "image_path": "", "type": "job"})
                seen.add(key)
        clean = []
        for job in jobs:
            key = normalize_key(job.get("name"))
            if not key or "mage" in key or "bestiologue" in key:
                continue
            clean.append(job)
        self.jobs = sorted(clean, key=lambda job: (JOB_ORDER.get(normalize_key(job.get("name")), 100), normalize_key(job.get("name"))))

    def find_item_by_name(self, name: str) -> dict[str, Any] | None:
        key = normalize_key(name)
        if not key:
            return None
        if key in self.item_lookup_cache:
            return self.item_lookup_cache[key]
        if key in self.items_by_name:
            item = self.items_by_name[key]
            self.item_lookup_cache[key] = item
            return item
        if hasattr(local_data_cache, "search_items"):
            try:
                results = local_data_cache.search_items(name, limit=8)
                if results:
                    self.item_lookup_cache[key] = results[0]
                    return results[0]
            except Exception:
                pass

        # The old fallback returned the first substring match, making results
        # depend on insertion order. Accept a partial only when it is unique;
        # otherwise rely on the similarity threshold below.
        partials: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        best = None
        best_score = 0.0
        for item_key, item in self.items_by_name.items():
            if key in item_key or item_key in key:
                marker = id(item)
                if marker not in seen_ids:
                    seen_ids.add(marker)
                    partials.append(item)
            score = difflib.SequenceMatcher(None, key, item_key).ratio()
            if score > best_score:
                best = item
                best_score = score
        if len(partials) == 1:
            result = partials[0]
        else:
            result = best if best is not None and best_score >= 0.82 else None
        self.item_lookup_cache[key] = result
        return result

    def find_job_resource(self, job_name: str, resource_name: str) -> dict[str, Any]:
        candidates = [resource_name]
        if normalize_key(job_name) == "bucheron":
            candidates = [f"Bois de {resource_name}", f"Bois d'{resource_name}", f"Bois d {resource_name}", resource_name]
        for candidate in candidates:
            item = self.find_item_by_name(candidate)
            if item:
                clone = dict(item)
                clone["name"] = resource_name
                return clone
        return {"name": resource_name, "level": "?", "_missing_local_item": True}

    def write_harvest_asset_report(self) -> None:
        rows = []
        missing_images = 0
        missing_routes = 0
        for job_name, resources in JOB_RESOURCE_GROUPS.items():
            for resource_name, _tag in resources:
                item = self.find_job_resource(job_name, resource_name)
                image_path = local_image_path(item)
                route_path = existing_route_path(canonical_job_name(job_name), resource_name, 1)
                row = {
                    "job": job_name,
                    "resource": resource_name,
                    "matched_item": item.get("name", ""),
                    "item_id": item_id(item),
                    "image_path": display_path(image_path),
                    "image_exists": bool(image_path),
                    "route_path": display_path(route_path),
                    "route_exists": bool(route_path),
                    "missing_local_item": bool(item.get("_missing_local_item")),
                }
                if not row["image_exists"]:
                    missing_images += 1
                if not row["route_exists"]:
                    missing_routes += 1
                rows.append(row)
        write_json(
            HARVEST_ASSET_REPORT,
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "resources": len(rows),
                "missing_images": missing_images,
                "missing_routes": missing_routes,
                "rows": rows,
            },
        )

    def guide_for_job(self, job_name: str) -> dict[str, Any] | None:
        key = normalize_key(job_name)
        for name, guide in (self.guides.get("guides") or {}).items():
            if normalize_key(name) == key:
                return guide
        return None

    def is_harvest_job(self, job_name: str) -> bool:
        return normalize_key(job_name) in HARVEST_JOBS

    def job_icon_source(self, job: dict[str, Any]) -> dict[str, Any]:
        if job.get("image_path"):
            return job
        key = normalize_key(job.get("name"))
        fallbacks = {
            "alchimiste": ("Alchimiste", "Ortie"),
            "bucheron": ("Bucheron", "Frene"),
            "mineur": ("Mineur", "Fer"),
            "paysan": ("Paysan", "Ble"),
            "pecheur": ("Pecheur", "Goujon"),
            "chasseur": ("Chasseur", "Viande Fraiche"),
        }
        fallback = fallbacks.get(key)
        if fallback:
            return self.find_job_resource(fallback[0], fallback[1])
        return job

    def refresh_jobs(self) -> None:
        self.clear_layout(self.job_buttons_layout)
        self.clear_layout(self.job_actions_layout)
        self.clear_layout(self.job_grid)

        buttons = list(self.jobs)
        button_columns = self.job_button_column_count()
        for index, job in enumerate(buttons):
            name = str(job.get("name") or "Métier")
            key = normalize_key(name)
            button = AtlasButton(name)
            button.setMaximumHeight(28)
            if key == normalize_key(self.selected_job):
                button.setObjectName("ActiveButton")
            else:
                button.setObjectName("SecondaryButton")
            icon_source = self.job_icon_source(job)
            icon = self.icon_cache.icon_for_item(icon_source)
            if not icon.isNull() and key != "recolte":
                button.setIcon(icon)
                button.setIconSize(QSize(22, 22))
            button.clicked.connect(lambda _checked=False, target=name: self.set_job(target))
            self.job_buttons_layout.addWidget(button, index // button_columns, index % button_columns)
        for column in range(button_columns):
            self.job_buttons_layout.setColumnStretch(column, 1)

        selected_key = normalize_key(self.selected_job)
        if not selected_key:
            self.job_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.job_grid.setRowStretch(0, 1)
            self.job_actions_layout.addStretch(1)
            return

        guide = self.guide_for_job(self.selected_job)
        if self.is_harvest_job(self.selected_job) and guide and guide.get("entries"):
            leveling = AtlasButton("Leveling 0-200")
            leveling.setObjectName("PrimaryActionButton")
            leveling.setFixedHeight(30)
            leveling.clicked.connect(lambda _checked=False, job=self.selected_job: self.open_leveling_dialog(job))
            self.job_actions_layout.addWidget(leveling)
        self.job_actions_layout.addStretch(1)

        groups = {name: values for name, values in JOB_RESOURCE_GROUPS.items() if normalize_key(name) == selected_key}
        if not groups:
            self.job_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.job_grid.setRowStretch(0, 1)
            return

        columns = self.resource_column_count()
        tile_index = 0
        show_sections = len(groups) > 1
        for job_name, resources in groups.items():
            if show_sections:
                section = QLabel(job_name)
                section.setObjectName("SectionTitle")
                self.job_grid.addWidget(section, tile_index // columns, 0, 1, columns)
                tile_index += columns
            for resource_name, _tag in resources:
                item = self.find_job_resource(job_name, resource_name)
                label = str(item.get("name", "Ressource"))
                button = QToolButton()
                button.setCursor(Qt.PointingHandCursor)
                button.setObjectName("ResourceTile")
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setText(short_label(label, 10))
                button.setToolTip(label)
                button.setIcon(self.icon_cache.icon_for_item(item))
                button.setIconSize(QSize(16, 16))
                button.setFixedSize(56, 42)
                button.clicked.connect(lambda _checked=False, job=job_name, target=item: self.show_route(job, target))
                self.job_grid.addWidget(button, tile_index // columns, tile_index % columns, alignment=Qt.AlignTop)
                tile_index += 1
        for column in range(columns):
            self.job_grid.setColumnStretch(column, 1)
        self.job_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.job_grid.setRowStretch((tile_index // columns) + 1, 1)

    def set_job(self, job_name: str) -> None:
        self.selected_job = job_name
        self.refresh_jobs()
        if not self.is_harvest_job(job_name):
            guide = self.guide_for_job(job_name)
            if guide and guide.get("entries"):
                QTimer.singleShot(20, lambda: self.open_leveling_dialog(job_name))

    def open_leveling_dialog(self, job_name: str) -> None:
        guide = self.guide_for_job(job_name)
        if not guide:
            self.status_callback(f"Aucun guide leveling local pour {job_name}.")
            return
        dialog = LevelingDialog(job_name, guide, self.find_item_by_name, self.add_leveling_craft, self)
        dialog.exec()

    def add_leveling_craft(self, craft: dict[str, Any]) -> None:
        item = self.find_item_by_name((craft or {}).get("name", ""))
        if not item or item_id(item) is None:
            self.status_callback(f"Objet introuvable en base locale: {(craft or {}).get('name', 'Objet leveling')}")
            return
        self.add_item(item, int((craft or {}).get("quantity") or 1))

    def show_route(self, job_name: str, item: dict[str, Any]) -> None:
        dialog = RouteDialog(canonical_job_name(job_name), item, self)
        dialog.exec()

    def show_resources(self) -> None:
        if not self.selection:
            self.status_callback("Sélection vide.")
            return
        resources: dict[str, dict[str, Any]] = {}
        missing = []
        for row in self.selection.values():
            item = row["item"]
            ident = item_id(item)
            if ident is None:
                missing.append(item.get("name", "Objet sans ID"))
                continue
            try:
                recipe = local_data_cache.get_recipe_for_item(ident)
            except Exception:
                recipe = {"found": False, "ingredients": []}
            if not recipe.get("found") or not recipe.get("ingredients"):
                missing.append(item.get("name", str(ident)))
                continue
            for ingredient in recipe.get("ingredients", []):
                name = ingredient.get("name", "Ressource")
                entry = resources.setdefault(name, {"quantity": 0, "item": dict(ingredient)})
                entry["quantity"] += int(ingredient.get("quantity", 1)) * int(row["quantity"])
                if not entry.get("item") and isinstance(ingredient, dict):
                    entry["item"] = dict(ingredient)
                if ingredient.get("image_path"):
                    entry["image_path"] = ingredient.get("image_path")
        if self.resource_dialog is not None:
            self.resource_dialog.close()
        dialog = CraftResourceDialog(resources, missing)
        dialog.setModal(False)
        dialog.finished.connect(lambda _result: setattr(self, "resource_dialog", None))
        self.resource_dialog = dialog
        dialog.show()
        dialog.raise_()
        self.status_callback(f"{len(resources)} ressource(s) agregee(s).")
