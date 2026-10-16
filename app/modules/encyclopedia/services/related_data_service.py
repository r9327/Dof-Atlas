from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from app.constants import DATA_DIR, ROOT_DIR
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
    quest_graph: Any | None
    warmed_source_count: int = 0
    warmed_achievement_count: int = 0
    warmed_guide_file_count: int = 0
    warmed_guide_count: int = 0
    warmed_guide_item_count: int = 0


_CACHE_LOCK = RLock()
_CACHED_CATALOG: int | None = None
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
    """Count Guide sources without reading their bodies into Atlas' heap."""

    guides_dir = DATA_DIR / "encyclopedia" / "guides"
    if not guides_dir.is_dir():
        return 0
    return sum(1 for path in guides_dir.glob("*.json") if path.is_file())


def _run_compact_preload_worker(
    module: str,
    flag: str,
    *,
    label: str,
    result_key: str,
) -> int:
    """Validate/build one compact store in exactly one disposable process."""

    completed = subprocess.run(
        [sys.executable, "-m", module, flag],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=True,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"{label} n'a produit aucun résultat")
    try:
        payload = json.loads(lines[-1])
        return max(0, int(payload.get(result_key) or 0))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Résultat {label} invalide: {lines[-1]!r}") from exc


def _warm_achievement_catalogue() -> int:
    return _run_compact_preload_worker(
        "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
        "--ensure-compact-cache",
        label="du cache compact Succès",
        result_key="achievement_count",
    )


def _warm_guide_catalogue() -> int:
    return _run_compact_preload_worker(
        "app.modules.encyclopedia.providers.memory_bound_guide_provider",
        "--ensure-compact-cache",
        label="du cache compact Guide",
        result_key="guide_count",
    )


def _warm_guide_items_index() -> int:
    return _run_compact_preload_worker(
        "app.modules.encyclopedia.providers.dofus_item_provider",
        "--ensure-guide-index",
        label="de guide_items_index",
        result_key="item_count",
    )


def build_related_encyclopedia_data(catalog: QuestCatalog) -> RelatedEncyclopediaData:
    """Warm only durable compact artefacts; keep all rich runtime graphs cold.

    The Quest catalogue is already the startup payload. Building and retaining a
    QuestGraphService here duplicated a large reconstructible graph for the whole
    Atlas session, even while Home was visible. Phase 8 preload therefore keeps
    only tiny counters/adapters resident; Quests/Guide/Success construct the
    graph they need when the corresponding UI is actually opened.
    """

    global _BUILD_COUNT, _CACHED_CATALOG, _CACHED_DATA
    catalog_id = id(catalog)
    with _CACHE_LOCK:
        if _CACHED_CATALOG == catalog_id and _CACHED_DATA is not None:
            return _CACHED_DATA

        warmed_source_count = _warm_achievement_source_indexes()
        warmed_achievement_count = _warm_achievement_catalogue()
        warmed_guide_file_count = _warm_guide_files()
        warmed_guide_count = _warm_guide_catalogue()
        warmed_guide_item_count = _warm_guide_items_index()
        data = RelatedEncyclopediaData(
            achievement_provider=None,
            guide_provider=_EMPTY_GUIDE_PROVIDER,
            quest_graph=None,
            warmed_source_count=warmed_source_count,
            warmed_achievement_count=warmed_achievement_count,
            warmed_guide_file_count=warmed_guide_file_count,
            warmed_guide_count=warmed_guide_count,
            warmed_guide_item_count=warmed_guide_item_count,
        )
        # Cache only the identity integer + tiny result. Never pin the catalogue
        # or a reconstructed dependency graph through the preload service.
        _CACHED_CATALOG = catalog_id
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
