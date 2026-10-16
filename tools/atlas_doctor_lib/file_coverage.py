from __future__ import annotations
"""Read-only Graphify coverage: file representation is not runtime use."""
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

MAX_EXAMPLES = 100

def tracked_python(root: Path) -> list[str]:
    run = subprocess.run(["git", "ls-files", "--cached", "-z", "--", "*.py"],
                         cwd=root, capture_output=True, check=False, timeout=12)
    if run.returncode:
        raise RuntimeError("Git file inventory unavailable")
    return sorted({part.decode("utf-8", errors="replace") for part in run.stdout.split(b"\0") if part})

def file_coverage(root: Path) -> dict[str, Any]:
    from .architecture import graph_status
    root = root.resolve()
    files = tracked_python(root)
    state = graph_status(root)
    result = {
        "schema_version": 1, "kind": "doctor_file_coverage",
        "graph_status": state["status"], "tracked_python_files": len(files),
        "tests_executed": False, "graph_rebuilt": False,
        "runtime_coverage_proven": False, "dead_code_proven": False,
        "limits": "Graph file representation is not runtime coverage, dynamic consumer proof, or dead-code evidence.",
    }
    if state["status"] not in {"PASS", "STALE"}:
        return {**result, "status": "BLOCKED", "reason": state.get("reason"),
                "represented_files": None, "unrepresented_files": None, "coverage_percent": None}
    try:
        graph = json.loads(Path(state["graph"]).read_text(encoding="utf-8"))
        present = {n["source_file"].replace("\\", "/") for n in graph["nodes"]
                   if isinstance(n.get("source_file"), str) and n.get("file_type") != "external"}
    except (KeyError, OSError, UnicodeError, ValueError, TypeError) as exc:
        return {**result, "status": "BLOCKED", "reason": str(exc),
                "represented_files": None, "unrepresented_files": None, "coverage_percent": None}
    absent = sorted(set(files) - present)
    per_domain: dict[str, dict[str, int]] = defaultdict(lambda: {"tracked": 0, "represented": 0})
    for path in files:
        parts = path.split("/")
        key = "/".join(parts[:3]) if parts[:2] == ["app", "modules"] and len(parts) > 2 else parts[0]
        per_domain[key]["tracked"] += 1
        per_domain[key]["represented"] += int(path in present)
    return {**result,
        "status": "PASS" if state["status"] == "PASS" and not absent else "REVIEW",
        "reason": "Historical graph" if state["status"] == "STALE" else "Representation only; no runtime/dead-code proof.",
        "represented_files": len(files)-len(absent), "unrepresented_files": len(absent),
        "unrepresented_examples": absent[:MAX_EXAMPLES],
        "unrepresented_examples_truncated": len(absent)>MAX_EXAMPLES,
        "coverage_percent": round(100*(len(files)-len(absent))/len(files), 2) if files else 100.0,
        "domains": dict(sorted(per_domain.items())),
    }
