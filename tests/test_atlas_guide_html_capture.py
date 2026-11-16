"""Offline tests: full source step HTML -> one exact Atlas card, no fake text."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from app.modules.encyclopedia.services.guide_shared_route_contract import (
    assert_source_fidelity,
)
from tools.atlas_guide_html_capture import (
    SourceCaptureError, convert_manifest, extract_saved_html,
)
from tools.atlas_guide_importer import prepare_preview


STEP_ONE = """<!doctype html><main>
<article id="step-1"><h2>Step 1 <span>[25,-4]</span></h2>
  <div class="mt-5 guide-content">
    <p>Ouvrir la première page du guide fictif.</p>
    <p>Parler au <a href="https://example.org/quest/827">
    <span data-type="custom-tag" type="quest" dofusdbid="827">
    <img src="https://example.org/icon.png" alt="quest"><span>PNJ de test</span>
    </span></a>.</p>
    <ul data-type="taskList">
      <li data-checked="false" data-type="taskItem">
        <label><input type="checkbox"><span></span></label>
        <div><p>Vérifier <a href="https://example.org/object/10">
        <span data-type="custom-tag" type="item" dofusdbid="10">
        <img src="https://example.org/item.png" alt="item"><span>Objet fictif</span>
        </span></a>.</p></div>
      </li>
    </ul>
    <p>Ne pas résumer la dernière phrase.</p>
  </div>
</article></main>"""

STEP_TWO = """<main><article id="step-2"><h2>Step 2 [-1,2]</h2>
  <div class="guide-content">
    <p>Se rendre à la deuxième fiche.</p><p>Action supplémentaire.</p>
  </div>
</article></main>"""

STEP_TWO_WITH_MEDIA = """<article id="step-2"><h2>Step 2 [-1,2]</h2>
<div class="guide-content">
  <p>Se rendre à la deuxième fiche.</p>
  <p><img src="https://example.org/photo.png" alt="Illustration fictive"></p>
  <p>Action supplémentaire.</p>
</div></article>"""

# Tiny fictional PNG fixture. Not third-party guide artwork.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9eIcyRoAAAAASUVORK5CYII="
)


class AtlasGuideHtmlCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "one.html").write_text(STEP_ONE, encoding="utf-8")
        (self.root / "two.html").write_text(STEP_TWO, encoding="utf-8")
        self.manifest = {
            "rights_verified": True,
            "reference_verified": True,
            "guides": [{
                "guide_id": "fictional", "title": "Parcours fictif",
                "expected_steps": 2, "pages": ["one.html", "two.html"],
            }],
        }

    def test_two_full_source_fiches_become_two_ordered_atlas_cards(self):
        before = copy.deepcopy(self.manifest)
        source = convert_manifest(self.manifest, root=self.root)
        self.assertEqual(self.manifest, before)
        self.assertEqual(len(source["guides"]), 1)
        guide = source["guides"][0]
        self.assertEqual([s["source_step_id"] for s in guide["steps"]],
                         ["step-0001", "step-0002"])
        self.assertEqual(guide["steps"][0]["coordinates"], [25, -4])
        self.assertEqual(guide["steps"][1]["coordinates"], [-1, 2])
        first_action = guide["steps"][0]["actions"][0]
        self.assertEqual(first_action["text"],
                         "Ouvrir la première page du guide fictif.")
        blocks = first_action["rich_blocks"]
        self.assertEqual([b["type"] for b in blocks],
                         ["paragraph", "paragraph", "checklist", "paragraph"])
        self.assertEqual(
            blocks[2]["items"][0]["text"].strip(),
            "Vérifier Objet fictif.",
        )
        self.assertTrue(any(
            run.get("role") == "item" and run.get("href") ==
            "https://example.org/object/10"
            for run in blocks[2]["items"][0]["runs"]
        ))
        self.assertEqual(blocks[-1]["runs"][0]["text"],
                         "Ne pas résumer la dernière phrase.")
        self.assertEqual(guide["steps"][0]["actions"][0]["action_id"],
                         "authored-page-content")
        self.assertEqual(guide["steps"][1]["actions"][0]["action_id"],
                         "authored-page-content")
        route = prepare_preview(source, expected_guides=1,
                                expected_steps=2, partial=True)
        self.assertEqual(route["step_count"], 2)
        self.assertEqual(route["action_count"], 2)
        self.assertFalse(route["certified"])
        assert_source_fidelity(guide, route["routes"][0])
        self.assertEqual(
            route["routes"][0]["steps"][0]["manual_source_action_order"],
            ["authored-page-content"],
        )

    def test_incomplete_paginated_capture_must_fail_not_summarize(self):
        self.manifest["guides"][0]["pages"] = ["one.html"]
        with self.assertRaisesRegex(SourceCaptureError, "incomplete paginated capture: 1/2"):
            convert_manifest(self.manifest, root=self.root)

    def test_full_inventory_requires_95_guides_and_7705_real_pages(self):
        self.manifest["complete_inventory"] = True
        with self.assertRaisesRegex(SourceCaptureError, "full inventory incomplete"):
            convert_manifest(self.manifest, root=self.root)

    def test_duplicate_guide_source_ids_are_blocking(self):
        self.manifest["guides"].append(copy.deepcopy(self.manifest["guides"][0]))
        with self.assertRaisesRegex(SourceCaptureError, "duplicate guide ID"):
            convert_manifest(self.manifest, root=self.root)

    def test_gapped_or_duplicate_steps_are_blocking(self):
        self.manifest["guides"][0]["pages"] = ["two.html", "one.html"]
        with self.assertRaisesRegex(SourceCaptureError, "missing/duplicate/reordered"):
            convert_manifest(self.manifest, root=self.root)
        self.manifest["guides"][0]["pages"] = ["one.html", "one.html"]
        with self.assertRaisesRegex(SourceCaptureError, "missing/duplicate/reordered"):
            convert_manifest(self.manifest, root=self.root)

    def test_checklist_links_and_decorative_icons_are_preserved(self):
        steps = extract_saved_html(STEP_ONE)
        self.assertEqual(len(steps), 1)
        blocks = steps[0]["step"]["actions"][0]["rich_blocks"]
        paragraphs = blocks[1]["runs"]
        self.assertTrue(any(
            run["text"] == "PNJ de test"
            and run["role"] == "quest"
            for run in paragraphs
        ))
        self.assertNotIn("icon.png", json.dumps(blocks))

    def test_semantic_media_is_embedded_by_verified_explicit_sidecar(self):
        (self.root / "two.html").write_text(STEP_TWO_WITH_MEDIA, encoding="utf-8")
        (self.root / "photo.png").write_bytes(PNG)
        self.manifest["guides"][0]["media_files"] = {
            "https://example.org/photo.png": "photo.png",
        }
        source = convert_manifest(self.manifest, root=self.root)
        blocks = source["guides"][0]["steps"][1]["actions"][0]["rich_blocks"]
        self.assertEqual([block["type"] for block in blocks],
                         ["paragraph", "image", "paragraph"])
        self.assertEqual(blocks[1]["sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(base64.b64decode(blocks[1]["data_base64"]), PNG)

    def test_missing_media_must_fail_not_discard_source_image(self):
        (self.root / "two.html").write_text(STEP_TWO_WITH_MEDIA, encoding="utf-8")
        with self.assertRaisesRegex(SourceCaptureError, "missing local authorized asset"):
            convert_manifest(self.manifest, root=self.root)

    def test_unsupported_embedded_interaction_is_blocked(self):
        (self.root / "two.html").write_text(
            STEP_TWO.replace("<p>Action supplémentaire.</p>",
                             '<iframe src="https://example.org/widget"></iframe>'),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(SourceCaptureError, "unsupported guide element"):
            convert_manifest(self.manifest, root=self.root)

    def test_missing_rights_or_reference_proof_never_claims_import(self):
        for name in ("rights_verified", "reference_verified"):
            with self.subTest(name=name):
                source = copy.deepcopy(self.manifest)
                source[name] = False
                with self.assertRaisesRegex(SourceCaptureError, "rights/reference"):
                    convert_manifest(source, root=self.root)

    def test_media_traversal_or_missing_page_is_blocking(self):
        self.manifest["guides"][0]["pages"] = ["../outside.html"]
        with self.assertRaisesRegex(SourceCaptureError, "path escapes"):
            convert_manifest(self.manifest, root=self.root)
        self.manifest["guides"][0]["pages"] = ["missing.html"]
        with self.assertRaisesRegex(SourceCaptureError, "missing or oversized"):
            convert_manifest(self.manifest, root=self.root)


if __name__ == "__main__":
    unittest.main()
