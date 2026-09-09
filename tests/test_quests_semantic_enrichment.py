from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.tools.audit_quests_guides_semantic import base_result, compare_images, compare_quest_info
from app.modules.encyclopedia.tools.enrich_quests import (
    EXTRACTION_SCHEMA_VERSION,
    build_mapping,
    dedupe_items,
    dpln_mapping_confidence,
    enrichment_row_is_current,
    extract_dpln_page_v2,
    merge_required_items,
    parse_quantity_line,
    source_title_key,
)
from app.quest_catalog import QuestCatalog, QuestRecord, quest_catalog_cache_signature


@dataclass
class FakeQuest:
    id: int
    name: str
    level_min: int = 0
    prerequisites: tuple[str, ...] = ()


class QuestSemanticEnrichmentTests(unittest.TestCase):
    def test_mapping_is_deterministic_and_never_uses_list_position(self):
        quests = [FakeQuest(20, "Beta"), FakeQuest(10, "Alpha")]
        source_a = [{"id": 2, "name": "Beta"}, {"id": 1, "name": "Alpha"}]
        source_b = list(reversed(source_a))
        first = build_mapping(quests, source_a, [], {})["quests"]
        second = build_mapping(quests, source_b, [], {})["quests"]
        self.assertEqual(first["10"]["duffus"][0]["source_row_id"], 1)
        self.assertEqual(first["20"]["duffus"][0]["source_row_id"], 2)
        self.assertEqual(first, second)

    def test_duplicate_local_titles_remain_ambiguous(self):
        mapping = build_mapping(
            [FakeQuest(10, "Meme titre"), FakeQuest(20, "Meme titre")],
            [{"id": 1, "name": "Meme titre"}],
            [],
            {"meme-titre": "https://www.dofuspourlesnoobs.com/meme-titre.html"},
        )["quests"]
        self.assertEqual(mapping["10"]["status"], "ambiguous")
        self.assertEqual(mapping["20"]["status"], "ambiguous")

    def test_live_title_slug_and_level_produce_exact_confidence(self):
        status, signals, conflicts = dpln_mapping_confidence(
            FakeQuest(10, "Quete sure", 80),
            {"slug": "quete-sure"},
            {"title": "Quete sure", "prerequisites": ["Niveau recommande : 80"]},
        )
        self.assertEqual(status, "EXACT")
        self.assertIn("normalized_title_exact", signals)
        self.assertIn("generated_slug_exact", signals)
        self.assertIn("recommended_level_compatible", signals)
        self.assertEqual(conflicts, [])

    def test_title_collision_or_divergence_is_not_auto_accepted(self):
        status, _signals, conflicts = dpln_mapping_confidence(
            FakeQuest(10, "Quete locale", 80),
            {"slug": "quete-locale"},
            {"title": "Autre quete", "prerequisites": []},
        )
        self.assertEqual(status, "AMBIGUOUS")
        self.assertIn("source_title_mismatch", conflicts)

    def test_ligature_and_ascii_spelling_share_the_same_title_key(self):
        self.assertEqual(source_title_key("Coeur et oeuf"), source_title_key("Cœur et œuf"))

    def test_quantity_parser_rejects_prose_with_multiple_items(self):
        self.assertEqual(parse_quantity_line("3 x Cerise"), {"name": "Cerise", "quantity": 3, "source_text": "3 x Cerise"})
        self.assertIsNone(parse_quantity_line("Prevoir 1 x Pandneken et 1 x Alcool, puis 1 x Epice"))

    def test_duplicate_evidence_does_not_double_quantity(self):
        rows = dedupe_items([{"name": "Cerise", "quantity": 5}, {"name": "Cerise", "quantity": 5}])
        self.assertEqual(rows[0]["quantity"], 5)
        merged = merge_required_items(
            [{"name": "Cerise", "quantity": 5, "source": "dpln"}],
            [{"name": "Cerise", "quantity": 5, "source": "duffus"}],
        )
        self.assertEqual(merged, [{"name": "Cerise", "quantity": 5, "source": "dpln"}])

    def test_ordered_extraction_keeps_image_with_quest_blocks(self):
        html = b"""
        <html><head><title>Quete image</title><meta property="og:title" content="Quete image"></head>
        <body><div id="wsite-content">
        <p>Prerequis :</p><li>Niveau recommande : 50</li>
        <p>Parlez au gardien en [1,2].</p>
        <img src="/uploads/1/3/0/1/13010384/capture.jpg" alt="Capture quete image">
        <p>Retournez voir le gardien.</p>
        </div></body></html>
        """
        extracted = extract_dpln_page_v2(html, "https://www.dofuspourlesnoobs.com/quete-image.html", "Quete image")
        self.assertEqual(extracted["title"], "Quete image")
        self.assertEqual([block.block_type for block in extracted["blocks"]], ["position", "image", "text"])
        self.assertTrue(extracted["blocks"][1].source_url.endswith("capture.jpg"))

    def test_missing_dpln_images_are_not_reported_ok(self):
        status, recall, _reason = compare_images({"solution_steps": []}, {"https://example.test/a.jpg"})
        self.assertEqual(status, "IMAGE_MISSING")
        self.assertEqual(recall, 0.0)

    def test_legacy_enrichment_row_is_invalidated(self):
        self.assertFalse(enrichment_row_is_current({"quest_id": 1}))
        self.assertTrue(enrichment_row_is_current({"quest_id": 1, "extraction_version": EXTRACTION_SCHEMA_VERSION}))

    def test_pipeline_migration_is_not_counted_as_semantic_correction(self):
        row = base_result(
            FakeQuest(10, "Quete sure", 80),
            {"status": "matched", "dofus_pour_les_noobs": [{"url": "https://example.test/quete.html"}]},
            {"extraction_version": EXTRACTION_SCHEMA_VERSION, "source": "dofus_pour_les_noobs"},
        )
        self.assertEqual(row["technical_migration"], "dpln_v2_pipeline")
        self.assertEqual(row["correction"], "none")

    def test_quest_info_requires_structured_source_evidence(self):
        unknown, _reason = compare_quest_info({}, [{"flags": {}}])
        self.assertEqual(unknown, "QUEST_INFO_UNKNOWN")
        partial, _reason = compare_quest_info({}, [{"flags": {"combat": True}}])
        self.assertEqual(partial, "QUEST_INFO_PARTIAL")
        ok, _reason = compare_quest_info(
            {"solution_blocks": [{"flags": {"combat": True}}]},
            [{"flags": {"combat": True}}],
        )
        self.assertEqual(ok, "QUEST_INFO_OK")

    def test_catalog_cache_signature_changes_with_raw_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "quests.json").write_text(json.dumps({"data": []}), encoding="utf-8")
            before = quest_catalog_cache_signature(root)
            (root / "quests.json").write_text(json.dumps({"data": [{"id": 1}]}), encoding="utf-8")
            after = quest_catalog_cache_signature(root)
            self.assertNotEqual(before, after)

    def test_guides_reuse_the_primary_quest_provider_without_solution_copy(self):
        catalog = QuestCatalog(
            [QuestRecord(id=1, name="Unique", category="Test", level_min=1, level_max=1, start_criterion="")]
        )
        quest_provider = QuestProvider(catalog=catalog)
        achievement_provider = AchievementProvider(quest_provider=quest_provider)
        guide_provider = GuideProvider(quest_provider=quest_provider, achievement_provider=achievement_provider)
        self.assertIs(guide_provider.quest_provider, quest_provider)
        self.assertIs(guide_provider.quest_provider.get_catalog(), catalog)
        forbidden = {"solution", "solution_steps", "solution_blocks", "source_solution_steps"}
        for path in (Path("data") / "encyclopedia" / "guides").glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            stack = [payload]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    self.assertTrue(forbidden.isdisjoint(value), f"Donnee quete dupliquee dans {path}")
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)


if __name__ == "__main__":
    unittest.main()
