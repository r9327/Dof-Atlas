from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.quest_catalog import normalize_text


def load_ocre_capture_registry(manual_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Load the immutable Ocre registry referenced by the manual manifest."""

    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    filename = str(canonical.get("ocre_capture_registry") or "").strip()
    if not filename:
        return {}
    path = Path(manual_dir) / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Registre Ocre invalide: {path}")
    boss_steps = payload.get("boss_steps")
    if not isinstance(boss_steps, dict):
        raise ValueError(f"Registre Ocre sans boss_steps: {path}")
    return payload


def ocre_bosses_for_stage(stage: dict[str, Any], registry: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return registry bosses explicitly evidenced by one authored manual stage.

    Matching is deliberately conservative: only structured dungeon/monster data,
    the stage title and authored route/action text are considered. The adapter
    never invents a boss from a zone or level alone.
    """

    evidence = normalize_text(" ".join(_stage_evidence(stage)))
    if not evidence:
        return ()

    early_rows = {
        normalize_text(row.get("boss")): row
        for row in registry.get("early_route_state", []) or []
        if isinstance(row, dict) and normalize_text(row.get("boss"))
    }
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    boss_steps = registry.get("boss_steps") if isinstance(registry.get("boss_steps"), dict) else {}
    for step_number, values in boss_steps.items():
        for value in values if isinstance(values, list) else []:
            name = str(value or "").strip()
            key = normalize_text(name)
            if not key or key in seen or key not in evidence:
                continue
            seen.add(key)
            row = {
                "name": name,
                "step": str(step_number),
                "minimum_power": None,
                "state": "",
            }
            early = early_rows.get(key)
            if isinstance(early, dict):
                try:
                    minimum_power = int(early.get("minimum_power"))
                except (TypeError, ValueError):
                    minimum_power = None
                row["minimum_power"] = minimum_power if minimum_power and minimum_power > 0 else None
                row["state"] = str(early.get("state") or "")
            results.append(row)
    return tuple(results)


def ocre_capture_lines(
    stage: dict[str, Any],
    registry: dict[str, Any],
    *,
    capture_unlocked: bool,
    existing_lines: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
) -> list[dict[str, Any]]:
    """Build player-facing Ocre guidance from canonical structured evidence."""

    bosses = ocre_bosses_for_stage(stage, registry)
    if not bosses:
        return []
    existing = [
        normalize_text(str(row.get("text") or ""))
        for row in existing_lines
        if isinstance(row, dict) and str(row.get("text") or "").strip()
    ]
    rules = registry.get("rules") if isinstance(registry.get("rules"), dict) else {}
    special_kralamoure = bool(rules.get("kralamoure_special_capture"))
    result: list[dict[str, Any]] = []

    for boss in bosses:
        name = str(boss.get("name") or "").strip()
        key = normalize_text(name)
        if not key:
            continue
        # An authored capture instruction for this exact boss always wins over
        # generated guidance; unrelated capture text elsewhere in the card does
        # not hide the warning for another boss.
        if any(
            key in line and ("capture" in line or "pierre_d_ame" in line)
            for line in existing
        ):
            continue

        if not capture_unlocked:
            text = (
                f"Ocre — {name} est rencontré avant l'obtention de Capture d'âmes : "
                "ne simule aucune capture. Garde ce boss en rattrapage pour l'étape Ocre réelle."
            )
        elif special_kralamoure and "kralamoure" in key:
            text = (
                f"Ocre — {name} utilise la pierre spéciale fournie par L'éternelle moisson à l'étape 19 ; "
                "n'utilise pas de pierre standard."
            )
        else:
            minimum_power = boss.get("minimum_power")
            stone = (
                f"une pierre d'âme de puissance {int(minimum_power)} minimum"
                if isinstance(minimum_power, int) and minimum_power > 0
                else "une pierre d'âme de puissance adaptée au boss"
            )
            text = (
                f"Ocre — avant {name}, prépare {stone}, équipe-la et utilise Capture d'âmes. "
                "Si l'étape Ocre courante ne prend pas encore cette âme, conserve-la en banque et ne la vends pas."
            )
        result.append({"kind": "warning", "position": "", "text": text})
    return result


def ocre_unlock_policy_lines(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Surface the registry's cross-route capture policy when the spell unlocks."""

    if not registry:
        return []
    return [
        {
            "kind": "warning",
            "position": "",
            "text": (
                "Ocre — à partir de maintenant, garde des pierres adaptées disponibles : "
                "capture opportunistement tout archimonstre encore manquant croisé naturellement, "
                "mais ne bloque jamais la route principale en attendant son repop."
            ),
        }
    ]


def _stage_evidence(stage: dict[str, Any]) -> list[str]:
    values: list[str] = [str(stage.get("title") or "")]
    for field in ("dungeon", "dungeons", "monsters"):
        _collect_text(stage.get(field), values)
    for row in stage.get("route", []) or []:
        if not isinstance(row, dict):
            continue
        for field in ("area", "zone", "label", "pos", "position", "do", "action", "instruction"):
            value = row.get(field)
            if isinstance(value, str) and value.strip():
                values.append(value)
    return values


def _collect_text(value: Any, result: list[str]) -> None:
    if isinstance(value, str):
        if value.strip():
            result.append(value)
        return
    if isinstance(value, list):
        for child in value:
            _collect_text(child, result)
        return
    if not isinstance(value, dict):
        return
    for field in ("name", "boss", "monster", "label", "dungeon"):
        child = value.get(field)
        if isinstance(child, str) and child.strip():
            result.append(child)


__all__ = [
    "load_ocre_capture_registry",
    "ocre_bosses_for_stage",
    "ocre_capture_lines",
    "ocre_unlock_policy_lines",
]
