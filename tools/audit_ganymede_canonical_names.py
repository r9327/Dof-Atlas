"""Compare validated Ganymède/DPLN quest names to installed Atlas Doduda FR names.

Uses Atlas' own on-disk lazy source index, not the web or the Guide engine.
A name match is evidence of *candidate identity only*: never certify the
quest objective graph, requirements, location, or routing from name equality.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from app import quest_catalog as qc
from app.quest_source_index import QuestSources
from tools.audit_ganymede_quest_candidates import ROOT, audit_ganymede_quest_candidates


def audit_ganymede_canonical_names(
    root: Path,
    *,
    raw_quests_path: Path | None = None,
    french_language_path: Path | None = None,
) -> dict[str, object]:
    root = Path(root).resolve()
    default_data = (
        qc.RAW_QUEST_DATA_DIR if root == ROOT.resolve()
        else root / "data/cache/dofus_maps/raw/doduda_cli"
    )
    quest_path = Path(raw_quests_path) if raw_quests_path else default_data / "quests.json"
    language_path = (
        Path(french_language_path) if french_language_path
        else default_data / "languages/fr.json"
    )
    upstream = audit_ganymede_quest_candidates(root)
    if upstream["status"] != "REVIEW_REQUIRED":
        return {
            "status": "FAIL",
            "source": "canonical_doduda_localized_name_review",
            "issues": [{"code": "unvalidated_candidates",
                        "detail": "upstream candidate audit did not pass"}],
            "certified_quest_objectives": 0,
            "certified_routes": 0,
        }

    candidates = [
        {
            "source_guide_id": guide["source_guide_id"],
            "source_quest_id": item["external_dofusdb_quest_id"],
            "source_name": item["independent_quest_name"],
            "source_steps": item["observed_source_steps"],
            "evidence_file": guide["named_evidence_file"],
        }
        for guide in upstream["guide_reports"]
        for item in guide["candidate_pairs"]
        if item["status"] == "REVIEW_TRIANGULATED_SOURCES"
    ]
    if not quest_path.is_file() or not language_path.is_file():
        return {
            "schema_version": 1,
            "status": "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE",
            "source": "canonical_doduda_localized_name_review",
            "missing_files": [
                str(path) for path in (quest_path, language_path) if not path.is_file()
            ],
            "candidate_count": len(candidates),
            "verified_names": None,
            "review_name_variants": None,
            "certified_quest_objectives": 0,
            "certified_routes": 0,
            "issues": [],
        }

    results: list[dict[str, object]] = []
    issues: list[dict[str, str]] = []
    try:
        # No monolithic JSON decode and no durable index or app cache mutated.
        with tempfile.TemporaryDirectory(prefix="atlas-guide-name-audit-") as temp:
            sources = QuestSources(Path(temp), disk_backed=True)
            try:
                quests = sources.rows(quest_path)
                languages = sources.mapping(language_path, "entries", required=True)
                for candidate in candidates:
                    quest_id = candidate["source_quest_id"]
                    raw = quests.get(quest_id)
                    if (not isinstance(raw, dict) or
                            qc.safe_int(raw.get("id", quest_id)) != quest_id):
                        canonical_name = None
                        state = "REVIEW_CANONICAL_QUEST_MISSING_OR_WRONG_ID"
                    else:
                        canonical_name = qc.localized_name(raw, languages, fallback="")
                        if not canonical_name:
                            state = "REVIEW_FRENCH_LOCALIZATION_MISSING"
                        elif (qc.normalize_text(canonical_name)
                              == qc.normalize_text(candidate["source_name"])):
                            state = "REVIEW_CANONICAL_NAME_MATCH"
                        else:
                            state = "REVIEW_CANONICAL_NAME_VARIANT"
                    results.append({
                        **candidate,
                        "canonical_quest_name": canonical_name,
                        "status": state,
                        "candidate_identity_confirmed": False,
                        "required_quest_objectives_confirmed": False,
                    })
            finally:
                sources.close()
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        issues.append({"code": "invalid_canonical_doduda_source", "detail": str(exc)})

    matches = sum(r["status"] == "REVIEW_CANONICAL_NAME_MATCH" for r in results)
    variants = sum(r["status"] == "REVIEW_CANONICAL_NAME_VARIANT" for r in results)
    incomplete = len(candidates) - matches - variants
    return {
        "schema_version": 1,
        "status": "FAIL" if issues else "REVIEW_CANONICAL_NAME_GAPS" if variants or incomplete
                  else "PASS_CANONICAL_NAMES_ONLY",
        "source": "canonical_doduda_localized_name_review",
        "raw_quest_file": str(quest_path),
        "raw_french_language_file": str(language_path),
        "candidate_count": len(candidates),
        "matching_names": matches,
        "review_name_variants": variants,
        "missing_quest_or_name": incomplete,
        "certified_quest_objectives": 0,
        "certified_routes": 0,
        "reviews": sorted(results, key=lambda r: (r["source_guide_id"], r["source_quest_id"])),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--raw-quests", type=Path)
    parser.add_argument("--french-language", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_ganymede_canonical_names(
        args.root,
        raw_quests_path=args.raw_quests,
        french_language_path=args.french_language,
    )
    output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["status"] == "FAIL" else 2 if report["status"].startswith("BLOCKED_") else 0


if __name__ == "__main__":
    raise SystemExit(main())
