from __future__ import annotations

import copy
from typing import Any, Callable

from app.modules.encyclopedia.services.guide_ultime_generated_service import (
    GuideUltimeGeneratedService,
    GuideUltimeProgress,
)
from app.modules.encyclopedia.services.guide_shared_route_contract import (
    _identifier as _canonical_source_identifier,
)


class ImportedSourceManualRuntimeService(GuideUltimeGeneratedService):
    """One explicitly supplied source route in the existing shared Guide reader.

    This adapter does NOT discover candidates, import a local directory, attest
    a guide, or publish it to the live catalogue. The application composition
    must inject an independently authorized route before it is reachable from
    ManualRouteGuidesView. No generated V5 fallback or manual manifest is read.
    """

    def __init__(
        self,
        quest_progress: Any,
        achievement_progress: Any,
        guide_progress: Any,
        *,
        route: dict[str, Any],
        gate_evaluator: Callable[[str, dict[str, Any]], bool] | None = None,
    ) -> None:
        # Never call the generated V5 loader: its artifact paths and progress
        # identity belong to the two pre-existing optimized routes.
        super().__init__(
            quest_progress, achievement_progress, guide_progress,
            autoload=False,
        )
        if not isinstance(route, dict):
            raise ValueError("A source Guide route must be an explicit object")
        route_id = route.get("id")
        if not isinstance(route_id, str) or not route_id.startswith("source_guide:"):
            raise ValueError("Canonical source_guide:<id> required")
        source_id = route_id.removeprefix("source_guide:")
        # The projector and the reader must apply the same canonical ID
        # grammar: no whitespace, control characters, traversal or aliases.
        _canonical_source_identifier(source_id, "source guide ID")
        if route.get("source_compliance") != "NOT_CERTIFIED":
            # A staged source projection must not claim certification. The
            # publisher and independent witness control activation externally.
            raise ValueError("Source route cannot self-attest certification")
        cards = route.get("steps")
        if not isinstance(cards, list) or not cards:
            raise ValueError("Source route has no cards")
        known: set[str] = set()
        for index, card in enumerate(cards, 1):
            if not isinstance(card, dict) or card.get("manual_source") is not True:
                raise ValueError("Source route contains a non-source card")
            stage = card.get("source_step_id")
            key = card.get("manual_stage_id")
            if not isinstance(stage, str) or not stage:
                raise ValueError("Source step must have a stable identity")
            _canonical_source_identifier(stage, "source step ID")
            if key != f"source:{source_id}:{stage}" or key in known:
                raise ValueError("Duplicate or mismatched source stage identity")
            if type(card.get("index")) is not int or card["index"] != index:
                raise ValueError("Unexpected source step ordering")
            if not isinstance(card.get("manual_sections"), dict):
                raise ValueError("Source step needs canonical shared UI sections")
            known.add(key)
        # Keep the in-memory snapshot private to this one opened guide. No
        # 95-guide global preloading, cloning of the optimized V5 route or
        # additional file cache.
        self.route = copy.deepcopy(route)
        self.cards = self.route["steps"]
        self.guide_id = route_id
        self.progress_id = route_id
        self.guide_title = str(
            self.route.get("source_guide_metadata", {}).get("title") or source_id
        )
        self._known_stage_ids = frozenset(known)
        # References only: one opened guide, no extra route copy or preload.
        self._canonical_cards = {
            card["manual_stage_id"]: card for card in self.cards
        }
        self._authorization_guard: Callable[[str, dict], bool] | None = None
        self._gate_evaluator = gate_evaluator

    def set_authorization_guard(
        self, guard: Callable[[str, dict], bool],
    ) -> None:
        if not callable(guard):
            raise TypeError("A source authorization guard must be callable")
        self._authorization_guard = guard

    def can_write_progress(self) -> bool:
        guard = self._authorization_guard
        if guard is None:
            return False
        try:
            return guard(self.guide_id, self.route) is True
        except Exception:
            # Authorization can be revoked while a Guide is visible. Never
            # allow a stale page to write just because it was opened earlier.
            return False

    def load(self) -> None:
        """No implicit disk discovery or fallback to the generated V5 route."""
        raise RuntimeError("Imported source routes require explicit injection")

    def reload_progress(self) -> None:
        self.guide_progress.reload()

    def card_key(self, card: dict[str, Any], fallback_index: int = 0) -> str:
        return self.page_key(card, fallback_index)

    def page_key(self, card: dict[str, Any], fallback_index: int = 0) -> str:
        key = card.get("manual_stage_id")
        if not isinstance(key, str) or key not in self._known_stage_ids:
            raise ValueError("Unknown source step; refusing progress attribution")
        return key

    def manual_checked(self, character_key: str, key: str) -> bool:
        return self.guide_progress.is_manual_step_completed(
            character_key, self.progress_id, key,
        )

    def set_manual_checked(
        self, character_key: str, key: str, checked: bool,
    ) -> None:
        ready_prefix = f"__ui:preparation_ready:{self.guide_id}:"
        if not isinstance(key, str) or not (
            key in self._known_stage_ids
            or key == "__ui:shared_route_locked__"
            or (key.startswith(ready_prefix) and len(key) > len(ready_prefix))
        ):
            # Header and preparation have scoped UI keys; other writes must
            # target a canonical step of this exact imported source guide.
            raise ValueError("Unknown or foreign source progress key")
        # Both the page button and the shared UI call this public writer.
        # A direct write must never bypass the canonical per-guide gate.
        if checked and key in self._known_stage_ids and self.manual_order_choice_blocking(
            character_key, self._canonical_cards[key],
        ):
            return
        if not self.can_write_progress():
            return
        self.guide_progress.set_manual_step_completed(
            character_key, self.progress_id, key, bool(checked),
        )

    def page_checked(
        self, character_key: str, card: dict[str, Any], fallback_index: int = 0,
    ) -> bool:
        return self.manual_checked(character_key, self.page_key(card, fallback_index))

    def set_page_checked(
        self, character_key: str, card: dict[str, Any],
        fallback_index: int, checked: bool,
    ) -> None:
        # The public writer below owns the canonical gate exactly once.
        self.set_manual_checked(
            character_key, self.page_key(card, fallback_index), checked,
        )

    def card_automatic_values(
        self, character_key: str, card: dict[str, Any],
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> tuple[bool, ...]:
        # An authored step can mention a quest without being equivalent to
        # its completion. Automatic validation needs per-guide certified proof.
        return ()

    def card_auto_complete(
        self, character_key: str, card: dict[str, Any],
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> bool:
        return False

    def route_sheet_progress(self, character_key: str) -> tuple[int, int]:
        completed = self.guide_progress.manual_steps(character_key, self.progress_id)
        return sum(card["manual_stage_id"] in completed for card in self.cards), len(self.cards)

    def first_incomplete_index(self, character_key: str) -> int:
        completed = self.guide_progress.manual_steps(character_key, self.progress_id)
        for index, card in enumerate(self.cards):
            if card["manual_stage_id"] not in completed:
                return index
        return len(self.cards) - 1

    def manual_sections_for_card(
        self, character_key: str, card: dict[str, Any],
    ) -> dict[str, Any]:
        key = self.page_key(card)
        # A shared Qt widget may decorate its returned sections in place.
        # Return only this card's detached sections, never an alias into the
        # canonical route used by authorization and validation.
        return copy.deepcopy(self._canonical_cards[key]["manual_sections"])

    def manual_lines_for_card(
        self, character_key: str, card: dict[str, Any],
    ) -> list[dict[str, Any]]:
        key = self.page_key(card)
        # A shallow list copy would still expose each mutable source action.
        return copy.deepcopy(
            list(self._canonical_cards[key]["manual_sections"].get("now", ()))
        )

    def manual_order_choice_blocking(
        self, character_key: str, card: dict[str, Any],
    ) -> bool:
        # Hard prerequisites are preserved as structured source evidence.
        # Never treat them as satisfied merely because the universal reader
        # lacks a corresponding validator. Every guide can inject its own
        # independently qualified evaluator; unknown/failing means blocked.
        canonical = self._canonical_cards[self.page_key(card)]
        if not canonical.get("hard_runtime_gates"):
            return False
        if not callable(self._gate_evaluator):
            return True
        try:
            # A failing or buggy per-guide evaluator must not be able to
            # change the immutable gate contract for later validation clicks.
            return self._gate_evaluator(
                character_key, copy.deepcopy(canonical),
            ) is not True
        except Exception:
            return True

    def manual_validation_block_reason(self) -> str:
        return (
            "Les prérequis de cette étape n'ont pas été validés par "
            "le contrôle propre au parcours."
        )

    def progress(self, character_key: str) -> GuideUltimeProgress:
        # Never borrow the optimized guide's Quest/Success progress indicator.
        return GuideUltimeProgress(*(0 for _ in range(10)))


__all__ = ["ImportedSourceManualRuntimeService"]
