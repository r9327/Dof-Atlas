from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.quest_source_index import JsonSourceMapping


class QuestSourceIndexStreamingTests(unittest.TestCase):
    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    def test_object_mapping_streams_nested_unicode_and_escaped_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "mapping.json"
            self._write_json(
                source,
                {
                    "ignored": {"large": [1, 2, {"text": "brace } and comma ,"}]},
                    "payload": {
                        "entries": {
                            "clé-é": {
                                "text": "guillemet \" et accolade }",
                                "nested": [1, {"emoji": "éàç"}],
                            },
                            "plain": "valeur",
                        }
                    },
                    "tail": True,
                },
            )

            mapping = JsonSourceMapping(source, root / "cache", "entries")
            with patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("full source read forbidden"),
            ):
                self.assertEqual(len(mapping), 2)
                self.assertEqual(mapping["clé-é"]["nested"][1]["emoji"], "éàç")
                self.assertEqual(mapping["plain"], "valeur")
            mapping.close()

    def test_doduda_refids_can_be_nested_without_full_source_decode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "rows.json"
            self._write_json(
                source,
                {
                    "meta": {"version": 1, "text": "RefIds inside a string is ignored"},
                    "wrapper": {
                        "ignored": {"RefIds": 123},
                        "payload": {
                            "RefIds": [
                                {
                                    "data": {
                                        "id": 42,
                                        "name": "Monstre, {test}",
                                        "nested": {"quote": "\\\""},
                                    }
                                },
                                {"data": {"id": 7, "items": ["a,b", "é"]}},
                            ]
                        },
                    },
                },
            )

            rows = JsonSourceMapping(source, root / "cache", "RefIds", doduda=True)
            with patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("full source read forbidden"),
            ):
                self.assertEqual(set(rows), {42, 7})
                self.assertEqual(rows[42]["name"], "Monstre, {test}")
                self.assertEqual(rows[7]["items"], ["a,b", "é"])
            rows.close()

    def test_streaming_offset_cache_is_reused_without_rescanning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "mapping.json"
            self._write_json(
                source,
                {"payload": {"entries": {"1": {"name": "A"}, "2": {"name": "B"}}}},
            )
            cache_root = root / "cache"

            first = JsonSourceMapping(source, cache_root, "entries")
            self.assertEqual(first["1"]["name"], "A")
            first.close()
            self.assertTrue(list(cache_root.glob("source_*.json.gz")))

            second = JsonSourceMapping(source, cache_root, "entries")
            with patch.object(
                JsonSourceMapping,
                "_build_offsets",
                side_effect=AssertionError("offset cache should be reused"),
            ):
                self.assertEqual(second["2"]["name"], "B")
            second.close()


if __name__ == "__main__":
    unittest.main()
