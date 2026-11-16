"""Strict, Qt-free contract for *authorized* source-authored guide blocks.

The original block order, text, colors-as-roles, checkboxes, links and image
bytes are data, not instructions to be summarized. This module does not fetch
remote guides or infer copyrights/permissions from a public URL.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from urllib.parse import urlsplit
from typing import Any

from app.ui.entity_link_roles import ENTITY_LINK_COLOR_ROLES

_MAX_BLOCKS = 128
_MAX_TEXT_CHARS = 16000
_MAX_IMAGE_BYTES = 2 * 1024 * 1024
_MAX_CHECK_ITEMS = 128
_ROLES = frozenset((*ENTITY_LINK_COLOR_ROLES, "plain", "warning"))
_MIMES = frozenset(("image/png", "image/jpeg", "image/webp"))
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z")


class GuideRichContentError(ValueError):
    """Rich source content cannot be represented without losing evidence."""


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT_CHARS:
        raise GuideRichContentError(f"{label}: nonempty bounded source text required")
    return value


def _link(url: Any, label: str) -> None:
    if not isinstance(url, str) or len(url) > 2048 or any(c.isspace() for c in url):
        raise GuideRichContentError(f"{label}: unsafe source link")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise GuideRichContentError(f"{label}: HTTPS source link required")


def _runs(raw: Any, label: str) -> str:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 256:
        raise GuideRichContentError(f"{label}: ordered text runs required")
    chunks: list[str] = []
    for i, run in enumerate(raw):
        field = f"{label}[{i}]"
        if not isinstance(run, dict) or set(run) - {"text", "role", "href"}:
            raise GuideRichContentError(f"{field}: unknown inline source fields")
        text = run.get("text")
        # Separately styled spaces are significant in an exact source export.
        if not isinstance(text, str) or not text or len(text) > _MAX_TEXT_CHARS:
            raise GuideRichContentError(f"{field}.text: nonempty source span required")
        role = run.get("role", "plain")
        if role not in _ROLES:
            raise GuideRichContentError(f"{field}.role: unmapped Dev UI role")
        if "href" in run:
            _link(run["href"], f"{field}.href")
        chunks.append(text)
    plain = "".join(chunks)
    if len(plain) > _MAX_TEXT_CHARS:
        raise GuideRichContentError(f"{label}: source text exceeds limit")
    return plain


def image_bytes(block: dict[str, Any], label: str = "image") -> bytes:
    """Verify embedded source media, including MIME signature, without I/O."""
    mime = block.get("mime")
    digest = block.get("sha256")
    encoded = block.get("data_base64")
    if mime not in _MIMES or not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise GuideRichContentError(f"{label}: typed media and SHA-256 required")
    if not isinstance(encoded, str) or len(encoded) > (_MAX_IMAGE_BYTES * 4 // 3 + 8):
        raise GuideRichContentError(f"{label}: source media exceeds size limit")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise GuideRichContentError(f"{label}: invalid media encoding") from exc
    if not data or len(data) > _MAX_IMAGE_BYTES:
        raise GuideRichContentError(f"{label}: invalid media size")
    valid_signature = (
        (mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"))
        or (mime == "image/jpeg" and data.startswith(b"\xff\xd8\xff"))
        or (mime == "image/webp" and data.startswith(b"RIFF")
            and data[8:12] == b"WEBP")
    )
    if not valid_signature or hashlib.sha256(data).hexdigest() != digest:
        raise GuideRichContentError(f"{label}: media format or digest mismatch")
    return data


def validate_source_rich_blocks(raw: Any, action_text: str, label: str) -> None:
    """Reject loss, unsupported HTML and mismatched source action text.

    Rich blocks replace the generic action prose when present. The *first*
    paragraph must reproduce the exact raw action text, not a rewrite.
    Remaining blocks follow in source order and may carry additional authored
    paragraphs, checklists and embedded immutable images.
    """
    if not isinstance(raw, list) or not 1 <= len(raw) <= _MAX_BLOCKS:
        raise GuideRichContentError(f"{label}: nonempty bounded source blocks required")
    seen_checks: set[str] = set()
    for i, block in enumerate(raw):
        field = f"{label}[{i}]"
        if not isinstance(block, dict):
            raise GuideRichContentError(f"{field}: source block object required")
        kind = block.get("type")
        if kind in {"paragraph", "heading"}:
            allowed = {"type", "runs"} | ({"level"} if kind == "heading" else set())
            if set(block) != ({"type", "runs"} | ({"level"} if "level" in block else set())) or set(block) - allowed:
                raise GuideRichContentError(f"{field}: unexpected source text fields")
            if kind == "heading" and (
                type(block.get("level", 2)) is not int
                or block.get("level", 2) not in (1, 2, 3)
            ):
                raise GuideRichContentError(f"{field}: invalid source heading level")
            plain = _runs(block.get("runs"), f"{field}.runs")
            if i == 0 and (kind != "paragraph" or plain != action_text):
                raise GuideRichContentError(
                    f"{field}: first paragraph must match original action text exactly"
                )
        elif kind == "checklist":
            if set(block) != {"type", "items"}:
                raise GuideRichContentError(f"{field}: unexpected checklist fields")
            items = block["items"]
            if not isinstance(items, list) or not 1 <= len(items) <= _MAX_CHECK_ITEMS:
                raise GuideRichContentError(f"{field}: source checkbox items required")
            for j, item in enumerate(items):
                item_label = f"{field}.items[{j}]"
                if not isinstance(item, dict) or set(item) != {"id", "text", "checked"}:
                    raise GuideRichContentError(f"{item_label}: exact checkbox schema required")
                item_id = item["id"]
                if (not isinstance(item_id, str) or not _ID.fullmatch(item_id)
                        or item_id in seen_checks):
                    raise GuideRichContentError(f"{item_label}: duplicate/invalid checkbox id")
                seen_checks.add(item_id)
                _nonempty(item["text"], f"{item_label}.text")
                if type(item["checked"]) is not bool:
                    raise GuideRichContentError(f"{item_label}: boolean checked required")
        elif kind == "image":
            if set(block) != {"type", "alt", "mime", "sha256", "data_base64"}:
                raise GuideRichContentError(f"{field}: exact embedded image schema required")
            _nonempty(block["alt"], f"{field}.alt")
            image_bytes(block, field)
        else:
            raise GuideRichContentError(
                f"{field}: unsupported rich block {kind!r}; refuse lossy import"
            )
    first = raw[0]
    if first.get("type") != "paragraph":
        raise GuideRichContentError(f"{label}: original action paragraph missing")


__all__ = [
    "GuideRichContentError", "image_bytes", "validate_source_rich_blocks",
]
