from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / ".cache" / "dofus_atlas" / "startup_cache_warmup_v1.json"
SCHEMA_VERSION = 1


_TASKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "success",
        (
            "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
            "--ensure-compact-cache",
        ),
    ),
    (
        "success_names",
        ("app.modules.encyclopedia.services.achievement_index_warmup",),
    ),
    (
        "guide",
        (
            "app.modules.encyclopedia.providers.memory_bound_guide_provider",
            "--ensure-compact-cache",
        ),
    ),
    (
        "guide_items",
        (
            "app.modules.encyclopedia.providers.dofus_item_provider",
            "--ensure-guide-index",
        ),
    ),
)


def _run_module(module: str, *arguments: str) -> str:
    environment = dict(os.environ)
    root = str(ROOT)
    current_pythonpath = str(environment.get("PYTHONPATH") or "")
    environment["PYTHONPATH"] = (
        root if not current_pythonpath else root + os.pathsep + current_pythonpath
    )
    options: dict[str, object] = {
        "cwd": root,
        "env": environment,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": False,
        "timeout": 180,
    }
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    completed = subprocess.run(
        [sys.executable, "-m", module, *arguments],
        **options,
    )
    if int(completed.returncode) != 0:
        stderr = str(completed.stderr or "").strip()
        raise RuntimeError(
            f"startup cache warmup failed: {module} "
            f"(code {int(completed.returncode)})"
            + (f": {stderr}" if stderr else "")
        )
    return str(completed.stdout or "").strip()


def _last_json_line(output: str) -> dict[str, object]:
    for line in reversed(output.splitlines()):
        value = line.strip()
        if not value:
            continue
        try:
            payload = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _write_result(payload: dict[str, object]) -> None:
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RESULT_PATH.with_suffix(RESULT_PATH.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(RESULT_PATH)


def main() -> int:
    started = perf_counter()
    quest_output = _run_module("app.quest_catalog_details", "--ensure-cache")
    try:
        quest_count = max(0, int(quest_output.splitlines()[-1].strip()))
    except (IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("startup Quest cache warmup returned no count") from exc

    task_results: dict[str, dict[str, object]] = {}
    for label, task in _TASKS:
        task_results[label] = _last_json_line(_run_module(task[0], *task[1:]))

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "quest_count": quest_count,
        "encyclopedia_ready": True,
        "tasks": task_results,
        "elapsed_ms": round((perf_counter() - started) * 1000.0, 2),
    }
    _write_result(payload)
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
