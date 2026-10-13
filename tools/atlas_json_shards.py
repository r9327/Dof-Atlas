"""Derived, reversible Quest JSON partitions for offline evaluation (Lot 4).

The canonical enriched JSON is never edited. QuestSources keeps ownership of
its byte offsets. No UI/runtime consumer is switched to the derived format here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from app.quest_source_index import QuestSources

ROOT = Path(__file__).resolve().parents[1]
SAFE_SHARD = re.compile(r"^quests_[0-9]{8}\.json$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_duplicate_json_keys(path: Path) -> None:
    """Stream the canonical JSON and reject lossy duplicate object members.

    json.loads and the existing byte-offset index both apply last-key-wins
    semantics. This offline preflight must detect duplicates at every nesting
    level *before* any derived snapshot is published. Memory stays bounded by
    nesting depth and the largest individual member key, not source size.
    """
    stack: list[set[str] | None] = []  # object key sets, None for arrays
    in_string = False
    escaped = False
    key_bytes: bytearray | None = None
    previous = None
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(256 * 1024), b""):
            for byte in chunk:
                if in_string:
                    if key_bytes is not None:
                        key_bytes.append(byte)
                        if len(key_bytes) > 65536:
                            raise ValueError("Clé JSON anormalement longue")
                    if escaped:
                        escaped = False
                    elif byte == 92:  # backslash
                        escaped = True
                    elif byte == 34:  # closing quote
                        in_string = False
                        if key_bytes is not None:
                            key = json.loads(bytes(key_bytes))
                            members = stack[-1]
                            if key in members:
                                raise ValueError(f"Clé JSON dupliquée : {key!r}")
                            members.add(key)
                        key_bytes = None
                        previous = byte
                    continue

                if byte in (9, 10, 13, 32):
                    continue
                if byte == 34:  # opening quote
                    in_string = True
                    key_bytes = (
                        bytearray(b'"') if stack and stack[-1] is not None
                        and previous in (123, 44) else None
                    )
                elif byte == 123:  # {
                    stack.append(set())
                elif byte == 91:  # [
                    stack.append(None)
                elif byte == 125:  # }
                    if not stack or stack[-1] is None:
                        raise ValueError("Fermeture d'objet JSON invalide")
                    stack.pop()
                elif byte == 93:  # ]
                    if not stack or stack[-1] is not None:
                        raise ValueError("Fermeture de tableau JSON invalide")
                    stack.pop()
                previous = byte
    if in_string or stack:
        raise ValueError("JSON canonique tronqué")


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _write(path: Path, payload: object) -> tuple[str, int]:
    content = _json_bytes(payload)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest(), len(content)


def _manifest(directory: Path) -> dict:
    """Treat every on-disk manifest as untrusted, even when previously published."""
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("field") != "quests":
        raise ValueError("Version ou famille de shards incompatible")
    index, shards = manifest.get("index"), manifest.get("shards")
    if not isinstance(index, dict) or not isinstance(shards, dict):
        raise ValueError("Index de shards invalide")
    count, batch = manifest.get("record_count"), manifest.get("ids_per_shard")
    if (type(count) is not int or count < 0 or type(batch) is not int
            or not 1 <= batch <= 4096 or count != len(index)):
        raise ValueError("Comptage ou granularité de shards invalide")
    if (manifest.get("source_name") != "quests_enriched.json"
            or type(manifest.get("source_bytes")) is not int
            or manifest["source_bytes"] < 0
            or not isinstance(manifest.get("source_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", manifest["source_sha256"]) is None):
        raise ValueError("Identité de la source invalide")
    for name, info in shards.items():
        if (not isinstance(name, str) or SAFE_SHARD.fullmatch(name) is None
                or not isinstance(info, dict)
                or not isinstance(info.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", info["sha256"]) is None
                or type(info.get("bytes")) is not int or info["bytes"] < 1
                or type(info.get("record_count")) is not int or info["record_count"] < 1):
            raise ValueError("Métadonnées de shard invalides")
    observed: dict[str, int] = {}
    for key, name in index.items():
        if (not isinstance(key, str) or not key.isascii() or not key.isdecimal()
                or str(int(key)) != key or not isinstance(name, str)
                or name not in shards
                or name != f"quests_{int(key) // batch:08d}.json"):
            raise ValueError("Index ID→shard incohérent")
        observed[name] = observed.get(name, 0) + 1
    if (sum(info["record_count"] for info in shards.values()) != count
            or any(observed.get(name) != info["record_count"]
                   for name, info in shards.items())):
        raise ValueError("Couverture des shards incohérente")
    return manifest


def verify(source: Path, directory: Path, *, cache_root: Path) -> dict:
    """Fail closed: source SHA, ID coverage and every nested value must match."""
    source, directory = Path(source), Path(directory)
    manifest = _manifest(directory)
    if source.name != manifest.get("source_name"):
        raise ValueError("Nom de source incompatible")
    if source.stat().st_size != manifest.get("source_bytes") or sha256_file(source) != manifest.get("source_sha256"):
        raise ValueError("Source différente : dérivés périmés")
    _reject_duplicate_json_keys(source)
    sources = QuestSources(cache_root)
    try:
        original = sources.mapping(source, "quests", required=True)
        ids = list(original)
        if set(ids) != set(manifest["index"]) or len(ids) != manifest.get("record_count"):
            raise ValueError("IDs manquants, supplémentaires ou dupliqués")
        seen: set[str] = set()
        for name, info in manifest["shards"].items():
            if not SAFE_SHARD.fullmatch(name) or not isinstance(info, dict):
                raise ValueError("Nom de shard interdit")
            path = directory / name
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != info.get("sha256") or len(content) != info.get("bytes"):
                raise ValueError(f"Shard corrompu : {name}")
            payload = json.loads(content)
            rows = payload.get("quests") if isinstance(payload, dict) else None
            if not isinstance(rows, dict) or len(rows) != info.get("record_count"):
                raise ValueError(f"Structure invalide : {name}")
            for key, value in rows.items():
                if key in seen or manifest["index"].get(key) != name or original[key] != value:
                    raise ValueError(f"Parité invalide pour l'ID {key}")
                seen.add(key)
            original.close()  # No retention of decoded rich quest details.
        if seen != set(ids):
            raise ValueError("Couverture des IDs incomplète")
        return manifest
    finally:
        sources.close()


def build(
    source: Path,
    output_root: Path,
    *,
    ids_per_shard: int = 32,
    cache_root: Path | None = None,
) -> dict:
    """Publish immutable content and switch a small pointer only after parity."""
    source_input = Path(source)
    if source_input.is_symlink():
        raise ValueError("Source canonique symlink interdite")
    source = source_input.resolve()
    output_root = Path(output_root).resolve()
    if source.name != "quests_enriched.json":
        raise ValueError("Ce producteur est réservé à quests_enriched.json")
    if not source.is_file() or source.is_symlink():
        raise ValueError("Source canonique inaccessible")
    if ids_per_shard < 1 or ids_per_shard > 4096:
        raise ValueError("ids_per_shard hors limites")
    if (output_root == source.parent or source.parent in output_root.parents
            or output_root in source.parents):
        raise ValueError("Ne pas publier de dérivés dans les sources canoniques")

    output_root.mkdir(parents=True, exist_ok=True)
    versions = output_root / "versions"
    versions.mkdir(exist_ok=True)
    cache = Path(cache_root) if cache_root is not None else output_root / "source_offsets"
    before_size = source.stat().st_size
    before_sha = sha256_file(source)
    _reject_duplicate_json_keys(source)
    version_name = f"quests_v1_{before_sha}_{ids_per_shard:04d}"
    final = versions / version_name

    if final.exists():
        manifest = verify(source, final, cache_root=cache)
    else:
        with tempfile.TemporaryDirectory(prefix="building_", dir=versions) as temp:
            staging = Path(temp)
            sources = QuestSources(cache)
            try:
                rows = sources.mapping(source, "quests", required=True)
                keys = list(rows)
                numeric_ids = [int(key) for key in keys]
                if (any(str(number) != key or number < 0 for key, number in zip(keys, numeric_ids))
                        or len(set(numeric_ids)) != len(keys)):
                    raise ValueError("IDs Quêtes non canoniques, négatifs ou dupliqués")
                group_ids: dict[int, list[str]] = {}
                for key in keys:
                    group_ids.setdefault(int(key) // ids_per_shard, []).append(key)
                index: dict[str, str] = {}
                shards: dict[str, dict] = {}
                for group, members in sorted(group_ids.items()):
                    name = f"quests_{group:08d}.json"
                    if not SAFE_SHARD.fullmatch(name):
                        raise ValueError("Index de partition invalide")
                    data = {key: rows[key] for key in sorted(members, key=int)}
                    digest, size = _write(staging / name, {"quests": data})
                    shards[name] = {"sha256": digest, "bytes": size, "record_count": len(data)}
                    index.update({key: name for key in data})
                    rows.close()
            finally:
                sources.close()
            manifest = {
                "schema_version": 1,
                "source_name": source.name,
                "source_bytes": before_size,
                "source_sha256": before_sha,
                "field": "quests",
                "ids_per_shard": ids_per_shard,
                "record_count": len(keys),
                "index": index,
                "shards": shards,
                "canonical_retained": True,
            }
            _write(staging / "manifest.json", manifest)
            if source.stat().st_size != before_size or sha256_file(source) != before_sha:
                raise ValueError("La source a changé pendant la génération")
            verify(source, staging, cache_root=cache)
            staging.rename(final)

    # Recheck after verification as well: an offline generator may replace the
    # source while we are comparing thousands of records.
    if source.stat().st_size != before_size or sha256_file(source) != before_sha:
        raise ValueError("La source a changé avant publication")
    # Previous versions remain immutable and may be explicitly reactivated.
    _activate_pointer(output_root, version_name)
    return manifest


def _activate_pointer(output_root: Path, version_name: str) -> None:
    if re.fullmatch(r"quests_v1_[0-9a-f]{64}_[0-9]{4}", version_name) is None:
        raise ValueError("Version interdite")
    pointer = {"schema_version": 1, "version": version_name}
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix="active_", suffix=".tmp", dir=output_root, delete=False
    ) as stream:
        temp_pointer = Path(stream.name)
        stream.write(_json_bytes(pointer))
    try:
        os.replace(temp_pointer, output_root / "active.json")
    finally:
        temp_pointer.unlink(missing_ok=True)


def activate_version(
    source: Path, output_root: Path, version_name: str, *, cache_root: Path | None = None
) -> dict:
    """Rollback only to a fully verified snapshot of the CURRENT canonical source."""
    output_root = Path(output_root).resolve()
    if re.fullmatch(r"quests_v1_[0-9a-f]{64}_[0-9]{4}", version_name) is None:
        raise ValueError("Version interdite")
    target = output_root / "versions" / version_name
    if not target.is_dir() or target.is_symlink():
        raise ValueError("Version absente ou lien interdit")
    source = Path(source).resolve()
    cache = Path(cache_root) if cache_root is not None else output_root / "source_offsets"
    manifest = verify(source, target, cache_root=cache)
    if version_name != f"quests_v1_{manifest['source_sha256']}_{manifest['ids_per_shard']:04d}":
        raise ValueError("Nom de version incompatible")
    if (source.stat().st_size != manifest["source_bytes"]
            or sha256_file(source) != manifest["source_sha256"]):
        raise ValueError("La source a changé avant rollback")
    _activate_pointer(output_root, version_name)
    return manifest


def current_directory(output_root: Path) -> Path:
    output_root = Path(output_root).resolve()
    pointer = json.loads((output_root / "active.json").read_text(encoding="utf-8"))
    version = pointer.get("version")
    if pointer.get("schema_version") != 1 or not isinstance(version, str) or not re.fullmatch(r"quests_v1_[0-9a-f]{64}_[0-9]{4}", version):
        raise ValueError("Pointeur actif invalide")
    return output_root / "versions" / version


def read_by_id(output_root: Path, quest_id: int) -> object:
    """Read one derived record with hash validation; caller handles source freshness."""
    directory = current_directory(output_root)
    manifest = _manifest(directory)
    key = str(int(quest_id))
    name = manifest["index"].get(key)
    if name is None:
        raise KeyError(key)
    if not SAFE_SHARD.fullmatch(name):
        raise ValueError("Nom de shard interdit")
    info = manifest["shards"].get(name)
    if not isinstance(info, dict):
        raise ValueError("Shard sans manifeste")
    content = (directory / name).read_bytes()
    if len(content) != info.get("bytes") or hashlib.sha256(content).hexdigest() != info.get("sha256"):
        raise ValueError("Shard corrompu")
    return json.loads(content)["quests"][key]


def main() -> int:
    parser = argparse.ArgumentParser(description="Générer et vérifier les shards Quêtes sans changer la source")
    parser.add_argument("--source", type=Path, default=ROOT / "data/encyclopedia/quests/quests_enriched.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/dofus_atlas/quests_shards")
    parser.add_argument("--ids-per-shard", type=int, default=32)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--activate-version", metavar="VERSION",
                        help="Réactiver un snapshot vérifié de la même source")
    args = parser.parse_args()
    if args.verify_only and args.activate_version:
        parser.error("--verify-only et --activate-version sont incompatibles")
    cache = args.output / "source_offsets"
    if args.activate_version:
        report = activate_version(args.source, args.output, args.activate_version, cache_root=cache)
    elif args.verify_only:
        report = verify(args.source, current_directory(args.output), cache_root=cache)
    else:
        report = build(args.source, args.output, ids_per_shard=args.ids_per_shard, cache_root=cache)
    print(json.dumps({
        "source_sha256": report["source_sha256"],
        "record_count": report["record_count"],
        "shard_count": len(report["shards"]),
        "source_preserved": True,
        "verified": True,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
