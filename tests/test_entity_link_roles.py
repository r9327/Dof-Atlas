"""Regression tests for the one UI-wide, Qt-free entity link contract."""
from __future__ import annotations

import unittest

from app.ui.entity_link_roles import (
    ENTITY_LINK_COLOR_ROLES,
    GUIDE_ENTITY_LINK_ROLES,
    entity_link_colors,
    entity_link_markup,
    entity_text_markup,
)


class EntityLinkRolesTests(unittest.TestCase):
    def setUp(self) -> None:
        # Each category uses an existing role; overrides should flow everywhere.
        self.palette = {
            role: f"#{index + 1:06x}"
            for index, role in enumerate(dict.fromkeys(ENTITY_LINK_COLOR_ROLES.values()))
        }

    def test_one_shared_category_index_no_guide_copy(self) -> None:
        self.assertIs(GUIDE_ENTITY_LINK_ROLES, ENTITY_LINK_COLOR_ROLES)
        self.assertEqual(
            set(ENTITY_LINK_COLOR_ROLES),
            {"monster", "boss", "item", "equipment", "npc", "position", "quest"},
        )
        self.assertEqual(
            set(entity_link_colors(self.palette)), set(ENTITY_LINK_COLOR_ROLES),
        )

    def test_palette_overrides_propagate_without_new_markup_rules(self) -> None:
        for category, role in ENTITY_LINK_COLOR_ROLES.items():
            with self.subTest(category=category):
                html = entity_link_markup("Essai", category, "dev-preview:essai", self.palette)
                self.assertIn(f"color:{self.palette[role]}", html)
                self.assertIn('href="dev-preview:essai"', html)
                updated = dict(self.palette, **{role: "#abcdef"})
                self.assertIn("color:#abcdef", entity_link_markup(
                    "Essai", category, "dev-preview:essai", updated,
                ))

    def test_html_escaped_without_changing_link_action(self) -> None:
        result = entity_link_markup("L'Ortie <test> & \"Bottes\"", "equipment",
                                    'item-copy:a&b"c', self.palette)
        self.assertIn("L&#x27;Ortie &lt;test&gt; &amp; &quot;Bottes&quot;", result)
        self.assertIn('href="item-copy:a&amp;b&quot;c"', result)
        self.assertIn("text-decoration:none;", result)
        plain = entity_text_markup('PNJ <test> &', "npc", self.palette)
        self.assertIn("PNJ &lt;test&gt; &amp;", plain)
        self.assertNotIn("<a ", plain)

    def test_unknown_categories_fail_closed(self) -> None:
        with self.assertRaises(KeyError):
            entity_link_markup("Inconnu", "unknown", "guess:123", self.palette)
        with self.assertRaises(KeyError):
            entity_text_markup("Inconnu", "unknown", self.palette)


if __name__ == "__main__":
    unittest.main()
