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

    def test_large_source_offsets_skip_quoted_json_without_losing_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "quests_enriched.json"
            records = {
                "18": {
                    "text": "long " + ("écriture \\\" [{}] " * 8500),
                    "nested": [{"inner": {"}": "[escaped \\\\ path]"}}],
                },
                "19": {
                    "text": "small",
                    "nested": [1, {"nested": "quotation: \\\" and } ]"}],
                },
                "20": {"text": "final"},
            }
            path.write_text(
                json.dumps({"quests": records}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertGreater(path.stat().st_size, 64 * 1024)
            for _ in range(2):
                sources = QuestSources(root / "cache")
                try:
                    mapping = sources.mapping(path, "quests")
                    self.assertEqual(set(mapping), set(records))
                    for key, value in records.items():
                        self.assertEqual(mapping[key], value)
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
