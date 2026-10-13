from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_json_shards import build, current_directory, read_by_id, verify


class AtlasJsonShardTests(unittest.TestCase):
    def test_deterministic_shards_by_stable_id_roundtrip_and_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "quests_enriched.json"
            rows = {str(key): {
                "quest_id": key,
                "prerequisites": ["Étape \"à\" terminer", None] if key % 3 == 0 else [],
                "steps": [{"text": "évasion \\ [ ] { } " * 20}, {"position": [1, -2]}],
                "nullable": None,
            } for key in range(1, 75)}
            original = json.dumps({"version": 2, "quests": rows}, ensure_ascii=False)
            source.write_text(original, encoding="utf-8")
            output = root / "derived"
            first = build(source, output, ids_per_shard=16)
            self.assertEqual(first["record_count"], len(rows))
            self.assertEqual(len(first["shards"]), 5)
            self.assertEqual(read_by_id(output, 17), rows["17"])
            self.assertEqual(read_by_id(output, 73), rows["73"])
            self.assertEqual(verify(source, current_directory(output), cache_root=root / "offsets"), first)
            again = build(source, output, ids_per_shard=16)
            self.assertEqual(again, first)
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            with self.assertRaises(KeyError):
                read_by_id(output, 999999)

    def test_corruption_does_not_silently_fallback_and_source_change_invalidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "quests_enriched.json", root / "derived"
            source.write_text('{"quests":{"10":{"name":"Quest"}}}', encoding="utf-8")
            report = build(source, output, ids_per_shard=4)
            shard = current_directory(output) / next(iter(report["shards"]))
            shard.write_bytes(b'{"quests":{}}')
            with self.assertRaises(ValueError):
                read_by_id(output, 10)
            with self.assertRaises(ValueError):
                verify(source, current_directory(output), cache_root=root / "offsets")
            # Corrupted published output is not overwritten or advertised as valid.
            with self.assertRaises(ValueError):
                build(source, output, ids_per_shard=4)
            source.write_text('{"quests":{"10":{"name":"Quest updated"}}}', encoding="utf-8")
            renewed = build(source, output, ids_per_shard=4)
            self.assertNotEqual(report["source_sha256"], renewed["source_sha256"])
            self.assertEqual(read_by_id(output, 10), {"name": "Quest updated"})


if __name__ == "__main__":
    unittest.main()
