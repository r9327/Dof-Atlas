from __future__ import annotations

import unittest

from app.modules.encyclopedia.tools.verify_quest_visuals_work import (
    canonical_slug,
    duplicate_unique_signals,
    page_content,
    select_confirmed_pages,
    title_similarity,
)


class QuestVisualsWorkVerificationTests(unittest.TestCase):
    def test_encoded_weebly_slug_is_normalized(self) -> None:
        self.assertEqual(canonical_slug("premiegraveres-armes"), "premieres_armes")
        self.assertEqual(canonical_slug("quecirctes"), "quetes")

    def test_plural_source_title_is_a_close_but_not_exact_match(self) -> None:
        score = title_similarity("Squelettes et amulette", "Squelettes et amulettes")
        self.assertGreaterEqual(score, 0.94)
        self.assertLess(score, 1.0)

    def test_page_images_keep_source_order_and_surrounding_passages(self) -> None:
        payload = b"""<html><head><meta property='og:title' content='Quete test'></head><body>
        <div id='wsite-content'><p>Allez en [1,2].</p>
        <img src='/uploads/1/3/0/1/13010384/a_orig.png' alt='A'>
        <p>Parlez au PNJ.</p><img src='/uploads/1/3/0/1/13010384/b.png' alt='B'>
        <p>Terminez.</p></div></body></html>"""
        page = page_content(payload, "https://www.dofuspourlesnoobs.com/test.html", "Quete test")
        self.assertEqual([row["order"] for row in page["images"]], [1, 2])
        self.assertEqual(page["images"][0]["passage_before"], "Allez en [1,2].")
        self.assertEqual(page["images"][0]["passage_after"], "Parlez au PNJ.")
        self.assertEqual(page["images"][1]["passage_before"], "Parlez au PNJ.")
        self.assertEqual(page["images"][1]["passage_after"], "Terminez.")

    def test_content_evidence_selects_current_page_between_exact_title_versions(self) -> None:
        quest = type("Quest", (), {"name": "Premières armes"})()
        pages = [
            {"association": "confirmed_unique_title", "exact_title": True, "content_evidence": []},
            {
                "association": "confirmed_unique_title",
                "exact_title": True,
                "content_evidence": ["bouftou_celeste", "tiboufton_celeste"],
            },
        ]
        select_confirmed_pages(quest, pages)
        self.assertEqual(pages[0]["association"], "rejected_alternative")
        self.assertEqual(pages[1]["association"], "confirmed_unique_title")

    def test_duplicate_variants_keep_only_their_distinctive_signal(self) -> None:
        first = type("Quest", (), {"id": 1, "name": "Même titre", "prerequisites": [], "steps": []})()
        second = type("Quest", (), {"id": 2, "name": "Même titre", "prerequisites": [], "steps": []})()
        first.steps = [
            type(
                "Step",
                (),
                {
                    "name": "",
                    "description": "",
                    "objectives": [type("Objective", (), {"text": "Vaincre x1 Boss Alpha [1,2]"})()],
                },
            )()
        ]
        second.steps = [
            type(
                "Step",
                (),
                {
                    "name": "",
                    "description": "",
                    "objectives": [type("Objective", (), {"text": "Vaincre x1 Boss Bêta [1,2]"})()],
                },
            )()
        ]
        catalog = type("Catalog", (), {"by_id": {1: first, 2: second}})()
        signals = duplicate_unique_signals(first, [1, 2], catalog)
        self.assertIn("boss_alpha", signals)
        self.assertNotIn("[1,2]", signals)

    def test_multipart_title_extensions_are_kept_together(self) -> None:
        quest = type("Quest", (), {"name": "Le monde à l'envers"})()
        pages = [
            {
                "title": f"Le monde à l'envers (partie {part})",
                "association": "rejected_title",
                "content_evidence": ["signal_a", "signal_b"],
                "title_similarity": 0.8,
            }
            for part in (1, 2, 3)
        ]
        select_confirmed_pages(quest, pages)
        self.assertTrue(all(page["association"] == "confirmed_multipart_by_content" for page in pages))


if __name__ == "__main__":
    unittest.main()
