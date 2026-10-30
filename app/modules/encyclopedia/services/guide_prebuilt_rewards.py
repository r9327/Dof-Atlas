"""Portable build-time aggregate rewards for all Guide overviews.

The expensive aggregation of every quest's rich rewards runs on the build
runner, not on the Qt thread. Quest details remain lazy and authoritative.
Only a small release-owned JSON projection is retained, without progress.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from app.constants import DATA_DIR, ROOT_DIR, RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.providers.guide_provider import GUIDES_DIR
from app.modules.encyclopedia.services.guide_quest_view_model import DisplayReward, guide_rewards
from app.quest_catalog import QUEST_CATALOG_SOURCE_FILES

SCHEMA = 1
BUNDLE_PATH = DATA_DIR / "bootstrap" / "guide_rewards_v1.json"
MAX_BYTES = 8 * 1024 * 1024
_IMAGE_PREFIX = "@atlas-root/"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_sizes() -> dict[str, int]:
    values = {}
    for _label, relative in QUEST_CATALOG_SOURCE_FILES:
        path = RAW_QUEST_DATA_DIR / relative
        values[str(relative).replace("\\", "/")] = path.stat().st_size
    return values


def _encode_path(image_path: str) -> str:
    value = str(image_path or "")
    if not value:
        return ""
    path = Path(value)
    if path.is_absolute():
        try:
            return _IMAGE_PREFIX + path.relative_to(ROOT_DIR).as_posix()
        except ValueError as exc:
            raise ValueError("Guide reward image outside bundled assets") from exc
    if ".." in path.parts:
        raise ValueError("Guide reward image cannot escape bundled assets")
    return value


def _decode_path(image_path: str) -> str:
    value = str(image_path or "")
    if value.startswith(_IMAGE_PREFIX):
        relative = Path(value[len(_IMAGE_PREFIX):])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid precompiled Guide asset path")
        return str(ROOT_DIR / relative)
    if Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("Invalid external Guide asset path")
    return value


def _steps_sha(guide: Any) -> str:
    steps = [
        (
            str(getattr(step, "id", "") or ""),
            str(getattr(step, "step_type", "") or ""),
            str(getattr(step, "entity_id", "") or ""),
            int(getattr(step, "order", 0) or 0),
        )
        for step in getattr(guide, "required_steps", ()) or ()
    ]
    return hashlib.sha256(
        json.dumps(steps, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _guide_sha(guide_id: str) -> str:
    if not guide_id or "/" in guide_id or "\\" in guide_id or ".." in guide_id:
        raise ValueError("Invalid Guide identifier")
    return _sha256(GUIDES_DIR / f"{guide_id}.json")


def _path(path: Path | None) -> Path | None:
    if path is not None:
        return Path(path)
    override = os.environ.get("DOFUS_ATLAS_PREBUILT_REWARDS_FILE", "").strip()
    if override:
        return Path(override)
    return BUNDLE_PATH if bool(getattr(sys, "frozen", False)) else None


def write_bundle(
    guides: Iterable[Any],
    quest_catalog: Any,
    achievement_provider: Any,
    output: Path,
    *,
    source_sha: str,
) -> dict[str, int]:
    if len(source_sha) != 40 or any(c not in "0123456789abcdef" for c in source_sha):
        raise ValueError("Exact build SHA required")
    guide_rows: dict[str, dict[str, object]] = {}
    for guide in guides:
        guide_id = str(guide.id)
        quest_ids = tuple(dict.fromkeys(
            int(step.entity_id)
            for step in guide.required_steps
            if step.step_type == "quest" and step.entity_id is not None
        ))
        # Reuse canonical aggregation and the original Guide order: no
        # independent reward rules or accidental quest duplicates.
        quests = (
            quest_catalog.by_id[qid]
            for qid in quest_ids
            if qid in quest_catalog.by_id
        )
        rewards = guide_rewards(guide, achievement_provider, quests)
        guide_rows[guide_id] = {
            "guide_sha256": _guide_sha(guide_id),
            "guide_steps_sha256": _steps_sha(guide),
            "rewards": [
                {**asdict(reward), "image_path": _encode_path(reward.image_path)}
                for reward in rewards
            ],
        }
    if not guide_rows:
        raise ValueError("No Guide rewards to publish")
    payload = {
        "schema": SCHEMA,
        "source_sha": source_sha,
        "quest_source_sizes": _source_sizes(),
        "guides": guide_rows,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("Guide reward index exceeds size budget")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    try:
        temp.write_bytes(raw)
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)
    return {"guides": len(guide_rows), "bytes": len(raw)}


def cached_rewards(guide: Any, *, path: Path | None = None) -> tuple[DisplayReward, ...] | None:
    """None => exact existing runtime fallback; tuple => certified projection."""
    path = _path(path)
    if path is None:
        return None
    try:
        if not 0 < path.stat().st_size <= MAX_BYTES:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
            return None
        if _source_sizes() != payload.get("quest_source_sizes"):
            return None
        values = payload.get("guides")
        if not isinstance(values, dict):
            return None
        row = values.get(str(guide.id))
        if (not isinstance(row, dict)
                or row.get("guide_sha256") != _guide_sha(str(guide.id))
                or row.get("guide_steps_sha256") != _steps_sha(guide)):
            return None
        rewards = row.get("rewards")
        if not isinstance(rewards, list) or len(rewards) > 1000:
            return None
        output = []
        for reward in rewards:
            if not isinstance(reward, dict):
                return None
            if (set(reward) != {"kind", "name", "quantity", "image_path"}
                    or not isinstance(reward["kind"], str)
                    or not isinstance(reward["name"], str)
                    or (reward["quantity"] is not None
                        and type(reward["quantity"]) is not int)):
                return None
            output.append(DisplayReward(
                kind=reward["kind"], name=reward["name"],
                quantity=reward["quantity"],
                image_path=_decode_path(reward["image_path"]),
            ))
        return tuple(output)
    except (OSError, ValueError, TypeError, KeyError):
        return None
