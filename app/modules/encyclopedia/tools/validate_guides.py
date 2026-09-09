from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.modules.encyclopedia.providers import GuideProvider
from app.modules.encyclopedia.providers.guide_provider import GUIDE_ALLOWED_CATEGORIES
from app.quest_catalog import normalize_text

AUDIT_PATH = Path("artifacts/duffus_guides_full_audit.json")
BANNED_KEYS = {"verifier_les_prerequis", "continuer_le_parcours"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valide les guides locaux de l'Encyclop?die.")
    parser.add_argument("--guides-dir", type=Path, default=None, help="Dossier de guides ? valider.")
    args = parser.parse_args(argv)

    provider = GuideProvider(guides_dir=args.guides_dir) if args.guides_dir is not None else GuideProvider()
    guides = provider.load_all()
    errors = list(provider.validation_errors)
    warnings: list[str] = []
    linked_quests: set[int] = set()
    linked_achievements: set[int] = set()
    missing_images = 0
    part_count = 0
    chapter_count = 0
    series_count = 0
    activity_count = 0
    success_steps = 0
    duplicate_quests = 0
    prerequisite_progress_steps = 0
    verify_prereq_steps = 0

    for guide in guides:
        if guide.category not in GUIDE_ALLOWED_CATEGORIES:
            errors.append(f"{guide.id}: cat?gorie non autoris?e: {guide.category}")
        if not guide.sections:
            errors.append(f"{guide.id}: guide vide")
        if not guide.parts:
            errors.append(f"{guide.id}: structure parts absente")
        if guide.total_steps is not None and guide.total_steps != len(guide.steps):
            errors.append(f"{guide.id}: total_steps incoh?rent ({guide.total_steps} != {len(guide.steps)})")
        if guide.verified_steps is not None and guide.verified_steps > len(guide.steps):
            errors.append(f"{guide.id}: verified_steps sup?rieur au nombre d'?tapes")
        if guide.completeness_status not in {"complete", "partial", "draft"}:
            errors.append(f"{guide.id}: completeness_status invalide: {guide.completeness_status}")
        if guide.category == "dofus":
            if guide.completeness_status != "draft" and guide.reward_item_id is None:
                errors.append(f"{guide.id}: guide Dofus actif sans reward_item_id")
            if guide.completeness_status != "draft" and guide.illustration_item_id is None:
                errors.append(f"{guide.id}: guide Dofus actif sans illustration_item_id")
        if guide.image_path and not Path(guide.image_path).exists():
            missing_images += 1
            warnings.append(f"{guide.id}: image locale introuvable: {guide.image_path}")
        if guide.validation_warnings:
            warnings.extend(f"{guide.id}: {warning}" for warning in guide.validation_warnings)

        seen_guide_quests: set[int] = set()
        for part in guide.parts:
            part_count += 1
            if normalize_text(part.title) in BANNED_KEYS:
                verify_prereq_steps += 1
                errors.append(f"{guide.id}: bloc interdit: {part.title}")
            if part.progress_mode == "prerequisites":
                prerequisite_progress_steps += len(part.steps)
            for chapter in part.chapters:
                chapter_count += 1
                for series in chapter.series:
                    series_count += 1
                    activity_count += len(series.activities)
                    if normalize_text(series.title) in BANNED_KEYS:
                        verify_prereq_steps += 1
                        errors.append(f"{guide.id}: s?rie interdite: {series.title}")
                    for quest_id in series.quest_ids:
                        if quest_id in seen_guide_quests:
                            duplicate_quests += 1
                        seen_guide_quests.add(quest_id)

        for ref in guide.context_entities:
            if ref.entity_type == "achievement":
                linked_achievements.add(int(ref.entity_id))
        for section in guide.sections:
            if not section.steps:
                errors.append(f"{guide.id}: section vide: {section.id}")
            for step in section.steps:
                if step.step_type == "quest" and step.entity_id is not None:
                    linked_quests.add(int(step.entity_id))
                    _validate_alignment_separation(provider, guide.id, int(step.entity_id), errors)
                if step.step_type == "achievement" and step.entity_id is not None:
                    success_steps += 1
                    linked_achievements.add(int(step.entity_id))
                if normalize_text(step.display_title) in BANNED_KEYS:
                    verify_prereq_steps += 1
                    errors.append(f"{guide.id}: ?tape interdite: {step.display_title}")
                for error in step.validation_errors:
                    errors.append(f"{guide.id}: {step.id}: {error}")

    complete = sum(1 for guide in guides if guide.completeness_status == "complete")
    partial = sum(1 for guide in guides if guide.completeness_status == "partial")
    draft = sum(1 for guide in guides if guide.completeness_status == "draft")
    print(f"Guides actifs : {len(guides)}")
    print(f"Guides audit?s : {_audited_count()}")
    print(f"Guides complets : {complete}")
    print(f"Guides partiels : {partial}")
    print(f"Guides brouillons : {draft}")
    print(f"Parties : {part_count}")
    print(f"Chapitres : {chapter_count}")
    print(f"S?ries : {series_count}")
    print(f"Qu?tes li?es : {len(linked_quests)}")
    print(f"Succ?s li?s : {len(linked_achievements)}")
    print(f"Qu?tes uniques : {len(linked_quests)}")
    print(f"Objets r?solus : {sum(1 for guide in guides if guide.reward_item_id)}")
    print(f"Activit?s : {activity_count}")
    print(f"Succ?s compt?s comme ?tapes : {success_steps}")
    print(f"Doublons succ?s/qu?tes : {duplicate_quests}")
    print(f"Pr?requis compt?s dans la progression : {prerequisite_progress_steps}")
    print(f"?tapes V?rifier les pr?requis : {verify_prereq_steps}")
    print(f"R?f?rences invalides : {len(errors)}")
    print(f"Images manquantes : {missing_images}")
    for guide in guides:
        print(f"OK: {guide.id} - {guide.title}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


def _validate_alignment_separation(provider: GuideProvider, guide_id: str, quest_id: int, errors: list[str]) -> None:
    if guide_id not in {"alignement_bonta", "alignement_brakmar"}:
        return
    quest = provider.quest_provider.get_quest(quest_id)
    if quest is None:
        errors.append(f"{guide_id}: qu?te inexistante: {quest_id}")
        return
    if guide_id == "alignement_bonta" and "Br?kmar" in quest.category:
        errors.append(f"{guide_id}: qu?te Br?kmar m?lang?e: {quest_id}")
    if guide_id == "alignement_brakmar" and "Bonta" in quest.category:
        errors.append(f"{guide_id}: qu?te Bonta m?lang?e: {quest_id}")


def _audited_count() -> int:
    if not AUDIT_PATH.exists():
        return 0
    try:
        payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("guides", []) if isinstance(payload, dict) else []
        return len(rows) if isinstance(rows, list) else 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
