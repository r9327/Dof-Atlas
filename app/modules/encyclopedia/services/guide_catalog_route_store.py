"""Indexed, reconstructible Guide route cache.

The indexed cards retain exact order/IDs/progression metadata. Large walkthrough
lines live in individually compressed SQLite rows and are read only when a sheet
is rendered (or when the player explicitly opens global preparation).
The authored Quest and Guide data remain the sole sources of truth.
"""
from __future__ import annotations

import json
import os
import sqlite3
import zlib
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from typing import Any


SCHEMA = 1
MAX_INDEX_BYTES = 16 * 1024 * 1024
MAX_DETAIL_BYTES = 2 * 1024 * 1024
DETAIL_FIELDS = ("manual_lines", "manual_sections")
LAZY_MARKER = "_catalog_route_detail_lazy"


def indexed_path(legacy_path: Path) -> Path:
    return Path(str(legacy_path) + ".sqlite3")


def compact_card(card: dict[str, Any]) -> dict[str, Any]:
    """Keep stable identities and preparation metadata for all route scans."""
    compact = {key: value for key, value in card.items() if key not in DETAIL_FIELDS}
    sections = card.get("manual_sections")
    if isinstance(sections, dict) and sections.get("prepare"):
        # Global preparation can aggregate all cards without hydrating walkthroughs.
        compact["manual_sections"] = {"prepare": sections["prepare"]}
    compact[LAZY_MARKER] = True
    return compact


def write_indexed_route(service: Any, legacy_path: Path, signature: str) -> Path:
    """Publish a complete new SQLite generation atomically, or leave old one."""
    cards = service.cards
    if not cards:
        raise ValueError("Guide catalogue sans fiches")
    index_route = {
        key: value for key, value in service.route.items() if key != "steps"
    }
    light_cards = [compact_card(card) for card in cards]
    # The global preparation panel scans all stable sheets. Compute its
    # *filtered* preparation exactly once while source cards are still rich:
    # an item acquired on the current map is not a requirement before travel.
    # The panel may then aggregate metadata without 1,672 SQLite reads.
    sections_for_card = getattr(service, "manual_sections_for_card", None)
    if callable(sections_for_card):
        for light, full in zip(light_cards, cards):
            sections = sections_for_card("", full)
            prepared = sections.get("prepare", []) if isinstance(sections, dict) else []
            if prepared:
                light["manual_sections"] = {"prepare": prepared}
            else:
                light.pop("manual_sections", None)
    index_route["steps"] = light_cards
    manifest = {
        "schema": SCHEMA,
        "signature": signature,
        "route": index_route,
        "audit": service.manual_audit_data,
        "common_quest_ids": list(service._common_quest_ids),
    }
    manifest_data = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    if len(manifest_data) > MAX_INDEX_BYTES:
        raise ValueError("Index Guide supérieur au budget")
    path = indexed_path(legacy_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        # sqlite3.Connection.__exit__ commits but does NOT close handles.
        # Windows rejects tmp.replace() while the writer is still open.
        with closing(sqlite3.connect(tmp)) as connection, connection:
            connection.execute("CREATE TABLE metadata (name TEXT PRIMARY KEY, value BLOB NOT NULL)")
            connection.execute("CREATE TABLE details (idx INTEGER PRIMARY KEY, data BLOB NOT NULL)")
            connection.execute(
                "INSERT INTO metadata VALUES (?, ?)", ("manifest", manifest_data)
            )
            # Avoid retaining every compressed walkthrough at once (Sylvestre
            # contains more than a thousand cards). Keep the same SQLite rows,
            # order, and atomic publication while bounding temporary memory.
            rows = []
            for idx, card in enumerate(cards):
                detail = {
                    field: card.get(field, {} if field == "manual_sections" else [])
                    for field in DETAIL_FIELDS
                }
                serialized = json.dumps(
                    detail, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                if len(serialized) > MAX_DETAIL_BYTES:
                    raise ValueError(f"Fiche Guide {idx} supérieure au budget")
                rows.append((idx, zlib.compress(serialized, level=1)))
                if len(rows) == 32:
                    connection.executemany("INSERT INTO details VALUES (?, ?)", rows)
                    rows.clear()
            if rows:
                connection.executemany("INSERT INTO details VALUES (?, ?)", rows)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def restore_indexed_route(service: Any, legacy_path: Path, signature: str) -> bool:
    """Validate the compact manifest before exposing stable card identities."""
    path = indexed_path(legacy_path)
    try:
        if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
            return False
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE name='manifest'"
            ).fetchone()
            if row is None or len(row[0]) > MAX_INDEX_BYTES:
                return False
            data = json.loads(row[0])
            count = connection.execute("SELECT COUNT(*) FROM details").fetchone()[0]
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return False
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return False
    if data.get("signature") != signature:
        return False
    route, audit = data.get("route"), data.get("audit")
    ids = data.get("common_quest_ids")
    if not isinstance(route, dict) or not isinstance(audit, dict):
        return False
    cards = route.get("steps")
    if not isinstance(cards, list) or not cards or count != len(cards):
        return False
    if audit.get("card_count") != len(cards):
        return False
    if route.get("id") != f"catalog_manual_{service.guide_id}":
        return False
    if not all(
        isinstance(card, dict)
        and card.get(LAZY_MARKER) is True
        and isinstance(card.get("manual_stage_id"), str)
        for card in cards
    ):
        return False
    if not isinstance(ids, list) or any(type(qid) is not int for qid in ids):
        return False
    service.route = route
    service.cards = cards
    service.manual_audit_data = audit
    service._common_quest_ids = tuple(ids)
    service._full_success_ids = ()
    service.manual_preview_active = True
    service.manual_preview_chapters = (service.guide_id,)
    service.manual_manifest_active = False
    service.manual_chapters = (service.guide_id,)
    service.manual_preview_error = ""
    service._catalog_detail_store_path = path
    service._catalog_detail_cache = {}
    return True


def load_detail(path: Path, index: int) -> dict[str, Any]:
    """One bounded row, no full-route inflation and no mutable shared tree."""
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        row = connection.execute(
            "SELECT data FROM details WHERE idx=?", (int(index),)
        ).fetchone()
    if (row is None or not isinstance(row[0], bytes)
            or len(row[0]) > MAX_DETAIL_BYTES):
        # A malformed/replaced SQLite BLOB can be a TEXT value. Do not let
        # zlib's TypeError escape the rebuildable-cache error boundary.
        raise ValueError(f"Fiche Guide absente ou invalide: {index}")
    try:
        decompressor = zlib.decompressobj()
        content = decompressor.decompress(row[0], MAX_DETAIL_BYTES + 1)
    except zlib.error as exc:
        # The UI prefetch path handles ValueError, not arbitrary zlib errors.
        # A damaged rebuildable cache must fail closed without crashing Qt.
        raise ValueError(f"Fiche Guide compressée altérée: {index}") from exc
    if (not decompressor.eof or decompressor.unused_data
            or decompressor.unconsumed_tail or len(content) > MAX_DETAIL_BYTES):
        raise ValueError(f"Fiche Guide trop grande ou altérée: {index}")
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError(f"Fiche Guide incorrecte: {index}")
    if not isinstance(data.get("manual_lines"), list):
        raise ValueError(f"Lignes invalides: {index}")
    if not isinstance(data.get("manual_sections"), dict):
        raise ValueError(f"Sections invalides: {index}")
    return data
