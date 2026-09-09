from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def detect_encoding(path: str | Path) -> str:
    raw = Path(path).read_bytes()[:4]
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    return "utf-8"


def load_json_safe(path: str | Path, default: Any = None, warnings: list[str] | None = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding=detect_encoding(path)))
    except Exception as exc:
        if warnings is not None:
            warnings.append(f"JSON illisible: {path} ({exc})")
        return default


def save_json_atomic(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def normalize_text(value: Any) -> str:
    text = repair_mojibake("" if value is None else str(value))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.casefold()).strip()


def slugify(value: Any) -> str:
    text = normalize_text(value)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def safe_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def deep_merge(base: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = dict(base or {})
    for key, value in (incoming or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        elif value not in (None, "", [], {}):
            result[key] = value
        elif key not in result:
            result[key] = value
    return result


def parse_map_position(value: Any) -> tuple[int | None, int | None]:
    if isinstance(value, dict):
        return safe_int(value.get("x")), safe_int(value.get("y"))
    text = str(value or "")
    match = re.search(r"(-?\d+)\s*[,;:/]\s*(-?\d+)", text)
    if not match:
        return None, None
    return safe_int(match.group(1)), safe_int(match.group(2))


def relative_path_safe(path: str | Path, root: str | Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve())).replace("\\", "/")
    except Exception:
        return str(Path(path)).replace("\\", "/")


def repair_mojibake(value: Any) -> str:
    text = "" if value is None else str(value)
    if not any(marker in text for marker in ("Ã", "Â", "Å")):
        return text
    for encoding in ("latin1", "cp1252"):
        try:
            repaired = text.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        if repaired.count("\ufffd") <= text.count("\ufffd"):
            return repaired
    return text


def text_from_locale(value: Any, default: str = "") -> str:
    if isinstance(value, dict):
        for key in ("fr", "fr_FR", "name_fr", "en", "en_US", "name_en"):
            if value.get(key):
                return repair_mojibake(value[key])
        return default
    if isinstance(value, str):
        return repair_mojibake(value)
    return default


def image_basename_from_url(value: Any) -> str:
    match = re.search(r"/([^/?#]+\.(?:png|jpg|jpeg|webp))(?:[?#].*)?$", str(value or ""), flags=re.IGNORECASE)
    return match.group(1) if match else ""


def copy_if_missing(source: str | Path, destination: str | Path) -> bool:
    source = Path(source)
    destination = Path(destination)
    if not source.exists() or destination.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True
