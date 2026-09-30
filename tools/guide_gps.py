from __future__ import annotations

"""Canonical Guide GPS entry point with player-safe map semantics."""

import json
import traceback

from app.modules.encyclopedia.services.guide_ultime_route_adapter import GuideUltimeRouteAdapter
from tools import build_guide_ultime_gps_route as _builder


def main() -> None:
    _builder.AdventureRouteAdapter = GuideUltimeRouteAdapter
    _builder.main()


def _run() -> None:
    try:
        main()
    except BaseException as exc:
        artifacts = getattr(_builder, "ARTIFACTS", None)
        crash_path = getattr(_builder, "CRASH_AUDIT", None)
        stage = getattr(_builder, "_GPS_STAGE", "canonical_entry_point")
        if artifacts is not None and crash_path is not None:
            try:
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
                    ) + "\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
        if isinstance(exc, SystemExit):
            raise SystemExit(exc.code if isinstance(exc.code, int) else 1)
        raise


if __name__ == "__main__":
    _run()
