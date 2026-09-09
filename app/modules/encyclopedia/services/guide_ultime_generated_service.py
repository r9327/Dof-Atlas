from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import AchievementProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService


ROOT = Path(__file__).resolve().parents[4]
GUIDE_ULTIME_FINAL_FILE = ROOT / "artifacts" / "guide_ultime_final.json"
GUIDE_ULTIME_ROUTE_FILE = ROOT / "artifacts" / "guide_ultime_gps_route.json"
GUIDE_ULTIME_FINAL_AUDIT_FILE = ROOT / "artifacts" / "guide_ultime_final_audit.json"
GUIDE_ULTIME_ROUTE_AUDIT_FILE = ROOT / "artifacts" / "guide_ultime_gps_route_audit.json"
GUIDE_ULTIME_PROGRESS_ID = "guide_ultime_v5"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-zA-Z0-9]+", " ", text.casefold()).strip()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON objet attendu: {path}")
    return payload


@dataclass(frozen=True, slots=True)
class GuideUltimeProgress:
    common_completed: int
    common_total: int
    qq_completed: int
    qq_required: int
    full_success_completed: int
    full_success_total: int
    class_completed: int
    class_total: int
    order_completed: int
    order_total: int

    @property
    def common_percent(self) -> int | None:
        if self.common_total <= 0:
            return None
        return min(100, round(self.common_completed * 100 / self.common_total))


@dataclass(frozen=True, slots=True)
class GuideUltimeCardState:
    complete: bool
    historical: bool
    automatic_done: int
    automatic_total: int
    manual_done: int
    manual_total: int


class GuideUltimeGeneratedService:
    """Read-only consumer of the generated V5 route plus shared player progress.

    Quest and achievement completion remain owned by the existing services. The
    Guide Ultime stores only one manual override per route sheet. Internal route
    instructions/resources are never independent checkboxes.
    """

    def __init__(
        self,
        quest_progress: QuestProgressService,
        achievement_progress: AchievementProgressService,
        guide_progress: GuideProgressService,
        *,
        route_path: Path = GUIDE_ULTIME_ROUTE_FILE,
        final_path: Path = GUIDE_ULTIME_FINAL_FILE,
        autoload: bool = True,
    ) -> None:
        self.quest_progress = quest_progress
        self.achievement_progress = achievement_progress
        self.guide_progress = guide_progress
        self.route_path = Path(route_path)
        self.final_path = Path(final_path)
        self.route: dict[str, Any] = {}
        self.final: dict[str, Any] = {}
        self.cards: list[dict[str, Any]] = []
        self._common_quest_ids: tuple[int, ...] = ()
        self._full_success_ids: tuple[int, ...] = ()
        if autoload:
            self.load()

    @property
    def available(self) -> bool:
        return bool(self.route and self.cards)

    @property
    def common_quest_ids(self) -> tuple[int, ...]:
        return self._common_quest_ids

    @property
    def full_success_ids(self) -> tuple[int, ...]:
        return self._full_success_ids

    def load(self) -> None:
        self.route = _read_json(self.route_path) if self.route_path.exists() else {}
        self.final = _read_json(self.final_path) if self.final_path.exists() else {}
        if self.route and int(self.route.get("schema_version") or 0) != 5:
            raise ValueError("guide_ultime_gps_route.json n'est pas un payload V5")
        self.cards = [row for row in self.route.get("steps", []) if isinstance(row, dict)]
        self._common_quest_ids = self._collect_common_quest_ids()
        self._full_success_ids = self._collect_full_success_ids()

    def reload_progress(self) -> None:
        self.quest_progress.reload()
        self.achievement_progress.reload()
        self.guide_progress.reload()

    def common_total(self) -> int:
        route_meta = self.route.get("universal_route") if isinstance(self.route.get("universal_route"), dict) else {}
        declared = _safe_int(route_meta.get("common_route_quest_count"))
        return declared if declared is not None and declared > 0 else len(self._common_quest_ids)

    def qq_required(self) -> int:
        route_meta = self.route.get("universal_route") if isinstance(self.route.get("universal_route"), dict) else {}
        value = _safe_int(route_meta.get("qq_required_count"))
        return max(0, value or 0)

    def progress(self, character_key: str) -> GuideUltimeProgress:
        completed_quests = self.quest_progress.completed_quest_ids(character_key)
        common_done = len(completed_quests.intersection(self._common_quest_ids))
        completed_successes = {
            aid for aid in self._full_success_ids
            if self.achievement_progress.is_achievement_completed(character_key, aid)
        }
        class_ids = self.class_quest_ids()
        class_done = 1 if any(qid in completed_quests for qid in class_ids) else 0
        order_ids = self.selected_order_quest_ids(character_key)
        order_done = sum(1 for qid in order_ids if qid in completed_quests)
        return GuideUltimeProgress(
            common_completed=common_done,
            common_total=self.common_total(),
            qq_completed=len(completed_quests),
            qq_required=self.qq_required(),
            full_success_completed=len(completed_successes),
            full_success_total=len(self._full_success_ids),
            class_completed=class_done,
            class_total=1 if class_ids else 0,
            order_completed=order_done,
            order_total=len(order_ids) if order_ids else 5,
        )

    def card_key(self, card: dict[str, Any], fallback_index: int = 0) -> str:
        raw = _safe_int(card.get("index"))
        return f"gps:{raw if raw is not None else fallback_index}"

    def page_key(self, card: dict[str, Any], fallback_index: int = 0) -> str:
        return f"page:{self.card_key(card, fallback_index)}"

    def page_checked(self, character_key: str, card: dict[str, Any], fallback_index: int = 0) -> bool:
        return self.manual_checked(character_key, self.page_key(card, fallback_index))

    def set_page_checked(
        self,
        character_key: str,
        card: dict[str, Any],
        fallback_index: int,
        checked: bool,
    ) -> None:
        self.set_manual_checked(character_key, self.page_key(card, fallback_index), checked)

    def card_quest_ids(self, card: dict[str, Any]) -> tuple[int, ...]:
        ids: list[int] = []
        for section in ("a_prendre", "a_faire_ici"):
            for row in card.get(section, []) or []:
                if not isinstance(row, dict):
                    continue
                qid = _safe_int(row.get("quest_id"))
                if qid is not None and qid not in ids:
                    ids.append(qid)
        progress = card.get("progresse_aussi") if isinstance(card.get("progresse_aussi"), dict) else {}
        for raw in progress.get("quest_ids", []) or []:
            qid = _safe_int(raw)
            if qid is not None and qid not in ids:
                ids.append(qid)
        return tuple(ids)

    def card_success_ids(self, card: dict[str, Any]) -> tuple[int, ...]:
        ids: list[int] = []
        for section in ("succes_monstres_a_faire", "succes_donjon_a_faire"):
            for row in card.get(section, []) or []:
                if not isinstance(row, dict):
                    continue
                aid = _safe_int(row.get("achievement_id"))
                if aid is not None and aid not in ids:
                    ids.append(aid)
        return tuple(ids)

    def action_completed(self, character_key: str, row: dict[str, Any]) -> bool:
        qid = _safe_int(row.get("quest_id"))
        if qid is None:
            return False
        if self.quest_progress.is_quest_completed(character_key, qid):
            return True
        oid = _safe_int(row.get("objective_id"))
        return bool(oid is not None and self.quest_progress.is_objective_completed(character_key, qid, oid))

    def card_automatic_values(
        self,
        character_key: str,
        card: dict[str, Any],
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> tuple[bool, ...]:
        quest_ids = self.card_quest_ids(card)
        success_ids = self.card_success_ids(card)
        automatic: list[bool] = []
        for section in ("a_prendre", "a_faire_ici"):
            automatic.extend(
                self.action_completed(character_key, row)
                for row in card.get(section, []) or []
                if isinstance(row, dict)
            )
        automatic.extend(
            self.achievement_progress.is_achievement_completed(character_key, aid)
            for aid in success_ids
        )
        if not automatic and quest_ids:
            snapshot = completed_quests
            if snapshot is None:
                snapshot = self.quest_progress.completed_quest_ids(character_key)
            automatic.extend(qid in snapshot for qid in quest_ids)
        return tuple(automatic)

    def card_auto_complete(
        self,
        character_key: str,
        card: dict[str, Any],
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> bool:
        values = self.card_automatic_values(character_key, card, completed_quests)
        return bool(values) and all(values)

    def card_state(
        self,
        character_key: str,
        card: dict[str, Any],
        fallback_index: int = 0,
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> GuideUltimeCardState:
        quest_ids = self.card_quest_ids(card)
        snapshot = completed_quests
        if snapshot is None:
            snapshot = self.quest_progress.completed_quest_ids(character_key)
        historical = bool(quest_ids) and all(qid in snapshot for qid in quest_ids)
        automatic = self.card_automatic_values(character_key, card, snapshot)
        automatic_ok = bool(automatic) and all(automatic)
        page_done = self.page_checked(character_key, card, fallback_index)

        # One route sheet = one validation unit. Detailed instructions/resources
        # never create extra manual checkboxes. Automatic quest/success progress
        # validates the sheet; otherwise the player may validate the sheet once.
        return GuideUltimeCardState(
            complete=bool(automatic_ok or page_done),
            historical=historical,
            automatic_done=sum(1 for value in automatic if value),
            automatic_total=len(automatic),
            manual_done=1 if page_done else 0,
            manual_total=1,
        )

    def first_incomplete_index(self, character_key: str) -> int:
        completed_quests = self.quest_progress.completed_quest_ids(character_key)
        for index, card in enumerate(self.cards):
            if not self.card_state(
                character_key,
                card,
                index,
                completed_quests=completed_quests,
            ).complete:
                return index
        return max(0, len(self.cards) - 1)

    def manual_checked(self, character_key: str, key: str) -> bool:
        return self.guide_progress.is_manual_step_completed(
            character_key, GUIDE_ULTIME_PROGRESS_ID, key
        )

    def set_manual_checked(self, character_key: str, key: str, checked: bool) -> None:
        self.guide_progress.set_manual_step_completed(
            character_key, GUIDE_ULTIME_PROGRESS_ID, key, bool(checked)
        )

    def resource_key(self, card: dict[str, Any], row: dict[str, Any], index: int, fallback_index: int = 0) -> str:
        card_key = self.card_key(card, fallback_index)
        item_id = _safe_int(row.get("item_id"))
        name = _norm(row.get("name")) or "item"
        quantity = _safe_int(row.get("quantity")) or 1
        return f"resource:{card_key}:{item_id if item_id is not None else name}:{quantity}:{index}"

    def manual_action_key(self, card: dict[str, Any], section: str, index: int, fallback_index: int = 0) -> str:
        return f"manual:{self.card_key(card, fallback_index)}:{section}:{index}"

    def manual_keys_for_card(self, card: dict[str, Any], fallback_index: int = 0) -> tuple[str, ...]:
        # Compatibility only for old persisted data. The current UI no longer
        # renders these keys independently; page_key() is the only manual control.
        result: list[str] = []
        resources = list(card.get("a_preparer", []) or []) + list(card.get("manual_preparation", []) or [])
        for index, row in enumerate(resources):
            if isinstance(row, dict):
                result.append(self.resource_key(card, row, index, fallback_index))
        for section in ("hard_runtime_gates", "profession_gates", "avant_de_partir"):
            for index, _row in enumerate(card.get(section, []) or []):
                result.append(self.manual_action_key(card, section, index, fallback_index))
        return tuple(result)

    def class_options(self) -> tuple[dict[str, Any], ...]:
        branches = self.route.get("conditional_branches") if isinstance(self.route.get("conditional_branches"), dict) else {}
        card = branches.get("class_card") if isinstance(branches.get("class_card"), dict) else {}
        return tuple(row for row in card.get("options", []) or [] if isinstance(row, dict))

    def class_quest_ids(self) -> tuple[int, ...]:
        return tuple(
            qid for qid in (_safe_int(row.get("quest_id")) for row in self.class_options())
            if qid is not None
        )

    def inferred_class_option(self, character_key: str) -> dict[str, Any] | None:
        completed = self.quest_progress.completed_quest_ids(character_key)
        matches = [row for row in self.class_options() if _safe_int(row.get("quest_id")) in completed]
        return matches[0] if len(matches) == 1 else None

    def bonta_order_names(self) -> tuple[str, ...]:
        names: list[str] = []
        branches = self.route.get("conditional_branches") if isinstance(self.route.get("conditional_branches"), dict) else {}
        for card in branches.get("order_cards", []) or []:
            if not isinstance(card, dict):
                continue
            for row in card.get("options", []) or []:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("order") or "").strip()
                if name and _norm(name) not in {_norm(value) for value in names}:
                    names.append(name)
        return tuple(names[:3])

    def selected_order_name(self, character_key: str) -> str:
        choice = self.achievement_progress.alignment_order_choice(character_key)
        if choice is None or _norm(choice[0]) != "bonta":
            return ""
        return choice[1]

    def set_bonta_order(self, character_key: str, order_name: str) -> None:
        allowed = self.bonta_order_names()
        matched = next((value for value in allowed if _norm(value) == _norm(order_name)), None)
        if matched is None:
            raise ValueError(f"Ordre Bonta inconnu dans la route V5: {order_name!r}")
        self.achievement_progress.set_alignment_order_choice(character_key, "bonta", matched)

    def selected_order_quest_ids(self, character_key: str) -> tuple[int, ...]:
        selected = self.selected_order_name(character_key)
        if not selected:
            return ()
        branches = self.route.get("conditional_branches") if isinstance(self.route.get("conditional_branches"), dict) else {}
        ids: list[int] = []
        for card in branches.get("order_cards", []) or []:
            if not isinstance(card, dict):
                continue
            option = next(
                (row for row in card.get("options", []) or [] if isinstance(row, dict) and _norm(row.get("order")) == _norm(selected)),
                None,
            )
            qid = _safe_int(option.get("quest_id")) if option else None
            if qid is not None:
                ids.append(qid)
        return tuple(ids)

    def _collect_common_quest_ids(self) -> tuple[int, ...]:
        result: list[int] = []
        for card in self.cards:
            for qid in self.card_quest_ids(card):
                if qid not in result:
                    result.append(qid)
        return tuple(result)

    def _collect_full_success_ids(self) -> tuple[int, ...]:
        full = self.route.get("full_success_cards") if isinstance(self.route.get("full_success_cards"), dict) else {}
        result: list[int] = []
        for row in full.get("monster_success_cards", []) or []:
            if isinstance(row, dict):
                aid = _safe_int(row.get("achievement_id"))
                if aid is not None and aid not in result:
                    result.append(aid)
        for row in full.get("dungeon_success_cards", []) or []:
            if not isinstance(row, dict):
                continue
            for achievement in row.get("achievements", []) or []:
                if not isinstance(achievement, dict):
                    continue
                aid = _safe_int(achievement.get("achievement_id"))
                if aid is not None and aid not in result:
                    result.append(aid)
        for row in full.get("dungeon_meta_success_cards", []) or []:
            if isinstance(row, dict):
                aid = _safe_int(row.get("achievement_id"))
                if aid is not None and aid not in result:
                    result.append(aid)
        return tuple(result)
