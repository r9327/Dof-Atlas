"""Focused authored guide copy-link contract; does not certify gameplay."""
from __future__ import annotations

import json
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDES_DIR = ROOT / "data" / "encyclopedia" / "guides"


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


class GanymedeCopyLinksTests(unittest.TestCase):
    @staticmethod
    def _render(step):
        from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView

        return GuideCatalogView._format_offline_instruction_rich(step, 1, 1)

    def test_every_position_and_explicit_item_is_individually_copyable(self):
        step = {
            "title": "Exemple",
            "instructions": "Ceci est une consigne hors ligne.",
            "actions": [
                {"kind": "travel", "text": "Première carte", "coordinates": [13, 26]},
                {"kind": "travel", "text": "Deuxième carte", "coordinates": [-46, 18]},
                {"kind": "prepare", "text": "Rassembler les objets", "copy_values": [
                    "Gros Boulet", "Huile de Sésame",
                ]},
                {"kind": "talk", "text": "Parler au capitaine",
                 "copy_values": ["Capitaine Kradoc"]},
            ],
        }
        html, targets = self._render(step)
        self.assertEqual(targets, (
            "/travel 13,26", "/travel -46,18",
            "Gros Boulet", "Huile de Sésame", "Capitaine Kradoc",
        ))
        links = _Links()
        links.feed(html)
        self.assertEqual(links.hrefs, [
            "copy:0", "copy:1", "copy:2", "copy:3", "copy:4",
        ])
        self.assertIn("[13,26]", html)
        self.assertIn("font-weight:700", html)

    def test_rendering_escapes_markup_and_rejects_unspecified_targets(self):
        step = {
            "title": "<script>",
            "instructions": "<img src=x onerror=bad()>",
            "actions": [
                {"kind": "talk", "text": "<a href='https://evil.test'>hello</a>",
                 "copy_values": ["Roi & Reine", "", 42]},
                {"kind": "prepare", "text": "Aucune copie spéculative",
                 "copy_values": "Cette valeur invalide doit être ignorée"},
            ],
        }
        html, targets = self._render(step)
        self.assertEqual(targets, ("Roi & Reine",))
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img src=x onerror=bad()&gt;", html)
        self.assertNotIn("https://evil.test", html.replace(
            "&#x27;https://evil.test&#x27;", "",
        ))
        self.assertNotIn("<script>", html)
        links = _Links()
        links.feed(html)
        self.assertEqual(links.hrefs, ["copy:0"])

    def test_copy_strip_does_not_duplicate_reader_text(self):
        from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView

        step = {
            "title": "Étape originale",
            "instructions": "Description complète hors ligne",
            "actions": [
                {"kind": "travel", "text": "Plusieurs cartes",
                 "coordinates": [24, -3]},
                {"kind": "talk", "text": "Questionner le marin",
                 "copy_values": ["Capitaine Kradoc"]},
                {"kind": "information", "text": "Aucune copie inventée"},
            ],
        }
        html, targets = GuideCatalogView._format_offline_instruction_rich(
            step, 1, 7, links_only=True,
        )
        self.assertNotIn("Étape originale", html)
        self.assertNotIn("Description complète hors ligne", html)
        self.assertNotIn("Plusieurs cartes", html)
        self.assertNotIn("Aucune copie inventée", html)
        self.assertIn("Copier :", html)
        self.assertEqual(targets, ("/travel 24,-3", "Capitaine Kradoc"))
        links = _Links()
        links.feed(html)
        self.assertEqual(links.hrefs, ["copy:0", "copy:1"])

    def test_otomai_one_contains_explicit_targets_without_certificate(self):
        data = json.loads(
            (GUIDES_DIR / "ganymede_2219_instructions.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertEqual(data["source_guide_id"], 2219)
        self.assertEqual(len(data["steps"]), 7)
        self.assertIs(data["source_parity_certified"], False)
        self.assertIs(data["gameplay_certified"], False)
        pages = [
            self._render({"title": step["title"], "instructions": step["instructions"],
                          "actions": step["actions"]})
            for step in data["steps"]
        ]
        all_targets = [value for _html, targets in pages for value in targets]
        self.assertIn("Capitaine Kradoc", all_targets)
        self.assertIn("Flip Flap", all_targets)
        self.assertIn("Spitte Fayeur", all_targets)
        self.assertIn("Miséricorde du Chafer d'Élite", all_targets)
        self.assertIn("Dragodinde Amande", all_targets)
        self.assertIn("Casque amélioré", all_targets)
        self.assertEqual(
            sum(value.startswith("/travel ") for value in all_targets), 9,
        )


if __name__ == "__main__":
    unittest.main()
