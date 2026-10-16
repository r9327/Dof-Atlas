from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_json_benchmark import benchmark
from tools.atlas_json_shards import build


class AtlasJsonBenchmarkTests(unittest.TestCase):
    def test_compare_both_strategies_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "canonical" / "quests_enriched.json"
            source.parent.mkdir()
            rows = {
                str(i): {
                    "name": f"Quête {i}",
                    "details": ["{}[]\\\\\\\"" * 30, None, i],
                }
                for i in range(1, 77)
            }
            original = json.dumps({"quests": rows}, ensure_ascii=False)
            source.write_text(original, encoding="utf-8")
            shards = root / "derived"
            build(source, shards, ids_per_shard=12)
            result = benchmark(source, shards, sample_count=11)

            self.assertTrue(result["lookup_values_equal"])
            self.assertEqual(result["sample_count"], 11)
            self.assertEqual(result["record_count"], 76)
            self.assertEqual(result["shard_count"], 7)
            self.assertFalse(result["runtime_consumers_changed"])
            self.assertGreaterEqual(result["source_offset_lookup_seconds"], 0)
            self.assertGreaterEqual(result["derived_shard_lookup_seconds"], 0)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_invalid_sample_sizes_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            benchmark(Path("unused"), Path("unused"), sample_count=0)
        with self.assertRaises(ValueError):
            benchmark(Path("unused"), Path("unused"), sample_count=1001)


if __name__ == "__main__":
    unittest.main()
