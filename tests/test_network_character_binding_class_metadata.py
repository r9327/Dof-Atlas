from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.character_resolver import CharacterSlotResolver, merge_verified_binding_classes


class NetworkCharacterBindingClassMetadataTests(unittest.TestCase):
    def test_network_refresh_preserves_class_for_same_verified_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binding_path = Path(temp_dir) / "network_character_bindings.json"
            binding_path.write_text(
                json.dumps(
                    {
                        "characters": {
                            "55": {
                                "name": "Bob",
                                "pid": 100,
                                "source": "verified_network_identity",
                                "class_key": "pandawa",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            resolver = CharacterSlotResolver(binding_path=binding_path, progress_paths=())

            resolver.resolve_for_session("Bob", "tcp:200:1", 55)

            payload = json.loads(binding_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["characters"]["55"]["pid"], 200)
            self.assertEqual(payload["characters"]["55"]["class_key"], "pandawa")

    def test_network_refresh_drops_class_when_slot_identity_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binding_path = Path(temp_dir) / "network_character_bindings.json"
            binding_path.write_text(
                json.dumps(
                    {
                        "characters": {
                            "55": {
                                "name": "Bob",
                                "pid": 100,
                                "source": "verified_network_identity",
                                "class_key": "pandawa",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            resolver = CharacterSlotResolver(binding_path=binding_path, progress_paths=())

            resolver.resolve_for_session("Alice", "tcp:300:1", 66)

            payload = json.loads(binding_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["characters"]["66"]["name"], "Alice")
            self.assertNotIn("class_key", payload["characters"]["66"])
            self.assertEqual(payload["characters"]["55"]["class_key"], "pandawa")

    def test_network_refresh_does_not_trust_class_from_unverified_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binding_path = Path(temp_dir) / "network_character_bindings.json"
            binding_path.write_text(
                json.dumps(
                    {
                        "slots": {
                            "1": {
                                "name": "Bob",
                                "pid": 100,
                                "source": "manual",
                                "class_key": "pandawa",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            resolver = CharacterSlotResolver(binding_path=binding_path, progress_paths=())

            resolver.resolve_for_session("Bob", "tcp:200:1", 55)

            payload = json.loads(binding_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["characters"]["55"]["source"], "verified_network_identity")
            self.assertNotIn("class_key", payload["characters"]["55"])

    def test_class_merge_never_creates_unverified_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binding_path = Path(temp_dir) / "network_character_bindings.json"
            binding_path.write_text(
                json.dumps(
                    {
                        "slots": {
                            "1": {"name": "Bob", "pid": 100, "source": "manual"},
                            "2": {"name": "Alice", "pid": 200, "source": "verified_network_identity"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            changed = merge_verified_binding_classes(
                binding_path,
                {"Bob": {"pandawa"}, "Alice": {"eliotrope"}},
                {"pandawa", "eliotrope"},
            )

            self.assertTrue(changed)
            payload = json.loads(binding_path.read_text(encoding="utf-8"))
            self.assertNotIn("class_key", payload["slots"]["1"])
            self.assertEqual(payload["slots"]["2"]["class_key"], "eliotrope")

    def test_class_merge_refuses_duplicate_verified_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binding_path = Path(temp_dir) / "network_character_bindings.json"
            binding_path.write_text(
                json.dumps(
                    {
                        "slots": {
                            "1": {"name": "Same", "pid": 100, "source": "verified_network_identity"},
                            "2": {"name": "Same", "pid": 200, "source": "verified_network_identity"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            changed = merge_verified_binding_classes(
                binding_path,
                {"Same": {"cra"}},
                {"cra"},
            )

            self.assertFalse(changed)
            payload = json.loads(binding_path.read_text(encoding="utf-8"))
            self.assertNotIn("class_key", payload["slots"]["1"])
            self.assertNotIn("class_key", payload["slots"]["2"])

    def test_conflicting_class_candidates_remove_stale_class(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binding_path = Path(temp_dir) / "network_character_bindings.json"
            binding_path.write_text(
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

            changed = merge_verified_binding_classes(
                binding_path,
                {"Same": {"cra"}},
                {"iop", "cra"},
            )

            self.assertTrue(changed)
            payload = json.loads(binding_path.read_text(encoding="utf-8"))
            self.assertNotIn("class_key", payload["slots"]["1"])


if __name__ == "__main__":
    unittest.main()
