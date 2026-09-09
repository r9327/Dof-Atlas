from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from app.constants import KEY_SELECTED_CHARACTER
from app.services.profile_settings_service import ProfileSettingsService


class ProfileSettingsServiceTests(unittest.TestCase):
    def test_independent_writers_preserve_each_others_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "profiles.json"
            profile_path.write_text(
                json.dumps(
                    {
                        KEY_SELECTED_CHARACTER: "character:101",
                        "__topmost__": False,
                        "__switch_click__": False,
                    }
                ),
                encoding="utf-8",
            )
            writer_a = ProfileSettingsService(profile_path)
            writer_b = ProfileSettingsService(profile_path)

            stale_b = writer_b.load()
            self.assertEqual(stale_b[KEY_SELECTED_CHARACTER], "character:101")

            writer_a.set_selected_character("character:202")
            writer_b.update_values({"__switch_click__": True})

            final = writer_a.load()
            self.assertEqual(final[KEY_SELECTED_CHARACTER], "character:202")
            self.assertTrue(final["__switch_click__"])
            self.assertFalse(final["__topmost__"])

    def test_concurrent_targeted_mutations_do_not_lose_independent_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "profiles.json"
            profile_path.write_text("{}", encoding="utf-8")
            writer_a = ProfileSettingsService(profile_path)
            writer_b = ProfileSettingsService(profile_path)
            barrier = threading.Barrier(3)
            errors: list[BaseException] = []

            def mutate(service: ProfileSettingsService, key: str, value: object) -> None:
                try:
                    barrier.wait(timeout=5)
                    service.set_value(key, value)
                except BaseException as exc:  # pragma: no cover - asserted below
                    errors.append(exc)

            thread_a = threading.Thread(
                target=mutate,
                args=(writer_a, "writer_a", "kept"),
                daemon=True,
            )
            thread_b = threading.Thread(
                target=mutate,
                args=(writer_b, "writer_b", 42),
                daemon=True,
            )
            thread_a.start()
            thread_b.start()
            barrier.wait(timeout=5)
            thread_a.join(timeout=5)
            thread_b.join(timeout=5)

            self.assertFalse(thread_a.is_alive())
            self.assertFalse(thread_b.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(
                writer_a.load(),
                {"writer_a": "kept", "writer_b": 42},
            )

    def test_rapid_mutations_reload_latest_disk_state_each_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "profiles.json"
            profile_path.write_text("{}", encoding="utf-8")
            writer_a = ProfileSettingsService(profile_path)
            writer_b = ProfileSettingsService(profile_path)

            for index in range(20):
                writer_a.set_value("selected_revision", index)
                writer_b.set_value("organizer_revision", index * 10)

            self.assertEqual(
                writer_a.load(),
                {"selected_revision": 19, "organizer_revision": 190},
            )


if __name__ == "__main__":
    unittest.main()
