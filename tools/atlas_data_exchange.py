"""Atlas adapter for the generic Documentalist batch exchange contract.

Validates source-bound records, kinds and cross-references before diffing.
Never writes Atlas catalogues, modifies progress or optimizes guide routes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re

from .atlas_data_plan import DataRecord, PlannedChange, plan_data_changes

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_KINDS = frozenset({"quest", "success", "guide", "item"})
_MAX_BYTES = 8 * 1024 * 1024


class InvalidDocumentExchange(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AtlasDocumentExchange:
    source: str
    collected_at: str
    source_sha256: str
    records: tuple[DataRecord, ...]


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidDocumentExchange(f"duplicate JSON key {key}")
        result[key] = value
    return result


def _identifier(value: object) -> str:
    if type(value) is int and value >= 0:
        return str(value)
    if (isinstance(value, str) and not isinstance(value, bool)
            and 1 <= len(value) <= 128 and value.strip() == value
            and all(ch.isascii() and (ch.isalnum() or ch in "._:-") for ch in value)):
        return value
    raise InvalidDocumentExchange("invalid Atlas ID")


def load_documentalist_exchange(raw: bytes) -> AtlasDocumentExchange:
    if not isinstance(raw, bytes) or len(raw) > _MAX_BYTES:
        raise InvalidDocumentExchange("batch exceeds 8 MiB or is not bytes")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InvalidDocumentExchange("invalid exchange JSON") from exc
    expected = {"schema", "source", "collected_at", "source_sha256", "records"}
    if not isinstance(doc, dict) or set(doc) != expected or doc["schema"] != "documentalist-batch/v1":
        raise InvalidDocumentExchange("unknown documentalist schema")
    source, stamp, raw_hash, rows = doc["source"], doc["collected_at"], doc["source_sha256"], doc["records"]
    if (not isinstance(source, str) or len(source) > 2048 or
            not (source.startswith("https://") or source.startswith("local:"))):
        raise InvalidDocumentExchange("invalid document source")
    try:
        observed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("timezone required")
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidDocumentExchange("invalid collection timestamp") from exc
    if not isinstance(raw_hash, str) or not _SHA.fullmatch(raw_hash):
        raise InvalidDocumentExchange("invalid source digest")
    if not isinstance(rows, list) or len(rows) > 20_000:
        raise InvalidDocumentExchange("too many records")
    seen: set[tuple[str, str]] = set()
    records = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "sha256", "payload"}:
            raise InvalidDocumentExchange("invalid normalized record")
        payload, content_sha = row["payload"], row["sha256"]
        if not isinstance(payload, dict) or not isinstance(content_sha, str) or not _SHA.fullmatch(content_sha):
            raise InvalidDocumentExchange("invalid record content")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode("utf-8")
        if sha256(canonical).hexdigest() != content_sha:
            raise InvalidDocumentExchange("normalized record hash mismatch")
        identifier = _identifier(row["id"])
        if "id" not in payload or _identifier(payload["id"]) != identifier:
            raise InvalidDocumentExchange("record ID mismatch")
        kind = payload.get("kind")
        if kind not in _KINDS:
            raise InvalidDocumentExchange("unknown Atlas record kind")
        refs_raw = payload.get("references", [])
        if not isinstance(refs_raw, list) or len(refs_raw) > 500:
            raise InvalidDocumentExchange("invalid references")
        refs = []
        for ref in refs_raw:
            if not isinstance(ref, dict) or set(ref) != {"kind", "id"} or ref["kind"] not in _KINDS:
                raise InvalidDocumentExchange("invalid reference kind")
            refs.append((ref["kind"], _identifier(ref["id"])))
        rec = DataRecord(kind, identifier, content_sha, tuple(refs))
        if rec.key() in seen:
            raise InvalidDocumentExchange("duplicate record identity")
        seen.add(rec.key())
        records.append(rec)
    return AtlasDocumentExchange(source, stamp, raw_hash, tuple(sorted(records, key=lambda r: r.key())))


def plan_documentalist_exchange(
    current: AtlasDocumentExchange, incoming: AtlasDocumentExchange
) -> tuple[PlannedChange, ...]:
    """Missing IDs remain observations, never automatic deletions."""
    return plan_data_changes(current.records, incoming.records)
