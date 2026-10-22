"""Build a *reviewable* Atlas quest-preparation pack from Documentalist batches.

No application file is changed: output is an inert, deterministic JSON blob
for the staged updater. Only explicit, fully typed per-quest preparation
records can become runtime facts; generic quest/success/guide prose cannot.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys

from .atlas_data_exchange import (
    InvalidDocumentExchange, _unique_pairs, load_documentalist_exchange,
)

_ID = re.compile(r"[1-9][0-9]{0,9}\Z", re.ASCII)
_MAX_QUESTS = 5000
_MAX_ROWS = 48
_MAX_PACK = 1024 * 1024


class InvalidQuestEvidence(ValueError):
    pass


def _positive(value: object) -> bool:
    return type(value) is int and 0 < value <= 2**31 - 1


def _text(value: object) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= 160
            and not any(ord(char) < 32 for char in value))


def _validate_preparation(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"items", "combats"}:
        raise InvalidQuestEvidence("preparation must contain items and combats")
    if (not isinstance(value["items"], list) or not isinstance(value["combats"], list)
            or len(value["items"]) > _MAX_ROWS or len(value["combats"]) > _MAX_ROWS):
        raise InvalidQuestEvidence("invalid preparation row budget")
    for field, key, text_key in (("items", "item_id", "name"),
                                 ("combats", "objective_id", "monster")):
        seen = set()
        for row in value[field]:
            if (not isinstance(row, dict) or set(row) != {key, text_key, "quantity"}
                    or not _positive(row[key]) or not _text(row[text_key])
                    or not _positive(row["quantity"]) or row["quantity"] > 100000):
                raise InvalidQuestEvidence("invalid preparation record")
            if row[key] in seen:
                raise InvalidQuestEvidence("duplicate preparation reference")
            seen.add(row[key])
    return value


def build_quest_evidence_packet(raw: bytes) -> bytes:
    """Derive precisely selected data, never infer game IDs or missing counts."""
    # This validates the source hash, each record hash, IDs and reference kinds.
    accepted = load_documentalist_exchange(raw)
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InvalidQuestEvidence("invalid batch JSON") from exc
    known = {(r.kind, r.identifier) for r in accepted.records}
    evidence: dict[str, dict] = {}
    for row in doc["records"]:
        item = row["payload"]
        if item.get("kind") != "quest" or "preparation" not in item:
            continue
        ident = row["id"]
        if (not isinstance(ident, str) or not _ID.fullmatch(ident)
                or ("quest", ident) not in known or int(ident) > 2**31 - 1):
            raise InvalidQuestEvidence("noncanonical quest ID in preparation")
        evidence[ident] = _validate_preparation(item["preparation"])
        if len(evidence) > _MAX_QUESTS:
            raise InvalidQuestEvidence("too many quest preparations")
    if not evidence:
        raise InvalidQuestEvidence("no explicit quest preparation records")
    document = {"schema": "atlas-quest-guide-evidence/v1",
                "quests": {key: evidence[key] for key in sorted(evidence, key=int)}}
    packed = json.dumps(document, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(packed) > _MAX_PACK:
        raise InvalidQuestEvidence("runtime preparation pack exceeds 1 MiB")
    return packed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage a verified quest-preparation pack (no installation)")
    parser.add_argument("batch", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.batch.is_symlink() or not args.batch.is_file() or args.batch.stat().st_size > 8 * 1024 * 1024:
            raise InvalidQuestEvidence("source batch must be a bounded regular file")
        blob = build_quest_evidence_packet(args.batch.read_bytes())
        if args.out.is_symlink():
            raise InvalidQuestEvidence("output cannot be a symlink")
        with args.out.open("xb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        result = {"status": "STAGED_ONLY", "sha256": sha256(blob).hexdigest(),
                  "bytes": len(blob), "path": str(args.out),
                  "installation_performed": False}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (InvalidDocumentExchange, InvalidQuestEvidence, OSError,
            UnicodeError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
