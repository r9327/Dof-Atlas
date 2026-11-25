from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.tools.audit_quests_guides_semantic import (
    base_result, compare_images, compare_quest_info, local_start_position_coverage,
)
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
    def test_local_only_audit_never_hydrates_guides_successes_or_web(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from app.modules.encyclopedia.tools import audit_quests_guides_semantic as mod

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "local_coverage.json"
            sources = Mock()
            sources.rows.side_effect = lambda path: (
                {10: {"startPosition": [{"mapId": 1}]},
                 20: {"startPosition": [{"mapId": 2}]}}
                if path.name == "quests.json"
                else {1: {"posX": 3, "posY": 4}, 2: {"posX": -5, "posY": 6}}
            )
            sources.mapping.return_value = {
                "10": {
                    "launch_position": {"position": "[3,4]"},
                    "solution_blocks": [
                        {"type": "text", "content": "Parler au PNJ."},
                    ],
                },
                "20": {"solution_blocks": []},
            }
            with (
                patch.object(mod, "DEFAULT_LOCAL_COVERAGE", output),
                patch("app.quest_catalog_details.load_quest_ids", return_value=(10, 20)),
                patch.object(mod, "QuestProvider",
                             side_effect=AssertionError("must not hydrate Quest catalog")),
                patch.object(mod, "GuideProvider",
                             side_effect=AssertionError("must stay local")),
                patch.object(mod, "AchievementProvider",
                             side_effect=AssertionError("must stay light")),
                patch.object(mod, "build_audit",
                             side_effect=AssertionError("must skip full audit")),
                patch.object(mod, "read_json_file",
                             side_effect=AssertionError("must not eagerly load enriched JSON")),
                patch.object(mod, "QuestSources", return_value=sources),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(mod.main([
                    "--local-coverage-only",
                    "--online", "full",
                ]), 0)
            self.assertNotEqual(output, mod.DEFAULT_JSON)
            sources.mapping.assert_called_once_with(
                mod.ENRICHED_PATH, "quests", required=True,
            )
            self.assertEqual(sources.rows.call_count, 2)
            sources.close.assert_called_once_with()
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["scope"], "LOCAL_QUEST_STARTS_AND_INSTRUCTIONS")
            self.assertEqual(payload["evidence"], "LOCAL_ENRICHMENT_ONLY_NOT_GAME_VERIFIED")
            self.assertEqual(payload["quests_considered"], 2)
            self.assertEqual(payload["counts"]["LOCAL_START_DECLARED"], 1)
            self.assertEqual(payload["counts"]["NO_DECLARED_START"], 1)
            self.assertEqual(payload["counts"]["WITHOUT_TEXTUAL_SOLUTION_BLOCKS"], 1)
            self.assertEqual(payload["missing_instruction_quest_ids"], [20])
            self.assertEqual(payload["priority_missing_both_quest_ids"], [20])
            native = payload["native_start_coverage"]
            self.assertEqual(native["quests_considered"], 2)
            self.assertEqual(native["counts"]["NATIVE_START_DECLARED"], 2)
            self.assertEqual(native["recovered_from_native_map_quest_ids"], [20])
            self.assertEqual(native["needs_review"], [])
            self.assertEqual(
                payload["needs_review"],
                [{"quest_id": 20, "status": "NO_DECLARED_START"}],
            )

    def test_native_start_audit_separates_recovered_conflicting_and_unresolved_ids(self):
        from app.modules.encyclopedia.tools.audit_quests_guides_semantic import native_start_coverage

        rows = {
            "1": {"source_meta": {"startCoords": "[9,9]"}},
            "2": {"native_start": {"map_id": 10, "position": "[1,2]"}},
            "4": {"launch_position": {"position": "[7,8]"}},
            "5": {"source_meta": {"startCoords": "[1,2]"}},
        }
        quests = {
            1: {"startPosition": [{"mapId": 10}]},
            3: {"startPosition": [{"mapId": 10}]},
            5: {"startPosition": [{"mapId": 10}]},
            6: {"startPosition": [{"mapId": 10}, {"mapId": 11}]},
        }
        maps = {10: {"posX": 1, "posY": 2}, 11: {"posX": 3, "posY": 4}}
        report = native_start_coverage(rows, range(1, 7), quests, maps)
        self.assertEqual(report["quests_considered"], 6)
        self.assertEqual(report["counts"]["WITH_UNIQUE_NATIVE_MAP"], 3)
        self.assertEqual(report["counts"]["NATIVE_START_DECLARED"], 2)
        self.assertEqual(report["counts"]["LOCAL_START_DECLARED"], 1)
        self.assertEqual(report["counts"]["CONFLICTING_DECLARED_START"], 1)
        self.assertEqual(report["counts"]["NO_DECLARED_START"], 2)
        self.assertEqual(report["recovered_from_native_map_quest_ids"], [3])
        self.assertEqual([row["quest_id"] for row in report["needs_review"]], [1, 2, 6])
        self.assertEqual(report["native_review_reasons"], {
            "UNIQUE_NATIVE_START_MAP": 1, "NATIVE_QUEST_ROW_MISSING": 1,
            "MULTIPLE_NATIVE_START_MAPS": 1,
        })
        self.assertEqual(report["needs_review"][0]["declared_positions"], ["[9,9]", "[1,2]"])
        self.assertEqual(report["needs_review"][2]["native_review"]["map_ids"], [10, 11])

    def test_native_instruction_audit_compiles_only_documentary_gaps_in_bounded_batches(self):
        from unittest.mock import Mock, patch
        from types import SimpleNamespace
        from app.quest_catalog import QuestObjective, QuestStep
        from app.modules.encyclopedia.tools.audit_quests_guides_semantic import native_instruction_coverage

        sources = Mock()
        calls = []
        def compile_batch(_data_dir, *, quest_ids, sources, include_enrichment):
            self.assertFalse(include_enrichment)
            calls.append(set(quest_ids))
            rows = {}
            for ident in quest_ids:
                text = "Parler au garde." if ident % 2 else "Objectif 42"
                rows[ident] = QuestRecord(
                    ident, "Quête locale", "Quêtes", 1, 1, "",
                    steps=[QuestStep(1, "Étape 1", "", objectives=[
                        QuestObjective(id=1, text=text, type_id=0),
                    ])],
                )
            return SimpleNamespace(by_id=rows)
        with patch.object(QuestCatalog, "_load_source", side_effect=compile_batch):
            report = native_instruction_coverage([*range(1, 66), 1], sources)
        self.assertEqual([len(batch) for batch in calls], [32, 32, 1])
        self.assertEqual(report["quests_considered"], 65)
        self.assertEqual(report["recovered_from_native_objective_quest_ids"], list(range(1, 66, 2)))
        self.assertEqual(report["still_missing_instruction_quest_ids"], list(range(2, 66, 2)))
        with patch.object(QuestCatalog, "_load_source", return_value=SimpleNamespace(by_id={})):
            with self.assertRaisesRegex(ValueError, "Native Quest 1 missing"):
                native_instruction_coverage([1], sources)

    def test_waypoint_and_placeholder_fallback_do_not_hide_native_instructions(self):
        from app.quest_catalog import QuestObjective, QuestSolutionBlock, QuestStep
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_blocks_have_instructions, quest_fallback_instruction_steps, quest_solution_blocks,
        )
        quest = QuestRecord(1, "Quête locale", "Quêtes", 1, 1, "",
                            steps=[QuestStep(1, "Étape 1", "Parler au garde.")])
        quest.source_solution_steps = [QuestStep(-1, "Étape 1", "[3,4]", objectives=[
            QuestObjective(id=-1, text="Objectif 99", type_id=0),
        ])]
        quest.solution_blocks = [QuestSolutionBlock(order=1, block_type="text", content="Objectif 99")]
        self.assertFalse(quest_blocks_have_instructions(quest_solution_blocks(quest)))
        fallback = quest_fallback_instruction_steps(quest)
        self.assertEqual(len(fallback), 1)
        self.assertEqual(fallback[0].description, "Parler au garde.")
        quest.steps = []
        self.assertEqual(quest_fallback_instruction_steps(quest), ())

    def test_local_coverage_closes_sqlite_readers_after_audit_error(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from app.modules.encyclopedia.tools import audit_quests_guides_semantic as mod

        sources = Mock()
        sources.mapping.return_value = {"10": {}}
        with (
            patch("app.quest_catalog_details.load_quest_ids", return_value=(10,)),
            patch.object(mod, "QuestProvider",
                         side_effect=AssertionError("must not hydrate Quest catalog")),
            patch.object(mod, "QuestSources", return_value=sources),
            patch.object(
                mod, "local_start_position_coverage",
                side_effect=RuntimeError("source changed during audit"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "source changed"):
                mod.main(["--local-coverage-only"])
        sources.close.assert_called_once_with()

    def test_local_coverage_rejects_missing_enrichment_without_false_report(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        from unittest.mock import patch
        from app.modules.encyclopedia.tools import audit_quests_guides_semantic as mod
        from app.quest_source_index import QuestSourceError

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing_quests_enriched.json"
            output = root / "coverage.json"
            with (
                patch.object(mod, "ENRICHED_PATH", missing),
                patch("app.quest_catalog_details.load_quest_ids", return_value=(10,)),
                patch.object(mod, "QuestProvider",
                             side_effect=AssertionError("must not hydrate Quest catalog")),
                redirect_stdout(StringIO()),
            ):
                with self.assertRaises(QuestSourceError):
                    mod.main([
                        "--local-coverage-only",
                        "--json-output", str(output),
                    ])
            self.assertFalse(output.exists())

    def test_local_coverage_reads_sparse_enrichment_with_existing_disk_index(self):
        from app.quest_source_index import QuestSources

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "quests_enriched.json"
            path.write_text(json.dumps({
                "quests": {
                    "10": {
                        "launch_position": {"position": "[3,4]"},
                        "solution_blocks": [{"type": "text", "content": "Parler"}],
                    },
                    "20": {"solution_blocks": []},
                    "30": {"solution_blocks": [
                        {"type": "heading", "content": "Préparation"},
                    ]},
                },
            }), encoding="utf-8")
            sources = QuestSources(root / "offsets", disk_backed=True)
            try:
                enrichment = sources.mapping(path, "quests", required=False)
                report = local_start_position_coverage(enrichment, [30, 10, 20, 99])
                self.assertEqual(report["quests_considered"], 4)
                self.assertEqual(report["counts"]["LOCAL_START_DECLARED"], 1)
                self.assertEqual(
                    report["missing_instruction_quest_ids"], [20, 30, 99],
                )
                self.assertEqual(report["priority_missing_both_quest_ids"], [20, 30, 99])
                # One bounded row cache; JSON is never loaded as one dict.
                self.assertLessEqual(len(enrichment._cache), 128)
                self.assertIsNotNone(enrichment._disk_index)
            finally:
                sources.close()

    def test_local_start_coverage_distinguishes_source_gaps_from_real_positions(self):
        rows = {
            "10": {
                "launch_position": {"position": "[3,4]"},
                "source_meta": {"startCoords": "[03, 4]"},
                "solution_blocks": [{"type": "text", "content": "Instruction"}],
            },
            "20": {
                "launch_position": {"position": "[0,0]"},
                "source_meta": {"startCoords": "[1,0]"},
            },
            "30": {"launch_position": {"position": "position inconnue"}},
            "50": {"solution_blocks": []},
            "60": {"source_meta": {"startCoords": "[5, -6]"}},
            "70": {"launch_position": {"position": "[-2147483648, 2]"}},
            "80": {"launch_position": {"position": "[2147483648, 2]"}},
            "90": {"launch_position": {"position": "[" + "9" * 5000 + ",2]"}},
        }
        report = local_start_position_coverage(rows, [90, 80, 70, 60, 50, 40, 30, 20, 10])
        self.assertEqual(report["evidence"], "LOCAL_ENRICHMENT_ONLY_NOT_GAME_VERIFIED")
        self.assertEqual(report["quests_considered"], 9)
        self.assertEqual(report["counts"]["LOCAL_START_DECLARED"], 2)
        self.assertEqual(report["counts"]["CONFLICTING_DECLARED_START"], 1)
        self.assertEqual(report["counts"]["INVALID_START_COORDINATES"], 4)
        self.assertEqual(report["counts"]["NO_DECLARED_START"], 1)
        self.assertEqual(report["counts"]["NO_ENRICHMENT"], 1)
        self.assertEqual(report["counts"]["WITH_DOCUMENTARY_BLOCKS"], 1)
        self.assertEqual(report["counts"]["WITHOUT_DOCUMENTARY_BLOCKS"], 8)
        self.assertEqual(report["counts"]["WITH_TEXTUAL_SOLUTION_BLOCKS"], 1)
        self.assertEqual(report["counts"]["WITHOUT_TEXTUAL_SOLUTION_BLOCKS"], 8)
        self.assertEqual(
            report["missing_instruction_quest_ids"],
            [20, 30, 40, 50, 60, 70, 80, 90],
        )
        self.assertEqual(
            report["priority_missing_both_quest_ids"],
            [20, 30, 40, 50, 70, 80, 90],
        )
        self.assertEqual(
            [(row["quest_id"], row["status"]) for row in report["needs_review"]],
            [
                (20, "CONFLICTING_DECLARED_START"),
                (30, "INVALID_START_COORDINATES"),
                (40, "NO_ENRICHMENT"),
                (50, "NO_DECLARED_START"),
                (70, "INVALID_START_COORDINATES"),
                (80, "INVALID_START_COORDINATES"),
                (90, "INVALID_START_COORDINATES"),
            ],
        )
        issues = report["declared_start_issues"]
        self.assertEqual(
            [issue["quest_id"] for issue in issues],
            [20, 30, 70, 80, 90],
        )
        self.assertEqual(issues[0], {
            "quest_id": 20,
            "status": "CONFLICTING_DECLARED_START",
            "launch_position": "[0,0]",
            "source_start_coords": "[1,0]",
            "truncated": False,
        })
        self.assertEqual(issues[1]["launch_position"], "position inconnue")
        self.assertEqual(issues[2]["launch_position"], "[-2147483648, 2]")
        self.assertEqual(issues[3]["launch_position"], "[2147483648, 2]")
        self.assertTrue(issues[-1]["truncated"])
        self.assertLessEqual(len(issues[-1]["launch_position"]), 80)
        self.assertNotIn(10, [issue["quest_id"] for issue in issues])
        # The report retains declared data as review evidence only.
        self.assertEqual(
            report["evidence"], "LOCAL_ENRICHMENT_ONLY_NOT_GAME_VERIFIED",
        )

    def test_local_documentation_coverage_does_not_count_empty_or_image_blocks(self):
        rows = {
            "1": {"solution_blocks": [
                {"type": "text", "content": "  "},
                {"type": "image", "content": "Une image", "image_path": "a.png"},
            ]},
            "2": {"solution_blocks": [
                {"type": "text", "content": "Parler au PNJ."},
            ]},
            "3": {"solution_blocks": [
                {"content": "Texte sans type non affiché"},
            ]},
            "4": {"solution_blocks": [
                {"type": "heading", "content": "Étape 1"},
                {"type": "subtitle", "content": "Préparation"},
            ]},
            "5": {"solution_blocks": [
                {"type": "heading", "content": "Étape 2"},
                {"type": "text", "content": "Parler au gardien."},
            ]},
            "6": {"solution_blocks": [
                {},
                {"type": "text", "content": "   "},
            ]},
            "7": {"solution_blocks": [
                {"type": "image", "image_path": "illustration.webp"},
            ]},
            "8": {"solution_blocks": [
                {"type": "text", "content": "Qf>=20"},
            ]},
            "9": {"solution_blocks": [
                {"type": "text", "content": "Mini-carte L’aperçu de la carte sera affiché ici sur le site."},
            ]},
            "10": {"solution_blocks": [
                {"type": "text", "content": "Découvrir la carte : 9999"},
            ]},
        }
        report = local_start_position_coverage(rows, range(1, 11))
        self.assertEqual(report["counts"]["WITH_DOCUMENTARY_BLOCKS"], 9)
        self.assertEqual(report["counts"]["WITHOUT_DOCUMENTARY_BLOCKS"], 1)
        self.assertEqual(report["counts"]["WITH_TEXTUAL_SOLUTION_BLOCKS"], 3)
        self.assertEqual(report["counts"]["WITHOUT_TEXTUAL_SOLUTION_BLOCKS"], 7)
        self.assertEqual(
            report["missing_instruction_quest_ids"],
            [1, 3, 4, 6, 7, 8, 9],
        )
        self.assertNotIn(10, report["missing_instruction_quest_ids"])

    def test_waypoint_only_blocks_do_not_count_as_instructions(self):
        rows = {
            "1": {"solution_blocks": [{"type": "text", "position": "[3,4]"}]},
            "2": {"solution_blocks": [{"type": "text", "content": "[3,4]"}],
                  "solution_steps": [{"description": "Parler au garde."}]},
            "3": {"solution_blocks": [{"type": "text", "content": "Aller en [3,4]."}]},
        }
        report = local_start_position_coverage(rows, (1, 2, 3))
        self.assertEqual(report["missing_instruction_quest_ids"], [1])
        self.assertEqual(report["fallback_instruction_quest_ids"], [2])
        self.assertEqual(report["counts"]["WITH_TEXTUAL_SOLUTION_BLOCKS"], 1)

    def test_quest_coverage_counts_only_fallback_instructions_actually_rendered(self):
        rows = {
            "1": {"solution_steps": [
                {"title": "Suite", "description": "Parler au garde."},
            ]},
            "2": {"solution_steps": [
                {"objectives": [
                    {"text": "Découvrir la carte : 9999",
                     "position": "[-2147483648,0]"},
                ]},
            ]},
            "3": {"solution_steps": [
                {"description": "Qf>=20",
                 "objectives": [{"text": "Mini-carte L’aperçu de la carte sera affiché ici sur le site."}]},
            ]},
            # Keep the illustration and the existing source instructions.
            "4": {
                "solution_blocks": [
                    {"type": "image", "image_path": "illustration.webp"},
                ],
                "solution_steps": [{"description": "Étape non visible."}],
            },
            # The artificial heading is filtered, so the fallback is visible.
            "5": {
                "solution_blocks": [{"type": "heading", "content": "Étape 1"}],
                "solution_steps": [{"description": "Avancer vers la sortie."}],
            },
            # Keep the genuine heading without suppressing the source fallback.
            "6": {
                "solution_blocks": [{"type": "heading", "content": "Préparation"}],
                "solution_steps": [{"description": "Texte de secours invisible."}],
            },
            "7": {
                "solution_blocks": [
                    {"type": "text", "content": "Mini-carte L’aperçu de la carte sera affiché ici sur le site."},
                ],
                "solution_steps": [{"description": "Parlez au capitaine."}],
            },
            "8": {
                "solution_blocks": [{"type": "text", "position": "[ 003, -06 ]"}],
            },
            "9": {
                "solution_blocks": [{"type": "text", "position": "[2147483648,3]"}],
            },
        }
        report = local_start_position_coverage(rows, range(1, 10))
        self.assertEqual(report["counts"]["WITH_TEXTUAL_SOLUTION_BLOCKS"], 1)
        self.assertEqual(report["counts"]["WITHOUT_TEXTUAL_SOLUTION_BLOCKS"], 8)
        self.assertEqual(report["counts"]["WITH_RENDERABLE_INSTRUCTIONS"], 7)
        self.assertEqual(report["counts"]["WITHOUT_RENDERABLE_INSTRUCTIONS"], 2)
        self.assertEqual(report["fallback_instruction_quest_ids"], [1, 2, 4, 5, 6, 7])
        self.assertEqual(report["missing_instruction_quest_ids"], [3, 9])
        self.assertEqual(report["priority_missing_both_quest_ids"], [3, 9])

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
