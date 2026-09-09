from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.pages.organizer_page as organizer
import app.pages.organizer_icon_cache as icon_cache


class CharacterClassIconResolutionTests(unittest.TestCase):
    def tearDown(self) -> None:
        icon_cache.clear_organizer_icon_cache()

    def test_character_name_resolves_icon_from_exported_slot_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            classes = root / "classes"
            classes.mkdir()
            expected = classes / "pandawa.png"
            expected.write_bytes(b"icon")
            client_index = root / "client_index.json"
            client_index.write_text(
                json.dumps(
                    {
                        "clients": [
                            {
                                "character_name": "Bob",
                                "name": "Bob - Pandawa",
                                "class_key": "pandawa",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(organizer, "CLIENT_INDEX_JSON", client_index),
                patch.object(organizer, "CLASS_ICON_DIRS", (classes,)),
            ):
                self.assertEqual(organizer.dofus_class_key_for_character_name("Bob"), "pandawa")
                self.assertEqual(organizer.class_icon_path_for_window_name("Bob"), expected)

    def test_legacy_client_index_can_infer_class_from_raw_window_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client_index = root / "client_index.json"
            client_index.write_text(
                json.dumps(
                    {
                        "clients": [
                            {
                                "character_name": "Alice",
                                "name": "Alice - Eliotrope",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(organizer, "CLIENT_INDEX_JSON", client_index):
                self.assertEqual(organizer.dofus_class_key_for_character_name("Alice"), "eliotrope")

    def test_duplicate_name_with_conflicting_classes_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client_index = Path(temp_dir) / "client_index.json"
            client_index.write_text(
                json.dumps(
                    {
                        "clients": [
                            {"character_name": "Same", "name": "Same - Iop", "class_key": "iop"},
                            {"character_name": "Same", "name": "Same - Cra", "class_key": "cra"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(organizer, "CLIENT_INDEX_JSON", client_index):
                self.assertIsNone(organizer.dofus_class_key_for_character_name("Same"))

    def test_verified_binding_keeps_class_after_active_clients_are_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client_index = root / "client_index.json"
            bindings = root / "network_character_bindings.json"
            client_index.write_text(
                json.dumps(
                    {
                        "clients": [
                            {
                                "character_name": "Bob",
                                "name": "Bob - Pandawa",
                                "class_key": "pandawa",
                                "handle": 999,
                                "pid": 123,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "slots": {
                            "1": {
                                "name": "Bob",
                                "pid": 123,
                                "source": "verified_network_identity",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(organizer, "CLIENT_INDEX_JSON", client_index),
                patch.object(icon_cache, "NETWORK_CHARACTER_BINDINGS_FILE", bindings),
            ):
                icon_cache.clear_organizer_icon_cache()
                self.assertTrue(icon_cache.preserve_verified_character_classes([]))
                persisted = json.loads(bindings.read_text(encoding="utf-8"))
                self.assertEqual(persisted["slots"]["1"]["class_key"], "pandawa")

                # Organizer's safe startup reset must still be allowed to remove
                # stale handles/PIDs from the active runtime client list.
                client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
                icon_cache.clear_organizer_icon_cache()
                self.assertEqual(icon_cache.cached_dofus_class_key_for_character_name("Bob"), "pandawa")

    def test_verified_binding_and_client_conflict_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client_index = root / "client_index.json"
            bindings = root / "network_character_bindings.json"
            client_index.write_text(
                json.dumps(
                    {
                        "clients": [
                            {"character_name": "Same", "name": "Same - Cra", "class_key": "cra"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps(
                    {
                        "slots": {
                            "1": {
                                "name": "Same",
                                "pid": 100,
                                "source": "verified_network_identity",
                                "class_key": "iop",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(organizer, "CLIENT_INDEX_JSON", client_index),
                patch.object(icon_cache, "NETWORK_CHARACTER_BINDINGS_FILE", bindings),
            ):
                icon_cache.clear_organizer_icon_cache()
                self.assertIsNone(icon_cache.cached_dofus_class_key_for_character_name("Same"))

    def test_live_release_title_can_refresh_verified_binding_class(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client_index = root / "client_index.json"
            bindings = root / "network_character_bindings.json"
            client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
            bindings.write_text(
                json.dumps(
                    {
                        "slots": {
                            "1": {
                                "name": "Alice",
                                "pid": 321,
                                "source": "verified_network_identity",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(organizer, "CLIENT_INDEX_JSON", client_index),
                patch.object(icon_cache, "NETWORK_CHARACTER_BINDINGS_FILE", bindings),
            ):
                icon_cache.clear_organizer_icon_cache()
                self.assertTrue(
                    icon_cache.preserve_verified_character_classes(
                        [{"nom": "Alice - Eliotrope", "hwnd": 10, "pid": 321}]
                    )
                )
                persisted = json.loads(bindings.read_text(encoding="utf-8"))
                self.assertEqual(persisted["slots"]["1"]["class_key"], "eliotrope")


if __name__ == "__main__":
    unittest.main()
