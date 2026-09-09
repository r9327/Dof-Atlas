from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

FOR_CODEX = ROOT / "artifacts" / "lot6_work_final_for_codex.json"
VERIFICATION = ROOT / "artifacts" / "lot6_work_final_verification.json"
QUESTS = ROOT / "data" / "encyclopedia" / "quests" / "quests_enriched.json"
MANIFEST = ROOT / "data" / "encyclopedia" / "quests" / "image_manifest.json"
IMAGES_ROOT = ROOT / "data" / "encyclopedia" / "images" / "quests"
ARTIFACTS = ROOT / "artifacts"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm_path(value: str | None) -> str | None:
    if not value:
        return None

    s = str(value).strip().strip("'\"").replace("\\", "/")

    while "//" in s and not s.startswith("http"):
        s = s.replace("//", "/")

    return s.casefold()


def norm_url(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


def scalar(value):
    return isinstance(value, (str, int, float, bool))


def recursive_values(obj: Any, wanted: set[str]):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).casefold() in wanted and scalar(value):
                yield value

            if isinstance(value, (dict, list)):
                yield from recursive_values(value, wanted)

    elif isinstance(obj, list):
        for value in obj:
            if isinstance(value, (dict, list)):
                yield from recursive_values(value, wanted)


def first_value(obj: Any, keys):
    wanted = {str(k).casefold() for k in keys}

    for value in recursive_values(obj, wanted):
        if value not in (None, ""):
            return value

    return None


def as_bool(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return bool(value)

    if isinstance(value, str):
        return value.strip().casefold() in {
            "1", "true", "yes", "oui", "authorized",
            "confirmed", "accepted", "ok",
        }

    return False


def resolve_local_path(raw: str | None) -> Path | None:
    if not raw:
        return None

    text = str(raw).strip().strip("'\"")

    p = Path(text)

    if p.is_absolute():
        return p

    text2 = text.replace("\\", "/")

    if text2.startswith("./"):
        text2 = text2[2:]

    return ROOT / Path(text2)


def rel_key(path: Path | None):
    if path is None:
        return None

    try:
        return norm_path(path.resolve().relative_to(ROOT.resolve()).as_posix())
    except Exception:
        return norm_path(str(path))


def looks_sha(value):
    return isinstance(value, str) and bool(SHA_RE.fullmatch(value.strip()))


def extract_direct_sha(candidate):
    dv = candidate.get("direct_validation", {})

    value = first_value(
        dv,
        {
            "direct_image_sha256",
            "source_image_sha256",
            "source_sha256",
            "verified_sha256",
            "download_sha256",
            "sha256",
        },
    )

    if looks_sha(value):
        return value.lower(), "direct_validation"

    image = candidate.get("image", {})

    value = first_value(
        image,
        {
            "direct_image_sha256",
            "source_image_sha256",
            "source_sha256",
        },
    )

    if looks_sha(value):
        return value.lower(), "image"

    return None, None


def extract_candidate(candidate, role):
    quest = candidate.get("quest", {})
    image = candidate.get("image", {})
    placement = candidate.get("documentary_placement", {})
    integration = candidate.get("integration", {})

    qid = first_value(
        quest,
        {"quest_id", "id"},
    )

    if qid is None:
        qid = first_value(candidate, {"quest_id"})

    qname = first_value(
        quest,
        {"quest_name", "name", "title"},
    )

    if qname is None:
        qname = first_value(candidate, {"quest_name"})

    source_url = first_value(
        image,
        {
            "source_url",
            "image_url",
            "url",
            "legacy_source_url",
        },
    )

    if not source_url:
        source_url = first_value(
            candidate,
            {
                "source_url",
                "legacy_source_url",
            },
        )

    page_url = first_value(
        placement,
        {
            "page_url",
            "quest_page_url",
            "confirmed_page_url",
        },
    )

    if not page_url:
        page_url = first_value(
            candidate,
            {
                "page_url",
                "quest_page_url",
                "confirmed_page_url",
            },
        )

    source_order = first_value(
        placement,
        {
            "source_image_order",
            "documentary_order",
            "image_order",
        },
    )

    if source_order is None:
        source_order = first_value(
            candidate,
            {
                "source_image_order",
                "documentary_order",
            },
        )

    local_path = first_value(
        integration,
        {
            "local_path",
            "image_path",
            "path",
            "target_path",
            "integrated_path",
        },
    )

    if not local_path:
        local_path = first_value(
            image,
            {
                "local_path",
                "image_path",
                "path",
            },
        )

    expected_sha, sha_origin = extract_direct_sha(candidate)

    return {
        "candidate_id": str(candidate.get("candidate_id", "")),
        "role": role,
        "quest_id": str(qid) if qid is not None else "",
        "quest_name": str(qname or ""),
        "source_url": norm_url(source_url),
        "page_url": norm_url(page_url),
        "source_order": source_order,
        "integration_authorized": as_bool(
            candidate.get("integration_authorized")
        ),
        "local_path_raw": str(local_path) if local_path else None,
        "expected_sha256": expected_sha,
        "expected_sha_origin": sha_origin,
    }


def manifest_entry_info(entry):
    result = {
        "path": None,
        "sha256": None,
    }

    if isinstance(entry, str):
        if looks_sha(entry):
            result["sha256"] = entry.lower()
        elif "." in entry or "/" in entry or "\\" in entry:
            result["path"] = entry

        return result

    if isinstance(entry, dict):
        result["path"] = first_value(
            entry,
            {
                "local_path",
                "image_path",
                "path",
                "file",
                "filepath",
                "relative_path",
            },
        )

        sha = first_value(
            entry,
            {
                "sha256",
                "image_sha256",
                "content_sha256",
            },
        )

        if looks_sha(sha):
            result["sha256"] = sha.lower()

    return result


def build_manifest_indexes(manifest):
    by_url_raw = manifest.get("by_url", {})
    by_sha_raw = manifest.get("by_sha256", {})

    by_url = {}

    if isinstance(by_url_raw, dict):
        for url, entry in by_url_raw.items():
            by_url[str(url)] = manifest_entry_info(entry)

    by_sha = {}

    if isinstance(by_sha_raw, dict):
        for sha, entry in by_sha_raw.items():
            if not looks_sha(str(sha)):
                continue

            info = manifest_entry_info(entry)
            by_sha[str(sha).lower()] = info

    return by_url, by_sha


def inventory_images():
    files = []

    print("[1/8] Inventaire + SHA des images locales...")

    for p in IMAGES_ROOT.rglob("*"):
        if p.is_file() and p.suffix.casefold() in IMAGE_EXTS:
            files.append(p)

    path_to_sha = {}
    sha_to_paths = defaultdict(list)

    for i, path in enumerate(files, 1):
        try:
            sha = sha256_file(path)
        except OSError:
            continue

        key = rel_key(path)

        path_to_sha[key] = sha
        sha_to_paths[sha].append(path)

        if i % 1000 == 0 or i == len(files):
            print(f"  {i:,}/{len(files):,}", flush=True)

    return files, path_to_sha, sha_to_paths


def runtime_indexes(quests, path_to_sha):
    by_candidate = defaultdict(list)
    by_source_url = defaultdict(list)
    by_quest = defaultdict(list)
    runtime_paths = set()

    print("[2/8] Index runtime solution_blocks/start maps...")

    for qid, quest in quests.items():
        qid = str(qid)

        for block_index, block in enumerate(
            quest.get("solution_blocks") or []
        ):
            if not isinstance(block, dict):
                continue

            if str(block.get("type", "")).casefold() != "image":
                continue

            raw_path = block.get("image_path")
            source_url = block.get("source_url")

            data = block.get("data")
            if not isinstance(data, dict):
                data = {}

            cid = data.get("lot6_candidate_id")

            path = resolve_local_path(raw_path)
            key = rel_key(path)

            if key:
                runtime_paths.add(key)

            sha = path_to_sha.get(key)

            item = {
                "quest_id": qid,
                "kind": "content",
                "block_index": block_index,
                "candidate_id": str(cid or ""),
                "source_url": norm_url(source_url),
                "path_raw": raw_path,
                "path_key": key,
                "sha256": sha,
                "exists": bool(path and path.exists()),
            }

            by_quest[qid].append(item)

            if cid:
                by_candidate[str(cid)].append(item)

            if source_url:
                by_source_url[
                    (qid, norm_url(source_url))
                ].append(item)

        source_meta = quest.get("source_meta")
        if not isinstance(source_meta, dict):
            source_meta = {}

        maps = []

        one = source_meta.get("startMapImage")

        if one:
            maps.append(one)

        many = source_meta.get("startMapImages")

        if isinstance(many, list):
            maps.extend(many)
        elif many:
            maps.append(many)

        for map_index, entry in enumerate(maps):
            raw_path = None
            source_url = None
            cid = None

            if isinstance(entry, str):
                raw_path = entry

            elif isinstance(entry, dict):
                raw_path = first_value(
                    entry,
                    {
                        "image_path",
                        "local_path",
                        "path",
                    },
                )

                source_url = first_value(
                    entry,
                    {
                        "source_url",
                        "url",
                        "image_url",
                    },
                )

                cid = first_value(
                    entry,
                    {
                        "lot6_candidate_id",
                        "candidate_id",
                    },
                )

            if not raw_path:
                continue

            path = resolve_local_path(str(raw_path))
            key = rel_key(path)

            if key:
                runtime_paths.add(key)

            sha = path_to_sha.get(key)

            item = {
                "quest_id": qid,
                "kind": "start_map",
                "block_index": map_index,
                "candidate_id": str(cid or ""),
                "source_url": norm_url(source_url),
                "path_raw": str(raw_path),
                "path_key": key,
                "sha256": sha,
                "exists": bool(path and path.exists()),
            }

            by_quest[qid].append(item)

            if cid:
                by_candidate[str(cid)].append(item)

            if source_url:
                by_source_url[
                    (qid, norm_url(source_url))
                ].append(item)

    return by_candidate, by_source_url, by_quest, runtime_paths


def choose_runtime_match(candidate, by_candidate, by_source_url):
    cid = candidate["candidate_id"]
    qid = candidate["quest_id"]
    source_url = candidate["source_url"]

    if cid and by_candidate.get(cid):
        matches = by_candidate[cid]

        preferred = [
            x for x in matches
            if x["kind"] == candidate["role"]
        ]

        return preferred[0] if preferred else matches[0]

    if source_url:
        matches = by_source_url.get((qid, source_url), [])

        preferred = [
            x for x in matches
            if x["kind"] == candidate["role"]
        ]

        if preferred:
            return preferred[0]

        if matches:
            return matches[0]

    return None


def audit_candidate(
    candidate,
    manifest_by_url,
    path_to_sha,
    by_candidate,
    by_source_url,
):
    issues = []

    source_url = candidate["source_url"]
    expected_sha = candidate["expected_sha256"]

    manifest_info = manifest_by_url.get(
        source_url,
        {},
    ) if source_url else {}

    manifest_path_raw = manifest_info.get("path")
    manifest_sha = manifest_info.get("sha256")

    chosen_raw = (
        candidate["local_path_raw"]
        or manifest_path_raw
    )

    chosen_path = resolve_local_path(chosen_raw)
    chosen_key = rel_key(chosen_path)

    local_exists = bool(
        chosen_path and chosen_path.exists()
    )

    local_sha = path_to_sha.get(chosen_key)

    if local_exists and not local_sha:
        try:
            local_sha = sha256_file(chosen_path)
        except OSError:
            local_sha = None

    runtime = choose_runtime_match(
        candidate,
        by_candidate,
        by_source_url,
    )

    if not candidate["integration_authorized"]:
        issues.append("NOT_AUTHORIZED")

    if candidate["integration_authorized"]:
        if not expected_sha:
            issues.append("NO_DIRECT_SOURCE_SHA")

        if not chosen_raw:
            issues.append("NO_LOCAL_PATH")

        elif not local_exists:
            issues.append("MISSING_LOCAL_FILE")

        if expected_sha and local_sha and expected_sha != local_sha:
            issues.append("WRONG_LOCAL_SHA")

        if not runtime:
            issues.append("MISSING_RUNTIME_REFERENCE")

        else:
            if not runtime["exists"]:
                issues.append("RUNTIME_FILE_MISSING")

            if (
                expected_sha
                and runtime.get("sha256")
                and runtime["sha256"] != expected_sha
            ):
                issues.append("WRONG_RUNTIME_SHA")

            if (
                candidate["role"] != runtime["kind"]
            ):
                issues.append("WRONG_RUNTIME_ROLE")

    if (
        expected_sha
        and manifest_sha
        and expected_sha != manifest_sha
    ):
        issues.append("MANIFEST_SHA_CONTRADICTION")

    if not issues:
        status = "OK"

    elif issues == ["NOT_AUTHORIZED"]:
        status = "NOT_AUTHORIZED"

    else:
        status = issues[0]

    return {
        **candidate,
        "manifest_path": manifest_path_raw,
        "manifest_sha256": manifest_sha,
        "resolved_local_path": (
            chosen_path.as_posix()
            if chosen_path else None
        ),
        "local_exists": local_exists,
        "local_sha256": local_sha,
        "runtime_found": bool(runtime),
        "runtime_kind": (
            runtime["kind"] if runtime else None
        ),
        "runtime_path": (
            runtime["path_raw"] if runtime else None
        ),
        "runtime_sha256": (
            runtime["sha256"] if runtime else None
        ),
        "status": status,
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quest",
        help="ID ou morceau du nom d'une quÃªte",
    )
    args = parser.parse_args()

    started = time.time()

    for path in (
        FOR_CODEX,
        VERIFICATION,
        QUESTS,
        MANIFEST,
    ):
        if not path.exists():
            raise SystemExit(
                f"Fichier obligatoire absent : {path}"
            )

    ARTIFACTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    for_codex = load_json(FOR_CODEX)
    verification = load_json(VERIFICATION)
    quest_data = load_json(QUESTS)
    manifest = load_json(MANIFEST)

    quests = quest_data.get("quests", {})

    files, path_to_sha, sha_to_paths = (
        inventory_images()
    )

    (
        runtime_by_candidate,
        runtime_by_source,
        runtime_by_quest,
        runtime_paths,
    ) = runtime_indexes(
        quests,
        path_to_sha,
    )

    manifest_by_url, manifest_by_sha = (
        build_manifest_indexes(manifest)
    )

    print("[3/8] Extraction des candidats Work/Codex...")

    wc = for_codex.get(
        "work_whitelist_candidates",
        {},
    )

    raw_candidates = []

    for row in wc.get(
        "content_images_pending_direct_validation",
        [],
    ):
        raw_candidates.append(
            extract_candidate(row, "content")
        )

    for row in wc.get(
        "start_maps_pending_direct_validation",
        [],
    ):
        raw_candidates.append(
            extract_candidate(row, "start_map")
        )

    print(
        f"  {len(raw_candidates):,} candidats"
    )

    print("[4/8] Audit candidat â†’ source â†’ local â†’ runtime...")

    audited = []

    for i, candidate in enumerate(
        raw_candidates,
        1,
    ):
        audited.append(
            audit_candidate(
                candidate,
                manifest_by_url,
                path_to_sha,
                runtime_by_candidate,
                runtime_by_source,
            )
        )

        if i % 1000 == 0:
            print(
                f"  {i:,}/{len(raw_candidates):,}",
                flush=True,
            )

    print("[5/8] AgrÃ©gation quÃªte par quÃªte...")

    per_quest = defaultdict(list)

    for item in audited:
        per_quest[item["quest_id"]].append(item)

    quest_summary = []

    for qid, rows in per_quest.items():
        quest = quests.get(str(qid), {})

        qname = (
            quest.get("name")
            or next(
                (
                    x["quest_name"]
                    for x in rows
                    if x["quest_name"]
                ),
                "",
            )
        )

        authorized = [
            x for x in rows
            if x["integration_authorized"]
        ]

        content = [
            x for x in authorized
            if x["role"] == "content"
        ]

        maps = [
            x for x in authorized
            if x["role"] == "start_map"
        ]

        issues = [
            x for x in authorized
            if x["status"] != "OK"
        ]

        source_urls = {
            x["source_url"]
            for x in authorized
            if x["source_url"]
        }

        direct_shas = {
            x["expected_sha256"]
            for x in authorized
            if x["expected_sha256"]
        }

        runtime_items = runtime_by_quest.get(
            str(qid),
            [],
        )

        quest_summary.append({
            "quest_id": str(qid),
            "quest_name": qname,
            "authorized_total": len(authorized),
            "content_authorized": len(content),
            "start_maps_authorized": len(maps),
            "unique_source_urls": len(source_urls),
            "unique_direct_sha256": len(direct_shas),
            "runtime_images": len(runtime_items),
            "ok": sum(
                x["status"] == "OK"
                for x in authorized
            ),
            "problems": len(issues),
        })

    quest_summary.sort(
        key=lambda x: (
            -x["problems"],
            x["quest_name"].casefold(),
        )
    )

    print("[6/8] Analyse globale...")

    status_counts = Counter(
        x["status"]
        for x in audited
        if x["integration_authorized"]
    )

    issue_counts = Counter()

    for item in audited:
        if not item["integration_authorized"]:
            continue

        issue_counts.update(item["issues"])

    duplicate_groups = {
        sha: paths
        for sha, paths in sha_to_paths.items()
        if len(paths) > 1
    }

    authorized_hashes = {
        x["expected_sha256"]
        for x in audited
        if (
            x["integration_authorized"]
            and x["expected_sha256"]
        )
    }

    runtime_hashes = {
        item["sha256"]
        for items in runtime_by_quest.values()
        for item in items
        if item.get("sha256")
    }

    local_hashes = set(sha_to_paths)

    expected_missing_hashes = (
        authorized_hashes - local_hashes
    )

    print("[7/8] Ã‰criture rapports...")

    stamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    json_path = (
        ARTIFACTS
        / f"lot6_forensic_audit_{stamp}.json"
    )

    md_path = (
        ARTIFACTS
        / f"lot6_forensic_audit_{stamp}.md"
    )

    candidates_csv = (
        ARTIFACTS
        / f"lot6_forensic_candidates_{stamp}.csv"
    )

    quests_csv = (
        ARTIFACTS
        / f"lot6_forensic_quests_{stamp}.csv"
    )

    payload = {
        "generated_at": stamp,
        "summary": {
            "physical_files": len(files),
            "unique_local_sha256": len(local_hashes),
            "duplicate_groups": len(
                duplicate_groups
            ),
            "candidates_total": len(audited),
            "authorized_total": sum(
                x["integration_authorized"]
                for x in audited
            ),
            "authorized_with_direct_sha": sum(
                bool(x["expected_sha256"])
                for x in audited
                if x["integration_authorized"]
            ),
            "authorized_ok": sum(
                x["status"] == "OK"
                for x in audited
                if x["integration_authorized"]
            ),
            "authorized_problem": sum(
                x["status"] != "OK"
                for x in audited
                if x["integration_authorized"]
            ),
            "expected_hashes_absent_locally":
                len(expected_missing_hashes),
            "runtime_unique_sha256":
                len(runtime_hashes),
            "status_counts":
                dict(status_counts),
            "issue_counts":
                dict(issue_counts),
        },
        "quests": quest_summary,
        "candidates": audited,
        "expected_hashes_absent_locally":
            sorted(expected_missing_hashes),
    }

    json_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with candidates_csv.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        fields = [
            "candidate_id",
            "role",
            "quest_id",
            "quest_name",
            "page_url",
            "source_url",
            "source_order",
            "integration_authorized",
            "expected_sha256",
            "local_path_raw",
            "local_sha256",
            "runtime_found",
            "runtime_path",
            "runtime_sha256",
            "status",
            "issues",
        ]

        w = csv.DictWriter(
            f,
            fieldnames=fields,
            extrasaction="ignore",
        )

        w.writeheader()

        for row in audited:
            out = dict(row)
            out["issues"] = "|".join(
                row["issues"]
            )
            w.writerow(out)

    with quests_csv.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        fields = list(
            quest_summary[0].keys()
        ) if quest_summary else []

        w = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        if fields:
            w.writeheader()
            w.writerows(quest_summary)

    md = [
        "# LOT 6 â€” Audit forensic",
        "",
        "LECTURE SEULE â€” aucun fichier modifiÃ©.",
        "",
        "## RÃ©sumÃ©",
        "",
        f"- Images physiques : {len(files):,}",
        f"- SHA locaux uniques : {len(local_hashes):,}",
        f"- Candidats Work/Codex : {len(audited):,}",
        f"- AutorisÃ©s : {sum(x['integration_authorized'] for x in audited):,}",
        f"- AutorisÃ©s avec SHA source direct : {sum(bool(x['expected_sha256']) for x in audited if x['integration_authorized']):,}",
        f"- AutorisÃ©s parfaitement raccordÃ©s : {sum(x['status']=='OK' for x in audited if x['integration_authorized']):,}",
        f"- AutorisÃ©s avec problÃ¨me : {sum(x['status']!='OK' for x in audited if x['integration_authorized']):,}",
        f"- SHA attendus mais absents localement : {len(expected_missing_hashes):,}",
        "",
        "## ProblÃ¨mes",
        "",
    ]

    for key, value in issue_counts.most_common():
        md.append(
            f"- {key}: {value:,}"
        )

    md += [
        "",
        "## QuÃªtes avec le plus de problÃ¨mes",
        "",
    ]

    for q in [
        x for x in quest_summary
        if x["problems"]
    ][:100]:
        md.append(
            f"- [{q['quest_id']}] {q['quest_name']} : "
            f"{q['problems']} problÃ¨me(s) / "
            f"{q['authorized_total']} attendu(s)"
        )

    md_path.write_text(
        "\n".join(md),
        encoding="utf-8",
    )

    print("[8/8] TERMINÃ‰")
    print()
    print("=" * 72)
    print("LOT 6 â€” FORENSIC")
    print("=" * 72)
    print(
        "Images physiques             :",
        f"{len(files):,}",
    )
    print(
        "SHA locaux uniques           :",
        f"{len(local_hashes):,}",
    )
    print(
        "Candidats Work/Codex         :",
        f"{len(audited):,}",
    )

    authorized_count = sum(
        x["integration_authorized"]
        for x in audited
    )

    print(
        "Candidats autorisÃ©s          :",
        f"{authorized_count:,}",
    )

    direct_count = sum(
        bool(x["expected_sha256"])
        for x in audited
        if x["integration_authorized"]
    )

    print(
        "Avec SHA source direct       :",
        f"{direct_count:,}",
    )

    ok_count = sum(
        x["status"] == "OK"
        for x in audited
        if x["integration_authorized"]
    )

    problem_count = sum(
        x["status"] != "OK"
        for x in audited
        if x["integration_authorized"]
    )

    print(
        "RaccordÃ©s correctement       :",
        f"{ok_count:,}",
    )
    print(
        "Avec problÃ¨me                :",
        f"{problem_count:,}",
    )
    print(
        "SHA attendus absents local   :",
        f"{len(expected_missing_hashes):,}",
    )

    print("\nProblÃ¨mes dÃ©tectÃ©s :")

    for key, value in issue_counts.most_common():
        print(
            f"  {key:<30} {value:,}"
        )

    if args.quest:
        needle = args.quest.casefold()

        print("\n--- QUÃŠTE CIBLÃ‰E ---")

        for q in quest_summary:
            if (
                needle == q["quest_id"].casefold()
                or needle in q["quest_name"].casefold()
            ):
                print(
                    json.dumps(
                        q,
                        ensure_ascii=False,
                        indent=2,
                    )
                )

                rows = per_quest.get(
                    q["quest_id"],
                    [],
                )

                for row in rows:
                    if row["integration_authorized"]:
                        print(
                            "\n",
                            row["candidate_id"],
                            row["role"],
                            row["status"],
                        )
                        print(
                            " source:",
                            row["source_url"],
                        )
                        print(
                            " attendu:",
                            row["expected_sha256"],
                        )
                        print(
                            " local:",
                            row["local_sha256"],
                        )
                        print(
                            " runtime:",
                            row["runtime_sha256"],
                        )
                        print(
                            " issues:",
                            row["issues"],
                        )

    elapsed = time.time() - started

    print()
    print("Rapport MD   :", md_path)
    print("Rapport JSON :", json_path)
    print("CSV quÃªtes   :", quests_csv)
    print("CSV images   :", candidates_csv)
    print(f"DurÃ©e        : {elapsed:.1f}s")
    print()
    print(
        "AUCUN FICHIER DU PROJET N'A Ã‰TÃ‰ MODIFIÃ‰."
    )


if __name__ == "__main__":
    main()
