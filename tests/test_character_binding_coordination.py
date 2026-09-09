from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from app.network.character_resolver import CharacterSlotResolver, _BINDING_LOCK
from app.services.character_data_service import (
    CharacterDataService,
    _NETWORK_BINDING_LOCK,
)


class CharacterBindingCoordinationTests(unittest.TestCase):
    @staticmethod
    def _write_progress(path: Path) -> None:
        path.write_text(
            json.dumps({"version": 1, "characters": {}}),
            encoding="utf-8",
        )

    def test_network_update_and_character_delete_share_one_binding_lock(self) -> None:
        self.assertIs(_NETWORK_BINDING_LOCK, _BINDING_LOCK)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_path = root / "profiles.json"
            client_index_path = root / "client_index.json"
            binding_path = root / "network_character_bindings.json"
            quest_path = root / "quest_progress.json"
            achievement_path = root / "achievement_progress.json"
            guide_path = root / "guide_progress.json"

            profile_path.write_text("{}", encoding="utf-8")
            client_index_path.write_text(
                json.dumps(
                    {
                        "clients": [
                            {"pid": 111, "slot": 5, "name": "Dofus"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            binding_path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "characters": {
                            "202": {
                                "name": "Bravo",
                                "pid": 222,
                                "source": "verified_network_identity",
                            }
                        },
                        "legacy_slots": {
                            "8": {
                                "name": "Historic",
                                "source": "verified_network_identity",
                            }
                        },
                        "slots": {
                            "3": {
                                "name": "LegacyMapped",
                                "character_id": 303,
                                "source": "verified_network_identity",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            for path in (quest_path, achievement_path, guide_path):
                self._write_progress(path)

            resolver = CharacterSlotResolver(
                profile_path=profile_path,
                client_index_path=client_index_path,
                binding_path=binding_path,
                progress_paths=(quest_path, achievement_path, guide_path),
            )
            data_service = CharacterDataService(
                profile_path=profile_path,
                binding_path=binding_path,
                quest_progress_path=quest_path,
                achievement_progress_path=achievement_path,
                guide_progress_path=guide_path,
            )

            network_started = threading.Event()
            delete_started = threading.Event()
            network_done = threading.Event()
            delete_done = threading.Event()
            errors: list[BaseException] = []

            def network_writer() -> None:
                network_started.set()
                try:
                    resolution = resolver.resolve_for_session(
                        "Alpha",
                        "tcp:111:1",
                        character_id=101,
                    )
                    self.assertIsNotNone(resolution)
                    self.assertEqual(resolution.character_key, "character:101")
                except BaseException as exc:  # pragma: no cover - asserted below
                    errors.append(exc)
                finally:
                    network_done.set()

            def delete_writer() -> None:
                delete_started.set()
                try:
                    self.assertTrue(data_service.delete_character("character:202"))
                except BaseException as exc:  # pragma: no cover - asserted below
                    errors.append(exc)
                finally:
                    delete_done.set()

            # Holding the canonical network binding lock must block both writer
            # paths. With the former independent ProgressFileCoordinator lock,
            # CharacterDataService could pass this point and race the resolver.
            with _BINDING_LOCK:
                network_thread = threading.Thread(target=network_writer, daemon=True)
                delete_thread = threading.Thread(target=delete_writer, daemon=True)
                network_thread.start()
                delete_thread.start()
                self.assertTrue(network_started.wait(timeout=2))
                self.assertTrue(delete_started.wait(timeout=2))
                self.assertFalse(network_done.wait(timeout=0.05))
                self.assertFalse(delete_done.wait(timeout=0.05))

            network_thread.join(timeout=5)
            delete_thread.join(timeout=5)
            self.assertFalse(network_thread.is_alive())
            self.assertFalse(delete_thread.is_alive())
            self.assertEqual(errors, [])

            final = json.loads(binding_path.read_text(encoding="utf-8"))
            characters = final.get("characters", {})
            self.assertNotIn("202", characters)
            self.assertEqual(characters["101"]["name"], "Alpha")
            self.assertEqual(
                characters["101"]["source"],
                "verified_network_identity",
            )
            # Historical verified slot mapping is migrated, not discarded.
            self.assertEqual(characters["303"]["name"], "LegacyMapped")
            self.assertEqual(
                final.get("legacy_slots", {}).get("8", {}).get("name"),
                "Historic",
            )


if __name__ == "__main__":
    unittest.main()
