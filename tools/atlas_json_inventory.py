"""Inventaire conservateur des JSON suivis par Git (Lot 4).

Aucune modification des sources ni des données utilisateur. Les lecteurs retrouvés
par recherche textuelle sont des *candidats*, pas des dépendances certifiées.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = "data/large_file_contracts.json"
LFS_HEADER = b"version https://git-lfs.github.com/spec/v1"
CODE_SUFFIXES = {".py", ".ps1", ".sh", ".bat", ".js", ".ts", ".yml", ".yaml"}


def tracked_files(root: Path) -> list[str]:
    command = ["git", "-C", str(root), "ls-files", "-z", "--"]
    result = subprocess.run(command, check=True, capture_output=True)
    return sorted(
        path.decode("utf-8", "surrogateescape")
        for path in result.stdout.split(b"\0") if path
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _contracts(root: Path) -> dict[str, dict]:
    path = root / CONTRACT_PATH
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        row["path"]: row
        for row in payload.get("files", [])
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }


def _family(path: str) -> str:
    """Classify tracked content by its owning subsystem, never by file size."""
    normalized = path.replace(chr(92), "/")
    if normalized.startswith("data/encyclopedia/quests/"):
        return "quests"
    if normalized.startswith("data/routes/guide_ultime_manual/"):
        return "guide_manual"
    if normalized.startswith("data/encyclopedia/guides/"):
        return "guide_catalog"
    if normalized.startswith("data/routes/"):
        return "professions_routes"
    if normalized.startswith("data/cartography/"):
        return "cartography"
    if normalized.startswith("data/network/"):
        return "protocol_research"
    if normalized.startswith("data/local/"):
        return "local_static_data"
    if normalized.startswith("data/"):
        return "other_data"
    if normalized.startswith(".ai/"):
        return "ai_context"
    if normalized.startswith(".github/"):
        return "github_policy"
    if normalized.startswith("tests/"):
        return "test_contract"
    if normalized.startswith("tools/"):
        return "tool_contract"
    return "other_tracked_json"


def _decision(path: str, size: int, available: bool) -> tuple[str, str]:
    if not available:
        return "REVIEW", "Source absente, symlink ou pointeur Git LFS non matérialisé"
    if path.startswith("data/routes/guide_ultime_manual/"):
        return "ALREADY_OPTIMIZED", "Guide découpé en chapitres : préserver le manifeste et la progression"
    if path == "data/encyclopedia/quests/quests_enriched.json":
        return "INDEX_ONLY", "Offsets Quêtes/SQLite existants ; auditer les lectures intégrales avant tout shard"
    if path == "data/encyclopedia/quests/image_manifest.json":
        return "REVIEW", "Gros index de provenance offline : mesurer les consommateurs avant partition"
    if path == "data/encyclopedia/quests/source_mapping.json":
        return "REVIEW", "Mapping croisé : vérifier index et usages avant changement de format"
    if size >= 1024 * 1024:
        return "REVIEW", "Fichier >=1 Mio : usage et provenance à confirmer"
    return "KEEP", "Petit fichier ou partition existante : aucun gain de découpage démontré"


def _referencers(root: Path, files: list[str], names: set[str]) -> dict[str, list[str]]:
    """Candidats lexicaux uniquement ; Graphify et le runtime restent nécessaires."""
    found: dict[str, list[str]] = {name: [] for name in names}
    for relative in files:
        path = Path(relative)
        if path.suffix.lower() not in CODE_SUFFIXES or relative.startswith(".cache/"):
            continue
        actual = root / path
        if not actual.is_file() or actual.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            content = actual.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for name in names:
            if name in content:
                found[name].append(relative)
    return found


def audit(root: Path, *, files: list[str] | None = None) -> dict:
    root = Path(root)
    files = tracked_files(root) if files is None else sorted(files)
    json_paths = [path for path in files if path.lower().endswith(".json")]
    basenames = {Path(path).name for path in json_paths}
    referencers = _referencers(root, files, basenames)
    contracts = _contracts(root)
    records = []
    counts: dict[str, int] = {}
    for relative in json_paths:
        path = root / relative
        available = path.is_file() and not path.is_symlink()
        size = path.stat().st_size if available else 0
        lfs_pointer = False
        if available:
            with path.open("rb") as stream:
                lfs_pointer = stream.read(len(LFS_HEADER)) == LFS_HEADER
        usable = available and not lfs_pointer
        decision, reason = _decision(relative, size, usable)
        source_contract = contracts.get(relative, {})
        sha256 = _sha256(path) if usable else None
        expected_sha256 = source_contract.get("sha256")
        if not isinstance(expected_sha256, str):
            expected_sha256 = None
        contract_matches = (
            sha256 == expected_sha256 if sha256 is not None and expected_sha256 else None
        )
        if contract_matches is False:
            decision, reason = "REVIEW", "SHA-256 différent du contrat canonique : vérifier la source"
        record = {
            "path": relative.replace("\\", "/"),
            "family": _family(relative),
            "bytes": size,
            "status": decision,
            "reason": reason,
            "available": usable,
            "lfs_pointer": lfs_pointer,
            "sha256": sha256,
            "contract_sha256": expected_sha256,
            "contract_matches": contract_matches,
            "declared_role": source_contract.get("role"),
            "declared_generator": source_contract.get("generator"),
            "declared_consumers": source_contract.get("consumers", []),
            "consumer_text_candidates": sorted(
                set(referencers.get(Path(relative).name, []))
            ),
            "consumer_graph_verified": False,
            "runtime_profile": "NOT_MEASURED",
        }
        if usable and size <= 256 * 1024:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                record["root_type"] = type(payload).__name__
                record["top_level_entries"] = len(payload) if isinstance(payload, (list, dict)) else None
                if isinstance(payload, dict):
                    record["top_level_keys"] = list(payload)[:25]
            except (OSError, UnicodeError, ValueError) as exc:
                record["parse_error"] = type(exc).__name__
                record["status"] = "REVIEW"
                record["reason"] = "JSON illisible ; ne pas traiter comme fichier valide"
        counts[record["status"]] = counts.get(record["status"], 0) + 1
        records.append(record)

    families: dict[str, dict[str, object]] = {}
    for record in records:
        family = str(record["family"])
        group = families.setdefault(family, {"count": 0, "bytes": 0, "decisions": {}})
        group["count"] += 1
        group["bytes"] += record["bytes"]
        decisions = group["decisions"]
        status = record["status"]
        decisions[status] = decisions.get(status, 0) + 1

    return {
        "schema_version": 1,
        "inventory_method": "git ls-files, local bytes, declared contracts and lexical candidate discovery",
        "notes": [
            "Tracked JSON only; generated local caches, SQLite stores and untracked user state are excluded.",
            "Consumer text candidates are NOT Graphify or runtime proof.",
            "REVIEW and NOT_MEASURED are not PASS or optimization claims.",
            "Contract SHA mismatches are REVIEW, not permission to regenerate canonical network data.",
            "No source or user files are modified by the audit.",
        ],
        "json_count": len(records),
        "total_bytes": sum(item["bytes"] for item in records),
        "decisions": dict(sorted(counts.items())),
        "families": {name: families[name] for name in sorted(families)},
        "files": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lot 4 : inventaire JSON reproductible")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, help="Rapport JSON (ne pas placer dans data/)")
    args = parser.parse_args()
    report = audit(args.root)
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output.resolve()
        data_dir = (args.root / "data").resolve()
        if output == data_dir or data_dir in output.parents:
            parser.error("Ne pas écrire un rapport généré dans data/")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(f"{report['json_count']} JSON, rapport : {output}")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
