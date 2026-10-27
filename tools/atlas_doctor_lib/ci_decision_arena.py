from __future__ import annotations

"""Read-only rehearsal of existing Doctor/domain/Qt decisions.

This is a regression arena, not an agent executor, merge gate, FULL certificate
or independently attested runtime measurement. Case expectations are reviewed
test inputs, never authority to disable a required validation.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any

MAX_CASES = 32
MAX_PATHS = 12
SHA = re.compile(r"^[a-f0-9]{40}$")
CASE_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def replay_cases(root: Path, cases: list[dict[str, Any]], *,
                 base_sha: str, candidate_sha: str) -> dict[str, Any]:
    """Compare deterministic plans to a fixed reference matrix; never run tests."""
    from tools.ci_domain_certification import plan_domains
    from tools.atlas_doctor_lib.doctor_ui_ci import classify_ui
    from tools.atlas_doctor_lib.ci_orchestrator import select_workflows

    if not SHA.fullmatch(base_sha) or not SHA.fullmatch(candidate_sha):
        raise ValueError("Valid exact SHA-shaped identifiers are required")
    if (not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES
            or not all(isinstance(case, dict) for case in cases)):
        raise ValueError("Expected 1..32 structured scenarios")
    ids: set[str] = set()
    results: list[dict[str, Any]] = []
    for case in cases:
        ident = case.get("id")
        paths = case.get("paths")
        deleted = case.get("deleted", [])
        expected = case.get("expected", {})
        if (not isinstance(ident, str) or not CASE_ID.fullmatch(ident) or ident in ids
                or not isinstance(paths, list) or not 1 <= len(paths) <= MAX_PATHS
                or any(not isinstance(path, str) for path in paths)
                or not isinstance(deleted, list) or not isinstance(expected, dict)
                or not isinstance(expected.get("status"), str)
                or not isinstance(expected.get("domains"), list)
                or not all(isinstance(name, str) for name in expected["domains"])):
            raise ValueError("Incomplete, duplicate or unsafe scenario contract")
        ids.add(ident)
        plan = plan_domains(base_sha=base_sha, candidate_sha=candidate_sha,
                            paths=paths, deleted=deleted)
        deviations: list[str] = []
        if plan["status"] != expected["status"]:
            deviations.append("domain_status")
        if plan["domains"] != expected["domains"]:
            deviations.append("domain_owners")
        ui_status: str | None = None
        selected: list[str] | None = None
        if "ui_status" in expected:
            if (not isinstance(expected["ui_status"], str)
                    or not all(isinstance(expected.get(key, []), list)
                               and all(isinstance(value, str)
                                       for value in expected.get(key, []))
                               for key in ("required_jobs", "excluded_jobs"))):
                raise ValueError("Invalid UI/job expectations")
            # The production Qt impact analyzer is called rather than a
            # synthetic UI_NONE stub. No Qt runtime or graph build is executed.
            ui = classify_ui(root, paths, candidate_sha=candidate_sha,
                             base_sha=base_sha, deleted=deleted)
            ui_status = ui["status"]
            if ui_status != expected["ui_status"]:
                deviations.append("ui_impact")
            # Conservative synthetic phase route exercises the production
            # specialist selector, never purports to be a hosted Phase verdict.
            route = select_workflows(
                paths, event="pull_request", phase_route={"route": "FULL"},
                ui_plan=ui, deleted=deleted, domain_plan=plan,
                tooling_scope=False,
            )
            selected = sorted(
                name for name, decision in route["workflows"].items()
                if decision["selected"]
            )
            for required in expected.get("required_jobs", []):
                if required not in selected:
                    deviations.append("missing_job:" + required)
            for excluded in expected.get("excluded_jobs", []):
                if excluded in selected:
                    deviations.append("unjustified_job:" + excluded)
        results.append({
            "id": ident,
            "status": "MATCH" if not deviations else "MISMATCH",
            "deviations": deviations,
            "domains": plan["domains"],
            "domain_status": plan["status"],
            "ui_status": ui_status,
            "selected_jobs": selected,
            "tests_executed": False,
            "independent_host_attestation": False,
        })
    matched = sum(row["status"] == "MATCH" for row in results)
    return {
        "schema_version": 1,
        "kind": "ci_decision_arena",
        "status": "MATCHED_ADVISORY_NOT_CERTIFIED" if matched == len(cases) else "MISMATCH",
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
        "scenarios": len(cases),
        "matched": matched,
        "results": results,
        "tests_executed": False,
        "full_suite_executed": False,
        "phase_certified": False,
        "merge_authorized": False,
        "limitations": (
            "Case expectations are editable regression data, not independent "
            "trusted policy or GitHub run attestations. Runtime tests, Windows/"
            "Qt behavior, task success and phase certification were not run."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if (args.cases.is_symlink() or not args.cases.is_file()
                or args.cases.stat().st_size > 150_000):
            raise ValueError("Case manifest missing, symlinked or oversized")
        manifest = json.loads(args.cases.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            raise ValueError("Invalid scenario manifest")
        output = replay_cases(
            args.root.resolve(), manifest.get("cases"),
            base_sha=args.base_sha, candidate_sha=args.candidate_sha,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:200],
                          "certified": False}, ensure_ascii=False))
        return 2
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output["status"] == "MATCHED_ADVISORY_NOT_CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
