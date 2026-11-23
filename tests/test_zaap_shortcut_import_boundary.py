from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import zaap_shortcuts
from app.core.profile_settings import read_zaap_button_ratios as read_profile_ratios
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

    def test_profile_and_macro_use_one_ratio_codec_with_independent_file_paths(self) -> None:
        cases = (
            ({}, None),
            ({"zaap_button": {"x_ratio": "0.25", "y_ratio": 1}}, (0.25, 1.0)),
            ({"zaap_button": {"x_ratio": 0, "y_ratio": 0}}, (0.0, 0.0)),
            ({"zaap_button": {"x_ratio": -0.1, "y_ratio": 0.3}}, None),
            ({"zaap_button": {"x_ratio": "nan", "y_ratio": 0.2}}, None),
            ({"zaap_button": []}, None),
        )
        for payload, expected in cases:
            with self.subTest(payload=payload):
                self.assertEqual(read_profile_ratios(payload), expected)
                self.assertEqual(zaap_shortcuts.read_zaap_button_ratios(payload), expected)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile-zaap-shortcuts.json"
            path.write_text(
                json.dumps({"zaap_button": {"x_ratio": 0.2, "y_ratio": 0.8}}),
                encoding="utf-8",
            )
            self.assertEqual(read_profile_ratios(path=path), (0.2, 0.8))
            # An explicit caller payload wins over a potentially stale disk copy.
            self.assertEqual(
                read_profile_ratios({"zaap_button": {"x_ratio": 0.4, "y_ratio": 0.6}},
                                    path=path),
                (0.4, 0.6),
            )

    def test_file_based_macro_reader_uses_non_ui_json_loader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shortcuts.json"
            path.write_text(json.dumps({"zaap_button": {"x_ratio": 0.25, "y_ratio": 0.75}}), encoding="utf-8")
            with patch.object(zaap_shortcuts, "ZAAP_SHORTCUTS_FILE", path):
                self.assertEqual(zaap_shortcuts.read_zaap_button_ratios(), (0.25, 0.75))

    def test_macro_uses_chat_command_without_legacy_click_dependencies(self) -> None:
        path = ROOT / "app/macros/zaap.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(node.module == "app.storage" for node in imports))
        imported_modules = {node.module for node in imports}
        self.assertIn("app.macros.input_tools", imported_modules)
        self.assertNotIn("app.core.zaap_shortcuts", imported_modules)
        self.assertNotIn("app.windows.clicks", imported_modules)


if __name__ == "__main__":
    unittest.main()
