from __future__ import annotations

"""Canonical Guide Ultime integrity orchestrator."""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

TOOL_SPEC = {"schema_version": 1, "id": "guide-integrity", "role": "guide_validation_orchestrator", "capabilities": ["validation", "guide"], "modes": ["fast", "full", "list"], "cost_hint": "variable", "side_effects": "artifact_output", "structured_output": True, "canonical": True, "recommended_tests": ["tests.test_guide_integrity"], "target_scopes": ["encyclopedia_guide"]}
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = ROOT / "artifacts" / "guide_integrity_summary.json"
CI_LOG_DIR = Path("artifacts") / "ci_guide_ultime_logs"

@dataclass(frozen=True)
class GuideCheck:
    key: str
    label: str
    argv: tuple[str, ...]
    modes: frozenset[str]

def _check(key: str, label: str, module: str, *arguments: str, modes: Iterable[str] = ("full",)) -> GuideCheck:
    return GuideCheck(key=key, label=label, argv=("-m", module, *arguments), modes=frozenset(modes))

CHECKS: tuple[GuideCheck, ...] = (
    _check("canonical_lock", "Canonical route lock", "tools.audit_guide_ultime_canonical_lock", "--strict", "--output", str(CI_LOG_DIR / "canonical_lock.json"), modes=("fast", "full")),
    _check("canonical_dependencies", "Canonical dependencies", "tools.audit_guide_ultime_canonical_dependencies", "--strict", "--output", str(CI_LOG_DIR / "canonical_dependencies.json"), modes=("fast", "full")),
    _check("manual_bundle", "Manual route structure", "tools.validate_guide_ultime_manual_bundle", "--strict", "--skip-catalog", modes=("fast", "full")),
    _check("transversals", "Manual transversal contracts", "tools.validate_guide_ultime_manual_transversals", "--strict", "--skip-catalog", modes=("fast", "full")),
    _check("route_hooks", "Route hook resolution", "tools.audit_guide_ultime_manual_route_hooks", "--strict"),
    _check("prerequisites", "Prerequisite ordering", "tools.audit_guide_ultime_manual_prerequisites", "--strict", "--output", str(CI_LOG_DIR / "prerequisite_order.json")),
    _check("coverage_light", "Light route coverage", "tools.audit_guide_ultime_manual_coverage"),
    _check("coverage_final", "Final success coverage", "tools.audit_guide_ultime_manual_final_coverage", "--strict", "--output", str(CI_LOG_DIR / "final_coverage.json")),
    _check("runtime", "Runtime contract", "tools.audit_guide_ultime_manual_runtime", "--strict-fields"),
    _check("action_quality", "Player action quality", "tools.audit_guide_ultime_action_quality", "--strict-hard", "--output", str(CI_LOG_DIR / "action_quality.json"), modes=("fast", "full")),
    _check("player_contract_7e", "Phase 7E player Guide contract", "tools.guide_player_contract", "--strict-hard", "--output", str(CI_LOG_DIR / "player_contract_7e.json"), modes=("fast", "full")),
)

def checks_for_mode(mode: str) -> tuple[GuideCheck, ...]:
    if mode not in {"fast", "full"}:
        raise ValueError(f"unsupported Guide integrity mode: {mode}")
    return tuple(check for check in CHECKS if mode in check.modes)

def _run_check(check: GuideCheck, *, root: Path) -> dict[str, object]:
    command = [sys.executable, "-X", "faulthandler", *check.argv]
    print(f"[guide-integrity] START {check.key}: {check.label}")
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=root, check=False)
    duration = round(time.perf_counter() - started, 3)
    status = "PASS" if completed.returncode == 0 else "FAIL"
    print(f"[guide-integrity] {status} {check.key} exit={completed.returncode} duration_s={duration}")
    return {"key": check.key, "label": check.label, "status": status, "exit_code": int(completed.returncode), "duration_seconds": duration, "command": command}

def run(mode: str, *, root: Path = ROOT) -> dict[str, object]:
    results = [_run_check(check, root=root) for check in checks_for_mode(mode)]
    failed = [row for row in results if row["exit_code"] != 0]
    return {"schema_version": 1, "mode": mode, "status": "PASS" if not failed else "FAIL", "check_count": len(results), "failed_check_count": len(failed), "checks": results}

def _render_summary(report: dict[str, object]) -> None:
    print(f"[guide-integrity] SUMMARY mode={report['mode']} status={report['status']} checks={report['check_count']} failures={report['failed_check_count']}")
    for row in report["checks"]:
        print(f"  [{row['status']}] {row['key']} ({row['duration_seconds']}s)")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canonical Dofus Atlas Guide integrity orchestrator.")
    parser.add_argument("mode", nargs="?", choices=("fast", "full"), default="fast")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--list", action="store_true", help="List checks for the selected mode without running them.")
    args = parser.parse_args(argv)
    selected = checks_for_mode(args.mode)
    if args.list:
        for check in selected:
            print(f"{check.key}: {check.label}")
        return 0
    report = run(args.mode)
    _render_summary(report)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
