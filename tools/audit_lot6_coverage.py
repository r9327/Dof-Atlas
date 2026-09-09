from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

QUESTS_FILE = ROOT / "data" / "encyclopedia" / "quests" / "quests_enriched.json"
VERIFY_FILE = ROOT / "artifacts" / "lot6_work_final_verification.json"
ARTIFACTS = ROOT / "artifacts"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(raw):
    if not raw:
        return None

    text = str(raw).replace("\\", "/")
    if "/data/" in text.lower():
        index = text.lower().index("/data/")
        return ROOT / Path(text[index + 1:])

    p = Path(str(raw))
    return p if p.is_absolute() else ROOT / p

def start_map_entries(quest):
    meta = quest.get("source_meta") or {}
    result = []

    one = meta.get("startMapImage")
    many = meta.get("startMapImages")

    if one:
        result.append(one)

    if isinstance(many, list):
        result.extend(many)
    elif many:
        result.append(many)

    # dÃ©doublonnage simple
    unique = []
    seen = set()

    for entry in result:
        key = json.dumps(entry, sort_keys=True, ensure_ascii=False) if isinstance(entry, dict) else str(entry)
        if key not in seen:
            seen.add(key)
            unique.append(entry)

    return unique


def map_path(entry):
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return (
            entry.get("image_path")
            or entry.get("local_path")
            or entry.get("path")
        )
    return None


def map_url(entry):
    if isinstance(entry, dict):
        return (
            entry.get("source_url")
            or entry.get("url")
            or entry.get("image_url")
        )
    return None


def main():
    quests_payload = load(QUESTS_FILE)
    verify = load(VERIFY_FILE)

    quests = quests_payload["quests"]
    strict = verify.get("strict_source_visuals", [])

    strict_by_quest = defaultdict(list)

    for row in strict:
        strict_by_quest[str(row.get("quest_id"))].append(row)

    results = []
    status_counter = Counter()

    for qid, quest in quests.items():
        qid = str(qid)
        name = quest.get("name", "")

        source_rows = strict_by_quest.get(qid, [])

        expected_content = [
            row for row in source_rows
            if bool(row.get("content_display_eligible"))
        ]

        expected_maps = [
            row for row in source_rows
            if row.get("display_role") == "start_map_only"
        ]

        hidden_rows = [
            row for row in source_rows
            if not bool(row.get("content_display_eligible"))
            and row.get("display_role") != "start_map_only"
        ]

        expected_content_urls = {
            row.get("source_url")
            for row in expected_content
            if row.get("source_url")
        }

        hidden_urls = {
            row.get("source_url")
            for row in hidden_rows
            if row.get("source_url")
        }

        runtime_blocks = [
            b for b in (quest.get("solution_blocks") or [])
            if isinstance(b, dict) and b.get("type") == "image"
        ]

        runtime_urls = {
            b.get("source_url")
            for b in runtime_blocks
            if b.get("source_url")
        }

        runtime_paths = [
            b.get("image_path")
            for b in runtime_blocks
            if b.get("image_path")
        ]

        maps = start_map_entries(quest)
        runtime_map_paths = [
            map_path(x) for x in maps
            if map_path(x)
        ]

        runtime_map_urls = {
            map_url(x) for x in maps
            if map_url(x)
        }

        broken_paths = []

        for raw in runtime_paths + runtime_map_paths:
            p = resolve_path(raw)
            if not p or not p.exists():
                broken_paths.append(str(raw))

        missing_urls = sorted(expected_content_urls - runtime_urls)
        extra_urls = sorted(runtime_urls - expected_content_urls)

        exposed_hidden = sorted(runtime_urls & hidden_urls)

        statuses = []

        if broken_paths:
            statuses.append("BROKEN_LOCAL_FILE")

        if expected_content_urls and missing_urls:
            statuses.append("MISSING_IMAGE")

        if exposed_hidden:
            statuses.append("HIDDEN_IMAGE_EXPOSED")

        # Cas comme quÃªte 1760 :
        # Atlas possÃ¨de des images mais le registre strict n'en connaÃ®t aucune.
        if runtime_blocks and not source_rows:
            statuses.append("UNVERIFIED_IMAGES")

        elif extra_urls:
            statuses.append("EXTRA_IMAGE")

        if len(runtime_map_paths) != len(expected_maps):
            if expected_maps or runtime_map_paths:
                statuses.append("START_MAP_MISMATCH")

        if not statuses:
            statuses = ["OK"]

        for status in statuses:
            status_counter[status] += 1

        results.append({
            "quest_id": qid,
            "quest_name": name,
            "status": "|".join(statuses),

            "dpln_total": len(source_rows),
            "dpln_content_expected": len(expected_content),
            "dpln_start_maps_expected": len(expected_maps),
            "dpln_hidden": len(hidden_rows),

            "atlas_content_images": len(runtime_blocks),
            "atlas_start_maps": len(runtime_map_paths),

            "missing_images": len(missing_urls),
            "extra_images": len(extra_urls),
            "hidden_exposed": len(exposed_hidden),
            "broken_files": len(broken_paths),

            "missing_urls": missing_urls,
            "extra_urls": extra_urls,
            "broken_paths": broken_paths,
        })

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = ARTIFACTS / f"lot6_coverage_audit_{stamp}.json"
    csv_path = ARTIFACTS / f"lot6_coverage_audit_{stamp}.csv"

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(
            {
                "summary": dict(status_counter),
                "quests": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        fields = [
            "quest_id",
            "quest_name",
            "status",
            "dpln_total",
            "dpln_content_expected",
            "dpln_start_maps_expected",
            "dpln_hidden",
            "atlas_content_images",
            "atlas_start_maps",
            "missing_images",
            "extra_images",
            "hidden_exposed",
            "broken_files",
        ]

        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for row in results:
            writer.writerow({k: row[k] for k in fields})

    print("=" * 68)
    print("LOT 6 â€” COVERAGE AUDIT")
    print("=" * 68)

    for status, count in status_counter.most_common():
        print(f"{status:<28}: {count:,}")

    print()
    print("QuÃªtes totales              :", f"{len(results):,}")
    print()

    for target in ("1760", "2464"):
        row = next((r for r in results if r["quest_id"] == target), None)

        if row:
            print(f"[{target}] {row['quest_name']}")
            print("  STATUT               :", row["status"])
            print("  DPLN total           :", row["dpln_total"])
            print("  DPLN contenu         :", row["dpln_content_expected"])
            print("  DPLN start maps      :", row["dpln_start_maps_expected"])
            print("  Atlas contenu        :", row["atlas_content_images"])
            print("  Atlas start maps     :", row["atlas_start_maps"])
            print("  Manquantes           :", row["missing_images"])
            print("  Extras               :", row["extra_images"])
            print("  Fichiers cassÃ©s      :", row["broken_files"])
            print()

    print("JSON :", json_path)
    print("CSV  :", csv_path)
    print()
    print("AUCUN FICHIER DU PROJET N'A Ã‰TÃ‰ MODIFIÃ‰.")


if __name__ == "__main__":
    main()
