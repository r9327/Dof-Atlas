from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from threading import RLock
from typing import Any

from app.modules.encyclopedia.services.guide_ultime_manual_conditions import GuideUltimeManualConditionsMixin
from app.modules.encyclopedia.services.guide_ultime_manual_route import (
    _manual_tree_signature,
    load_manual_chapter,
)
from app.modules.encyclopedia.services.guide_ultime_runtime_service import GuideUltimeRuntimeService
from app.quest_catalog import normalize_text


ROOT = Path(__file__).resolve().parents[4]
MANUAL_DIR = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST_PATH = MANUAL_DIR / "manifest_v1.json"
_MANUAL_BUNDLE_LOCK = RLock()
_MANUAL_BUNDLE_CACHE: dict[tuple[object, ...], dict[str, Any]] = {}
_MAX_MANUAL_BUNDLE_CACHE_ENTRIES = 4


def _manual_bundle_catalog_signature(service: Any) -> tuple[object, ...]:
    provider = getattr(service, "quest_provider", None)
    getter = getattr(provider, "get_catalog", None)
    if callable(getter):
        try:
            catalog = getter()
            hash(catalog)
        except (Exception, TypeError):
            catalog = None
        if catalog is not None:
            return ("catalog", catalog)
    mapping = getattr(service, "_quest_name_to_id", {})
    if isinstance(mapping, dict):
        return (
            "quest-map",
            tuple(sorted((str(name), int(quest_id)) for name, quest_id in mapping.items())),
        )
    return ("provider", id(provider))


def _manual_bundle_cache_key(service: Any) -> tuple[object, ...]:
    manual_dir = Path(getattr(service, "manual_dir")).resolve()
    route = getattr(service, "route", None)
    branches = route.get("conditional_branches") if isinstance(route, dict) else None
    if isinstance(branches, dict) and branches:
        try:
            branch_signature = json.dumps(branches, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except TypeError:
            branch_signature = repr(branches)
    else:
        branch_signature = ""
    return (
        str(manual_dir),
        _manual_tree_signature(manual_dir),
        _manual_bundle_catalog_signature(service),
        branch_signature,
    )


def _manual_bundle_snapshot(service: Any) -> dict[str, Any]:
    return {
        "route": copy.deepcopy(service.route),
        "manual_audit_data": copy.deepcopy(service.manual_audit_data),
        "manual_preview_active": bool(service.manual_preview_active),
        "manual_preview_chapters": tuple(service.manual_preview_chapters),
        "manual_manifest_active": bool(service.manual_manifest_active),
        "manual_chapters": tuple(service.manual_chapters),
        "common_quest_ids": tuple(service._common_quest_ids),
        "full_success_ids": tuple(service._full_success_ids),
    }


def _restore_manual_bundle(service: Any, bundle: dict[str, Any]) -> None:
    service.route = copy.deepcopy(bundle["route"])
    service.cards = service.route.get("steps", [])
    service.manual_audit_data = copy.deepcopy(bundle["manual_audit_data"])
    service.manual_preview_active = bool(bundle["manual_preview_active"])
    service.manual_preview_chapters = tuple(bundle["manual_preview_chapters"])
    service.manual_manifest_active = bool(bundle["manual_manifest_active"])
    service.manual_chapters = tuple(bundle["manual_chapters"])
    service._common_quest_ids = tuple(bundle["common_quest_ids"])
    service._full_success_ids = tuple(bundle["full_success_ids"])
    service.manual_preview_error = ""


def clear_manual_bundle_cache() -> None:
    with _MANUAL_BUNDLE_LOCK:
        _MANUAL_BUNDLE_CACHE.clear()

_META_INSTRUCTION_TOKENS = (
    "ne créer aucune étape",
    "ne creer aucune etape",
    "session logique",
    "point de pause",
    "macro-stage",
    "macro stage",
    "exactly_one:",
    "merge_hook",
    "manual_route",
)

_CHAPTER_PREPARATION_FIELDS = (
    "preparation",
    "global_preparation",
    "global_ebene_preparation",
    "global_preparation_post_eliocalypse",
)

_PREREQUISITE_STAGE_FIELDS = (
    "entry",
    "activation",
    "prerequisite",
    "prerequisites",
    "requirements",
    "hard_gates",
)

_PREPARATION_STAGE_FIELDS = (
    "preparation",
    "a_preparer",
    "resource_plan",
    "resources",
    "required_items",
    "items_to_prepare",
    "manual_preparation",
    "keep_in_bank",
    "bank_items",
    "pod_policy",
    "pods",
    "profession",
    "professions",
    "profession_gates",
    "jobs",
)

_STRUCTURED_PREPARATION_FIELDS = (
    "preparation",
    "a_preparer",
    "resource_plan",
    "resources",
    "required_items",
    "items_to_prepare",
    "manual_preparation",
    "keep_in_bank",
    "bank_items",
)

_PROFESSION_STAGE_FIELDS = (
    "profession",
    "professions",
    "profession_gates",
    "jobs",
)

_RUNTIME_GATE_STAGE_FIELDS = (
    "conditions",
    "runtime_conditions",
    "runtime_gate",
    "runtime_gates",
    "hard_runtime_gates",
    "hard_gates",
)

_BEFORE_LEAVING_STAGE_FIELDS = (
    "before_leaving_area",
    "before_leaving",
    "before_leave",
    "avant_de_partir",
    "hard_exit",
    "hard_stop",
    "next_transport",
)

# Historical manual chapters contain a few authored fields whose content is
# player-relevant but did not originally map to a dedicated V5 card field. They
# remain source-of-truth semantics: surface their narrative to the player and
# retain the exact values as structured runtime metadata. ``branch_file`` is
# metadata-only because class selection is resolved by the manifest-driven
# GuideUltimeManualConditionsMixin rather than by exposing a filename in the UI.
_RUNTIME_NARRATIVE_STAGE_FIELDS = (
    "capture_note",
    "capture_transition",
    "carry_forward",
    "choice_policy",
    "defer",
    "future_merge",
    "temporal_rule",
    "conditional",
    "branch_policy",
)
_RUNTIME_METADATA_STAGE_FIELDS = (
    "branch_file",
    *_RUNTIME_NARRATIVE_STAGE_FIELDS,
)

_SUPPORTED_STAGE_FIELDS = {
    "id",
    "title",
    "expected_level",
    "level",
    "duration_min",
    "estimated_duration_min",
    "start",
    "end",
    "entry",
    "exit",
    "activation",
    "prerequisite",
    "prerequisites",
    "requirements",
    "hard_gates",
    "quests",
    "quest_sequence",
    "parallel_quests",
    "waypoints",
    "route",
    "route_hooks",
    "transversal",
    "instructions",
    "conditional_actions",
    "opportunistic",
    "take",
    "progress_also",
    "progress_alongside",
    "preparation",
    "a_preparer",
    "resource_plan",
    "resources",
    "required_items",
    "items_to_prepare",
    "manual_preparation",
    "keep_in_bank",
    "bank_items",
    "pod_policy",
    "pods",
    "profession",
    "professions",
    "profession_gates",
    "jobs",
    "dungeon",
    "dungeons",
    "monsters",
    "successes",
    "before_leaving_area",
    "before_leaving",
    "before_leave",
    "avant_de_partir",
    "hard_exit",
    "hard_stop",
    "next",
    "next_transport",
    "pause",
    "pause_checkpoint",
    "conditions",
    "runtime_conditions",
    "runtime_gate",
    "runtime_gates",
    "hard_runtime_gates",
    "temporal_hook",
    "temporal_hooks",
    "totem_policy",
    "conditional_route",
    "thread",
    "ranks",
    "rank",
    "alignment_rank",
    "notes",
    "note",
    *_RUNTIME_METADATA_STAGE_FIELDS,
}


class GuideUltimeManualRuntimeService(GuideUltimeManualConditionsMixin, GuideUltimeRuntimeService):
    """Runtime consumer of the canonical hand-authored Guide Ultime route.

    The manual manifest and its resolved canonical chapters are the primary
    source of truth. The generated V5 artifacts loaded by the parent service are
    kept only as an emergency fallback if the manual route cannot be resolved.
    """

    def __init__(self, *args, quest_provider: Any = None, manual_dir: Path = MANUAL_DIR, **kwargs) -> None:
        self.quest_provider = quest_provider
        self.manual_dir = Path(manual_dir)
        self.manual_preview_active = False
        self.manual_preview_error = ""
        self.manual_preview_chapters: tuple[str, ...] = ()
        self.manual_manifest_active = False
        self.manual_chapters: tuple[str, ...] = ()
        self.manual_audit_data: dict[str, Any] = {}
        self._quest_name_to_id: dict[str, int] = {}
        super().__init__(*args, **kwargs)
        self._build_quest_name_index()
        try:
            self._load_manual_preview()
        except Exception as exc:
            self.manual_preview_error = f"{type(exc).__name__}: {exc}"

    def _build_quest_name_index(self) -> None:
        provider = self.quest_provider
        if provider is None:
            return
        try:
            quests = provider.list_quests()
        except Exception:
            return
        for quest in quests:
            name = normalize_text(getattr(quest, "name", ""))
            qid = getattr(quest, "id", None)
            try:
                qid = int(qid)
            except (TypeError, ValueError):
                continue
            if name and name not in self._quest_name_to_id:
                self._quest_name_to_id[name] = qid

    def _load_manual_preview_uncached(self) -> None:
        """Load every canonical chapter declared by manifest_v1.json.

        The method name is kept for compatibility with the first manual rollout;
        it no longer selects a preview subset.
        """
        manifest_path = self.manual_dir / "manifest_v1.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        canonical = payload.get("canonical") if isinstance(payload.get("canonical"), dict) else {}
        chapters = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
        chapters.sort(key=lambda row: int(row.get("order") or 0))
        if not chapters:
            raise ValueError("Le manifeste manuel ne contient aucun chapitre canonique")

        chapter_ids = tuple(str(row.get("id") or "").strip() for row in chapters)
        if any(not value for value in chapter_ids):
            raise ValueError("Un chapitre canonique du manifeste n'a pas d'id")
        if len(chapter_ids) != len(set(chapter_ids)):
            raise ValueError(f"Ids de chapitres canoniques dupliqués: {chapter_ids}")

        artifact_route = self.route if isinstance(self.route, dict) else {}
        cards: list[dict[str, Any]] = []
        empty_cards: list[str] = []
        unsupported_by_chapter: dict[str, list[str]] = {}
        stage_count_by_chapter: dict[str, int] = {}
        resolved_files_by_chapter: dict[str, list[str]] = {}
        index = 1

        for chapter_meta in chapters:
            chapter_id = str(chapter_meta.get("id") or "").strip()
            filename = str(chapter_meta.get("file") or "").strip()
            if not filename:
                raise ValueError(f"Chapitre canonique sans fichier: {chapter_id}")
            chapter = load_manual_chapter(self.manual_dir / filename)
            stages = [row for row in chapter.get("stages", []) or [] if isinstance(row, dict)]
            stage_count_by_chapter[chapter_id] = len(stages)
            resolved_files_by_chapter[chapter_id] = [
                str(value) for value in chapter.get("_resolved_from", []) or [] if str(value).strip()
            ]

            declared = chapter_meta.get("stage_count")
            if declared is not None and self._as_int(declared) != len(stages):
                raise ValueError(
                    f"Stage count canonique incohérent pour {chapter_id}: manifeste={declared}, résolu={len(stages)}"
                )

            chapter_preparation_schedule = self._chapter_preparation_schedule(chapter, stages)
            unsupported: set[str] = set()
            for stage_position, stage in enumerate(stages):
                unsupported.update(str(key) for key in stage.keys() if str(key) not in _SUPPORTED_STAGE_FIELDS)
                card = self._stage_to_card(
                    chapter_id,
                    chapter_meta,
                    chapter,
                    stage,
                    index,
                    chapter_preparation=chapter_preparation_schedule.get(stage_position, []),
                )
                if not card.get("manual_lines"):
                    empty_cards.append(f"{chapter_id}:{card.get('manual_stage_id')}")
                cards.append(card)
                index += 1
            if unsupported:
                unsupported_by_chapter[chapter_id] = sorted(unsupported)

        self._link_next_cards(cards)

        self.manual_audit_data = {
            "manifest_status": str(payload.get("status") or ""),
            "chapter_count": len(chapters),
            "card_count": len(cards),
            "chapter_ids": list(chapter_ids),
            "stage_count_by_chapter": stage_count_by_chapter,
            "resolved_files_by_chapter": resolved_files_by_chapter,
            "empty_cards": empty_cards,
            "unsupported_stage_fields": unsupported_by_chapter,
        }

        if not cards:
            raise ValueError("Aucune fiche manuelle canonique résolue")
        if empty_cards:
            raise ValueError(f"Fiches manuelles sans instructions utiles: {empty_cards}")

        branches = artifact_route.get("conditional_branches") if isinstance(artifact_route.get("conditional_branches"), dict) else {}
        self.route = {
            "schema_version": 5,
            "id": "guide_ultime_manual_runtime",
            "source": "data/routes/guide_ultime_manual/manifest_v1.json",
            "manual_preview": False,
            "manual_manifest": True,
            "manual_chapters": list(chapter_ids),
            "manual_manifest_status": str(payload.get("status") or ""),
            "manual_audit": copy.deepcopy(self.manual_audit_data),
            "universal_route": {"common_route_quest_count": 0, "qq_required_count": 0},
            "conditional_branches": branches,
            "full_success_cards": {},
            "steps": cards,
        }
        self.cards = cards
        self._common_quest_ids = self._collect_common_quest_ids()
        self.route["universal_route"]["common_route_quest_count"] = len(self._common_quest_ids)
        self._full_success_ids = ()
        self.manual_preview_active = True
        self.manual_preview_chapters = chapter_ids
        self.manual_manifest_active = True
        self.manual_chapters = chapter_ids

    def _load_manual_preview(self) -> None:
        key = _manual_bundle_cache_key(self)
        with _MANUAL_BUNDLE_LOCK:
            cached = _MANUAL_BUNDLE_CACHE.get(key)
        if cached is not None:
            _restore_manual_bundle(self, cached)
            return
        self._load_manual_preview_uncached()
        bundle = _manual_bundle_snapshot(self)
        with _MANUAL_BUNDLE_LOCK:
            _MANUAL_BUNDLE_CACHE[key] = bundle
            while len(_MANUAL_BUNDLE_CACHE) > _MAX_MANUAL_BUNDLE_CACHE_ENTRIES:
                _MANUAL_BUNDLE_CACHE.pop(next(iter(_MANUAL_BUNDLE_CACHE)))

    def manual_audit(self) -> dict[str, Any]:
        return copy.deepcopy(self.manual_audit_data)

    def _stage_to_card(
        self,
        chapter_id: str,
        chapter_meta: dict[str, Any],
        chapter: dict[str, Any],
        stage: dict[str, Any],
        index: int,
        *,
        chapter_preparation: Any = None,
    ) -> dict[str, Any]:
        start = stage.get("start") if isinstance(stage.get("start"), dict) else {}
        end = stage.get("end") if isinstance(stage.get("end"), dict) else {}
        location = start if start else end
        x = self._as_int(location.get("x"))
        y = self._as_int(location.get("y"))

        first_route_position = self._first_route_position(stage)
        if x is None or y is None:
            route_coords = self._coords_from_text(first_route_position)
            if route_coords is not None:
                x, y = route_coords

        coverage = chapter.get("coverage") if isinstance(chapter.get("coverage"), dict) else {}
        zone = str(
            location.get("zone")
            or location.get("label")
            or coverage.get("chapter")
            or chapter_meta.get("label")
            or chapter_id.replace("_", " ").title()
        ).strip()
        destination = self._location_text(x, y, zone)
        if not destination and first_route_position:
            destination = first_route_position

        quest_names = self._stage_quest_names(stage)
        quest_ids = [self._quest_name_to_id[name] for name in quest_names if name in self._quest_name_to_id]
        lines = self._stage_lines(stage, quest_names, chapter_preparation=chapter_preparation)
        resource_names = self._stage_resource_names(chapter, stage)
        temporal_hooks = self._string_list(stage.get("temporal_hooks")) + self._string_list(stage.get("temporal_hook"))
        temporal_hooks = list(dict.fromkeys(temporal_hooks))

        structured_preparation = self._structured_rows_from_fields(stage, _STRUCTURED_PREPARATION_FIELDS)
        structured_preparation = self._dedupe_structured_rows(
            [*self._structured_rows(chapter_preparation, "chapter_preparation"), *structured_preparation]
        )
        profession_gates = self._structured_rows_from_fields(stage, _PROFESSION_STAGE_FIELDS)
        runtime_gates = self._structured_rows_from_fields(stage, _RUNTIME_GATE_STAGE_FIELDS)
        before_leaving = self._player_text_from_fields(stage, _BEFORE_LEAVING_STAGE_FIELDS)
        runtime_metadata = {
            field: copy.deepcopy(stage.get(field))
            for field in _RUNTIME_METADATA_STAGE_FIELDS
            if stage.get(field) not in (None, "", [], {})
        }

        return {
            "index": index,
            "manual_source": True,
            "_manual_route_cacheable": True,
            "manual_chapter_id": chapter_id,
            "manual_chapter_label": str(
                chapter_meta.get("label")
                or coverage.get("chapter")
                or chapter_id.replace("_", " ").title()
            ).strip(),
            "manual_stage_id": str(stage.get("id") or f"{chapter_id}-{index}"),
            "manual_title": str(stage.get("title") or zone or "Fiche de route").strip(),
            "expected_level": str(stage.get("expected_level") or stage.get("level") or "").strip(),
            "x": x,
            "y": y,
            "zone": zone,
            "subzone": zone,
            "destination": destination,
            "manual_lines": lines,
            "manual_quest_ids": quest_ids,
            "manual_quest_names": quest_names,
            "manual_resource_names": resource_names,
            "manual_success_names": self._string_list(stage.get("successes")),
            "manual_temporal_hooks": temporal_hooks,
            "manual_runtime_metadata": runtime_metadata,
            # Keep the exact resolved canonical stage so future pods/profession/
            # inventory logic never has to reverse-engineer player-facing text.
            "manual_stage_data": copy.deepcopy(stage),
            "manual_chapter_preparation": copy.deepcopy(chapter_preparation or []),
            "a_prendre": [],
            "a_faire_ici": [],
            "progresse_aussi": {"quest_ids": quest_ids, "success_ids": []},
            "a_preparer": structured_preparation,
            "hard_runtime_gates": runtime_gates,
            "profession_gates": profession_gates,
            "avant_de_partir": before_leaving,
            "succes_monstres_a_faire": [],
            "succes_donjon_a_faire": [],
            "ensuite": None,
        }

    def card_quest_ids(self, card: dict[str, Any]) -> tuple[int, ...]:
        if card.get("manual_source"):
            result: list[int] = []
            for raw in card.get("manual_quest_ids", []) or []:
                try:
                    qid = int(raw)
                except (TypeError, ValueError):
                    continue
                if qid not in result:
                    result.append(qid)
            return tuple(result)
        return super().card_quest_ids(card)

    def _stage_lines(
        self,
        stage: dict[str, Any],
        quest_names: list[str],
        *,
        chapter_preparation: Any = None,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []

        # Blocking information must be visible before any travel/action instruction.
        for field in _PREREQUISITE_STAGE_FIELDS:
            self._append_player_value(result, stage.get(field), quest_names, kind="warning")

        # Chapter-wide shopping/profession plans are surfaced only on the first
        # stage where their authored target becomes relevant.
        self._append_player_value(
            result,
            chapter_preparation,
            quest_names,
            kind="warning",
            preparation=True,
        )

        # Stage-local preparation comes before route/actions so the player never
        # discovers a key, profession, group size or resource after travelling.
        for field in _PREPARATION_STAGE_FIELDS:
            self._append_player_value(result, stage.get(field), quest_names, kind="warning", preparation=True)

        self._append_player_value(result, stage.get("take"), quest_names, kind="action")

        waypoints = [row for row in stage.get("waypoints", []) or [] if isinstance(row, dict)]
        for waypoint in waypoints:
            wx = self._as_int(waypoint.get("x"))
            wy = self._as_int(waypoint.get("y"))
            label = str(waypoint.get("label") or "").strip()
            position = self._location_text(wx, wy, label)
            waypoint_quests = [
                normalize_text(value)
                for value in waypoint.get("quests", []) or []
                if isinstance(value, str) and normalize_text(value)
            ]
            for action in waypoint.get("actions", []) or []:
                self._append_line(result, "action", position, action, waypoint_quests or quest_names)

        for route_row in stage.get("route", []) or []:
            if not isinstance(route_row, dict):
                continue
            position = str(
                route_row.get("pos")
                or route_row.get("position")
                or route_row.get("area")
                or route_row.get("zone")
                or route_row.get("label")
                or ""
            ).strip()
            raw_action = (
                route_row.get("do")
                or route_row.get("action")
                or route_row.get("instruction")
                or route_row.get("note")
            )
            self._append_line(result, "action", position, raw_action, quest_names)

        for field in (
            "conditional_actions",
            "instructions",
            "opportunistic",
            "progress_also",
            "progress_alongside",
        ):
            self._append_player_value(result, stage.get(field), quest_names, kind="action")

        dungeon = stage.get("dungeon")
        if dungeon:
            text = self._structured_target_instruction(dungeon, "donjon")
            if text and not self._line_mentions_target(result, dungeon):
                self._append_line(result, "action", "", text, quest_names)
        dungeons = stage.get("dungeons")
        if dungeons:
            self._append_structured_targets(result, dungeons, "donjon", quest_names)

        monsters = stage.get("monsters")
        if monsters:
            self._append_structured_targets(result, monsters, "monstre", quest_names)

        successes = self._string_list(stage.get("successes"))
        for success in successes:
            if not self._line_contains(result, success):
                self._append_line(result, "action", "", f"Profite du passage pour faire le succès « {success} » s'il est encore ouvert.", quest_names)

        # Narrative authoring fields are not decorative: they carry capture,
        # deferral, temporal and branch policies that must remain visible at the
        # exact stage where the route author placed them.
        for field in _RUNTIME_NARRATIVE_STAGE_FIELDS:
            self._append_player_value(result, stage.get(field), quest_names, kind="warning")

        for field in _BEFORE_LEAVING_STAGE_FIELDS:
            self._append_player_value(result, stage.get(field), quest_names, kind="warning")

        for field in ("conditions", "runtime_conditions", "runtime_gate", "runtime_gates", "hard_runtime_gates"):
            self._append_player_value(result, stage.get(field), quest_names, kind="warning")

        return self._dedupe_lines(result)

    @classmethod
    def _chapter_preparation_schedule(
        cls,
        chapter: dict[str, Any],
        stages: list[dict[str, Any]],
    ) -> dict[int, list[dict[str, Any]]]:
        schedule: dict[int, list[dict[str, Any]]] = {}
        if not stages:
            return schedule
        evidence_by_stage = [normalize_text(json.dumps(stage, ensure_ascii=False, sort_keys=True)) for stage in stages]

        for field in _CHAPTER_PREPARATION_FIELDS:
            source = chapter.get(field)
            for row, context in cls._iter_chapter_preparation_rows(source):
                target = row.get("for")
                target_index: int | None = None
                if target not in (None, "", []):
                    targets = target if isinstance(target, list) else [target]
                    for index, evidence in enumerate(evidence_by_stage):
                        if any(cls._preparation_target_matches(value, evidence) for value in targets):
                            target_index = index
                            break
                elif field == "preparation":
                    context_tokens = [
                        token for token in normalize_text(context).split("_")
                        if len(token) >= 4 and token not in {"access", "route", "full", "plan"}
                    ]
                    if context_tokens:
                        target_index = next(
                            (
                                index
                                for index, evidence in enumerate(evidence_by_stage)
                                if any(token in evidence for token in context_tokens)
                            ),
                            None,
                        )
                    else:
                        target_index = 0
                else:
                    # A row deliberately authored as global but without a target is
                    # safer on the chapter's first card than silently invisible.
                    target_index = 0

                if target_index is None:
                    continue
                schedule.setdefault(target_index, []).append(copy.deepcopy(row))

        for index, rows in list(schedule.items()):
            unique: list[dict[str, Any]] = []
            seen: set[str] = set()
            for row in rows:
                key = normalize_text(json.dumps(row, ensure_ascii=False, sort_keys=True))
                if key and key not in seen:
                    seen.add(key)
                    unique.append(row)
            schedule[index] = unique
        return schedule

    @classmethod
    def _iter_chapter_preparation_rows(
        cls,
        value: Any,
        context: str = "",
    ) -> list[tuple[dict[str, Any], str]]:
        result: list[tuple[dict[str, Any], str]] = []
        if isinstance(value, list):
            for child in value:
                result.extend(cls._iter_chapter_preparation_rows(child, context))
            return result
        if not isinstance(value, dict):
            return result

        descriptor_keys = {
            "name",
            "item",
            "resource",
            "requirement",
            "kamas",
            "note",
            "policy",
            "warning",
        }
        if descriptor_keys.intersection(value):
            result.append((value, context))
            return result

        for key, child in value.items():
            child_context = f"{context}_{key}".strip("_")
            result.extend(cls._iter_chapter_preparation_rows(child, child_context))
        return result

    @staticmethod
    def _preparation_target_matches(target: Any, evidence: str) -> bool:
        raw = str(target or "").strip()
        if not raw:
            return False
        exact = normalize_text(raw)
        if exact and exact in evidence:
            return True

        stop = {
            "avec",
            "pour",
            "dans",
            "sans",
            "avant",
            "apres",
            "capture",
            "utile",
            "hors",
            "ocre",
            "pass",
            "boss",
            "quete",
            "quetes",
        }
        tokens = [
            token for token in exact.split("_")
            if len(token) >= 5 and token not in stop
        ]
        return any(token in evidence for token in tokens)

    @classmethod
    def _structured_rows_from_fields(
        cls,
        stage: dict[str, Any],
        fields: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for field in fields:
            rows.extend(cls._structured_rows(stage.get(field), field))
        return cls._dedupe_structured_rows(rows)

    @classmethod
    def _structured_rows(cls, value: Any, source_field: str) -> list[dict[str, Any]]:
        if value is None or value is False or value == "":
            return []
        if isinstance(value, list):
            rows: list[dict[str, Any]] = []
            for child in value:
                rows.extend(cls._structured_rows(child, source_field))
            return rows
        if isinstance(value, dict):
            row = copy.deepcopy(value)
            row.setdefault("_source_field", source_field)
            return [row]
        if isinstance(value, str):
            text = value.strip()
            return [{"instruction": text, "_source_field": source_field}] if text else []
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return [{"value": value, "_source_field": source_field}]
        return []

    @staticmethod
    def _dedupe_structured_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            try:
                key = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            except TypeError:
                key = repr(row)
            if key not in seen:
                seen.add(key)
                result.append(row)
        return result

    @classmethod
    def _player_text_from_fields(
        cls,
        stage: dict[str, Any],
        fields: tuple[str, ...],
    ) -> list[str]:
        result: list[str] = []
        for field in fields:
            cls._collect_player_text(stage.get(field), result)
        unique: list[str] = []
        seen: set[str] = set()
        for value in result:
            text = " ".join(str(value or "").split()).strip()
            key = normalize_text(text)
            if text and key and key not in seen:
                seen.add(key)
                unique.append(text)
        return unique

    @classmethod
    def _collect_player_text(cls, value: Any, result: list[str]) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text:
                result.append(text)
            return
        if isinstance(value, list):
            for child in value:
                cls._collect_player_text(child, result)
            return
        if not isinstance(value, dict):
            return

        preferred = (
            "action",
            "instruction",
            "requirement",
            "warning",
            "note",
            "policy",
            "condition",
            "do",
        )
        found = False
        for key in preferred:
            child = value.get(key)
            if isinstance(child, str) and child.strip():
                result.append(child.strip())
                found = True
        if found:
            return
        for child in value.values():
            cls._collect_player_text(child, result)

    @staticmethod
    def _link_next_cards(cards: list[dict[str, Any]]) -> None:
        for index, card in enumerate(cards):
            if index + 1 >= len(cards):
                card["ensuite"] = None
                continue
            nxt = cards[index + 1]
            card["ensuite"] = {
                "destination": str(nxt.get("destination") or ""),
                "x": nxt.get("x"),
                "y": nxt.get("y"),
                "zone": str(nxt.get("zone") or ""),
                "subzone": str(nxt.get("subzone") or ""),
                "manual_stage_id": str(nxt.get("manual_stage_id") or ""),
            }

    def _append_player_value(
        self,
        result: list[dict[str, Any]],
        value: Any,
        quest_names: list[str],
        *,
        kind: str,
        preparation: bool = False,
    ) -> None:
        if value is None or value is False:
            return
        if isinstance(value, str):
            self._append_line(result, kind, "", value, quest_names)
            return
        if isinstance(value, (int, float)):
            return
        if isinstance(value, list):
            for child in value:
                self._append_player_value(result, child, quest_names, kind=kind, preparation=preparation)
            return
        if not isinstance(value, dict):
            return

        name = str(value.get("name") or value.get("item") or value.get("resource") or "").strip()
        quantity = value.get("quantity")
        if preparation and name:
            text = f"Prépare {quantity} × {name}." if quantity not in (None, "") else f"Prépare {name}."
            alternative = str(value.get("alternative") or "").strip()
            policy = str(value.get("policy") or "").strip()
            why = str(value.get("why") or value.get("for") or "").strip()
            if alternative:
                text += f" Alternative : {alternative}."
            if policy:
                text += f" {policy}"
            elif why:
                text += f" À garder pour {why}."
            self._append_line(result, kind, "", text, quest_names)

        kamas = value.get("kamas")
        if preparation and kamas not in (None, ""):
            suffix = str(value.get("for") or value.get("policy") or "").strip()
            text = f"Prévois {kamas} kamas."
            if suffix:
                text += f" {suffix}"
            self._append_line(result, kind, "", text, quest_names)

        for key in ("requirement", "instruction", "action", "do", "note", "policy", "warning", "condition"):
            child = value.get(key)
            if isinstance(child, str) and child.strip():
                self._append_line(result, kind, "", child, quest_names)

        if not name and kamas in (None, ""):
            for key, child in value.items():
                if key in {"requirement", "instruction", "action", "do", "note", "policy", "warning", "condition"}:
                    continue
                if isinstance(child, (list, dict)):
                    self._append_player_value(result, child, quest_names, kind=kind, preparation=preparation)

    def _append_structured_targets(
        self,
        result: list[dict[str, Any]],
        value: Any,
        target_kind: str,
        quest_names: list[str],
    ) -> None:
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            text = self._structured_target_instruction(row, target_kind)
            if text and not self._line_mentions_target(result, row):
                self._append_line(result, "action", "", text, quest_names)

    @staticmethod
    def _structured_target_instruction(value: Any, target_kind: str) -> str:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return ""
            if target_kind == "donjon":
                return f"Fais le donjon {text}."
            if target_kind == "monstre":
                return f"Tue {text}."
            return text
        if not isinstance(value, dict):
            return ""
        name = str(value.get("name") or value.get("boss") or value.get("monster") or "").strip()
        if not name:
            return ""
        boss = str(value.get("boss") or "").strip()
        if target_kind == "donjon":
            return f"Fais le donjon {name}{f' et bats {boss}' if boss and boss != name else ''}."
        quantity = value.get("quantity")
        return f"Tue {quantity} × {name}." if quantity not in (None, "") else f"Tue {name}."

    def _append_line(
        self,
        result: list[dict[str, Any]],
        kind: str,
        position: str,
        raw_text: Any,
        quest_names: list[str],
    ) -> None:
        if raw_text is None:
            return
        text = self._clean_player_instruction(str(raw_text), quest_names)
        if text and not self._meta_instruction(text):
            result.append({"kind": kind, "position": str(position or "").strip(), "text": text})

    def _stage_quest_names(self, stage: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for field in ("quest_sequence", "parallel_quests", "quests"):
            raw = stage.get(field)
            rows = raw if isinstance(raw, list) else [raw] if raw else []
            for value in rows:
                if isinstance(value, str) and value.strip() and not value.startswith("conditional:"):
                    values.append(value.strip())
        for waypoint in stage.get("waypoints", []) or []:
            if not isinstance(waypoint, dict):
                continue
            for value in waypoint.get("quests", []) or []:
                if isinstance(value, str) and value.strip() and not value.startswith("conditional:"):
                    values.append(value.strip())
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = normalize_text(value)
            if key and key not in seen:
                seen.add(key)
                result.append(key)
        return result

    def _clean_player_instruction(self, text: str, normalized_quest_names: list[str]) -> str:
        value = " ".join(str(text or "").split()).strip()
        if not value:
            return ""
        normalized_value = normalize_text(value)
        for quest_key in sorted(normalized_quest_names, key=len, reverse=True):
            quest_id = self._quest_name_to_id.get(quest_key)
            quest_name = ""
            if quest_id is not None and self.quest_provider is not None:
                try:
                    quest = self.quest_provider.get_quest(quest_id)
                    quest_name = str(getattr(quest, "name", "") or "").strip()
                except Exception:
                    quest_name = ""
            if not quest_name or normalize_text(quest_name) not in normalized_value:
                continue
            start_verbs = (
                "prendre",
                "prends",
                "lancer",
                "lance",
                "demarrer",
                "demarre",
                "accepter",
                "accepte",
                "commencer",
                "commence",
                "ouvrir",
                "ouvre",
            )
            keep_for_take = any(f"{verb}_{quest_key}" in normalized_value for verb in start_verbs)
            if keep_for_take:
                continue
            value = re.sub(re.escape(quest_name), "la quête en cours", value, flags=re.IGNORECASE)
            normalized_value = normalize_text(value)

        value = re.sub(r"\bla quête en cours\s+(?:et\s+)?la quête en cours\b", "la quête en cours", value, flags=re.IGNORECASE)
        value = re.sub(r"\b(?:avancer|avance|progresser|progresse)\s+la quête en cours\s+avec\s+", "Parler avec ", value, flags=re.IGNORECASE)
        value = re.sub(r"\b(?:terminer|termine|rendre)\s+la quête en cours\s+(?:auprès de|aupres de|avec|à|a)\s+", "Parler à ", value, flags=re.IGNORECASE)
        return value.strip()

    @classmethod
    def _stage_resource_names(cls, chapter: dict[str, Any], stage: dict[str, Any]) -> list[str]:
        values: list[str] = []
        sources = [
            chapter.get("resource_plan"),
            chapter.get("preparation"),
            chapter.get("global_preparation"),
            chapter.get("global_ebene_preparation"),
            chapter.get("global_preparation_post_eliocalypse"),
            stage.get("preparation"),
            stage.get("resource_plan"),
            stage.get("resources"),
            stage.get("required_items"),
            stage.get("items_to_prepare"),
            stage.get("a_preparer"),
            stage.get("manual_preparation"),
            stage.get("keep_in_bank"),
            stage.get("bank_items"),
        ]
        for source in sources:
            cls._collect_named_resources(source, values)

        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = " ".join(str(value or "").split()).strip()
            key = normalize_text(text)
            if text and key and key not in seen:
                seen.add(key)
                result.append(text)
        return sorted(result, key=len, reverse=True)

    @classmethod
    def _collect_named_resources(cls, value: Any, result: list[str]) -> None:
        if isinstance(value, dict):
            for key in ("name", "item", "resource"):
                named = value.get(key)
                if isinstance(named, str) and named.strip():
                    result.append(named.strip())
            for child in value.values():
                cls._collect_named_resources(child, result)
            return
        if isinstance(value, list):
            for child in value:
                cls._collect_named_resources(child, result)

    @staticmethod
    def _first_route_position(stage: dict[str, Any]) -> str:
        for row in stage.get("route", []) or []:
            if isinstance(row, dict):
                value = str(
                    row.get("pos")
                    or row.get("position")
                    or row.get("area")
                    or row.get("zone")
                    or row.get("label")
                    or ""
                ).strip()
                if value:
                    return value
        for row in stage.get("waypoints", []) or []:
            if not isinstance(row, dict):
                continue
            x = GuideUltimeManualRuntimeService._as_int(row.get("x"))
            y = GuideUltimeManualRuntimeService._as_int(row.get("y"))
            label = str(row.get("label") or "").strip()
            value = GuideUltimeManualRuntimeService._location_text(x, y, label)
            if value:
                return value
        return ""

    @staticmethod
    def _coords_from_text(text: str) -> tuple[int, int] | None:
        match = re.search(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]", str(text or ""))
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        rows = value if isinstance(value, list) else [value] if value else []
        return [str(row).strip() for row in rows if isinstance(row, str) and str(row).strip()]

    @staticmethod
    def _line_contains(lines: list[dict[str, Any]], target: str) -> bool:
        needle = normalize_text(target)
        return bool(needle) and any(needle in normalize_text(row.get("text")) for row in lines)

    @classmethod
    def _line_mentions_target(cls, lines: list[dict[str, Any]], value: Any) -> bool:
        if isinstance(value, str):
            return cls._line_contains(lines, value)
        if isinstance(value, dict):
            for key in ("name", "boss", "monster"):
                target = str(value.get(key) or "").strip()
                if target and cls._line_contains(lines, target):
                    return True
        return False

    @staticmethod
    def _meta_instruction(text: str) -> bool:
        value = normalize_text(text)
        return any(normalize_text(token) in value for token in _META_INSTRUCTION_TOKENS)

    @staticmethod
    def _dedupe_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in lines:
            key = normalize_text(f"{row.get('position', '')} {row.get('text', '')}")
            if key and key not in seen:
                seen.add(key)
                result.append(row)
        return result

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _location_text(x: int | None, y: int | None, zone: str) -> str:
        coords = f"[{x},{y}]" if x is not None and y is not None else ""
        return " — ".join(value for value in (coords, str(zone or "").strip()) if value)
