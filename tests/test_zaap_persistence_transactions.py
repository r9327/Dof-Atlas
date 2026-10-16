from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.core.json_store import InvalidPersistentJsonError
from app.core.zaap_shortcuts import update_zaap_shortcuts_field


class ZaapPersistenceTransactionTests(unittest.TestCase):
    def test_field_updates_keep_other_keys_and_existing_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "shortcuts.json"
            path.write_text(json.dumps({"custom": "unchanged"}), encoding="utf-8")
            update_zaap_shortcuts_field(
                path, "zaap_favorites", ["Astrub", "Bonta"]
            )
            update_zaap_shortcuts_field(
                path, "zaap_button", {"x_ratio": 0.7, "y_ratio": 0.8}
            )
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {
                    "custom": "unchanged",
                    "zaap_favorites": ["Astrub", "Bonta"],
                    "zaap_button": {"x_ratio": 0.7, "y_ratio": 0.8},
                },
            )

    def test_corrupt_settings_are_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "shortcuts.json"
            original = b'{"zaap_button":'
            path.write_bytes(original)
            with self.assertRaises(InvalidPersistentJsonError):
                update_zaap_shortcuts_field(path, "zaap_favorites", ["Astrub"])
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(list(path.parent.glob("shortcuts.json.corrupt.*.bak"))), 1)

    def test_concurrent_processes_preserve_both_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "shortcuts.json"
            script = (
                "import json, sys; "
                "from app.core.zaap_shortcuts import update_zaap_shortcuts_field; "
                "from pathlib import Path; "
                "p=Path(sys.argv[1]); field=sys.argv[2]; value=json.loads(sys.argv[3]); "
                "[(update_zaap_shortcuts_field(p, field, value)) for _ in range(15)]"
            )
            commands = (
                [sys.executable, "-c", script, str(path), "zaap_favorites", '["Astrub"]'],
                [sys.executable, "-c", script, str(path), "zaap_button", '{"x_ratio":0.7,"y_ratio":0.8}'],
            )
            children = [subprocess.Popen(command, stderr=subprocess.PIPE) for command in commands]
            for process in children:
                _, stderr = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, stderr.decode(errors="replace"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["zaap_favorites"], ["Astrub"])
            self.assertEqual(payload["zaap_button"], {"x_ratio": 0.7, "y_ratio": 0.8})

    def test_real_storage_setters_use_field_transaction(self) -> None:
        from app import storage

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "shortcuts.json"
            zaaps = [{"name": "Astrub", "search": "Astrub", "label": "Astrub"}]
            storage.save_zaap_favorites(["Astrub"], zaaps=zaaps, path=path)
            storage.save_zaap_button_ratios(0.7, 0.8, path=path)
            self.assertEqual(storage.read_zaap_favorites(zaaps, storage.read_zaap_shortcuts(path)), ["Astrub"])
            self.assertEqual(
                storage.read_zaap_button_ratios(storage.read_zaap_shortcuts(path)),
                (0.7, 0.8),
            )


if __name__ == "__main__":
    unittest.main()
