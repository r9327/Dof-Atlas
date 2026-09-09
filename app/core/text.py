from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-zA-Z0-9]+", "_", text.casefold()).strip("_")


def strip_accents(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def clean_auto_group_name(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()
    return re.split(r"\s+-\s+", text, maxsplit=1)[0].strip()


__all__ = ["clean_auto_group_name", "normalize_key", "strip_accents"]
