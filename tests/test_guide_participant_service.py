from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.constants import KEY_GUIDE_PARTICIPANTS
from app.services.guide_participant_service import GuideParticipantService


class GuideParticipantServiceTests(unittest.TestCase):
    def test_selection_persists_canonical_ids_and_keeps_offline_characters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profiles.json"
            clients = root / "clients.json"
            bindings = root / "bindings.json"
            profile.write_text("{}", encoding="utf-8")
            clients.write_text(
                json.dumps(
                    {
                        "clients": [
                            {"character_name": "Alpha", "pid": 101, "slot": 1}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps(
                    {
                        "characters": {
                            "1": {"name": "Alpha", "pid": 101},
                            "2": {"name": "Beta", "pid": 202},
                        }
                    }
                ),
                encoding="utf-8",
            )
            service = GuideParticipantService(profile, clients, bindings)

            saved = service.save_selected_keys(
                ["character:2", "slot:1", "character:1", "character:2"]
            )

            self.assertEqual(saved, ("character:2", "character:1"))
            self.assertEqual(service.selected_keys(), saved)
            available = {row.key: row.connected for row in service.available_characters()}
            self.assertEqual(available, {"character:1": True, "character:2": False})
            persisted = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted[KEY_GUIDE_PARTICIPANTS],
                ["character:2", "character:1"],
            )

    def test_corrupt_selection_type_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profiles.json"
            profile.write_text(
                json.dumps({KEY_GUIDE_PARTICIPANTS: "character:1"}),
                encoding="utf-8",
            )
            service = GuideParticipantService(
                profile,
                root / "clients.json",
                root / "bindings.json",
            )

            self.assertEqual(service.selected_keys(), ())


if __name__ == "__main__":
    unittest.main()
