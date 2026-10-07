from __future__ import annotations

from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import (
    write_manual_runtime_compact_cache,
)
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)


class _ColdProgressService:
    """Constructor-only placeholder; route composition never reads progress."""



def main() -> int:
    progress = _ColdProgressService()
    service = GuideUltimeManualRuntimeService(
        progress,
        progress,
        progress,
        quest_provider=QuestProvider(),
        autoload=False,
        cache_manual_bundle=False,
        compact_runtime=True,
        use_disk_cache=False,
    )
    if not service.available or not service.cards:
        return 1
    write_manual_runtime_compact_cache(service)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
