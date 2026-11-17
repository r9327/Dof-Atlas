"""Source material titles/Quest links are not items; source bytes remain intact."""
import copy
import unittest

from app.modules.encyclopedia.services.guide_source_preparation_rows import (
    authored_material_rows,
)


class SourceMaterialDisplayTests(unittest.TestCase):
    def test_linked_quest_title_is_context_not_object(self):
        blocks = [
            {"type": "paragraph", "runs": [{"text": "Prévoyez les ressources suivantes :",
                                            "role": "plain"}]},
            {"type": "paragraph", "runs": [{"text": "Art gastronomique:", "role": "plain"}]},
            {"type": "paragraph", "runs": [
                {"text": "1 ", "role": "plain"},
                {"text": "Cawotte", "role": "item", "href": "https://example.org/items/1"},
                {"text": " (droppable plus tard)", "role": "plain"},
            ]},
            {"type": "paragraph", "runs": [
                {"text": "L'œuf ou la cawotte ?", "role": "quest",
                 "href": "https://example.org/quests/1"}
            ]},
            {"type": "paragraph", "runs": [
                {"text": "1 ", "role": "plain"},
                {"text": "Couronne du Wa Wabbit", "role": "equipment",
                 "href": "https://example.org/equip/2"},
                {"text": " (HDV ou craft plus tard)", "role": "plain"},
            ]},
        ]
        card = {"manual_preparation_block_indexes": list(range(len(blocks))),
                "manual_runtime_metadata": {"source_step": {
                    "actions": [{"rich_blocks": blocks}]
                }}}
        before = copy.deepcopy(card)
        rows = authored_material_rows([card])
        self.assertEqual([r["kind"] for r in rows],
                         ["context", "context", "item", "context", "equipment"])
        self.assertEqual(
            [(r["name"], r["quantity"]) for r in rows if r["kind"] != "context"],
            [("Cawotte", 1), ("Couronne du Wa Wabbit", 1)],
        )
        self.assertEqual(rows[3]["runs"][0]["role"], "quest")
        self.assertEqual(rows[2]["runs"][-1]["text"], " (droppable plus tard)")
        self.assertEqual(card, before)

    def test_untyped_or_ambiguous_rows_never_become_fabricated_inventory(self):
        blocks = [
            {"type": "checklist", "items": [
                {"id": "a", "text": "10 Cawottes", "checked": False,
                 "runs": [{"text": "10 Cawottes", "role": "plain"}]},
                {"id": "b", "text": "1 équipement X et Y", "checked": False,
                 "runs": [
                    {"text": "1 ", "role": "plain"},
                    {"text": "X", "role": "equipment"},
                    {"text": " et ", "role": "plain"},
                    {"text": "Y", "role": "equipment"},
                ]},
            ]}
        ]
        card = {"manual_preparation_block_indexes": [0],
                "manual_runtime_metadata": {"source_step": {
                    "actions": [{"rich_blocks": blocks}]
                }}}
        rows = authored_material_rows([card])
        self.assertEqual([r["kind"] for r in rows], ["context", "context"])
        self.assertTrue(all("quantity" not in r for r in rows))


    def test_global_rows_merge_same_verified_item_id_without_quest_titles(self):
        blocks = [
            {"type": "paragraph", "runs": [
                {"text": "Quest A", "role": "quest"},
            ]},
            {"type": "paragraph", "runs": [
                {"text": "3 ", "role": "plain"},
                {"text": "Cawotte", "role": "item", "entity_id": 44},
            ]},
            {"type": "paragraph", "runs": [
                {"text": "Quest B", "role": "quest"},
            ]},
            {"type": "paragraph", "runs": [
                {"text": "5 ", "role": "plain"},
                {"text": "Cawotte", "role": "item", "entity_id": 44},
            ]},
            {"type": "paragraph", "runs": [
                {"text": "2 ", "role": "plain"},
                {"text": "Une autre Cawotte", "role": "item", "entity_id": 88},
            ]},
        ]
        card = {"manual_preparation_block_indexes": list(range(len(blocks))),
                "manual_runtime_metadata": {
                    "source_step": {"actions": [{"rich_blocks": blocks}]}
                }}
        before = copy.deepcopy(card)
        from app.modules.encyclopedia.services.guide_source_preparation_rows import (
            global_source_material_rows,
        )
        entries = global_source_material_rows([card])
        self.assertEqual(len(entries), 2)
        self.assertEqual([(r["item_id"], r["quantity"]) for r in entries],
                         [(44, 8), (88, 2)])
        self.assertEqual(card, before)
        self.assertTrue(all("Quest" not in r["name"] for r in entries))

    def test_unknown_amount_never_becomes_complete_count(self):
        blocks = [
            {"type": "paragraph", "runs": [
                {"text": "Cawotte", "role": "item", "entity_id": 44},
            ]},
            {"type": "paragraph", "runs": [
                {"text": "2 ", "role": "plain"},
                {"text": "Cawotte", "role": "item", "entity_id": 44},
            ]},
        ]
        card = {"manual_preparation_block_indexes": [0, 1],
                "manual_runtime_metadata": {
                    "source_step": {"actions": [{"rich_blocks": blocks}]}
                }}
        from app.modules.encyclopedia.services.guide_source_preparation_rows import (
            global_source_material_rows,
        )
        row = global_source_material_rows([card])[0]
        self.assertEqual(row["item_id"], 44)
        self.assertIsNone(row["quantity"])


if __name__ == "__main__":
    unittest.main()
