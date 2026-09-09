from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_ultime_runtime_service import GuideUltimeRuntimeService


class _ProgressKeyService(GuideUltimeRuntimeService):
    def __init__(self) -> None:
        self.checked: set[tuple[str, str]] = set()

    def manual_checked(self, character_key: str, key: str) -> bool:
        return (character_key, key) in self.checked

    def set_manual_checked(self, character_key: str, key: str, checked: bool) -> None:
        pair = (character_key, key)
        if checked:
            self.checked.add(pair)
        else:
            self.checked.discard(pair)


class GuideUltimeStableProgressKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _ProgressKeyService()
        self.card = {
            "index": 42,
            "manual_source": True,
            "manual_chapter_id": "astrub",
            "manual_stage_id": "astrub-egouts-prairie",
        }

    def test_manual_card_key_is_stable_across_reordering(self) -> None:
        first = self.service.card_key(self.card, 0)
        reordered = dict(self.card, index=99)
        second = self.service.card_key(reordered, 0)
        self.assertEqual(first, "manual:astrub:astrub-egouts-prairie")
        self.assertEqual(second, first)
        self.assertEqual(self.service.page_key(reordered, 0), "page:manual:astrub:astrub-egouts-prairie")

    def test_legacy_gps_key_is_migrated_lazily(self) -> None:
        character = "slot:1"
        self.service.checked.add((character, "page:gps:42"))

        self.assertTrue(self.service.page_checked(character, self.card, 0))
        self.assertIn((character, "page:manual:astrub:astrub-egouts-prairie"), self.service.checked)
        self.assertNotIn((character, "page:gps:42"), self.service.checked)

    def test_new_manual_key_does_not_depend_on_fallback_index(self) -> None:
        self.assertEqual(
            self.service.card_key(self.card, 1),
            self.service.card_key(self.card, 999),
        )


if __name__ == "__main__":
    unittest.main()
