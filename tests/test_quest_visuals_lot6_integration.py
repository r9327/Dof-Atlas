from __future__ import annotations

import unittest

from app.modules.encyclopedia.tools.integrate_quest_visuals_lot6 import (
    actionable_images,
    insert_images_into_existing,
    normalize_orders,
    source_sequence,
)


class QuestVisualsLot6IntegrationTests(unittest.TestCase):
    def test_actionable_images_exclude_shared_and_nonconfirmed_states(self) -> None:
        page = {
            "images": [
                {"source_url": "a", "quest_relevance": "specific", "local_state": "absent_local"},
                {"source_url": "b", "quest_relevance": "shared_or_unassigned", "local_state": "absent_local"},
                {"source_url": "c", "quest_relevance": "specific", "local_state": "connected"},
            ]
        }
        self.assertEqual([row["source_url"] for row in actionable_images(page)], ["a"])

    def test_source_sequence_keeps_text_image_text_order_without_repeating_anchor(self) -> None:
        images = [
            {
                "order": 1,
                "source_url": "a",
                "alt": "A",
                "passage_before": "Avant.",
                "passage_after": "Après.",
            },
            {
                "order": 2,
                "source_url": "b",
                "alt": "B",
                "passage_before": "Après.",
                "passage_after": "Fin.",
            },
        ]
        blocks = source_sequence(images, {"a": "data/a.webp", "b": "data/b.webp"})
        self.assertEqual([block["type"] for block in blocks], ["text", "image", "text", "image", "text"])
        self.assertEqual([block.get("content") for block in blocks if block["type"] == "text"], ["Avant.", "Après.", "Fin."])

    def test_missing_image_is_inserted_before_next_known_source_image(self) -> None:
        existing = [
            {"order": 1, "type": "text", "content": "Passage."},
            {"order": 2, "type": "image", "source_url": "next", "image_path": "data/next.webp"},
        ]
        page = {
            "images": [
                {"order": 1, "source_url": "missing", "local_state": "absent_local", "quest_relevance": "specific"},
                {"order": 2, "source_url": "next", "local_state": "connected", "quest_relevance": "specific"},
            ]
        }
        blocks, added = insert_images_into_existing(existing, page, {"missing": "data/missing.webp"})
        self.assertEqual(added, 1)
        self.assertEqual([block.get("source_url") for block in blocks if block["type"] == "image"], ["missing", "next"])

    def test_normalize_orders_keeps_portable_paths(self) -> None:
        blocks = normalize_orders(
            [
                {"order": 99, "type": "text", "content": "Texte"},
                {"order": 100, "type": "image", "image_path": "data/encyclopedia/images/quests/1/step_01.webp"},
            ]
        )
        self.assertEqual([block["order"] for block in blocks], [1, 2])
        self.assertEqual(blocks[1]["image_path"], "data/encyclopedia/images/quests/1/step_01.webp")


if __name__ == "__main__":
    unittest.main()
