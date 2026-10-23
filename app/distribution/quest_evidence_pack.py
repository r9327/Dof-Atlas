"""Read-only, bounded quest preparation facts from an approved data pack.

The only runtime overlay supported here is atlas-quest-guide-evidence/v1:
per-quest item/combat preparation facts. Generic Documentalist batches or
complete game-source JSON cannot silently overwrite the Doduda quest catalog.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from .data_pack_plan import InvalidDataPack
from .data_pack_store import accepted_pack

_MAX_BYTES = 1024 * 1024
_MAX_QUESTS = 5000
_MAX_ROWS = 48
_POSITIVE = re.compile(r"[1-9][0-9]{0,9}\Z", re.ASCII)


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidDataPack("duplicate quest evidence field")
        result[key] = value
    return result


def _positive(value: object) -> bool:
    return type(value) is int and 0 < value <= 2**31 - 1


def _name(value: object) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= 160
            and not any(ord(char) < 32 for char in value))


def _facts(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"items", "combats"}:
        raise InvalidDataPack("invalid quest guide facts")
    items, combats = value["items"], value["combats"]
    if (not isinstance(items, list) or not isinstance(combats, list)
            or len(items) > _MAX_ROWS or len(combats) > _MAX_ROWS):
        raise InvalidDataPack("quest evidence row budget exceeded")
    item_records: list[dict[str, object]] = []
    combat_records: list[dict[str, object]] = []
    item_keys, combat_keys = set(), set()
    for row in items:
        if (not isinstance(row, dict) or set(row) != {"item_id", "name", "quantity"}
                or not _positive(row["item_id"]) or not _name(row["name"])
                or not _positive(row["quantity"]) or row["quantity"] > 100000):
            raise InvalidDataPack("invalid quest item fact")
        key = row["item_id"]
        if key in item_keys:
            raise InvalidDataPack("duplicate quest item")
        item_keys.add(key)
        item_records.append(dict(row))
    for row in combats:
        if (not isinstance(row, dict) or set(row) != {"objective_id", "monster", "quantity"}
                or not _positive(row["objective_id"]) or not _name(row["monster"])
                or not _positive(row["quantity"]) or row["quantity"] > 100000):
            raise InvalidDataPack("invalid quest combat fact")
        key = row["objective_id"]
        if key in combat_keys:
            raise InvalidDataPack("duplicate combat objective")
        combat_keys.add(key)
        combat_records.append(dict(row))
    return {"items": item_records, "combats": combat_records}


def load_accepted_quest_guide_evidence(root: Path) -> dict[int, dict[str, object]]:
    """Return a verified snapshot, never mutate bundled files.

    Call lazily from a quest provider instance; re-open the provider on app
    restart after package updates. Per-instance cache avoids repeated hashes.
    """
    blob = accepted_pack(root, "quests")
    if blob is None:
        return {}
    if blob.stat().st_size > _MAX_BYTES:
        raise InvalidDataPack("runtime quest evidence pack exceeds 1 MiB")
    try:
        with blob.open("rb") as stream:
            payload = json.loads(
                stream.read(_MAX_BYTES + 1).decode("utf-8"),
                object_pairs_hook=_unique,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
            )
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, InvalidDataPack):
            raise
        raise InvalidDataPack("invalid quest evidence JSON") from exc
    if (not isinstance(payload, dict) or set(payload) != {"schema", "quests"}
            or payload["schema"] != "atlas-quest-guide-evidence/v1"
            or not isinstance(payload["quests"], dict)
            or not 1 <= len(payload["quests"]) <= _MAX_QUESTS):
        raise InvalidDataPack("unrecognized quest evidence pack schema")
    result: dict[int, dict[str, object]] = {}
    for ident, raw in payload["quests"].items():
        if not isinstance(ident, str) or not _POSITIVE.fullmatch(ident):
            raise InvalidDataPack("invalid quest ID in pack")
        result[int(ident)] = _facts(raw)
    return result
