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


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _write(path: Path, payload: object) -> tuple[str, int]:
    content = _json_bytes(payload)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest(), len(content)


def _manifest(directory: Path) -> dict:
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("field") != "quests":
        raise ValueError("Version ou famille de shards incompatible")
    if not isinstance(manifest.get("index"), dict) or not isinstance(manifest.get("shards"), dict):
        raise ValueError("Index de shards invalide")
    return manifest


def verify(source: Path, directory: Path, *, cache_root: Path) -> dict:
    """Fail closed: source SHA, ID coverage and every nested value must match."""
    source, directory = Path(source), Path(directory)
    manifest = _manifest(directory)
    if source.name != manifest.get("source_name"):
        raise ValueError("Nom de source incompatible")
    if source.stat().st_size != manifest.get("source_bytes") or sha256_file(source) != manifest.get("source_sha256"):
        raise ValueError("Source différente : dérivés périmés")
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
    source = Path(source).resolve()
    output_root = Path(output_root).resolve()
    if source.name != "quests_enriched.json":
        raise ValueError("Ce producteur est réservé à quests_enriched.json")
    if not source.is_file() or source.is_symlink():
        raise ValueError("Source canonique inaccessible")
    if ids_per_shard < 1 or ids_per_shard > 4096:
        raise ValueError("ids_per_shard hors limites")
    if output_root == source.parent or source.parent in output_root.parents:
        raise ValueError("Ne pas publier de dérivés dans les sources canoniques")

    output_root.mkdir(parents=True, exist_ok=True)
    versions = output_root / "versions"
    versions.mkdir(exist_ok=True)
    cache = Path(cache_root) if cache_root is not None else output_root / "source_offsets"
    before_size = source.stat().st_size
    before_sha = sha256_file(source)
    version_name = "quests_v1_" + before_sha
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

    # The active pointer is small and atomic; previous versions remain for rollback.
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
    return manifest


def current_directory(output_root: Path) -> Path:
    output_root = Path(output_root).resolve()
    pointer = json.loads((output_root / "active.json").read_text(encoding="utf-8"))
    version = pointer.get("version")
    if pointer.get("schema_version") != 1 or not isinstance(version, str) or not re.fullmatch(r"quests_v1_[0-9a-f]{64}", version):
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
    args = parser.parse_args()
    cache = args.output / "source_offsets"
    if args.verify_only:
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
