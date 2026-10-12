from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.quest_source_index import QuestSourceError, QuestSources


class QuestSourceBoundaryTests(unittest.TestCase):
    def test_required_rows_reject_missing_business_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = QuestSources(root / "cache")
            try:
                with self.assertRaises(QuestSourceError):
                    len(sources.rows(root / "quests.json"))
            finally:
                sources.close()

    def test_required_rows_reject_malformed_business_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "quests.json"
            path.write_text('{"RefIds": [{"data": {"id": 1}}', encoding="utf-8")
            sources = QuestSources(root / "cache")
            try:
                with self.assertRaises(QuestSourceError):
                    list(sources.rows(path).items())
            finally:
                sources.close()

    def test_required_rows_read_valid_doduda_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "quests.json"
            path.write_text(
                json.dumps({"RefIds": [{"data": {"id": 42, "nameId": 7}}]}),
                encoding="utf-8",
            )
            sources = QuestSources(root / "cache")
            try:
                self.assertEqual(sources.rows(path)[42]["nameId"], 7)
            finally:
                sources.close()

    def test_primed_objective_ids_still_require_valid_canonical_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = QuestSources(root / "cache")
            try:
                sources.prime_objective_steps({10: [40, 41]})
                with self.assertRaises(QuestSourceError):
                    list(sources.objectives_for_steps(root / "quest_objectives.json", [10]))
            finally:
                sources.close()

    def test_selected_enrichment_avoids_full_offsets_and_nested_key_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "quests_enriched.json"
            # The requested key also appears deep inside an earlier record.
            # Only the direct member of "quests" is a real Quest enrichment.
            source = {"quests": {
                "1": {"solution_blocks": [{"other": {"18": {"source": "wrong"}}}]},
                "18": {"source": "correct", "solution_steps": [{"title": 'Test "quoted"'}]},
                "19": {"source": "later"},
            }}
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            sources = QuestSources(root / "cache")
            try:
                mapping = sources.mapping(path, "quests")
                self.assertEqual(
                    mapping.selected_values({"18"}),
                    {"18": source["quests"]["18"]},
                )
                # Selected lookup does not materialize thousands of offsets.
                self.assertIsNone(mapping._offsets)
                # Ordinary indexed reads continue to work afterwards.
                self.assertEqual(mapping["1"], source["quests"]["1"])
                self.assertEqual(mapping["19"], source["quests"]["19"])
            finally:
                sources.close()

    def test_missing_optional_selected_enrichment_remains_empty_and_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = QuestSources(root / "cache")
            try:
                with self.assertLogs("dofus_atlas_pyside", level="WARNING") as logs:
                    self.assertEqual(
                        sources.mapping(root / "quests_enriched.json", "quests")
                        .selected_values({"18"}),
                        {},
                    )
                self.assertTrue(any("optionnelle" in line for line in logs.output))
            finally:
                sources.close()

    def test_optional_enrichment_fallback_is_logged_and_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = QuestSources(root / "cache")
            path = root / "quests_enriched.json"
            try:
                with self.assertLogs("dofus_atlas_pyside", level="WARNING") as logs:
                    mapping = sources.mapping(path, "quests")
                    self.assertEqual(len(mapping), 0)
                self.assertTrue(any("optionnelle" in message for message in logs.output))
            finally:
                sources.close()


if __name__ == "__main__":
    unittest.main()
