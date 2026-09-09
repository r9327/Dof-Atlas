from __future__ import annotations

import difflib
import inspect
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplashScreen,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import (
    BOOTSTRAP_STATUS_FILE,
    KEY_DEBUG_MODE,
    KEY_SCRIPT_SPEED,
    KEY_SESSION_ORDER,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SWITCH_CHARACTER,
    KEY_SWITCH_CLICK,
    KEY_SWITCH_DOUBLE_CLICK,
    KEY_SWITCH_MOVEMENT,
    KEY_TOPMOST,
    KEY_TRAVEL_TEXT,
    KEY_ZAAP_CLICK_LOCKED,
    KEY_ZAAP_CLICK_POSITION,
    LOGGER,
    PROFILE_FILE,
    ROOT_DIR,
    ROUTES_DIR,
    ZAAPS_FILE,
    ZAAP_CLICK_POSITION_DEFAULT,
    ZAAP_CLICK_X,
    ZAAP_CLICK_Y,
    ZAAP_FAVORITES_KEY,
    ZAAP_SHORTCUTS_FILE,
)
from app.core.json_store import read_json_resilient, write_json_atomic
from app.core.text import clean_auto_group_name, normalize_key, strip_accents
from app.ui.components import AtlasButton
from app.windows.unity_windows import enable_dpi_awareness

try:
    from app import local_data_cache
except Exception:
    local_data_cache = None


def strip_zaap_coordinate_suffix(value: Any) -> str:
    return re.sub(r"\s*\[-?\d+\s*,\s*-?\d+\]\s*$", "", str(value or "")).strip()


def zaap_runtime_search_text(row: dict[str, Any]) -> str:
    for key in ("dofus_search", "search", "name", "label"):
        text = strip_zaap_coordinate_suffix(row.get(key, ""))
        text = re.sub(r"\s+", " ", strip_accents(text)).strip()
        if text:
            return text
    return "Zaap"


def zaap_favorite_name(row: dict[str, Any]) -> str:
    for key in ("name", "search", "label"):
        text = strip_zaap_coordinate_suffix(row.get(key, ""))
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if text:
            return text
    return "Zaap"


def short_label(value: Any, limit: int = 10) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "."


def tile_label(value: Any, limit: int = 18) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= 10:
        return text
    if len(text) <= limit:
        words = text.split(" ")
        if len(words) > 1:
            middle = max(1, len(words) // 2)
            return " ".join(words[:middle]) + "\n" + " ".join(words[middle:])
        return text
    words = text.split(" ")
    if len(words) > 1:
        first = []
        second = []
        for word in words:
            target = first if sum(len(part) for part in first) + len(first) + len(word) <= limit // 2 + 3 else second
            target.append(word)
        if first and second:
            return " ".join(first) + "\n" + " ".join(second)
    half = max(1, len(text) // 2)
    return text[:half].rstrip() + "\n" + text[half:].lstrip()


def canonical_job_name(value: Any) -> str:
    key = normalize_key(value)
    aliases = {
        "pecheur": "Pecheur",
        "bucheron": "Bucheron",
        "alchimiste": "Alchimiste",
        "chasseur": "Chasseur",
        "paysan": "Paysan",
        "mineur": "Mineur",
    }
    return aliases.get(key, str(value or ""))


def route_path_for(job_name: str, item_name: str, step: int = 1) -> Path:
    return ROUTES_DIR / normalize_key(job_name) / f"{normalize_key(item_name or 'ressource')}_{step}.png"


def existing_route_path(job_name: str, item_name: str, step: int = 1) -> Path | None:
    path = route_path_for(job_name, item_name, step)
    if path.exists():
        return path
    legacy = ROUTES_DIR / normalize_key(job_name) / f"{normalize_key(item_name)}.png"
    if step == 1 and legacy.exists():
        return legacy
    return None


def key_sequence_to_hotkey(key: int, modifiers: Qt.KeyboardModifiers | None = None) -> str:
    replacements = {
        Qt.Key_Escape: "ESCAPE",
        Qt.Key_Return: "RETURN",
        Qt.Key_Enter: "ENTER",
        Qt.Key_Space: "SPACE",
        Qt.Key_Tab: "TAB",
        Qt.Key_Backspace: "BACKSPACE",
        Qt.Key_Delete: "DELETE",
        Qt.Key_Insert: "INSERT",
        Qt.Key_Home: "HOME",
        Qt.Key_End: "END",
        Qt.Key_PageUp: "PAGEUP",
        Qt.Key_PageDown: "PAGEDOWN",
        Qt.Key_Up: "UP",
        Qt.Key_Down: "DOWN",
        Qt.Key_Left: "LEFT",
        Qt.Key_Right: "RIGHT",
        Qt.Key_Control: "CONTROL",
        Qt.Key_Shift: "SHIFT",
        Qt.Key_Alt: "ALT",
    }
    if key in replacements:
        base = replacements[key]
    else:
        text = QKeySequence(key).toString(QKeySequence.PortableText).strip()
        base = text.upper() if text else ""
    if not base:
        return ""
    if modifiers is None:
        return base
    parts = []
    if modifiers & Qt.ControlModifier and key != Qt.Key_Control:
        parts.append("CTRL")
    if modifiers & Qt.AltModifier and key != Qt.Key_Alt:
        parts.append("ALT")
    if modifiers & Qt.ShiftModifier and key != Qt.Key_Shift:
        parts.append("SHIFT")
    if modifiers & Qt.MetaModifier:
        parts.append("WIN")
    parts.append(base)
    return "+".join(parts)


def score_match(values: list[str], query: str) -> int:
    query_key = normalize_key(query)
    if not query_key:
        return 1
    compact_query = query_key.replace("_", "")
    best = 0
    for value in values:
        key = normalize_key(value)
        compact = key.replace("_", "")
        if key == query_key or compact == compact_query:
            best = max(best, 100)
        elif key.startswith(query_key) or compact.startswith(compact_query):
            best = max(best, 90)
        elif query_key in key or compact_query in compact:
            best = max(best, 82)
        else:
            ratio = difflib.SequenceMatcher(None, compact_query, compact).ratio()
            if ratio >= 0.55:
                best = max(best, int(ratio * 70))
    return best


def text_variants(value: Any) -> list[str]:
    text = str(value or "")
    variants = [text]
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        repaired = ""
    if repaired and repaired != text:
        variants.append(repaired)
    return variants


SEARCH_STOP_TOKENS = {"a", "au", "aux", "d", "de", "des", "du", "l", "la", "le", "les", "un", "une"}


def search_tokens(value: Any) -> list[str]:
    return [
        token
        for token in normalize_key(value).split("_")
        if token and (token not in SEARCH_STOP_TOKENS or token.isdigit())
    ]


def token_spelling_variants(token: str) -> set[str]:
    token = str(token or "")
    variants = {token} if token else set()
    if len(token) <= 3:
        return variants
    if token.endswith("eaux"):
        variants.add(token[:-1])
    if token.endswith("aux"):
        variants.add(token[:-3] + "al")
    if token.endswith(("s", "x")):
        variants.add(token[:-1])
    if token.endswith("es"):
        variants.add(token[:-2])
    return {variant for variant in variants if variant}


def is_subsequence(needle: str, haystack: str) -> bool:
    if not needle:
        return True
    if not haystack:
        return False
    index = 0
    for char in haystack:
        if char == needle[index]:
            index += 1
            if index == len(needle):
                return True
    return False


def coordinate_pair(value: Any) -> tuple[int, int] | None:
    numbers = re.findall(r"-?\d+", str(value or ""))
    if len(numbers) < 2:
        return None
    try:
        return (int(numbers[0]), int(numbers[1]))
    except ValueError:
        return None


def row_coordinate_pair(row: dict[str, Any]) -> tuple[int, int] | None:
    try:
        return (int(row["posX"]), int(row["posY"]))
    except (KeyError, TypeError, ValueError):
        return coordinate_pair(row.get("label", ""))


def flattened_text_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for nested in value.values():
            values.extend(flattened_text_values(nested))
        return values
    if isinstance(value, (list, tuple, set)):
        for item in value:
            values.extend(flattened_text_values(item))
        return values
    values.extend(text_variants(value))
    return [text for text in values if str(text).strip()]


def row_text_values(row: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for key in keys:
        values.extend(flattened_text_values(row.get(key, "")))
    return [value for value in values if str(value).strip()]


def zaap_search_values(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    values.extend(
        row_text_values(
            row,
            (
                "label",
                "name",
                "search",
                "region",
                "area",
                "zone",
                "world",
                "subarea",
                "subArea",
                "mapArea",
                "mapSubArea",
                "alias",
                "aliases",
                "tag",
                "tags",
                "keyword",
                "keywords",
            ),
        )
    )
    values.extend(row_text_values(row, ("regions", "areas", "zones", "subareas", "subAreas", "mapAreas", "mapSubAreas")))
    coords = row_coordinate_pair(row)
    if coords is not None:
        x, y = coords
        values.extend((f"{x},{y}", f"{x} {y}", f"[{x},{y}]"))
    return [value for value in values if str(value).strip()]


def token_match_score(query_tokens: list[str], value_tokens: list[str]) -> int:
    if not query_tokens:
        return 1
    if not value_tokens:
        return 0
    total = 0.0
    matched = 0
    used_indexes: set[int] = set()
    for query_token in query_tokens:
        query_variants = token_spelling_variants(query_token)
        best = 0.0
        best_index = -1
        for index, value_token in enumerate(value_tokens):
            if index in used_indexes:
                continue
            value_variants = token_spelling_variants(value_token)
            if query_variants & value_variants:
                if best < 1.0:
                    best = 1.0
                    best_index = index
            elif len(query_token) >= 2 and any(value.startswith(query) for query in query_variants for value in value_variants):
                if best < 0.94:
                    best = 0.94
                    best_index = index
            elif min(len(query_token), len(value_token)) >= 3 and any(query in value for query in query_variants for value in value_variants):
                if best < 0.88:
                    best = 0.88
                    best_index = index
            elif len(value_token) >= 4 and any(value in query for query in query_variants for value in value_variants):
                if best < 0.82:
                    best = 0.82
                    best_index = index
            elif len(query_token) >= 3 and any(is_subsequence(query, value) for query in query_variants for value in value_variants):
                if best < 0.78:
                    best = 0.78
                    best_index = index
            elif len(query_token) >= 4 and len(value_token) >= 4:
                ratio = max(difflib.SequenceMatcher(None, query, value).ratio() for query in query_variants for value in value_variants)
                if min(len(query_token), len(value_token)) <= 4 and ratio < 0.86:
                    continue
                if best < ratio:
                    best = ratio
                    best_index = index
        if best >= 0.70:
            matched += 1
            total += best
            used_indexes.add(best_index)
    if matched == len(query_tokens):
        return int(70 + 25 * (total / len(query_tokens)))
    if matched:
        return int(30 + 35 * (matched / len(query_tokens)))
    return 0


def zaap_search_score(row: dict[str, Any], query: str) -> int:
    query_text = str(query or "").strip()
    if not query_text:
        return 1
    values = zaap_search_values(row)
    best = score_match(values, query_text)
    query_tokens = search_tokens(query_text)
    primary_values = row_text_values(row, ("label", "name", "search"))
    primary_score = score_match(primary_values, query_text)
    for value in primary_values:
        primary_score = max(primary_score, token_match_score(query_tokens, search_tokens(value)))
    if primary_score > 0:
        best = max(best, min(100, primary_score + 5))
    query_coords = coordinate_pair(query_text)
    row_coords = row_coordinate_pair(row)
    if query_coords is not None and row_coords == query_coords:
        best = max(best, 100)

    combined_tokens: list[str] = []
    for value in values:
        combined_tokens.extend(search_tokens(value))
        best = max(best, token_match_score(query_tokens, search_tokens(value)))
    combined_tokens = list(dict.fromkeys(combined_tokens))
    best = max(best, token_match_score(query_tokens, combined_tokens))

    query_compact = normalize_key(query_text).replace("_", "")
    combined_compact = "".join(combined_tokens)
    if query_compact and query_compact in combined_compact:
        best = max(best, 86)
    return best


def zaap_search_min_score(query: str) -> int:
    query_text = str(query or "").strip()
    if not query_text:
        return 1
    if coordinate_pair(query_text) is not None:
        return 90
    tokens = search_tokens(query_text)
    if len(tokens) >= 2:
        return 70
    if len(normalize_key(query_text)) >= 2:
        return 50
    return 1


def read_json(path: Path, default: Any) -> Any:
    return read_json_resilient(Path(path), default, logger=LOGGER)


def write_json(path: Path, payload: Any) -> None:
    write_json_atomic(Path(path), payload)


def invoke_compatible_callback(callback, *args):
    """Invoke a legacy callback once, selecting its supported signature first.

    Old callbacks accepted no arguments while current Zaap launchers receive
    search/position/ratios. Inspecting/binding before invocation preserves both
    contracts without catching a TypeError raised *inside* callback code and
    then executing the callback a second time.
    """

    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return callback(*args)

    try:
        signature.bind(*args)
    except TypeError as argument_error:
        try:
            signature.bind()
        except TypeError:
            raise argument_error
        return callback()
    return callback(*args)


def parse_unit_ratio(value: Any) -> float | None:
    try:
        ratio = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 0.0 <= ratio <= 1.0:
        return ratio
    return None


def format_zaap_ratio(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def read_zaap_shortcuts(path: Path | None = None) -> dict[str, Any]:
    payload = read_json(path or ZAAP_SHORTCUTS_FILE, {})
    return payload if isinstance(payload, dict) else {}


def read_zaap_button_ratios(payload: dict[str, Any] | None = None) -> tuple[float, float] | None:
    payload = payload if isinstance(payload, dict) else read_zaap_shortcuts()
    button = payload.get("zaap_button")
    if not isinstance(button, dict):
        return None
    x_ratio = parse_unit_ratio(button.get("x_ratio"))
    y_ratio = parse_unit_ratio(button.get("y_ratio"))
    if x_ratio is None or y_ratio is None:
        return None
    return (x_ratio, y_ratio)


def zaap_favorite_lookup(zaaps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in zaaps:
        if not isinstance(row, dict):
            continue
        for value in (zaap_favorite_name(row), strip_zaap_coordinate_suffix(row.get("label", "")), row.get("search", "")):
            key = normalize_key(value)
            if key and key not in lookup:
                lookup[key] = row
    return lookup


def clean_zaap_favorites(values: Any, zaaps: list[dict[str, Any]] | None = None) -> list[str]:
    if not isinstance(values, list):
        return []
    zaaps = zaaps if isinstance(zaaps, list) else load_zaap_index()
    lookup = zaap_favorite_lookup(zaaps)
    favorites: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = normalize_key(value)
        if not key or key in seen:
            continue
        row = lookup.get(key)
        if row is None:
            continue
        name = zaap_favorite_name(row)
        favorite_key = normalize_key(name)
        if not favorite_key or favorite_key in seen:
            continue
        favorites.append(name)
        seen.add(favorite_key)
    return favorites


def read_zaap_favorites(
    zaaps: list[dict[str, Any]] | None = None,
    payload: dict[str, Any] | None = None,
) -> list[str]:
    payload = payload if isinstance(payload, dict) else read_zaap_shortcuts()
    return clean_zaap_favorites(payload.get(ZAAP_FAVORITES_KEY, []), zaaps)


def save_zaap_favorites(
    favorites: list[str],
    zaaps: list[dict[str, Any]] | None = None,
    path: Path | None = None,
) -> list[str]:
    path = path or ZAAP_SHORTCUTS_FILE
    payload = read_zaap_shortcuts(path)
    cleaned = clean_zaap_favorites(favorites, zaaps)
    payload[ZAAP_FAVORITES_KEY] = cleaned
    write_json(path, payload)
    return cleaned


def save_zaap_button_ratios(x_ratio: float, y_ratio: float, path: Path | None = None) -> tuple[float, float]:
    parsed_x = parse_unit_ratio(x_ratio)
    parsed_y = parse_unit_ratio(y_ratio)
    if parsed_x is None or parsed_y is None:
        raise ValueError("Ratios Zaap invalides.")
    path = path or ZAAP_SHORTCUTS_FILE
    payload = read_zaap_shortcuts(path)
    payload["zaap_button"] = {
        "x_ratio": round(parsed_x, 6),
        "y_ratio": round(parsed_y, 6),
    }
    write_json(path, payload)
    return (parsed_x, parsed_y)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_bootstrap_status() -> str:
    try:
        text = BOOTSTRAP_STATUS_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return "Verification des prerequis..."
    return text or "Verification des prerequis..."


def default_profiles() -> dict[str, Any]:
    return {
        KEY_SWITCH_CHARACTER: True,
        KEY_SWITCH_CLICK: False,
        KEY_SWITCH_DOUBLE_CLICK: False,
        KEY_SWITCH_MOVEMENT: False,
        KEY_STOP_SCRIPT_HOTKEY: "",
        KEY_ZAAP_CLICK_POSITION: ZAAP_CLICK_POSITION_DEFAULT,
        KEY_ZAAP_CLICK_LOCKED: True,
        KEY_SESSION_ORDER: [],
        KEY_TOPMOST: False,
        KEY_SCRIPT_SPEED: "normal",
        KEY_DEBUG_MODE: False,
    }


def profile_bool(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, str):
        return value.strip().casefold() not in ("0", "false", "faux", "non", "off", "")
    return bool(value)


def parse_zaap_click_position(value: Any, default: tuple[int, int] = (ZAAP_CLICK_X, ZAAP_CLICK_Y)) -> tuple[int, int]:
    text = str(value or "").strip()
    match = re.search(r"(-?\d+)\s*[,;:xX ]\s*(-?\d+)", text)
    if not match:
        return default
    try:
        return (max(0, int(match.group(1))), max(0, int(match.group(2))))
    except ValueError:
        return default


def format_zaap_click_position(position: tuple[int, int]) -> str:
    return f"{int(position[0])},{int(position[1])}"


def parse_size_pair(value: Any, default: tuple[int, int], minimum: tuple[int, int] = (320, 240)) -> tuple[int, int]:
    text = str(value or "").strip()
    match = re.search(r"(\d+)\s*[,;:xX ]\s*(\d+)", text)
    if not match:
        return default
    try:
        width = max(int(minimum[0]), int(match.group(1)))
        height = max(int(minimum[1]), int(match.group(2)))
        return (width, height)
    except ValueError:
        return default


def format_size_pair(size: tuple[int, int]) -> str:
    return f"{int(size[0])},{int(size[1])}"


def read_profile_payload() -> dict[str, Any]:
    payload = read_json(PROFILE_FILE, default_profiles())
    if not isinstance(payload, dict):
        payload = default_profiles()
    legacy_debug_key = "".join(["__mode_debug_", "a", "h", "k__"])
    if legacy_debug_key in payload and KEY_DEBUG_MODE not in payload:
        payload[KEY_DEBUG_MODE] = payload.get(legacy_debug_key)
    payload.pop(legacy_debug_key, None)
    payload.pop(KEY_TRAVEL_TEXT, None)
    merged = default_profiles()
    merged.update(payload)
    return merged


def read_zaap_click_position(payload: dict[str, Any] | None = None) -> tuple[int, int]:
    payload = payload or read_profile_payload()
    return parse_zaap_click_position(payload.get(KEY_ZAAP_CLICK_POSITION), (ZAAP_CLICK_X, ZAAP_CLICK_Y))


def read_zaap_click_locked(payload: dict[str, Any] | None = None) -> bool:
    payload = payload or read_profile_payload()
    return profile_bool(payload, KEY_ZAAP_CLICK_LOCKED, True)


def save_zaap_click_position(text: Any) -> tuple[int, int]:
    payload = read_profile_payload()
    position = parse_zaap_click_position(text, read_zaap_click_position(payload))
    payload[KEY_ZAAP_CLICK_POSITION] = format_zaap_click_position(position)
    write_json(PROFILE_FILE, payload)
    return position


def save_zaap_click_locked(locked: bool) -> None:
    payload = read_profile_payload()
    payload[KEY_ZAAP_CLICK_LOCKED] = bool(locked)
    write_json(PROFILE_FILE, payload)


def dofus_window_from_point(mouse_x: int, mouse_y: int) -> dict[str, Any] | None:
    if os.name != "nt":
        return None
    try:
        import win32con
        import win32gui
    except Exception:
        return None

    point = (int(mouse_x), int(mouse_y))
    candidates: list[int] = []

    def client_screen_rect(hwnd: int) -> tuple[int, int, int, int] | None:
        try:
            client_left, client_top, client_right, client_bottom = win32gui.GetClientRect(hwnd)
            screen_left, screen_top = win32gui.ClientToScreen(hwnd, (client_left, client_top))
            screen_right, screen_bottom = win32gui.ClientToScreen(hwnd, (client_right, client_bottom))
            width = int(screen_right - screen_left)
            height = int(screen_bottom - screen_top)
        except Exception:
            return None
        if width <= 0 or height <= 0:
            return None
        return (int(screen_left), int(screen_top), width, height)

    def window_screen_rect(hwnd: int) -> tuple[int, int, int, int] | None:
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = int(right - left)
            height = int(bottom - top)
        except Exception:
            return None
        if width <= 0 or height <= 0:
            return None
        return (int(left), int(top), width, height)

    def contains(rect: tuple[int, int, int, int]) -> bool:
        left, top, width, height = rect
        return left <= point[0] < left + width and top <= point[1] < top + height

    try:
        hwnd = int(win32gui.WindowFromPoint(point))
        root = int(win32gui.GetAncestor(hwnd, win32con.GA_ROOT)) if hwnd else 0
        if root:
            candidates.append(root)
    except Exception:
        pass

    def enum_callback(hwnd: int, _extra: Any) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd) or win32gui.GetClassName(hwnd) != "UnityWndClass":
                return True
        except Exception:
            return True
        client_rect = client_screen_rect(hwnd)
        rect = client_rect if client_rect is not None else window_screen_rect(hwnd)
        if rect is not None and contains(rect):
            candidates.append(int(hwnd))
        return True

    try:
        win32gui.EnumWindows(enum_callback, None)
    except Exception:
        pass

    seen: set[int] = set()
    for hwnd in candidates:
        if hwnd in seen:
            continue
        seen.add(hwnd)
        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                continue
            if win32gui.GetClassName(hwnd) != "UnityWndClass":
                continue
            rect_source = "client"
            rect = client_screen_rect(hwnd)
            if rect is not None and not contains(rect):
                continue
            if rect is None:
                rect_source = "window"
                rect = window_screen_rect(hwnd)
            if rect is None or not contains(rect):
                continue
            left, top, width, height = rect
            return {
                "hwnd": int(hwnd),
                "title": win32gui.GetWindowText(hwnd),
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "rect_source": rect_source,
            }
        except Exception:
            continue
    return None


def calibrate_zaap_button_from_mouse() -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("Calibration disponible seulement sous Windows.")
    enable_dpi_awareness()
    try:
        import pyautogui
        import win32gui
    except Exception as exc:
        raise RuntimeError("pyautogui ou pywin32 est introuvable.") from exc

    mouse = pyautogui.position()
    mouse_x = int(mouse.x)
    mouse_y = int(mouse.y)
    window = dofus_window_from_point(mouse_x, mouse_y)
    if window is None:
        raise RuntimeError("Aucune fenetre Dofus detectee sous la souris.")

    left = int(window["left"])
    top = int(window["top"])
    width = int(window["width"])
    height = int(window["height"])
    x_ratio = (mouse_x - left) / width
    y_ratio = (mouse_y - top) / height
    ratios = save_zaap_button_ratios(x_ratio, y_ratio)

    try:
        client_x, client_y = win32gui.ScreenToClient(int(window["hwnd"]), (mouse_x, mouse_y))
        fallback = (max(0, int(client_x)), max(0, int(client_y)))
    except Exception:
        fallback = (max(0, mouse_x - left), max(0, mouse_y - top))
    save_zaap_click_position(format_zaap_click_position(fallback))

    return {
        "mouse": (mouse_x, mouse_y),
        "window": window,
        "ratios": ratios,
        "fallback_click_position": fallback,
    }


def load_zaap_index(path: Path = ZAAPS_FILE) -> list[dict[str, Any]]:
    payload = read_json(path, {"zaaps": []})
    rows = payload.get("zaaps") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    zaaps = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or row.get("name") or "").strip()
        search = str(row.get("search") or row.get("name") or label).strip()
        key = normalize_key(label or search)
        if not key or key in seen:
            continue
        item = dict(row)
        item["label"] = label or search
        item["search"] = search or label
        zaaps.append(item)
        seen.add(key)
    return sorted(zaaps, key=lambda entry: normalize_key(entry.get("label")))


def item_id(item: dict[str, Any]) -> int | None:
    value = item.get("id_dofus") or item.get("ankama_id") or item.get("id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def local_image_path(item: dict[str, Any]) -> Path | None:
    raw = item.get("image_path") or item.get("local_image_path") or ""
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path if path.exists() else None


def display_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def hidden_process_options() -> dict[str, Any]:
    options: dict[str, Any] = {
        "cwd": str(ROOT_DIR),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        options["startupinfo"] = startup
    return options


class IconCache:
    def __init__(self, size: int = 32, max_items: int = 1200):
        self.size = size
        self.max_items = max_items
        self.cache: dict[str, QIcon] = {}
        self.order: list[str] = []

    def icon_for_item(self, item: dict[str, Any], fallback: QIcon | None = None) -> QIcon:
        raw = item.get("image_path") or item.get("local_image_path") or ""
        if not raw:
            return fallback or QIcon()
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT_DIR / path
        key = str(path)
        if key in self.cache:
            return self.cache[key]
        if not path.exists():
            return fallback or QIcon()
        pixmap = QPixmap(key)
        if pixmap.isNull():
            return fallback or QIcon()
        icon = QIcon(pixmap.scaled(self.size, self.size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.cache[key] = icon
        self.order.append(key)
        while len(self.order) > self.max_items:
            old = self.order.pop(0)
            self.cache.pop(old, None)
        return icon


def lock_icon(locked: bool) -> QIcon:
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor("#f8fafc" if locked else "#33d46f")
    pen = QPen(color, 1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(4.5, 8.0, 9.0, 7.0), 1.8, 1.8)
    if locked:
        painter.drawArc(QRectF(5.7, 3.0, 6.6, 8.0), 0, 180 * 16)
        painter.drawLine(5.7, 7.1, 5.7, 8.3)
        painter.drawLine(12.3, 7.1, 12.3, 8.3)
    else:
        painter.drawArc(QRectF(7.0, 3.0, 6.6, 8.0), 30 * 16, 155 * 16)
        painter.drawLine(7.0, 7.1, 7.0, 8.3)
    painter.end()
    return QIcon(pixmap)


def location_icon() -> QIcon:
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor("#33d46f"), 1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(4.2, 2.2, 9.6, 9.6))
    painter.drawEllipse(QRectF(7.2, 5.2, 3.6, 3.6))
    painter.drawLine(9.0, 12.0, 9.0, 16.0)
    painter.drawLine(6.8, 14.2, 9.0, 16.0)
    painter.drawLine(11.2, 14.2, 9.0, 16.0)
    painter.end()
    return QIcon(pixmap)


class ZaapWidget(QWidget):
    def __init__(
        self,
        status_callback,
        start_callback=None,
        config_update_callback=None,
        parent: QWidget | None = None,
        show_position_controls: bool = True,
        show_favorites: bool = True,
    ):
        super().__init__(parent)
        self.status_callback = status_callback
        self.start_callback = start_callback
        self.config_update_callback = config_update_callback
        self.show_position_controls = bool(show_position_controls)
        self.show_favorites = bool(show_favorites)
        self.position_locked = read_zaap_click_locked()
        self.zaaps = load_zaap_index()
        self.filtered_zaaps: list[dict[str, Any]] = []
        self.favorite_names = read_zaap_favorites(self.zaaps) if self.show_favorites else []
        self.favorite_buttons: list[QPushButton] = []
        self.favorite_star_buttons: list[QToolButton] = []
        self.calibration_active = False
        self.launching_zaap = False
        self.search_input = QLineEdit()
        self.search_input.setObjectName("comboField")
        self.search_input.setPlaceholderText("Sélectionner un zaap")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setToolTip("Rechercher un zaap par nom, zone ou coordonnees")
        self.search_input.installEventFilter(self)
        self.suggestion_popup = QListWidget(self)
        self.suggestion_popup.setObjectName("ZaapSuggestionPopup")
        self.suggestion_popup.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.NoDropShadowWindowHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.suggestion_popup.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.suggestion_popup.setFocusPolicy(Qt.NoFocus)
        self.suggestion_popup.setMouseTracking(True)
        self.suggestion_popup.viewport().installEventFilter(self)
        self.suggestion_popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.suggestion_popup.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.suggestion_popup.setSelectionMode(QAbstractItemView.SingleSelection)
        self.suggestion_popup.setUniformItemSizes(True)
        self.zaap_label = QLabel("Zaap :")
        self.zaap_label.setObjectName("CompactLabel")
        self.zaap_label.setFixedSize(46, 32)
        self.zaap_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.position_label = QLabel("Position :")
        self.position_label.setObjectName("CompactLabel")
        self.position_label.setFixedSize(62, 32)
        self.position_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.position_edit = QLineEdit(format_zaap_click_position(read_zaap_click_position()))
        self.position_edit.setObjectName("inputField")
        self.position_edit.setPlaceholderText(ZAAP_CLICK_POSITION_DEFAULT)
        self.position_edit.setFixedSize(90, 32)
        self.position_edit.setToolTip("Fallback clic Python si la position Zaap n'est pas calibree")
        self.lock_button = QToolButton()
        self.lock_button.setObjectName("iconButton")
        self.lock_button.setFixedSize(32, 32)
        self.lock_button.setIconSize(QSize(15, 15))
        self.lock_button.setCursor(Qt.PointingHandCursor)
        self.lock_button.setAutoRaise(False)
        self.position_wrapper = QWidget(self)
        self.position_wrapper.setFixedSize(90, 32)
        position_layout = QHBoxLayout(self.position_wrapper)
        position_layout.setContentsMargins(0, 0, 0, 0)
        position_layout.setSpacing(0)
        position_layout.addWidget(self.position_edit)
        self.calibrate_button = QToolButton()
        self.calibrate_button.setObjectName("iconButton")
        self.calibrate_button.setFixedSize(32, 32)
        self.calibrate_button.setIcon(location_icon())
        self.calibrate_button.setIconSize(QSize(18, 18))
        self.calibrate_button.setCursor(Qt.PointingHandCursor)
        self.calibrate_button.setToolTip("Localiser le bouton Zaap")
        self.position_divider = QFrame(self)
        self.position_divider.setObjectName("Divider")
        self.position_divider.setFixedSize(1, 32)
        self.position_divider.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        input_layout.addWidget(self.zaap_label)
        input_layout.addWidget(self.search_input, 1)
        if self.show_position_controls:
            input_layout.addWidget(self.position_label)
            input_layout.addWidget(self.position_wrapper)
            input_layout.addWidget(self.lock_button)
            input_layout.addWidget(self.calibrate_button)
        else:
            self.position_divider.hide()
            self.position_label.hide()
            self.position_wrapper.hide()
            self.lock_button.hide()
            self.calibrate_button.hide()
        layout.addLayout(input_layout)
        self.favorites_row = QWidget(self)
        self.favorites_row.setObjectName("ZaapFavoritesRow")
        self.favorites_layout = QHBoxLayout(self.favorites_row)
        self.favorites_layout.setContentsMargins(0, 0, 0, 0)
        self.favorites_layout.setSpacing(8)
        self.favorites_label = QLabel("Favoris :")
        self.favorites_label.setObjectName("CompactLabel")
        self.favorites_label.setFixedSize(62, 28)
        self.favorites_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.favorites_layout.addWidget(self.favorites_label)
        self.favorites_layout.addStretch(1)
        layout.addWidget(self.favorites_row)
        self.favorites_row.setVisible(False)
        self.search_input.setMinimumWidth(220 if self.show_position_controls else 260)
        self.search_input.setMaximumWidth(16777215)
        self.search_input.setFixedHeight(32)
        self.search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMaximumHeight(68 if self.show_favorites else 32)
        self.search_input.textEdited.connect(self.refresh_results)
        self.search_input.returnPressed.connect(self.launch_selected)
        self.suggestion_popup.itemEntered.connect(self.highlight_suggestion_item)
        self.suggestion_popup.itemPressed.connect(self.launch_suggestion_item)
        if self.show_position_controls:
            self.lock_button.clicked.connect(self.toggle_position_lock)
            self.position_edit.editingFinished.connect(self.save_position_edit)
            self.calibrate_button.clicked.connect(self.begin_calibration)
        self.apply_position_lock()
        if self.show_favorites:
            self.refresh_favorite_chips()
        self.refresh_results("")

    def refresh_results(self, text: str) -> None:
        rows = self.search(text)
        self.filtered_zaaps = rows
        self.populate_suggestions(rows)
        if text.strip() and rows and self.search_input.hasFocus():
            self.show_suggestions()
        else:
            self.hide_suggestions()

    def populate_suggestions(self, rows: list[dict[str, Any]]) -> None:
        self.suggestion_popup.blockSignals(True)
        self.suggestion_popup.clear()
        for row in rows[:8]:
            label = self.suggestion_label(row)
            if self.show_favorites:
                label = f"{self.favorite_marker(row)} {label}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, row)
            item.setToolTip(self.suggestion_tooltip(row))
            item.setSizeHint(QSize(0, 28))
            self.suggestion_popup.addItem(item)
        if self.suggestion_popup.count():
            self.suggestion_popup.setCurrentRow(0)
        self.suggestion_popup.blockSignals(False)

    def suggestion_label(self, row: dict[str, Any]) -> str:
        label = str(row.get("label") or row.get("name") or row.get("search") or "Zaap").strip()
        return re.sub(r"\s+", " ", label)

    def favorite_marker(self, row: dict[str, Any]) -> str:
        if not self.show_favorites:
            return ""
        return "★" if self.is_favorite(row) else "☆"

    def is_favorite(self, row: dict[str, Any]) -> bool:
        if not self.show_favorites:
            return False
        key = normalize_key(zaap_favorite_name(row))
        return bool(key and key in {normalize_key(name) for name in self.favorite_names})

    def toggle_favorite(self, row: dict[str, Any]) -> None:
        if not self.show_favorites:
            return
        name = zaap_favorite_name(row)
        key = normalize_key(name)
        if not key:
            return
        current = [favorite for favorite in self.favorite_names if normalize_key(favorite)]
        if key in {normalize_key(favorite) for favorite in current}:
            current = [favorite for favorite in current if normalize_key(favorite) != key]
            message = f"Favori Zaap retire: {name}"
        else:
            current.append(name)
            message = f"Favori Zaap ajoute: {name}"
        self.favorite_names = save_zaap_favorites(current, self.zaaps)
        self.populate_suggestions(self.filtered_zaaps)
        self.refresh_favorite_chips()
        self.status_callback(message)

    def refresh_favorite_chips(self) -> None:
        if not self.show_favorites:
            self.favorite_buttons = []
            self.favorite_star_buttons = []
            self.favorites_row.setVisible(False)
            return
        while self.favorites_layout.count() > 1:
            item = self.favorites_layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.favorite_buttons = []
        self.favorite_star_buttons = []
        lookup = zaap_favorite_lookup(self.zaaps)
        rows: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        for name in self.favorite_names:
            key = normalize_key(name)
            if not key or key in seen:
                continue
            row = lookup.get(key)
            if row is None:
                continue
            rows.append((name, row))
            seen.add(key)
            if len(rows) >= 8:
                break
        for name, row in rows:
            chip = QWidget(self.favorites_row)
            chip.setObjectName("favoriteChip")
            chip.setAttribute(Qt.WA_Hover, True)
            chip.setFixedHeight(28)
            chip.setMaximumWidth(190)
            chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 0, 10, 0)
            chip_layout.setSpacing(4)
            star_button = QToolButton(chip)
            star_button.setObjectName("favoriteChipStar")
            star_button.setText("★")
            star_button.setFixedSize(16, 26)
            star_button.setCursor(Qt.PointingHandCursor)
            star_button.setToolTip(f"Retirer {name} des favoris")
            button = QPushButton(short_label(name, 24), chip)
            button.setObjectName("favoriteChipName")
            button.setFixedHeight(26)
            button.setMaximumWidth(152)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(name)
            star_button.clicked.connect(lambda _checked=False, value=row: self.toggle_favorite(value))
            button.clicked.connect(lambda _checked=False, value=row: self.launch_zaap(value))
            chip_layout.addWidget(star_button)
            chip_layout.addWidget(button)
            self.favorite_star_buttons.append(star_button)
            self.favorite_buttons.append(button)
            self.favorites_layout.addWidget(chip)
        self.favorites_layout.addStretch(1)
        self.favorites_row.setVisible(bool(rows))

    def suggestion_tooltip(self, row: dict[str, Any]) -> str:
        details = []
        for key in ("region", "area", "zone", "subarea", "subArea"):
            details.extend(row_text_values(row, (key,)))
        coords = row_coordinate_pair(row)
        if coords is not None:
            details.append(f"{coords[0]},{coords[1]}")
        clean_details = []
        seen = set()
        for detail in details:
            text = re.sub(r"\s+", " ", str(detail)).strip()
            key = normalize_key(text)
            if text and key not in seen:
                seen.add(key)
                clean_details.append(text)
        label = self.suggestion_label(row)
        return label if not clean_details else f"{label}\n" + " - ".join(clean_details[:3])

    def highlight_suggestion_item(self, item: QListWidgetItem) -> None:
        self.suggestion_popup.setCurrentItem(item)

    def show_suggestions(self) -> None:
        if not self.suggestion_popup.count():
            self.hide_suggestions()
            return
        row_height = max(28, self.suggestion_popup.sizeHintForRow(0))
        visible_rows = min(8, self.suggestion_popup.count())
        width = max(self.search_input.width() + 120, 320)
        height = 8 + row_height * visible_rows
        anchor = self.search_input.mapToGlobal(QPoint(0, self.search_input.height() + 3))
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            width = min(width, max(260, area.width() - 24))
            x = min(max(anchor.x(), area.left() + 8), area.right() - width - 8)
            y = anchor.y()
            if y + height > area.bottom() - 8:
                y = self.search_input.mapToGlobal(QPoint(0, -height - 3)).y()
            anchor = QPoint(x, max(area.top() + 8, y))
        self.suggestion_popup.setFixedSize(width, height)
        self.suggestion_popup.move(anchor)
        self.suggestion_popup.show()
        self.suggestion_popup.raise_()
        self.search_input.setFocus(Qt.OtherFocusReason)

    def hide_suggestions(self) -> None:
        self.suggestion_popup.hide()

    def _schedule_owned_callback(self, delay_ms: int, callback: Callable[[], None]) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.timeout.connect(timer.deleteLater)
        timer.start(max(0, int(delay_ms)))

    def hideEvent(self, event) -> None:
        self.hide_suggestions()
        super().hideEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.hide_suggestions()
        super().closeEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if self.show_favorites and watched is self.suggestion_popup.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                point = event.position().toPoint() if hasattr(event, "position") else event.pos()
                item = self.suggestion_popup.itemAt(point)
                if item is not None and point.x() <= 26:
                    zaap = item.data(Qt.UserRole)
                    if isinstance(zaap, dict):
                        self.toggle_favorite(zaap)
                        return True
        if watched is self.search_input and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Escape and self.suggestion_popup.isVisible():
                self.hide_suggestions()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter) and self.suggestion_popup.isVisible():
                self.launch_current_suggestion()
                return True
            if key in (Qt.Key_Down, Qt.Key_Up):
                if not self.suggestion_popup.isVisible() and self.suggestion_popup.count() and self.search_input.text().strip():
                    self.show_suggestions()
                self.move_suggestion_selection(1 if key == Qt.Key_Down else -1)
                return True
        if watched is self.search_input and event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress):
            if self.search_input.text().strip() and self.suggestion_popup.count():
                self._schedule_owned_callback(0, self.show_suggestions)
        if watched is self.search_input and event.type() == QEvent.FocusOut:
            self._schedule_owned_callback(120, self.hide_suggestions_if_idle)
        return super().eventFilter(watched, event)

    def move_suggestion_selection(self, delta: int) -> None:
        count = self.suggestion_popup.count()
        if not count:
            return
        current = self.suggestion_popup.currentRow()
        if current < 0:
            current = 0 if delta >= 0 else count - 1
        else:
            current = (current + delta) % count
        self.suggestion_popup.setCurrentRow(current)
        self.suggestion_popup.scrollToItem(self.suggestion_popup.currentItem())

    def hide_suggestions_if_idle(self) -> None:
        if not self.search_input.hasFocus() and not self.suggestion_popup.underMouse():
            self.hide_suggestions()

    def search(self, text: str) -> list[dict[str, Any]]:
        scored = []
        min_score = zaap_search_min_score(text)
        for row in self.zaaps:
            score = zaap_search_score(row, text)
            if not text.strip() or score >= min_score:
                scored.append((score, normalize_key(row.get("label")), row))
        return [row for _score, _label, row in sorted(scored, key=lambda part: (-part[0], part[1]))[:60]]

    def selected_zaap(self) -> dict[str, Any] | None:
        text = self.search_input.text().strip()
        if not text:
            return None
        exact = self.find_zaap_by_label(text, self.filtered_zaaps)
        if exact is not None:
            return exact
        rows = self.search(text)
        return rows[0] if rows else None

    def find_zaap_by_label(self, text: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        key = normalize_key(text)
        for row in rows:
            if normalize_key(row.get("label")) == key:
                return row
        return None

    def launch_selected(self) -> None:
        if self.suggestion_popup.isVisible() and self.suggestion_popup.currentItem() is not None:
            if self.launch_current_suggestion():
                return
        zaap = self.selected_zaap()
        if not zaap:
            self.status_callback("Zaap introuvable.")
            return
        self.launch_zaap(zaap)

    def launch_current_suggestion(self) -> bool:
        item = self.suggestion_popup.currentItem()
        if item is None:
            return False
        zaap = item.data(Qt.UserRole)
        if not isinstance(zaap, dict):
            return False
        self.launch_zaap(zaap)
        return True

    def launch_suggestion_item(self, item: QListWidgetItem) -> None:
        zaap = item.data(Qt.UserRole)
        if isinstance(zaap, dict):
            self.launch_zaap(zaap)

    def launch_zaap(self, zaap: dict[str, Any]) -> None:
        if self.launching_zaap:
            return
        self.launching_zaap = True
        label = self.suggestion_label(zaap)
        search = zaap_runtime_search_text(zaap)
        coords = row_coordinate_pair(zaap)
        try:
            self.search_input.setText(label)
            if self.config_update_callback is not None:
                self.config_update_callback()
            if self.start_callback is not None:
                position = read_zaap_click_position()
                ratios = read_zaap_button_ratios()
                invoke_compatible_callback(self.start_callback, search, position, ratios)
            self.hide_suggestions()
            LOGGER.info("Auto zaap selection: label=%s search=%s coords=%s", label, search, coords)
            self.status_callback(f"Auto zaap lance: {label}")
        finally:
            self._schedule_owned_callback(0, self.reset_launch_guard)

    def reset_launch_guard(self) -> None:
        self.launching_zaap = False

    def apply_position_lock(self) -> None:
        self.position_edit.setReadOnly(self.position_locked)
        self.lock_button.setText("")
        self.lock_button.setIcon(lock_icon(self.position_locked))
        self.lock_button.setToolTip("")

    def toggle_position_lock(self) -> None:
        if not self.position_locked:
            self.save_position_edit()
        self.position_locked = not self.position_locked
        save_zaap_click_locked(self.position_locked)
        self.apply_position_lock()

    def save_position_edit(self) -> None:
        position = save_zaap_click_position(self.position_edit.text())
        self.position_edit.setText(format_zaap_click_position(position))
        if self.config_update_callback is not None:
            self.config_update_callback()

    def begin_calibration(self) -> None:
        if self.calibration_active:
            return
        self.calibration_active = True
        self.calibrate_button.setEnabled(False)
        for remaining in (3, 2, 1):
            delay = (3 - remaining) * 1000
            self._schedule_owned_callback(delay, lambda value=remaining: self.status_callback(
                f"Calibration Zaap: place la souris sur le bouton Zaap dans Dofus ({value}s)."
            ))
        self._schedule_owned_callback(3000, self.finish_calibration)

    def finish_calibration(self) -> None:
        try:
            result = calibrate_zaap_button_from_mouse()
        except Exception as exc:
            self.status_callback(f"Calibration Zaap impossible: {exc}")
        else:
            ratios = result["ratios"]
            fallback = result["fallback_click_position"]
            self.position_edit.setText(format_zaap_click_position(fallback))
            if self.config_update_callback is not None:
                self.config_update_callback()
            self.status_callback(
                "Calibration Zaap enregistree: "
                f"x={format_zaap_ratio(ratios[0])}, y={format_zaap_ratio(ratios[1])}."
            )
        finally:
            self.calibration_active = False
            self.calibrate_button.setEnabled(True)
