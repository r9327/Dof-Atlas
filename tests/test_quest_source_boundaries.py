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
