from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from app.constants import DATA_DIR, ROOT_DIR
from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService
from app.quest_catalog import QuestCatalog


class _EmptyGuideProvider:
    """Progress-preload adapter that deliberately keeps full Guides cold."""

    __slots__ = ()

    @staticmethod
    def load_all() -> list[Any]:
        return []


_EMPTY_GUIDE_PROVIDER = _EmptyGuideProvider()


@dataclass(frozen=True, slots=True)
class RelatedEncyclopediaData:
    achievement_provider: Any | None
    guide_provider: Any
    quest_graph: QuestGraphService
    warmed_source_count: int = 0
    warmed_guide_file_count: int = 0


_CACHE_LOCK = RLock()
_CACHED_CATALOG: QuestCatalog | None = None
_CACHED_DATA: RelatedEncyclopediaData | None = None
_BUILD_COUNT = 0


def _warm_achievement_source_indexes() -> int:
    """Build durable Success indexes without polluting Atlas' long-lived heap.

    The raw Dofus JSON files are large enough that building their byte-offset
    indexes in a thread temporarily expands the process heap. CPython/Windows
    can keep those arenas reserved long after the temporary strings disappear,
    so Atlas looked as if preload permanently cost tens of megabytes. Build the
    reconstructible indexes in a disposable Python process instead: the warm
    disk indexes survive, while every temporary allocation returns to Windows
    when the helper exits.
    """

    # A frozen executable would recursively launch itself rather than a Python
    # helper. In that packaging mode keep the indexes click-lazy until a small
    # dedicated helper executable exists.
    if bool(getattr(sys, "frozen", False)):
        return 0

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.modules.encyclopedia.services.achievement_index_warmup",
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        timeout=90,
        check=True,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("Le warmup des index Succès n'a produit aucun résultat")
    try:
        payload = json.loads(lines[-1])
        return max(0, int(payload.get("warmed_source_count") or 0))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Résultat du warmup des index Succès invalide: {lines[-1]!r}"
        ) from exc


def _warm_guide_files() -> int:
    """Warm small Guide JSON files in the filesystem cache, then release their bytes."""

    guides_dir = DATA_DIR / "encyclopedia" / "guides"
    if not guides_dir.is_dir():
        return 0
    count = 0
    for path in sorted(guides_dir.glob("*.json")):
        try:
            path.read_bytes()
        except OSError:
            continue
        count += 1
    return count


def build_related_encyclopedia_data(catalog: QuestCatalog) -> RelatedEncyclopediaData:
    """Warm reusable related data while keeping the heavy providers click-lazy.

    Phase 8 intentionally does not keep the fully materialized Success and Guide
    providers alive in the background. The worker prepares durable source indexes
    and filesystem cache plus the compact quest dependency graph. Temporary raw
    JSON allocations live in a disposable helper process, not Atlas itself.
    """

    global _BUILD_COUNT, _CACHED_CATALOG, _CACHED_DATA
    with _CACHE_LOCK:
        if _CACHED_CATALOG is catalog and _CACHED_DATA is not None:
            return _CACHED_DATA

        quest_provider = QuestProvider(catalog=catalog)
        warmed_source_count = _warm_achievement_source_indexes()
        warmed_guide_file_count = _warm_guide_files()
        data = RelatedEncyclopediaData(
            achievement_provider=None,
            guide_provider=_EMPTY_GUIDE_PROVIDER,
            quest_graph=QuestGraphService(quest_provider),
            warmed_source_count=warmed_source_count,
            warmed_guide_file_count=warmed_guide_file_count,
        )
        _CACHED_CATALOG = catalog
        _CACHED_DATA = data
        _BUILD_COUNT += 1
        return data


def related_data_build_count() -> int:
    with _CACHE_LOCK:
        return _BUILD_COUNT


__all__ = [
    "RelatedEncyclopediaData",
    "build_related_encyclopedia_data",
    "related_data_build_count",
]
