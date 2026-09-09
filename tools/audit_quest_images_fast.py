from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

QUEST_IMAGES = ROOT / "data" / "encyclopedia" / "images" / "quests"

SCAN_ROOTS = [
    ROOT / "app",
    ROOT / "config",
    ROOT / "data" / "encyclopedia",
    ROOT / "data" / "local",
    ROOT / "data" / "routes",
]

ARTIFACTS = ROOT / "artifacts"

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
}

TEXT_EXTENSIONS = {
    ".py",
    ".json",
    ".jsonl",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
}

IGNORE_PARTS = {
    ".git",
    "__pycache__",
    "artifacts",
    "reports",
    "cache",
    "backups",
    "archive",
    ".cache",
}

# Cherche directement des chemins/noms d'images dans le texte.
IMAGE_TOKEN_RE = re.compile(
    r"""(?i)
    (?:
        [A-Za-z]:[\\/][^"'<>|\r\n]+?
        |
        (?:data|app|assets|images)[\\/][^"'<>|\r\n]+?
        |
        [A-Za-z0-9_.\- /\\]+?
    )
    \.(?:png|jpe?g|webp|gif|bmp)
    """,
    re.VERBOSE,
)


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)

    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024

    return f"{size} B"


def norm(value: str) -> str:
    value = value.strip().strip("\"'")

    value = value.replace("\\", "/")

    while "//" in value:
        value = value.replace("//", "/")

    return value.casefold()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def should_ignore(path: Path) -> bool:
    parts = {p.casefold() for p in path.parts}

    return any(part.casefold() in parts for part in IGNORE_PARTS)


def collect_images():
    print("\n[1/6] Scan des images de quêtes...")

    images = []

    if not QUEST_IMAGES.exists():
        raise SystemExit(
            f"Dossier introuvable : {QUEST_IMAGES}"
        )

    for i, path in enumerate(QUEST_IMAGES.rglob("*"), 1):
        if not path.is_file():
            continue

        if path.suffix.casefold() not in IMAGE_EXTENSIONS:
            continue

        try:
            size = path.stat().st_size
        except OSError:
            continue

        rel = path.relative_to(ROOT).as_posix()

        images.append({
            "path": path,
            "rel": rel,
            "rel_norm": norm(rel),
            "name": path.name,
            "name_norm": path.name.casefold(),
            "size": size,
        })

        if len(images) % 1000 == 0:
            print(
                f"  {len(images):,} images trouvées...",
                flush=True,
            )

    return images


def hash_images(images):
    print("\n[2/6] Calcul SHA-256...")

    groups = defaultdict(list)
    total = len(images)

    for i, img in enumerate(images, 1):
        try:
            digest = sha256_file(img["path"])
        except OSError as exc:
            img["sha256"] = None
            img["hash_error"] = str(exc)
            continue

        img["sha256"] = digest
        groups[digest].append(img)

        if i % 1000 == 0 or i == total:
            print(
                f"  {i:,}/{total:,}",
                flush=True,
            )

    return groups


def build_indexes(images):
    by_full_path = defaultdict(list)
    by_suffix = defaultdict(list)
    by_name = defaultdict(list)

    for img in images:
        rel = img["rel_norm"]

        by_full_path[rel].append(img)

        # Plusieurs suffixes utiles :
        # data/encyclopedia/images/quests/foo/bar.webp
        # encyclopedia/images/quests/foo/bar.webp
        # images/quests/foo/bar.webp
        # quests/foo/bar.webp
        pieces = rel.split("/")

        for n in (2, 3, 4, 5, 6):
            if len(pieces) >= n:
                suffix = "/".join(pieces[-n:])
                by_suffix[suffix].append(img)

        by_name[img["name_norm"]].append(img)

    return by_full_path, by_suffix, by_name


def iter_text_files():
    seen = set()

    for base in SCAN_ROOTS:
        if not base.exists():
            continue

        for path in base.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.casefold() not in TEXT_EXTENSIONS:
                continue

            if should_ignore(path):
                continue

            try:
                resolved = path.resolve()
            except OSError:
                resolved = path

            key = str(resolved).casefold()

            if key in seen:
                continue

            seen.add(key)

            yield path


def match_token(
    token,
    by_full_path,
    by_suffix,
    by_name,
):
    token_norm = norm(token)

    results = {}

    # Exact relatif complet.
    for img in by_full_path.get(token_norm, []):
        results[img["rel_norm"]] = img

    # Cas chemin absolu contenant /data/...
    marker = "/data/"

    if marker in token_norm:
        candidate = "data/" + token_norm.split(marker, 1)[1]

        for img in by_full_path.get(candidate, []):
            results[img["rel_norm"]] = img

    # Suffixes.
    pieces = token_norm.split("/")

    for n in (6, 5, 4, 3, 2):
        if len(pieces) < n:
            continue

        suffix = "/".join(pieces[-n:])

        matches = by_suffix.get(suffix, [])

        # Suffisamment précis.
        if matches:
            for img in matches:
                results[img["rel_norm"]] = img

            break

    # Nom seul uniquement s'il est unique physiquement.
    name = pieces[-1]

    name_matches = by_name.get(name, [])

    if len(name_matches) == 1:
        img = name_matches[0]
        results[img["rel_norm"]] = img

    return list(results.values())


def scan_references(images):
    print(
        "\n[3/6] Scan rapide des références runtime/code..."
    )

    (
        by_full_path,
        by_suffix,
        by_name,
    ) = build_indexes(images)

    text_files = list(iter_text_files())

    print(
        f"  {len(text_files)} fichiers texte à scanner."
    )

    refs = defaultdict(list)

    for idx, path in enumerate(text_files, 1):
        try:
            text = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except OSError:
            continue

        # Une passe regex par fichier.
        tokens = set(
            m.group(0)
            for m in IMAGE_TOKEN_RE.finditer(text)
        )

        for token in tokens:
            matches = match_token(
                token,
                by_full_path,
                by_suffix,
                by_name,
            )

            for img in matches:
                refs[img["rel_norm"]].append({
                    "file": path.relative_to(ROOT).as_posix(),
                    "token": token,
                })

        if idx % 20 == 0 or idx == len(text_files):
            print(
                f"  {idx}/{len(text_files)} fichiers scannés...",
                flush=True,
            )

    return refs


def analyse(images, hash_groups, refs):
    print("\n[4/6] Analyse...")

    duplicate_groups = {
        digest: group
        for digest, group in hash_groups.items()
        if len(group) > 1
    }

    duplicate_copies = sum(
        len(group) - 1
        for group in duplicate_groups.values()
    )

    recoverable_bytes = sum(
        sum(img["size"] for img in group)
        - max(img["size"] for img in group)
        for group in duplicate_groups.values()
    )

    referenced = []
    unreferenced = []

    for img in images:
        if refs.get(img["rel_norm"]):
            referenced.append(img)
        else:
            unreferenced.append(img)

    referenced_duplicate_groups = 0
    totally_unreferenced_duplicate_groups = 0

    for group in duplicate_groups.values():
        group_ref_count = sum(
            bool(refs.get(img["rel_norm"]))
            for img in group
        )

        if group_ref_count:
            referenced_duplicate_groups += 1
        else:
            totally_unreferenced_duplicate_groups += 1

    return {
        "images_total": len(images),
        "bytes_total": sum(
            img["size"]
            for img in images
        ),
        "unique_sha256": len(hash_groups),
        "duplicate_groups": len(duplicate_groups),
        "duplicate_copies": duplicate_copies,
        "recoverable_bytes": recoverable_bytes,
        "referenced_images": len(referenced),
        "unreferenced_images": len(unreferenced),
        "duplicate_groups_with_reference":
            referenced_duplicate_groups,
        "duplicate_groups_without_reference":
            totally_unreferenced_duplicate_groups,
    }


def write_reports(
    images,
    hash_groups,
    refs,
    stats,
):
    print("\n[5/6] Écriture du rapport...")

    ARTIFACTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = time.strftime("%Y%m%d_%H%M%S")

    json_path = (
        ARTIFACTS
        / f"quest_images_fast_audit_{stamp}.json"
    )

    md_path = (
        ARTIFACTS
        / f"quest_images_fast_audit_{stamp}.md"
    )

    duplicate_groups = []

    for digest, group in hash_groups.items():
        if len(group) < 2:
            continue

        duplicate_groups.append({
            "sha256": digest,
            "count": len(group),
            "size_each": group[0]["size"],
            "files": [
                {
                    "path": img["rel"],
                    "referenced": bool(
                        refs.get(img["rel_norm"])
                    ),
                    "references": refs.get(
                        img["rel_norm"],
                        [],
                    )[:50],
                }
                for img in group
            ],
        })

    duplicate_groups.sort(
        key=lambda x: (
            x["count"],
            x["size_each"],
        ),
        reverse=True,
    )

    unreferenced = [
        {
            "path": img["rel"],
            "sha256": img.get("sha256"),
            "size": img["size"],
        }
        for img in images
        if not refs.get(img["rel_norm"])
    ]

    payload = {
        "generated_at": stamp,
        "root": str(ROOT),
        "quest_images": str(QUEST_IMAGES),
        "stats": stats,
        "duplicate_groups": duplicate_groups,
        "unreferenced_images": unreferenced,
    }

    json_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Audit rapide images de quêtes",
        "",
        "LECTURE SEULE — aucune suppression.",
        "",
        "## Résumé",
        "",
        f"- Images physiques : {stats['images_total']:,}",
        f"- Taille : {human_size(stats['bytes_total'])}",
        f"- SHA-256 uniques : {stats['unique_sha256']:,}",
        f"- Groupes de doublons exacts : {stats['duplicate_groups']:,}",
        f"- Copies exactes supplémentaires : {stats['duplicate_copies']:,}",
        f"- Espace théoriquement récupérable : {human_size(stats['recoverable_bytes'])}",
        f"- Images avec au moins une référence détectée : {stats['referenced_images']:,}",
        f"- Images sans référence détectée : {stats['unreferenced_images']:,}",
        f"- Groupes doublons avec référence : {stats['duplicate_groups_with_reference']:,}",
        f"- Groupes doublons totalement non référencés : {stats['duplicate_groups_without_reference']:,}",
        "",
        "## Important",
        "",
        "Une image marquée sans référence n'est PAS automatiquement supprimable.",
        "Ce rapport sert uniquement à préparer l'audit provenance/runtime.",
        "",
        "## Plus gros groupes de doublons",
        "",
    ]

    for group in duplicate_groups[:100]:
        lines.append(
            f"### {group['sha256']} — {group['count']} copies"
        )

        for item in group["files"]:
            ref = "référencée" if item["referenced"] else "non référencée"

            lines.append(
                f"- `{item['path']}` — {ref}"
            )

        lines.append("")

    md_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return md_path, json_path


def main():
    started = time.time()

    print("=" * 72)
    print("AUDIT RAPIDE DES IMAGES DE QUÊTES")
    print("MODE LECTURE SEULE")
    print("=" * 72)

    images = collect_images()

    hash_groups = hash_images(images)

    refs = scan_references(images)

    stats = analyse(
        images,
        hash_groups,
        refs,
    )

    md_path, json_path = write_reports(
        images,
        hash_groups,
        refs,
        stats,
    )

    elapsed = time.time() - started

    print("\n[6/6] TERMINÉ")
    print()
    print(
        f"Images physiques           : {stats['images_total']:,}"
    )
    print(
        f"SHA-256 uniques            : {stats['unique_sha256']:,}"
    )
    print(
        f"Groupes doublons exacts    : {stats['duplicate_groups']:,}"
    )
    print(
        f"Copies exactes inutiles    : {stats['duplicate_copies']:,}"
    )
    print(
        "Espace récupérable         : "
        + human_size(stats["recoverable_bytes"])
    )
    print(
        f"Images référencées         : {stats['referenced_images']:,}"
    )
    print(
        f"Images sans ref détectée   : {stats['unreferenced_images']:,}"
    )
    print()
    print(f"Rapport MD   : {md_path}")
    print(f"Rapport JSON : {json_path}")
    print(f"Durée        : {elapsed:.1f}s")
    print()
    print("AUCUN FICHIER N'A ÉTÉ MODIFIÉ OU SUPPRIMÉ.")


if __name__ == "__main__":
    main()