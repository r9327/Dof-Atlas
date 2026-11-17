from __future__ import annotations

import unittest

from app.core.entity_identity import canonical_entity_key, parse_entity_key


class CanonicalGuideEntityIdsTests(unittest.TestCase):
    def test_same_numeric_id_never_collides_across_types(self):
        kinds = ("item", "class", "profession", "monster", "boss",
                 "dungeon", "npc", "quest", "achievement", "character")
        keys = tuple(canonical_entity_key(kind, 123) for kind in kinds)
        self.assertEqual(len(set(keys)), len(kinds))
        self.assertEqual(keys[0], "item:123")
        self.assertEqual(keys[-1], "character:123")
        self.assertEqual(tuple(parse_entity_key(key) for key in keys),
                         tuple((kind, 123) for kind in kinds))

    def test_catalog_item_subtypes_share_the_same_item_identity(self):
        for kind in ("object", "resource", "equipment", "potion",
                     "soul_stone", "key"):
            self.assertEqual(canonical_entity_key(kind, 42), "item:42")
        self.assertEqual(canonical_entity_key("success", "18"), "achievement:18")
        self.assertEqual(canonical_entity_key("job", 4), "profession:4")

    def test_invalid_or_ambiguous_ids_are_never_silently_accepted(self):
        for kind, value in (("item", 0), ("item", -1), ("item", True),
                            ("item", 1.2), ("item", ""), ("item", "bad"),
                            ("unexpected", 1)):
            with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                canonical_entity_key(kind, value)
        for key in ("item:0", "item:01", "object:1", "ITEM:1",
                    "item:not-numeric", "item:1:2", "slot:1", "name:potion"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_entity_key(key)


if __name__ == "__main__":
    unittest.main()
