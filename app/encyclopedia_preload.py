from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

_TASKS: tuple[tuple[str, ...], ...] = (
    (
        "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
        "--ensure-compact-cache",
    ),
    ("app.modules.encyclopedia.services.achievement_index_warmup",),
    (
        "app.modules.encyclopedia.providers.memory_bound_guide_provider",
        "--ensure-compact-cache",
    ),
    (
        "app.modules.encyclopedia.providers.dofus_item_provider",
        "--ensure-guide-index",
    ),
)


def _run(module: str, *arguments: str) -> None:
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
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "check": False,
    }
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    completed = subprocess.run(
        [sys.executable, "-m", module, *arguments],
        **options,
    )
    if int(completed.returncode) != 0:
        raise RuntimeError(
            f"Encyclopedia preload worker failed: {module} "
            f"(code {int(completed.returncode)})"
        )


def main() -> int:
    for task in _TASKS:
        _run(task[0], *task[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
