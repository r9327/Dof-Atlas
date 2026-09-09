from __future__ import annotations

"""Strict V5 GPS entry point using player-safe map semantics.

The historical builder remains importable for compatibility.  This launcher swaps
only its adapter class before execution so the V5 route rejects Dofus sentinel
coordinates and mapId=0 without changing other app modules.
"""

import sys

from app.modules.encyclopedia.services.guide_ultime_route_adapter import (
    GuideUltimeRouteAdapter,
)
from tools import build_guide_ultime_gps_route as builder


def main() -> None:
    builder.AdventureRouteAdapter = GuideUltimeRouteAdapter
    builder.main()


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        # Keep the original builder's crash diagnostics when possible.
        artifacts = getattr(builder, "ARTIFACTS", None)
        crash_path = getattr(builder, "CRASH_AUDIT", None)
        stage = getattr(builder, "_GPS_STAGE", "strict_wrapper")
        if artifacts is not None and crash_path is not None:
            try:
                import json
                import traceback

                artifacts.mkdir(parents=True, exist_ok=True)
                crash_path.write_text(
                    json.dumps(
                        {
                            "stage": stage,
                            "exception_type": type(exc).__name__,
                            "message": str(exc),
                            "repr": repr(exc),
                            "traceback": traceback.format_exc(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
        if isinstance(exc, SystemExit):
            code = exc.code if isinstance(exc.code, int) else 1
            raise SystemExit(code)
        raise
