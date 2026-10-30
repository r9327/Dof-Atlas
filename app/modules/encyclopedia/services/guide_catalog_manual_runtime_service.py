from __future__ import annotations

import copy
import gzip
import hashlib
import json
import logging
import os
import sys
import sqlite3
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from app.constants import RAW_QUEST_DATA_DIR, ROOT_DIR, USER_DATA_ROOT
from app.quest_catalog import quest_catalog_cache_signature
from app.modules.encyclopedia.providers.quest_provider import QuestProvider

from app.modules.encyclopedia.services.guide_catalog_route_store import (
    LAZY_MARKER,
    load_detail as load_catalog_card_detail,
    restore_indexed_route,
    write_indexed_route,
)
from app.modules.encyclopedia.services.guide_quest_view_model import (
    clean_requirement_line,
    first_position_from_quest,
    quest_items_from_objectives,
    quest_solution_steps,
    quest_start_info,
)
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_ultime_generated_service import (
    GuideUltimeGeneratedService,
)
from app.modules.encyclopedia.services.guide_ultime_player_policy import (
    line_acquires_resource,
    preparation_resource_name,
)
from app.core.text import normalize_key as normalize_text


_COORD_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")


@lru_cache(maxsize=4096)
def _position_key_short(text: str) -> str:
    """Cache only short position labels shared by thousands of route objectives."""
    return _position_key_uncached(text)


def _position_key_uncached(text: str) -> str:
    match = _COORD_RE.search(text)
    if match is not None:
        return f"{int(match.group(1))},{int(match.group(2))}"
    return normalize_text(text)



_CATALOG_ROUTE_CACHE_DIR = (USER_DATA_ROOT or ROOT_DIR) / ".cache" / "dofus_atlas" / "catalog_routes_v1"
_CATALOG_ROUTE_CACHE_SCHEMA = 1
_LOGGER = logging.getLogger(__name__)


def _catalog_route_cache_identity(service: Any) -> tuple[Path, str] | None:
    """Cache only canonical, reconstructible Quest-backed routes.

    Custom/in-memory Quest providers are intentionally excluded. The signature
    includes authored Guide order, every Quest-source generation and the
    projection code, but no character or saved progress.
    """
    if not bool(getattr(service, "use_disk_cache", True)):
        return None
    provider = getattr(service, "quest_provider", None)
    if type(provider) is not QuestProvider:
        return None
    data_dir = Path(provider.data_dir)
    if data_dir.resolve() != RAW_QUEST_DATA_DIR.resolve():
        return None
    loaded = getattr(provider, "_catalog", None)
    if loaded is not None and not bool(getattr(loaded, "deferred_details", False)):
        return None
    guide = service.catalog_guide
    steps = [
        (
            str(getattr(step, "id", "") or ""),
            str(getattr(step, "step_type", "") or ""),
            str(getattr(step, "entity_id", "") or ""),
            int(getattr(step, "order", 0) or 0),
        )
        for step in getattr(guide, "required_steps", ()) or ()
    ]
    from app.modules.encyclopedia.services import (
        guide_catalog_route_store,
        guide_quest_view_model,
        guide_ultime_player_policy,
    )
    sources = (
        Path(__file__),
        Path(guide_quest_view_model.__file__),
        Path(guide_ultime_player_policy.__file__),
        Path(guide_catalog_route_store.__file__),
    )
    # Frozen bundles unpack sources to a different temporary path on each
    # launch. Bind cache validity to the durable executable version instead.
    frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        executable = Path(sys.executable)
        meta = executable.stat()
        source_stats = [("frozen_executable", meta.st_mtime_ns, meta.st_size)]
    else:
        source_stats = [
            (str(path), path.stat().st_mtime_ns, path.stat().st_size)
            for path in sources
        ]
    quest_sources = quest_catalog_cache_signature(data_dir)
    frozen_root = getattr(sys, "_MEIPASS", None) if frozen else None
    if frozen_root and data_dir.resolve().is_relative_to(Path(frozen_root).resolve()):
        # Content is bundled immutably with the signed executable; disregard
        # ephemeral extraction paths and mtimes while retaining file sizes.
        quest_sources = tuple((label, size) for label, _, _, size in quest_sources)
    payload = {
        "schema": _CATALOG_ROUTE_CACHE_SCHEMA,
        "guide": [service.guide_id, service.guide_title, steps],
        "quest_sources": quest_sources,
        "projection_files": source_stats,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    safe_name = hashlib.sha256(service.guide_id.encode("utf-8")).hexdigest()[:24]
    return _CATALOG_ROUTE_CACHE_DIR / f"{safe_name}.json.gz", digest


def _restore_catalog_route_cache(
    service: Any, path: Path, signature: str,
) -> bool:
    try:
        if path.stat().st_size > 24 * 1024 * 1024:
            return False
        # Bound decompressed bytes even for a malformed cache on disk.
        with gzip.open(path, "rb") as stream:
            content = stream.read(64 * 1024 * 1024 + 1)
        if len(content) > 64 * 1024 * 1024:
            return False
        payload = json.loads(content)
    except (OSError, EOFError, ValueError, TypeError):
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") != _CATALOG_ROUTE_CACHE_SCHEMA:
        return False
    if payload.get("source_signature") != signature:
        return False
    route = payload.get("route")
    audit = payload.get("audit")
    ids = payload.get("common_quest_ids")
    if not isinstance(route, dict) or not isinstance(audit, dict):
        return False
    cards = route.get("steps")
    if not isinstance(cards, list) or not cards or not all(isinstance(row, dict) for row in cards):
        return False
    if route.get("id") != f"catalog_manual_{service.guide_id}":
        return False
    if audit.get("card_count") != len(cards):
        return False
    if not isinstance(ids, list) or any(type(value) is not int for value in ids):
        return False

    service.route = route
    service.cards = cards
    service._common_quest_ids = tuple(ids)
    service._full_success_ids = ()
    service.manual_audit_data = audit
    service.manual_preview_active = True
    service.manual_preview_chapters = (service.guide_id,)
    service.manual_manifest_active = False
    service.manual_chapters = (service.guide_id,)
    service.manual_preview_error = ""
    return True


def _write_catalog_route_cache(
    service: Any, path: Path, signature: str,
) -> None:
    """Atomic source cache, never progression; failures cannot block the Guide."""
    payload = {
        "schema_version": _CATALOG_ROUTE_CACHE_SCHEMA,
        "source_signature": signature,
        "route": service.route,
        "audit": service.manual_audit_data,
        "common_quest_ids": service._common_quest_ids,
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(gzip.compress(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            compresslevel=1,
        ))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class GuideCatalogManualRuntimeService(GuideUltimeManualRuntimeService):
    """Project a Guide catalogue route into the shared manual road-book UI.

    The Guide model remains authoritative for quest order and completion. Quest
    source data supplies route positions, walkthrough actions, preparation and
    combat objectives. A rendered sheet represents a route position, not a quest:
    one quest may span several maps and consecutive work on the same map is merged.
    """

    def __init__(
        self,
        *args,
        guide,
        quest_provider,
        **kwargs,
    ) -> None:
        self.catalog_guide = guide
        self.guide_id = str(getattr(guide, "id", "") or "")
        self.guide_title = str(getattr(guide, "title", "") or self.guide_id)
        self.progress_id = f"catalog_manual:{self.guide_id}"
        kwargs["autoload"] = False
        super().__init__(*args, quest_provider=quest_provider, **kwargs)

    def manual_class_gate_for_card(self, card: dict[str, Any]) -> None:
        # This Guide comes from the Quest catalogue, not the authored Guide
        # Ultime manifest. Never scan its instructions for another route's
        # class-specific branching text.
        return None

    def manual_order_gate_for_card(self, card: dict[str, Any]) -> None:
        # Alignment/Order requirements belong to the authored manual route.
        # The catalogue cards contain only their canonical Quest objectives.
        return None

    def card_success_ids(self, card: dict[str, Any]) -> tuple[int, ...]:
        # No manual_success_names or cross-manifest index in catalogue cards.
        return GuideUltimeGeneratedService.card_success_ids(self, card)

    def card_automatic_values(
        self,
        character_key: str,
        card: dict[str, Any],
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> tuple[bool, ...]:
        # Keep the original Quest/objective/success completion rule, without
        # rescanning 1,672 cards for unrelated manual class/Order conditions.
        return GuideUltimeGeneratedService.card_automatic_values(
            self, character_key, card, completed_quests=completed_quests,
        )

    def _catalog_card_detail(self, card: dict[str, Any]) -> dict[str, Any]:
        """Only fetch the requested sheet's text; retain a bounded LRU."""
        if not card.get(LAZY_MARKER):
            return card
        index = int(card["index"]) - 1
        cache = getattr(self, "_catalog_detail_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict(cache or ())
            self._catalog_detail_cache = cache
        detail = cache.get(index)
        if detail is not None:
            cache.move_to_end(index)
            return detail
        store = getattr(self, "_catalog_detail_store_path", None)
        if not isinstance(store, Path):
            raise ValueError("Index Guide sans source de détails")
        if not (0 <= index < len(self.cards)):
            raise ValueError(f"Index de fiche Guide invalide: {index}")
        if self.cards[index].get("manual_stage_id") != card.get("manual_stage_id"):
            raise ValueError(f"Identifiant fiche Guide discordant: {index}")
        detail = load_catalog_card_detail(store, index)
        cache[index] = detail
        while len(cache) > 10:
            cache.popitem(last=False)
        return detail

    def prefetch_route_near(self, index: int, *, max_reads: int = 9) -> bool:
        """Hydrate a bounded neighborhood, optionally one SQLite row per UI tick.

        True means another slice may be useful. This only caches texts: no Qt
        objects, character state or persisted progress are ever touched.
        """
        if not isinstance(getattr(self, "_catalog_detail_store_path", None), Path):
            return False
        total = len(self.cards)
        if not total:
            return False
        index = max(0, min(total - 1, int(index)))
        budget = max(1, min(9, int(max_reads)))
        reads = 0
        for candidate in (index, *range(index + 1, min(total, index + 7)),
                          *range(max(0, index - 2), index)):
            cache = getattr(self, "_catalog_detail_cache", {})
            if candidate in cache:
                continue
            try:
                self._catalog_card_detail(self.cards[candidate])
            except (OSError, ValueError, sqlite3.Error) as exc:
                _LOGGER.warning("Prélecture de fiche Guide indisponible: %s", exc)
                return False
            reads += 1
            if reads >= budget:
                # The next slice will determine whether all neighbors are ready.
                return True
        return False

    def _load_manual_preview(self) -> None:
        # Restore only compact card identities, then fetch walkthroughs on demand.
        try:
            cached_identity = _catalog_route_cache_identity(self)
        except (OSError, ValueError, TypeError):
            cached_identity = None
        if cached_identity is not None:
            try:
                if restore_indexed_route(self, *cached_identity):
                    return
            except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
                _LOGGER.warning("Index de Guide invalide, reconstruction: %s", exc)
            # One-time conversion of the previous full gzip generation.
            if _restore_catalog_route_cache(self, *cached_identity):
                try:
                    write_indexed_route(self, *cached_identity)
                    restore_indexed_route(self, *cached_identity)
                except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
                    _LOGGER.warning("Migration cache Guide ignorée: %s", exc)
                return

        quest_count = 0
        raw_segments: list[dict[str, Any]] = []
        seen_quests: set[int] = set()
        candidate_ids: set[int] = set()
        candidates: list[tuple[Any, int]] = []
        for step in sorted(
            getattr(self.catalog_guide, "required_steps", ()) or (),
            key=lambda row: int(getattr(row, "order", 0) or 0),
        ):
            if str(getattr(step, "step_type", "")) != "quest":
                continue
            try:
                quest_id = int(getattr(step, "entity_id", None))
            except (TypeError, ValueError):
                continue
            if quest_id not in candidate_ids:
                candidate_ids.add(quest_id)
                candidates.append((step, quest_id))
        # A cold route previously made 198 separate _load_source calls on
        # deferred Quest records. Reuse one source pass for at most eight IDs,
        # then immediately project that batch into route segments.
        catalog = self.quest_provider.get_catalog()
        prefetch = getattr(catalog, "warm_details_batch", None)
        for offset in range(0, len(candidates), 8):
            batch = candidates[offset:offset + 8]
            if callable(prefetch):
                prefetch(tuple(quest_id for _, quest_id in batch))
            for step, quest_id in batch:
                quest = self.quest_provider.get_quest(quest_id)
                if quest is None:
                    continue
                seen_quests.add(quest_id)
                quest_count += 1
                raw_segments.extend(self._quest_segments(step, quest, finalize=False))

        raw_segment_count = len(raw_segments)
        # These segments are newly built and exclusively owned by this route.
        # Transfer their lists into cards instead of copying every rich row
        # two more times while all Quest details are still resident.
        segments = self._merge_consecutive_positions(raw_segments, consume=True)
        cards = [
            self._segment_to_card(segment, index, consume=True)
            for index, segment in enumerate(segments)
        ]
        del raw_segments, segments
        if not cards:
            raise ValueError(f"Aucune fiche route exploitable pour {self.guide_id}")

        self._link_next_cards(cards)
        self.route = {
            "schema_version": 5,
            "id": f"catalog_manual_{self.guide_id}",
            "source": f"data/encyclopedia/guides/{self.guide_id}.json+quest_catalog",
            "manual_preview": False,
            "manual_manifest": False,
            "manual_chapters": [self.guide_id],
            "route_model": "map_segments",
            "universal_route": {
                "common_route_quest_count": quest_count,
                "qq_required_count": 0,
            },
            "conditional_branches": {},
            "full_success_cards": {},
            "steps": cards,
        }
        self.cards = cards
        self._common_quest_ids = tuple(sorted(seen_quests))
        self._full_success_ids = ()
        self.manual_audit_data = {
            "source": self.route["source"],
            "guide_id": self.guide_id,
            "route_model": "map_segments",
            "card_count": len(cards),
            "raw_segment_count": raw_segment_count,
            "quest_count": quest_count,
            "merged_segment_count": max(0, raw_segment_count - len(cards)),
        }
        self.manual_preview_active = True
        self.manual_preview_chapters = (self.guide_id,)
        self.manual_manifest_active = False
        self.manual_chapters = (self.guide_id,)
        self.manual_preview_error = ""
        if cached_identity is not None:
            try:
                write_indexed_route(self, *cached_identity)
                if not restore_indexed_route(self, *cached_identity):
                    raise ValueError("L'index nouvellement écrit n'est pas restaurable")
            except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
                _LOGGER.warning("Index reconstruit indisponible, repli sans perte: %s", exc)
                # Leave the complete in-memory route usable; keep prior
                # full-format fallback for environments without SQLite writes.
                try:
                    _write_catalog_route_cache(self, *cached_identity)
                except (OSError, ValueError, TypeError) as fallback_exc:
                    _LOGGER.warning("Cache Guide de repli indisponible: %s", fallback_exc)

    def _quest_segments(
        self, guide_step, quest, *, finalize: bool = True,
    ) -> list[dict[str, Any]]:
        quest_id = int(quest.id)
        quest_name = str(getattr(quest, "name", "") or f"Quête #{quest_id}")
        start = quest_start_info(quest, include_map_images=False)
        start_position = str(
            start.position
            or first_position_from_quest(quest, start_info=start)
            or ""
        ).strip()
        zone = str(
            start.zone
            or (quest.zones[0] if getattr(quest, "zones", ()) else "")
            or ""
        ).strip()

        first = self._new_segment(
            position=start_position,
            zone=zone,
            quest_id=quest_id,
            quest_name=quest_name,
            guide_step_id=str(getattr(guide_step, "id", "") or f"quest-{quest_id}"),
        )

        for prerequisite in getattr(quest, "prerequisites", ()) or ():
            text = clean_requirement_line(str(prerequisite or ""))
            if text:
                first["sections"]["prepare"].append(
                    self._line("warning", start_position, f"Prérequis : {text}")
                )

        for item in quest_items_from_objectives(quest):
            name = str(getattr(item, "name", "") or "").strip()
            if name and name.casefold() not in {
                value.casefold() for value in first["resource_names"]
            }:
                first["resource_names"].append(name)
            if not bool(getattr(item, "preparable", False)) or not name:
                continue
            quantity = int(getattr(item, "quantity", 0) or 0) or 1
            first["sections"]["prepare"].append(
                self._line("warning", start_position, f"Prépare {quantity} × {name}.")
            )
            first["structured_preparation"].append(
                {
                    "item_id": getattr(item, "item_id", None),
                    "name": name,
                    "quantity": quantity,
                    "_source_field": "quest_required_items",
                }
            )

        location = " — ".join(value for value in (start_position, zone) if value)
        if start.npc:
            text = f"Prends la quête « {quest_name} » auprès de {start.npc}."
            if location:
                text += f" {location}"
        else:
            text = f"Commence / poursuis la quête « {quest_name} »."
        first["sections"]["now"].append(
            self._line("action", start_position, text)
        )

        segments: list[dict[str, Any]] = []
        current = first
        current_key = self._position_key(current["position"])
        for solution_step in quest_solution_steps(quest):
            if solution_step.title:
                current["sections"]["now"].append(
                    self._line("action", current["position"], solution_step.title)
                )
            if solution_step.description:
                current["sections"]["now"].append(
                    self._line("action", current["position"], solution_step.description)
                )

            for objective in solution_step.objectives:
                text = str(objective.text or "").strip()
                if not text:
                    continue
                objective_position = str(
                    objective.position
                    or current["position"]
                    or start_position
                    or ""
                ).strip()
                # Resolve each coordinate once; preserve the original split rule.
                objective_key = self._position_key(objective_position)
                if objective_key and current_key and objective_key != current_key:
                    if finalize:
                        self._finalize_segment(current)
                    if self._segment_has_content(current):
                        segments.append(current)
                    current = self._new_segment(
                        position=objective_position,
                        zone=zone,
                        quest_id=quest_id,
                        quest_name=quest_name,
                        guide_step_id=str(
                            getattr(guide_step, "id", "") or f"quest-{quest_id}"
                        ),
                    )
                    current_key = objective_key

                row = self._line(
                    "combat" if bool(objective.combat) else "action",
                    objective_position,
                    text,
                )
                if bool(objective.combat):
                    current["sections"]["boss"].append(row)
                else:
                    current["sections"]["now"].append(row)

        if finalize:
            self._finalize_segment(current)
        if self._segment_has_content(current):
            segments.append(current)
        return segments

    @staticmethod
    def _new_segment(
        *,
        position: str,
        zone: str,
        quest_id: int,
        quest_name: str,
        guide_step_id: str,
    ) -> dict[str, Any]:
        return {
            "position": str(position or "").strip(),
            "zone": str(zone or "").strip(),
            "guide_step_ids": [str(guide_step_id)],
            "quest_ids": [int(quest_id)],
            "quest_names": [str(quest_name)],
            "resource_names": [],
            "structured_preparation": [],
            "sections": {
                "prepare": [],
                "now": [],
                "opportunity": [],
                "keep": [],
                "boss": [],
                "before_leave": [],
            },
            "manual_lines": [],
        }

    def _finalize_segment(
        self, segment: dict[str, Any], *, consume: bool = False,
    ) -> None:
        sections = segment["sections"]
        for key in sections:
            sections[key] = self._dedupe_rows(sections[key])
        segment["manual_lines"] = [
            row if consume else copy.deepcopy(row)
            for key in ("prepare", "now", "boss", "before_leave")
            for row in sections[key]
        ]

    @staticmethod
    def _segment_has_content(segment: dict[str, Any]) -> bool:
        return bool(
            segment.get("manual_lines")
            or any(segment.get("sections", {}).values())
        )

    def _merge_consecutive_positions(
        self,
        segments: list[dict[str, Any]],
        *,
        consume: bool = False,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        previous_key = ""
        for raw in segments:
            segment = raw if consume else copy.deepcopy(raw)
            key = self._position_key(segment.get("position"))
            if merged and key and key == previous_key:
                # The source is private to this route only in consume mode.
                self._merge_segment(
                    merged[-1], segment, finalize=False, consume=consume,
                )
                continue
            merged.append(segment)
            previous_key = key
        for segment in merged:
            if consume:
                self._finalize_segment(segment, consume=True)
            else:
                self._finalize_segment(segment)
        return merged

    def _merge_segment(
        self,
        target: dict[str, Any],
        source: dict[str, Any],
        *,
        finalize: bool = True,
        consume: bool = False,
    ) -> None:
        for field in ("guide_step_ids", "quest_ids", "quest_names", "resource_names"):
            for value in source.get(field, ()) or ():
                if value not in target[field]:
                    target[field].append(value)
        prepared = source.get("structured_preparation", ())
        target["structured_preparation"].extend(
            prepared if consume else copy.deepcopy(prepared)
        )
        for key, rows in source.get("sections", {}).items():
            target["sections"].setdefault(key, [])
            target["sections"][key].extend(rows if consume else copy.deepcopy(rows))
        if finalize:
            if consume:
                self._finalize_segment(target, consume=True)
            else:
                self._finalize_segment(target)

    def _segment_to_card(
        self,
        segment: dict[str, Any],
        index: int,
        *,
        consume: bool = False,
    ) -> dict[str, Any]:
        position = str(segment.get("position") or "").strip()
        zone = str(segment.get("zone") or "").strip()
        coords = self._coords(position)
        quest_names = list(segment.get("quest_names", ()))
        quest_ids = [int(value) for value in segment.get("quest_ids", ())]
        stage_ids = [str(value) for value in segment.get("guide_step_ids", ())]
        route_label = " — ".join(value for value in (position, zone) if value)
        title = f"Étape GPS — {route_label}" if route_label else (
            quest_names[0]
            if len(quest_names) == 1
            else f"Étape GPS — {len(quest_names)} quêtes"
        )
        stage_key = "+".join(stage_ids[:3]) or f"map-{index + 1}"
        if len(stage_ids) > 3:
            stage_key += f"+{len(stage_ids) - 3}"

        waypoint: dict[str, Any] = {
            "label": position or zone,
            "quests": quest_names,
        }
        if coords is not None:
            waypoint["x"], waypoint["y"] = coords

        return {
            "index": index + 1,
            "manual_source": True,
            "_manual_route_cacheable": True,
            "manual_chapter_id": self.guide_id,
            "manual_chapter_label": self.guide_title,
            "manual_stage_id": f"{self.guide_id}:gps:{stage_key}:{index + 1}",
            "manual_title": title,
            "manual_route_position": position,
            "expected_level": "",
            "x": coords[0] if coords is not None else None,
            "y": coords[1] if coords is not None else None,
            "zone": zone,
            "subzone": zone,
            "destination": route_label or title,
            "manual_lines": (
                segment.get("manual_lines", ())
                if consume else copy.deepcopy(segment.get("manual_lines", ()))
            ),
            "manual_sections": (
                segment.get("sections", {})
                if consume else copy.deepcopy(segment.get("sections", {}))
            ),
            "structured_runtime_lines": [],
            "manual_quest_ids": quest_ids,
            "manual_quest_names": quest_names,
            "manual_resource_names": list(segment.get("resource_names", ())),
            "manual_success_names": [],
            "manual_temporal_hooks": [],
            "manual_runtime_metadata": {},
            "manual_stage_data": {"waypoints": [waypoint]},
            "a_prendre": [],
            "a_faire_ici": [],
            "progresse_aussi": {"quest_ids": quest_ids, "success_ids": []},
            "a_preparer": self._dedupe_structured_preparation(
                segment.get("structured_preparation", ())
            ),
            "hard_runtime_gates": [],
            "profession_gates": [],
            "avant_de_partir": [],
            "succes_monstres_a_faire": [],
            "succes_donjon_a_faire": [],
            "ensuite": None,
        }

    def manual_lines_for_card(
        self,
        character_key: str,
        card: dict[str, Any],
    ) -> list[dict[str, Any]]:
        del character_key
        source = self._catalog_card_detail(card)
        return [
            copy.deepcopy(row)
            for row in source.get("manual_lines", ())
            if isinstance(row, dict)
        ]

    def manual_sections_for_card(
        self,
        character_key: str,
        card: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        del character_key
        detail = self._catalog_card_detail(card)
        source = (
            detail.get("manual_sections")
            if isinstance(detail.get("manual_sections"), dict)
            else {}
        )
        sections = {
            key: [
                copy.deepcopy(row)
                for row in source.get(key, ())
                if isinstance(row, dict)
            ]
            for key in (
                "prepare",
                "now",
                "opportunity",
                "keep",
                "boss",
                "before_leave",
            )
        }
        # The Lanyel catalogue supplies authored sections directly and thus
        # bypasses the shared player-facing preparation policy. Keep the
        # authored steps, but do not demand an item "before departure" when the
        # very same route sheet explicitly obtains it on this map.
        acquisitions = [
            str(row.get("text") or "")
            for section in ("now", "opportunity")
            for row in sections[section]
        ]
        sections["prepare"] = [
            row for row in sections["prepare"]
            if not (
                (name := preparation_resource_name(str(row.get("text") or "")))
                and any(line_acquires_resource(text, name) for text in acquisitions)
            )
        ]
        return sections

    def manual_checked(self, character_key: str, key: str) -> bool:
        return self.guide_progress.is_manual_step_completed(
            character_key,
            self.progress_id,
            key,
        )

    def set_manual_checked(
        self,
        character_key: str,
        key: str,
        checked: bool,
    ) -> None:
        self.guide_progress.set_manual_step_completed(
            character_key,
            self.progress_id,
            key,
            bool(checked),
        )

    @staticmethod
    def _line(kind: str, position: str, text: str) -> dict[str, Any]:
        return {
            "kind": str(kind),
            "position": str(position or "").strip(),
            "text": " ".join(str(text or "").split()).strip(),
        }

    @staticmethod
    def _coords(position: str) -> tuple[int, int] | None:
        match = _COORD_RE.search(str(position or ""))
        if match is None:
            return None
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def _position_key(value: Any) -> str:
        text = " ".join(str(value or "").split()).strip()
        # No unbounded retention of long walkthroughs or unhashable input.
        return _position_key_short(text) if len(text) <= 160 else _position_key_uncached(text)

    @staticmethod
    def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            text = " ".join(str(row.get("text") or "").split()).strip()
            position = " ".join(str(row.get("position") or "").split()).strip()
            key = (position.casefold(), text.casefold())
            if text and key not in seen:
                seen.add(key)
                result.append(row)
        return result

    @staticmethod
    def _dedupe_structured_preparation(rows) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[Any, str, int]] = set()
        for raw in rows or ():
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            quantity = int(raw.get("quantity") or 0)
            key = (raw.get("item_id"), name.casefold(), quantity)
            if name and key not in seen:
                seen.add(key)
                result.append(copy.deepcopy(raw))
        return result


__all__ = ["GuideCatalogManualRuntimeService"]
