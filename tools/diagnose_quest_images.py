from __future__ import annotations

import argparse
import ast
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}

STATUS_FIELDS = {
    "integration_authorized",
    "content_display_eligible",
    "start_map_only",
    "display_eligible",
}

CODE_DIRS = ("app", "tools", "scripts", "tests")

NEEDLES = (
    "quests_enriched.json",
    "image_manifest.json",
    "lot6_work_final_for_codex.json",
    "integration_authorized",
    "content_display_eligible",
    "start_map_only",
    "QPixmap",
    "setPixmap",
    "setVisible",
    ".hide(",
    "image",
    "visual",
    "legacy",
    "documentary",
)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().casefold()


def img_ref(s: Any) -> bool:
    if not isinstance(s, str) or not s.strip():
        return False

    parsed = urlparse(s)
    target = parsed.path if parsed.scheme in {"http", "https", "file"} else s

    return Path(target).suffix.lower() in IMG_EXT


def walk(x: Any, path=()):
    if isinstance(x, dict):
        for k, v in x.items():
            p = path + (str(k),)
            yield p, v
            yield from walk(v, p)

    elif isinstance(x, list):
        for i, v in enumerate(x):
            p = path + (f"[{i}]",)
            yield p, v
            yield from walk(v, p)


def load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f), None

    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def image_refs(obj: Any):
    return [
        (".".join(p), v)
        for p, v in walk(obj)
        if img_ref(v)
    ]


def status_counts(obj: Any):
    out = {k: Counter() for k in STATUS_FIELDS}

    for p, v in walk(obj):
        if p and p[-1] in STATUS_FIELDS:
            out[p[-1]][repr(v)] += 1

    return {
        k: dict(v)
        for k, v in out.items()
        if v
    }


def build_url_map(manifest: Any):
    """
    Essaie de relier URL source -> fichier local
    lorsque les deux apparaissent dans le même bloc du manifeste.
    """
    out = {}

    def rec(x):
        if isinstance(x, dict):
            urls = [
                v
                for v in x.values()
                if isinstance(v, str)
                and v.startswith(("http://", "https://"))
            ]

            local = [
                v
                for v in x.values()
                if isinstance(v, str)
                and img_ref(v)
                and not v.startswith(("http://", "https://"))
            ]

            if urls and local:
                for u in urls:
                    out.setdefault(u, local[0])

            for v in x.values():
                rec(v)

        elif isinstance(x, list):
            for v in x:
                rec(v)

    rec(manifest)

    return out


def resolve_ref(ref: str, root: Path, url_map: dict[str, str]):
    if ref.startswith(("http://", "https://")):
        ref = url_map.get(ref)

        if not ref:
            return None

    ref = ref.replace("/", os.sep)

    p = Path(ref)

    if p.is_absolute():
        return p

    candidates = (
        root / p,
        root / "data" / p,
        root / "data" / "encyclopedia" / p,
        root / "data" / "encyclopedia" / "images" / p,
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return root / p


def summarize_refs(refs, root: Path, url_map):
    unique = {}

    for keypath, ref in refs:
        unique.setdefault(ref, keypath)

    existing = 0
    missing = 0
    unmapped = 0

    missing_samples = []

    for ref, keypath in unique.items():
        p = resolve_ref(ref, root, url_map)

        if p is None:
            unmapped += 1
            continue

        if p.exists():
            existing += 1
        else:
            missing += 1

            if len(missing_samples) < 20:
                missing_samples.append(
                    {
                        "field": keypath,
                        "ref": ref,
                        "resolved": str(p),
                    }
                )

    return {
        "occurrences": len(refs),
        "unique": len(unique),
        "existing": existing,
        "missing": missing,
        "remote_unmapped": unmapped,
        "missing_samples": missing_samples,
    }


def find_quest(obj: Any, query: str):
    q = norm(query)

    hits = []

    def rec(x, path=()):
        if isinstance(x, dict):
            names = [
                x.get(k)
                for k in (
                    "name",
                    "title",
                    "quest_name",
                    "questTitle",
                    "label",
                )
                if isinstance(x.get(k), str)
            ]

            if any(q in norm(name) for name in names):
                hits.append((".".join(path), x))

            for k, v in x.items():
                rec(v, path + (str(k),))

        elif isinstance(x, list):
            for i, v in enumerate(x):
                rec(v, path + (f"[{i}]",))

    rec(obj)

    return hits[:20]


def probe_quest(obj: Any, query: str, root: Path, url_map):
    out = []

    if obj is None:
        return out

    for path, quest in find_quest(obj, query):
        refs = image_refs(quest)

        title = next(
            (
                quest.get(k)
                for k in (
                    "name",
                    "title",
                    "quest_name",
                    "questTitle",
                    "label",
                )
                if isinstance(quest.get(k), str)
            ),
            None,
        )

        out.append(
            {
                "path": path,
                "id": quest.get("id", quest.get("quest_id")),
                "title": title,
                "keys": sorted(map(str, quest.keys())),
                "refs": summarize_refs(refs, root, url_map),
                "status": status_counts(quest),
            }
        )

    return out


def disk_images(root: Path):
    base = root / "data" / "encyclopedia" / "images"

    count = 0
    total = 0
    extensions = Counter()

    if base.exists():
        for p in base.rglob("*"):
            if not p.is_file():
                continue

            if p.suffix.lower() not in IMG_EXT:
                continue

            count += 1
            extensions[p.suffix.lower()] += 1

            try:
                total += p.stat().st_size
            except OSError:
                pass

    return {
        "path": str(base),
        "exists": base.exists(),
        "count": count,
        "bytes": total,
        "gb": round(total / 1024**3, 3),
        "extensions": dict(extensions),
    }


def source_files(root: Path):
    files = []

    for folder in CODE_DIRS:
        base = root / folder

        if not base.exists():
            continue

        files.extend(base.rglob("*.py"))
        files.extend(base.rglob("*.qss"))
        files.extend(base.rglob("*.css"))

    if (root / "main.py").exists():
        files.append(root / "main.py")

    return sorted(set(files))


def scan_code(root: Path):
    hits = defaultdict(list)
    suspicious = []
    functions = []
    syntax_errors = []

    for path in source_files(root):
        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            continue

        rel = str(path.relative_to(root))

        lines = text.splitlines()

        for number, line in enumerate(lines, 1):
            low = line.casefold()

            for needle in NEEDLES:
                if needle.casefold() in low:
                    if len(hits[needle]) < 250:
                        hits[needle].append(
                            (
                                rel,
                                number,
                                line.strip()[:500],
                            )
                        )

            if (
                re.search(
                    r"\bif\b.*(?:integration_authorized|"
                    r"content_display_eligible|"
                    r"start_map_only|legacy|image|visual)",
                    line,
                    re.I,
                )
                or re.search(
                    r"setVisible\s*\(\s*False\s*\)|"
                    r"\.hide\s*\(\s*\)",
                    line,
                )
            ):
                if len(suspicious) < 500:
                    suspicious.append(
                        (
                            rel,
                            number,
                            line.strip()[:500],
                        )
                    )

        if path.suffix == ".py":
            try:
                tree = ast.parse(
                    text,
                    filename=str(path),
                )

                for node in ast.walk(tree):
                    if not isinstance(
                        node,
                        (
                            ast.FunctionDef,
                            ast.AsyncFunctionDef,
                            ast.ClassDef,
                        ),
                    ):
                        continue

                    name = getattr(node, "name", "")
                    n = norm(name)

                    if any(
                        word in n
                        for word in (
                            "quest",
                            "image",
                            "visual",
                            "render",
                            "populate",
                            "guide",
                            "success",
                        )
                    ):
                        functions.append(
                            (
                                rel,
                                getattr(node, "lineno", 0),
                                type(node).__name__,
                                name,
                            )
                        )

            except SyntaxError as e:
                syntax_errors.append(
                    (
                        rel,
                        str(e),
                    )
                )

    return {
        "hits": dict(hits),
        "suspicious": suspicious,
        "functions": functions,
        "syntax_errors": syntax_errors,
    }


def json_info(
    path: Path,
    root: Path,
    url_map,
):
    obj, error = load_json(path)

    if obj is None:
        return None, {
            "path": str(path),
            "error": error,
        }

    refs = image_refs(obj)

    return obj, {
        "path": str(path.relative_to(root)),
        "error": None,
        "refs": summarize_refs(
            refs,
            root,
            url_map,
        ),
        "status": status_counts(obj),
    }


def causes(
    disk,
    quests,
    work,
    code,
    probe_runtime,
    probe_work,
):
    out = []

    qrefs = quests.get("refs", {})
    wstatus = work.get("status", {})

    auth_true = (
        wstatus
        .get("integration_authorized", {})
        .get("True", 0)
    )

    runtime_probe_refs = sum(
        x["refs"]["occurrences"]
        for x in probe_runtime
    )

    work_probe_refs = sum(
        x["refs"]["occurrences"]
        for x in probe_work
    )

    # CAS 1
    if (
        disk["count"]
        and qrefs.get("occurrences", 0) == 0
    ):
        out.append(
            (
                "CRITIQUE",
                "Les images existent sur disque mais "
                "quests_enriched.json ne contient aucune "
                "référence image détectable.",
                "L'intégration Lot 6 n'a probablement pas "
                "été écrite dans la donnée réellement "
                "utilisée au runtime.",
            )
        )

    # CAS 2
    if (
        auth_true
        and qrefs.get("occurrences", 0) == 0
    ):
        out.append(
            (
                "CRITIQUE",
                f"{auth_true} autorisations existent dans "
                f"le registre Lot 6, mais aucune référence "
                f"n'arrive dans quests_enriched.json.",
                "Les décisions sont peut-être restées dans "
                "artifacts/ au lieu d'être injectées dans "
                "les données runtime.",
            )
        )

    # CAS 3
    if (
        qrefs.get("occurrences", 0)
        and qrefs.get("existing", 0) == 0
    ):
        out.append(
            (
                "CRITIQUE",
                "Les données runtime contiennent des "
                "références images, mais aucune ne se "
                "résout vers un fichier existant.",
                "Vérifier la résolution des chemins et "
                "image_manifest.json.",
            )
        )

    # CAS 4 : quête témoin
    if (
        work_probe_refs
        and runtime_probe_refs == 0
    ):
        out.append(
            (
                "CRITIQUE",
                f"La quête témoin possède "
                f"{work_probe_refs} refs côté WORK/CODEX "
                f"mais 0 côté runtime.",
                "Le pont registre Lot 6 -> "
                "quests_enriched/provider est cassé.",
            )
        )

    # CAS 5 : flags de filtre absents
    if (
        code["hits"].get(
            "integration_authorized"
        )
        or code["hits"].get(
            "content_display_eligible"
        )
    ):
        if (
            "integration_authorized"
            not in quests.get("status", {})
        ):
            out.append(
                (
                    "ÉLEVÉE",
                    "Le code contient des filtres Lot 6 "
                    "mais les flags correspondants ne "
                    "sont pas présents dans "
                    "quests_enriched.json.",
                    "Un `if not integration_authorized` "
                    "ou `content_display_eligible` peut "
                    "masquer 100 % des images.",
                )
            )

    # CAS 6 : aucun renderer Qt trouvé
    if (
        qrefs.get("existing", 0)
        and not (
            code["hits"].get("QPixmap")
            or code["hits"].get("setPixmap")
        )
    ):
        out.append(
            (
                "ÉLEVÉE",
                "Des images valides arrivent dans les "
                "données mais aucun renderer Qt d'image "
                "n'a été détecté.",
                "Vérifier que la fiche quête commune "
                "crée toujours ses widgets image.",
            )
        )

    if code["suspicious"]:
        out.append(
            (
                "À VOIR",
                f"{len(code['suspicious'])} conditions "
                f"de filtre/masquage potentiellement "
                f"liées aux images ont été trouvées.",
                "Le rapport donne les fichiers et lignes "
                "exactes.",
            )
        )

    if not out:
        out.append(
            (
                "INFO",
                "Aucune cause certaine trouvée "
                "statiquement.",
                "Il faudra ensuite tracer au runtime : "
                "attendu -> provider -> renderer -> "
                "widget créé -> widget visible.",
            )
        )

    return out


def write_md(
    report,
    path: Path,
):
    lines = []

    lines += [
        "# Diagnostic images de quêtes",
        "",
        f"- Projet : `{report['root']}`",
        f"- Quête témoin : `{report['quest']}`",
        f"- Date : `{report['generated']}`",
        "",
        "## CAUSES PROBABLES",
        "",
    ]

    for severity, why, check in report["causes"]:
        lines += [
            f"- **{severity}** — {why}",
            f"  - À vérifier : {check}",
        ]

    d = report["disk"]

    lines += [
        "",
        "## Images physiques",
        "",
        f"- Dossier : `{d['path']}`",
        f"- Images : **{d['count']}**",
        f"- Taille : **{d['gb']} Go**",
        "",
    ]

    for title, key in (
        (
            "quests_enriched.json",
            "quests",
        ),
        (
            "image_manifest.json",
            "manifest",
        ),
        (
            "Registre WORK/CODEX",
            "work",
        ),
    ):
        info = report[key]

        lines += [
            f"## {title}",
            "",
            f"- Fichier : `{info.get('path')}`",
        ]

        if info.get("error"):
            lines += [
                f"- ERREUR : `{info['error']}`",
                "",
            ]
            continue

        r = info["refs"]

        lines += [
            f"- Occurrences image : **{r['occurrences']}**",
            f"- Références uniques : **{r['unique']}**",
            f"- Fichiers résolus existants : **{r['existing']}**",
            f"- Manquants : **{r['missing']}**",
            f"- URL non mappées : **{r['remote_unmapped']}**",
            f"- Flags : `{info['status']}`",
            "",
        ]

    for title, key in (
        (
            "Quête témoin dans runtime",
            "probe_runtime",
        ),
        (
            "Quête témoin dans WORK/CODEX",
            "probe_work",
        ),
    ):
        lines += [
            f"## {title}",
            "",
        ]

        if not report[key]:
            lines += [
                "- Aucune correspondance.",
                "",
            ]

        for q in report[key]:
            r = q["refs"]

            lines += [
                f"- `{q['title']}` id=`{q['id']}`",
                f"  - chemin JSON : `{q['path']}`",
                f"  - refs : **{r['occurrences']}**",
                f"  - existantes : **{r['existing']}**",
                f"  - manquantes : **{r['missing']}**",
                f"  - flags : `{q['status']}`",
            ]

        lines += [""]

    code = report["code"]

    lines += [
        "## Pipeline code — occurrences importantes",
        "",
    ]

    important = (
        "quests_enriched.json",
        "image_manifest.json",
        "lot6_work_final_for_codex.json",
        "integration_authorized",
        "content_display_eligible",
        "start_map_only",
        "QPixmap",
        "setPixmap",
        "setVisible",
        ".hide(",
    )

    for needle in important:
        arr = code["hits"].get(
            needle,
            [],
        )

        lines += [
            f"### `{needle}` — {len(arr)} hit(s)"
        ]

        for file, number, text in arr[:40]:
            text = text.replace("|", "\\|")

            lines += [
                f"- `{file}:{number}` — `{text}`"
            ]

        lines += [""]

    lines += [
        "## Conditions suspectes",
        "",
    ]

    for file, number, text in code["suspicious"][:150]:
        text = text.replace("|", "\\|")

        lines += [
            f"- `{file}:{number}` — `{text}`"
        ]

    lines += [
        "",
        "## Fonctions/classes impliquées",
        "",
    ]

    for file, number, typ, name in code["functions"][:250]:
        lines += [
            f"- `{file}:{number}` — {typ} `{name}`"
        ]

    path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        default=".",
    )

    parser.add_argument(
        "--quest",
        default="Colonie de vaillance",
    )

    parser.add_argument(
        "--work-json",
        default=(
            "artifacts/"
            "lot6_work_final_for_codex.json"
        ),
    )

    args = parser.parse_args()

    root = Path(
        args.root
    ).resolve()

    if (
        not (root / "app").exists()
        or not (root / "data").exists()
    ):
        print(
            "[ERREUR] Lance le script depuis "
            "la racine de Dev Atlas."
        )
        return 2

    qpath = (
        root
        / "data"
        / "encyclopedia"
        / "quests"
        / "quests_enriched.json"
    )

    mpath = (
        root
        / "data"
        / "encyclopedia"
        / "quests"
        / "image_manifest.json"
    )

    wpath = (
        root
        / args.work_json
    )

    print(
        "[1/6] Images physiques..."
    )

    disk = disk_images(
        root
    )

    print(
        "[2/6] Manifeste..."
    )

    manifest_obj, _ = load_json(
        mpath
    )

    url_map = (
        build_url_map(manifest_obj)
        if manifest_obj is not None
        else {}
    )

    _, manifest_info = json_info(
        mpath,
        root,
        url_map,
    )

    print(
        "[3/6] Données runtime quêtes..."
    )

    quests_obj, quests_info = json_info(
        qpath,
        root,
        url_map,
    )

    print(
        "[4/6] Registre Lot 6 WORK/CODEX..."
    )

    work_obj, work_info = json_info(
        wpath,
        root,
        url_map,
    )

    print(
        "[5/6] Scan COMPLET du code..."
    )

    code = scan_code(
        root
    )

    probe_runtime = probe_quest(
        quests_obj,
        args.quest,
        root,
        url_map,
    )

    probe_work = probe_quest(
        work_obj,
        args.quest,
        root,
        url_map,
    )

    likely = causes(
        disk,
        quests_info,
        work_info,
        code,
        probe_runtime,
        probe_work,
    )

    report = {
        "generated": datetime.now().isoformat(
            timespec="seconds"
        ),
        "root": str(root),
        "quest": args.quest,
        "disk": disk,
        "quests": quests_info,
        "manifest": manifest_info,
        "work": work_info,
        "probe_runtime": probe_runtime,
        "probe_work": probe_work,
        "code": code,
        "causes": likely,
        "url_map_entries": len(url_map),
    }

    print(
        "[6/6] Rapports..."
    )

    outdir = (
        root
        / "artifacts"
    )

    outdir.mkdir(
        exist_ok=True
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    md = (
        outdir
        / f"quest_images_diagnostic_{stamp}.md"
    )

    js = (
        outdir
        / f"quest_images_diagnostic_{stamp}.json"
    )

    write_md(
        report,
        md,
    )

    js.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "=" * 72
    )
    print(
        "CAUSES PROBABLES"
    )
    print(
        "=" * 72
    )

    for severity, why, check in likely:
        print(
            f"[{severity}] {why}"
        )
        print(
            f"        -> {check}"
        )

    print()
    print(
        "RÉSUMÉ"
    )

    print(
        f"Images physiques : "
        f"{disk['count']} "
        f"({disk['gb']} Go)"
    )

    print(
        "Refs quests_enriched : "
        f"{quests_info.get('refs', {}).get('occurrences', 0)}"
    )

    print(
        "Refs résolues existantes : "
        f"{quests_info.get('refs', {}).get('existing', 0)}"
    )

    print(
        "Quête témoin runtime : "
        f"{len(probe_runtime)} match(es)"
    )

    print(
        "Quête témoin WORK : "
        f"{len(probe_work)} match(es)"
    )

    print()
    print(
        f"Rapport : {md}"
    )

    print(
        f"JSON    : {js}"
    )

    print()
    print(
        "LECTURE SEULE : aucune donnée de l'app "
        "n'a été modifiée."
    )

    print(
        "Seuls les deux rapports dans artifacts/ "
        "ont été créés."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )