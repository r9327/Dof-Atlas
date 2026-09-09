from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.constants import KEY_SESSION_ORDER
from app.network.character_resolver import CharacterSlotResolver
from app.quest_catalog import load_quest_characters


class CharacterPidOwnershipTests(unittest.TestCase):
    def test_verified_character_switch_detaches_previous_pid_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile = root / "profiles.json"
            client_index = root / "client_index.json"
            bindings = root / "network_character_bindings.json"

            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: ["dofus_3_6_10_11_release_1"]}),
                encoding="utf-8",
            )
            client_index.write_text(
                json.dumps(
                    {
                        "clients": [
                            {
                                "slot": 1,
                                "character_name": "Dofus 3.6.10.11 Release 1",
                                "pid": 4101,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            resolver = CharacterSlotResolver(
                profile,
                client_index,
                binding_path=bindings,
                slot_count=2,
                progress_paths=(),
            )

            resolver.resolve_for_session("Alice", "tcp:4101:1", 55)
            resolver.resolve_for_session("Bob", "tcp:4101:2", 66)

            connected = load_quest_characters(
                profile,
                client_index,
                2,
                binding_path=bindings,
                connected_only=True,
            )
            payload = json.loads(bindings.read_text(encoding="utf-8"))

            self.assertEqual(
                [(row.key, row.label) for row in connected],
                [("character:66", "Bob")],
            )
            self.assertNotIn("pid", payload["characters"]["55"])
            self.assertEqual(payload["characters"]["66"]["pid"], 4101)


if __name__ == "__main__":
    unittest.main()
