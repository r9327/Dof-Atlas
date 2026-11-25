from __future__ import annotations

import difflib
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import local_data_cache
from app.core.item_artwork import item_with_artwork
from app.core.file_stamp import mtime_ctime_size_stamp
from app.core.numbers import clamp_int32, optional_int
from app.core.json_store import InvalidPersistentJsonError
from app.core.craft_selection import (
    selection_item_row, resolve_selection, selection_editor_maximum,
    persist_selection_quantity, clear_persisted_selection, read_selection_payload,
)
from app.constants import (
    CRAFT_SELECTION_FILE,
    HARVEST_ASSET_REPORT,
    HARVEST_JOBS,
    JOB_ORDER,
    JOB_RESOURCE_GROUPS,
    LEVELING_FILE,
    ROOT_DIR,
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
from app.ui.components import (
    AtlasButton, AtlasDialog, AtlasPageTitle,
    configure_unity_number_spinbox, restore_unity_number_value,
    present_transient_dialog, exec_transient_dialog,
    clear_unity_widget_layout,
    configure_unity_scroll_area, configure_unity_tool_button,
)
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX, UNITY_SPACING_PX

CRAFT_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["craft"]
from app.ui.unity_skin import apply_unity_panel_shadow


LOGGER = logging.getLogger(__name__)

_RESULT_BATCH_SIZE = 8


def craft_image_item(item: dict[str, Any], *, root: Path = ROOT_DIR) -> dict[str, Any]:
    """Compatibility adapter; the Craft artwork service owns all lookup rules."""
    return item_with_artwork(item, root=root)


def quantity_spinbox(value: int, maximum: int = 999) -> QSpinBox:
    return configure_unity_number_spinbox(
        QSpinBox(), minimum=1, maximum=maximum,
        value=max(1, min(maximum, int(value or 1))),
        object_name="QuantitySpinBox", centered=True, tooltip="Quantité",
    )


class CraftResourceDialog(AtlasDialog):
    def __init__(self, resources: dict[str, dict[str, Any]], missing: list[str], parent: QWidget | None = None):
        super().__init__(parent, density="compact")
        self.resources = resources
        self.icon_cache = IconCache(26)
        self.resource_checks: list[QCheckBox] = []
        self.setAccessibleName("CraftResourceDialog")
        self.setWindowTitle("Ressources craft")
        self.resize(*CRAFT_GEOMETRY["resource_dialog_size"])
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        root = self.content_layout

        self.add_header("Ressources craft", f"{len(resources)} ressource(s)")

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(6)
        select_all = AtlasButton("Tout sélectionner", variant="secondary")
        select_all.clicked.connect(lambda: self.set_all_checked(True))
        unselect_all = AtlasButton("Tout désélectionner", variant="secondary")
        unselect_all.clicked.connect(lambda: self.set_all_checked(False))
        toolbar.addWidget(select_all)
        toolbar.addWidget(unselect_all)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        list_layout = self.add_scroll_rows()
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
            box = CRAFT_GEOMETRY["resource_icon_box"]
            icon.setFixedSize(box, box)
            icon.setAlignment(Qt.AlignCenter)
            item_info = info.get("item") if isinstance(info.get("item"), dict) else {"name": name, "image_path": info.get("image_path", "")}
            resource_icon = self.icon_cache.icon_for_item(item_info).pixmap(24, 24)
            if not resource_icon.isNull():
                icon.setPixmap(resource_icon)
            label = AtlasButton(name)
            label.setObjectName("ResourceNameButton")
            label.setFlat(True)
            label.clicked.connect(lambda _checked=False, text=name: QApplication.clipboard().setText(text))
            layout.addWidget(checkbox)
            layout.addWidget(quantity)
            layout.addWidget(multiplier)
            layout.addWidget(icon)
            layout.addWidget(label, 1)
            list_layout.addWidget(row)
        list_layout.addStretch(1)

        if missing:
            label = QLabel("Sans recette : " + ", ".join(missing[:8]))
            label.setObjectName("WarningLabel")
            label.setWordWrap(True)
            root.addWidget(label)
        close = AtlasButton("Fermer", variant="primary")
        close.clicked.connect(self.accept)
        self.add_action_row(close)

    def set_resource_quantity(self, name: str, value: int) -> None:
        if name in self.resources:
            self.resources[name]["quantity"] = max(1, int(value or 1))

    def set_all_checked(self, checked: bool) -> None:
        for checkbox in self.resource_checks:
            checkbox.setChecked(checked)

    def keyPressEvent(self, event) -> None:
        # Only Escape asks for confirmation. Programmatic close() during Craft
        # reload/cleanup must never spawn a modal question and block shutdown.
        if event.key() == Qt.Key_Escape:
            answer = QMessageBox.question(
                self,
                "Fermer les ressources ?",
                "Voulez-vous vraiment fermer la fenêtre des ressources craft ?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                self.reject()
            event.accept()
            return
        super().keyPressEvent(event)


class ItemSetDialog(AtlasDialog):
    def __init__(self, item_set: dict[str, Any] | None, add_callback, parent: QWidget | None = None):
        super().__init__(parent, density="compact")
        self.item_set = item_set or {}
        self.add_callback = add_callback
        self.icon_cache = IconCache(28)
        self.setWindowTitle("Panoplie")
        self.resize(*CRAFT_GEOMETRY["item_set_dialog_size"])
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        root = self.content_layout
        name = (
            self.item_set.get("name_fr") or self.item_set.get("name_en")
            or f"Panoplie {self.item_set.get('ankama_id', '')}".strip()
        )
        self.add_header(
            str(name),
            f"{len(self.item_set.get('items', []))} objet(s) connu(s)"
            if self.item_set else "",
        )
        if not item_set:
            empty = QLabel("Aucune panoplie connue pour cet équipement.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            root.addWidget(empty, 1)
            close = AtlasButton("Fermer")
            close.clicked.connect(self.accept)
            root.addWidget(close)
            return

        rows = self.add_scroll_rows()
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


        add_set = AtlasButton("Ajouter la panoplie")
        add_set.clicked.connect(self.add_whole_set)
        root.addWidget(add_set)

    def add_whole_set(self) -> None:
        for item in self.item_set.get("items", []):
            self.add_callback(item, 1)
        self.accept()


class LevelingDialog(AtlasDialog):
    def __init__(self, job_name: str, guide: dict[str, Any], find_item_callback, add_craft_callback, parent: QWidget | None = None):
        super().__init__(parent, density="compact")
        self.find_item_callback = find_item_callback
        self.add_craft_callback = add_craft_callback
        self.icon_cache = IconCache(28)
        self.setAccessibleName("LevelingDialog")
        local = guide.get("source") == "atlas-local"
        harvest = local and guide.get("kind") == "harvest"
        self.setWindowTitle(f"{job_name} — Repères locaux" if local else f"{job_name} 0-200")
        self.resize(*CRAFT_GEOMETRY["leveling_dialog_size"])
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        root = self.content_layout
        self.add_header(f"{job_name} — Repères locaux" if local else f"{job_name} 0-200")
        if local:
            note = QLabel(
                "Ressources classées par progression, sans palier XP ni quantité garantie."
                if harvest else
                "Recettes du catalogue local accessibles par niveau. "
                "1 exemplaire est proposé par défaut : ce n'est pas une route XP optimisée."
            )
            note.setObjectName("MutedLabel")
            note.setWordWrap(True)
            root.addWidget(note)
        rows = self.add_scroll_rows()
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
            box = CRAFT_GEOMETRY["leveling_icon_box"]
            icon.setFixedSize(box, box)
            icon.setAlignment(Qt.AlignCenter)
            if item:
                icon.setPixmap(self.icon_cache.icon_for_item(item).pixmap(28, 28))
            layout.addWidget(icon)
            level = QLabel(str(entry.get("level_range", "")))
            level.setObjectName("LevelBadge")
            level.setFixedWidth(CRAFT_GEOMETRY["leveling_level_badge_width"])
            level.setAlignment(Qt.AlignCenter)
            layout.addWidget(level)
            recipe = QLabel(
                f"Récolter : {craft.get('name', '')}" if harvest
                else f"{craft.get('quantity', 1)} x {craft.get('name', '')}"
            )
            recipe.setObjectName("CompactLabel")
            recipe.setWordWrap(False)
            layout.addWidget(recipe, 1)
            add = AtlasButton("Copier" if harvest else "+", variant="primary")
            add.setFixedSize(
                CRAFT_GEOMETRY["leveling_copy_action_width"] if harvest
                else CRAFT_GEOMETRY["leveling_add_action_width"],
                CRAFT_GEOMETRY["leveling_action_height"],
            )
            if harvest:
                add.clicked.connect(
                    lambda _checked=False, name=craft.get("name", ""):
                    QApplication.clipboard().setText(name)
                )
            else:
                add.clicked.connect(lambda _checked=False, target=craft: self.add_craft_callback(target))
            layout.addWidget(add)
            rows.addWidget(row)
        rows.addStretch(1)

        close = AtlasButton("Fermer", variant="secondary")
        close.clicked.connect(self.accept)
        self.add_action_row(close)


class RouteImageLabel(QLabel):
    def __init__(self, zoom_callback, parent: QWidget | None = None):
        super().__init__(parent)
        self.zoom_callback = zoom_callback
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(CRAFT_GEOMETRY["route_image_min_height"])

    def wheelEvent(self, event) -> None:
        delta = 1 if event.angleDelta().y() > 0 else -1
        self.zoom_callback(delta)
        event.accept()


class RouteDialog(AtlasDialog):
    def __init__(self, job_name: str, item: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent, density="compact")
        self.job_name = job_name
        self.item = item
        self.step = 1
        self.zoom = 1.0
        self.setWindowTitle(f"{job_name} - {item.get('name', 'Ressource')}")
        self.resize(*CRAFT_GEOMETRY["route_dialog_size"])
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        root = self.content_layout
        self.add_header(f"{job_name} - {item.get('name', 'Ressource')}")
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
        minimum = CRAFT_GEOMETRY["route_zoom_min_percent"] / 100
        maximum = CRAFT_GEOMETRY["route_zoom_max_percent"] / 100
        increment = CRAFT_GEOMETRY["route_zoom_step_percent"] / 100
        self.zoom = max(minimum, min(maximum, self.zoom + increment * delta))
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
        box = self.image.size()
        size = QSize(
            max(CRAFT_GEOMETRY["route_preview_min_width"], int(box.width() * self.zoom)),
            max(CRAFT_GEOMETRY["route_preview_min_height"], int(box.height() * self.zoom)),
        )
        # Route images share the same bounded Qt thumbnail decoder as Craft
        # icons, Quests and Guide preparation; no full-size reload on each zoom.
        from app.modules.encyclopedia.services.image_service import (
            ENCYCLOPEDIA_IMAGE_SERVICE,
        )
        scaled = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(path, size)
        if scaled.isNull():
            self.image.setPixmap(QPixmap())
            self.image.setText("Capture illisible.")
            return
        self.image.setText("")
        self.image.setPixmap(scaled)


class CraftPage(QWidget):
    def __init__(
        self,
        status_callback,
        parent: QWidget | None = None,
        preload: dict[str, Any] | None = None,
        *,
        defer_runtime: bool = False,
        retry_preload_callback: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.status_callback = status_callback
        self.retry_preload_callback = retry_preload_callback
        self.preload = preload if isinstance(preload, dict) else {}
        self.icon_cache = IconCache(32)
        self.items: list[dict[str, Any]] = []
        self.items_by_name: dict[str, dict[str, Any]] = {}
        self.item_lookup_cache: dict[str, dict[str, Any] | None] = {}
        self.selection: dict[int, dict[str, Any]] = {}
        self._selection_source_stamp = None
        self._selection_source_loaded = False
        self.guides: dict[str, Any] = {}
        self.jobs: list[dict[str, Any]] = []
        self.selected_job = ""
        self.category = "equipment"
        self._runtime_ready = False
        self._pending_result_items: list[dict[str, Any]] = []
        self._result_generation = 0
        self._job_layout_signature: tuple[object, ...] | None = None
        self._job_buttons_signature: tuple[object, ...] | None = None
        self._pending_leveling_job: str | None = None
        self.leveling_timer = QTimer(self)
        self.leveling_timer.setSingleShot(True)
        self.leveling_timer.timeout.connect(self._open_pending_leveling)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.refresh_results)
        self.result_batch_timer = QTimer(self)
        self.result_batch_timer.setSingleShot(True)
        self.result_batch_timer.setInterval(0)
        self.result_batch_timer.timeout.connect(self._render_next_result_batch)
        self.jobs_resize_timer = QTimer(self)
        self.jobs_resize_timer.setSingleShot(True)
        self.jobs_resize_timer.timeout.connect(self.refresh_jobs)
        self.layout_timer = QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.timeout.connect(self.apply_craft_body_layout)
        self.resource_dialog: CraftResourceDialog | None = None

        root = QVBoxLayout(self)
        compact_gap = UNITY_SPACING_PX["sm"]
        panel_padding = UNITY_SPACING_PX["md"]
        root.setContentsMargins(compact_gap, compact_gap, compact_gap, compact_gap)
        title = AtlasPageTitle("Craft")
        root.addWidget(title)
        self.retry_preload_button = AtlasButton("Réessayer le chargement Craft")
        self.retry_preload_button.setObjectName("CraftRetryPreload")
        self.retry_preload_button.setToolTip(
            "Réessayer le chargement du catalogue local après réparation des données."
        )
        self.retry_preload_button.setVisible(False)
        self.retry_preload_button.clicked.connect(self.retry_preload)
        root.addWidget(self.retry_preload_button, 0, Qt.AlignLeft)

        self.global_scroll = configure_unity_scroll_area(
            QScrollArea(), vertical_policy=Qt.ScrollBarAlwaysOn,
        )
        scroll_content = QWidget()
        content_root = QVBoxLayout(scroll_content)
        compact_inset = UNITY_SPACING_PX["xs"]
        content_root.setContentsMargins(compact_inset, compact_inset, compact_inset, compact_inset)
        content_root.setSpacing(compact_gap)
        self.global_scroll.setWidget(scroll_content)
        root.addWidget(self.global_scroll, 1)

        main_split = QVBoxLayout()
        main_split.setSpacing(compact_gap)
        content_root.addLayout(main_split, 1)

        self.craft_body_narrow = False
        self.craft_body = QGridLayout()
        self.craft_body.setSpacing(compact_gap)
        main_split.addLayout(self.craft_body, 1)

        self.craft_left_panel = QFrame()
        self.craft_left_panel.setObjectName("CraftPanel")
        apply_unity_panel_shadow(self.craft_left_panel)
        self.craft_left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        left = QVBoxLayout(self.craft_left_panel)
        left.setContentsMargins(panel_padding, panel_padding, panel_padding, panel_padding)
        left.setSpacing(compact_gap)
        category_row = QHBoxLayout()
        category_row.setSpacing(compact_inset)
        left.addLayout(category_row)
        self.category_buttons: dict[str, AtlasButton] = {}
        for key, label in (("equipment", "Équipement"), ("trophy_prysma", "Trophée / Prysmaradite"), ("resource", "Ressource craftable")):
            button = AtlasButton(label, variant="secondary", size="compact")
            button.clicked.connect(lambda _checked=False, k=key: self.set_category(k))
            self.category_buttons[key] = button
            category_row.addWidget(button)
        self.search = QLineEdit()
        self.search.setObjectName("CraftSearch")
        self.search.setPlaceholderText("Rechercher un item...")
        self.search.setMaximumWidth(CRAFT_GEOMETRY["search_max_width"])
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
        apply_unity_panel_shadow(self.craft_right_panel)
        self.craft_right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right = QVBoxLayout(self.craft_right_panel)
        right.setContentsMargins(panel_padding, panel_padding, panel_padding, panel_padding)
        right.setSpacing(compact_gap)
        selection_header = QHBoxLayout()
        selection_title = QLabel("Sélection")
        selection_title.setObjectName("PanelTitle")
        selection_header.addWidget(selection_title)
        selection_header.addStretch(1)
        clear_button = AtlasButton("Vider", variant="secondary")
        clear_button.setMaximumWidth(58)
        selection_header.addWidget(clear_button)
        right.addLayout(selection_header)
        self.selection_list = QListWidget()
        self.selection_list.setIconSize(QSize(24, 24))
        self.selection_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.selection_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.selection_list.setTextElideMode(Qt.ElideRight)
        right.addWidget(self.selection_list, 1)
        craft_button = AtlasButton("Lancer le Craft", variant="primary", size="normal")
        craft_button.setMinimumWidth(180)
        right.addWidget(craft_button, alignment=Qt.AlignHCenter)
        clear_button.clicked.connect(self.clear_selection)
        craft_button.clicked.connect(self.show_resources)
        self.apply_craft_body_layout(force=True)

        self.jobs_panel = QFrame()
        self.jobs_panel.setObjectName("CraftPanel")
        apply_unity_panel_shadow(self.jobs_panel)
        jobs_root = QVBoxLayout(self.jobs_panel)
        jobs_root.setContentsMargins(panel_padding, panel_padding, panel_padding, panel_padding)
        jobs_root.setSpacing(compact_gap)
        self.job_buttons_layout = QGridLayout()
        self.job_buttons_layout.setSpacing(compact_inset)
        jobs_root.addLayout(self.job_buttons_layout)
        self.job_actions_layout = QHBoxLayout()
        self.job_actions_layout.setSpacing(compact_inset)
        jobs_root.addLayout(self.job_actions_layout)
        self.job_content = QWidget()
        # Nested panel content is transparent: QWidget's default QSS fill
        # otherwise paints a near-black rectangle over the Unity glass card.
        self.job_content.setObjectName("AtlasTransparentHost")
        self.job_grid = QGridLayout(self.job_content)
        self.job_grid.setContentsMargins(0, 0, 0, 0)
        self.job_grid.setSpacing(compact_inset)
        jobs_root.addWidget(self.job_content, 1)
        main_split.addWidget(self.jobs_panel, 1)

        self.update_category_buttons()
        if defer_runtime:
            self.show_runtime_loading()
        else:
            self.hydrate_runtime(self.preload)
        self.layout_timer.start(0)

    def is_navigation_ready(self) -> bool:
        return True

    def show_runtime_loading(self) -> None:
        self.retry_preload_button.setVisible(False)
        self.search.setEnabled(False)
        for button in self.category_buttons.values():
            button.setEnabled(False)
        self.results.clear()
        loading = QListWidgetItem("Chargement des données Craft et Métiers…")
        loading.setFlags(Qt.NoItemFlags)
        self.results.addItem(loading)
        self.status_callback("Craft disponible · données en arrière-plan...")

    def show_runtime_error(self, message: str) -> None:
        self._runtime_ready = False
        self.search.setEnabled(False)
        for button in self.category_buttons.values():
            button.setEnabled(False)
        self.retry_preload_button.setVisible(callable(self.retry_preload_callback))
        self.results.clear()
        item = QListWidgetItem(str(message or "Chargement Craft impossible."))
        item.setFlags(Qt.NoItemFlags)
        self.results.addItem(item)
        self.status_callback(f"Chargement Craft impossible : {message}")

    def retry_preload(self) -> None:
        """Ask the owning Atlas shell to retry asynchronously, never block Qt."""
        if not callable(self.retry_preload_callback):
            return
        self.show_runtime_loading()
        self.retry_preload_callback()

    def hydrate_runtime(self, preload: dict[str, Any]) -> bool:
        if self._runtime_ready:
            return True
        if not isinstance(preload, dict) or not isinstance(preload.get("items"), list):
            return False
        # An empty list is expected for a valid lazy SQLite catalogue, but
        # not for the absent/corrupt-catalogue fallback.
        if preload.get("_skipped_reason") or preload.get("errors"):
            return False
        if preload.get("_prepared") is False:
            return False
        if not preload.get("items") and not (
            preload.get("_lazy_items") and preload.get("_prepared") is True
        ):
            return False
        self.retry_preload_button.setVisible(False)
        self.preload = preload
        self.load_items()
        self.load_leveling_guides()
        self.load_jobs()
        self.load_selection()
        self._runtime_ready = True
        self.search.setEnabled(True)
        for button in self.category_buttons.values():
            button.setEnabled(True)
        self._job_layout_signature = None
        self.refresh_results()
        self.refresh_selection()
        self.refresh_jobs()
        if bool(self.preload.get("_lazy_items")):
            self.status_callback(
                f"Craft prêt · recherche SQLite à la demande, {len(self.jobs)} métiers."
            )
        else:
            self.status_callback(
                f"Craft prêt · {len(self.items)} objets, {len(self.jobs)} métiers."
            )
        return True

    def release_runtime(self) -> None:
        """Drop reconstructible Craft UI/data before the page is destroyed."""

        for timer_name in (
            "search_timer",
            "result_batch_timer",
            "jobs_resize_timer",
            "layout_timer",
            "leveling_timer",
        ):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                timer.stop()
        if self.resource_dialog is not None:
            self.resource_dialog.close()
            self.resource_dialog = None
        self.items.clear()
        self.items_by_name.clear()
        self.item_lookup_cache.clear()
        clear_icons = getattr(self.icon_cache, "clear", None)
        if callable(clear_icons):
            clear_icons()
        self.selection.clear()
        self.jobs.clear()
        # A preloaded guide dict is borrowed, not owned by this page.
        self.guides = {}
        self._pending_leveling_job = None
        self.selected_job = ""
        self._result_generation += 1
        self._pending_result_items.clear()
        # The Craft shell is reconstructible: release populated Qt lists and
        # job widgets before deleteLater(), not just their Python providers.
        # Windows RSS sampling sees the Home transition before deferred QObject
        # destruction has necessarily reclaimed every large QListWidgetItem.
        self.results.clear()
        self.selection_list.clear()
        self.clear_layout(self.job_grid)
        self.clear_layout(self.job_buttons_layout)
        self.clear_layout(self.job_actions_layout)
        self._job_layout_signature = None
        self._job_buttons_signature = None
        self._runtime_ready = False
        self.preload = {}
        release = getattr(local_data_cache, "release_adapter", None)
        if callable(release):
            release()

    def clear_layout(self, layout) -> None:
        # Craft used to keep widget parents until Qt processes DeferredDelete.
        clear_unity_widget_layout(layout, recursive=True, detach_widgets=False)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._runtime_ready and self._selection_source_loaded:
            stamp = mtime_ctime_size_stamp(CRAFT_SELECTION_FILE)
            if stamp != self._selection_source_stamp:
                try:
                    self.load_selection()
                except (InvalidPersistentJsonError, OSError, TimeoutError) as exc:
                    self.status_callback(f"Sélection non actualisée : {exc}")
                else:
                    self.refresh_selection()

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
            button.set_variant("selected" if key == self.category else "secondary")

    def category_for_item(self, item: dict[str, Any]) -> str:
        # SQLite/preload already classifies items. Load the normalizer only for
        # an unclassified item, not when opening Craft and returning Home.
        from local_dofus_data.normalizer import craft_category_for_item

        return craft_category_for_item(item)

    def load_items(self) -> None:
        preloaded_items = self.preload.get("items")
        if isinstance(preloaded_items, list):
            if bool(self.preload.get("_prepared")):
                self.items = [item for item in preloaded_items if isinstance(item, dict)]
            else:
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
        if not bool(self.preload.get("_prepared")):
            for item in self.items:
                item["_search_name"] = normalize_key(item.get("name"))
                item["_craft_category"] = self.category_for_item(item)
        preloaded_by_name = self.preload.get("items_by_name")
        if isinstance(preloaded_by_name, dict):
            self.items_by_name = dict(preloaded_by_name)
        else:
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
        self._result_generation += 1
        self.result_batch_timer.stop()
        raw_query = self.search.text().strip()
        query = normalize_key(raw_query).replace("_", "")
        self.results.clear()
        self._pending_result_items = []
        if not self._runtime_ready or len(query) < 2:
            return

        if bool(self.preload.get("_lazy_items")) and hasattr(local_data_cache, "search_craft_items"):
            try:
                candidates = local_data_cache.search_craft_items(raw_query, limit=160, category=self.category)
            except Exception as exc:
                LOGGER.debug("Recherche Craft SQLite indisponible: %s", exc)
                candidates = []
        else:
            candidates = self.items

        for item in candidates:
            if not isinstance(item, dict):
                continue
            search_name = item.get("_search_name")
            if not isinstance(search_name, str):
                search_name = normalize_key(item.get("name"))
                item["_search_name"] = search_name
            category = item.get("_craft_category")
            if category not in {"equipment", "trophy_prysma", "resource"}:
                category = self.category_for_item(item)
                item["_craft_category"] = category
            if category != self.category or query not in search_name.replace("_", ""):
                continue
            self._pending_result_items.append(item)
            if len(self._pending_result_items) >= 80:
                break
        if self._pending_result_items:
            self.result_batch_timer.start()

    def _render_next_result_batch(self) -> None:
        if not self._pending_result_items:
            return
        generation = self._result_generation
        batch = self._pending_result_items[:_RESULT_BATCH_SIZE]
        del self._pending_result_items[:_RESULT_BATCH_SIZE]
        for item in batch:
            if generation != self._result_generation:
                return
            entry = QListWidgetItem(
                self.icon_cache.icon_for_item(item),
                f"{item.get('name', 'Objet')} | Lvl {item.get('level', '?')} | {item.get('type', '')}",
            )
            entry.setData(Qt.UserRole, item)
            self.results.addItem(entry)
        if self._pending_result_items and generation == self._result_generation:
            self.result_batch_timer.start()

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
        try:
            action = menu.exec(self.results.viewport().mapToGlobal(position))
            add_selected = action == add_action
            set_selected = set_action is not None and action == set_action
        finally:
            menu.deleteLater()
        if add_selected:
            self.add_item(item, 1)
        elif set_selected:
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
        exec_transient_dialog(dialog)

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
        before = dict(self.selection)
        row = self.selection.get(ident, {"item": item, "quantity": 0})
        self.selection[ident] = {**row, "quantity": max(1, int(row["quantity"]) + int(quantity or 1))}
        if not self._commit_selection_edit(before, ident):
            return
        self.refresh_selection()
        self.status_callback(f"Ajoute: {item.get('name', 'Objet')}")

    def remove_selected(self) -> None:
        entry = self.selection_list.currentItem()
        if not entry:
            return
        ident = entry.data(Qt.UserRole)
        self.remove_selection_item(ident)

    def remove_selection_item(self, ident: int) -> None:
        before = dict(self.selection)
        self.selection.pop(ident, None)
        if self._commit_selection_edit(before, ident):
            self.refresh_selection()

    def change_selection_quantity(self, ident: int, delta: int) -> None:
        row = self.selection.get(ident)
        if not row:
            return
        current = int(row.get("quantity") or 1)
        before = dict(self.selection)
        self.selection[ident] = {**row, "quantity": max(1, min(selection_editor_maximum(current), current + delta))}
        if self._commit_selection_edit(before, ident):
            self.refresh_selection()

    def set_selection_quantity(self, ident: int, value: int) -> None:
        row = self.selection.get(ident)
        if not row:
            return
        # The live editor already enforces its displayed range; do not
        # shrink it mid-edit when a bulk quantity crosses below 1000.
        before = dict(self.selection)
        self.selection[ident] = {**row, "quantity": max(1, clamp_int32(int(value or 1)))}
        if not self._commit_selection_edit(before, ident):
            # Roll back the visible counter without replacing its live sender.
            counter = self.sender()
            if isinstance(counter, QSpinBox):
                restore_unity_number_value(counter, min(counter.maximum(), int(row["quantity"])))

    def _commit_selection_edit(self, before: dict, ident: int | None = None, *, clear: bool = False) -> bool:
        try:
            self.save_selection(ident, clear=clear)
        except (InvalidPersistentJsonError, OSError, TimeoutError) as exc:
            self.selection.clear()
            self.selection.update(before)
            self.status_callback(f"Sélection non enregistrée : {exc}")
            return False
        return True

    def clear_selection(self) -> None:
        before = dict(self.selection)
        self.selection.clear()
        if self._commit_selection_edit(before, clear=True):
            self.refresh_selection()
            self.status_callback("Sélection vidée.")

    def refresh_selection(self) -> None:
        # The dict's insertion order is the user's craft order, including after
        # save/load. Keep the viewport stable when a new item is appended.
        scrollbar = self.selection_list.verticalScrollBar()
        scroll_position = scrollbar.value()
        updates_enabled = self.selection_list.updatesEnabled()
        self.selection_list.setUpdatesEnabled(False)
        try:
            self.selection_list.clear()
            for ident, row in self.selection.items():
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
                quantity = int(row["quantity"])
                qty = quantity_spinbox(quantity, maximum=selection_editor_maximum(quantity))
                delete = AtlasButton("x")
                delete.setObjectName("CraftRemoveSelectionItem")
                accessible_label = f"Retirer {item.get('name', 'Objet')} de la sélection"
                delete.setToolTip(accessible_label)
                delete.setAccessibleName(accessible_label)
                delete.setFocusPolicy(Qt.StrongFocus)
                delete.setMaximumWidth(30)
                qty.valueChanged.connect(lambda value, target=ident: self.set_selection_quantity(target, value))
                delete.clicked.connect(lambda _checked=False, target=ident: self.remove_selection_item(target))
                layout.addWidget(qty)
                layout.addWidget(delete)
                self.selection_list.setItemWidget(entry, widget)
        finally:
            self.selection_list.setUpdatesEnabled(updates_enabled)
        scrollbar.setValue(min(scroll_position, scrollbar.maximum()))

    def save_selection(self, ident: int | None = None, *, clear: bool = False) -> None:
        if clear:
            clear_persisted_selection(CRAFT_SELECTION_FILE)
            self._selection_source_stamp = mtime_ctime_size_stamp(CRAFT_SELECTION_FILE)
            self._selection_source_loaded = True
            return
        if ident is not None:
            row = self.selection.get(ident)
            persist_selection_quantity(
                CRAFT_SELECTION_FILE, ident,
                str(row["item"].get("name") or "") if row else "",
                int(row["quantity"]) if row else 0,
            )
            # An external editor may have changed unrelated rows. Force the
            # next activation to compare against the full persisted selection.
            self._selection_source_loaded = True
            return
        # Compatibility snapshot writer for explicit legacy callers.
        payload = {
            "items": [
                selection_item_row(
                    ident, row["item"].get("name", ""), row["quantity"],
                )
                for ident, row in self.selection.items()
            ]
        }
        write_json(CRAFT_SELECTION_FILE, payload)

    def load_selection(self) -> None:
        preloaded_selection = self.preload.get("selection")
        stamp = mtime_ctime_size_stamp(CRAFT_SELECTION_FILE)
        stamp_value = list(stamp) if stamp is not None else None
        previous_selection = dict(self.selection)
        loaded_selection = {}
        if (not self._selection_source_loaded and isinstance(preloaded_selection, dict)
                and ("selection_source_stamp" not in self.preload
                     or self.preload["selection_source_stamp"] == stamp_value)):
            for ident, row in preloaded_selection.items():
                item_id_value = optional_int(ident)
                item = row.get("item") if isinstance(row, dict) else None
                quantity = optional_int(row.get("quantity")) if isinstance(row, dict) else None
                if (item_id_value is not None and item_id_value > 0
                        and isinstance(item, dict) and quantity is not None and quantity > 0):
                    loaded_selection[item_id_value] = {"item": item, "quantity": quantity}
            self.selection.clear()
            self.selection.update(loaded_selection)
            self._selection_source_stamp = stamp
            self._selection_source_loaded = True
            return

        def lookup(ident: int):
            previous = previous_selection.get(ident)
            if previous is not None:
                return previous["item"]
            if isinstance(preloaded_selection, dict):
                row = preloaded_selection.get(ident, preloaded_selection.get(str(ident)))
                if isinstance(row, dict) and isinstance(row.get("item"), dict):
                    return row["item"]
            try:
                return local_data_cache.get_item(ident)
            except Exception:
                return None

        # Never replace visible state with an empty fallback on a damaged source.
        payload = (
            read_selection_payload(CRAFT_SELECTION_FILE)
            if self._selection_source_loaded
            else read_json(CRAFT_SELECTION_FILE, {"items": []})
        )
        loaded_selection = resolve_selection(payload, lookup, allow_legacy=True)
        self.selection.clear()
        self.selection.update(loaded_selection)
        self._selection_source_stamp = stamp
        self._selection_source_loaded = True

    def load_leveling_guides(self) -> None:
        payload = self.preload.get("guides")
        entries = payload.get("guides") if isinstance(payload, dict) else None
        if not isinstance(entries, dict) or not entries:
            # An empty placeholder from the asynchronous preload must not
            # hide a legitimate local guide catalogue already on disk.
            disk = read_json(
                LEVELING_FILE,
                {"source": "gamosaurus", "offline_runtime": True, "guides": {}},
            )
            disk_entries = disk.get("guides") if isinstance(disk, dict) else None
            if isinstance(disk_entries, dict) and disk_entries:
                payload = disk
            elif not isinstance(entries, dict):
                payload = disk
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
            if not key or key == "base" or "mage" in key or "bestiologue" in key:
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
        if bool(self.preload.get("_prepared")) and not bool(self.preload.get("_lazy_items")):
            self.item_lookup_cache[key] = None
            return None
        if hasattr(local_data_cache, "search_items"):
            try:
                results = local_data_cache.search_items(name, limit=8)
                if results:
                    self.item_lookup_cache[key] = results[0]
                    return results[0]
            except Exception as exc:
                LOGGER.debug(
                    "Recherche cache local indisponible pour %r; fallback index mémoire: %s",
                    name,
                    exc,
                )

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

    def has_leveling_content(self, job_name: str) -> bool:
        guide = self.guide_for_job(job_name)
        if isinstance(guide, dict) and guide.get("entries"):
            return True
        # Harvest professions have a lightweight, authored resource sequence
        # even when the optional editorial JSON is not shipped. No SQLite
        # scan or synthetic XP calculation is needed for the click.
        if self.is_harvest_job(job_name):
            selected = normalize_key(job_name)
            return any(
                normalize_key(name) == selected and bool(resources)
                for name, resources in JOB_RESOURCE_GROUPS.items()
            )
        return False

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
        signature = (
            normalize_key(self.selected_job),
            self.job_button_column_count(),
            self.resource_column_count(),
            tuple(normalize_key(job.get("name")) for job in self.jobs),
        )
        if signature == self._job_layout_signature:
            return
        self._job_layout_signature = signature
        self.clear_layout(self.job_actions_layout)
        self.clear_layout(self.job_grid)

        selected_key = normalize_key(self.selected_job)
        names = tuple(str(job.get("name") or "Métier") for job in self.jobs)
        button_columns = self.job_button_column_count()
        button_signature = (button_columns, names)
        if button_signature != self._job_buttons_signature:
            self.clear_layout(self.job_buttons_layout)
            self._job_buttons_signature = button_signature
            for index, name in enumerate(names):
                # Decorative icons must not open the local-data adapter.
                button = AtlasButton(name, variant="secondary")
                button.setMaximumHeight(28)
                button.clicked.connect(lambda _checked=False, target=name: self.set_job(target))
                self.job_buttons_layout.addWidget(
                    button, index // button_columns, index % button_columns,
                )
            for column in range(button_columns):
                self.job_buttons_layout.setColumnStretch(column, 1)
        # Reuse the actual buttons on selection and resource-grid resize.
        for index in range(self.job_buttons_layout.count()):
            button = self.job_buttons_layout.itemAt(index).widget()
            if isinstance(button, AtlasButton):
                if normalize_key(button.text()) == selected_key:
                    button.set_variant("selected")
                else:
                    button.set_variant("secondary")

        if not selected_key:
            self.job_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.job_grid.setRowStretch(0, 1)
            self.job_actions_layout.addStretch(1)
            return

        if self.has_leveling_content(self.selected_job):
            source_guide = self.guide_for_job(self.selected_job)
            authored = isinstance(source_guide, dict) and bool(source_guide.get("entries"))
            label = "Leveling 0-200" if authored else "Repères de récolte"
            leveling = AtlasButton(label, variant="primary", size="normal")
            leveling.setToolTip(
                "Guide Leveling local" if authored
                else "Ressources locales classées, sans gains d'XP garantis"
            )
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
                button = configure_unity_tool_button(
                    QToolButton(), object_name="ResourceTile",
                    box=CRAFT_GEOMETRY["resource_tile_box"],
                    icon_size=CRAFT_GEOMETRY["resource_tile_artwork"],
                    text=short_label(label, 10), pointing=True,
                )
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setToolTip(label)
                button.setIcon(self.icon_cache.icon_for_item(item))
                button.clicked.connect(lambda _checked=False, job=job_name, target=item: self.show_route(job, target))
                self.job_grid.addWidget(button, tile_index // columns, tile_index % columns, alignment=Qt.AlignTop)
                tile_index += 1
        for column in range(columns):
            self.job_grid.setColumnStretch(column, 1)
        self.job_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.job_grid.setRowStretch((tile_index // columns) + 1, 1)

    def set_job(self, job_name: str) -> None:
        self.leveling_timer.stop()
        self._pending_leveling_job = None
        self.selected_job = job_name
        self.refresh_jobs()
        # A job click opens its authored local guide only when it actually has
        # entries. Missing/editorial guides should never cause a blocking
        # warning popup on every selection. The explicit Leveling action can
        # still offer the existing catalogue-based fallback when requested.
        if not self.has_leveling_content(job_name):
            return
        # Owned timer: coalesce repeated clicks and cancel on page release.
        self._pending_leveling_job = job_name
        self.leveling_timer.start(20)

    def _open_pending_leveling(self) -> None:
        selected = self._pending_leveling_job
        self._pending_leveling_job = None
        if selected is not None and self.selected_job == selected:
            self.open_leveling_dialog(selected)

    def open_leveling_dialog(self, job_name: str) -> None:
        guide = self.guide_for_job(job_name)
        if not isinstance(guide, dict) or not guide.get("entries"):
            # The editorial JSON is not tracked in Git. Prefer the real guide
            # when present, otherwise derive visible, honest suggestions
            # from the canonical local Craft catalogue already installed.
            from app.craft_preload import build_local_leveling_suggestions
            guide = build_local_leveling_suggestions(job_name)
        if not isinstance(guide, dict) or not guide.get("entries"):
            if not LEVELING_FILE.is_file():
                detail = f"Fichier de guides absent : {LEVELING_FILE}"
            else:
                detail = f"Guide absent ou vide pour {job_name} dans {LEVELING_FILE.name}."
            message = f"Leveling indisponible pour {job_name}. {detail}"
            LOGGER.warning("%s", message)
            self.status_callback(message)
            QMessageBox.warning(self, "Leveling indisponible", message)
            return
        dialog = LevelingDialog(job_name, guide, self.find_item_by_name, self.add_leveling_craft, self)
        exec_transient_dialog(dialog)

    def add_leveling_craft(self, craft: dict[str, Any]) -> None:
        item = self.find_item_by_name((craft or {}).get("name", ""))
        if not item or item_id(item) is None:
            self.status_callback(f"Objet introuvable en base locale: {(craft or {}).get('name', 'Objet leveling')}")
            return
        self.add_item(item, int((craft or {}).get("quantity") or 1))

    def show_route(self, job_name: str, item: dict[str, Any]) -> None:
        dialog = RouteDialog(canonical_job_name(job_name), item, self)
        exec_transient_dialog(dialog)

    def show_resources(self) -> None:
        if not self.selection:
            self.status_callback("Sélection vide.")
            return
        resources: dict[str, dict[str, Any]] = {}
        missing = []
        lookup_errors = 0
        for row in self.selection.values():
            item = row["item"]
            ident = item_id(item)
            if ident is None:
                missing.append(item.get("name", "Objet sans ID"))
                continue
            try:
                recipe = local_data_cache.get_recipe_for_item(ident)
            except Exception:
                LOGGER.exception("Craft recipe lookup failed for item %s", ident)
                lookup_errors += 1
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
        dialog = CraftResourceDialog(resources, missing)
        dialog.setModal(False)
        if not present_transient_dialog(self, "resource_dialog", dialog):
            self.status_callback("La fenêtre de ressources actuelle reste ouverte.")
            return
        message = f"{len(resources)} ressource(s) agregee(s)."
        if lookup_errors:
            message += f" {lookup_errors} recette(s) indisponible(s) (erreur de lecture)."
        self.status_callback(message)
