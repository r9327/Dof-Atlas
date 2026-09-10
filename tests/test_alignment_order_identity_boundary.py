from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services import AchievementProgressService
from app.modules.encyclopedia.services.guide_path_profiles import ORDER_QUEST_IDS


class AlignmentOrderIdentityBoundaryTests(unittest.TestCase):
    def test_new_choice_persists_stable_order_id_not_display_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "achievement_progress.json"
            service = AchievementProgressService(path)
            order_name = "Ordre du Cœur Vaillant"

            service.set_alignment_order_choice("character:1", "bonta", order_name)

            payload = json.loads(path.read_text(encoding="utf-8"))
            choice = payload["characters"]["character:1"]["alignment_order"]
            self.assertEqual(
                choice,
                {
                    "side": "bonta",
                    "order_id": int(ORDER_QUEST_IDS["bonta"][order_name][0]),
                },
            )
            self.assertNotIn("order", choice)
            self.assertEqual(
                AchievementProgressService(path).alignment_order_choice("character:1"),
                ("bonta", order_name),
            )

    def test_legacy_named_choice_remains_readable_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "achievement_progress.json"
            payload = {
                "version": 1,
                "characters": {
                    "character:1": {
                        "alignment_order": {
                            "side": "brakmar",
                            "order": "Ordre de l'Œil Putride",
                        }
                    }
                },
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            before = path.read_bytes()

            service = AchievementProgressService(path)

            self.assertEqual(
                service.alignment_order_choice("character:1"),
                ("brakmar", "Ordre de l'Œil Putride"),
            )
            self.assertEqual(path.read_bytes(), before)

    def test_unknown_order_name_cannot_be_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "achievement_progress.json"
            service = AchievementProgressService(path)

            with self.assertRaises(ValueError):
                service.set_alignment_order_choice(
                    "character:1",
                    "bonta",
                    "Nom arbitraire",
                )

            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
