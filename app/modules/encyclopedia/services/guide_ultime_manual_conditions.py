from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from app.constants import NETWORK_CHARACTER_BINDINGS_FILE
from app.core.character_identity import character_id_from_key
from app.modules.encyclopedia.services.guide_quest_view_model import quest_solution_steps
from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_ocre_registry import (
    load_ocre_capture_registry,
    ocre_capture_lines,
    ocre_unlock_policy_lines,
)
from app.modules.encyclopedia.services.guide_ultime_temporal_registry import load_temporal_registry
from app.quest_catalog import normalize_text, read_json_file


_ORDER_LABELS = {
    normalize_text("coeur vaillant"): "Cœur Vaillant",
    normalize_text("oeil attentif"): "Œil Attentif",
    normalize_text("esprit salvateur"): "Esprit Salvateur",
}
_MISSING = object()


def _manual_card_static_key(card: dict[str, Any]) -> tuple[str, str, int]:
    try:
        index = int(card.get("index") or 0)
    except (TypeError, ValueError):
        index = 0
    return (
        str(card.get("manual_chapter_id") or ""),
        str(card.get("manual_stage_id") or ""),
        index,
    )


class GuideUltimeManualConditionsMixin:
    """Runtime conditions backed by the authored manual manifest."""

    def _manual_manifest(self) -> dict[str, Any]:
        cached = getattr(self, "_manual_manifest_cache", None)
        if isinstance(cached, dict):
            return cached
        payload = json.loads((self.manual_dir / "manifest_v1.json").read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("manifest_v1.json doit être un objet JSON")
        self._manual_manifest_cache = payload
        return payload

    def _manual_class_route(self) -> dict[str, Any] | None:
        cached = getattr(self, "_manual_class_route_cache", None)
        if cached is False:
            return None
        if isinstance(cached, dict):
            return cached
        canonical = self._manual_manifest().get("canonical") or {}
        for meta in canonical.get("conditional_routes", []) or []:
            if not isinstance(meta, dict):
                continue
            if str(meta.get("selector") or "").strip() != "actual_character_class":
                continue
            filename = str(meta.get("file") or "").strip()
            if not filename:
                continue
            route = json.loads((self.manual_dir / filename).read_text(encoding="utf-8"))
            trigger = route.get("trigger") if isinstance(route.get("trigger"), dict) else {}
            branches = route.get("branches") if isinstance(route.get("branches"), dict) else {}
            expected = self._as_int(meta.get("option_count"))
            hard_checks = route.get("hard_checks") if isinstance(route.get("hard_checks"), dict) else {}
            hard_expected = self._as_int(hard_checks.get("expected_branch_count"))
            if expected is not None and len(branches) != expected:
                raise ValueError(f"Route de classe {filename}: {len(branches)} branches au lieu de {expected}")
            if hard_expected is not None and len(branches) != hard_expected:
                raise ValueError(f"Route de classe {filename}: hard check {hard_expected} non respecté")
            if not bool(meta.get("manual_selection_forbidden")) or not bool(route.get("trigger", {}).get("manual_selection_forbidden")):
                raise ValueError(f"Route de classe {filename}: la sélection manuelle doit rester interdite")
            self._manual_class_route_cache = {
                "id": str(meta.get("id") or "astrub_class_branches"),
                "file": filename,
                "route": route,
                "trigger": trigger,
                "branches": branches,
            }
            return self._manual_class_route_cache
        self._manual_class_route_cache = False
        return None

    def _character_class_key(self, character_key: str) -> str:
        gate = self._manual_class_route()
        branches = gate.get("branches") if isinstance(gate, dict) else {}
        if not branches:
            return ""
        character_id = character_id_from_key(character_key)
        if character_id is None:
            return ""

        binding_path = Path(
            getattr(self, "network_character_binding_path", NETWORK_CHARACTER_BINDINGS_FILE)
        )
        binding_payload = read_json_file(binding_path, {})
        identities = (
            binding_payload.get("characters", {})
            if isinstance(binding_payload, dict)
            else {}
        )
        row = identities.get(str(character_id), {}) if isinstance(identities, dict) else {}
        if (
            not isinstance(row, dict)
            or str(row.get("source") or "") != "verified_network_identity"
        ):
            return ""

        explicit = normalize_text(row.get("class_key"))
        if explicit in branches:
            return explicit
        inferred = self._infer_class_key_from_text(row.get("name"), branches)
        if inferred:
            return inferred
        return ""

    @staticmethod
    def _infer_class_key_from_text(value: Any, branches: dict[str, Any]) -> str:
        tokens = set(normalize_text(value).split("_"))
        if not tokens:
            return ""
        for raw_key in branches:
            key = normalize_text(raw_key)
            if key and key in tokens:
                return key
        return ""

    def _completed_class_key(
        self,
        character_key: str,
        gate: dict[str, Any],
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> str:
        if completed_quests is None and character_id_from_key(character_key) is None:
            return ""
        completed: list[str] = []
        for raw_key, branch in (gate.get("branches") or {}).items():
            if not isinstance(branch, dict):
                continue
            qid = self._quest_id_for_name(branch.get("quest"))
            if qid is None:
                continue
            done = (
                qid in completed_quests
                if completed_quests is not None
                else self.quest_progress.is_quest_completed(character_key, qid)
            )
            if done:
                completed.append(normalize_text(raw_key))
        return completed[0] if len(completed) == 1 else ""

    def _selected_class_branch(
        self,
        character_key: str,
        gate: dict[str, Any] | None,
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        if not gate:
            return "", None
        class_key = self._character_class_key(character_key) or self._completed_class_key(
            character_key,
            gate,
            completed_quests,
        )
        branch = (gate.get("branches") or {}).get(class_key)
        return class_key, branch if isinstance(branch, dict) else None

    def _manual_class_gate_for_card_uncached(self, card: dict[str, Any]) -> dict[str, Any] | None:
        gate = self._manual_class_route()
        if not gate:
            return None
        trigger = gate.get("trigger") if isinstance(gate.get("trigger"), dict) else {}
        start_key = normalize_text(trigger.get("quest"))
        end_key = normalize_text(trigger.get("end_unlock"))
        card_names = {normalize_text(value) for value in card.get("manual_quest_names", []) or [] if normalize_text(value)}
        if start_key and end_key and start_key in card_names and end_key in card_names:
            return gate
        text = normalize_text(" ".join(str(row.get("text") or "") for row in card.get("manual_lines", []) or [] if isinstance(row, dict)))
        if normalize_text(gate.get("file")) in text:
            return gate
        return None

    def manual_class_gate_for_card(self, card: dict[str, Any]) -> dict[str, Any] | None:
        key = _manual_card_static_key(card)
        cache = getattr(self, "_manual_class_gate_by_card_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._manual_class_gate_by_card_cache = cache
        cached = cache.get(key, _MISSING)
        if cached is not _MISSING:
            return cached if isinstance(cached, dict) else None
        gate = self._manual_class_gate_for_card_uncached(card)
        cache[key] = gate if isinstance(gate, dict) else False
        return gate

    def _manual_class_quest_detail_lines(self, branch: dict[str, Any]) -> list[dict[str, Any]]:
        """Reuse the enriched Quest catalogue instead of duplicating 19 walkthroughs."""

        quest_name = str(branch.get("quest") or "").strip()
        quest_id = self._quest_id_for_name(quest_name)
        provider = getattr(self, "quest_provider", None)
        if not quest_name or quest_id is None or provider is None:
            return []
        try:
            quest = provider.get_quest(quest_id)
        except Exception:
            return []
        if quest is None:
            return []

        result: list[dict[str, Any]] = []
        try:
            steps = quest_solution_steps(quest)
        except Exception:
            return []
        for step in steps:
            for objective in step.objectives:
                text = " ".join(str(objective.text or "").split()).strip()
                if not text:
                    continue
                result.append({
                    "kind": "action",
                    "position": str(objective.position or "").strip(),
                    "text": text,
                })
        return self._dedupe_lines(result)

    def _manual_class_branch_lines(self, character_key: str, gate: dict[str, Any]) -> list[dict[str, Any]]:
        class_key, branch = self._selected_class_branch(character_key, gate)
        if not class_key or not branch:
            return [{
                "kind": "warning",
                "position": "",
                "text": "Classe non détectée pour ce personnage. Ouvre sa fenêtre DOFUS dans l'Organizer : la sous-route de classe sera chargée automatiquement, sans choix manuel.",
            }]

        quest = str(branch.get("quest") or "").strip()
        trigger = gate.get("trigger") if isinstance(gate.get("trigger"), dict) else {}
        end_unlock = str(trigger.get("end_unlock") or "").strip()
        result: list[dict[str, Any]] = []
        chief = branch.get("chief") if isinstance(branch.get("chief"), list) else []
        if len(chief) >= 2 and self._as_int(chief[0]) is not None and self._as_int(chief[1]) is not None:
            position = f"[{self._as_int(chief[0])},{self._as_int(chief[1])}]"
        else:
            position = ""
        if quest:
            result.append({"kind": "action", "position": position, "text": f"Prends « {quest} » auprès du responsable de ta classe."})

        for prep in branch.get("preparation", []) or []:
            if not isinstance(prep, dict):
                continue
            name = str(prep.get("name") or "").strip()
            quantity = prep.get("quantity")
            if not name:
                continue
            if normalize_text(name) == "kamas" and quantity not in (None, ""):
                text = f"Prévois {quantity} kamas avant de partir."
            else:
                text = f"Prépare {quantity} × {name}." if quantity not in (None, "") else f"Prépare {name}."
            result.append({"kind": "warning", "position": "", "text": text})

        detail_lines = self._manual_class_quest_detail_lines(branch)
        result.extend(detail_lines)
        covered_positions: set[tuple[int, int]] = set()
        for row in detail_lines:
            coords = self._coords_from_text(str(row.get("position") or ""))
            if coords is not None:
                covered_positions.add(coords)

        points = branch.get("route_points") if isinstance(branch.get("route_points"), list) else []
        first_point = True
        for raw in points:
            if not isinstance(raw, list) or len(raw) < 2:
                continue
            x = self._as_int(raw[0])
            y = self._as_int(raw[1])
            if x is None or y is None:
                continue
            if first_point and position == f"[{x},{y}]":
                first_point = False
                continue
            first_point = False
            if (x, y) in covered_positions:
                continue
            result.append({
                "kind": "action",
                "position": f"[{x},{y}]",
                "text": "Effectue l'objectif actif de la quête en cours sur cette carte, puis poursuis le trajet.",
            })

        if end_unlock:
            result.append({
                "kind": "action",
                "position": "",
                "text": f"Quand la quête de classe est terminée, lance « {end_unlock} » puis reprends la route commune.",
            })
        return self._dedupe_lines(result)

    @staticmethod
    def _class_placeholder_line(row: dict[str, Any], gate: dict[str, Any]) -> bool:
        text = normalize_text(row.get("text"))
        filename = normalize_text(gate.get("file"))
        return bool(
            (filename and filename in text)
            or "sous_route_de_la_classe_reelle" in text
            or "sous_route_de_classe" in text
        )

    def _manual_order_routes(self) -> tuple[dict[str, Any], ...]:
        cached = getattr(self, "_manual_order_routes_cache", None)
        if isinstance(cached, tuple):
            return cached
        canonical = self._manual_manifest().get("canonical") or {}
        result: list[dict[str, Any]] = []
        for meta in canonical.get("conditional_routes", []) or []:
            if not isinstance(meta, dict):
                continue
            route_id = str(meta.get("id") or "").strip()
            filename = str(meta.get("file") or "").strip()
            if not route_id.startswith("bonta_order_rank") or not filename:
                continue
            route = load_manual_chapter(self.manual_dir / filename)
            trigger = route.get("trigger") if isinstance(route.get("trigger"), dict) else {}
            rank = self._as_int(
                trigger.get("minimum_alignment_rank")
                or trigger.get("minimum_rank")
                or route_id.removeprefix("bonta_order_rank")
            )
            required = str(trigger.get("required_quest") or trigger.get("after_quest") or "").strip()
            options = route.get("options") if isinstance(route.get("options"), dict) else {}
            if rank is not None and required and options:
                result.append({
                    "id": route_id,
                    "rank": rank,
                    "required_quest": required,
                    "required_quest_key": normalize_text(required),
                    "route": route,
                    "options": options,
                })
        result.sort(key=lambda row: int(row["rank"]))
        self._manual_order_routes_cache = tuple(result)
        return self._manual_order_routes_cache

    def bonta_order_names(self) -> tuple[str, ...]:
        routes = self._manual_order_routes()
        if not routes:
            return ()
        options = routes[0].get("options") or {}
        labels = [_ORDER_LABELS.get(normalize_text(key), str(key).strip().title()) for key in options]
        wanted = ("Cœur Vaillant", "Œil Attentif", "Esprit Salvateur")
        return tuple(next(label for label in labels if normalize_text(label) == normalize_text(name)) for name in wanted)

    def set_bonta_order(self, character_key: str, order_name: str) -> None:
        existing = self.selected_order_name(character_key)
        if existing and normalize_text(existing) != normalize_text(order_name):
            raise ValueError("L'Ordre Bonta est déjà choisi pour ce personnage et ne peut plus être changé.")
        super().set_bonta_order(character_key, order_name)

    def selected_order_quest_ids(self, character_key: str) -> tuple[int, ...]:
        selected = normalize_text(self.selected_order_name(character_key))
        result: list[int] = []
        if not selected:
            return ()
        for gate in self._manual_order_routes():
            option = self._selected_order_option(gate, selected)
            qid = self._quest_id_for_name(option.get("quest")) if option else None
            if qid is not None and qid not in result:
                result.append(qid)
        return tuple(result)

    def _card_success_ids_uncached(self, card: dict[str, Any]) -> tuple[int, ...]:
        result = list(super().card_success_ids(card))
        index = self._manual_achievement_name_index()
        for name in card.get("manual_success_names", []) or []:
            aid = index.get(normalize_text(name))
            if aid is not None and aid not in result:
                result.append(aid)
        return tuple(result)

    def _contract_success_index(self) -> dict[str, tuple[int, ...]] | None:
        contract = getattr(self, "auto_validation_contract", None)
        if not isinstance(contract, dict):
            return None
        contract_id = id(contract)
        cached = getattr(self, "_contract_success_ids_cache", None)
        if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == contract_id:
            return cached[1]
        index: dict[str, tuple[int, ...]] = {}
        for row in contract.get("cards", []) or []:
            if not isinstance(row, dict):
                continue
            card_key = str(row.get("card_key") or "").strip()
            if not card_key:
                continue
            ids: list[int] = []
            for target in row.get("successes", []) or []:
                if not isinstance(target, dict):
                    continue
                achievement_id = self._as_int(target.get("achievement_id"))
                if achievement_id is not None and achievement_id > 0 and achievement_id not in ids:
                    ids.append(achievement_id)
            index[card_key] = tuple(ids)
        self._contract_success_ids_cache = (contract_id, index)
        return index

    def card_success_ids(self, card: dict[str, Any]) -> tuple[int, ...]:
        index = self._contract_success_index()
        if index is None:
            return self._card_success_ids_uncached(card)
        result = list(super().card_success_ids(card))
        card_key = self.card_key(card, 0)
        for achievement_id in index.get(card_key, ()):
            if achievement_id not in result:
                result.append(achievement_id)
        return tuple(result)

    def _manual_achievement_name_index(self) -> dict[str, int]:
        cached = getattr(self, "_manual_achievement_name_index_cache", None)
        if isinstance(cached, dict):
            return cached
        provider = getattr(self, "achievement_provider", None)
        grouped: dict[str, set[int]] = {}
        try:
            achievements = provider.load_all() if provider is not None else []
        except Exception:
            achievements = []
        for achievement in achievements:
            key = normalize_text(getattr(achievement, "name", ""))
            aid = self._as_int(getattr(achievement, "id", None))
            if key and aid is not None:
                grouped.setdefault(key, set()).add(aid)
        self._manual_achievement_name_index_cache = {
            key: next(iter(ids)) for key, ids in grouped.items() if len(ids) == 1
        }
        return self._manual_achievement_name_index_cache

    def _manual_order_gate_for_card_uncached(self, card: dict[str, Any]) -> dict[str, Any] | None:
        card_ids = {
            qid for qid in (self._as_int(value) for value in card.get("manual_quest_ids", []) or [])
            if qid is not None
        }
        text = normalize_text(" ".join([
            str(card.get("manual_title") or ""),
            *(str(row.get("text") or "") for row in card.get("manual_lines", []) or [] if isinstance(row, dict)),
        ]))
        for gate in self._manual_order_routes():
            qid = self._quest_id_for_name(gate.get("required_quest"))
            if qid is not None and qid in card_ids:
                return gate
            if str(gate.get("required_quest_key") or "") in text:
                return gate
        return None

    def manual_order_gate_for_card(self, card: dict[str, Any]) -> dict[str, Any] | None:
        key = _manual_card_static_key(card)
        cache = getattr(self, "_manual_order_gate_by_card_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._manual_order_gate_by_card_cache = cache
        cached = cache.get(key, _MISSING)
        if cached is not _MISSING:
            return cached if isinstance(cached, dict) else None
        gate = self._manual_order_gate_for_card_uncached(card)
        cache[key] = gate if isinstance(gate, dict) else False
        return gate

    def manual_order_choice_required(self, character_key: str, card: dict[str, Any]) -> bool:
        if self.selected_order_name(character_key):
            return False
        gate = self.manual_order_gate_for_card(card)
        if gate is None or self._as_int(gate.get("rank")) != 20:
            return False
        qid = self._quest_id_for_name(gate.get("required_quest"))
        return bool(qid is not None and self.quest_progress.is_quest_completed(character_key, qid))

    def manual_order_choice_blocking(self, character_key: str, card: dict[str, Any]) -> bool:
        gate = self.manual_order_gate_for_card(card)
        return bool(gate and self._as_int(gate.get("rank")) == 20 and not self.selected_order_name(character_key))

    def manual_order_options_for_card(self, card: dict[str, Any]) -> tuple[str, ...]:
        gate = self.manual_order_gate_for_card(card)
        return self.bonta_order_names() if gate and self._as_int(gate.get("rank")) == 20 else ()

    def manual_lines_for_card(self, character_key: str, card: dict[str, Any]) -> list[dict[str, Any]]:
        base = copy.deepcopy([row for row in card.get("manual_lines", []) or [] if isinstance(row, dict)])
        class_gate = self.manual_class_gate_for_card(card)
        if class_gate:
            class_lines = self._manual_class_branch_lines(character_key, class_gate)
            result: list[dict[str, Any]] = []
            injected = False
            for row in base:
                if self._class_placeholder_line(row, class_gate):
                    if not injected:
                        result.extend(copy.deepcopy(class_lines))
                        injected = True
                    continue
                result.append(row)
            if not injected:
                result.extend(copy.deepcopy(class_lines))
        else:
            result = base

        self._append_temporal_policy_lines(result, card)
        self._append_ocre_policy_lines(result, card)
        gate = self.manual_order_gate_for_card(card)
        selected = normalize_text(self.selected_order_name(character_key))
        option = self._selected_order_option(gate, selected) if gate and selected else None
        if option:
            stage = self._order_option_as_stage(gate, option)
            names = [normalize_text(str(option.get("quest") or ""))]
            result.extend(self._stage_lines(stage, [name for name in names if name]))
        return self._dedupe_lines(result)

    def card_automatic_values(
        self,
        character_key: str,
        card: dict[str, Any],
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> tuple[bool, ...]:
        values = list(
            super().card_automatic_values(
                character_key,
                card,
                completed_quests=completed_quests,
            )
        )
        class_gate = self.manual_class_gate_for_card(card)
        if class_gate:
            _, branch = self._selected_class_branch(character_key, class_gate, completed_quests)
            qid = self._quest_id_for_name(branch.get("quest")) if branch else None
            if qid is not None:
                values.append(
                    qid in completed_quests
                    if completed_quests is not None
                    else self.quest_progress.is_quest_completed(character_key, qid)
                )
            else:
                values.append(False)

        gate = self.manual_order_gate_for_card(card)
        selected = normalize_text(self.selected_order_name(character_key))
        option = self._selected_order_option(gate, selected) if gate and selected else None
        qid = self._quest_id_for_name(option.get("quest")) if option else None
        if qid is not None:
            values.append(
                qid in completed_quests
                if completed_quests is not None
                else self.quest_progress.is_quest_completed(character_key, qid)
            )
        return tuple(values)

    def card_auto_complete(
        self,
        character_key: str,
        card: dict[str, Any],
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> bool:
        class_gate = self.manual_class_gate_for_card(card)
        if class_gate:
            _, branch = self._selected_class_branch(character_key, class_gate, completed_quests)
            if branch is None:
                return False
        return (
            False
            if self.manual_order_choice_blocking(character_key, card)
            else super().card_auto_complete(
                character_key,
                card,
                completed_quests=completed_quests,
            )
        )

    def card_state(
        self,
        character_key: str,
        card: dict[str, Any],
        fallback_index: int = 0,
        completed_quests: set[int] | frozenset[int] | None = None,
    ):
        state = super().card_state(
            character_key,
            card,
            fallback_index,
            completed_quests=completed_quests,
        )

        class_gate = self.manual_class_gate_for_card(card)
        if class_gate:
            _, branch = self._selected_class_branch(character_key, class_gate, completed_quests)
            qid = self._quest_id_for_name(branch.get("quest")) if branch else None
            done = bool(
                qid is not None
                and (
                    qid in completed_quests
                    if completed_quests is not None
                    else self.quest_progress.is_quest_completed(character_key, qid)
                )
            )
            if not done:
                state = self._incomplete_state(state)

        gate = self.manual_order_gate_for_card(card)
        if gate is None:
            return state
        selected = normalize_text(self.selected_order_name(character_key))
        if not selected:
            if self._as_int(gate.get("rank")) != 20:
                return state
            return self._incomplete_state(state)
        option = self._selected_order_option(gate, selected)
        qid = self._quest_id_for_name(option.get("quest")) if option else None
        if qid is None:
            return state
        done = (
            qid in completed_quests
            if completed_quests is not None
            else self.quest_progress.is_quest_completed(character_key, qid)
        )
        return state if done else self._incomplete_state(state)

    @staticmethod
    def _incomplete_state(state):
        return type(state)(
            complete=False,
            historical=state.historical,
            automatic_done=state.automatic_done,
            automatic_total=max(state.automatic_total, state.automatic_done + 1),
            manual_done=0,
            manual_total=state.manual_total,
        )

    def first_incomplete_index(self, character_key: str) -> int:
        # This is the production manual route override. Keep the same freshness
        # and revision cache contract as GuideUltimeRuntimeService while applying
        # the authored class/Order conditions above.
        self.reload_progress()
        cache_key_getter = getattr(self, "_route_cache_key", None)
        cache_key = cache_key_getter(character_key) if callable(cache_key_getter) else None
        cache = getattr(self, "_first_incomplete_cache", None)
        if cache_key is not None and isinstance(cache, dict) and cache_key in cache:
            return int(cache[cache_key])

        completed_quests = self.quest_progress.completed_quest_ids(character_key)
        result = max(0, len(self.cards) - 1)
        for index, card in enumerate(self.cards):
            if not self.card_state(
                character_key,
                card,
                index,
                completed_quests=completed_quests,
            ).complete:
                result = index
                break

        if callable(cache_key_getter):
            self._first_incomplete_cache = {cache_key_getter(character_key): result}
        return result

    def _append_ocre_policy_lines(self, result: list[dict[str, Any]], card: dict[str, Any]) -> None:
        stage = card.get("manual_stage_data") if isinstance(card.get("manual_stage_data"), dict) else {}
        if not stage:
            return
        transition = stage.get("capture_transition")
        if transition:
            self._append_player_value(
                result,
                transition,
                [normalize_text(value) for value in card.get("manual_quest_names", []) or []],
                kind="warning",
                preparation=True,
            )

        registry = self._manual_ocre_registry()
        if not registry:
            return
        if transition:
            result.extend(ocre_unlock_policy_lines(registry))
        result.extend(
            ocre_capture_lines(
                stage,
                registry,
                capture_unlocked=self._ocre_capture_unlocked_for_card(card),
                existing_lines=result,
            )
        )

    def _ocre_capture_unlocked_for_card(self, card: dict[str, Any]) -> bool:
        current_index = self._as_int(card.get("index"))
        if current_index is None:
            return False
        cached = getattr(self, "_ocre_capture_unlock_index_cache", _MISSING)
        if cached is _MISSING:
            unlock_index: int | None = None
            for candidate in getattr(self, "cards", ()):
                if not isinstance(candidate, dict):
                    continue
                stage = candidate.get("manual_stage_data")
                if not isinstance(stage, dict) or not stage.get("capture_transition"):
                    continue
                unlock_index = self._as_int(candidate.get("index"))
                break
            self._ocre_capture_unlock_index_cache = unlock_index
        else:
            unlock_index = cached if isinstance(cached, int) else None
        return bool(unlock_index is not None and current_index >= unlock_index)

    def _manual_ocre_registry(self) -> dict[str, Any]:
        cached = getattr(self, "_manual_ocre_registry_cache", None)
        if isinstance(cached, dict):
            return cached
        self._manual_ocre_registry_cache = load_ocre_capture_registry(
            self.manual_dir,
            self._manual_manifest(),
        )
        return self._manual_ocre_registry_cache

    def _append_temporal_policy_lines(self, result: list[dict[str, Any]], card: dict[str, Any]) -> None:
        hooks = [str(value).strip() for value in card.get("manual_temporal_hooks", []) or [] if str(value).strip()]
        if not hooks:
            return
        entries = {
            str(row.get("id") or ""): row
            for row in self._manual_temporal_registry().get("entries", []) or []
            if isinstance(row, dict) and str(row.get("id") or "").strip()
        }
        for hook in hooks:
            policy = self._temporal_player_instruction(entries.get(hook, {}))
            if policy:
                result.append({"kind": "warning", "position": "", "text": policy})

    @staticmethod
    def _temporal_player_instruction(entry: dict[str, Any]) -> str:
        opened = str(entry.get("open_local_time") or "").strip()
        closed = str(entry.get("close_local_time") or "").strip()
        if str(entry.get("type") or "") == "daily_time_window" and opened and closed:
            npc = str(entry.get("npc") or "").strip()
            text = f"Entre {opened} et {closed}, fais les interactions prévues{f' avec {npc}' if npc else ''}."
            if bool(entry.get("hard_wait_forbidden")):
                text += " Si la fenêtre est fermée, continue le guide et reviens à la prochaine fenêtre ; n'attends pas sur place."
            return text
        return str(entry.get("route_policy") or "").strip()

    def _manual_temporal_registry(self) -> dict[str, Any]:
        cached = getattr(self, "_manual_temporal_registry_cache", None)
        if isinstance(cached, dict):
            return cached
        canonical = self._manual_manifest().get("canonical") or {}
        filename = str(canonical.get("temporal_registry") or "").strip()
        self._manual_temporal_registry_cache = load_temporal_registry(self.manual_dir / filename) if filename else {}
        return self._manual_temporal_registry_cache

    def _selected_order_option(self, gate: dict[str, Any] | None, selected: str) -> dict[str, Any] | None:
        if not gate or not selected:
            return None
        for raw_key, option in (gate.get("options") or {}).items():
            if not isinstance(option, dict):
                continue
            label = _ORDER_LABELS.get(normalize_text(raw_key), str(raw_key).strip().title())
            if selected in {normalize_text(raw_key), normalize_text(label)}:
                return option
        return None

    def _quest_id_for_name(self, value: Any) -> int | None:
        return self._as_int(getattr(self, "_quest_name_to_id", {}).get(normalize_text(value)))

    def _order_option_as_stage(self, gate: dict[str, Any], option: dict[str, Any]) -> dict[str, Any]:
        route = gate.get("route") if isinstance(gate.get("route"), dict) else {}
        shared = route.get("shared_contract") if isinstance(route.get("shared_contract"), dict) else {}
        shared_dungeon = route.get("shared_dungeon_contract") if isinstance(route.get("shared_dungeon_contract"), dict) else {}
        preparation: list[Any] = []
        instructions: list[Any] = []
        route_rows: list[Any] = []
        hard_exit: list[Any] = []
        for source in (shared, shared_dungeon, option):
            if isinstance(source.get("preparation"), list):
                preparation.extend(copy.deepcopy(source["preparation"]))
        for key in ("route", "pre_ougah_route", "post_ougah_route"):
            if isinstance(option.get(key), list):
                route_rows.extend(copy.deepcopy(option[key]))
        for source in (shared, shared_dungeon):
            policy = source.get("route_policy")
            instructions.extend(copy.deepcopy(policy) if isinstance(policy, list) else [policy] if isinstance(policy, str) and policy.strip() else [])
            if isinstance(source.get("before_exit"), str) and source["before_exit"].strip():
                hard_exit.append(source["before_exit"])
        if isinstance(option.get("ougah_actions"), list):
            instructions.extend(copy.deepcopy(option["ougah_actions"]))
        if isinstance(option.get("hard_exit"), list):
            hard_exit.extend(copy.deepcopy(option["hard_exit"]))
        elif isinstance(option.get("hard_exit"), str) and option["hard_exit"].strip():
            hard_exit.append(option["hard_exit"])
        dungeon = str(shared.get("dungeon") or shared_dungeon.get("dungeon") or "").strip()
        return {
            "quests": [str(option.get("quest") or "").strip()],
            "preparation": preparation,
            "route": route_rows,
            "instructions": instructions,
            "hard_exit": hard_exit,
            "dungeon": dungeon or None,
        }
