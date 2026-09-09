from __future__ import annotations

import argparse
import io
import json
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = Path("tools/atlas_fault_injection.json")


def load_inventory(root: Path, inventory: Path = DEFAULT_INVENTORY) -> list[dict[str, str]]:
    path = inventory if inventory.is_absolute() else root / inventory
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("scenarios"), list):
        raise ValueError("fault injection inventory schema_version must be 1")
    scenarios = payload["scenarios"]
    ids = [row.get("id") for row in scenarios]
    if len(scenarios) != 10 or len(set(ids)) != len(ids):
        raise ValueError("fault injection inventory must contain ten unique scenarios")
    return scenarios


def execute(root: Path, inventory: Path = DEFAULT_INVENTORY) -> dict[str, Any]:
    loader = unittest.TestLoader()
    rows = []
    for scenario in load_inventory(root, inventory):
        suite = loader.loadTestsFromName(scenario["test"])
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
        passed = result.wasSuccessful() and result.testsRun == 1
        rows.append(
            {
                "id": scenario["id"],
                "test": scenario["test"],
                "status": "PASS" if passed else "BLOCKED",
                "crash": False if passed else "NOT_PROVEN",
                "corruption": False if passed else "NOT_PROVEN",
                "output": stream.getvalue() if not passed else "",
            }
        )
    return {
        "schema_version": 1,
        "scenarios": rows,
        "counts": {"total": len(rows), "passed": sum(row["status"] == "PASS" for row in rows)},
        "verdict": "PASS" if all(row["status"] == "PASS" for row in rows) else "BLOCKED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run targeted Dofus Atlas fault-injection contracts.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = execute(args.root.resolve(), args.inventory)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("ATLAS FAULT INJECTION")
        for row in report["scenarios"]:
            print(f"{row['id']:28} {row['status']}")
        print(f"VERDICT: {report['verdict']}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
