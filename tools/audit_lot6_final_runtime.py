import json
from pathlib import Path
from collections import defaultdict, Counter

from app.quest_catalog import resolve_local_asset_path

ROOT = Path(__file__).resolve().parents[1]

FINAL = json.loads(
    (ROOT / "artifacts/lot6_work_final_for_codex.json").read_text(encoding="utf-8")
)
QUESTS = json.loads(
    (ROOT / "data/encyclopedia/quests/quests_enriched.json").read_text(encoding="utf-8")
)["quests"]

WL = FINAL["work_whitelist_candidates"]

content = [
    x for x in WL["content_images_pending_direct_validation"]
    if x.get("integration_authorized") is True
]
maps = [
    x for x in WL["start_maps_pending_direct_validation"]
    if x.get("integration_authorized") is True
]
rejected_maps = [
    x for x in WL["start_maps_pending_direct_validation"]
    if x.get("integration_authorized") is False
]

def local_path(candidate):
    return (
        (candidate.get("integration") or {}).get("local_path")
        or ((candidate.get("direct_validation") or {}).get("evidence") or {}).get("local_path")
    )

def norm(raw):
    if not raw:
        return ""
    return str(Path(resolve_local_asset_path(str(raw))).resolve()).lower()

expected_content = {}
content_by_quest = defaultdict(set)

for c in content:
    cid = c["candidate_id"]
    qid = str(c["quest"]["quest_id"])
    expected_content[cid] = {
        "quest_id": qid,
        "path": local_path(c),
    }
    content_by_quest[qid].add(cid)

expected_maps = defaultdict(set)
for c in maps:
    qid = str(c["quest"]["quest_id"])
    p = local_path(c)
    if p:
        expected_maps[qid].add(norm(p))

runtime_content = {}
duplicate_candidate_ids = []
legacy_images = defaultdict(list)
broken_content = []

runtime_maps = defaultdict(set)
broken_legacy_maps = []

for qid, quest in QUESTS.items():
    for block in quest.get("solution_blocks") or []:
        if block.get("type") != "image":
            continue

        raw = block.get("image_path")
        cid = (block.get("data") or {}).get("lot6_candidate_id")

        if raw and not Path(resolve_local_asset_path(raw)).exists():
            broken_content.append((qid, raw))

        if cid:
            if cid in runtime_content:
                duplicate_candidate_ids.append(cid)
            runtime_content[cid] = raw
        else:
            legacy_images[qid].append(raw)

    meta = quest.get("source_meta") or {}
    vals = []

    if meta.get("startMapImage"):
        vals.append(meta["startMapImage"])

    extra = meta.get("startMapImages") or []
    if isinstance(extra, list):
        vals.extend(extra)

    for raw in vals:
        if not isinstance(raw, str) or not raw:
            continue
        p = norm(raw)
        runtime_maps[qid].add(p)

        if not Path(resolve_local_asset_path(raw)).exists():
            broken_legacy_maps.append((qid, raw))

missing_content = []
wrong_content_path = []
missing_content_files = []

for cid, exp in expected_content.items():
    raw = runtime_content.get(cid)

    if not raw:
        missing_content.append(cid)
        continue

    if exp["path"] and norm(raw) != norm(exp["path"]):
        wrong_content_path.append(cid)

    if not Path(resolve_local_asset_path(raw)).exists():
        missing_content_files.append(cid)

missing_maps = []
extra_maps = []

all_map_quests = set(expected_maps) | set(runtime_maps)

for qid in all_map_quests:
    exp = expected_maps.get(qid, set())
    got = runtime_maps.get(qid, set())

    for p in exp - got:
        missing_maps.append((qid, p))

    for p in got - exp:
        extra_maps.append((qid, p))

lot6_ok_quests = 0
lot6_bad_quests = 0

lot6_quests = set(content_by_quest) | set(expected_maps)

for qid in lot6_quests:
    bad = False

    for cid in content_by_quest.get(qid, set()):
        if cid in missing_content or cid in wrong_content_path or cid in missing_content_files:
            bad = True

    if expected_maps.get(qid, set()) - runtime_maps.get(qid, set()):
        bad = True

    if bad:
        lot6_bad_quests += 1
    else:
        lot6_ok_quests += 1

print("=" * 70)
print("LOT 6 — AUDIT FINAL RUNTIME")
print("=" * 70)
print("Images contenu autorisées       :", len(content))
print("Images contenu présentes        :", len(set(expected_content) & set(runtime_content)))
print("Images contenu manquantes       :", len(missing_content))
print("Chemins contenu incorrects      :", len(wrong_content_path))
print("Fichiers contenu cassés         :", len(broken_content))
print()
print("Maps autorisées                 :", len(maps))
print("Maps autorisées manquantes      :", len(missing_maps))
print("Maps rejetées                   :", len(rejected_maps))
print()
print("Quêtes Lot6 OK                  :", lot6_ok_quests)
print("Quêtes Lot6 avec anomalie       :", lot6_bad_quests)
print()
print("Images legacy non vérifiées     :", sum(map(len, legacy_images.values())))
print("Quêtes avec images legacy       :", len(legacy_images))
print("Références start-map legacy     :", len(extra_maps))
print("Start-map legacy cassées        :", len(broken_legacy_maps))
print()
print("Candidate IDs dupliqués         :", len(duplicate_candidate_ids))

report = {
    "authorized_content": len(content),
    "missing_content": missing_content,
    "wrong_content_path": wrong_content_path,
    "missing_content_files": missing_content_files,
    "broken_content_runtime": broken_content,
    "authorized_maps": len(maps),
    "missing_maps": missing_maps,
    "rejected_maps": len(rejected_maps),
    "extra_legacy_maps": extra_maps,
    "broken_legacy_maps": broken_legacy_maps,
    "legacy_images_by_quest": legacy_images,
    "duplicate_candidate_ids": duplicate_candidate_ids,
    "lot6_ok_quests": lot6_ok_quests,
    "lot6_bad_quests": lot6_bad_quests,
}

out = ROOT / "artifacts/lot6_final_runtime_audit.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print()
print("Rapport :", out)
print("LECTURE SEULE — aucune donnée métier modifiée.")
