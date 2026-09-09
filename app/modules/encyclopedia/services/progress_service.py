from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

from app.constants import DATA_DIR
from local_dofus_data.utils import now_iso, save_json_atomic
from app.modules.encyclopedia.models.progress_state import ProgressState


ACHIEVEMENT_PROGRESS_FILE = DATA_DIR / "encyclopedia" / "progress" / "achievement_progress.json"


class AchievementProgressService:
    def __init__(self, path: Path = ACHIEVEMENT_PROGRESS_FILE) -> None:
        self.path = path
        self.progress = self._load()
        self._completion_cache: dict[
            str,
            tuple[frozenset[int], dict[int, frozenset[int]]],
        ] = {}
        self._automatic_sync_cache: dict[str, tuple[object, ...]] = {}

    def _completion_state(
        self,
        character_key: str,
    ) -> tuple[frozenset[int], dict[int, frozenset[int]]]:
        key = str(character_key or "").strip()
        if not key:
            return frozenset(), {}
        cached = self._completion_cache.get(key)
        if cached is not None:
            return cached

        character = self._character(key)
        completed = {
            int(value)
            for value in character.get("completed_achievements", [])
            if self._safe_int(value) is not None
        }
        completed.update(
            int(value)
            for value in character.get("auto_completed_achievements", [])
            if self._safe_int(value) is not None
        )
        objectives: dict[int, set[int]] = {}
        for field in ("completed_objectives", "auto_completed_objectives"):
            objective_rows = character.get(field, {})
            if not isinstance(objective_rows, dict):
                continue
            for achievement_id, values in objective_rows.items():
                aid = self._safe_int(achievement_id)
                if aid is None:
                    continue
                rows = values if isinstance(values, list) else []
                objectives.setdefault(aid, set()).update(
                    int(value)
                    for value in rows
                    if self._safe_int(value) is not None
                )
        result = (
            frozenset(completed),
            {aid: frozenset(values) for aid, values in objectives.items()},
        )
        self._completion_cache[key] = result
        return result

    def state_for(self, character_key: str) -> ProgressState:
        completed, objectives = self._completion_state(character_key)
        return ProgressState(
            completed_achievements=set(completed),
            completed_objectives={aid: set(values) for aid, values in objectives.items()},
        )

    def is_achievement_completed(self, character_key: str, achievement_id: int) -> bool:
        completed, _objectives = self._completion_state(character_key)
        return int(achievement_id) in completed

    def set_achievement_completed(self, character_key: str, achievement_id: int, completed: bool) -> None:
        if not str(character_key or "").strip():
            return
        character = self._character(character_key)
        values = {
            int(value)
            for value in character.get("completed_achievements", [])
            if self._safe_int(value) is not None
        }
        if completed:
            values.add(int(achievement_id))
        else:
            values.discard(int(achievement_id))
        character["completed_achievements"] = sorted(values)
        self.save()

    def is_objective_completed(self, character_key: str, achievement_id: int, objective_id: int) -> bool:
        _completed, objectives = self._completion_state(character_key)
        return int(objective_id) in objectives.get(int(achievement_id), frozenset())

    def set_objective_completed(
        self,
        character_key: str,
        achievement_id: int,
        objective_id: int,
        completed: bool,
    ) -> None:
        if not str(character_key or "").strip():
            return
        character = self._character(character_key)
        objectives = character.setdefault("completed_objectives", {})
        if not isinstance(objectives, dict):
            objectives = {}
            character["completed_objectives"] = objectives
        key = str(int(achievement_id))
        values = {
            int(value)
            for value in objectives.get(key, [])
            if self._safe_int(value) is not None
        }
        if completed:
            values.add(int(objective_id))
        else:
            values.discard(int(objective_id))
        if values:
            objectives[key] = sorted(values)
        else:
            objectives.pop(key, None)
        self.save()

    def alignment_order_choice(self, character_key: str) -> tuple[str, str] | None:
        if not str(character_key or "").strip():
            return None
        value = self._character(character_key).get("alignment_order")
        if not isinstance(value, dict):
            return None
        side = str(value.get("side") or "").strip().casefold()
        order_name = str(value.get("order") or "").strip()
        if side not in {"bonta", "brakmar"} or not order_name:
            return None
        return side, order_name

    def set_alignment_order_choice(
        self,
        character_key: str,
        side: str,
        order_name: str,
    ) -> None:
        if not str(character_key or "").strip():
            return
        normalized_side = str(side or "").strip().casefold()
        normalized_order = str(order_name or "").strip()
        if normalized_side not in {"bonta", "brakmar"}:
            raise ValueError(f"Cité d'alignement inconnue : {side!r}")
        if not normalized_order:
            raise ValueError("Le nom de l'Ordre est obligatoire.")
        self._character(character_key)["alignment_order"] = {
            "side": normalized_side,
            "order": normalized_order,
        }
        self.save()

    def clear_alignment_order_choice(self, character_key: str) -> None:
        if not str(character_key or "").strip():
            return
        character = self._character(character_key)
        character.pop("alignment_order", None)
        self.save()

    @staticmethod
    def _manual_objectives_signature(character: dict[str, Any]) -> tuple[tuple[int, tuple[int, ...]], ...]:
        rows = character.get("completed_objectives", {})
        if not isinstance(rows, dict):
            return ()
        normalized: list[tuple[int, tuple[int, ...]]] = []
        for raw_achievement_id, values in rows.items():
            try:
                achievement_id = int(raw_achievement_id)
            except (TypeError, ValueError):
                continue
            if not isinstance(values, list):
                continue
            objective_ids: set[int] = set()
            for raw_objective_id in values:
                try:
                    objective_ids.add(int(raw_objective_id))
                except (TypeError, ValueError):
                    continue
            normalized.append((achievement_id, tuple(sorted(objective_ids))))
        return tuple(sorted(normalized))

    @staticmethod
    def _alignment_order_signature(character: dict[str, Any]) -> tuple[str, str]:
        value = character.get("alignment_order")
        if not isinstance(value, dict):
            return ("", "")
        return (
            str(value.get("side") or "").strip().casefold(),
            str(value.get("order") or "").strip(),
        )

    def sync_from_quest_progress(
        self,
        character_key: str,
        achievement_provider: Any,
        quest_progress_service: Any,
        guide_provider: Any = None,
    ) -> bool:
        """Derive quest-based achievement progress from the shared quest state.

        Manual achievement/objective checks remain separate. Automatic values are
        stored in dedicated fields so unchecking a quest can remove only the
        derived completion without erasing an explicit manual choice.
        """
        key = str(character_key or "").strip()
        if not key:
            return False
        completed_quests = frozenset(quest_progress_service.completed_quest_ids(key))
        character = self._character(key)
        manual_achievements = {
            int(value)
            for value in character.get("completed_achievements", [])
            if self._safe_int(value) is not None
        }
        sync_signature: tuple[object, ...] = (
            id(achievement_provider),
            id(guide_provider),
            completed_quests,
            tuple(sorted(manual_achievements)),
            self._manual_objectives_signature(character),
            self._alignment_order_signature(character),
        )
        if self._automatic_sync_cache.get(key) == sync_signature:
            return False

        achievements = tuple(achievement_provider.load_retained())
        by_id = {int(achievement.id): achievement for achievement in achievements}
        completed_quest_count = len(completed_quests)
        alignment_main = self._alignment_main_quest_ids(guide_provider)
        alignment_counts = {
            side: sum(1 for quest_id in quest_ids if int(quest_id) in completed_quests)
            for side, quest_ids in alignment_main.items()
        }
        alignment_count = max(alignment_counts.values(), default=0)

        try:
            from app.modules.encyclopedia.services.guide_path_profiles import ORDER_QUEST_IDS
        except Exception:
            ORDER_QUEST_IDS = {}

        manual_objectives: dict[int, set[int]] = {}
        raw_manual_objectives = character.get("completed_objectives", {})
        if isinstance(raw_manual_objectives, dict):
            for raw_aid, values in raw_manual_objectives.items():
                aid = self._safe_int(raw_aid)
                if aid is None or not isinstance(values, list):
                    continue
                manual_objectives[aid] = {
                    int(value)
                    for value in values
                    if self._safe_int(value) is not None
                }

        auto_objectives: dict[int, set[int]] = {}
        memo: dict[int, bool] = {}

        def compare(value: int, criterion: str, code: str) -> bool | None:
            match = re.search(
                rf"\b{re.escape(code)}\s*(>=|<=|=|>|<)\s*(\d+)",
                str(criterion or ""),
                flags=re.IGNORECASE,
            )
            if match is None:
                return None
            operator, raw_target = match.groups()
            target = int(raw_target)
            if operator == ">":
                return value > target
            if operator == ">=":
                return value >= target
            if operator == "<":
                return value < target
            if operator == "<=":
                return value <= target
            return value == target

        def ref_group_done(refs: Iterable[Any], entity_type: str, criterion: str) -> bool | None:
            matching = [ref for ref in refs if str(getattr(ref, "entity_type", "")) == entity_type]
            if not matching:
                return None
            values: list[bool] = []
            for ref in matching:
                entity_id = int(getattr(ref, "entity_id"))
                if entity_type == "quest":
                    values.append(entity_id in completed_quests)
                else:
                    values.append(resolve_achievement(entity_id, frozenset()))
            return any(values) if "|" in str(criterion or "") else all(values)

        def objective_done(achievement: Any, objective: Any, visiting: frozenset[int]) -> tuple[bool | None, bool]:
            aid = int(achievement.id)
            oid = int(objective.id)
            objective_type = str(getattr(objective, "objective_type", "") or "").strip().casefold()
            category_name = str(getattr(achievement, "category_name", "") or "").strip().casefold()
            if objective_type in {"critère pl", "critère ea"}:
                return None, True
            if objective_type == "critère bi" and category_name == "quêtes":
                return None, True
            if oid in manual_objectives.get(aid, set()):
                return True, False

            refs = tuple(getattr(objective, "entity_refs", ()) or ())
            criterion = str(getattr(objective, "criterion", "") or "")
            quest_value = ref_group_done(refs, "quest", criterion)
            if quest_value is not None:
                return quest_value, False
            achievement_refs = [ref for ref in refs if str(getattr(ref, "entity_type", "")) == "achievement"]
            if achievement_refs:
                values = [resolve_achievement(int(getattr(ref, "entity_id")), visiting) for ref in achievement_refs]
                return (any(values) if "|" in criterion else all(values)), False

            if objective_type == "critère qq":
                value = compare(completed_quest_count, criterion, "QQ")
                return (bool(value), False) if value is not None else (False, False)
            if objective_type == "critère pa":
                value = compare(alignment_count, criterion, "Pa")
                return (bool(value), False) if value is not None else (False, False)
            if objective_type == "critère pr":
                rank_match = re.search(r"\bRang\s+(\d+)\b", str(getattr(objective, "text", "") or ""), re.IGNORECASE)
                choice = self.alignment_order_choice(key)
                if rank_match is None or choice is None:
                    return False, False
                rank = int(rank_match.group(1))
                side, order_name = choice
                quest_ids = tuple(ORDER_QUEST_IDS.get(side, {}).get(order_name, ()))
                if rank < 1 or rank > len(quest_ids):
                    return False, False
                return int(quest_ids[rank - 1]) in completed_quests, False

            # Unsupported Lot 8/9 objective types must not auto-complete a success.
            return False, False

        def resolve_achievement(achievement_id: int, visiting: frozenset[int]) -> bool:
            aid = int(achievement_id)
            if aid in manual_achievements:
                return True
            if aid in memo:
                return memo[aid]
            if aid in visiting:
                return False
            achievement = by_id.get(aid)
            if achievement is None:
                return False
            next_visiting = visiting | {aid}
            evaluated: list[bool] = []
            for objective in tuple(getattr(achievement, "objectives", ()) or ()):
                value, ignored = objective_done(achievement, objective, next_visiting)
                if ignored:
                    continue
                done = bool(value)
                evaluated.append(done)
                if done and int(objective.id) not in manual_objectives.get(aid, set()):
                    auto_objectives.setdefault(aid, set()).add(int(objective.id))
            result = bool(evaluated) and all(evaluated)
            memo[aid] = result
            return result

        auto_achievements = {
            int(achievement.id)
            for achievement in achievements
            if int(achievement.id) not in manual_achievements
            and resolve_achievement(int(achievement.id), frozenset())
        }
        serialized_objectives = {
            str(aid): sorted(values)
            for aid, values in auto_objectives.items()
            if values
        }
        previous_achievements = sorted(
            int(value)
            for value in character.get("auto_completed_achievements", [])
            if self._safe_int(value) is not None
        )
        previous_objectives = character.get("auto_completed_objectives", {})
        next_achievements = sorted(auto_achievements)
        changed = previous_achievements != next_achievements or previous_objectives != serialized_objectives
        character["auto_completed_achievements"] = next_achievements
        character["auto_completed_objectives"] = serialized_objectives
        if changed:
            self.save()
        self._automatic_sync_cache[key] = sync_signature
        return changed

    @staticmethod
    def _alignment_main_quest_ids(guide_provider: Any) -> dict[str, tuple[int, ...]]:
        if guide_provider is None:
            return {}
        try:
            from app.modules.encyclopedia.achievement_catalog_policy import ALIGNMENT_GUIDE_IDS
        except Exception:
            return {}
        result: dict[str, tuple[int, ...]] = {}
        for side, guide_id in ALIGNMENT_GUIDE_IDS.items():
            try:
                guide = guide_provider.get_by_id(guide_id)
            except Exception:
                guide = None
            if guide is None:
                continue
            quest_ids = []
            for step in tuple(getattr(guide, "required_steps", ()) or ()):
                if str(getattr(step, "step_type", "")) != "quest":
                    continue
                entity_id = getattr(step, "entity_id", None)
                try:
                    quest_id = int(entity_id)
                except (TypeError, ValueError):
                    continue
                if quest_id not in quest_ids:
                    quest_ids.append(quest_id)
            result[str(side)] = tuple(quest_ids)
        return result

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        save_json_atomic(self.path, self.progress)
        self._completion_cache.clear()
        self._automatic_sync_cache.clear()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "characters": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._backup_corrupt_file()
            return {"version": 1, "characters": {}}
        if not isinstance(payload, dict):
            return {"version": 1, "characters": {}}
        payload.setdefault("version", 1)
        if not isinstance(payload.get("characters"), dict):
            payload["characters"] = {}
        return payload

    def _character(self, character_key: str) -> dict[str, Any]:
        characters = self.progress.setdefault("characters", {})
        if not isinstance(characters, dict):
            characters = {}
            self.progress["characters"] = characters
        key = str(character_key or "").strip()
        if not key:
            raise ValueError("character_key is required for progress mutation")
        character = characters.setdefault(key, {})
        if not isinstance(character, dict):
            character = {}
            characters[key] = character
        character.setdefault("completed_achievements", [])
        character.setdefault("completed_objectives", {})
        character.setdefault("auto_completed_achievements", [])
        character.setdefault("auto_completed_objectives", {})
        return character

    def _backup_corrupt_file(self) -> None:
        if not self.path.exists():
            return
        timestamp = now_iso().replace(":", "-")
        backup = self.path.with_suffix(self.path.suffix + f".corrupt.{timestamp}.bak")
        backup.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(self.path, backup)
        except OSError:
            pass

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
