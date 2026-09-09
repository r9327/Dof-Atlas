from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    MANUAL_DIR,
    GuideUltimeManualRuntimeService,
)
from app.quest_catalog import QuestObjective, QuestRecord, QuestStep, normalize_text


class _QuestProvider:
    def __init__(self, quest: QuestRecord) -> None:
        self.quest = quest

    def get_quest(self, quest_id: int):
        return self.quest if int(quest_id) == int(self.quest.id) else None


class GuideUltimeManualClassBranchTests(unittest.TestCase):
    @staticmethod
    def _binding_file(root: Path, characters: dict[str, dict]) -> Path:
        binding_path = root / "bindings.json"
        binding_path.write_text(
            json.dumps({"characters": characters}, ensure_ascii=False),
            encoding="utf-8",
        )
        return binding_path

    @staticmethod
    def _service(binding_path: Path | None = None) -> GuideUltimeManualRuntimeService:
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.manual_dir = MANUAL_DIR
        if binding_path is not None:
            service.network_character_binding_path = binding_path
        return service

    def test_verified_character_binding_selects_only_matching_manual_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binding_path = self._binding_file(
                root,
                {
                    "55": {
                        "name": "Alice",
                        "class_key": "eliotrope",
                        "source": "verified_network_identity",
                    }
                },
            )
            service = self._service(binding_path)

            gate = service._manual_class_route()
            self.assertIsNotNone(gate)
            self.assertEqual(len(gate["branches"]), 19)
            self.assertEqual(service._character_class_key("character:55"), "eliotrope")

            class_key, branch = service._selected_class_branch("character:55", gate)
            self.assertEqual(class_key, "eliotrope")
            self.assertEqual(branch["quest"], "Un rayon de soleil")

            lines = service._manual_class_branch_lines("character:55", gate)
            rendered = "\n".join(
                f"{row.get('position', '')} {row.get('text', '')}" for row in lines
            )
            self.assertIn("Un rayon de soleil", rendered)
            self.assertIn("[7,-19]", rendered)
            self.assertIn("Ça sent le gaz", rendered)
            self.assertNotIn("Iop et hop", rendered)
            self.assertNotIn("C'est pour ta pomme", rendered)

    def test_verified_binding_can_infer_class_from_its_own_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binding_path = self._binding_file(
                root,
                {
                    "66": {
                        "name": "Bob - Pandawa - DOFUS",
                        "source": "verified_network_identity",
                    }
                },
            )
            service = self._service(binding_path)

            self.assertEqual(
                service._character_class_key("character:66"),
                "pandawa",
            )

    def test_missing_or_unverified_binding_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            binding_path = self._binding_file(
                Path(tmp),
                {
                    "55": {
                        "name": "Alice - Eliotrope - DOFUS",
                        "class_key": "eliotrope",
                        "source": "organizer_metadata",
                    }
                },
            )
            service = self._service(binding_path)

            self.assertEqual(service._character_class_key("character:55"), "")
            self.assertEqual(service._character_class_key("character:99"), "")
            self.assertEqual(service._character_class_key("character:055"), "")

    def test_noncanonical_keys_never_read_binding_or_persisted_progress(self):
        class ProgressSpy:
            def __init__(self) -> None:
                self.reads: list[tuple[str, int]] = []

            def is_quest_completed(self, character_key: str, quest_id: int) -> bool:
                self.reads.append((character_key, quest_id))
                return False

        service = self._service()
        service.quest_progress = ProgressSpy()
        gate = service._manual_class_route()
        first_key, first_branch = next(iter(gate["branches"].items()))
        service._quest_name_to_id = {normalize_text(first_branch["quest"]): 101}

        with patch(
            "app.modules.encyclopedia.services.guide_ultime_manual_conditions.read_json_file",
            side_effect=AssertionError("noncanonical keys must not read bindings"),
        ):
            self.assertEqual(service._character_class_key("slot:1"), "")
            self.assertEqual(service._character_class_key("invalid"), "")

        self.assertEqual(service._selected_class_branch("slot:1", gate), ("", None))
        self.assertEqual(service._selected_class_branch("invalid", gate), ("", None))
        self.assertEqual(service.quest_progress.reads, [])

        class_key, branch = service._selected_class_branch(
            "slot:1",
            gate,
            completed_quests={101},
        )
        self.assertEqual(class_key, normalize_text(first_key))
        self.assertIs(branch, first_branch)
        self.assertEqual(service.quest_progress.reads, [])

    def test_unknown_class_keeps_warning_state_without_progress_lookup(self):
        class ProgressThatMustStayCold:
            def is_quest_completed(self, *_args) -> bool:
                raise AssertionError("noncanonical identity must stay out of persistence")

        service = self._service()
        service.quest_progress = ProgressThatMustStayCold()
        gate = service._manual_class_route()

        lines = service._manual_class_branch_lines("slot:1", gate)

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["kind"], "warning")
        self.assertIn("Classe non détectée", lines[0]["text"])

    def test_enriched_quest_objective_replaces_generic_line_on_known_class_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binding_path = self._binding_file(
                root,
                {
                    "42": {
                        "name": "Alice",
                        "class_key": "eliotrope",
                        "source": "verified_network_identity",
                    }
                },
            )
            quest = QuestRecord(
                id=42,
                name="Un rayon de soleil",
                category="Astrub",
                level_min=20,
                level_max=20,
                start_criterion="",
                steps=[],
                source_solution_steps=[
                    QuestStep(
                        id=-1,
                        name="",
                        description="",
                        objectives=[
                            QuestObjective(
                                id=-1001,
                                text="Parlez à la Sentinelle Eliotrope pour poursuivre la quête.",
                                type_id=0,
                                map_label="[1,-17]",
                            )
                        ],
                    )
                ],
            )

            service = self._service(binding_path)
            service.quest_provider = _QuestProvider(quest)
            service._quest_name_to_id = {normalize_text(quest.name): quest.id}

            gate = service._manual_class_route()
            self.assertIsNotNone(gate)
            lines = service._manual_class_branch_lines("character:42", gate)
            exact = [row for row in lines if row.get("position") == "[1,-17]"]
            self.assertTrue(exact, lines)
            self.assertTrue(
                any("Sentinelle Eliotrope" in str(row.get("text") or "") for row in exact),
                exact,
            )
            self.assertFalse(
                any("Effectue l'objectif actif" in str(row.get("text") or "") for row in exact),
                exact,
            )
            self.assertTrue(
                any("Effectue l'objectif actif" in str(row.get("text") or "") for row in lines),
                "Les positions non couvertes par l'enrichissement doivent garder le fallback.",
            )

    def test_manifest_forbids_manual_class_selection(self):
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.manual_dir = MANUAL_DIR
        gate = service._manual_class_route()
        self.assertIsNotNone(gate)
        trigger = gate["trigger"]
        self.assertEqual(trigger.get("selector"), "actual_character_class")
        self.assertIs(trigger.get("manual_selection_forbidden"), True)


if __name__ == "__main__":
    unittest.main()
