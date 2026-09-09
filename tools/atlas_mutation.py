from __future__ import annotations

import argparse
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]


def _expect_value_error(function: Callable[..., Any], value: Any) -> None:
    try:
        function(value)
    except ValueError:
        return
    raise AssertionError(f"expected ValueError for {value!r}")


def _identity_positive(ns: dict[str, Any]) -> None:
    _expect_value_error(ns["character_key"], -1)


def _identity_padding(ns: dict[str, Any]) -> None:
    assert ns["character_id_from_key"]("character:001") is None


def _identity_prefix(ns: dict[str, Any]) -> None:
    assert ns["character_key"](12) == "character:12"


def _json_corruption_backup(ns: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "progress.json"
        path.write_text("{broken", encoding="utf-8")
        assert ns["read_json_resilient"](path, {}, logger=logging.getLogger("mutation")) == {}
        assert len(list(Path(directory).glob("progress.json.corrupt.*.bak"))) == 1


def _json_missing_copy(ns: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory() as directory:
        default = {"completed": []}
        result = ns["read_json_resilient"](Path(directory) / "missing.json", default)
        result["completed"].append(1)
        assert default == {"completed": []}


MUTANTS: tuple[dict[str, Any], ...] = (
    {
        "id": "identity_accept_negative",
        "module": "app/core/character_identity.py",
        "old": 'raw = str(character_id or "").strip()',
        "new": 'raw = str(character_id or "").lstrip("-").strip()',
        "probe": _identity_positive,
    },
    {
        "id": "identity_accept_padded_key",
        "module": "app/core/character_identity.py",
        "old": "return parsed if text == character_key(parsed) else None",
        "new": "return parsed",
        "probe": _identity_padding,
    },
    {
        "id": "identity_change_canonical_prefix",
        "module": "app/core/character_identity.py",
        "old": 'CHARACTER_KEY_PREFIX = "character:"',
        "new": 'CHARACTER_KEY_PREFIX = "slot:"',
        "probe": _identity_prefix,
    },
    {
        "id": "persistence_skip_corrupt_backup",
        "module": "app/core/json_store.py",
        "old": "backup = backup_corrupt_json(target)",
        "new": "backup = None",
        "probe": _json_corruption_backup,
    },
    {
        "id": "persistence_share_default_state",
        "module": "app/core/json_store.py",
        "old": "if not target.exists():\n        return copy.deepcopy(default)",
        "new": "if not target.exists():\n        return default",
        "probe": _json_missing_copy,
    },
)


def _namespace(source: str, path: Path) -> dict[str, Any]:
    namespace: dict[str, Any] = {"__file__": str(path), "__name__": f"atlas_mutant_{path.stem}"}
    exec(compile(source, str(path), "exec"), namespace)
    return namespace


def execute(root: Path = ROOT) -> dict[str, Any]:
    rows = []
    for mutant in MUTANTS:
        path = root / mutant["module"]
        source = path.read_text(encoding="utf-8-sig")
        old = mutant["old"]
        if source.count(old) != 1:
            rows.append({"id": mutant["id"], "module": mutant["module"], "status": "ERROR", "detail": "mutation anchor is not unique"})
            continue
        mutated = source.replace(old, mutant["new"], 1)
        try:
            mutant["probe"](_namespace(mutated, path))
        except AssertionError as exc:
            rows.append({"id": mutant["id"], "module": mutant["module"], "status": "KILLED", "detail": str(exc)})
        except Exception as exc:
            rows.append({"id": mutant["id"], "module": mutant["module"], "status": "ERROR", "detail": repr(exc)})
        else:
            rows.append({"id": mutant["id"], "module": mutant["module"], "status": "SURVIVED", "detail": ""})
    counts = {status.lower(): sum(row["status"] == status for row in rows) for status in ("KILLED", "SURVIVED", "ERROR")}
    counts["generated"] = len(rows)
    verdict = "PASS" if counts["killed"] == len(rows) else "BLOCKED"
    return {"schema_version": 1, "modules": sorted({row["module"] for row in rows}), "mutants": rows, "counts": counts, "verdict": verdict}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run targeted deterministic Atlas mutation probes.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = execute(args.root.resolve())
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("ATLAS TARGETED MUTATION")
        for row in report["mutants"]:
            print(f"{row['id']:36} {row['status']}")
        counts = report["counts"]
        print(f"generated={counts['generated']} killed={counts['killed']} survived={counts['survived']} error={counts['error']}")
        print(f"VERDICT: {report['verdict']}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
