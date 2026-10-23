"""Progress-safe navigation for Ganymède source-trusted manual guide routes.

This is the state contract behind the "Actuelle" control. It intentionally
does not equate a checked sheet with a completed Doduda quest or achievement.
UI scroll/expanded-menu state is independent from the persisted character
progress, and historical legacy sheet IDs are never implicitly migrated.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.core.character_identity import is_character_key, require_character_key
from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService


def known_guide_participants(
    selected_keys: Iterable[str], available_characters: Iterable[object],
) -> tuple[str, ...]:
    """Never enable route progress for an absent/unverified identity.

    Offline characters are still known when they remain in the verified
    binding registry. Unknown/stale IDs are not silently treated as players.
    """
    available = {
        key for row in available_characters
        if is_character_key(key := getattr(row, "key", ""))
    }
    return tuple(
        key for key in selected_keys if is_character_key(key) and key in available
    )


@dataclass(frozen=True, slots=True)
class ContinuousGuidePosition:
    guide_id: str
    viewed_step_id: str | None
    actual_step_id: str | None
    selected_character_keys: tuple[str, ...]
    completed_by_character: dict[str, int]
    total_steps: int
    status: str


class ContinuousGuideNavigation:
    """Calculate actual position from the *current* selected characters.

    Viewing a historical/future sheet cannot move "Actuelle". The persistent
    store owns manual completion flags and remains isolated per character.
    """

    def __init__(
        self,
        route: Mapping[str, object],
        progress: GuideProgressService,
        selected_character_keys: Iterable[str] = (),
    ) -> None:
        if (route.get("category") != "dofus"
                or route.get("route_origin") != "GANYMEDE_CONTINUOUS_STEP_ORDER"
                or route.get("replacement_status") != "TRUSTED_SOURCE_STEPS"
                or route.get("auto_completion_allowed") is not False
                or route.get("canonical_objectives_certified") is not False):
            raise ValueError("not an explicitly manual Ganymède Dofus route")
        source_id = route.get("source_guide_id")
        guide_id = route.get("id")
        sections = route.get("sections")
        if (type(source_id) is not int or source_id <= 0
                or not isinstance(guide_id, str) or not guide_id
                or not isinstance(sections, list) or len(sections) != 1
                or not isinstance(sections[0], dict)):
            raise ValueError("source route identity or sections invalid")
        steps = sections[0].get("steps")
        count = route.get("expected_source_step_count")
        if (not isinstance(steps, list) or not steps or type(count) is not int
                or count != len(steps)):
            raise ValueError("source step count mismatch")
        ids: list[str] = []
        for number, row in enumerate(steps, 1):
            expected = f"ganymede_{source_id}_step_{number:04d}"
            if (not isinstance(row, dict)
                    or row.get("id") != expected
                    or row.get("source_guide_id") != source_id
                    or row.get("source_step_number") != number
                    or row.get("manual_completion_allowed") is not True
                    or row.get("auto_completion_allowed") is not False
                    or row.get("verified_actions") != []):
                raise ValueError(f"unsafe manual source step {number}")
            ids.append(expected)
        self.guide_id = guide_id
        self.step_ids = tuple(ids)
        self._step_set = frozenset(ids)
        self.progress = progress
        self.viewed_step_id: str | None = None
        self.selected_character_keys: tuple[str, ...] = ()
        self.select_characters(selected_character_keys)

    def select_characters(self, character_keys: Iterable[str]) -> None:
        keys = tuple(require_character_key(key) for key in character_keys)
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate selected character")
        self.selected_character_keys = keys

    def _completion(self) -> dict[str, set[str]]:
        return {
            key: self.progress.manual_steps(key, self.guide_id) & self._step_set
            for key in self.selected_character_keys
        }

    def completed_count(self, character_key: str) -> int:
        """Manual step count for any verified stable key, selected or not.

        The portrait ring stays truthful for an offline/deselected character;
        it never changes or infers quest/achievement completion.
        """
        key = require_character_key(character_key)
        return len(self.progress.manual_steps(key, self.guide_id) & self._step_set)

    def position(self) -> ContinuousGuidePosition:
        completed = self._completion()
        if not completed:
            actual = None
            status = "NO_SELECTED_CHARACTER"
        else:
            actual = next(
                (step_id for step_id in self.step_ids
                 if any(step_id not in done for done in completed.values())),
                None,
            )
            status = "ALL_COMPLETE" if actual is None else "IN_PROGRESS"
        return ContinuousGuidePosition(
            guide_id=self.guide_id,
            viewed_step_id=self.viewed_step_id,
            actual_step_id=actual,
            selected_character_keys=self.selected_character_keys,
            completed_by_character={
                key: len(done) for key, done in completed.items()
            },
            total_steps=len(self.step_ids),
            status=status,
        )

    def show_step(self, step_id: str) -> str:
        if step_id not in self._step_set:
            raise ValueError("step not in this guide")
        self.viewed_step_id = step_id
        return step_id

    def show_actual(self) -> str | None:
        actual = self.position().actual_step_id
        if actual is not None:
            self.viewed_step_id = actual
        return actual

    def next_step(self) -> str | None:
        if self.viewed_step_id is None:
            # Browsing source sheets never certifies a character's position.
            # With no selected character there is no "Actuelle", but the
            # user must still be able to inspect the full manual guide.
            return self.show_actual() or self.show_step(self.step_ids[0])
        index = self.step_ids.index(self.viewed_step_id)
        if index + 1 >= len(self.step_ids):
            return None
        return self.show_step(self.step_ids[index + 1])

    def previous_step(self) -> str | None:
        if self.viewed_step_id is None:
            return self.show_actual()
        index = self.step_ids.index(self.viewed_step_id)
        if index == 0:
            return None
        return self.show_step(self.step_ids[index - 1])

    def mark_manual_step(self, step_id: str, completed: bool) -> bool:
        """Explicit user action only. Never write quest/achievement progress."""
        if step_id not in self._step_set:
            raise ValueError("step not in this guide")
        if not self.selected_character_keys:
            return False
        return self.progress.set_manual_steps_for_characters(
            self.selected_character_keys, self.guide_id, step_id, bool(completed),
        )


__all__ = [
    "ContinuousGuideNavigation", "ContinuousGuidePosition",
    "known_guide_participants",
]
