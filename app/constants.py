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

LOG_DIR.mkdir(parents=True, exist_ok=True)
PYSIDE_LOG_FILE = LOG_DIR / "session_manager_pyside.log"
START_LOG_FILE = LOG_DIR / "start_log.txt"
if PYSIDE_LOG_FILE.exists() and PYSIDE_LOG_FILE.stat().st_size > 512 * 1024:
    os_replace_target = LOG_DIR / "session_manager_pyside.log.old"
    try:
        PYSIDE_LOG_FILE.replace(os_replace_target)
    except OSError:
        pass
LOGGER = logging.getLogger("dofus_atlas_pyside")


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
KEY_STOP_SCRIPT_HOTKEY = "__raccourci_stop_script__"
KEY_TRAVEL_TEXT = "__texte_travel__"
KEY_ZAAP_CLICK_POSITION = "__position_clic_zaap__"
KEY_ZAAP_CLICK_LOCKED = "__position_clic_zaap_verrouillee__"
KEY_PRIMARY_WINDOW = "__fenetre_principale__"
KEY_SESSION_ORDER = "__ordre_personnages__"
KEY_TOPMOST = "__fenetre_premier_plan__"
KEY_SCRIPT_SPEED = "__vitesse_script__"
KEY_DEBUG_MODE = "__mode_debug_runtime__"
KEY_SELECTED_CHARACTER = "__personnage_selectionne_ui__"

HARVEST_JOBS = {"bucheron", "pecheur", "alchimiste", "chasseur", "paysan", "mineur"}
JOB_ORDER = {
    "bucheron": 0,
    "pecheur": 1,
    "alchimiste": 2,
    "chasseur": 3,
    "paysan": 4,
    "mineur": 5,
    "bijoutier": 20,
    "bricoleur": 21,
    "cordonnier": 22,
    "faconneur": 23,
    "forgeron": 24,
    "sculpteur": 25,
    "tailleur": 26,
}

JOB_RESOURCE_GROUPS = {
    "Mineur": (
        ("Fer", "MINEUR_FER"), ("Cuivre", "MINEUR_CUIVRE"), ("Bronze", "MINEUR_BRONZE"),
        ("Kobalte", "MINEUR_KOBALTE"), ("Manganese", "MINEUR_MANGANESE"), ("Etain", "MINEUR_ETAIN"),
        ("Silicate", "MINEUR_SILICATE"), ("Argent", "MINEUR_ARGENT"), ("Bauxite", "MINEUR_BAUXITE"),
        ("Or", "MINEUR_OR"), ("Dolomite", "MINEUR_DOLOMITE"), ("Cendrepierre", "MINEUR_CENDREPIERRE"),
        ("Obsidienne", "MINEUR_OBSIDIENNE"), ("Ecume de mer", "MINEUR_ECUMEDEMER"),
        ("Cristal pliable", "MINEUR_CRISTALPLIABLE"), ("Cristal liquide", "MINEUR_CRISTALLIQUIDE"),
    ),
    "Bucheron": (
        ("Frene", "BUCHERON_FRENE"), ("Chataignier", "BUCHERON_CHATAIGNIER"),
        ("Noyer", "BUCHERON_NOYER"), ("Chene", "BUCHERON_CHENE"), ("Bombu", "BUCHERON_BOMBU"),
        ("Erable", "BUCHERON_ERABLE"), ("Oliviolet", "BUCHERON_OLIVIOLET"), ("Pin", "BUCHERON_PIN"),
        ("If", "BUCHERON_IF"), ("Bambou", "BUCHERON_BAMBOU"), ("Merisier", "BUCHERON_MERISIER"),
        ("Noisetier", "BUCHERON_NOISETIER"), ("Ebene", "BUCHERON_EBENE"), ("Kaliptus", "BUCHERON_KALIPTUS"),
        ("Charme", "BUCHERON_CHARME"), ("Bambou sombre", "BUCHERON_BAMBOUSOMBRE"),
        ("Orme", "BUCHERON_ORME"), ("Bambou sacre", "BUCHERON_BAMBOUSACRE"),
        ("Tremble", "BUCHERON_TREMBLE"), ("Aquajou", "BUCHERON_AQUAJOU"),
    ),
    "Paysan": (
        ("Ble", "PAYSAN_BLE"), ("Orge", "PAYSAN_ORGE"), ("Avoine", "PAYSAN_AVOINE"),
        ("Houblon", "PAYSAN_HOUBLON"), ("Lin", "PAYSAN_LIN"), ("Seigle", "PAYSAN_SEIGLE"),
        ("Riz", "PAYSAN_RIZ"), ("Malt", "PAYSAN_MALT"), ("Chanvre", "PAYSAN_CHANVRE"),
        ("Mais", "PAYSAN_MAIS"), ("Millet", "PAYSAN_MILLET"), ("Frostiz", "PAYSAN_FROSTIZ"),
        ("Quisnoa", "PAYSAN_QUISNOA"),
    ),
    "Alchimiste": (
        ("Ortie", "ALCHIMISTE_ORTIE"), ("Sauge", "ALCHIMISTE_SAUGE"),
        ("Trefle a 5 feuilles", "ALCHIMISTE_TREFLEA5FEUILLE"),
        ("Menthe sauvage", "ALCHIMISTE_MENTHESAUVAGE"),
        ("Orchidee Freyesque", "ALCHIMISTE_ORCHIDEEFREYESQUE"),
        ("Edelweiss", "ALCHIMISTE_EDELWEISS"), ("Pandouille", "ALCHIMISTE_PANDOUILLE"),
        ("Ginseng", "ALCHIMISTE_GINSENG"), ("Belladone", "ALCHIMISTE_BELLADONE"),
        ("Mandragore", "ALCHIMISTE_MANDRAGORE"), ("Salikrone", "ALCHIMISTE_SALIKRONE"),
        ("Perce-neige", "ALCHIMISTE_PERCENEIGE"), ("Tulipe en papier", "ALCHIMISTE_TULIPEENPAPIER"),
    ),
    "Pecheur": (
        ("Goujon", "PECHEUR_GOUJON"), ("Greuvette", "PECHEUR_GREUVETTE"),
        ("Truite", "PECHEUR_TRUITE"), ("Crabe Sourimi", "PECHEUR_CRABE"),
        ("Poisson-Chaton", "PECHEUR_POISSONCHATON"), ("Poisson Pane", "PECHEUR_POISSONPANE"),
        ("Carpe d'Iem", "PECHEUR_CARPEDIEM"), ("Sardine Brillante", "PECHEUR_SARDINEBRILLANTE"),
        ("Brochet", "PECHEUR_BROCHET"), ("Kralamoure", "PECHEUR_KRALAMOUR"),
        ("Anguille", "PECHEUR_ANGUILLE"), ("Dorade Grise", "PECHEUR_DORADEGRISE"),
        ("Perche", "PECHEUR_PERCHE"), ("Raie Bleue", "PECHEUR_RAIE"), ("Lotte", "PECHEUR_LOTTE"),
        ("Requin Marteau-Faucille", "PECHEUR_REQUINMARTEAU"), ("Bar Rikain", "PECHEUR_BARRIKAIN"),
        ("Morue", "PECHEUR_MORUE"), ("Tanche", "PECHEUR_TANCHE"), ("Espadon", "PECHEUR_ESPADON"),
        ("Patelle", "PECHEUR_PATELLE"), ("Poisskaille", "PECHEUR_POISKAILLE"),
        ("Pichon d'encre", "PECHEUR_PICHONDENCRE"),
    ),
    "Chasseur": (
        ("Viande Intangible", "CHASSEUR_VIANDE_INTANGIBLE"),
        ("Viande Hachee", "CHASSEUR_VIANDE_HACHEE"),
        ("Viande Faisandee", "CHASSEUR_VIANDE_FAISANDEE"),
        ("Viande Frelatee", "CHASSEUR_VIANDE_FRELATEE"),
        ("Viande Minerale", "CHASSEUR_VIANDE_MINERALE"),
        ("Viande Tendre", "CHASSEUR_VIANDE_TENDRE"),
        ("Viande Ladre", "CHASSEUR_VIANDE_LADRE"),
        ("Viande Avariee", "CHASSEUR_VIANDE_AVARIEE"),
        ("Viande Sanguinolente", "CHASSEUR_VIANDE_SANGUINOLENTE"),
        ("Viande Rassie", "CHASSEUR_VIANDE_RASSIE"),
        ("Viande Exsudative", "CHASSEUR_VIANDE_EXSUDATIVE"),
        ("Viande Sechee", "CHASSEUR_VIANDE_SECHEE"),
        ("Viande Saignante", "CHASSEUR_VIANDE_SAIGNANTE"),
        ("Viande Persillee", "CHASSEUR_VIANDE_PERSILLEE"),
        ("Viande Maceree", "CHASSEUR_VIANDE_MACEREE"),
        ("Viande de Brousse", "CHASSEUR_VIANDE_BROUSSE"),
        ("Viande Fraiche", "CHASSEUR_VIANDE_FRAICHE"),
        ("Viande Maigre", "CHASSEUR_VIANDE_MAIGRE"),
        ("Viande Gatee", "CHASSEUR_VIANDE_GATEE"),
        ("Viande Noire", "CHASSEUR_VIANDE_NOIRE"),
        ("Viande Goutue", "CHASSEUR_VIANDE_GOUTUE"),
    ),
}

