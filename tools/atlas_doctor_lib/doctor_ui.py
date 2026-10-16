from __future__ import annotations

"""Opt-in Doctor UI session. No Qt or application imports in the coordinator.

One isolated child owns the real widgets, interactions and capture session.
The parent enforces a wall-clock bound even if Qt fails before Python can report.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCENARIOS = ("guides-success", "guides-lanyel", "guide-quests", "validator-smoke")
DEFAULT_SCENARIOS = SCENARIOS[:3]
MODES = ("all", "verify", "capture", "inspect")
MAX_SECONDS = 240


def required_assertions(scenarios, repeats=2) -> list[str]:
    required = []
    for name in scenarios:
        if name == "guide-quests":
            keys = [f"{gid}-quest-{turn}" for gid in ("guide_complet", "dofus_sylvestre") for turn in range(2)]
        else:
            smoke = name == "validator-smoke"
            pages = (1,) if smoke else (1, 8) if name == "guides-lanyel" else (1, 3)
            keys = ["open"]
            for page in pages:
                for width in (1200, 960):
                    keys.extend((f"page-{page}-{width}", f"geometry-{page}-{width}"))
            for turn in range(1 if smoke else repeats):
                keys.extend(f"{action}-{turn}" for action in ("next", "destroy", "previous", "refresh"))
            keys.extend(("lock", "unlock", "no-game-proof", "manual-persist", "character-isolation"))
            if not smoke:
                keys.extend(("combat", "combat-geometry-1200", "combat-geometry-960"))
            keys.append("home-reopen")
            if not smoke:
                keys.append("guide-return")
            keys.append("final-sheet")
        required.extend(name + "/" + key for key in keys)
    return required + ["session/qt-exceptions"]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git_value(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True, timeout=15).stdout.strip()


def verdict(assertions: list[dict], required: list[str]) -> str:
    """No implicit green for absent, duplicate or nonexecuted mandatory assertions."""
    ids = [row["assertion_id"] for row in assertions]
    if len(set(ids)) != len(ids):
        return "REVIEW"
    by_id = {row["assertion_id"]: row for row in assertions}
    statuses = [by_id[key]["assertion_status"] if key in by_id else "NOT_COVERED"
                for key in required]
    if "FAIL" in statuses:
        return "FAIL"
    if not required or any(s in {"BLOCKED", "NOT_COVERED"} for s in statuses):
        return "BLOCKED"
    return "PASS" if all(s == "PASS" for s in statuses) else "REVIEW"


def run_ui(root: Path, *, scenarios=DEFAULT_SCENARIOS, mode="all", repeats=2,
           timeout=MAX_SECONDS) -> dict[str, Any]:
    root = root.resolve()
    selected = list(dict.fromkeys(scenarios))
    if not selected or set(selected) - set(SCENARIOS) or mode not in MODES:
        raise ValueError("Unknown or empty Doctor UI selection")
    if not 1 <= repeats <= 5 or not 1 <= timeout <= MAX_SECONDS:
        raise ValueError("Doctor UI bounds: repeats 1..5, timeout 1..240 seconds")
    started = time.monotonic()
    sha = git_value(root, "rev-parse", "HEAD")
    dirty = bool(git_value(root, "status", "--porcelain"))
    session = root / ".ai/runtime/atlas_doctor/ui" / (sha[:12] + "-" + uuid.uuid4().hex[:12])
    session.mkdir(parents=True)
    manifest = {
        "schema_version": 1, "candidate_sha": sha, "dirty": dirty,
        "worktree_diff_sha256": hashlib.sha256(
            git_value(root, "diff", "HEAD").encode()).hexdigest(),
        "session_id": session.name, "selected_scenarios": selected, "mode": mode,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "Qt offscreen; installed Windows EXE NOT_COVERED",
        "network_requested": False, "user_profile_modified": False,
    }
    write_json(session / "manifest.json", manifest)
    write_json(session / "request.json", {"scenarios": selected, "mode": mode, "repeats": repeats})
    error = None
    code = None
    with tempfile.TemporaryDirectory(prefix="atlas-doctor-ui-") as temp:
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM="offscreen", DOFUS_ATLAS_USER_ROOT=temp,
                   DOFUS_ATLAS_VALIDATION_DATA_DIR=temp, PYTHONUTF8="1")
        # Never inherit a user's Qt plugin path into the vetted interpreter.
        env.pop("QT_PLUGIN_PATH", None)
        with (session / "worker.log").open("w", encoding="utf-8") as log:
            try:
                process = subprocess.run(
                    [sys.executable, "-X", "faulthandler", "-m",
                     "tools.atlas_doctor_lib.doctor_ui_qt", str(session)],
                    cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                    check=False, timeout=timeout)
                code = process.returncode
            except subprocess.TimeoutExpired:
                error = "UI_TIMEOUT"
    path = session / "ui_verdict.json"
    if not path.is_file():
        report = {"schema_version": 1, "status": "BLOCKED", "tests_executed": False,
                  "assertions": [], "error": error or "WORKER_DID_NOT_REPORT"}
    else:
        report = json.loads(path.read_text(encoding="utf-8"))
        if error or code != 0 and report.get("status") == "PASS":
            report.update(status="BLOCKED", error=error or "WORKER_EXIT_FAILURE")
    report.update(candidate_sha=sha, dirty=dirty, selected_scenarios=selected,
                  session_path=str(session), worker_exit_code=code,
                  duration_seconds=round(time.monotonic() - started, 3),
                  phase_certified=False, full_suite_waived=False)
    # Detect tampered/missing evidence even if a child emitted a green verdict.
    missing = [name for name in report.get("required_evidence", [])
               if not (session / name).is_file()]
    if missing:
        report.update(status="BLOCKED", missing_evidence=missing)
    write_json(path, report)
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    files = sorted(p for p in session.iterdir() if p.is_file() and p.name != "manifest.json")
    manifest["artifacts"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    write_json(session / "manifest.json", manifest)
    return report
