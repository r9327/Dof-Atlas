from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import DATA_DIR
from app.modules.encyclopedia.providers import GuideProvider
from app.modules.encyclopedia.services.guide_catalog_builder import DOFUS_GUIDE_ORDER, GuideCatalogBuilder
from app.modules.encyclopedia.services.guide_path_profiles import ORDER_QUEST_IDS, ORDER_QUESTS
from app.quest_catalog import normalize_text

GUIDES_DIR = DATA_DIR / "encyclopedia" / "guides"
ARTIFACTS_DIR = ROOT / "artifacts"


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON invalide: {path}")
    return payload


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(path)


def collect_quest_ids(value: Any) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            kind = normalize_text(node.get("type") or node.get("step_type") or "")
            if kind == "quest":
                try:
                    quest_id = int(node.get("entity_id"))
                except (TypeError, ValueError):
                    quest_id = None
                if quest_id is not None and quest_id not in seen:
                    seen.add(quest_id)
                    result.append(quest_id)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return result


def fresh_provider(builder: GuideCatalogBuilder) -> GuideProvider:
    return GuideProvider(
        guides_dir=GUIDES_DIR,
        quest_provider=builder.quest_provider,
        achievement_provider=builder.achievement_provider,
        dofus_item_provider=builder.dofus_item_provider,
        include_drafts=True,
    )


def validate_exact_live(builder: GuideCatalogBuilder, guide_id: str, payload: dict[str, Any]) -> None:
    provider = fresh_provider(builder)
    guide = provider.get_by_id(guide_id)
    if guide is None:
        raise RuntimeError(f"{guide_id}: GuideProvider ne charge pas le guide")

    expected = set(collect_quest_ids(payload))
    visible = {int(value) for value in guide.quest_ids}
    if expected != visible:
        missing = sorted(expected - visible)
        extra = sorted(visible - expected)
        raise RuntimeError(
            f"{guide_id}: différence GuideProvider; manquantes={missing[:20]}, extras={extra[:20]}, "
            f"attendu={len(expected)}, visible={len(visible)}"
        )

    # Validate only the guide/quest structure touched by this patch.
    # Reward/illustration assets can legitimately be absent from a lightweight
    # architecture export and must not rollback otherwise valid quest guides.
    fatal_tokens = (
        "quete_inexistante",
        "etape_dupliquee",
        "type_d_etape_non_autorise",
        "prerequis_circulaire",
        "guide_vide",
    )
    errors = provider.validate_guide(guide)
    fatal = [
        error
        for error in errors
        if any(token in normalize_text(error) for token in fatal_tokens)
    ]
    if fatal:
        raise RuntimeError(f"{guide_id}: validation structure/quête: {fatal[:10]}")


def validate_alignment_live(builder: GuideCatalogBuilder, side: str, payload: dict[str, Any]) -> None:
    guide_id = f"alignement_{side}"
    validate_exact_live(builder, guide_id, payload)
    guide = fresh_provider(builder).get_by_id(guide_id)
    if guide is None:
        raise RuntimeError(f"{guide_id}: absent")

    parts = list(guide.parts)
    if len(parts) != 8:
        raise RuntimeError(
            f"{guide_id}: 8 étapes attendues (5 alignement + 3 Ordres), obtenu {len(parts)}"
        )

    main_quest_ids = {
        int(step.entity_id)
        for part in parts[:5]
        for step in part.steps
        if step.step_type == "quest" and step.entity_id is not None
    }
    if len(main_quest_ids) != 100:
        raise RuntimeError(f"{guide_id}: {len(main_quest_ids)} quêtes principales au lieu de 100")

    expected_titles = sorted(ORDER_QUEST_IDS[side], key=normalize_text)
    actual_order_titles = [part.title for part in parts[5:]]
    if [normalize_text(value) for value in actual_order_titles] != [
        normalize_text(value) for value in expected_titles
    ]:
        raise RuntimeError(
            f"{guide_id}: Ordres mal rangés ou non séparés; "
            f"attendus={expected_titles}, visibles={actual_order_titles}"
        )

    for part, title in zip(parts[5:], expected_titles, strict=True):
        actual_ids = [
            int(step.entity_id)
            for step in part.steps
            if step.step_type == "quest" and step.entity_id is not None
        ]
        expected_ids = list(ORDER_QUEST_IDS[side][title])
        if actual_ids != expected_ids:
            raise RuntimeError(
                f"{guide_id}: {title}: quest_id/order incorrect; "
                f"attendus={expected_ids}, visibles={actual_ids}"
            )

    visible_all = {int(value) for value in guide.quest_ids}
    if len(visible_all) != 115:
        raise RuntimeError(
            f"{guide_id}: total visible {len(visible_all)} au lieu de 115 (100 alignement + 15 Ordres)"
        )


def current_count(guide_id: str) -> int:
    path = GUIDES_DIR / f"{guide_id}.json"
    if not path.exists():
        return 0
    return len(collect_quest_ids(read_json(path)))


def print_audit(result: Any) -> None:
    profile_report = result.report.get("profiled_dofus", {})
    print()
    print("=" * 104)
    print("DOFUS ATLAS — GUIDES V3 — AVANT / APRÈS")
    print("=" * 104)
    for side in ("bonta", "brakmar"):
        guide_id = f"alignement_{side}"
        payload = result.guides[guide_id]
        print(
            f"{payload['title']:<34} {current_count(guide_id):>4} -> {len(collect_quest_ids(payload)):>4}  "
            "| 3 étapes d'Ordre séparées x 5 quêtes"
        )
    print("-" * 104)
    print(f"{'GUIDE':34} {'AVANT':>7} {'AJOUT':>7} {'APRÈS':>7} {'CIBLE':>10}  ETAT")
    for guide_id in DOFUS_GUIDE_ORDER:
        payload = result.guides.get(guide_id)
        if payload is None:
            continue
        row = profile_report.get(guide_id, {})
        before = current_count(guide_id)
        after = len(collect_quest_ids(payload))
        exact = row.get("expected_exact")
        minimum = row.get("expected_min")
        target = str(exact) if exact is not None else (f">={minimum}" if minimum is not None else "-")
        status = row.get("status") or ("OK" if payload.get("completeness_status") == "complete" else "PARTIEL")
        print(f"{str(payload.get('title') or guide_id)[:33]:34} {before:>7} {max(0, after-before):>7} {after:>7} {target:>10}  {status}")
    print("=" * 104)


def apply_one(
    builder: GuideCatalogBuilder,
    guide_id: str,
    payload: dict[str, Any],
    backup_dir: Path,
    validator: Any,
) -> tuple[str, str]:
    path = GUIDES_DIR / f"{guide_id}.json"
    if not path.exists():
        return "ECHEC", f"fichier absent: {path}"

    backup = backup_dir / path.name
    shutil.copy2(path, backup)
    try:
        write_json_atomic(path, payload)
        validator()
        return "APPLIQUE", "validation GuideProvider OK"
    except Exception as exc:
        shutil.copy2(backup, path)
        return "ECHEC", str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Applique les guides Dofus complets et les Ordres d'alignement, guide par guide.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    builder = GuideCatalogBuilder()
    result = builder.build()
    print_audit(result)

    report: dict[str, Any] = {
        "timestamp": stamp,
        "mode": "apply" if args.apply else "audit",
        "results": {},
        "profiled_dofus": result.report.get("profiled_dofus", {}),
    }

    if not args.apply:
        print("\nAUDIT UNIQUEMENT — aucun fichier modifié.")
        print(r"Application: py -3.13 .\tools\apply_verified_guides_v3.py --apply")
    else:
        backup_dir = ARTIFACTS_DIR / f"guides_v3_backup_{stamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Alignments are isolated from Dofus failures. A Dofus problem can no longer rollback Orders.
        for side in ("bonta", "brakmar"):
            guide_id = f"alignement_{side}"
            payload = result.guides[guide_id]
            state, detail = apply_one(
                builder,
                guide_id,
                payload,
                backup_dir,
                lambda s=side, p=payload: validate_alignment_live(builder, s, p),
            )
            report["results"][guide_id] = {"state": state, "detail": detail}
            print(f"{guide_id}: {state} — {detail}")

        profile_report = result.report.get("profiled_dofus", {})
        for guide_id in DOFUS_GUIDE_ORDER:
            payload = result.guides.get(guide_id)
            if payload is None:
                report["results"][guide_id] = {"state": "NON_APPLIQUE", "detail": "guide absent du build"}
                print(f"{guide_id}: NON_APPLIQUE — guide absent du build")
                continue

            row = profile_report.get(guide_id, {})
            if row.get("status") != "OK" or payload.get("completeness_status") != "complete":
                detail = "; ".join(row.get("unresolved", [])) or "profil complet non démontré"
                if row.get("expected_exact") is not None:
                    detail = f"{row.get('after')}/{row.get('expected_exact')} — {detail}"
                elif row.get("expected_min") is not None:
                    detail = f"{row.get('after')}/{row.get('expected_min')} minimum — {detail}"
                report["results"][guide_id] = {"state": "NON_APPLIQUE", "detail": detail}
                print(f"{guide_id}: NON_APPLIQUE — {detail}")
                continue

            state, detail = apply_one(
                builder,
                guide_id,
                payload,
                backup_dir,
                lambda gid=guide_id, p=payload: validate_exact_live(builder, gid, p),
            )
            report["results"][guide_id] = {"state": state, "detail": detail}
            print(f"{guide_id}: {state} — {detail}")

        print(f"\nBackup par fichier: {backup_dir}")
        print("Un échec sur un guide restaure uniquement CE guide; les autres restent appliqués.")

    report_path = ARTIFACTS_DIR / f"guides_v3_report_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Rapport: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        # Keep PowerShell alive and always expose the real Python error.
        print("\nERREUR V3 — aucun exit PowerShell n'est exécuté.")
        print(f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
