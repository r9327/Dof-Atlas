from __future__ import annotations

"""Read-only diagnostics for the canonical Guide tool surface."""

import importlib.util
from pathlib import Path
from typing import Any

from tools.guide_tools_status import STATUS

ROOT = Path(__file__).resolve().parents[1]


def doctor() -> dict[str, Any]:
    canonical = {
        name: {"module": module, "importable": importlib.util.find_spec(module) is not None}
        for name, module in STATUS["canonical"].items()
    }
    retired = {
        module: not (ROOT / (module.replace(".", "/") + ".py")).exists()
        for module in STATUS["retired"]
    }
    ok = all(row["importable"] for row in canonical.values()) and all(retired.values())
    return {"ok": ok, "canonical": canonical, "retired_absent": retired}
