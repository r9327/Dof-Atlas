from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_key(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", strip_accents(value).casefold()).strip("_")


def strip_accents(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_words(value: Any) -> str:
    """Normalize Guide route names with spaces, not identifier underscores."""
    return re.sub(r"[^a-zA-Z0-9]+", " ", strip_accents(value).casefold()).strip()


def normalize_world_label(value: Any, *, casefold: bool = True) -> str:
    """Normalize world labels while preserving the caller's original case policy."""
    text = strip_accents(value).replace("’", "'").strip()
    return text.casefold() if casefold else text.lower()


def clean_auto_group_name(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()
    return re.split(r"(?:^|\s+)-\s+", text, maxsplit=1)[0].strip()


__all__ = ["clean_auto_group_name", "normalize_key", "normalize_words", "normalize_world_label", "strip_accents"]
