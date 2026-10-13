from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_json_inventory import audit


class AtlasJsonInventoryTests(unittest.TestCase):
    def test_quest_sources_manual_guides_and_lexical_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            enriched = "data/encyclopedia/quests/quests_enriched.json"
            image = "data/encyclopedia/quests/image_manifest.json"
            manual = "data/routes/guide_ultime_manual/astrub_v1.json"
            plain = "data/local/zaaps.json"
            paths = [enriched, image, manual, plain, "app/consumer.py",
                     "data/large_file_contracts.json"]
            for rel in paths:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
            for rel in (enriched, image, manual, plain):
                (root / rel).write_text('{"quests": {"1": {"name": "Épreuve"}}}', encoding="utf-8")
            (root / "app/consumer.py").write_text('name = "quests_enriched.json"\n', encoding="utf-8")
            (root / "data/large_file_contracts.json").write_text(
                json.dumps({"files": [{
                    "path": enriched, "role": "canonical_runtime_source",
                    "generator": "tools/example.py", "consumers": ["app/consumer.py"],
                }]}), encoding="utf-8",
            )
            report = audit(root, files=paths)
            rows = {r["path"]: r for r in report["files"]}
            self.assertEqual(report["json_count"], 5)
            self.assertEqual(rows[enriched]["status"], "INDEX_ONLY")
            self.assertEqual(rows[image]["status"], "REVIEW")
            self.assertEqual(rows[manual]["status"], "ALREADY_OPTIMIZED")
            self.assertEqual(rows[plain]["status"], "KEEP")
            self.assertEqual(rows[enriched]["declared_consumers"], ["app/consumer.py"])
            self.assertIn("app/consumer.py", rows[enriched]["consumer_text_candidates"])
            self.assertFalse(rows[enriched]["consumer_graph_verified"])
            self.assertEqual(rows[plain]["top_level_keys"], ["quests"])
            self.assertEqual(rows[plain]["runtime_profile"], "NOT_MEASURED")

    def test_bad_json_and_unavailable_lfs_are_not_reported_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bad, lfs = "bad.json", "large.json"
            (root / bad).write_text("{broken", encoding="utf-8")
            (root / lfs).write_bytes(
                b"version https://git-lfs.github.com/spec/v1\n"
                b"oid sha256:0000\nsize 10000000\n"
            )
            rows = {x["path"]: x for x in audit(root, files=[bad, lfs])["files"]}
            self.assertEqual(rows[bad]["status"], "REVIEW")
            self.assertIn("parse_error", rows[bad])
            self.assertFalse(rows[lfs]["available"])
            self.assertTrue(rows[lfs]["lfs_pointer"])
            self.assertIsNone(rows[lfs]["sha256"])


if __name__ == "__main__":
    unittest.main()
