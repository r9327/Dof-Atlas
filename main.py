from __future__ import annotations

import ctypes
import gc
import os
import sys
from collections import deque
from contextlib import nullcontext
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any, Callable
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
    DATA_DIR,
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
from app.logging_setup import configure_logging
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
from app.pages.home_page import HomePage
from app.preload import PreloadTask, StartupPreloader
from app.services.character_data_service import CharacterDataService
from app.services.character_order_service import CharacterOrderService
from app.storage import default_profiles, item_id, normalize_key, read_json, write_json
from app.ui.components import AtlasButton, AtlasDialog, AtlasDialogHeader, AtlasPageTitle, atlas_application_icon
from app.ui.preload_popup import PreloadProgressPopup
from app.ui.splash_image import clear_connected_dark_background
from app.ui.theme import atlas_stylesheet
from app.windows.unity_windows import enable_dpi_awareness
from app.windows.single_instance import SingleInstanceGuard

SPLASH_MIN_VISIBLE_SECONDS = 0.25
STARTUP_PRELOAD_DELAY_MS = 500
STARTUP_PRELOAD_TIMEOUT_SECONDS = 90.0
EQUIPMENT_PRELOAD_DELAY_MS = 0
POST_RENDER_TRAY_DELAY_MS = 75
POST_RENDER_RUNTIME_DELAY_MS = 150
POST_RENDER_NETWORK_DELAY_MS = 300
GLOBAL_QUEST_PRELOAD_DELAY_MS = 650
GLOBAL_CRAFT_PRELOAD_DELAY_MS = 2000

PRELOAD_IDLE = "IDLE"
PRELOAD_LOADING = "LOADING"
PRELOAD_READY = "READY"
PRELOAD_FAILED = "FAILED"

# Compatibility patch points used by a few focused tests. Runtime code resolves
# the concrete classes only on first use, keeping them out of the startup path.
CharacterPage: Any = None
CraftPage: Any = None
EncyclopediaPage: Any = None
EquipmentPage: Any = None
OrganizerPage: Any = None
QuestProvider: Any = None
load_quest_characters: Any = None

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


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


def _resolve_character_page() -> type:
    global CharacterPage
    if CharacterPage is None:
        from app.pages.character_page_modern import CharacterPage as resolved

        CharacterPage = resolved
    return CharacterPage


def _resolve_craft_page() -> type:
    global CraftPage
    if CraftPage is None:
        from app.pages.craft_page import CraftPage as resolved

        CraftPage = resolved
    return CraftPage


def _resolve_encyclopedia_page() -> type:
    global EncyclopediaPage
    if EncyclopediaPage is None:
        from app.modules.encyclopedia.views import EncyclopediaPage as resolved

        EncyclopediaPage = resolved
    return EncyclopediaPage


def _resolve_equipment_page() -> type:
    global EquipmentPage
    if EquipmentPage is None:
        from app.pages.equipment_page import EquipmentPage as resolved

        EquipmentPage = resolved
    return EquipmentPage


def _resolve_organizer_page() -> type:
    global OrganizerPage
    if OrganizerPage is None:
        from app.pages.organizer_page import OrganizerPage as resolved

        OrganizerPage = resolved
    return OrganizerPage


def _resolve_quest_provider() -> type:
    global QuestProvider
    if QuestProvider is None:
        from app.modules.encyclopedia.providers import QuestProvider as resolved

        QuestProvider = resolved
    return QuestProvider


def _load_quest_characters(*args: Any, **kwargs: Any) -> list[Any]:
    loader = load_quest_characters
    if loader is None:
        from app.quest_catalog import load_quest_characters as loader

    return list(loader(*args, **kwargs))


def build_craft_preload() -> dict[str, Any]:
    """Prepare small Craft metadata in a disposable worker.

    Searchable item rows stay in SQLite and are queried only when the user types.
    """

    import json

    fallback: dict[str, Any] = {
        "items": [],
        "items_by_name": {},
        "jobs": [],
        "guides": {},
        "selection": {},
        "lookup_items": [],
        "_prepared": True,
        "_lazy_items": True,
        "errors": [],
    }
    try:
        raw = _run_preload_module_result("app.craft_preload")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Résultat du preload Craft compact invalide")
        return payload
    except Exception as exc:
        fallback["errors"].append(str(exc))
        return fallback

def _run_preload_module_status(module: str, *arguments: str) -> None:
    """Run one disposable cache builder without parent-side pipes or payloads."""

    root = str(Path(__file__).resolve().parent)
    environment = dict(os.environ)
    current_pythonpath = str(environment.get("PYTHONPATH") or "")
    environment["PYTHONPATH"] = (
        root
        if not current_pythonpath
        else root + os.pathsep + current_pythonpath
    )
    exit_code = os.spawnve(
        os.P_WAIT,
        sys.executable,
        [sys.executable, "-m", module, *arguments],
        environment,
    )
    if int(exit_code) != 0:
        raise RuntimeError(
            f"Worker preload en échec: {module} (code {int(exit_code)})"
        )


def _run_preload_module_result(module: str, *arguments: str) -> str:
    """Run a worker through a tiny result file instead of parent-side pipes."""

    root = Path(__file__).resolve().parent
    result_dir = root / ".cache" / "dofus_atlas" / "preload_results"
    result_dir.mkdir(parents=True, exist_ok=True)
    safe_name = module.replace(".", "_").replace("/", "_")
    result_path = result_dir / f"{os.getpid()}_{safe_name}.txt"
    try:
        result_path.unlink(missing_ok=True)
        _run_preload_module_status(
            module,
            *arguments,
            "--result-file",
            str(result_path),
        )
        raw = result_path.read_text(encoding="utf-8").strip()
        if not raw:
            raise RuntimeError(f"Worker preload vide: {module}")
        return raw
    finally:
        result_path.unlink(missing_ok=True)


def _warm_encyclopedia_compact_stores() -> None:
    """Prepare Guide/Success indexes entirely in disposable child processes."""

    # These workers persist reconstructible artefacts to disk; Atlas needs only
    # their exit status. Avoid four subprocess.Popen capture pipes in the
    # long-lived process: their transient Windows allocations raised the parent
    # working-set watermark even though no catalogue payload was retained.
    _run_preload_module_status(
        "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
        "--ensure-compact-cache",
    )
    _run_preload_module_status(
        "app.modules.encyclopedia.services.achievement_index_warmup",
    )
    _run_preload_module_status(
        "app.modules.encyclopedia.providers.memory_bound_guide_provider",
        "--ensure-compact-cache",
    )
    _run_preload_module_status(
        "app.modules.encyclopedia.providers.dofus_item_provider",
        "--ensure-guide-index",
    )


def build_quest_related_preload(catalog: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "achievement_provider": None,
        "guide_provider": None,
        "quest_graph": None,
        "guide_progress_by_guide": None,
        "guide_progress_character_key": "",
        "errors": [],
    }
    try:
        if catalog is None:
            _warm_encyclopedia_compact_stores()
            return payload

        from app.modules.encyclopedia.services import build_related_encyclopedia_data
        related = build_related_encyclopedia_data(catalog)
        achievement_provider = related.achievement_provider
        guide_provider = related.guide_provider
        payload["quest_graph"] = related.quest_graph
        payload["achievement_provider"] = achievement_provider
        payload["guide_provider"] = guide_provider
        if isinstance(catalog, QuestCatalog):
            guide_progress, character_key = build_guide_progress_preload(catalog, guide_provider)
            payload["guide_progress_by_guide"] = guide_progress
            payload["guide_progress_character_key"] = character_key
    except Exception as exc:
        payload["errors"].append(str(exc))
    return payload


def build_guide_progress_preload(
    catalog: Any,
    guide_provider: Any,
) -> tuple[dict[str, tuple[int, int, str]], str]:
    load_all = getattr(guide_provider, "load_all", None)
    guides = tuple(load_all()) if callable(load_all) else ()
    if not guides:
        return {}, ""

    from app.modules.encyclopedia.services import (
        ACHIEVEMENT_PROGRESS_FILE,
        GUIDE_PROGRESS_FILE,
        AchievementProgressService,
        GuideProgressCalculator,
        GuideProgressService,
        QuestProgressService,
    )
    characters = _load_quest_characters(
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
    for guide in guides:
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


def _warm_quest_catalogue() -> int:
    """Build/validate the Quest SQLite store in one disposable child process."""

    raw = _run_preload_module_result(
        "app.quest_catalog_details",
        "--ensure-cache",
    )
    return max(0, int(raw))


def build_quest_preload(
    owned_items: dict[int, dict[str, Any]] | None = None,
    include_related: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        # Preload owns disk artefacts only. A live QuestCatalog is created on
        # explicit Encyclopedia use and released again when the page sleeps.
        "catalog": None,
        "catalog_count": 0,
        "owned_items": owned_items or {},
        "achievement_provider": None,
        "guide_provider": None,
        "quest_graph": None,
        "guide_progress_by_guide": None,
        "guide_progress_character_key": "",
        "errors": [],
    }
    try:
        payload["catalog_count"] = _warm_quest_catalogue()
        if include_related:
            related = build_quest_related_preload(None)
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

        self.runtime: AtlasRuntime | None = None
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
        initial_quests = self.preload_results.get("quests")
        initial_related_ready = bool(
            isinstance(initial_quests, dict)
            and initial_quests.get("guide_provider") is not None
            and initial_quests.get("achievement_provider") is not None
            and initial_quests.get("quest_graph") is not None
        )
        self.preload_started = False
        self.preload_finished = bool(initial_preload) and initial_related_ready
        self.preload_states = {
            "quests": PRELOAD_READY if "quests" in self.preload_results else PRELOAD_IDLE,
            "encyclopedia": PRELOAD_READY if initial_related_ready else PRELOAD_IDLE,
            "craft": PRELOAD_READY if "craft" in self.preload_results else PRELOAD_IDLE,
        }
        self.preload_state_lock = Lock()
        self.preload_user_tasks: set[str] = set()
        self.pending_page_name = ""
        self.pending_encyclopedia_tab = ""
        self.pending_guide_target: tuple[str, int | None] | None = None
        self.preload_queue: Queue[dict[str, Any]] = Queue(maxsize=8)
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

        self.register_page("Organizer", self.loading_page("Organizer"))
        self.register_page("Scan Monde", self.loading_page("Scan Monde"))
        self.register_page("Craft", self.loading_page("Craft"))
        self.register_page("Quetes", self.loading_page("Encyclopédie"))
        self.register_page("Equipement", self.loading_page("Équipement"))
        self.register_page("Almanax", self.placeholder_page("Almanax", "Le module Almanax sera intégré ici.", badge="En travaux"))
        self.register_page("Settings", self.create_settings_page())

        self.page_factories["Organizer"] = self.create_organizer_page
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
        self.preload_popup = PreloadProgressPopup(self)
        self._schedule_owned_callback(POST_RENDER_TRAY_DELAY_MS, self.setup_tray)
        self.update_topmost_button()
        self.refresh_nav_selection("")
        if self.topmost_enabled:
            self._schedule_owned_callback(0, lambda: self.set_topmost(True))
        self._schedule_owned_callback(POST_RENDER_RUNTIME_DELAY_MS, self.start_runtime)
        if os.environ.get("QT_QPA_PLATFORM", "").strip().casefold() != "offscreen":
            self._schedule_owned_callback(POST_RENDER_NETWORK_DELAY_MS, self.prepare_network_capture)
        if EQUIPMENT_PRELOAD_DELAY_MS > 0:
            self._schedule_owned_callback(EQUIPMENT_PRELOAD_DELAY_MS, self.preload_equipment_page)
        if not self.preload_finished and self.preload_states["quests"] == PRELOAD_IDLE:
            self._schedule_owned_callback(
                GLOBAL_QUEST_PRELOAD_DELAY_MS,
                lambda: self.start_preload("quests"),
            )
        if self.preload_states["encyclopedia"] == PRELOAD_IDLE and self.preload_states["quests"] == PRELOAD_READY:
            self._schedule_owned_callback(
                GLOBAL_QUEST_PRELOAD_DELAY_MS,
                lambda: self.start_preload("encyclopedia"),
            )
        if not self.preload_finished and self.preload_states["craft"] == PRELOAD_IDLE:
            self._schedule_owned_callback(
                GLOBAL_CRAFT_PRELOAD_DELAY_MS,
                lambda: self.start_preload("craft"),
            )

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
            _load_quest_characters(
                PROFILE_FILE,
                CLIENT_INDEX_JSON,
                binding_path=NETWORK_CHARACTER_BINDINGS_FILE,
                connected_only=False,
            )
        )

    def _connected_characters(self, known_characters: list[Any]) -> list[Any]:
        from app.network.character_runtime_state import character_runtime_state
        from app.quest_catalog import is_generic_dofus_client_name, normalize_text

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
        if not str(label or "").strip() or label == "Aucun personnage connecté":
            return str(LOGO_PATH) if LOGO_PATH.exists() else ""
        try:
            from app.pages.organizer_page import class_icon_path_for_window_name

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
        if "Quetes" not in self.page_factories and isinstance(
            page, _resolve_encyclopedia_page()
        ):
            page.refresh_characters()
            page.set_character_key(self.current_character_key)

        character_page = self.page_widgets.get("Personnage")
        if "Personnage" not in self.page_factories and isinstance(
            character_page, _resolve_character_page()
        ):
            character_page.refresh_from_sources(self.current_character_key)

    def open_character_selector(self) -> None:
        character_page_type = _resolve_character_page()
        page = self.page_widgets.get("Personnage")
        if not isinstance(page, character_page_type):
            page = character_page_type()
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
        if not isinstance(page, _resolve_character_page()):
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
        page = self.page_widgets.get("Quetes")
        prepare_navigation = getattr(page, "prepare_external_tab_navigation", None)
        if callable(prepare_navigation):
            prepare_navigation(label)
        self.show_page("Quetes")
        self._schedule_owned_callback(0, self.finish_pending_encyclopedia_tab)

    def finish_pending_encyclopedia_tab(self) -> None:
        label = str(getattr(self, "pending_encyclopedia_tab", "") or "")
        if not label:
            return

        page = self.page_widgets.get("Quetes")
        if "Quetes" in self.page_factories or not isinstance(
            page, _resolve_encyclopedia_page()
        ):
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

        self.pending_encyclopedia_tab = ""
        page.on_tab_changed(target_index)

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
        if "Quetes" in self.page_factories or not isinstance(
            page, _resolve_encyclopedia_page()
        ):
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
            release_context = getattr(self.home_page, "release_encyclopedia_context", None)
            if callable(release_context):
                release_context(preserve_display=True)
            # Encyclopedia is reconstructible from compact stores. Destroy the
            # whole page on Home instead of retaining its Qt/runtime shell.
            self.release_reconstructible_page("Quetes", self.create_encyclopedia_page)
            self.release_reconstructible_page("Craft", self.create_craft_page)
            self.release_reconstructible_page("Equipement", self.create_equipment_page)
            # deleteLater() tears down the Qt side, but signal/layout cycles can
            # keep Python wrappers alive until a generational GC eventually runs.
            # Flush deferred deletes once Home is visible, then collect only the
            # now-unreachable wrappers. This is lifecycle cleanup, not a working-
            # set trim: live caches/providers have already been explicitly released.
            self._schedule_owned_callback(0, self.collect_released_page_cycles)
            self.home_page.refresh_progress()
        elif name == "Quetes":
            page = self.page_widgets.get("Quetes")
            if "Quetes" not in self.page_factories and isinstance(
                page, _resolve_encyclopedia_page()
            ):
                page.set_character_key(self.current_character_key)
            self._schedule_owned_callback(0, self.finish_pending_encyclopedia_tab)
            self._schedule_owned_callback(0, self.finish_pending_guide_target)

    @staticmethod
    def collect_released_page_cycles() -> None:
        """Finalize deferred Qt deletion and reclaim unreachable wrapper cycles."""

        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        gc.collect()

    def release_reconstructible_page(
        self,
        name: str,
        factory: Callable[[], QWidget],
    ) -> None:
        """Replace a loaded heavy page with its tiny lazy slot."""

        if name in self.page_factories:
            return
        page = self.page_widgets.get(name)
        if page is None or page is self.stack.currentWidget():
            return
        index = self.stack.indexOf(page)
        if index < 0:
            return
        release = getattr(page, "release_runtime", None)
        if callable(release):
            release()
        placeholder = self.loading_page(name)
        self.stack.removeWidget(page)
        self.stack.insertWidget(index, placeholder)
        self.page_widgets[name] = placeholder
        self.page_factories[name] = factory
        self.pages = [
            (page_name, placeholder if page_name == name else widget)
            for page_name, widget in self.pages
        ]
        page.deleteLater()
        self.rebuild_page_indexes()

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

    def create_organizer_page(self) -> QWidget:
        organizer_type = _resolve_organizer_page()
        return organizer_type(
            self.set_status,
            self.reload_runtime,
            self.stop_runtime,
            self.launch_auto_group,
            self.launch_travel,
            self.launch_zaap,
            sessions_changed_callback=self.refresh_global_characters,
            active_session_callback=self.on_organizer_active_window,
        )

    def create_craft_page(self) -> QWidget:
        preload = self.preload_results.get("craft")
        ready = isinstance(preload, dict) and isinstance(preload.get("items"), list)
        if ready:
            self.preload_results.pop("craft", None)
        else:
            self.start_preload("craft", user_requested=True)
        return _resolve_craft_page()(
            self.set_status,
            preload=preload if ready else None,
            defer_runtime=not ready,
        )

    def create_equipment_page(self) -> QWidget:
        return _resolve_equipment_page()(self.set_status)

    def create_encyclopedia_page(self) -> QWidget | None:
        start_preload = getattr(self, "start_preload", None)
        if callable(start_preload):
            start_preload("quests", user_requested=True)
            if self.pending_guide_target or self.pending_encyclopedia_tab in {
                GUIDES_TAB,
                ACHIEVEMENTS_TAB,
            }:
                start_preload("encyclopedia", user_requested=True)
        encyclopedia_page_type = _resolve_encyclopedia_page()
        quest_provider_type = _resolve_quest_provider()
        preload = self.preload_results.get("quests")
        catalog = preload.get("catalog") if isinstance(preload, dict) else None
        owned_items = preload.get("owned_items") if isinstance(preload, dict) else None
        achievement_provider = preload.get("achievement_provider") if isinstance(preload, dict) else None
        guide_provider = preload.get("guide_provider") if isinstance(preload, dict) else None
        quest_graph = preload.get("quest_graph") if isinstance(preload, dict) else None
        guide_progress_by_guide = preload.get("guide_progress_by_guide") if isinstance(preload, dict) else None
        guide_progress_character_key = preload.get("guide_progress_character_key") if isinstance(preload, dict) else ""
        resolved_catalog = (
            catalog
            if catalog is not None
            and hasattr(catalog, "quests")
            and hasattr(catalog, "by_id")
            else None
        )
        quest_provider = (
            quest_provider_type(catalog=resolved_catalog)
            if resolved_catalog is not None
            else quest_provider_type()
        )
        resolved_achievement = (
            achievement_provider
            if achievement_provider is not None
            and bool(getattr(achievement_provider, "_loaded", False))
            else None
        )
        resolved_guide = (
            guide_provider
            if guide_provider is not None
            and bool(getattr(guide_provider, "_loaded", False))
            else None
        )
        resolved_graph = quest_graph
        page = encyclopedia_page_type(
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
        achievement_provider: Any,
        guide_provider: Any,
    ) -> None:
        # Home no longer owns the rich Encyclopedia runtime. Network validation
        # gets its own tiny SQLite-backed Quest context and cold compact
        # providers, so returning Home can release the UI/runtime graphs fully.
        bridge = getattr(self.home_page, "network_bridge", None)
        configure_compact = getattr(bridge, "configure_compact_context", None)
        if callable(configure_compact):
            try:
                configure_compact()
            except Exception:
                LOGGER.exception("Compact network Encyclopedia context unavailable.")
        release_context = getattr(self.home_page, "release_encyclopedia_context", None)
        if callable(release_context):
            release_context(preserve_display=True)

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

    def refresh_preload_popup(self) -> None:
        popup = getattr(self, "preload_popup", None)
        if popup is not None:
            popup.update_states(dict(self.preload_states))

    def start_preload(
        self,
        target: str = "quests",
        *,
        user_requested: bool = False,
        prefer_quests: bool | None = None,
    ) -> None:
        if prefer_quests is not None:
            target = "quests" if prefer_quests else "craft"
        task = str(target or "").strip().casefold()
        result_key = task

        with self.preload_state_lock:
            loading_tasks = [
                key
                for key, state in self.preload_states.items()
                if state == PRELOAD_LOADING and key != task
            ]
        if loading_tasks:
            if user_requested:
                self.preload_user_tasks.add(task)
            self._schedule_owned_callback(
                180,
                lambda target=task, priority=user_requested: self.start_preload(
                    target,
                    user_requested=priority,
                ),
            )
            return

        if task == "encyclopedia":
            with self.preload_state_lock:
                quest_state = self.preload_states.get("quests", PRELOAD_IDLE)
            if quest_state in {PRELOAD_IDLE, PRELOAD_LOADING}:
                if quest_state == PRELOAD_IDLE:
                    self.start_preload("quests", user_requested=user_requested)
                self._schedule_owned_callback(
                    180,
                    lambda: self.start_preload(
                        "encyclopedia",
                        user_requested=user_requested,
                    ),
                )
                return
            # Serialize heavyweight cache builders: Encyclopedia warmup starts
            # only after the Quest disk cache worker has exited.
            builder = lambda: build_quest_related_preload(None)
            result_key = "quests"
        else:
            builders: dict[str, Callable[[], dict[str, Any]]] = {
                "quests": lambda: build_quest_preload(include_related=False),
                "craft": build_craft_preload,
            }
            builder = builders.get(task)  # type: ignore[assignment]
            if builder is None:
                return

        with self.preload_state_lock:
            if self.preload_states.get(task) in {PRELOAD_LOADING, PRELOAD_READY}:
                if user_requested and self.preload_states.get(task) == PRELOAD_LOADING:
                    self.preload_user_tasks.add(task)
                return
            if not user_requested and self.preload_user_tasks:
                self._schedule_owned_callback(
                    250,
                    lambda target=task: self.start_preload(target),
                )
                return
            self.preload_states[task] = PRELOAD_LOADING
            if user_requested:
                self.preload_user_tasks.add(task)
            self.preload_started = True
            self.preload_finished = False
        self.refresh_preload_popup()

        def worker() -> None:
            priority = nullcontext() if user_requested else background_io_priority()
            try:
                with priority:
                    payload = builder()
                self.preload_queue.put(
                    {result_key: payload, "_preload_task": task, "_complete": True}
                )
            except Exception as exc:
                LOGGER.exception("Préchargement asynchrone interrompu (%s).", task)
                self.preload_queue.put(
                    {
                        result_key: {"errors": [str(exc)]},
                        "_preload_task": task,
                        "_fatal_error": str(exc),
                        "_complete": True,
                    }
                )

        Thread(
            target=worker,
            name=f"DofusAtlasPreload-{task}",
            daemon=True,
        ).start()
        self.preload_poll_timer.start()

    def collect_preload_result(self) -> None:
        handled = False
        completed_tasks: list[str] = []
        fatal_error = ""
        errors: list[str] = []

        while True:
            try:
                result = self.preload_queue.get_nowait()
            except Empty:
                break
            handled = True
            task = str(result.pop("_preload_task", "") or "")
            result.pop("_complete", None)
            task_error = str(result.pop("_fatal_error", "") or "")
            payload_key = "quests" if task in {"quests", "encyclopedia"} else task
            task_payload = result.get(payload_key) if isinstance(result, dict) else None
            payload_errors = task_payload.get("errors") if isinstance(task_payload, dict) else None
            payload_error = (
                str(payload_errors[0])
                if isinstance(payload_errors, list) and payload_errors
                else ""
            )
            task_failed = bool(task_error or payload_error)
            fatal_error = task_error or fatal_error
            if task:
                completed_tasks.append(task)
                with self.preload_state_lock:
                    self.preload_user_tasks.discard(task)
                    self.preload_states[task] = (
                        PRELOAD_FAILED if task_failed else PRELOAD_READY
                    )
            self.merge_preload_result(result)
            self.refresh_preload_popup()
            quests = self.preload_results.get("quests")
            if isinstance(quests, dict):
                self.apply_home_preload_update(quests)
                self.apply_encyclopedia_preload_update(quests)
            craft = result.get("craft") if isinstance(result, dict) else {}
            result_quests = result.get("quests") if isinstance(result, dict) else {}
            if isinstance(craft, dict):
                errors.extend(craft.get("errors") or [])
                self.apply_craft_preload_update(craft)
            if isinstance(result_quests, dict):
                errors.extend(result_quests.get("errors") or [])

            if task == "quests" and not task_failed:
                if self.preload_states.get("encyclopedia") == PRELOAD_IDLE:
                    user_waiting = (
                        self.pending_page_name == "Quetes"
                        or self.active_page_name() == "Quetes"
                    )
                    self._schedule_owned_callback(
                        0,
                        lambda priority=user_waiting: self.start_preload(
                            "encyclopedia",
                            user_requested=priority,
                        ),
                    )

        if not handled:
            return

        with self.preload_state_lock:
            loading = any(
                state == PRELOAD_LOADING for state in self.preload_states.values()
            )
            self.preload_started = loading
            self.preload_finished = all(
                state in {PRELOAD_READY, PRELOAD_FAILED}
                for state in self.preload_states.values()
            )
        self.refresh_preload_popup()
        if not loading:
            self.preload_poll_timer.stop()
        if fatal_error:
            self.set_status(f"Préchargement interrompu : {fatal_error}")
        elif errors:
            self.set_status("Prechargement partiel, certains modules resteront charges a la demande.")
        else:
            merged_craft = self.preload_results.get("craft")
            craft_count = len(merged_craft.get("items", [])) if isinstance(merged_craft, dict) else 0
            merged_quests = self.preload_results.get("quests")
            quest_catalog = merged_quests.get("catalog") if isinstance(merged_quests, dict) else None
            quest_rows = getattr(quest_catalog, "quests", ()) if quest_catalog is not None else ()
            quest_count = len(quest_rows or ())
            if quest_count == 0 and isinstance(merged_quests, dict):
                quest_count = max(0, int(merged_quests.get("catalog_count") or 0))
            page = self.page_widgets.get("Quetes")
            if (
                quest_count == 0
                and "Quetes" not in self.page_factories
                and isinstance(page, _resolve_encyclopedia_page())
                and page.quest_page is not None
            ):
                quest_count = len(page.quest_page.catalog.quests)
            if craft_count or quest_count:
                self.set_status(
                    f"Prechargement pret ({craft_count} crafts, {quest_count} quetes)."
                )
            else:
                self.set_status(
                    f"Prechargement pret ({', '.join(completed_tasks) or 'données'})."
                )
        if not fatal_error:
            self.hydrate_active_preloaded_page()

    def merge_preload_result(self, result: dict[str, Any]) -> None:
        for key, value in result.items():
            current = self.preload_results.get(key)
            if isinstance(current, dict) and isinstance(value, dict):
                current.update(value)
            else:
                self.preload_results[key] = value

    def apply_craft_preload_update(self, craft: dict[str, Any]) -> None:
        page = self.page_widgets.get("Craft")
        if "Craft" in self.page_factories or not isinstance(
            page, _resolve_craft_page()
        ):
            return
        if page.hydrate_runtime(craft):
            self.preload_results.pop("craft", None)
            return
        errors = craft.get("errors") if isinstance(craft, dict) else None
        message = str(errors[0]) if isinstance(errors, list) and errors else "données absentes"
        page.show_runtime_error(message)

    def apply_home_preload_update(self, quests: dict[str, Any]) -> None:
        # Disk-only preload payloads deliberately carry no live Encyclopedia
        # objects. Do not call into Home for an all-None update: that path would
        # import the complete provider/catalogue runtime into Atlas merely to
        # discover that there is no context to apply.
        if not any(
            quests.get(key) is not None
            for key in ("catalog", "guide_provider", "achievement_provider")
        ):
            return
        self.home_page.apply_encyclopedia_context(
            catalog=quests.get("catalog"),
            guide_provider=quests.get("guide_provider"),
            achievement_provider=quests.get("achievement_provider"),
        )

    def apply_encyclopedia_preload_update(self, quests: dict[str, Any]) -> None:
        page = self.page_widgets.get("Quetes")
        if "Quetes" in self.page_factories or not isinstance(
            page, _resolve_encyclopedia_page()
        ):
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

    def _ensure_runtime(self) -> AtlasRuntime:
        if self.runtime is None:
            from app.core.runtime_state import AtlasRuntime

            self.runtime = AtlasRuntime(self.set_status, self.update_runtime_badge)
        return self.runtime

    def start_runtime(self) -> None:
        if self.quit_requested or self._background_services_stopped:
            return
        with self.preload_state_lock:
            user_load_in_progress = bool(self.preload_user_tasks)
        if user_load_in_progress:
            self._schedule_owned_callback(250, self.start_runtime)
            return
        self._ensure_runtime().start()

    def stop_runtime(self) -> None:
        runtime = self.runtime
        if runtime is not None:
            runtime.emergency_stop("bouton stop")

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
        runtime = self._ensure_runtime()
        if not getattr(runtime, "_running", False):
            runtime.start()
        else:
            runtime.reload_hotkeys(force_restart)

    def launch_travel(self, text: str) -> None:
        self.reload_runtime()
        self._ensure_runtime().launch_travel(text)

    def launch_zaap(self, text: str, click_position=None, click_ratios=None) -> None:
        self.reload_runtime()
        self._ensure_runtime().launch_zaap(
            text, click_position=click_position, click_ratios=click_ratios
        )

    def launch_auto_group(self, invite_entries: list[dict[str, object]]) -> None:
        self.reload_runtime()
        self._ensure_runtime().launch_auto_group(invite_entries)

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
                LOGGER.debug("Organizer watcher already unavailable during shutdown.", exc_info=True)

        bridge = getattr(getattr(self, "home_page", None), "network_bridge", None)
        stop_bridge = getattr(bridge, "stop", None)
        if callable(stop_bridge):
            try:
                stop_bridge()
            except RuntimeError:
                LOGGER.debug("Network bridge already unavailable during shutdown.", exc_info=True)

        if self.runtime is not None:
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
    guard = SingleInstanceGuard()
    if not guard.acquire():
        LOGGER.warning("[main] another Dofus Atlas instance is already running")
        return 0
    try:
        configure_logging()
        sys.excepthook = log_uncaught_exception
        LOGGER.info("[main] start argv=%s cwd=%s", sys.argv, Path.cwd())
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
        app.setStyleSheet(atlas_stylesheet())
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
    finally:
        guard.release()


if __name__ == "__main__":
    raise SystemExit(main())
