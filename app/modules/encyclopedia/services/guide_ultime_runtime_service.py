from __future__ import annotations

from typing import Any

from app.modules.encyclopedia.services.guide_ultime_generated_service import (
    GuideUltimeCardState,
    GuideUltimeGeneratedService,
    _norm,
    _safe_int,
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

    def route_sheet_progress(self, character_key: str) -> tuple[int, int]:
        """Return completion of the route units actually rendered to the player."""
        self.reload_progress()
        cache_key = self._route_cache_key(character_key)
        cache = getattr(self, "_route_sheet_progress_cache", None)
        if isinstance(cache, dict) and cache_key in cache:
            return cache[cache_key]

        total = len(self.cards)
        completed_quests = self.quest_progress.completed_quest_ids(character_key)
        completed = sum(
            1
            for index, card in enumerate(self.cards)
            if self.card_state(
                character_key,
                card,
                index,
                completed_quests=completed_quests,
            ).complete
        )
        result = (completed, total)

        # A lazy legacy-key migration may have published a new guide generation
        # while card_state() was evaluated. Store under the final revision so the
        # immediately following header/navigation read can reuse the result.
        self._route_sheet_progress_cache = {self._route_cache_key(character_key): result}
        return result

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
        available: dict[str, str] = {}
        branches = self.route.get("conditional_branches") if isinstance(self.route.get("conditional_branches"), dict) else {}
        for card in branches.get("order_cards", []) or []:
            if not isinstance(card, dict):
                continue
            for row in card.get("options", []) or []:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("order") or "").strip()
                if name:
                    available.setdefault(_norm(name), name)
        return tuple(
            available[_norm(expected)]
            for expected in BONTA_ORDERS
            if _norm(expected) in available
        )

    def selected_order_quest_ids(self, character_key: str) -> tuple[int, ...]:
        selected = self.selected_order_name(character_key)
        if not selected or _norm(selected) not in {_norm(value) for value in self.bonta_order_names()}:
            return ()
        branches = self.route.get("conditional_branches") if isinstance(self.route.get("conditional_branches"), dict) else {}
        ids: list[int] = []
        for card in branches.get("order_cards", []) or []:
            if not isinstance(card, dict):
                continue
            option = next(
                (
                    row for row in card.get("options", []) or []
                    if isinstance(row, dict) and _norm(row.get("order")) == _norm(selected)
                ),
                None,
            )
            qid = _safe_int(option.get("quest_id")) if option else None
            if qid is not None:
                ids.append(qid)
        return tuple(ids[:5])

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
        # This method is also called directly by navigation handlers. Refresh the
        # three progress snapshots before consulting the cache so a peer/external
        # write cannot be hidden behind an otherwise valid old cache entry.
        self.reload_progress()
        cache_key = self._route_cache_key(character_key)
        cache = getattr(self, "_first_incomplete_cache", None)
        if isinstance(cache, dict) and cache_key in cache:
            return int(cache[cache_key])

        # Fast migration path: historical completed cards are skipped from cached
        # set membership, avoiding thousands of QWidget/state-level operations.
        completed_quests = self.quest_progress.completed_quest_ids(character_key)
        achievement_state = self.achievement_progress.state_for(character_key)
        result = max(0, len(self.cards) - 1)
        for index, card in enumerate(self.cards):
            quest_ids = self.card_quest_ids(card)
            success_ids = self.card_success_ids(card)
            historical_auto_done = (
                bool(quest_ids)
                and all(qid in completed_quests for qid in quest_ids)
                and all(achievement_state.is_achievement_completed(aid) for aid in success_ids)
                and self.class_gate_satisfied(character_key, card, completed_quests)
            )
            if historical_auto_done:
                continue
            if not self.card_state(
                character_key,
                card,
                index,
                completed_quests=completed_quests,
            ).complete:
                result = index
                break

        self._first_incomplete_cache = {self._route_cache_key(character_key): result}
        return result
