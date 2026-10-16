from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.providers.dofus_item_provider import _iter_doduda_refs


class DodudaStreamingReaderTests(unittest.TestCase):
    def test_reads_chunk_boundaries_nested_values_and_escaped_strings(self) -> None:
        entries = [
            {
                "rid": index,
                "data": {
                    "id": index,
                    "text": 'escaped " quote, } brace, é unicode, \\ slash',
                    "effects": [{"rid": index + 1}, [1, {"nested": True}]],
                    "padding": "x" * (300000 if index == 12 else 20),
                },
            }
            for index in range(1200)
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "items.json"
            path.write_text(
                json.dumps({"version": "test", "RefIds": entries, "after": [1, 2]},
                           ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            self.assertEqual(list(_iter_doduda_refs(path)), entries)

    def test_empty_array_and_missing_refids_do_not_yield_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "items.json"
            for payload in ('{"RefIds":[]}', '{"other":[]}'):
                path.write_text(payload, encoding="utf-8")
                self.assertEqual(list(_iter_doduda_refs(path)), [])

    def test_truncated_item_is_not_silently_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "items.json"
            path.write_text('{"RefIds":[{"rid":1,"data":{"id":1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Incomplete Doduda RefIds"):
                list(_iter_doduda_refs(path))


if __name__ == "__main__":
    unittest.main()
