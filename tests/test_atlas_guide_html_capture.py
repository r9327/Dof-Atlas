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
    SourceCaptureError, convert_manifest, extract_saved_html, inspect_saved_capture,
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

    def test_any_silent_source_text_drop_is_blocking(self):
        # Cross-check parser output against the original DOM independently,
        # so future HTML/layout changes cannot recreate three-line summaries.
        from unittest.mock import patch
        from tools import atlas_guide_html_capture as capture

        original = capture._blocks

        def faulty_projection(container, assets):
            return original(container, assets)[:-1]

        with patch.object(capture, "_blocks", side_effect=faulty_projection):
            with self.assertRaisesRegex(
                SourceCaptureError, "authored page text differs after capture",
            ):
                extract_saved_html(STEP_ONE)

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

    def test_real_cawotte_html_shapes_are_lossless_and_indexed(self):
        # Fictional prose, but the actual Cawotte HTML structures: relative
        # guide-step link, dungeon glyph, and five authored RGB highlights.
        from app.modules.encyclopedia.services.guide_shared_route_contract import (
            project_authorized_guide,
        )
        source = """<article id="step-1"><h2>Step 1 [25,-4]</h2>
          <div class="guide-content"><p>Fiche fictive.</p>
          <p><span style="color: rgb(98, 172, 255);">Bleu</span>
          <span style="color: rgb(255, 255, 0);">Jaune</span>
          <span style="color: rgb(255, 255, 255);">Blanc</span>
          <span style="color: rgb(5, 160, 69);">Vert</span>
          <span style="color: rgb(250, 0, 0);">Rouge</span></p>
          <p><a href="/guides/3?page=1&amp;stepsPerPage=1">Guide lié</a></p>
          <p><span data-type="custom-tag" type="dungeon"><img
          src="https://example.org/icon-dungeon.png" alt="dungeon">Donjon fictif</span></p>
          </div></article>"""
        result = extract_saved_html(source)
        blocks = result[0]["step"]["actions"][0]["rich_blocks"]
        colors = [run["role"] for run in blocks[1]["runs"]
                  if run["role"].startswith("source-")]
        self.assertEqual(colors, [
            "source-blue", "source-yellow", "source-white",
            "source-green", "source-red",
        ])
        self.assertEqual(
            blocks[2]["runs"][0]["href"],
            "https://ganymede-app.com/guides/3?page=1&stepsPerPage=1",
        )
        self.assertEqual(blocks[3]["runs"][0]["text"], "Donjon fictif")
        self.assertTrue(project_authorized_guide({
            "guide_id": "fictive", "title": "Test",
            "steps": [result[0]["step"]],
        })["steps"])

    def test_source_unknown_color_or_unsafe_link_is_blocked(self):
        for markup, fragment in (
            ('<span style="color: rgb(1, 2, 3);">X</span>',
             "unmapped source text color"),
            ('<a href="//evil.example/attack">X</a>', "unsupported source link"),
            ('<span style="opacity:0.2">X</span>', "unmapped source inline CSS"),
        ):
            with self.subTest(markup=markup):
                html = (
                    '<article id="step-1"><h2>Step 1</h2>'
                    '<div class="guide-content"><p>Premier.</p><p>'
                    + markup + '</p></div></article>'
                )
                with self.assertRaisesRegex(SourceCaptureError, fragment):
                    extract_saved_html(html)

    def test_unlabelled_source_image_keeps_bytes_with_accessible_fallback(self):
        html = STEP_TWO_WITH_MEDIA.replace(
            'alt="Illustration fictive"', 'alt=""',
        )
        (self.root / "two.html").write_text(html, encoding="utf-8")
        (self.root / "photo.png").write_bytes(PNG)
        self.manifest["guides"][0]["media_files"] = {
            "https://example.org/photo.png": "photo.png",
        }
        blocks = convert_manifest(self.manifest, root=self.root)[
            "guides"][0]["steps"][1]["actions"][0]["rich_blocks"]
        self.assertEqual(blocks[1]["type"], "image")
        self.assertEqual(blocks[1]["alt"], "Illustration sans légende source")
        self.assertEqual(blocks[1]["sha256"], hashlib.sha256(PNG).hexdigest())

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


    def test_saved_full_source_inventory_counts_and_lists_missing_images(self):
        # Real Ganymède structure, fictional prose and local image URL.
        (self.root / "two.html").write_text(STEP_TWO_WITH_MEDIA, encoding="utf-8")
        inventory = inspect_saved_capture(self.manifest, root=self.root)
        self.assertEqual(inventory["status"], "INVENTORY_ONLY_NOT_CERTIFIED")
        self.assertEqual(inventory["guides"][0]["steps"], 2)
        self.assertEqual(
            inventory["guides"][0]["missing_media_urls"],
            ["https://example.org/photo.png"],
        )
        self.assertFalse(inventory["certified"])
        self.assertFalse(inventory["text_fidelity_verified"])
        self.assertFalse(inventory["safe_to_activate"])
        with self.assertRaisesRegex(SourceCaptureError, "missing local authorized asset"):
            convert_manifest(self.manifest, root=self.root)
        (self.root / "photo.png").write_bytes(PNG)
        self.manifest["guides"][0]["media_files"] = {
            "https://example.org/photo.png": "photo.png",
        }
        inventory = inspect_saved_capture(self.manifest, root=self.root)
        self.assertEqual(inventory["guides"][0]["missing_media_urls"], [])
        self.assertEqual(len(inventory["guides"][0]["required_media_urls"]), 1)
        self.assertEqual(len(convert_manifest(self.manifest, root=self.root)["guides"][0]["steps"]), 2)

    def test_saved_source_inventory_rejects_missing_pages_and_unverified_rights(self):
        self.manifest["guides"][0]["pages"] = ["two.html", "one.html"]
        with self.assertRaisesRegex(SourceCaptureError, "missing/duplicate/reordered"):
            inspect_saved_capture(self.manifest, root=self.root)
        self.manifest["guides"][0]["pages"] = ["one.html"]
        with self.assertRaisesRegex(SourceCaptureError, "incomplete paginated capture"):
            inspect_saved_capture(self.manifest, root=self.root)
        self.manifest["rights_verified"] = False
        with self.assertRaisesRegex(SourceCaptureError, "rights/reference"):
            inspect_saved_capture(self.manifest, root=self.root)


    def test_explicit_ganymede_prerequisites_appear_as_typed_gates(self):
        # Fictional text with the actual typed Ganymède source DOM grammar.
        page = """<article id="step-1"><h2>Step 1 [25,-4]</h2>
        <div class="guide-content">
         <p>Il est nécessaire d'être niveau 60 pour terminer ce parcours.</p>
         <p>Vous devriez avoir fait le guide
          <a href="https://ganymede-app.com/guides/3">
           <span data-type="guide-step" guideid="3" stepnumber="1"
           >[GP4] Guide de départ</span></a>
          et particulièrement les quêtes suivantes :</p><p></p>
         <ul data-type="taskList">
           <li data-checked="false"><div><p><a href="https://dofusdb.fr/fr/database/quest/827">
             <span data-type="custom-tag" type="quest" dofusdbid="827"
             ><img alt="quest" src="https://example.org/quest.png">Première quête</span>
           </a></p></div></li>
           <li data-checked="false"><div><p><a href="https://dofusdb.fr/fr/database/quest/2193">
             <span data-type="custom-tag" type="quest" dofusdbid="2193"
             ><img alt="quest" src="https://example.org/quest.png">Deuxième quête</span>
           </a></p></div></li>
         </ul>
         <p>Instructions suivantes.</p>
        </div></article>"""
        stage = extract_saved_html(page)[0]["step"]
        gates = stage["prerequisites"]
        self.assertEqual(len(gates), 4)
        self.assertEqual([gate.get("quest_id") for gate in gates], [None, None, 827, 2193])
        self.assertEqual(gates[1]["guide_id"], 3)
        from app.modules.encyclopedia.services.guide_shared_route_contract import (
            project_authorized_guide,
        )
        route = project_authorized_guide({
            "guide_id": "fictional", "title": "Fictional",
            "steps": [stage],
        })
        self.assertEqual(route["steps"][0]["hard_runtime_gates"], gates)
        self.assertEqual(stage["actions"][0]["rich_blocks"][-1]["runs"][0]["text"],
                         "Instructions suivantes.")

    def test_unrelated_checklist_is_not_mislabeled_prerequisite(self):
        page = """<article id="step-1"><h2>Step 1 [1,1]</h2>
        <div class="guide-content"><p>Parlez au PNJ.</p>
        <ul data-type="taskList"><li data-checked="false"><div><p>
          <span data-type="custom-tag" type="quest" dofusdbid="827">
            <img alt="quest" src="https://example.org/i.png">Quête ordinaire
          </span></p></div></li></ul></div></article>"""
        self.assertNotIn("prerequisites", extract_saved_html(page)[0]["step"])


    def test_cawotte_prerequisites_are_indexed_out_of_route_not_deleted(self):
        # Exact structural pattern from the French Wabbit/Cawotte source.
        page = """<article id="step-1"><h2>Step 1 [25,-4]</h2>
          <div class="guide-content">
          <p>Ce guide permet l'obtention d'un dofus fictif.</p>
          <p>Il est nécessaire d'être niveau 60 pour finir ce guide.</p>
          <p>Une information de trajet à conserver.</p>
          <p>Vous devriez avoir fait le guide
          <a href="/guides/3"><span data-type="guide-step" guideid="3">
            Guide de départ</span></a> et particulièrement les quêtes suivantes :</p>
          <ul data-type="taskList">
            <li data-checked="false"><div><p><span data-type="custom-tag"
              type="quest" dofusdbid="827"><img alt="quest" src="https://example.org/q.png"
              >Quête préalable</span></p></div></li>
          </ul>
          <p>Continuer ensuite jusqu'au prochain PNJ.</p>
          </div></article>"""
        captured = extract_saved_html(page)[0]["step"]
        self.assertEqual(captured["prerequisite_block_indexes"], [1, 3, 4])
        from app.modules.encyclopedia.services.guide_shared_route_contract import (
            project_authorized_guide,
        )
        route = project_authorized_guide({
            "guide_id": "fictional", "title": "Fictional",
            "steps": [captured],
        })
        card = route["steps"][0]
        self.assertEqual(card["manual_prerequisite_block_indexes"], [1, 3, 4])
        self.assertEqual(len(card["hard_runtime_gates"]), 3)
        self.assertEqual(
            len(card["manual_runtime_metadata"]["source_step"]["actions"][0]["rich_blocks"]), 6
        )


    def test_explicit_authored_material_section_moves_to_prepare_only(self):
        """The material declaration and item links move, travel stays."""
        html = """<article id="step-1"><h2>Step 1 [25,-4]</h2>
        <div class="guide-content">
        <p>Prévoyez les ressources suivantes :</p>
        <p>Art gastronomique:</p>
        <p>1 <a href="https://example.org/item/1">
          <span data-type="custom-tag" type="item" dofusdbid="1">
          <img alt="item" src="https://example.org/i.png">Cawotte</span></a>
          (droppable plus tard)</p>
        <p>Si vous voulez obtenir le sort, prévoyez 100 Cawotte plus tard.</p>
        <p>Ensuite allez en [24,-3] [zaap:25,-4]</p>
        <p>Parlez au PNJ du village.</p>
        </div></article>"""
        step = extract_saved_html(html)[0]["step"]
        self.assertEqual(step["preparation_block_indexes"], [0, 1, 2, 3])
        self.assertNotIn("prerequisite_block_indexes", step)
        from app.modules.encyclopedia.services.guide_shared_route_contract import (
            project_authorized_guide, assert_source_fidelity,
        )
        guide = {"guide_id": "fictional", "title": "Fixture", "steps": [step]}
        projected = project_authorized_guide(guide)
        assert_source_fidelity(guide, projected)
        self.assertEqual(projected["steps"][0]["manual_preparation_block_indexes"],
                         [0, 1, 2, 3])
        original = projected["steps"][0]["manual_runtime_metadata"]["source_step"]
        self.assertEqual(original["actions"][0]["rich_blocks"][4]["runs"][0]["text"],
                         "Ensuite allez en [24,-3] [zaap:25,-4]")

    def test_equipment_before_ensuite_keeps_dialogue_in_route(self):
        html = """<article id="step-1"><h2>Step 1 [23,-4]</h2>
        <div class="guide-content">
          <p>Parlez au PNJ puis revenez.</p>
          <p>Vérifiez que vous avez les équipements ci-dessous :</p>
          <p>1 <span data-type="custom-tag" type="equipment" dofusdbid="19">
             Couronne du Wa Wabbit</span></p>
          <p>1 <span data-type="custom-tag" type="equipment" dofusdbid="18">
             Bâton du Wa Wabbit</span></p>
          <p>Astuce : prévoyez une cape pour chaque personnage.</p>
          <p>Ensuite allez en [28,-12].</p>
        </div></article>"""
        step = extract_saved_html(html)[0]["step"]
        self.assertEqual(step["preparation_block_indexes"], [1, 2, 3, 4])
        self.assertEqual(len(step["actions"][0]["rich_blocks"]), 6)

    def test_party_gate_keeps_remainder_as_route_action(self):
        html = """<article id="step-1"><h2>Step 1 [22,-10]</h2>
        <div class="guide-content">
        <p>Prévoyez l'aide de <span style="color: rgb(255, 255, 0);">
        3</span> personnages, placez les comme ci-dessous :</p>
        <p>Une fois la grille ouverte, traversez-la.</p>
        </div></article>"""
        step = extract_saved_html(html)[0]["step"]
        lead = step["prerequisite_inline_leads"][0]
        self.assertEqual(lead["block_index"], 0)
        self.assertTrue(lead["prefix"].endswith(", "))
        self.assertEqual(step["prerequisites"][0]["party_size"], 3)
        original = "".join(
            run["text"] for run in step["actions"][0]["rich_blocks"][0]["runs"]
        )
        self.assertTrue(original.startswith(lead["prefix"]))
        self.assertIn("placez les comme ci-dessous", original[len(lead["prefix"]):])
        from app.modules.encyclopedia.services.guide_shared_route_contract import (
            project_authorized_guide, assert_source_fidelity,
        )
        guide = {"guide_id": "party-fixture", "title": "Party",
                 "steps": [step]}
        assert_source_fidelity(guide, project_authorized_guide(guide))

    def test_source_materials_without_typed_link_stay_in_route(self):
        html = """<article id="step-1"><h2>Step 1 [1,1]</h2>
        <div class="guide-content">
         <p>Prévoyez les ressources suivantes :</p>
         <p>Inspectez les ressources au village sans les acheter.</p>
        </div></article>"""
        step = extract_saved_html(html)[0]["step"]
        self.assertNotIn("preparation_block_indexes", step)


    def test_rich_typed_object_id_roundtrip_and_invalid_role_rejected(self):
        html = """<article id="step-1"><h2>Step 1 [1,1]</h2>
        <div class="guide-content"><p>Préparez les objets suivants :</p>
         <p>3 <a href="https://example.org/object/44"><span
          data-type="custom-tag" type="item" dofusdbid="44">Cawotte</span></a></p>
        </div></article>"""
        step = extract_saved_html(html)[0]["step"]
        block = step["actions"][0]["rich_blocks"][1]
        self.assertEqual(block["runs"][-1]["entity_id"], 44)
        from app.modules.encyclopedia.services.guide_shared_route_contract import (
            project_authorized_guide, assert_source_fidelity,
        )
        guide = {"guide_id": "fictional", "title": "Fixture", "steps": [step]}
        result = project_authorized_guide(guide)
        assert_source_fidelity(guide, result)
        self.assertEqual(
            result["steps"][0]["manual_runtime_metadata"]["source_step"]
                ["actions"][0]["rich_blocks"][1]["runs"][-1]["entity_id"], 44
        )
        broken = copy.deepcopy(guide)
        broken["steps"][0]["actions"][0]["rich_blocks"][1]["runs"][-1]["entity_id"] = True
        with self.assertRaises(ValueError):
            project_authorized_guide(broken)


if __name__ == "__main__":
    unittest.main()
