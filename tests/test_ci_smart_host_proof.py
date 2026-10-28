from __future__ import annotations

import copy
import unittest

from tools.ci_smart_host_proof import (
    HOST_CONTRACTS, REQUIRED_METRICS, validate_host_metrics,
)

HEAD = "a" * 40


def valid_run():
    return {"head_sha": HEAD, "event": "pull_request", "id": 418}


def valid_jobs():
    return [
        {"name": name, "run_id": 418, "head_sha": HEAD,
         "status": "completed", "conclusion": "success", "labels": [runner],
         "steps": [{"name": step, "status": "completed",
                    "conclusion": "success"} for step in mandatory]}
        for name, (runner, mandatory) in HOST_CONTRACTS.items()
    ]


class SmartHostProofTests(unittest.TestCase):
    def test_accepts_only_independently_validated_real_windows_qt_budgets(self):
        self.assertEqual(
            validate_host_metrics(valid_run(), valid_jobs(), candidate_sha=HEAD),
            REQUIRED_METRICS,
        )

    def test_missing_duplicate_or_wrong_host_identity_blocks(self):
        for name in HOST_CONTRACTS:
            with self.subTest(missing=name):
                selected = [j for j in valid_jobs() if j["name"] != name]
                with self.assertRaises(ValueError):
                    validate_host_metrics(valid_run(), selected, candidate_sha=HEAD)
        for mutation in ("duplicate", "wrong_sha", "wrong_run", "wrong_os",
                         "skipped", "failed", "pending", "no_steps",
                         "missing_step", "duplicate_step"):
            with self.subTest(mutation=mutation):
                jobs = copy.deepcopy(valid_jobs())
                item = jobs[0]
                if mutation == "duplicate": jobs.append(copy.deepcopy(item))
                elif mutation == "wrong_sha": item["head_sha"] = "b" * 40
                elif mutation == "wrong_run": item["run_id"] = 777
                elif mutation == "wrong_os": item["labels"] = ["ubuntu-latest"]
                elif mutation == "skipped": item["steps"][2]["conclusion"] = "skipped"
                elif mutation == "failed": item["steps"][2]["conclusion"] = "failure"
                elif mutation == "pending": item["status"] = "in_progress"
                elif mutation == "no_steps": item.pop("steps")
                elif mutation == "missing_step": item["steps"].pop(2)
                elif mutation == "duplicate_step": item["steps"].append(copy.deepcopy(item["steps"][2]))
                with self.assertRaises(ValueError):
                    validate_host_metrics(valid_run(), jobs, candidate_sha=HEAD)

    def test_rejects_wrong_run_or_head_even_if_all_jobs_green(self):
        for run in (
            {**valid_run(), "head_sha": "b" * 40},
            {**valid_run(), "event": "push"},
            {**valid_run(), "id": 900},
            {**valid_run(), "id": "418"},
        ):
            with self.subTest(run=run), self.assertRaises(ValueError):
                validate_host_metrics(run, valid_jobs(), candidate_sha=HEAD)
        with self.assertRaises(ValueError):
            validate_host_metrics(valid_run(), valid_jobs(), candidate_sha="bad")


if __name__ == "__main__":
    unittest.main()
