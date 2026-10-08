from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import zaap_shortcuts
from app.storage import parse_unit_ratio, read_zaap_button_ratios as legacy_read


ROOT = Path(__file__).resolve().parents[1]


class ZaapShortcutImportBoundaryTests(unittest.TestCase):
    def test_storage_reexports_canonical_ratio_parser(self) -> None:
        self.assertIs(parse_unit_ratio, zaap_shortcuts.parse_unit_ratio)

    def test_legacy_and_core_readers_agree_for_payloads(self) -> None:
        payloads = (
            {},
            {"zaap_button": {}},
            {"zaap_button": {"x_ratio": 0.5, "y_ratio": 1}},
            {"zaap_button": {"x_ratio": "0.33", "y_ratio": "0.75"}},
            {"zaap_button": {"x_ratio": -0.1, "y_ratio": 0.1}},
            {"zaap_button": {"x_ratio": "nope", "y_ratio": 0.5}},
            {"zaap_button": []},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(legacy_read(payload), zaap_shortcuts.read_zaap_button_ratios(payload))

    def test_file_based_macro_reader_uses_non_ui_json_loader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shortcuts.json"
            path.write_text(json.dumps({"zaap_button": {"x_ratio": 0.25, "y_ratio": 0.75}}), encoding="utf-8")
            with patch.object(zaap_shortcuts, "ZAAP_SHORTCUTS_FILE", path):
                self.assertEqual(zaap_shortcuts.read_zaap_button_ratios(), (0.25, 0.75))

    def test_macro_does_not_eagerly_import_storage(self) -> None:
        path = ROOT / "app/macros/zaap.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(node.module == "app.storage" for node in imports))
        self.assertTrue(any(
            node.module == "app.core.zaap_shortcuts"
            and any(alias.name == "read_zaap_button_ratios" for alias in node.names)
            for node in imports
        ))


if __name__ == "__main__":
    unittest.main()
