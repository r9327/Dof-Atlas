from __future__ import annotations

import logging
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
DATA_DIR = ROOT_DIR / "data"
CONFIG_DIR = ROOT_DIR / "config"
LOCAL_DIR = DATA_DIR / "local"
LOG_DIR = ROOT_DIR / "logs"
REPORTS_DIR = DATA_DIR / "reports"
LOGO_PATH = DATA_DIR / "images" / "misc" / "dofus_atlas_logo.png"
ICON_PATH = DATA_DIR / "images" / "misc" / "dofus_atlas.ico"
# Canonical product artwork used by the Windows taskbar, notification area,
# application menus and dialogs. ICON_PATH remains available for legacy callers.
APP_ICON_PATH = LOGO_PATH
ZAAP_SHORTCUTS_FILE = CONFIG_DIR / "zaap_shortcuts.json"
ZAAP_FAVORITES_KEY = "zaap_favorites"
ZAAP_CLICK_X = 540
ZAAP_CLICK_Y = 370
ZAAP_CLICK_POSITION_DEFAULT = f"{ZAAP_CLICK_X},{ZAAP_CLICK_Y}"
PROFILE_FILE = DATA_DIR / "client_profiles.json"
BOOTSTRAP_STATUS_FILE = DATA_DIR / "bootstrap_status.txt"
CLIENT_INDEX_JSON = DATA_DIR / "client_index.json"
CLIENT_INDEX_INI = DATA_DIR / "client_index.ini"
NETWORK_CHARACTER_BINDINGS_FILE = LOCAL_DIR / "network_character_bindings.json"
CRAFT_SELECTION_FILE = LOCAL_DIR / "craft_selection.json"
ZAAPS_FILE = LOCAL_DIR / "zaaps.json"
QUEST_PROGRESS_FILE = LOCAL_DIR / "quest_progress.json"
ROUTES_DIR = DATA_DIR / "routes"
LEVELING_FILE = DATA_DIR / "raw" / "json" / "gamosaurus" / "metiers_leveling.json"
RAW_QUEST_DATA_DIR = DATA_DIR / "cache" / "dofus_maps" / "raw" / "doduda_cli"
HARVEST_ASSET_REPORT = REPORTS_DIR / "pyside_harvest_assets_report.json"
HUZOUNET_URL = "https://huzounet.fr/equipments"
APP_NAME = "Dofus Atlas"
DEFAULT_WINDOW_WIDTH = 1180
DEFAULT_WINDOW_HEIGHT = 720
MIN_WINDOW_WIDTH = 900
MIN_WINDOW_HEIGHT = 600

LOGGER = logging.getLogger("dofus_atlas_pyside")
LOG_DIR.mkdir(parents=True, exist_ok=True)
PYSIDE_LOG_FILE = LOG_DIR / "session_manager_pyside.log"
START_LOG_FILE = LOG_DIR / "start_log.txt"
if PYSIDE_LOG_FILE.exists() and PYSIDE_LOG_FILE.stat().st_size > 512 * 1024:
    os_replace_target = LOG_DIR / "session_manager_pyside.log.old"
    try:
        PYSIDE_LOG_FILE.replace(os_replace_target)
    except OSError as exc:
        LOGGER.warning(
            "Impossible de faire tourner le journal PySide %s: %s",
            PYSIDE_LOG_FILE,
            exc,
        )


def add_log_file(path: Path) -> None:
    resolved = path.resolve()
    for existing in LOGGER.handlers:
        if isinstance(existing, logging.FileHandler) and Path(existing.baseFilename).resolve() == resolved:
            return
    try:
        handler = logging.FileHandler(path, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("[PYSIDE] %(asctime)s - %(levelname)s - %(message)s"))
    LOGGER.addHandler(handler)


add_log_file(PYSIDE_LOG_FILE)
LOGGER.setLevel(logging.INFO)


def log_uncaught_exception(exc_type, exc_value, exc_tb) -> None:
    LOGGER.critical("Erreur non geree PySide.", exc_info=(exc_type, exc_value, exc_tb))


KEY_SWITCH_CHARACTER = "__switch_character_actif__"
KEY_SWITCH_CLICK = "__switch_clique_actif__"
KEY_SWITCH_DOUBLE_CLICK = "__switch_double_clique_actif__"
KEY_SWITCH_MOVEMENT = "__switch_deplacement_actif__"
KEY_CLICK_HOTKEY = "__raccourci_switch_clique__"
KEY_DOUBLE_CLICK_HOTKEY = "__raccourci_switch_double_clique__"
