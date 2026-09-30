from __future__ import annotations

"""Canonical Guide GPS entry point with player-safe map semantics.

This module is the stable tool-facing entry point during consolidation. It keeps
legacy artifact generation isolated while enforcing the same adapter semantics
used by the Guide runtime.
"""

from app.modules.encyclopedia.services.guide_ultime_route_adapter import GuideUltimeRouteAdapter
from tools import build_guide_ultime_gps_route as _legacy_builder


def main() -> None:
    _legacy_builder.AdventureRouteAdapter = GuideUltimeRouteAdapter
    _legacy_builder.main()


if __name__ == "__main__":
    main()
