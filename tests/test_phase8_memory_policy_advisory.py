"""Executable regression tests for the Windows benchmark's RSS policy.

A 100 MB Home observation is never an acceptable reason to suppress a valid
benchmark, but it must be reported accurately rather than silently passing.
Other budgets and evidence-integrity checks remain release gates.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/phase8-memory-benchmark.yml"
STAGES = (
    "startup_stabilized",
    "after_preload",
    "quests_active",
    "after_quests_home",
    "achievements_active",
    "after_achievements_home",
    "guide_active",
    "after_guide_home",
    "craft_active",
    "after_craft_home",
    "before_equipment_home",
    "equipment_active",
    "after_equipment_home",
    "after_equipment_home_stabilized",
    "after_guide_home_stabilized",
    "repeat_1_quests_home",
    "repeat_1_achievements_home",
    "repeat_1_guide_home",
    "repeat_2_quests_home",
    "repeat_2_achievements_home",
    "repeat_2_guide_home",
)


def validation_code() -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    section = workflow.split("      - name: Validate memory evidence shape", 1)[1].split(
        "      - name: Publish memory summary", 1
    )[0]
    script = section.split("          @'\n", 1)[1].split("\n          '@ | python -", 1)[0]
    return textwrap.dedent(script)


def metric_payload() -> dict:
    return {
        "metrics": {
            "stages": [
                {
                    "label": label,
                    "process_rss_mb": 90.0,
                    "tree_rss_mb": 90.0,
                }
                for label in STAGES
            ],
            "peak_tree_rss_mb": 214.0,
            "achievements_retained_tree_delta_mb": 5.0,
            "guide_retained_tree_delta_mb": 13.0,
            "craft_retained_tree_delta_mb": 0.0,
            "equipment_tree_delta_stabilized_mb": 0.0,
        }
    }


def run_validation(payload: dict) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence = root / "artifacts/phase8_memory/memory.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-c", validation_code()],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )


class Phase8MemoryAdvisoryPolicyTests(unittest.TestCase):
    def test_100mb_home_overshoot_warns_without_falsely_claiming_budget_pass(self) -> None:
        payload = metric_payload()
        for row in payload["metrics"]["stages"]:
            if row["label"] == "repeat_2_guide_home":
                row["tree_rss_mb"] = 100.54
        result = run_validation(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HOME_TARGET_ADVISORY:", result.stdout)
        self.assertIn("repeat_2_guide_home: 100.54 MB >= 100.00 MB", result.stdout)
        self.assertIn("::warning title=Memory Home target (advisory)", result.stdout)

    def test_peak_still_blocks(self) -> None:
        payload = metric_payload()
        payload["metrics"]["peak_tree_rss_mb"] = 220.01
        result = run_validation(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("process-tree peak budget exceeded", result.stderr)

    def test_preload_still_blocks(self) -> None:
        payload = metric_payload()
        for row in payload["metrics"]["stages"]:
            if row["label"] == "after_preload":
                row["tree_rss_mb"] = 95.01
        result = run_validation(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("preload memory budget exceeded", result.stderr)

    def test_retained_heap_still_blocks(self) -> None:
        payload = metric_payload()
        payload["metrics"]["guide_retained_tree_delta_mb"] = 20.01
        result = run_validation(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("retained memory budget exceeded", result.stderr)

    def test_missing_required_evidence_still_blocks(self) -> None:
        payload = metric_payload()
        payload["metrics"]["stages"] = payload["metrics"]["stages"][:-1]
        result = run_validation(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("memory benchmark missing stages", result.stderr)


if __name__ == "__main__":
    unittest.main()
