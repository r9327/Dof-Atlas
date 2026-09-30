from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    MANUAL_DIR,
    GuideUltimeManualRuntimeService,
)


class _AchievementProgress:
    def __init__(self) -> None:
        self.choice: tuple[str, str] | None = None
        self.writes: list[tuple[str, str, str]] = []

    def alignment_order_choice(self, _character_key: str):
        return self.choice

    def set_alignment_order_choice(
        self,
        character_key: str,
        alignment: str,
        order_name: str,
    ) -> None:
        self.choice = (alignment, order_name)
        self.writes.append((character_key, alignment, order_name))


class GuideUltimeManualBontaOrderTests(unittest.TestCase):
    @staticmethod
    def _service() -> tuple[GuideUltimeManualRuntimeService, _AchievementProgress]:
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.manual_dir = MANUAL_DIR
        progress = _AchievementProgress()
        service.achievement_progress = progress
        return service, progress

    def test_manifest_exposes_the_three_canonical_bonta_orders(self) -> None:
        service, _progress = self._service()

        self.assertEqual(
            service.bonta_order_names(),
            ("Cœur Vaillant", "Œil Attentif", "Esprit Salvateur"),
        )

        routes = service._manual_order_routes()
        self.assertEqual([row["rank"] for row in routes], [20, 40, 60, 80, 100])
        self.assertTrue(all(row.get("options") for row in routes))

    def test_first_order_choice_persists_and_cannot_be_changed(self) -> None:
        service, progress = self._service()
        character_key = "character:42"

        service.set_bonta_order(character_key, "Cœur Vaillant")

        self.assertEqual(service.selected_order_name(character_key), "Cœur Vaillant")
        self.assertEqual(
            progress.writes,
            [(character_key, "bonta", "Cœur Vaillant")],
        )

        service.set_bonta_order(character_key, "Cœur Vaillant")
        self.assertEqual(service.selected_order_name(character_key), "Cœur Vaillant")

        with self.assertRaisesRegex(ValueError, "ne peut plus être changé"):
            service.set_bonta_order(character_key, "Œil Attentif")

        self.assertEqual(service.selected_order_name(character_key), "Cœur Vaillant")

    def test_unknown_order_fails_closed(self) -> None:
        service, progress = self._service()

        with self.assertRaises(ValueError):
            service.set_bonta_order("character:42", "Ordre inventé")

        self.assertIsNone(progress.choice)
        self.assertEqual(progress.writes, [])


if __name__ == "__main__":
    unittest.main()
