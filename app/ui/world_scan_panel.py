from __future__ import annotations

import logging
from threading import Thread
from typing import Any
import unicodedata

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget

from app.cartography.map_asset_loader import resolve_asset_path
from app.cartography.world_service import WorldService
from app.constants import LOGGER
from app.services.maps.map_cache_builder import get_cache_summary, get_local_image_stats
from app.services.maps.map_manifest import DEFAULT_WORLD_AREA, DEFAULT_WORLD_NAME, WORLD_MENU_NAMES
from app.ui.map_canvas_widget import MapCanvasWidget


DEFAULT_WORLD_CONTEXT = f"{DEFAULT_WORLD_NAME} / {DEFAULT_WORLD_AREA}"
WORLD_NAMES = WORLD_MENU_NAMES


class WorldMenuScrollArea(QScrollArea):
    def viewportEvent(self, event) -> bool:
        handled = super().viewportEvent(event)
        if event.type() == QEvent.Wheel:
            event.accept()
            return True
        return handled

    def wheelEvent(self, event) -> None:
        super().wheelEvent(event)
        event.accept()


class WorldScanPanel(QWidget):
    cartographyLoadFinished = Signal(int, object)

    def __init__(self, status_callback=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("worldScanPage")
        self.status_callback = status_callback or (lambda _text: None)
        # Database initialization and all initial queries are delayed to the
        # cartography worker. The panel itself can therefore be shown first.
        self.service = WorldService(initialize=False)

        self.views: list[dict[str, Any]] = []
        self.views_by_key: dict[str, dict[str, Any]] = {}
        self.current_view_key = ""
        self.current_view: dict[str, Any] | None = None
        self.maps: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.maps_by_coord: dict[tuple[int, int], dict[str, Any]] = {}
        self.selected_map: dict[str, Any] | None = None
        self.selected_link: dict[str, Any] | None = None
        self.history: list[str] = []
        self.current_world_name = DEFAULT_WORLD_NAME
        self.world_buttons: dict[str, QPushButton] = {}
        self.scan_progress_label: QLabel | None = None
        self.cache_state_label: QLabel | None = None
        self._load_generation = 0
        self._load_in_flight = False
        self._pending_load_request: dict[str, Any] | None = None
        self._deferred_load_result: tuple[int, object] | None = None
        self._initial_load_pending = True
        self._last_cache_summary = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        accent = QFrame()
        accent.setObjectName("TitleAccent")
        accent.setFixedSize(4, 24)
        title = QLabel("Scan Monde")
        title.setObjectName("PageTitle")
        title.setFixedHeight(28)
        header.addWidget(accent, alignment=Qt.AlignVCenter)
        header.addWidget(title, 1)
        root.addLayout(header)

        toolbar = QFrame()
        toolbar.setObjectName("MapToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)
        self.reload_button = self.make_button("Recharger", "secondaryButton")
        self.verify_button = self.make_button("Marquer map OK", "primaryButton")
        self.unverify_button = self.make_button("Marquer non vérif", "secondaryButton")
        self.current_button = self.make_button("Définir actuelle", "secondaryButton")
        for button in (
            self.reload_button,
            self.verify_button,
            self.unverify_button,
            self.current_button,
        ):
            toolbar_layout.addWidget(button)
        toolbar_layout.addStretch(1)
        root.addWidget(toolbar)

        self.breadcrumb_label = QLabel(DEFAULT_WORLD_CONTEXT)
        self.breadcrumb_label.setObjectName("BreadcrumbLabel")
        self.breadcrumb_label.setFixedHeight(24)
        root.addWidget(self.breadcrumb_label)

        self.canvas = MapCanvasWidget()
        self.canvas.set_map_placeholder("Chargement de la cartographie…")
        root.addWidget(self.canvas, 1)

        self.planet_button = QToolButton(self.canvas)
        self.planet_button.setObjectName("WorldPlanetButton")
        self.planet_button.setFixedSize(60, 60)
        self.planet_button.setCursor(Qt.PointingHandCursor)
        self.planet_button.setIcon(self.planet_icon())
        self.planet_button.setIconSize(QSize(34, 34))
        self.planet_button.setToolTip("Sélection du monde")
        self.planet_button.clicked.connect(self.toggle_world_menu)
        self.planet_button.move(14, 14)

        self.world_menu = QFrame(self.canvas)
        self.world_menu.setObjectName("WorldMenu")
        self.world_menu.hide()
        menu_layout = QVBoxLayout(self.world_menu)
        menu_layout.setContentsMargins(6, 6, 6, 6)
        menu_layout.setSpacing(0)
        self.world_menu_scroll = WorldMenuScrollArea(self.world_menu)
        self.world_menu_scroll.setObjectName("WorldMenuScroll")
        self.world_menu_scroll.setWidgetResizable(True)
        self.world_menu_scroll.setFrameShape(QFrame.NoFrame)
        self.world_menu_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.world_menu_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.world_menu_contents = QWidget()
        self.world_menu_contents.setObjectName("WorldMenuContents")
        self.world_menu_list = QVBoxLayout(self.world_menu_contents)
        self.world_menu_list.setContentsMargins(2, 2, 2, 2)
        self.world_menu_list.setSpacing(4)
        self.rebuild_world_menu(list(WORLD_NAMES))
        self.world_menu_scroll.setWidget(self.world_menu_contents)
        menu_layout.addWidget(self.world_menu_scroll)
        self.world_menu.move(14, 82)

        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("WorldDetailPanel")
        self.detail_panel.setFixedHeight(74)
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(12, 7, 12, 7)
        detail_layout.setSpacing(4)
        self.detail_title = QLabel("Détail")
        self.detail_title.setObjectName("WorldDetailTitle")
        detail_layout.addWidget(self.detail_title)
        self.scan_progress_label = QLabel("")
        self.scan_progress_label.setObjectName("WorldScanProgress")
        self.scan_progress_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.scan_progress_label)
        self.cache_state_label = QLabel("")
        self.cache_state_label.setObjectName("WorldCacheState")
        self.cache_state_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.cache_state_label)
        root.addWidget(self.detail_panel)

        self.status_label = QLabel("")
        self.status_label.setObjectName("MutedLabel")
        self.status_label.setFixedHeight(18)
        root.addWidget(self.status_label)

        self.reload_button.clicked.connect(self.reload_all)
        self.verify_button.clicked.connect(self.mark_selected_verified)
        self.unverify_button.clicked.connect(self.mark_selected_unverified)
        self.current_button.clicked.connect(self.set_selected_current)
        self.canvas.mapSelected.connect(self.on_map_selected)
        self.canvas.linkSelected.connect(self.on_link_selected)
        self.canvas.linkActivated.connect(self.open_link_target)
        self.cartographyLoadFinished.connect(self._on_cartography_load_finished)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self.set_scan_progress(0, None)
        self.set_cache_state("Cache local : chargement…")
        self.update_action_state()

    def make_button(self, text: str, object_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setFixedHeight(30)
        button.setMinimumWidth(108)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def set_message(self, text: str) -> None:
        self.set_status_text(text)

    def set_status_text(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_callback(text)

    def set_map_placeholder(self, text: str = "") -> None:
        self.canvas.set_map_placeholder(text)

    def set_scan_progress(self, scanned: int, total: int | None) -> None:
        scanned_count = max(0, int(scanned or 0))
        total_text = "—" if total is None else str(max(0, int(total)))
        if self.scan_progress_label is not None:
            self.scan_progress_label.setText(f"Maps à scanner : {scanned_count} / {total_text}")

    def set_cache_state(self, text: str) -> None:
        if self.cache_state_label is not None:
            self.cache_state_label.setText(text or "Cache local : en attente")

    def refresh_scan_progress(self) -> None:
        summary = self._last_cache_summary
        if summary is None:
            self.set_scan_progress(0, None)
            self.set_cache_state("Cache local : chargement…" if self._load_in_flight else "Cache local : en attente")
            return
        self.set_scan_progress(summary.scanned_count, summary.total_count)
        self.set_cache_state(summary.cache_state)

    def reload_all(self) -> None:
        if not self.isVisible():
            self._initial_load_pending = True
            return
        self._initial_load_pending = False
        self.set_message("Chargement de la cartographie…")
        self.set_map_placeholder("Chargement de la cartographie…")
        self._queue_cartography_load(
            mode="reload",
            view_key=self.current_view_key,
            push_history=False,
        )

    def import_manifest(self) -> None:
        summary = self.service.import_manifest()
        self.reload_all()
        if summary.get("errors"):
            self.set_message("; ".join(str(error) for error in summary["errors"][:2]))
            return
        self.set_message(
            f"Import termine: {summary['views']} vue(s), {summary['maps']} map(s), "
            f"{summary['links']} lien(s)."
        )

    def load_view_from_sidebar(self, view_key: str) -> None:
        self.load_view(view_key, push_history=True)

    def load_view(self, view_key: str, push_history: bool = True) -> None:
        target = str(view_key or "").strip()
        if not target:
            return
        self._queue_cartography_load(
            mode="view",
            view_key=target,
            push_history=push_history,
        )

    def _queue_cartography_load(
        self,
        *,
        mode: str,
        view_key: str,
        push_history: bool,
        select_coord: tuple[int, int] | None = None,
        completion_message: str = "",
    ) -> None:
        self._load_generation += 1
        self._pending_load_request = {
            "generation": self._load_generation,
            "mode": str(mode or "view"),
            "view_key": str(view_key or ""),
            "push_history": bool(push_history),
            "select_coord": select_coord,
            "completion_message": str(completion_message or ""),
        }
        self._deferred_load_result = None
        self._start_next_cartography_load()

    def _start_next_cartography_load(self) -> None:
        if self._load_in_flight or self._pending_load_request is None:
            return
        request = self._pending_load_request
        self._pending_load_request = None
        self._load_in_flight = True
        self.refresh_scan_progress()

        def worker() -> None:
            generation = int(request["generation"])
            try:
                payload = self._build_cartography_payload(request)
            except Exception as exc:
                LOGGER.exception("Chargement cartographique asynchrone impossible.")
                payload = {
                    "mode": request.get("mode"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            try:
                self.cartographyLoadFinished.emit(generation, payload)
            except RuntimeError:
                # The page can be destroyed while the worker is finishing.
                pass

        Thread(target=worker, name="DofusAtlasCartographyLoad", daemon=True).start()

    def _build_cartography_payload(self, request: dict[str, Any]) -> dict[str, Any]:
        views = self.service.get_map_views()
        views_by_key = {str(view.get("view_key") or ""): view for view in views}
        mode = str(request.get("mode") or "view")
        requested_key = str(request.get("view_key") or "")
        if mode == "reload" and requested_key not in views_by_key:
            requested_key = str((views[0] if views else {}).get("view_key") or "")
        view = views_by_key.get(requested_key) if requested_key else None

        maps: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        image = QImage()
        asset_path = ""
        is_placeholder = True
        world_name = DEFAULT_WORLD_NAME
        if view is not None:
            maps = self.service.get_maps_for_view(requested_key)
            links = self.service.get_links_for_view(requested_key)
            image, asset_path, is_placeholder = self._load_map_image(str(view.get("asset_path") or ""))
            world_name = self._world_name_from_view_data(view)

        try:
            cache_summary = get_cache_summary(world_name)
        except OSError:
            cache_summary = None

        return {
            "mode": mode,
            "views": views,
            "view_key": requested_key,
            "view": view,
            "maps": maps,
            "links": links,
            "image": image,
            "asset_path": asset_path,
            "is_placeholder": is_placeholder,
            "world_name": world_name,
            "cache_summary": cache_summary,
            "push_history": bool(request.get("push_history")),
            "select_coord": request.get("select_coord"),
            "completion_message": str(request.get("completion_message") or ""),
            "error": "",
        }

    @staticmethod
    def _world_name_from_view_data(view: dict[str, Any]) -> str:
        name = str(view.get("name") or "").strip()
        normalized = unicodedata.normalize("NFKD", name)
        ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
        if ascii_text.replace("’", "'").strip().casefold().startswith("monde des douze"):
            return DEFAULT_WORLD_NAME
        return name or DEFAULT_WORLD_NAME

    @staticmethod
    def _load_map_image(asset_path: str) -> tuple[QImage, str, bool]:
        resolved = resolve_asset_path(asset_path)
        image = QImage()
        is_placeholder = True
        path_text = str(resolved or "")
        if resolved is not None:
            try:
                if resolved.exists() and resolved.is_file():
                    image = QImage(str(resolved))
                    is_placeholder = image.isNull()
            except OSError:
                image = QImage()
        if image.isNull():
            image = QImage(1400, 880, QImage.Format_ARGB32)
            image.fill(QColor("#0D1724"))
            is_placeholder = True
        return image, path_text, is_placeholder

    def _on_cartography_load_finished(self, generation: int, payload: object) -> None:
        self._load_in_flight = False
        if int(generation) != self._load_generation:
            self._start_next_cartography_load()
            return
        if not self.isVisible():
            self._deferred_load_result = (int(generation), payload)
            self._start_next_cartography_load()
            return
        self._apply_cartography_payload(payload)
        self._start_next_cartography_load()

    def _apply_cartography_payload(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        error = str(data.get("error") or "")
        if error:
            self.refresh_scan_progress()
            self.set_message(f"Chargement cartographique impossible : {error}")
            return

        views = data.get("views")
        next_views = list(views) if isinstance(views, list) else []
        previous_view_signature = tuple(
            (str(view.get("view_key") or ""), str(view.get("name") or ""))
            for view in self.views
        )
        next_view_signature = tuple(
            (str(view.get("view_key") or ""), str(view.get("name") or ""))
            for view in next_views
            if isinstance(view, dict)
        )
        self.views = [view for view in next_views if isinstance(view, dict)]
        self.views_by_key = {str(view.get("view_key") or ""): view for view in self.views}
        if next_view_signature != previous_view_signature:
            self.rebuild_world_menu(self.world_names_from_views())

        self._last_cache_summary = data.get("cache_summary")
        view = data.get("view") if isinstance(data.get("view"), dict) else None
        requested_key = str(data.get("view_key") or "")
        mode = str(data.get("mode") or "view")
        if view is None:
            if mode == "view" and requested_key:
                self.refresh_scan_progress()
                self.set_message(f"Vue introuvable: {requested_key}")
                return
            self.current_view_key = ""
            self.current_view = None
            self.maps = []
            self.links = []
            self.maps_by_coord = {}
            self.selected_map = None
            self.selected_link = None
            self.canvas.set_view(None, QPixmap(), [], [], "", True)
            self.canvas.set_map_placeholder("Aucune vue cartographique chargée.")
            self.breadcrumb_label.setText(DEFAULT_WORLD_CONTEXT)
            self.refresh_scan_progress()
            self.update_action_state()
            self.log_scan_world_debug("startup")
            self.set_message("Aucune vue cartographique chargée.")
            return

        if bool(data.get("push_history")) and self.current_view_key and self.current_view_key != requested_key:
            self.history.append(self.current_view_key)

        self.current_view_key = requested_key
        self.current_view = view
        maps = data.get("maps")
        links = data.get("links")
        self.maps = [row for row in maps if isinstance(row, dict)] if isinstance(maps, list) else []
        self.links = [row for row in links if isinstance(row, dict)] if isinstance(links, list) else []
        self.maps_by_coord = {(int(row["x"]), int(row["y"])): row for row in self.maps}
        self.selected_map = None
        self.selected_link = None

        image = data.get("image")
        pixmap = QPixmap.fromImage(image) if isinstance(image, QImage) and not image.isNull() else QPixmap()
        asset_path = str(data.get("asset_path") or "")
        is_placeholder = bool(data.get("is_placeholder", True))
        self.current_world_name = str(data.get("world_name") or self.world_name_for_view(view))
        self.canvas.set_view(view, pixmap, self.maps, self.links, asset_path, is_placeholder)
        if is_placeholder:
            self.canvas.set_map_placeholder(self.missing_asset_message_for_view(view))
            LOGGER.warning(
                "[ScanMonde] asset manquant view_key=%s selected_world=%s asset_attendu=%s recuperation_tentee=%s commande=%s",
                requested_key,
                self.current_world_name,
                str(view.get("asset_path") or ""),
                False,
                "python scripts/recover_cartography_assets.py",
            )
        else:
            self.canvas.set_map_placeholder("")
        self.breadcrumb_label.setText(self.display_context_for_view(view))
        self.refresh_world_menu_state()

        select_coord = data.get("select_coord")
        if isinstance(select_coord, (tuple, list)) and len(select_coord) == 2:
            try:
                coord = (int(select_coord[0]), int(select_coord[1]))
            except (TypeError, ValueError):
                coord = None
            if coord is not None:
                refreshed = self.maps_by_coord.get(coord)
                if refreshed is not None:
                    self.selected_map = refreshed
                    self.canvas.select_map_coord(*coord)

        self.update_action_state()
        self.refresh_scan_progress()
        self.log_scan_world_debug("startup" if mode == "reload" else "view_loaded")
        completion_message = str(data.get("completion_message") or "")
        if completion_message:
            self.set_message(completion_message)
        elif mode == "reload":
            self.set_message(f"{len(self.views)} vue(s) cartographique(s) chargée(s).")

    def missing_asset_message_for_view(self, view: dict[str, Any]) -> str:
        asset_path = str(view.get("asset_path") or "")
        return (
            "Carte locale absente ou non valid\u00e9e pour ce monde.\n"
            f"Asset manquant : {asset_path}\n"
            "Lancez : python scripts/recover_cartography_assets.py"
        )

    def log_scan_world_debug(self, reason: str) -> None:
        stats = get_local_image_stats() if LOGGER.isEnabledFor(logging.DEBUG) else None
        view = self.current_view or {}
        asset_path_text = str(view.get("asset_path") or "")
        resolved_asset = resolve_asset_path(asset_path_text)
        asset_exists = bool(resolved_asset and resolved_asset.exists() and resolved_asset.is_file())
        first_cache_image = str(stats.first_image) if stats and stats.first_image else ""
        first_image_used = str(resolved_asset) if asset_exists and resolved_asset is not None else ""
        LOGGER.info(
            "[ScanMonde] debug reason=%s selected_world=%s view_key=%s view_name=%s "
            "local_image_count=%s first_cache_image=%s first_image_used=%s "
            "asset_path=%s resolved_asset=%s asset_exists=%s maps_in_view=%s",
            reason,
            self.current_world_name,
            self.current_view_key,
            str(view.get("name") or ""),
            stats.image_count if stats else "not_collected",
            first_cache_image,
            first_image_used,
            asset_path_text,
            str(resolved_asset or ""),
            asset_exists,
            len(self.maps),
        )
        if stats is None:
            return
        if stats.image_count <= 0:
            LOGGER.error(
                "[ScanMonde] cache local vide, aucune map image int\u00e9gr\u00e9e | "
                "selected_world=%s view_key=%s asset_path=%s resolved_asset=%s",
                self.current_world_name,
                self.current_view_key,
                asset_path_text,
                str(resolved_asset or ""),
            )
        elif asset_path_text and not asset_exists:
            LOGGER.warning(
                "[ScanMonde] images locales pr\u00e9sentes mais asset de vue introuvable | "
                "selected_world=%s view_key=%s asset_path=%s resolved_asset=%s first_cache_image=%s",
                self.current_world_name,
                self.current_view_key,
                asset_path_text,
                str(resolved_asset or ""),
                first_cache_image,
            )

    def breadcrumb_for(self, view: dict[str, Any]) -> str:
        parts = [str(view.get("name") or view.get("view_key") or "Vue")]
        parent_key = str(view.get("parent_view_key") or "").strip()
        seen = {str(view.get("view_key") or "")}
        while parent_key and parent_key not in seen:
            seen.add(parent_key)
            parent = self.views_by_key.get(parent_key)
            if parent is None:
                break
            parts.append(str(parent.get("name") or parent_key))
            parent_key = str(parent.get("parent_view_key") or "").strip()
        return " > ".join(reversed(parts))

    def on_map_selected(self, view_key: str, x: int, y: int) -> None:
        if view_key != self.current_view_key:
            return
        self.selected_map = self.maps_by_coord.get((int(x), int(y)))
        self.selected_link = None
        self.update_action_state()
        if self.selected_map:
            self.set_message(f"Map selectionnee: {x},{y}.")

    def on_link_selected(self, link: object) -> None:
        if not isinstance(link, dict):
            return
        self.selected_link = link
        self.selected_map = None
        self.update_action_state()
        self.set_message(f"Lien selectionne: {link.get('label') or link.get('target_view_key')}.")

    def open_link_target(self, target_view_key: str) -> None:
        target = str(target_view_key or "").strip()
        if target:
            self.load_view(target, push_history=True)

    def can_go_back(self) -> bool:
        parent_key = str((self.current_view or {}).get("parent_view_key") or "").strip()
        return bool(self.history or parent_key)

    def go_back(self) -> None:
        if self.history:
            self.load_view(self.history.pop(), push_history=False)
            return
        parent_key = str((self.current_view or {}).get("parent_view_key") or "").strip()
        if parent_key:
            self.load_view(parent_key, push_history=False)

    def update_action_state(self) -> None:
        has_selection = self.selected_map is not None
        for button in (self.verify_button, self.unverify_button, self.current_button):
            button.setEnabled(has_selection)

    def mark_selected_verified(self) -> None:
        self.change_selected_status("verified")

    def mark_selected_unverified(self) -> None:
        self.change_selected_status("unverified")

    def set_selected_current(self) -> None:
        self.change_selected_status("current")

    def change_selected_status(self, status: str) -> None:
        if not self.selected_map:
            return
        view_key = str(self.selected_map.get("view_key") or self.current_view_key)
        x = int(self.selected_map["x"])
        y = int(self.selected_map["y"])
        if status == "verified":
            self.service.mark_verified(view_key, x, y)
            message = f"Map {x},{y} verifiee."
        elif status == "unverified":
            self.service.mark_unverified(view_key, x, y)
            message = f"Map {x},{y} non verifiee."
        else:
            self.service.set_current(view_key, x, y)
            message = f"Map actuelle: {x},{y}."

        self._queue_cartography_load(
            mode="view",
            view_key=view_key,
            push_history=False,
            select_coord=(x, y),
            completion_message=message,
        )

    def set_current_world(self, name: str) -> None:
        world = str(name or "").strip() or DEFAULT_WORLD_NAME
        self.current_world_name = world
        view_key = self.view_key_for_world(world)
        if view_key:
            self.load_view(view_key, push_history=False)
            return
        self.current_view_key = ""
        self.current_view = None
        self.maps = []
        self.links = []
        self.maps_by_coord = {}
        self.selected_map = None
        self.selected_link = None
        self.canvas.set_view(None, QPixmap(), [], [], "", True)
        self.breadcrumb_label.setText(self.display_context_for_world(world))
        self.refresh_world_menu_state()
        self.update_action_state()
        self.refresh_scan_progress()
        self.log_scan_world_debug("world_selected")

    def toggle_world_menu(self) -> None:
        if self.world_menu.isVisible():
            self.hide_world_menu()
        else:
            self.show_world_menu()

    def show_world_menu(self) -> None:
        self.update_world_menu_geometry()
        self.world_menu.show()
        self.world_menu.raise_()
        self.planet_button.raise_()

    def update_world_menu_geometry(self) -> None:
        left = 14
        top = 82
        if self.canvas.height() - top - 14 < 120:
            top = 14
        available_width = max(120, self.canvas.width() - left - 14)
        width = min(320, available_width)
        row_height = 32
        content_height = 16 + row_height * max(1, len(self.world_buttons))
        available_height = max(80, self.canvas.height() - top - 14)
        page_height = max(80, int(self.height() * 0.7))
        height = min(content_height, 560, page_height, available_height)
        self.world_menu.setFixedSize(width, height)
        self.world_menu.move(left, top)

    def hide_world_menu(self) -> None:
        self.world_menu.hide()

    def on_world_selected(self, name: str) -> None:
        self.set_current_world(name)
        self.hide_world_menu()

    def view_key_for_world(self, name: str) -> str:
        needle = self.normalize_world_name(name)
        for view in self.views:
            view_name = str(view.get("name") or "")
            normalized_view = self.normalize_world_name(view_name)
            if needle == "monde des douze" and normalized_view.startswith("monde des douze"):
                return str(view.get("view_key") or "")
            if normalized_view == needle:
                return str(view.get("view_key") or "")
        return ""

    def world_name_for_view(self, view: dict[str, Any]) -> str:
        name = str(view.get("name") or "")
        if self.normalize_world_name(name).startswith("monde des douze"):
            return DEFAULT_WORLD_NAME
        for world in self.world_buttons:
            if self.normalize_world_name(world) == self.normalize_world_name(name):
                return world
        return name or self.current_world_name

    def display_context_for_view(self, view: dict[str, Any]) -> str:
        name = str(view.get("name") or "")
        if self.normalize_world_name(name).startswith("monde des douze"):
            return DEFAULT_WORLD_CONTEXT
        return self.breadcrumb_for(view)

    def display_context_for_world(self, world: str) -> str:
        if self.normalize_world_name(world) == "monde des douze":
            return DEFAULT_WORLD_CONTEXT
        return world

    def refresh_world_menu_state(self) -> None:
        current = self.normalize_world_name(self.current_world_name)
        for world, button in self.world_buttons.items():
            active = self.normalize_world_name(world) == current
            object_name = "WorldMenuItemActive" if active else "WorldMenuItem"
            if button.objectName() == object_name:
                continue
            button.setObjectName(object_name)
            button.style().unpolish(button)
            button.style().polish(button)

    def world_names_from_views(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        ignored_kinds = {"cave", "mine", "passage"}
        for view in self.views:
            if str(view.get("parent_view_key") or "").strip():
                continue
            kind = self.normalize_world_name(str(view.get("kind") or ""))
            if kind in ignored_kinds:
                continue
            raw_name = str(view.get("name") or view.get("view_key") or "").strip()
            if not raw_name:
                continue
            name = DEFAULT_WORLD_NAME if self.normalize_world_name(raw_name).startswith("monde des douze") else raw_name
            normalized = self.normalize_world_name(name)
            if normalized in seen:
                continue
            seen.add(normalized)
            names.append(name)
        return names or list(WORLD_NAMES)

    def rebuild_world_menu(self, names: list[str]) -> None:
        while self.world_menu_list.count():
            item = self.world_menu_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.world_buttons = {}
        for world in names:
            item = QPushButton(world)
            item.setObjectName("WorldMenuItem")
            item.setFixedHeight(28)
            item.setCursor(Qt.PointingHandCursor)
            item.clicked.connect(lambda _checked=False, name=world: self.on_world_selected(name))
            self.world_menu_list.addWidget(item)
            self.world_buttons[world] = item
            if world == DEFAULT_WORLD_NAME:
                divider = QFrame()
                divider.setObjectName("WorldMenuDivider")
                divider.setFixedHeight(1)
                self.world_menu_list.addWidget(divider)
        self.world_menu_list.addStretch(1)

    def normalize_world_name(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(text or ""))
        ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
        return ascii_text.replace("’", "'").strip().lower()

    def planet_icon(self) -> QIcon:
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor("#F2F6FF"), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QColor("#0B7F3D"))
        painter.drawEllipse(QRectF(5, 5, 30, 30))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(10, 5, 20, 30), 80 * 16, 200 * 16)
        painter.drawArc(QRectF(10, 5, 20, 30), -100 * 16, 200 * 16)
        painter.drawLine(5, 20, 35, 20)
        painter.drawArc(QRectF(7, 10, 26, 20), 0, 180 * 16)
        painter.drawArc(QRectF(7, 10, 26, 20), 180 * 16, 180 * 16)
        painter.end()
        return QIcon(pixmap)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.MouseButtonPress and self.world_menu.isVisible():
            global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            menu_rect = self.world_menu.rect().translated(self.world_menu.mapToGlobal(self.world_menu.rect().topLeft()))
            button_rect = self.planet_button.rect().translated(
                self.planet_button.mapToGlobal(self.planet_button.rect().topLeft())
            )
            if not menu_rect.contains(global_pos) and not button_rect.contains(global_pos):
                self.hide_world_menu()
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        deferred = self._deferred_load_result
        self._deferred_load_result = None
        if deferred is not None and int(deferred[0]) == self._load_generation:
            self._apply_cartography_payload(deferred[1])
        if self._initial_load_pending and not self._load_in_flight:
            self.reload_all()

    def hideEvent(self, event) -> None:
        self.hide_world_menu()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.world_menu.isVisible():
            self.update_world_menu_geometry()
