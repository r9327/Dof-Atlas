from __future__ import annotations

import copy
import re
from pathlib import Path
from threading import RLock
from typing import Any

from app.modules.encyclopedia.services.guide_ultime_manual_route import _manual_tree_signature
from app.quest_catalog import doduda_rows, normalize_text, read_json_file, text_for


AUTO_VALIDATION_SCHEMA_VERSION = 1
_MANUAL_DIR = Path(__file__).resolve().parents[4] / "data" / "routes" / "guide_ultime_manual"
_CONTRACT_CACHE_LOCK = RLock()
_CONTRACT_CACHE: dict[tuple[object, ...], dict[str, Any]] = {}
_MAX_CONTRACT_CACHE_ENTRIES = 8
_FARM_HINT_RE = re.compile(
    r"\b(?:farm|farmer|tuer|tuez|vaincre|combattre|chasser|capturer|éliminer|eliminer|drop|droper|dropez)\b",
    re.IGNORECASE,
)
_RESERVE_HINT_RE = re.compile(
    r"\b(?:garder|gardez|conserver|conservez|réserver|reserver|ne\s+pas\s+vendre)\b",
    re.IGNORECASE,
)
_BANK_HINT_RE = re.compile(r"\bbanque\b", re.IGNORECASE)
_CAPTURE_HINT_RE = re.compile(
    r"(?:pierre\s+(?:d['’]\s*)?âme|pierre\s+de\s+capture|capture(?:r|z)?\s+le\s+boss)",
    re.IGNORECASE,
)
_ITEM_HINT_RE = re.compile(
    r"\b(?:apporter|apportez|amener|amenez|donner|donnez|acheter|achetez|préparer|preparez|préparez)\b",
    re.IGNORECASE,
)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stable_card_key(card: dict[str, Any]) -> str:
    chapter = str(card.get("manual_chapter_id") or "route").strip() or "route"
    stage = str(card.get("manual_stage_id") or card.get("index") or "unknown").strip() or "unknown"
    return f"manual:{chapter}:{stage}"


def _rows(value: Any) -> list[Any]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _waypoints(stage: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in stage.get("waypoints", []) or [] if isinstance(row, dict)]


def _target_name(value: Any, *, fallback: str = "") -> str:
    if isinstance(value, dict):
        for key in ("name", "monster", "item", "requirement", "target", "dungeon", "boss"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return fallback
    return str(value or fallback).strip()


def _dungeon_name(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("name", "dungeon", "boss"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def _dungeon_targets(stage: dict[str, Any]) -> list[dict[str, Any]]:
    raw_targets = _rows(stage.get("dungeon")) + _rows(stage.get("dungeons"))
    for waypoint in _waypoints(stage):
        raw_targets.extend(_rows(waypoint.get("dungeon")))
        raw_targets.extend(_rows(waypoint.get("dungeons")))

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_targets:
        name = _dungeon_name(raw)
        if not name:
            continue
        key = normalize_text(name)
        if not key or key in seen:
            continue
        seen.add(key)
        payload = copy.deepcopy(raw) if isinstance(raw, dict) else {"name": name}
        payload.setdefault("name", name)
        payload["target_key"] = f"dungeon:{key}"
        result.append(payload)
    return result


def _monster_targets(stage: dict[str, Any]) -> list[dict[str, Any]]:
    raw_targets = _rows(stage.get("monsters"))
    for waypoint in _waypoints(stage):
        raw_targets.extend(_rows(waypoint.get("monsters")))

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_targets:
        name = _target_name(raw)
        if not name:
            continue
        key = normalize_text(name)
        if not key or key in seen:
            continue
        seen.add(key)
        payload = copy.deepcopy(raw) if isinstance(raw, dict) else {"name": name}
        payload.setdefault("name", name)
        quantity = _safe_int(payload.get("quantity") or payload.get("count") or payload.get("target_count"))
        if quantity is not None:
            payload["quantity"] = quantity
        payload["target_key"] = f"monster:{key}"
        result.append(payload)
    return result


def _success_names(card: dict[str, Any], stage: dict[str, Any]) -> list[str]:
    values = [str(value).strip() for value in card.get("manual_success_names", []) or [] if str(value).strip()]
    for waypoint in _waypoints(stage):
        values.extend(str(value).strip() for value in waypoint.get("successes", []) or [] if str(value).strip())

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = normalize_text(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _item_targets(
    card: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return exact item requirements without collapsing separate future uses.

    ``reserved`` means the player must keep the item and not sell/use it yet.
    ``bank`` is deliberately stricter: it is only emitted for an explicit bank
    instruction/source field. This distinction is required by the future network
    observer because keeping an item in inventory is not the same state as moving
    it to the character bank.
    """

    items: list[dict[str, Any]] = []
    reserved: list[dict[str, Any]] = []
    bank: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    occurrence_by_identity: dict[tuple[str, str], int] = {}

    for raw in card.get("a_preparer", []) or []:
        if not isinstance(raw, dict):
            continue
        name = _target_name(raw)
        if not name:
            continue
        key = normalize_text(name)
        quantity = _safe_int(raw.get("quantity") or raw.get("minimum_quantity"))
        purpose = normalize_text(raw.get("for") or raw.get("purpose") or raw.get("usage") or "")
        identity = (key, purpose)
        occurrence = occurrence_by_identity.get(identity, 0) + 1
        occurrence_by_identity[identity] = occurrence

        suffix = purpose or "general"
        target_id = f"item:{key}:{suffix}:{occurrence}"
        semantic = normalize_text(" ".join(str(value or "") for value in raw.values()))
        source_field = normalize_text(raw.get("_source_field") or "")
        storage = normalize_text(raw.get("storage") or raw.get("location") or "")

        payload = copy.deepcopy(raw)
        payload.setdefault("name", name)
        payload["target_key"] = target_id
        if purpose:
            payload["purpose_key"] = purpose
        if quantity is not None:
            payload["quantity"] = quantity
        items.append(payload)

        explicit_bank = (
            storage == "bank"
            or source_field in {"keep_in_bank", "bank_items"}
            or "banque" in semantic
        )
        keep_reserved = explicit_bank or any(
            token in semantic
            for token in ("garder", "conserver", "ne_pas_vendre", "reserve", "reserver")
        )
        if keep_reserved:
            reserved.append(copy.deepcopy(payload))
        if explicit_bank:
            bank.append(copy.deepcopy(payload))

        name_norm = normalize_text(name)
        if "pierre" in name_norm and ("ame" in name_norm or "capture" in name_norm):
            captures.append(copy.deepcopy(payload))
    return items, reserved, bank, captures


def _achievement_index_from_loaded_provider(achievement_provider: Any) -> dict[str, tuple[int, str]]:
    try:
        achievements = achievement_provider.load_all()
    except Exception:
        return {}
    result: dict[str, tuple[int, str]] = {}
    for achievement in achievements:
        aid = _safe_int(getattr(achievement, "id", None))
        name = str(getattr(achievement, "name", "") or "").strip()
        key = normalize_text(name)
        if aid is not None and key and key not in result:
            result[key] = (aid, name)
    return result


def _achievement_index(achievement_provider: Any) -> dict[str, tuple[int, str]]:
    if achievement_provider is None:
        return {}

    # If the Successes module already paid the full provider load, reuse it.
    # Otherwise the Guide only needs names and ids: loading objectives, rewards,
    # monsters, dungeons, items, spells, titles, emotes, ornaments and alterations
    # here creates a large first-open freeze for no benefit.
    if bool(getattr(achievement_provider, "_loaded", False)):
        return _achievement_index_from_loaded_provider(achievement_provider)

    data_dir = getattr(achievement_provider, "data_dir", None)
    if data_dir is not None:
        try:
            base = Path(data_dir)
            language = read_json_file(base / "languages" / "fr.json", {"entries": {}})
            entries = language.get("entries", {}) if isinstance(language, dict) else {}
            if not isinstance(entries, dict):
                entries = {}
            rows = doduda_rows(base / "achievements.json")
            result: dict[str, tuple[int, str]] = {}
            for achievement_id, row in rows.items():
                name = text_for(entries, row.get("nameId"), f"Succes {achievement_id}").strip()
                key = normalize_text(name)
                if key and key not in result:
                    result[key] = (int(achievement_id), name)
            if result:
                return result
        except Exception:
            # Custom providers or partial test data retain the historical path.
            pass

    return _achievement_index_from_loaded_provider(achievement_provider)


def _quantified_hints(card: dict[str, Any], pattern: re.Pattern[str]) -> list[str]:
    return [
        str(row.get("text") or "").strip()
        for row in card.get("manual_lines", []) or []
        if isinstance(row, dict)
        and pattern.search(str(row.get("text") or ""))
        and any(char.isdigit() for char in str(row.get("text") or ""))
    ]


def _aggregate_quantity_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate future stock by item name without erasing individual usages."""
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        name = str(target.get("name") or "").strip()
        key = normalize_text(name)
        if not key:
            continue
        if key not in grouped:
            grouped[key] = {
                "item_key": key,
                "name": name,
                "required_quantity": 0,
                "quantified_target_count": 0,
                "unquantified_target_count": 0,
                "target_keys": [],
                "purpose_keys": [],
            }
            order.append(key)
        row = grouped[key]
        quantity = _safe_int(target.get("quantity"))
        if quantity is None:
            row["unquantified_target_count"] += 1
        else:
            row["required_quantity"] += max(0, quantity)
            row["quantified_target_count"] += 1
        target_key = str(target.get("target_key") or "").strip()
        if target_key and target_key not in row["target_keys"]:
            row["target_keys"].append(target_key)
        purpose = str(target.get("purpose_key") or "").strip()
        if purpose and purpose not in row["purpose_keys"]:
            row["purpose_keys"].append(purpose)
    return [grouped[key] for key in order]


def build_card_auto_validation_contract(
    card: dict[str, Any],
    *,
    achievement_index: dict[str, tuple[int, str]] | None = None,
) -> dict[str, Any]:
    achievement_index = achievement_index or {}
    card_key = _stable_card_key(card)
    stage = card.get("manual_stage_data") if isinstance(card.get("manual_stage_data"), dict) else {}

    quest_ids = [qid for qid in (_safe_int(value) for value in card.get("manual_quest_ids", []) or []) if qid is not None]
    quest_names = [str(value).strip() for value in card.get("manual_quest_names", []) or [] if str(value).strip()]
    quests = [
        {"target_key": f"quest:{qid}", "quest_id": qid}
        for qid in dict.fromkeys(quest_ids)
    ]

    successes: list[dict[str, Any]] = []
    unresolved_successes: list[str] = []
    for name in _success_names(card, stage):
        found = achievement_index.get(normalize_text(name))
        if found is None:
            unresolved_successes.append(name)
            successes.append({"target_key": f"achievement_name:{normalize_text(name)}", "name": name, "achievement_id": None})
            continue
        aid, canonical_name = found
        successes.append({"target_key": f"achievement:{aid}", "name": canonical_name, "achievement_id": aid})

    dungeons = _dungeon_targets(stage)
    monsters = _monster_targets(stage)
    items, reserved, bank, captures = _item_targets(card)

    prose_farm_hints = _quantified_hints(card, _FARM_HINT_RE)
    prose_reserve_hints = _quantified_hints(card, _RESERVE_HINT_RE)
    prose_bank_hints = _quantified_hints(card, _BANK_HINT_RE)
    prose_capture_hints = _quantified_hints(card, _CAPTURE_HINT_RE)
    prose_item_hints = _quantified_hints(card, _ITEM_HINT_RE)

    missing_structured: list[str] = []
    if prose_farm_hints and not monsters:
        missing_structured.append("monster_farm")
    if prose_reserve_hints and not reserved:
        missing_structured.append("reserve_stock")
    if prose_bank_hints and not bank:
        missing_structured.append("bank_stock")
    if prose_capture_hints and not captures:
        missing_structured.append("capture_stock")
    if prose_item_hints and not items:
        missing_structured.append("item_quantity")

    return {
        "schema_version": AUTO_VALIDATION_SCHEMA_VERSION,
        "card_key": card_key,
        "quests": quests,
        "quest_names": quest_names,
        "successes": successes,
        "dungeons": dungeons,
        "monsters": monsters,
        "items": items,
        "reserved_items": reserved,
        "bank_reservations": bank,
        "capture_requirements": captures,
        "unresolved_success_names": unresolved_successes,
        "prose_hints": {
            "monster_farm": prose_farm_hints,
            "reserve_stock": prose_reserve_hints,
            "bank_stock": prose_bank_hints,
            "capture_stock": prose_capture_hints,
            "item_quantity": prose_item_hints,
        },
        # Compatibility alias used by the first readiness audit/tests.
        "prose_farm_hints": prose_farm_hints,
        "missing_structured_categories": missing_structured,
    }


def _build_route_auto_validation_contract_uncached(
    cards: list[dict[str, Any]],
    *,
    achievement_provider: Any = None,
) -> dict[str, Any]:
    achievement_index = _achievement_index(achievement_provider)
    rows = [build_card_auto_validation_contract(card, achievement_index=achievement_index) for card in cards]
    gap_counts: dict[str, int] = {}
    for row in rows:
        for category in row.get("missing_structured_categories", []) or []:
            gap_counts[category] = gap_counts.get(category, 0) + 1

    item_targets = [target for row in rows for target in row.get("items", []) or []]
    reserved_targets = [target for row in rows for target in row.get("reserved_items", []) or []]
    bank_targets = [target for row in rows for target in row.get("bank_reservations", []) or []]
    capture_targets = [target for row in rows for target in row.get("capture_requirements", []) or []]

    return {
        "schema_version": AUTO_VALIDATION_SCHEMA_VERSION,
        "source": "manual_guide_route",
        "cards": rows,
        "inventory_plan": {
            "items": _aggregate_quantity_targets(item_targets),
            "reserved_items": _aggregate_quantity_targets(reserved_targets),
            "bank_reservations": _aggregate_quantity_targets(bank_targets),
            "capture_requirements": _aggregate_quantity_targets(capture_targets),
        },
        "summary": {
            "card_count": len(rows),
            "quest_target_count": sum(len(row["quests"]) for row in rows),
            "success_target_count": sum(len(row["successes"]) for row in rows),
            "dungeon_target_count": sum(len(row["dungeons"]) for row in rows),
            "monster_target_count": sum(len(row["monsters"]) for row in rows),
            "item_target_count": len(item_targets),
            "reserved_target_count": len(reserved_targets),
            "bank_target_count": len(bank_targets),
            "capture_target_count": len(capture_targets),
            "cards_missing_structured_farm": gap_counts.get("monster_farm", 0),
            "gap_counts": dict(sorted(gap_counts.items())),
        },
    }


def _file_stamp(path: Path) -> tuple[int, int]:
    try:
        stat = Path(path).stat()
    except OSError:
        return (0, 0)
    return (int(stat.st_mtime_ns), int(stat.st_size))


def _achievement_provider_signature(provider: Any) -> tuple[object, ...]:
    if provider is None:
        return ("none",)
    data_dir = getattr(provider, "data_dir", None)
    if data_dir is None:
        return ("provider", id(provider))
    root = Path(data_dir)
    return (
        "provider-data",
        str(root),
        _file_stamp(root / "achievements.json"),
        _file_stamp(root / "languages" / "fr.json"),
        bool(getattr(provider, "_loaded", False)),
    )


def _manual_cards_signature(cards: list[dict[str, Any]]) -> tuple[object, ...] | None:
    if not cards or not all(
        bool(card.get("manual_source")) and card.get("_manual_route_cacheable") is True
        for card in cards
    ):
        return None
    identities = tuple(
        (
            str(card.get("manual_chapter_id") or ""),
            str(card.get("manual_stage_id") or ""),
            int(card.get("index") or index),
        )
        for index, card in enumerate(cards)
    )
    return (_manual_tree_signature(_MANUAL_DIR), identities)


def build_route_auto_validation_contract(
    cards: list[dict[str, Any]],
    *,
    achievement_provider: Any = None,
) -> dict[str, Any]:
    """Build the contract once per immutable manual route/provider revision."""

    route_signature = _manual_cards_signature(cards)
    if route_signature is None:
        return _build_route_auto_validation_contract_uncached(
            cards,
            achievement_provider=achievement_provider,
        )
    key = (route_signature, _achievement_provider_signature(achievement_provider))
    with _CONTRACT_CACHE_LOCK:
        cached = _CONTRACT_CACHE.get(key)
        if cached is not None:
            return cached
    contract = _build_route_auto_validation_contract_uncached(
        cards,
        achievement_provider=achievement_provider,
    )
    with _CONTRACT_CACHE_LOCK:
        _CONTRACT_CACHE[key] = contract
        while len(_CONTRACT_CACHE) > _MAX_CONTRACT_CACHE_ENTRIES:
            _CONTRACT_CACHE.pop(next(iter(_CONTRACT_CACHE)))
    return contract


def clear_auto_validation_contract_cache() -> None:
    with _CONTRACT_CACHE_LOCK:
        _CONTRACT_CACHE.clear()


def route_progress_counts(service: Any, character_key: str, contract: dict[str, Any] | None = None) -> dict[str, int]:
    cards = list(getattr(service, "cards", []) or [])

    # Manual runtime services expose a revision-aware route key. Refresh first so
    # an external or peer-written progress change can never be hidden by a cache
    # hit. The three reloads are signature/generation fast-paths when unchanged.
    cache_key_getter = getattr(service, "_route_cache_key", None)
    if callable(cache_key_getter):
        reload_progress = getattr(service, "reload_progress", None)
        if callable(reload_progress):
            reload_progress()

    cache_key = None
    if contract is not None and callable(cache_key_getter):
        cache_key = (cache_key_getter(character_key), id(contract))
        cache = getattr(service, "_route_progress_counts_cache", None)
        if isinstance(cache, dict) and cache_key in cache:
            return dict(cache[cache_key])

    contract = contract or build_route_auto_validation_contract(cards)

    quest_ids = {
        int(target["quest_id"])
        for row in contract.get("cards", []) or []
        for target in row.get("quests", []) or []
        if _safe_int(target.get("quest_id")) is not None
    }
    completed_quests = set(service.quest_progress.completed_quest_ids(character_key))

    dungeon_total = 0
    dungeon_done = 0
    contract_by_key = {str(row.get("card_key") or ""): row for row in contract.get("cards", []) or []}
    for index, card in enumerate(cards):
        row = contract_by_key.get(_stable_card_key(card), {})
        count = len(row.get("dungeons", []) or [])
        if not count:
            continue
        dungeon_total += count
        if callable(cache_key_getter):
            complete = service.card_state(
                character_key,
                card,
                index,
                completed_quests=completed_quests,
            ).complete
        else:
            complete = service.card_state(character_key, card, index).complete
        if complete:
            dungeon_done += count

    result = {
        "quests_completed": len(quest_ids.intersection(completed_quests)),
        "quests_total": len(quest_ids),
        "dungeons_completed": dungeon_done,
        "dungeons_total": dungeon_total,
    }
    if cache_key is not None and callable(cache_key_getter):
        final_key = (cache_key_getter(character_key), id(contract))
        service._route_progress_counts_cache = {final_key: dict(result)}
    return result


__all__ = [
    "AUTO_VALIDATION_SCHEMA_VERSION",
    "build_card_auto_validation_contract",
    "build_route_auto_validation_contract",
    "route_progress_counts",
]
