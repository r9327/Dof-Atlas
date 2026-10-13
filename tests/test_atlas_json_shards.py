from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_json_shards import activate_version, build, current_directory, read_by_id, verify


class AtlasJsonShardTests(unittest.TestCase):
    def test_deterministic_shards_by_stable_id_roundtrip_and_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "canonical" / "quests_enriched.json"
            source.parent.mkdir()
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
            finer = build(source, output, ids_per_shard=8)
            self.assertEqual(finer["record_count"], len(rows))
            self.assertEqual(len(finer["shards"]), 10)
            self.assertEqual(read_by_id(output, 17), rows["17"])
            # Two deterministic layouts coexist without overwriting old snapshots.
            older_version = f"quests_v1_{first['source_sha256']}_0016"
            self.assertEqual(verify(source, output / "versions" /
                older_version, cache_root=root / "offsets"), first)
            self.assertEqual(activate_version(source, output, older_version), first)
            self.assertEqual(current_directory(output).name, older_version)
            self.assertEqual(read_by_id(output, 17), rows["17"])
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            with self.assertRaises(KeyError):
                read_by_id(output, 999999)

    def test_corruption_does_not_silently_fallback_and_source_change_invalidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "canonical" / "quests_enriched.json", root / "derived"
            source.parent.mkdir()
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


    def test_manifest_corruption_fails_closed_before_publishing_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "canonical" / "quests_enriched.json"
            source.parent.mkdir()
            source.write_text(
                '{"quests":{"10":{"name":"A"},"11":{"name":"B"}}}',
                encoding="utf-8",
            )
            output = root / "derived"
            original = build(source, output, ids_per_shard=4)
            folder = current_directory(output)
            manifest_file = folder / "manifest.json"
            pristine = manifest_file.read_bytes()

            for modify in (
                lambda m: m["index"].update({"10": "quests_00000003.json"}),
                lambda m: m.update({"record_count": True}),
                lambda m: m["shards"][next(iter(m["shards"]))].update(
                    {"record_count": 999}
                ),
                lambda m: m.update({"source_sha256": "not-a-sha"}),
            ):
                corrupted = json.loads(pristine)
                modify(corrupted)
                manifest_file.write_text(json.dumps(corrupted), encoding="utf-8")
                with self.subTest(corrupted=corrupted):
                    with self.assertRaises(ValueError):
                        read_by_id(output, 10)
                    with self.assertRaises(ValueError):
                        verify(source, folder, cache_root=root / "offsets")
                    with self.assertRaises(ValueError):
                        build(source, output, ids_per_shard=4)
                manifest_file.write_bytes(pristine)

            self.assertEqual(verify(source, folder, cache_root=root / "offsets"), original)
            self.assertEqual(read_by_id(output, 11), {"name": "B"})
            with self.assertRaises(ValueError):
                activate_version(source, output, "../other")
            self.assertEqual(current_directory(output), folder)

            source.write_text(
                '{"quests":{"10":{"name":"changed"},"11":{"name":"B"}}}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                activate_version(source, output, folder.name)
            self.assertEqual(current_directory(output), folder)


if __name__ == "__main__":
    unittest.main()
