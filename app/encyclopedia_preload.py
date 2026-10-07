from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

_TASKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
        ("--ensure-compact-cache",),
    ),
    (
        "app.modules.encyclopedia.services.achievement_index_warmup",
        (),
    ),
    (
        "app.modules.encyclopedia.providers.memory_bound_guide_provider",
        ("--ensure-compact-cache",),
    ),
    (
        "app.modules.encyclopedia.providers.dofus_item_provider",
        ("--ensure-guide-index",),
    ),
)


def _hidden_worker_options() -> dict[str, object]:
    options: dict[str, object] = {
        "cwd": ROOT_DIR,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return options


def main() -> int:
    options = _hidden_worker_options()
    for module, arguments in _TASKS:
        completed = subprocess.run(
            [sys.executable, "-m", module, *arguments],
            check=False,
            **options,
        )
        if int(completed.returncode) != 0:
            print(
                f"Encyclopedia preload worker failed: {module} "
                f"(code {int(completed.returncode)})",
                file=sys.stderr,
            )
            return int(completed.returncode) or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
