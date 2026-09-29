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

    def test_main_navigation_groups_match_product_shell(self) -> None:
        previews = default_previews()
        groups = {preview.group for preview in previews}
        self.assertTrue(
            {
                "Accueil",
                "Organizer",
                "Encyclopédie",
                "Bestiaire",
                "Outils",
                "Stuffs",
                "Almanax",
                "Tutoriels",
            }.issubset(groups)
        )

        by_group: dict[str, list[str]] = {}
        for preview in previews:
            by_group.setdefault(preview.group, []).append(preview.label)

        self.assertEqual(by_group["Encyclopédie"], ["Guide", "Quêtes", "Succès"])
        self.assertEqual(
            by_group["Bestiaire"],
            ["Donjons", "Monstres", "Archimonstres", "Avis de recherche"],
        )
        self.assertEqual(
            by_group["Outils"],
            ["Crafts", "Map monde", "Chasse au trésor", "Ocre"],
        )
        self.assertEqual(by_group["Stuffs"], ["PvM", "PvP", "Builders"])

    def test_current_product_navigation_surfaces_are_live(self) -> None:
        live = {preview.key: preview for preview in default_previews() if preview.is_live}
        required = {
            "home",
            "organizer",
            "encyclopedia.guides",
            "encyclopedia.quests",
            "encyclopedia.achievements",
            "bestiary.dungeons",
            "bestiary.monsters",
            "bestiary.archmonsters",
            "bestiary.wanted",
            "tools.crafts",
            "tools.world_map",
            "tools.treasure_hunt",
            "tools.ocre",
            "stuffs.pvm",
            "stuffs.pvp",
            "stuffs.builders",
            "almanax",
            "tutorials.default",
            "tutorials.dofus_noob",
        }
        self.assertTrue(required.issubset(set(live)))

        for key in (
            "encyclopedia.guides",
            "encyclopedia.quests",
            "encyclopedia.achievements",
            "bestiary.dungeons",
            "bestiary.monsters",
            "bestiary.archmonsters",
            "bestiary.wanted",
        ):
            self.assertEqual(
                live[key].source,
                "app/modules/encyclopedia/views/encyclopedia_page.py",
            )

    def test_exact_tab_scenarios_are_declared(self) -> None:
        live = {preview.key: preview for preview in default_previews() if preview.is_live}
        self.assertIn("guide_first", live["encyclopedia.guides"].scenarios)
        self.assertIn("detail_first", live["encyclopedia.quests"].scenarios)
        self.assertIn("detail_first", live["encyclopedia.achievements"].scenarios)
        self.assertIn("target", live["encyclopedia.guides"].scenarios)
        self.assertIn("target", live["encyclopedia.quests"].scenarios)
        self.assertIn("target", live["encyclopedia.achievements"].scenarios)
        self.assertIn("saved_progress", live["home"].scenarios)


if __name__ == "__main__":
    unittest.main()
