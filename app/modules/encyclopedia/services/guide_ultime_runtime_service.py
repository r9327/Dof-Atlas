from __future__ import annotations

from typing import Any

from app.modules.encyclopedia.services.guide_ultime_generated_service import (
    GuideUltimeCardState,
    GuideUltimeGeneratedService,
    _norm,
    _safe_int,
    route_order_names, route_order_quest_ids,
)


BONTA_ORDERS = (
    "Coeur Vaillant",
    "Oeil Attentif",
    "Esprit Salvateur",
)


class GuideUltimeRuntimeService(GuideUltimeGeneratedService):
    """Application policy layer for the locked V5 universal contract.

    The generated conditional payload can carry every alignment branch for audit
    completeness. The application contract is Bonta-only, so runtime exposes
    exactly the three Bonta Orders without deleting anything from the artifact.
    """

    @staticmethod
    def _progress_service_revision(service: Any) -> tuple[Any, Any]:
        """Return the currently published revision without parsing progress JSON."""

        coordinator = getattr(service, "_coordinator", None)
        generation = (
            getattr(coordinator, "generation", None)
            if coordinator is not None
            else getattr(service, "_seen_generation", None)
        )
        signature_getter = getattr(service, "_current_disk_signature", None)
        disk_signature = (
            signature_getter()
            if callable(signature_getter)
            else getattr(service, "_disk_signature", None)
        )
        return generation, disk_signature

    def _route_cache_key(self, character_key: str) -> tuple[Any, ...]:
        """Key expensive route scans by route identity and persistent progress revision."""

        return (
            str(character_key or ""),
            id(self.cards),
            len(self.cards),
            self._progress_service_revision(self.quest_progress),
            self._progress_service_revision(self.achievement_progress),
            self._progress_service_revision(self.guide_progress),
        )

    def card_key(self, card: dict[str, Any], fallback_index: int = 0) -> str:
        """Return a persistent identity that survives manual-route reordering.

        Generated V5 cards keep their historical ``gps:<index>`` identity. Manual
        cards instead use their authored chapter/stage identifiers so inserting a
        new sheet earlier in the route can never move a player's completion onto
        another sheet.
        """
        if card.get("manual_source"):
            chapter_id = str(card.get("manual_chapter_id") or "").strip()
            stage_id = str(card.get("manual_stage_id") or "").strip()
            if stage_id:
                return f"manual:{chapter_id or 'route'}:{stage_id}"
        return super().card_key(card, fallback_index)

    @staticmethod
    def _legacy_manual_page_key(card: dict[str, Any], fallback_index: int = 0) -> str:
        raw_index = _safe_int(card.get("index"))
        return f"page:gps:{raw_index if raw_index is not None else fallback_index}"

    def page_checked(self, character_key: str, card: dict[str, Any], fallback_index: int = 0) -> bool:
        stable_key = self.page_key(card, fallback_index)
        if self.manual_checked(character_key, stable_key):
            return True
        if not card.get("manual_source"):
            return False

        # One-way lazy migration from the old positional key. This happens before
        # future route insertions can shift card indexes, then removes the legacy
        # key so subsequent reads are unambiguous.
        legacy_key = self._legacy_manual_page_key(card, fallback_index)
        if legacy_key == stable_key or not self.manual_checked(character_key, legacy_key):
            return False
        self.set_manual_checked(character_key, stable_key, True)
        self.set_manual_checked(character_key, legacy_key, False)
        return True

    def _remember_route_result(self, attribute: str, key: tuple, value: Any) -> None:
        """Keep at most eight characters of the current route/revision only."""
        cache = getattr(self, attribute, {})
        current = {k: v for k, v in cache.items() if k[1:] == key[1:]}
        current.pop(key, None)
        current[key] = value
        while len(current) > 8:
            current.pop(next(iter(current)))
        setattr(self, attribute, current)

    def _cached_completion(self, key: tuple) -> bytes | None:
        return getattr(self, "_route_completion_cache", {}).get(key)

    def route_completion_flags(self, character_key: str) -> bytes:
        """One compact, revision-scoped completion result per route sheet."""
        self.reload_progress()
        key = self._route_cache_key(character_key)
        cached = self._cached_completion(key)
        if cached is not None:
            return cached
        completed_quests = self.quest_progress.completed_quest_ids(character_key)
        flags = bytes(
            bool(self.card_state(
                character_key, card, index, completed_quests=completed_quests,
            ).complete)
            for index, card in enumerate(self.cards)
        )
        # Never publish a scan under a different revision. Legacy-key migration
        # or a concurrent progress writer may have changed it during evaluation.
        if self._route_cache_key(character_key) == key:
            self._remember_route_result("_route_completion_cache", key, flags)
        return flags

    def route_sheet_progress(self, character_key: str) -> tuple[int, int]:
        """Return completion of the same sheets used by team and preparation."""
        flags = self.route_completion_flags(character_key)
        return flags.count(1), len(flags)

    def active_route_card(self, character_key: str) -> tuple[int, dict[str, Any] | None]:
        """Return the canonical current sheet, or no card when the route is empty."""
        if not self.cards:
            return 0, None
        completed, total = self.route_sheet_progress(character_key)
        if total and completed >= total:
            return total - 1, self.cards[-1]
        index = self.first_incomplete_index(character_key)
        return index, self.cards[index]

    def bonta_order_names(self) -> tuple[str, ...]:
        available = route_order_names(self.route)
        return tuple(available[_norm(expected)] for expected in BONTA_ORDERS
                     if _norm(expected) in available)

    def selected_order_quest_ids(self, character_key: str) -> tuple[int, ...]:
        selected = self.selected_order_name(character_key)
        if not selected or _norm(selected) not in {_norm(value) for value in self.bonta_order_names()}:
            return ()
        return route_order_quest_ids(self.route, selected)[:5]

    def class_gate_satisfied(
        self,
        character_key: str,
        card: dict[str, Any],
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> bool:
        gates = [
            row for row in card.get("conditional_branch_gates", []) or []
            if isinstance(row, dict) and str(row.get("gate_type") or "") == "universal_class_card"
        ]
        if not gates:
            return True
        completed = completed_quests
        if completed is None:
            completed = self.quest_progress.completed_quest_ids(character_key)
        for gate in gates:
            options = {
                qid for qid in (_safe_int(value) for value in gate.get("class_quest_options", []) or [])
                if qid is not None
            }
            required = max(1, _safe_int(gate.get("required_count")) or 1)
            if len(options.intersection(completed)) < required:
                return False
        return True

    def card_state(
        self,
        character_key: str,
        card: dict[str, Any],
        fallback_index: int = 0,
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> GuideUltimeCardState:
        state = super().card_state(
            character_key,
            card,
            fallback_index,
            completed_quests=completed_quests,
        )
        gate_ok = self.class_gate_satisfied(character_key, card, completed_quests)
        if gate_ok:
            return state
        return GuideUltimeCardState(
            complete=False,
            historical=state.historical,
            automatic_done=state.automatic_done,
            automatic_total=state.automatic_total + 1,
            manual_done=state.manual_done,
            manual_total=state.manual_total,
        )

    def first_incomplete_index(self, character_key: str) -> int:
        """Use the same completion rule for every derived guide runtime.

        The warm path reuses the complete route snapshot. Cold navigation
        stops at the first incomplete sheet without materializing the route.
        """
        self.reload_progress()
        cache_key = self._route_cache_key(character_key)
        flags = self._cached_completion(cache_key)
        if flags is not None:
            first = flags.find(b"\x00")
            return first if first >= 0 else max(0, len(flags) - 1)
        cache = getattr(self, "_first_incomplete_cache", {})
        if cache_key in cache:
            return int(cache[cache_key])
        completed_quests = self.quest_progress.completed_quest_ids(character_key)
        result = max(0, len(self.cards) - 1)
        for index, card in enumerate(self.cards):
            if not self.card_state(
                character_key, card, index, completed_quests=completed_quests,
            ).complete:
                result = index
                break
        if self._route_cache_key(character_key) == cache_key:
            self._remember_route_result("_first_incomplete_cache", cache_key, result)
        return result
