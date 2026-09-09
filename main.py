from __future__ import annotations

import ctypes
import os
import sys
from collections import deque
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from time import monotonic, sleep
from typing import Any, Callable
from weakref import WeakSet

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplashScreen,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.background_work import background_io_priority
from app.constants import (
    APP_NAME,
    CLIENT_INDEX_JSON,
    CRAFT_SELECTION_FILE,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    JOB_RESOURCE_GROUPS,
    KEY_SELECTED_CHARACTER,
    KEY_TOPMOST,
    LEVELING_FILE,
    LOGGER,
    log_uncaught_exception,
    LOGO_PATH,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
    QUEST_PROGRESS_FILE,
)
from app.core.runtime_state import AtlasRuntime
from app.network.character_runtime_state import character_runtime_state
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import (
    ACHIEVEMENT_PROGRESS_FILE,
    GUIDE_PROGRESS_FILE,
    AchievementProgressService,
    GuideProgressCalculator,
    GuideProgressService,
    QuestGraphService,
    QuestProgressService,
    build_related_encyclopedia_data,
)
from app.modules.encyclopedia.views import EncyclopediaPage
from app.pages.character_page_modern import CharacterPage
from app.pages.craft_page import CraftPage
from app.pages.equipment_page import EquipmentPage
from app.pages.home_page import HomePage
from app.pages.organizer_page import OrganizerPage, class_icon_path_for_window_name
from app.preload import PreloadTask, StartupPreloader
from app.quest_catalog import (
    QuestCatalog,
    is_generic_dofus_client_name,
    load_quest_characters,
    normalize_text,
)
from app.services.character_data_service import CharacterDataService
from app.services.character_order_service import CharacterOrderService
from app.storage import default_profiles, item_id, normalize_key, read_json, write_json
from app.ui.components import AtlasButton, AtlasDialog, AtlasDialogHeader, AtlasPageTitle, atlas_application_icon
from app.ui.splash_image import clear_connected_dark_background
from app.ui.theme import atlas_stylesheet
from app.windows.unity_windows import enable_dpi_awareness

SPLASH_MIN_VISIBLE_SECONDS = 0.25
STARTUP_PRELOAD_DELAY_MS = 500
STARTUP_PRELOAD_TIMEOUT_SECONDS = 90.0
EQUIPMENT_PRELOAD_DELAY_MS = 0


def configure_windows_app_id() -> None:
    """Give the shell a stable Windows taskbar identity before Qt starts."""

    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "DofusAtlas.Desktop"
        )
    except (AttributeError, OSError):
        LOGGER.exception("Windows AppUserModelID impossible à configurer.")


def build_lookup_index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for field in ("name", "name_fr", "name_en"):
            key = normalize_key(item.get(field))
            if key:
                index.setdefault(key, item)
                for prefix in ("bois_de_", "bois_d_"):
                    if key.startswith(prefix):
                        index.setdefault(key.removeprefix(prefix), item)
    return index


def find_lookup_item(name: str, index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    key = normalize_key(name)
    if not key:
        return None
    item = index.get(key)
    if item is not None:
        return item

    # A fuzzy fallback is useful for aliases such as "Frene" vs "Bois de
    # Frene", but returning the first substring match made the result depend on
    # dictionary insertion order. Refuse ambiguity instead of silently choosing
    # the wrong craft/resource.
    matches: list[dict[str, Any]] = []
    seen_candidates: set[int] = set()
    for item_key, candidate in index.items():
        if key not in item_key and item_key not in key:
            continue
        marker = id(candidate)
        if marker in seen_candidates:
            continue
        seen_candidates.add(marker)
        matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def build_craft_preload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "items": [],
        "jobs": [],
        "guides": read_json(LEVELING_FILE, {"source": "gamosaurus", "offline_runtime": True, "guides": {}}),
        "selection": {},
        "lookup_items": [],
        "errors": [],
    }
    try:
        from local_dofus_data.compatibility_adapter import LocalCompatibilityAdapter

        adapter = LocalCompatibilityAdapter()
        try:
            payload["items"] = adapter.list_craft_items()
            payload["jobs"] = adapter.list_jobs()
            resource_items = adapter.list_resources() if hasattr(adapter, "list_resources") else []
            lookup_index = build_lookup_index([*payload["items"], *resource_items])
            lookup_names = {"Ortie", "Frene", "Fer", "Ble", "Goujon", "Viande Fraiche"}
            for resource_group in JOB_RESOURCE_GROUPS.values():
                lookup_names.update(resource_name for resource_name, _tag in resource_group)
            lookup_items = []
            seen_lookup_ids = set()
            for name in sorted(lookup_names, key=normalize_key):
                item = find_lookup_item(name, lookup_index)
                if item is None:
                    try:
                        results = adapter.search_items(name, limit=1)
                    except Exception:
                        results = []
                    if not results:
                        continue
                    item = results[0]
                ident = item_id(item) or item.get("name")
                if ident in seen_lookup_ids:
                    continue
                seen_lookup_ids.add(ident)
                lookup_items.append(item)
            payload["lookup_items"] = lookup_items

            selection_payload = read_json(CRAFT_SELECTION_FILE, {"items": []})
            rows = selection_payload.get("items") if isinstance(selection_payload, dict) else []
            selection: dict[int, dict[str, Any]] = {}
            if isinstance(rows, list):
                for row in rows:
                    try:
                        ident = int(row.get("ankama_id") or row.get("item_id"))
                    except (AttributeError, TypeError, ValueError):
                        continue
                    item = adapter.get_item(ident)
                    if item:
                        selection[ident] = {"item": item, "quantity": max(1, int(row.get("quantity") or 1))}
            payload["selection"] = selection
        finally:
            adapter.close()
    except Exception as exc:
        payload["errors"].append(str(exc))
    return payload


def build_quest_related_preload(catalog: QuestCatalog | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "achievement_provider": None,
        "guide_provider": None,
        "quest_graph": None,
        "guide_progress_by_guide": None,
        "guide_progress_character_key": "",
        "errors": [],
    }
    if not isinstance(catalog, QuestCatalog):
        return payload
    try:
        related = build_related_encyclopedia_data(catalog)
        achievement_provider = related.achievement_provider
        guide_provider = related.guide_provider
        payload["quest_graph"] = related.quest_graph
        payload["achievement_provider"] = achievement_provider
        payload["guide_provider"] = guide_provider
        guide_progress, character_key = build_guide_progress_preload(catalog, guide_provider)
        payload["guide_progress_by_guide"] = guide_progress
        payload["guide_progress_character_key"] = character_key
    except Exception as exc:
        payload["errors"].append(str(exc))
    return payload


def build_guide_progress_preload(
    catalog: QuestCatalog,
    guide_provider: GuideProvider,
) -> tuple[dict[str, tuple[int, int, str]], str]:
    characters = load_quest_characters(
        PROFILE_FILE,
        CLIENT_INDEX_JSON,
        connected_only=True,
    )
    character_key = characters[0].key if characters else ""
    calculator = GuideProgressCalculator(
        QuestProgressService(QUEST_PROGRESS_FILE),
        GuideProgressService(GUIDE_PROGRESS_FILE),
        AchievementProgressService(ACHIEVEMENT_PROGRESS_FILE),
        catalog.by_id,
    )
    progress_by_guide: dict[str, tuple[int, int, str]] = {}
    for guide in guide_provider.load_all():
        progress = calculator.guide_progress(guide, character_key)
        progress_by_guide[guide.id] = (
            progress.completed,
            progress.total,
            guide_progress_state(progress.completed, progress.total),
        )
    return progress_by_guide, character_key


def guide_progress_state(completed: int, total: int) -> str:
    if total and completed >= total:
        return "Terminé"
    if completed > 0:
        return "En cours"
    return "Non commencé"


def build_quest_preload(
    owned_items: dict[int, dict[str, Any]] | None = None,
    include_related: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "catalog": None,
        "owned_items": owned_items or {},
        "achievement_provider": None,
        "guide_provider": None,
        "quest_graph": None,
        "guide_progress_by_guide": None,
        "guide_progress_character_key": "",
        "errors": [],
    }
    try:
        catalog = QuestCatalog.load()
        payload["catalog"] = catalog
        payload["achievement_provider"] = AchievementProvider(
            quest_provider=QuestProvider(catalog=catalog)
        )
        if include_related:
            related = build_quest_related_preload(catalog)
            payload.update({key: value for key, value in related.items() if key != "errors"})
            payload["errors"].extend(related.get("errors") or [])
    except Exception as exc:
        payload["errors"].append(str(exc))
    return payload


def build_preload_payload() -> dict[str, Any]:
    return {
        "quests": build_quest_preload(include_related=False),
    }


def splash_logo_pixmap() -> QPixmap:
    image = QImage(str(LOGO_PATH)).convertToFormat(QImage.Format_ARGB32)
    image = image.scaled(420, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        return QPixmap(str(LOGO_PATH)).scaled(420, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return QPixmap.fromImage(clear_connected_dark_background(image))


def keep_splash_visible(app: QApplication, started_at: float) -> None:
    while monotonic() - started_at < SPLASH_MIN_VISIBLE_SECONDS:
        app.processEvents()
        sleep(0.03)


def run_startup_preload(app: QApplication, splash: QSplashScreen | None = None) -> dict[str, Any]:
    def update_status(label: str) -> None:
        if splash is None:
            return
        splash.showMessage(
            f"Préchargement · {label}",
            Qt.AlignBottom | Qt.AlignCenter,
            QColor("#dbe5f2"),
        )
        splash.repaint()

    tasks = (
        PreloadTask(
            "Index des quêtes",
            lambda _payload: {"quests": build_quest_preload(include_related=False)},
        ),
    )
    report = StartupPreloader(
        app,
        logger=LOGGER,
        timeout_seconds=STARTUP_PRELOAD_TIMEOUT_SECONDS,
    ).run(tasks, status_callback=update_status)
    LOGGER.info(
        "[preload] data ready elapsed=%.3fs tasks=%s error=%r",
        report.elapsed_seconds,
        report.completed_tasks,
        report.error,
    )
    payload = dict(report.payload)
    if report.error:
        payload["_startup_error"] = report.error
    return payload


class HoverMenuButton(AtlasButton):
    """Menu de navigation au survol avec passage direct entre les boutons."""

    _instances: WeakSet["HoverMenuButton"] = WeakSet()
    _active_button: "HoverMenuButton | None" = None
    _POLL_MS = 25
    _CLOSE_GRACE_TICKS = 6

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("TopNavButton")
        self.setFocusPolicy(Qt.NoFocus)
        self._hover_menu: QMenu | None = None
        self._outside_ticks = 0
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_MS)
        self._poll_timer.timeout.connect(self._poll_cursor)
        HoverMenuButton._instances.add(self)

    def set_hover_menu(self, menu: QMenu) -> None:
        self._hover_menu = menu
        menu.aboutToHide.connect(self._menu_hidden)

    def enterEvent(self, event) -> None:
        self.open_hover_menu()
        super().enterEvent(event)

    def open_hover_menu(self) -> None:
        menu = self._hover_menu
        if menu is None:
            return

        previous = HoverMenuButton._active_button
        if previous is not None and previous is not self:
            previous.close_hover_menu()

        if menu.isVisible():
            self._outside_ticks = 0
            return

        HoverMenuButton._active_button = self
        self._outside_ticks = 0
        self.setDown(False)
        self.clearFocus()
        menu.popup(self.mapToGlobal(QPoint(0, self.height())))
        if not self._poll_timer.isActive():
            self._poll_timer.start()

    def close_hover_menu(self) -> None:
        self._poll_timer.stop()
        self._outside_ticks = 0
        menu = self._hover_menu
        if menu is not None and menu.isVisible():
            menu.close()
        self.setDown(False)
        self.clearFocus()
        if HoverMenuButton._active_button is self:
            HoverMenuButton._active_button = None
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _menu_hidden(self) -> None:
        self._poll_timer.stop()
        self._outside_ticks = 0
        self.setDown(False)
        self.clearFocus()
        if HoverMenuButton._active_button is self:
            HoverMenuButton._active_button = None
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    @staticmethod
    def _contains_global(widget: QWidget, pos) -> bool:
        return widget.isVisible() and widget.rect().contains(widget.mapFromGlobal(pos))

    @classmethod
    def _button_under_cursor(cls, pos) -> "HoverMenuButton | None":
        for button in tuple(cls._instances):
            if cls._contains_global(button, pos):
                return button
        return None

    def _poll_cursor(self) -> None:
        menu = self._hover_menu
        if menu is None or not menu.isVisible():
            self._menu_hidden()
            return

        from PySide6.QtGui import QCursor
        pos = QCursor.pos()

        # QMenu est une popup et capte la souris : on détecte directement
        # la position globale pour passer d'un bouton de menu au suivant.
        other = self._button_under_cursor(pos)
        if other is not None and other is not self:
            self.close_hover_menu()
            QTimer.singleShot(0, other.open_hover_menu)
            return

        if self._contains_global(self, pos) or self._contains_global(menu, pos):
            self._outside_ticks = 0
            return

        self._outside_ticks += 1
        if self._outside_ticks >= self._CLOSE_GRACE_TICKS:
            self.close_hover_menu()


class CloseActionDialog(AtlasDialog):
    """Themed shell dialog used when the main window is closed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CloseActionDialog")
        self.setWindowTitle("Fermer Dofus Atlas")
        self.setWindowIcon(atlas_application_icon())
        self.setMinimumWidth(470)
        self._selected_action = "cancel"

        self.content_layout.addWidget(
            AtlasDialogHeader(
                "Fermer Dofus Atlas ?",
                "Choisis si l'application doit rester disponible en arrière-plan.",
                icon=atlas_application_icon(),
                parent=self,
            )
        )

        body = QLabel(
            "Réduire conserve Dofus Atlas dans la zone de notification. "
            "Quitter arrête complètement l'application et ses services."
        )
        body.setObjectName("DialogBody")
        body.setWordWrap(True)
        self.content_layout.addWidget(body)

        divider = QFrame()
        divider.setObjectName("DialogDivider")
        divider.setFrameShape(QFrame.HLine)
        self.content_layout.addWidget(divider)

        actions = QWidget()
        actions.setObjectName("DialogActions")
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        cancel_button = AtlasButton("Annuler", variant="secondary")
        cancel_button.clicked.connect(self.reject)
        actions_layout.addWidget(cancel_button)
        actions_layout.addStretch(1)

        quit_button = AtlasButton("Quitter", variant="danger")
        quit_button.clicked.connect(lambda: self._finish("quit"))
        actions_layout.addWidget(quit_button)

        reduce_button = AtlasButton("Réduire", variant="primary")
        reduce_button.setDefault(True)
        reduce_button.clicked.connect(lambda: self._finish("minimize"))
        actions_layout.addWidget(reduce_button)
        self.content_layout.addWidget(actions)

    def _finish(self, action: str) -> None:
        self._selected_action = action
        self.accept()

    def selected_action(self) -> str:
        if self.exec() != QDialog.Accepted:
            return "cancel"
        return self._selected_action


class AtlasWindow(QMainWindow):
    def __init__(self, initial_preload: dict[str, Any] | None = None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.shell_icon = atlas_application_icon()
        self.setWindowIcon(self.shell_icon)

        self.runtime = AtlasRuntime(self.set_status, self.update_runtime_badge)
        self.nav_buttons: list[tuple[QPushButton, str]] = []
        self.page_nav_group = {
            "Organizer": "Organizer",
            "Quetes": "Encyclopédie",
            "Scan Monde": "Outils",
            "Craft": "Outils",
            "Equipement": "Stuffs",
            "Almanax": "Almanax",
        }
        self.page_indexes: dict[str, int] = {}
        self.page_widgets: dict[str, QWidget] = {}
        self.page_factories: dict[str, Any] = {}
        self.preload_results: dict[str, Any] = dict(initial_preload) if isinstance(initial_preload, dict) else {}
        self.preload_started = False
        self.preload_finished = bool(initial_preload)
        self.pending_page_name = ""
        self.pending_encyclopedia_tab = ""
        self.pending_guide_target: tuple[str, int | None] | None = None
        self.preload_queue: Queue[dict[str, Any]] = Queue(maxsize=4)
        self.preload_poll_timer = QTimer(self)
        self.preload_poll_timer.setInterval(120)
        self.preload_poll_timer.timeout.connect(self.collect_preload_result)
        self.last_status_text = ""
        profiles = read_json(PROFILE_FILE, default_profiles())
        self.topmost_enabled = bool(profiles.get(KEY_TOPMOST, False)) if isinstance(profiles, dict) else False
        self.current_character_key = str(profiles.get(KEY_SELECTED_CHARACTER, "") or "") if isinstance(profiles, dict) else ""
        self.current_character_label = ""
        self.characters = []
        self.quit_requested = False
        self.close_prompt_visible = False
        self.tray_icon: QSystemTrayIcon | None = None
        self._background_services_stopped = False
        self._last_active_dofus_hwnd = 0

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        self.pages: list[tuple[str, QWidget]] = []

        self.home_page = HomePage()
        self.home_page.continueRequested.connect(self.open_guide_progress)
        self.home_page.changeCharacterRequested.connect(self.open_character_selector)
        self.home_page.network_bridge.characterActivated.connect(
            self.on_network_character_activated
        )
        self.home_page.network_bridge.progressChanged.connect(self.on_network_progress_changed)
        self.register_page("Home", self.home_page)

        self.register_page(
            "Organizer",
            OrganizerPage(
                self.set_status,
                self.reload_runtime,
                self.stop_runtime,
                self.launch_auto_group,
                self.launch_travel,
                self.launch_zaap,
                sessions_changed_callback=self.refresh_global_characters,
                active_session_callback=self.on_organizer_active_window,
            ),
        )
        self.register_page("Scan Monde", self.loading_page("Scan Monde"))
        self.register_page("Craft", self.loading_page("Craft"))
        self.register_page("Quetes", self.loading_page("Encyclopédie"))
        self.register_page("Equipement", self.loading_page("Équipement"))
        self.register_page("Almanax", self.placeholder_page("Almanax", "Le module Almanax sera intégré ici.", badge="En travaux"))
        self.register_page("Settings", self.create_settings_page())

        self.page_factories["Scan Monde"] = self.create_world_scan_page
        self.page_factories["Craft"] = self.create_craft_page
        self.page_factories["Quetes"] = self.create_encyclopedia_page
        self.page_factories["Equipement"] = self.create_equipment_page

        self.top_nav = self.build_top_nav()
        root.addWidget(self.top_nav)

        self.module_subnav = QFrame()
        self.module_subnav.setObjectName("ModuleSubNav")
        self.module_subnav_layout = QHBoxLayout(self.module_subnav)
        self.module_subnav_layout.setContentsMargins(10, 4, 10, 4)
        self.module_subnav_layout.setSpacing(4)
        self.module_subnav.setVisible(False)
        root.addWidget(self.module_subnav)

        root.addWidget(self.stack, 1)

        self.refresh_global_characters()
        if self.preload_results:
            self.hydrate_preloaded_pages()
        self.stack.setCurrentWidget(self.home_page)

        self.apply_style()
        self._schedule_owned_callback(0, self.setup_tray)
        self.update_topmost_button()
        self.refresh_nav_selection("")
        if self.topmost_enabled:
            self._schedule_owned_callback(0, lambda: self.set_topmost(True))
        self._schedule_owned_callback(0, self.start_runtime)
        if os.environ.get("QT_QPA_PLATFORM", "").strip().casefold() != "offscreen":
            self._schedule_owned_callback(0, self.prepare_network_capture)
        if EQUIPMENT_PRELOAD_DELAY_MS > 0:
            self._schedule_owned_callback(EQUIPMENT_PRELOAD_DELAY_MS, self.preload_equipment_page)
        if not self.preload_finished:
            self._schedule_owned_callback(STARTUP_PRELOAD_DELAY_MS, self.start_preload)

    def _schedule_owned_callback(self, delay_ms: int, callback: Callable[[], None]) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.timeout.connect(timer.deleteLater)
        timer.start(max(0, int(delay_ms)))

    def build_top_nav(self) -> QFrame:
        nav = QFrame()
        nav.setObjectName("TopNav")
        layout = QHBoxLayout(nav)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        self.brand_button = AtlasButton("")
        self.brand_button.setObjectName("TopNavBrand")
        self.brand_button.setIcon(self.shell_icon)
        self.brand_button.setIconSize(QSize(0, 0))
        self.brand_button.setMinimumWidth(170)
        self.brand_button.setCursor(Qt.PointingHandCursor)
        brand_layout = QHBoxLayout(self.brand_button)
        brand_layout.setContentsMargins(8, 0, 8, 0)
        brand_layout.setSpacing(8)
        self.brand_icon_label = QLabel()
        self.brand_icon_label.setObjectName("TopNavBrandIcon")
        self.brand_icon_label.setFixedSize(32, 32)
        self.brand_icon_label.setAlignment(Qt.AlignCenter)
        self.brand_icon_label.setPixmap(self.shell_icon.pixmap(QSize(30, 30)))
        self.brand_icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        brand_layout.addWidget(self.brand_icon_label)
        brand_text = QLabel(APP_NAME)
        brand_text.setObjectName("TopNavBrandText")
        brand_text.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        brand_layout.addWidget(brand_text, 1)
        self.brand_button.clicked.connect(lambda: self.show_page("Home"))
        layout.addWidget(self.brand_button)
        layout.addSpacing(8)

        organizer = AtlasButton("Organizer")
        organizer.setObjectName("TopNavButton")
        organizer.clicked.connect(lambda: self.show_page("Organizer"))
        layout.addWidget(organizer)
        self.nav_buttons.append((organizer, "Organizer"))

        encyclopedia_menu = QMenu(nav)
        encyclopedia_menu.addAction(
            "Guide",
            lambda: self.open_encyclopedia_tab(GUIDES_TAB),
        )
        encyclopedia_menu.addAction(
            "Quêtes",
            lambda: self.open_encyclopedia_tab(QUESTS_TAB),
        )
        encyclopedia_menu.addAction(
            "Succès",
            lambda: self.open_encyclopedia_tab(ACHIEVEMENTS_TAB),
        )

        encyclopedia = HoverMenuButton("Encyclopédie")
        encyclopedia.set_hover_menu(encyclopedia_menu)
        encyclopedia.clicked.connect(
            lambda: self.open_encyclopedia_tab(GUIDES_TAB)
        )
        layout.addWidget(encyclopedia)
        self.nav_buttons.append((encyclopedia, "Encyclopédie"))

        bestiary_menu = QMenu(nav)
        bestiary_menu.addAction("Donjons", lambda: self.open_encyclopedia_tab("DONJONS"))
        bestiary_menu.addAction("Monstres", lambda: self.open_encyclopedia_tab("MONSTRES"))
        bestiary_menu.addAction("Archimonstres", lambda: self.open_encyclopedia_tab("ARCHIMONSTRES"))
        bestiary_menu.addAction("Avis de recherche", lambda: self.open_encyclopedia_tab("AVIS DE RECHERCHE"))

        bestiary = HoverMenuButton("Bestiaire")
        bestiary.set_hover_menu(bestiary_menu)
        bestiary.clicked.connect(lambda: self.open_encyclopedia_tab("DONJONS"))
        layout.addWidget(bestiary)
        self.nav_buttons.append((bestiary, "Bestiaire"))

        tools_menu = QMenu(nav)
        tools_menu.addAction("Crafts", lambda: self.open_tools_tab("Crafts"))
        tools_menu.addAction("Map monde", lambda: self.open_tools_tab("Map monde"))
        tools_menu.addAction("Chasse au trésor", lambda: self.open_tools_tab("Chasse au trésor"))
        tools_menu.addAction("Ocre", lambda: self.open_tools_tab("Ocre"))

        tools = HoverMenuButton("Outils")
        tools.set_hover_menu(tools_menu)
        tools.clicked.connect(lambda: self.open_tools_tab("Crafts"))
        layout.addWidget(tools)
        self.nav_buttons.append((tools, "Outils"))

        stuffs_menu = QMenu(nav)
        stuffs_menu.addAction("PvM", lambda: self.open_stuffs_tab("PvM"))
        stuffs_menu.addAction("PvP", lambda: self.open_stuffs_tab("PvP"))
        stuffs_menu.addAction("Builders", lambda: self.open_stuffs_tab("Builders"))

        stuffs = HoverMenuButton("Stuffs")
        stuffs.set_hover_menu(stuffs_menu)
        stuffs.clicked.connect(lambda: self.open_stuffs_tab("PvM"))
        layout.addWidget(stuffs)
        self.nav_buttons.append((stuffs, "Stuffs"))

        almanax = AtlasButton("Almanax")
        almanax.setObjectName("TopNavButton")
        almanax.clicked.connect(lambda: self.show_page("Almanax"))
        layout.addWidget(almanax)
        self.nav_buttons.append((almanax, "Almanax"))

        tutorials_menu = QMenu(nav)
        tutorials_menu.addAction("Dofus Noob", lambda: self.show_placeholder("Dofus Noob", "L'intégration des tutoriels Dofus Noob sera ajoutée ici.", "Tutoriels"))
        tutorials = HoverMenuButton("Tutoriels")
        tutorials.set_hover_menu(tutorials_menu)
        tutorials.clicked.connect(lambda: self.show_placeholder("Tutoriels", "Les tutoriels seront intégrés ici.", "Tutoriels"))
        layout.addWidget(tutorials)
        self.nav_buttons.append((tutorials, "Tutoriels"))

        layout.addStretch(1)

        self.character_combo = QComboBox()
        self.character_combo.setObjectName("TopNavCharacterCombo")
        self.character_combo.setMinimumWidth(150)
        self.character_combo.setMaximumWidth(210)
        self.character_combo.setToolTip("Personnage actif")
        self.character_combo.currentIndexChanged.connect(self.on_global_character_changed)
        layout.addWidget(self.character_combo)

        self.settings_button = AtlasButton("⚙")
        self.settings_button.setObjectName("TopNavSettings")
        self.settings_button.setFixedSize(34, 34)
        self.settings_button.setToolTip("Paramètres")
        self.settings_button.clicked.connect(lambda: self.show_page("Settings"))
        layout.addWidget(self.settings_button)
        return nav

    def refresh_global_characters(self) -> None:
        previous_key = str(self.current_character_key or "")
        known_characters = self._known_characters()
        connected_characters = self._connected_characters(known_characters)
        known_by_key = {character.key: character for character in known_characters}
        self.characters = connected_characters

        selected_index = next(
            (
                index
                for index, character in enumerate(connected_characters)
                if character.key == previous_key
            ),
            -1,
        )

        previous_blocked = self.character_combo.blockSignals(True)
        try:
            self.character_combo.clear()
            for character in connected_characters:
                icon_path = self.character_icon_path(character.label)
                icon = QIcon(icon_path) if icon_path else QIcon()
                self.character_combo.addItem(icon, character.label, character)
                self.character_combo.setItemData(
                    self.character_combo.count() - 1,
                    character.label,
                    Qt.ToolTipRole,
                )

            if selected_index >= 0:
                self.character_combo.setCurrentIndex(selected_index)
                selected = connected_characters[selected_index]
                self.current_character_key = selected.key
                self.current_character_label = selected.label
            elif previous_key in known_by_key:
                selected = known_by_key[previous_key]
                self.character_combo.setCurrentIndex(-1)
                self.current_character_key = selected.key
                self.current_character_label = selected.label
            elif connected_characters:
                self.character_combo.setCurrentIndex(0)
                selected = connected_characters[0]
                self.current_character_key = selected.key
                self.current_character_label = selected.label
            else:
                self.character_combo.setCurrentIndex(-1)
                self.current_character_key = ""
                self.current_character_label = "Aucun personnage connecté"
        finally:
            self.character_combo.blockSignals(previous_blocked)

        self.persist_selected_character()
        self.home_page.set_character(
            self.current_character_key,
            self.current_character_label,
            self.character_icon_path(self.current_character_label),
        )
        self.sync_selected_character_to_pages()
        self._refresh_runtime_hotkeys_for_client_mapping()

    @staticmethod
    def _ordered_characters(characters: list[Any]) -> list[Any]:
        return list(
            CharacterOrderService().sort_rows(
                tuple(characters),
                label_getter=lambda row: row.label,
            )
        )

    def _known_characters(self) -> list[Any]:
        return self._ordered_characters(
            load_quest_characters(
                PROFILE_FILE,
                CLIENT_INDEX_JSON,
                binding_path=NETWORK_CHARACTER_BINDINGS_FILE,
                connected_only=False,
            )
        )

    def _connected_characters(self, known_characters: list[Any]) -> list[Any]:
        runtime_store = character_runtime_state()
        runtime_keys = {
            character.key
            for character in known_characters
            if (snapshot := runtime_store.snapshot(character.key)) is not None
            and snapshot.connected
        }

        payload = read_json(CLIENT_INDEX_JSON, {})
        clients = payload.get("clients", []) if isinstance(payload, dict) else []
        named_clients: set[str] = set()
        for client in clients if isinstance(clients, list) else ():
            if not isinstance(client, dict):
                continue
            name = str(client.get("character_name") or client.get("name") or "").strip()
            if not name or is_generic_dofus_client_name(name):
                continue
            normalized = normalize_text(name)
            if normalized:
                named_clients.add(normalized)

        connected: list[Any] = []
        for character in known_characters:
            if (
                character.key not in runtime_keys
                and normalize_text(character.label) not in named_clients
            ):
                continue
            character.connected = True
            connected.append(character)
        return self._ordered_characters(connected)

    def character_icon_path(self, label: str) -> str:
        try:
            path = class_icon_path_for_window_name(label)
        except Exception:
            path = None
        if path is not None and path.exists():
            return str(path)
        return str(LOGO_PATH) if LOGO_PATH.exists() else ""

    def on_global_character_changed(self) -> None:
        character = self.character_combo.currentData()
        if character is None:
            return
        key = str(getattr(character, "key", "") or "")
        if not key:
            return
        label = str(getattr(character, "label", "Personnage") or "Personnage")
        if key == self.current_character_key and label == self.current_character_label:
            return
        self.current_character_key = key
        self.current_character_label = label
        self.persist_selected_character()
        self.home_page.set_character(key, label, self.character_icon_path(label))
        self.sync_selected_character_to_pages()

    def on_network_progress_changed(self, character_key: str) -> None:
        from app.ui.network_bridge import refresh_visible_encyclopedia_widgets

        page = self.page_widgets.get("Quetes")
        if page is not None:
            refresh_visible_encyclopedia_widgets((page,), character_key)

    def on_network_character_activated(self, character_key: str) -> None:
        """Refresh learned profiles and display the intended Dofus client."""

        target = str(character_key or "").strip()
        if not target:
            return
        self.refresh_global_characters()

        # Network traffic from several clients is interleaved. The Organizer
        # favorite wins when set; otherwise follow the last Dofus window brought
        # to the foreground. A single connected client is an unambiguous final
        # fallback for in-client character changes.
        index_payload = read_json(CLIENT_INDEX_JSON, {})
        clients = index_payload.get("clients", []) if isinstance(index_payload, dict) else []
        clients = [client for client in clients if isinstance(client, dict)]
        favorite_clients = [client for client in clients if bool(client.get("primary"))]
        selected_client = favorite_clients[0] if len(favorite_clients) == 1 else None
        if selected_client is None and self._last_active_dofus_hwnd > 0:
            active_clients = [
                client
                for client in clients
                if int(client.get("handle") or 0) == self._last_active_dofus_hwnd
            ]
            selected_client = active_clients[0] if len(active_clients) == 1 else None
        if selected_client is None and len(clients) == 1:
            selected_client = clients[0]

        preferred_name = str(
            (selected_client or {}).get("character_name")
            or (selected_client or {}).get("name")
            or ""
        ).strip()
        if not preferred_name:
            return
        preferred_key = normalize_key(preferred_name)
        matches = [
            index
            for index in range(self.character_combo.count())
            if normalize_key(self.character_combo.itemText(index)) == preferred_key
        ]
        if len(matches) != 1:
            return
        self.character_combo.setCurrentIndex(matches[0])
        if self.current_character_key != str(
            getattr(self.character_combo.currentData(), "key", "") or ""
        ):
            self.on_global_character_changed()

    def prepare_network_capture(self) -> None:
        """Request UAC as soon as the visible shell enters its event loop."""

        bridge = getattr(self.home_page, "network_bridge", None)
        prepare = getattr(bridge, "prepare_capture", None)
        if callable(prepare):
            prepare()

    def on_organizer_active_window(self, hwnd: int) -> None:
        """Remember the active Dofus client for no-favorite multi-account mode."""

        try:
            self._last_active_dofus_hwnd = max(0, int(hwnd))
        except (TypeError, ValueError, OverflowError):
            return
        self.refresh_global_characters()

    def persist_selected_character(self) -> None:
        profiles = read_json(PROFILE_FILE, default_profiles())
        if not isinstance(profiles, dict):
            profiles = default_profiles()
        profiles[KEY_SELECTED_CHARACTER] = self.current_character_key
        write_json(PROFILE_FILE, profiles)

    def sync_selected_character_to_pages(self) -> None:
        page = self.page_widgets.get("Quetes")
        if isinstance(page, EncyclopediaPage):
            page.refresh_characters()
            page.set_character_key(self.current_character_key)

        character_page = self.page_widgets.get("Personnage")
        if isinstance(character_page, CharacterPage):
            character_page.refresh_from_sources(self.current_character_key)

    def open_character_selector(self) -> None:
        page = self.page_widgets.get("Personnage")
        if not isinstance(page, CharacterPage):
            page = CharacterPage()
            page.characterSelected.connect(self._activate_character_from_page)
            page.characterDeleteRequested.connect(self._delete_character_from_page)
            page.characterOrderChanged.connect(self._apply_character_order_from_page)
            self.register_page("Personnage", page)
            self.page_nav_group["Personnage"] = ""
        page.refresh_from_sources(self.current_character_key)
        self.show_page("Personnage")

    def _activate_character_from_page(self, character_key: str) -> None:
        key = str(character_key or "").strip()
        if not key:
            return
        page = self.page_widgets.get("Personnage")
        if not isinstance(page, CharacterPage):
            return
        known = next((row for row in page.characters if row.key == key), None)
        if known is None:
            return

        matching_index = next(
            (
                index
                for index in range(self.character_combo.count())
                if str(getattr(self.character_combo.itemData(index), "key", "") or "") == key
            ),
            -1,
        )
        if matching_index >= 0:
            if self.character_combo.currentIndex() != matching_index:
                self.character_combo.setCurrentIndex(matching_index)
            else:
                self.on_global_character_changed()
        else:
            previous_blocked = self.character_combo.blockSignals(True)
            try:
                self.character_combo.setCurrentIndex(-1)
            finally:
                self.character_combo.blockSignals(previous_blocked)
            self.current_character_key = known.key
            self.current_character_label = known.label
            self.persist_selected_character()
            self.home_page.set_character(
                known.key,
                known.label,
                self.character_icon_path(known.label),
            )
            self.sync_selected_character_to_pages()
        page.refresh_from_sources(self.current_character_key)

    def _delete_character_from_page(self, character_key: str) -> None:
        key = str(character_key or "").strip()
        if not key:
            return
        CharacterDataService().delete_character(key)
        if self.current_character_key == key:
            self.current_character_key = ""
            self.current_character_label = ""
        self.refresh_global_characters()

    def _apply_character_order_from_page(self) -> None:
        client_index_exported = False
        organizer = self.page_widgets.get("Organizer")
        if organizer is not None:
            load_profiles = getattr(organizer, "load_profiles", None)
            apply_saved_order = getattr(organizer, "apply_saved_session_order", None)
            export_client_index = getattr(organizer, "export_client_index", None)
            request_render = getattr(organizer, "request_sessions_render", None)
            if all(
                callable(callback)
                for callback in (
                    load_profiles,
                    apply_saved_order,
                    export_client_index,
                    request_render,
                )
            ):
                existing_sessions = list(getattr(organizer, "sessions", []) or [])
                organizer.profiles = load_profiles()
                organizer.sessions = apply_saved_order(existing_sessions)
                export_client_index()
                client_index_exported = True
                request_render()
                sync_event_watcher = getattr(organizer, "sync_event_watcher_sessions", None)
                if callable(sync_event_watcher):
                    sync_event_watcher()

        self.refresh_global_characters()
        if client_index_exported:
            self._refresh_runtime_hotkeys_for_client_mapping(force_if_untracked=True)

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return 0

    def _runtime_client_mapping_signature(self) -> tuple[tuple[int, int, str], ...]:
        payload = read_json(CLIENT_INDEX_JSON, {})
        clients = payload.get("clients", []) if isinstance(payload, dict) else []
        if not isinstance(clients, list):
            return ()
        return tuple(
            (
                self._int_value(client.get("index")),
                self._int_value(client.get("handle")),
                str(client.get("binding") or "").strip().upper(),
            )
            for client in clients
            if isinstance(client, dict)
        )

    def _loaded_runtime_client_mapping_signature(self) -> tuple[tuple[int, int, str], ...]:
        settings = getattr(self.runtime, "settings", None)
        clients = getattr(settings, "clients", ()) if settings is not None else ()
        return tuple(
            (
                self._int_value(getattr(client, "index", 0)),
                self._int_value(getattr(client, "handle", 0)),
                str(getattr(client, "binding", "") or "").strip().upper(),
            )
            for client in clients
        )

    def _refresh_runtime_hotkeys_for_client_mapping(
        self,
        *,
        force_if_untracked: bool = False,
    ) -> bool:
        desired = self._runtime_client_mapping_signature()
        if bool(getattr(self, "quit_requested", False)) or bool(
            getattr(self, "_background_services_stopped", False)
        ):
            return False
        runtime = getattr(self, "runtime", None)
        if runtime is None:
            return False

        marker_name = "_atlas_runtime_client_mapping_signature"
        running = getattr(runtime, "_running", None)
        if bool(getattr(runtime, "is_starting", False)):
            if getattr(self, marker_name, None) == desired:
                return False
            self._atlas_runtime_client_mapping_signature = desired
            start = getattr(runtime, "start", None)
            if callable(start):
                start()
                return True
            return False

        if running is True:
            if self._loaded_runtime_client_mapping_signature() == desired:
                self._atlas_runtime_client_mapping_signature = desired
                return False
            reload_hotkeys = getattr(runtime, "reload_hotkeys", None)
            if not callable(reload_hotkeys):
                return False
            reload_hotkeys(False)
            self._atlas_runtime_client_mapping_signature = desired
            return True

        if running is False:
            return False

        sentinel = object()
        previous = getattr(self, marker_name, sentinel)
        if previous is not sentinel and previous == desired:
            return False
        if previous is sentinel and not force_if_untracked:
            return False
        reload_hotkeys = getattr(runtime, "reload_hotkeys", None)
        if not callable(reload_hotkeys):
            return False
        reload_hotkeys(False)
        self._atlas_runtime_client_mapping_signature = desired
        return True

    def open_encyclopedia_tab(self, tab_label: str) -> None:
        label = str(tab_label or QUESTS_TAB)

        guide_tabs = {
            GUIDES_TAB,
            QUESTS_TAB,
            ACHIEVEMENTS_TAB,
        }
        bestiary_tabs = {
            "DONJONS",
            "MONSTRES",
            "ARCHIMONSTRES",
            "AVIS DE RECHERCHE",
        }

        if label in guide_tabs:
            self.page_nav_group["Quetes"] = "Encyclopédie"
        elif label in bestiary_tabs:
            self.page_nav_group["Quetes"] = "Bestiaire"

        self.pending_encyclopedia_tab = label
        self.show_page("Quetes")
        self._schedule_owned_callback(0, self.finish_pending_encyclopedia_tab)

    def finish_pending_encyclopedia_tab(self) -> None:
        label = str(getattr(self, "pending_encyclopedia_tab", "") or "")
        if not label:
            return

        page = self.page_widgets.get("Quetes")
        if not isinstance(page, EncyclopediaPage):
            return

        page.set_character_key(self.current_character_key)

        labels = page.tab_labels()
        if label not in labels:
            self.pending_encyclopedia_tab = ""
            return

        guide_tabs = {
            GUIDES_TAB,
            QUESTS_TAB,
            ACHIEVEMENTS_TAB,
        }

        bestiary_tabs = {
            "DONJONS",
            "MONSTRES",
            "ARCHIMONSTRES",
            "AVIS DE RECHERCHE",
        }

        target_index = labels.index(label)
        tab_bar = page.tabs.tabBar()

        # Hiding the selected tab can synchronously emit currentChanged. Apply
        # visibility and selection atomically, then activate only the target.
        was_blocked = page.tabs.blockSignals(True)
        try:
            for index, tab_name in enumerate(labels):
                if label in guide_tabs:
                    tab_bar.setTabVisible(index, tab_name in guide_tabs)
                elif label in bestiary_tabs:
                    tab_bar.setTabVisible(index, tab_name in bestiary_tabs)
                else:
                    tab_bar.setTabVisible(index, True)
            page.tabs.setCurrentIndex(target_index)
        finally:
            page.tabs.blockSignals(was_blocked)

        # Clear before the lazy handler can replace a placeholder or schedule a
        # callback, so an older request cannot be replayed.
        self.pending_encyclopedia_tab = ""
        page.on_tab_changed(target_index)

        # Lazy materialization may move the requested label. Restore the visual
        # selection without invoking the handler a second time.
        refreshed_labels = page.tab_labels()
        if label in refreshed_labels:
            final_index = refreshed_labels.index(label)
            if page.tabs.currentIndex() != final_index:
                was_blocked = page.tabs.blockSignals(True)
                try:
                    page.tabs.setCurrentIndex(final_index)
                finally:
                    page.tabs.blockSignals(was_blocked)

        active_group = self.page_nav_group.get("Quetes", "")
        self.refresh_nav_selection(active_group)

    def open_guide_progress(self, guide_id: str, quest_id: object = None) -> None:
        resolved_quest: int | None = None
        try:
            if quest_id is not None:
                resolved_quest = int(quest_id)
        except (TypeError, ValueError):
            resolved_quest = None
        self.pending_guide_target = (str(guide_id), resolved_quest)
        self.show_page("Quetes")
        self._schedule_owned_callback(0, self.finish_pending_guide_target)

    def finish_pending_guide_target(self) -> None:
        target = self.pending_guide_target
        if target is None:
            return
        page = self.page_widgets.get("Quetes")
        if not isinstance(page, EncyclopediaPage):
            return
        if not getattr(page, "_related_ready", False):
            page.request_related_preload(GUIDES_TAB)
            self._schedule_owned_callback(160, self.finish_pending_guide_target)
            return
        page.set_character_key(self.current_character_key)
        guides = page.ensure_guides_view()
        labels = page.tab_labels()
        if GUIDES_TAB in labels:
            page.tabs.setCurrentIndex(labels.index(GUIDES_TAB))
        guide_id, quest_id = target
        if not guides.select_guide(guide_id):
            self.pending_guide_target = None
            return
        if quest_id is not None:
            guides.show_quest_detail(quest_id)
        self.pending_guide_target = None

    def clear_module_subnav(self) -> None:
        if not hasattr(self, "module_subnav_layout"):
            return

        while self.module_subnav_layout.count():
            item = self.module_subnav_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def configure_module_subnav(
        self,
        group: str,
        labels: tuple[str, ...],
        active_label: str,
        callback,
    ) -> None:
        self.clear_module_subnav()

        for label in labels:
            button = AtlasButton(label)
            button.setObjectName(
                "TopNavButtonActive"
                if label == active_label
                else "TopNavButton"
            )
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, value=label: callback(value)
            )
            self.module_subnav_layout.addWidget(button)

        self.module_subnav_layout.addStretch(1)
        self.module_subnav.setVisible(True)
        self.refresh_nav_selection(group)

    def hide_module_subnav(self) -> None:
        if hasattr(self, "module_subnav"):
            self.module_subnav.setVisible(False)

    def open_tools_tab(self, label: str) -> None:
        labels = (
            "Crafts",
            "Map monde",
            "Chasse au trésor",
            "Ocre",
        )

        self.configure_module_subnav(
            "Outils",
            labels,
            label,
            self.open_tools_tab,
        )

        if label == "Crafts":
            self.page_nav_group["Craft"] = "Outils"
            self.show_page("Craft")
            return

        if label == "Map monde":
            self.page_nav_group["Scan Monde"] = "Outils"
            self.show_page("Scan Monde")
            return

        if label == "Chasse au trésor":
            self.show_placeholder(
                "Chasse au trésor",
                "Le module Chasse au trésor sera intégré ici.",
                "Outils",
            )
            return

        if label == "Ocre":
            self.show_placeholder(
                "Ocre",
                "Le module Ocre sera intégré ici.",
                "Outils",
            )

    def open_stuffs_tab(self, label: str) -> None:
        labels = (
            "PvM",
            "PvP",
            "Builders",
        )

        self.configure_module_subnav(
            "Stuffs",
            labels,
            label,
            self.open_stuffs_tab,
        )

        self.page_nav_group["Equipement"] = "Stuffs"

        page = self.ensure_page_loaded("Equipement")

        if page is not None:
            setter = getattr(page, "set_section", None)

            if callable(setter):
                setter(label)

        self.show_page("Equipement")

    def show_placeholder(self, title: str, message: str, group: str) -> None:
        name = f"Placeholder::{title}"
        if name not in self.page_widgets:
            self.register_page(name, self.placeholder_page(title, message, badge="En travaux"))
        self.page_nav_group[name] = group
        self.switch_to_page(name)

    def placeholder_page(self, title: str, message: str, badge: str = "") -> QWidget:
        page = QWidget()
        page.setObjectName("PlaceholderPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        heading = AtlasPageTitle(title)
        layout.addWidget(heading)
        if badge:
            state = QLabel(badge)
            state.setObjectName("HomePlaceholderBadge")
            layout.addWidget(state, 0, Qt.AlignLeft)
        text = QLabel(message)
        text.setObjectName("CompactLabel")
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addStretch(1)
        return page

    def create_settings_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("SettingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        title = AtlasPageTitle("Paramètres")
        layout.addWidget(title)
        self.settings_topmost_check = QCheckBox("Toujours au premier plan")
        self.settings_topmost_check.setChecked(self.topmost_enabled)
        self.settings_topmost_check.toggled.connect(self.set_topmost)
        layout.addWidget(self.settings_topmost_check)
        info = QLabel("Les autres paramètres seront regroupés ici progressivement.")
        info.setObjectName("MutedLabel")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch(1)
        return page

    def loading_page(self, name: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 6, 8, 8)
        title = AtlasPageTitle(name)
        layout.addWidget(title)
        label = QLabel("Préparation...")
        label.setObjectName("CompactLabel")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label, 1)
        return page

    def register_page(self, name: str, page: QWidget) -> int:
        index = self.stack.addWidget(page)
        self.page_indexes[name] = index
        self.page_widgets[name] = page
        self.pages.append((name, page))
        return index

    def show_page(self, name: str) -> None:
        if name == "Home":
            self.refresh_global_characters()
        if name in self.page_factories:
            self.pending_page_name = name
            self._schedule_owned_callback(0, lambda target=name: self.ensure_pending_page_loaded(target))
            return
        page = self.page_widgets.get(name)
        if page is not None and not self.page_ready_for_navigation(page):
            self.pending_page_name = name
            if not self.prepare_page_for_navigation(name, page):
                return
        self.pending_page_name = ""
        self.switch_to_page(name)

    def switch_to_page(self, name: str) -> None:
        group = self.page_nav_group.get(name, "")

        if group not in {"Outils", "Stuffs"}:
            self.hide_module_subnav()

        index = self.page_indexes.get(name)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        group = self.page_nav_group.get(name, "")
        self.refresh_nav_selection(group)
        if name == "Home":
            self.home_page.refresh_progress()
        elif name == "Quetes":
            page = self.page_widgets.get("Quetes")
            if isinstance(page, EncyclopediaPage):
                page.set_character_key(self.current_character_key)
            self._schedule_owned_callback(0, self.finish_pending_encyclopedia_tab)
            self._schedule_owned_callback(0, self.finish_pending_guide_target)

    def ensure_pending_page_loaded(self, name: str) -> QWidget | None:
        if self.pending_page_name != name:
            return None
        page = self.ensure_page_loaded(name)
        if page is None:
            return None
        if not self.page_ready_for_navigation(page):
            self.prepare_page_for_navigation(name, page)
            return None
        self.pending_page_name = ""
        self.switch_to_page(name)
        return page

    def ensure_active_page_loaded(self, name: str) -> QWidget | None:
        if self.active_page_name() != name:
            return None
        page = self.ensure_page_loaded(name)
        if page is not None:
            self.switch_to_page(name)
        return page

    def page_ready_for_navigation(self, page: QWidget) -> bool:
        ready = getattr(page, "is_navigation_ready", None)
        if callable(ready):
            return bool(ready())
        return True

    def prepare_page_for_navigation(self, name: str, page: QWidget) -> bool:
        prepare = getattr(page, "prepare_for_navigation", None)
        if not callable(prepare):
            return True
        return bool(prepare(lambda target=name: self.finish_pending_navigation(target)))

    def finish_pending_navigation(self, name: str) -> None:
        if self.pending_page_name != name:
            return
        page = self.page_widgets.get(name)
        if page is None or not self.page_ready_for_navigation(page):
            return
        self.pending_page_name = ""
        self.switch_to_page(name)

    def refresh_nav_selection(self, active_group: str) -> None:
        for button, group in self.nav_buttons:
            object_name = "TopNavButtonActive" if group == active_group and active_group else "TopNavButton"
            if button.objectName() == object_name:
                continue
            button.setObjectName(object_name)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def ensure_page_loaded(self, name: str) -> QWidget | None:
        factory = self.page_factories.get(name)
        if factory is None:
            return self.page_widgets.get(name)
        old_page = self.page_widgets.get(name)
        index = self.page_indexes.get(name, self.stack.count())
        page = factory()
        if page is None:
            return None
        self.page_factories.pop(name, None)
        self.stack.insertWidget(index, page)
        if old_page is not None and self.stack.currentWidget() is old_page:
            self.stack.setCurrentWidget(page)
        self.page_widgets[name] = page
        self.pages = [(page_name, page if page_name == name else widget) for page_name, widget in self.pages]
        if old_page is not None:
            self.stack.removeWidget(old_page)
            old_page.deleteLater()
        self.page_indexes = {page_name: self.stack.indexOf(widget) for page_name, widget in self.page_widgets.items()}
        return page

    def create_world_scan_page(self) -> QWidget:
        from app.ui.world_scan_panel import WorldScanPanel

        return WorldScanPanel(self.set_status)

    def create_craft_page(self) -> CraftPage | None:
        preload = self.preload_results.get("craft")
        if not isinstance(preload, dict) or not isinstance(preload.get("items"), list):
            self.start_preload(prefer_quests=False)
            self.set_status("Prechargement Items en cours...")
            return None
        self.preload_results.pop("craft", None)
        return CraftPage(self.set_status, preload=preload)

    def create_equipment_page(self) -> EquipmentPage:
        return EquipmentPage(self.set_status)

    def create_encyclopedia_page(self) -> EncyclopediaPage | None:
        preload = self.preload_results.get("quests")
        catalog = preload.get("catalog") if isinstance(preload, dict) else None
        owned_items = preload.get("owned_items") if isinstance(preload, dict) else None
        achievement_provider = preload.get("achievement_provider") if isinstance(preload, dict) else None
        guide_provider = preload.get("guide_provider") if isinstance(preload, dict) else None
        quest_graph = preload.get("quest_graph") if isinstance(preload, dict) else None
        guide_progress_by_guide = preload.get("guide_progress_by_guide") if isinstance(preload, dict) else None
        guide_progress_character_key = preload.get("guide_progress_character_key") if isinstance(preload, dict) else ""
        resolved_catalog = catalog if isinstance(catalog, QuestCatalog) else None
        quest_provider = (
            QuestProvider(catalog=resolved_catalog)
            if resolved_catalog is not None
            else QuestProvider()
        )
        resolved_achievement = (
            achievement_provider
            if isinstance(achievement_provider, AchievementProvider)
            and bool(getattr(achievement_provider, "_loaded", False))
            else None
        )
        resolved_guide = (
            guide_provider
            if isinstance(guide_provider, GuideProvider)
            and bool(getattr(guide_provider, "_loaded", False))
            else None
        )
        resolved_graph = quest_graph if isinstance(quest_graph, QuestGraphService) else None
        page = EncyclopediaPage(
            self.set_status,
            quest_provider=quest_provider,
            achievement_provider=resolved_achievement,
            guide_provider=resolved_guide,
            quest_graph=resolved_graph,
            guide_progress_by_guide=guide_progress_by_guide if isinstance(guide_progress_by_guide, dict) else None,
            guide_progress_character_key=str(guide_progress_character_key or ""),
            owned_items=owned_items if isinstance(owned_items, dict) else None,
            launch_travel_callback=self.launch_travel,
            related_data_ready_callback=self.on_encyclopedia_related_data_ready,
            initial_tab=self.pending_encyclopedia_tab or (GUIDES_TAB if self.pending_guide_target else QUESTS_TAB),
        )
        page.set_character_key(self.current_character_key)
        return page

    def on_encyclopedia_related_data_ready(
        self,
        achievement_provider: AchievementProvider,
        guide_provider: GuideProvider,
    ) -> None:
        quests = self.preload_results.get("quests")
        catalog = quests.get("catalog") if isinstance(quests, dict) else None
        if not isinstance(catalog, QuestCatalog):
            page = self.page_widgets.get("Quetes")
            if isinstance(page, EncyclopediaPage):
                catalog = page.quest_provider.get_catalog()
        self.home_page.apply_encyclopedia_context(
            catalog=catalog if isinstance(catalog, QuestCatalog) else None,
            achievement_provider=achievement_provider,
            guide_provider=guide_provider,
        )

    def hydrate_preloaded_pages(self) -> None:
        quests = self.preload_results.get("quests")
        if isinstance(quests, dict):
            self.apply_home_preload_update(quests)

    def active_page_name(self) -> str:
        current = self.stack.currentWidget()
        for name, widget in self.page_widgets.items():
            if widget is current:
                return name
        return ""

    def rebuild_page_indexes(self) -> None:
        self.page_indexes = {
            page_name: self.stack.indexOf(widget)
            for page_name, widget in self.page_widgets.items()
        }

    def start_preload(self, prefer_quests: bool = True) -> None:
        if prefer_quests:
            return
        if self.preload_started:
            return
        self.preload_started = True
        self.preload_finished = False

        def worker() -> None:
            with background_io_priority():
                try:
                    craft = build_craft_preload()
                    self.preload_queue.put({"craft": craft, "_complete": True})
                except Exception as exc:
                    LOGGER.exception("Préchargement asynchrone interrompu.")
                    self.preload_queue.put(
                        {
                            "craft": {"errors": [str(exc)]},
                            "_fatal_error": str(exc),
                            "_complete": True,
                        }
                    )

        Thread(target=worker, name="DofusAtlasPreload", daemon=True).start()
        self.preload_poll_timer.start()

    def collect_preload_result(self) -> None:
        handled = False
        complete = False
        fatal_error = ""
        latest_result: dict[str, Any] = {}
        errors: list[str] = []
        while True:
            try:
                result = self.preload_queue.get_nowait()
            except Empty:
                break
            handled = True
            complete = bool(result.pop("_complete", True)) or complete
            fatal_error = str(result.pop("_fatal_error", "") or fatal_error)
            if "Craft" not in self.page_factories:
                result.pop("craft", None)
            encyclopedia_loaded = isinstance(self.page_widgets.get("Quetes"), EncyclopediaPage)
            if "Quetes" not in self.page_factories and not encyclopedia_loaded:
                result.pop("quests", None)
            self.merge_preload_result(result)
            quests = self.preload_results.get("quests")
            if isinstance(quests, dict):
                self.apply_home_preload_update(quests)
                self.apply_encyclopedia_preload_update(quests)
            craft = result.get("craft") if isinstance(result, dict) else {}
            quests = result.get("quests") if isinstance(result, dict) else {}
            if isinstance(craft, dict):
                errors.extend(craft.get("errors") or [])
            if isinstance(quests, dict):
                errors.extend(quests.get("errors") or [])
            latest_result = result
        if not handled:
            return
        if complete:
            self.preload_poll_timer.stop()
            self.preload_started = False
            if fatal_error:
                self.preload_finished = False
            else:
                self.preload_finished = True
        if fatal_error:
            self.set_status(f"Préchargement interrompu : {fatal_error}")
        elif errors:
            self.set_status("Prechargement partiel, certains modules resteront charges a la demande.")
        elif not complete:
            craft = latest_result.get("craft") if isinstance(latest_result, dict) else {}
            quests = latest_result.get("quests") if isinstance(latest_result, dict) else {}
            craft_count = len(craft.get("items", [])) if isinstance(craft, dict) else 0
            quest_catalog = quests.get("catalog") if isinstance(quests, dict) else None
            quest_count = len(quest_catalog.quests) if isinstance(quest_catalog, QuestCatalog) else 0
            self.set_status(f"Donnees pretes ({craft_count} crafts, {quest_count} quetes).")
        else:
            merged_craft = self.preload_results.get("craft")
            craft_count = len(merged_craft.get("items", [])) if isinstance(merged_craft, dict) else 0
            merged_quests = self.preload_results.get("quests")
            quest_catalog = merged_quests.get("catalog") if isinstance(merged_quests, dict) else None
            quest_count = len(quest_catalog.quests) if isinstance(quest_catalog, QuestCatalog) else 0
            page = self.page_widgets.get("Quetes")
            if quest_count == 0 and isinstance(page, EncyclopediaPage) and page.quest_page is not None:
                quest_count = len(page.quest_page.catalog.quests)
            if craft_count or quest_count:
                self.set_status(f"Prechargement pret ({craft_count} crafts, {quest_count} quetes).")
            else:
                self.set_status("Prechargement pret.")
        if not fatal_error:
            self.hydrate_active_preloaded_page()

    def merge_preload_result(self, result: dict[str, Any]) -> None:
        for key, value in result.items():
            current = self.preload_results.get(key)
            if isinstance(current, dict) and isinstance(value, dict):
                current.update(value)
            else:
                self.preload_results[key] = value

    def apply_home_preload_update(self, quests: dict[str, Any]) -> None:
        self.home_page.apply_encyclopedia_context(
            catalog=quests.get("catalog"),
            guide_provider=quests.get("guide_provider"),
            achievement_provider=quests.get("achievement_provider"),
        )

    def apply_encyclopedia_preload_update(self, quests: dict[str, Any]) -> None:
        page = self.page_widgets.get("Quetes")
        if not isinstance(page, EncyclopediaPage):
            return
        apply_update = getattr(page, "apply_preloaded_related_data", None)
        if callable(apply_update):
            apply_update(
                achievement_provider=quests.get("achievement_provider"),
                guide_provider=quests.get("guide_provider"),
                quest_graph=quests.get("quest_graph"),
                guide_progress_by_guide=quests.get("guide_progress_by_guide"),
                guide_progress_character_key=str(quests.get("guide_progress_character_key") or ""),
            )

    def hydrate_active_preloaded_page(self) -> None:
        if self.pending_page_name in self.page_factories:
            self._schedule_owned_callback(
                0,
                lambda target=self.pending_page_name: self.ensure_pending_page_loaded(target),
            )
            return
        active_name = self.active_page_name()
        if active_name in self.page_factories:
            self.ensure_page_loaded(active_name)

    def preload_equipment_page(self) -> None:
        if "Equipement" in self.page_factories:
            self.ensure_page_loaded("Equipement")
            return
        page = self.page_widgets.get("Equipement")
        if page is None or self.page_ready_for_navigation(page):
            return
        self.prepare_page_for_navigation("Equipement", page)

    def setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.shell_icon
        if icon.isNull():
            icon = self.windowIcon()
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip(APP_NAME)
        menu = QMenu()
        show_action = menu.addAction("Afficher")
        hide_action = menu.addAction("Masquer")
        quit_action = menu.addAction("Fermer")
        show_action.triggered.connect(self.restore_from_tray)
        hide_action.triggered.connect(self.hide_to_tray)
        quit_action.triggered.connect(self.quit_from_tray)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.restore_from_tray()

    def hide_to_tray(self) -> None:
        if self.tray_icon is None:
            self.showMinimized()
            self.set_status("Dofus Atlas reduit dans la barre des taches.")
            return
        self.hide()
        self.tray_icon.showMessage(APP_NAME, "Dofus Atlas reste actif ici.", QSystemTrayIcon.Information, 1200)
        self.set_status("Dofus Atlas reduit dans la zone de notification.")

    def restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_from_tray(self) -> None:
        self.quit_requested = True
        self.close()

    def apply_style(self) -> None:
        style = atlas_stylesheet()
        app = QApplication.instance()
        if app is not None:
            if app.styleSheet() != style:
                app.setStyleSheet(style)
            return
        self.setStyleSheet(style)

    def set_status(self, text: str) -> None:
        message = str(text or "").strip()
        if not message:
            return
        self.last_status_text = message
        LOGGER.info("[status] %s", message)
        important_tokens = (
            "erreur",
            "impossible",
            "indisponible",
            "partiel",
            "interrompu",
            "bloqu",
            "droits insuffisants",
            "aucune session",
        )
        if self.tray_icon is not None and any(token in message.casefold() for token in important_tokens):
            self.tray_icon.showMessage(APP_NAME, message, QSystemTrayIcon.Warning, 5000)

    def set_topmost(self, enabled: bool) -> None:
        self.topmost_enabled = bool(enabled)
        profiles = read_json(PROFILE_FILE, default_profiles())
        if not isinstance(profiles, dict):
            profiles = default_profiles()
        profiles[KEY_TOPMOST] = self.topmost_enabled
        write_json(PROFILE_FILE, profiles)
        self.apply_topmost_state(enabled)
        self.update_topmost_button()

    def apply_topmost_state(self, enabled: bool) -> None:
        if os.name == "nt":
            hwnd = int(self.winId())
            if hwnd:
                hwnd_topmost = -1
                hwnd_notopmost = -2
                swp_nosize = 0x0001
                swp_nomove = 0x0002
                swp_noactivate = 0x0010
                insert_after = hwnd_topmost if enabled else hwnd_notopmost
                ctypes.windll.user32.SetWindowPos(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_void_p(insert_after),
                    0,
                    0,
                    0,
                    0,
                    0,
                    swp_nosize | swp_nomove | swp_noactivate,
                )
                return
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        self.show()

    def update_topmost_button(self) -> None:
        if hasattr(self, "settings_topmost_check"):
            self.settings_topmost_check.blockSignals(True)
            self.settings_topmost_check.setChecked(self.topmost_enabled)
            self.settings_topmost_check.blockSignals(False)

    def update_runtime_badge(self, connected: bool) -> None:
        organizer = self.page_widgets.get("Organizer") if hasattr(self, "page_widgets") else None
        if hasattr(organizer, "set_runtime_active"):
            organizer.set_runtime_active(bool(connected))

    def start_runtime(self) -> None:
        if self.quit_requested or self._background_services_stopped:
            return
        self.runtime.start()

    def stop_runtime(self) -> None:
        # The Organizer button is an emergency *macro* stop. It deliberately
        # keeps keyboard/mouse hooks alive, so the runtime badge must keep
        # reflecting the real hook state instead of pretending the runtime died.
        self.runtime.emergency_stop("bouton stop")

    def refresh_runtime_sessions(self) -> None:
        organizer = self.page_widgets.get("Organizer") if hasattr(self, "page_widgets") else None
        if not hasattr(organizer, "refresh_sessions_and_export"):
            return
        try:
            organizer.refresh_sessions_and_export(render=True)
            self.refresh_global_characters()
        except Exception:
            LOGGER.exception("Refresh sessions avant runtime impossible.")

    def reload_runtime(self, force_restart: bool = False) -> None:
        if self.quit_requested or self._background_services_stopped:
            return
        self.refresh_runtime_sessions()
        if self.quit_requested or self._background_services_stopped:
            return
        if not getattr(self.runtime, "_running", False):
            self.runtime.start()
        else:
            self.runtime.reload_hotkeys(force_restart)

    def launch_travel(self, text: str) -> None:
        self.reload_runtime()
        self.runtime.launch_travel(text)

    def launch_zaap(self, text: str, click_position=None, click_ratios=None) -> None:
        self.reload_runtime()
        self.runtime.launch_zaap(text, click_position=click_position, click_ratios=click_ratios)

    def launch_auto_group(self, invite_entries: list[dict[str, object]]) -> None:
        self.reload_runtime()
        self.runtime.launch_auto_group(invite_entries)

    def _shutdown_background_services(self) -> None:
        if self._background_services_stopped:
            return
        self._background_services_stopped = True
        self.quit_requested = True

        organizer = self.page_widgets.get("Organizer") if hasattr(self, "page_widgets") else None
        stop_watcher = getattr(organizer, "stop_session_event_watcher", None)
        if callable(stop_watcher):
            try:
                stop_watcher()
            except RuntimeError:
                pass

        bridge = getattr(getattr(self, "home_page", None), "network_bridge", None)
        stop_bridge = getattr(bridge, "stop", None)
        if callable(stop_bridge):
            try:
                stop_bridge()
            except RuntimeError:
                pass

        self.runtime.stop()

    def ask_close_action(self) -> str:
        if self.close_prompt_visible:
            return "cancel"
        self.close_prompt_visible = True
        try:
            return CloseActionDialog(self).selected_action()
        finally:
            self.close_prompt_visible = False

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.quit_requested:
            action = self.ask_close_action()
            if action == "minimize":
                event.ignore()
                self.hide_to_tray()
                return
            if action != "quit":
                event.ignore()
                return
            self.quit_requested = True
        self._shutdown_background_services()
        event.accept()


def main() -> int:
    sys.excepthook = log_uncaught_exception
    LOGGER.info("[main] start argv=%s cwd=%s", sys.argv, Path.cwd())
    # DPI awareness must be established explicitly before QApplication is
    # created. Runtime modules must not be relied on for import-time OS effects.
    enable_dpi_awareness()
    configure_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(atlas_application_icon())
    splash = None
    splash_started_at = None
    if LOGO_PATH.exists():
        pixmap = splash_logo_pixmap()
        splash = QSplashScreen(pixmap, Qt.Window | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        splash.setAttribute(Qt.WA_TranslucentBackground, True)
        splash.setStyleSheet("background: transparent;")
        splash.setMask(pixmap.mask())
        splash.show()
        splash.raise_()
        splash.repaint()
        app.processEvents()
        splash_started_at = monotonic()
        LOGGER.info("[main] splash shown size=%sx%s", pixmap.width(), pixmap.height())
    if splash is not None:
        splash.showMessage(
            "Ouverture de l'interface...",
            Qt.AlignBottom | Qt.AlignCenter,
            QColor("#dbe5f2"),
        )
        app.processEvents()
    # Apply the global theme while the splash is already visible. Child widgets
    # created afterwards inherit it immediately, avoiding a full-tree repolish
    # at the end of AtlasWindow construction.
    app.setStyleSheet(atlas_stylesheet())
    # The shell already owns a terminal async preload path. Do not block the
    # first visible window waiting for the quest catalogue; AtlasWindow starts
    # that worker shortly after the UI has painted, or immediately on demand.
    initial_preload: dict[str, Any] = {}
    LOGGER.info("[preload] initial quest load deferred until window is visible")
    LOGGER.info("[main] creating AtlasWindow")
    window = AtlasWindow(initial_preload=initial_preload)
    LOGGER.info("[main] AtlasWindow created visible=%s title=%r", window.isVisible(), window.windowTitle())
    window.show()
    LOGGER.info("[main] AtlasWindow shown visible=%s title=%r", window.isVisible(), window.windowTitle())
    if splash is not None and splash_started_at is not None:
        keep_splash_visible(app, splash_started_at)
        splash.finish(window)
    result = app.exec()
    LOGGER.info("[main] app.exec finished result=%s", result)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
