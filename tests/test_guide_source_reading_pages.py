"""No split paragraphs, invented steps or lost source content on resize."""
import copy
import unittest

from app.modules.encyclopedia.services.guide_source_reading_pages import (
    authored_reading_blocks, paginate_authored_blocks, source_page_for_index,
)


def _card(blocks, *, prereq=(), prep=(), inline=()):
    return {
        "manual_runtime_metadata": {"source_step": {
            "actions": [{"rich_blocks": blocks}],
        }},
        "manual_prerequisite_block_indexes": list(prereq),
        "manual_preparation_block_indexes": list(prep),
        "manual_prerequisite_inline_leads": list(inline),
    }


def _p(text, role="plain"):
    return {"type": "paragraph", "runs": [{"role": role, "text": text}]}


class OriginalReadingPagesTests(unittest.TestCase):
    def test_original_64_fiches_are_one_continuous_document_without_fake_steps(self):
        cards = [_card([_p(f"Instruction originale {i}, parlez au personnage."),
                         _p(f"Suite de la phrase {i}, dans le bon ordre.")])
                 for i in range(64)]
        saved = copy.deepcopy(cards)
        authored = authored_reading_blocks(cards)
        self.assertEqual(len(authored), 128)
        pages = paginate_authored_blocks(authored, chars_per_line=80)
        self.assertLess(len(pages), len(cards))
        self.assertGreater(len(pages), 1)
        self.assertEqual([b["block"] for pg in pages for b in pg],
                         [b["block"] for b in authored])
        self.assertEqual(cards, saved)
        self.assertTrue(all(0 <= source_page_for_index(pages, n) < len(pages)
                            for n in range(64)))

    def test_source_sections_are_not_duplicated_or_reordered(self):
        original = [
            _p("Niveau 60 obligatoire."),
            _p("Prévoyez des objets."),
            _p("Parlez au PNJ, puis revenez."),
            {"type": "checklist", "items": [
                {"text": "Quête A", "runs": [{"text": "Quête A", "role": "quest"}]},
                {"text": "Quête B", "runs": [{"text": "Quête B", "role": "quest"}]},
            ]},
            {"type": "image", "alt": "Plan source", "mime": "image/png",
             "data_base64": "original-immutable"},
        ]
        cards = [_card(original, prereq=[0], prep=[1])]
        rows = authored_reading_blocks(cards)
        self.assertEqual([e["block"]["type"] for e in rows],
                         ["paragraph", "checklist_item", "checklist_item", "image"])
        self.assertEqual(rows[1]["block"]["item"]["text"], "Quête A")
        self.assertEqual(rows[2]["block"]["item"]["text"], "Quête B")
        self.assertEqual(len(original), 5)

    def test_inline_requirement_only_moves_its_proven_prefix(self):
        cards = [_card([_p("Prévoyez l'aide de 3 personnages, placez-les ici.")],
                       inline=[{"block_index": 0,
                                "prefix": "Prévoyez l'aide de 3 personnages, "}])]
        original = copy.deepcopy(cards)
        rows = authored_reading_blocks(cards)
        self.assertEqual(rows[0]["block"]["runs"][0]["text"], "placez-les ici.")
        self.assertEqual(cards, original)

    def test_wide_and_narrow_keep_complete_source_sentences(self):
        huge = "Texte original " * 40 + "fin."
        cards = [_card([_p(huge), _p("Deuxième phrase intacte."),
                        _p("Troisième phrase intacte.")])]
        blocks = authored_reading_blocks(cards)
        for width in (35, 68, 120):
            pages = paginate_authored_blocks(blocks, chars_per_line=width)
            self.assertEqual([x for p in pages for x in p], list(blocks))
            self.assertEqual(pages[0][0]["block"]["runs"][0]["text"], huge)
        self.assertGreaterEqual(
            len(paginate_authored_blocks(blocks, chars_per_line=35)),
            len(paginate_authored_blocks(blocks, chars_per_line=120)),
        )

    def test_prerequisite_only_source_card_maps_to_next_readable_page(self):
        blocks = authored_reading_blocks([
            _card([_p("Prérequis")], prereq=[0]),
            _card([_p("Lire le trajet")]),
        ])
        pages = paginate_authored_blocks(blocks, chars_per_line=80)
        self.assertEqual(source_page_for_index(pages, 0), 0)
        self.assertEqual(source_page_for_index(pages, 1), 0)


if __name__ == "__main__":
    unittest.main()
