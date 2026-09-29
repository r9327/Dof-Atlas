from __future__ import annotations

import unittest

from tools.ui_lab.registry import LIVE, PLANNED, default_previews


class UiLabRegistryTests(unittest.TestCase):
    def test_preview_keys_are_unique(self) -> None:
        previews = default_previews()
        keys = [preview.key for preview in previews]
        self.assertEqual(len(keys), len(set(keys)))

    def test_live_previews_have_factories_and_planned_previews_do_not(self) -> None:
        previews = default_previews()
        self.assertTrue(any(preview.status == LIVE for preview in previews))
        for preview in previews:
            if preview.status == LIVE:
                self.assertTrue(preview.factory_path)
                self.assertTrue(preview.is_live)
            elif preview.status == PLANNED:
                self.assertIsNone(preview.factory_path)
                self.assertFalse(preview.is_live)
            else:
                self.fail(f"Statut UI Lab inconnu: {preview.status}")

    def test_initial_live_preview_is_the_real_guides_view_adapter(self) -> None:
        live = [preview for preview in default_previews() if preview.is_live]
        self.assertEqual([preview.key for preview in live], ["encyclopedia.guides"])
        self.assertEqual(
            live[0].factory_path,
            "tools.ui_lab.screens:create_guides_preview",
        )
        self.assertEqual(
            live[0].source,
            "app/modules/encyclopedia/views/guides_view.py",
        )


if __name__ == "__main__":
    unittest.main()
