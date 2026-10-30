from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.services import (
    guide_ultime_manual_route,
    guide_ultime_manual_runtime_core,
)


class GuideManualRouteCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        guide_ultime_manual_route.clear_manual_route_cache()

    def test_top_level_resolution_is_reused_and_returns_isolated_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chapter = root / "chapter.json"
            chapter.write_text("{}", encoding="utf-8")
            calls = 0

            def resolver(path, *, _seen=None, _expand_hooks=True):
                nonlocal calls
                calls += 1
                return {"path": Path(path).name, "rows": [calls]}

            with patch.object(
                guide_ultime_manual_route,
                "_load_manual_chapter_uncached",
                resolver,
            ):
                first = guide_ultime_manual_route.load_manual_chapter(chapter)
                first["rows"].append(999)
                second = guide_ultime_manual_route.load_manual_chapter(chapter)

            self.assertEqual(calls, 1)
            self.assertEqual(second["rows"], [1])

    def test_sibling_json_change_invalidates_top_level_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chapter = root / "chapter.json"
            dependency = root / "dependency.json"
            chapter.write_text("{}", encoding="utf-8")
            dependency.write_text("{}", encoding="utf-8")
            calls = 0

            def resolver(path, *, _seen=None, _expand_hooks=True):
                nonlocal calls
                calls += 1
                return {"call": calls}

            with patch.object(
                guide_ultime_manual_route,
                "_load_manual_chapter_uncached",
                resolver,
            ):
                guide_ultime_manual_route.load_manual_chapter(chapter)
                guide_ultime_manual_route.load_manual_chapter(chapter)
                dependency.write_text('{"changed": true}', encoding="utf-8")
                third = guide_ultime_manual_route.load_manual_chapter(chapter)

            self.assertEqual(calls, 2)
            self.assertEqual(third["call"], 2)

    def test_shared_memo_reuses_recursive_resolution_without_duplicate_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapter = Path(tmp) / "chapter.json"
            chapter.write_text("{}", encoding="utf-8")
            calls = 0

            def resolver(path, *, _seen=None, _expand_hooks=True, _memo=None):
                nonlocal calls
                calls += 1
                return {"call": calls, "rows": [calls]}

            memo: dict[tuple[Path, bool], dict] = {}
            seen = {Path(tmp) / "parent.json"}
            with patch.object(guide_ultime_manual_route, "_load_manual_chapter_uncached", resolver):
                first = guide_ultime_manual_route.load_manual_chapter(chapter, _seen=seen, _memo=memo)
                second = guide_ultime_manual_route.load_manual_chapter(chapter, _seen=seen, _memo=memo)

            self.assertEqual(calls, 1)
            self.assertIs(first, second)
            self.assertEqual(second["rows"], [1])

    def test_copy_on_write_patch_does_not_mutate_memoized_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.json"
            child = root / "child.json"
            base.write_text(
                '{"stages":[{"id":"A","quests":["Q1"],"meta":{"keep":true}}]}',
                encoding="utf-8",
            )
            child.write_text(
                '{"base_file":"base.json","stage_patches":{"A":{"append":{"quests":["Q2"]}}}}',
                encoding="utf-8",
            )
            memo: dict[tuple[Path, bool], dict] = {}
            resolved = guide_ultime_manual_route.load_manual_chapter(
                child,
                _seen={root / "parent.json"},
                _expand_hooks=False,
                _memo=memo,
            )

            memoized_base = memo[(base.resolve(), False)]
            self.assertEqual(memoized_base["stages"][0]["quests"], ["Q1"])
            self.assertEqual(resolved["stages"][0]["quests"], ["Q1", "Q2"])
            self.assertIsNot(resolved["stages"][0], memoized_base["stages"][0])
            self.assertIs(
                resolved["stages"][0]["meta"],
                memoized_base["stages"][0]["meta"],
            )

    def test_shared_memo_does_not_mask_active_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapter = Path(tmp) / "chapter.json"
            chapter.write_text("{}", encoding="utf-8")
            resolved = chapter.resolve()
            memo = {(resolved, True): {"rows": [1]}}

            with self.assertRaisesRegex(ValueError, "Cycle de composition"):
                guide_ultime_manual_route.load_manual_chapter(chapter, _seen={resolved}, _memo=memo)

    def test_compact_runtime_builds_hidden_cards_without_full_render_payload(self) -> None:
        service = object.__new__(
            guide_ultime_manual_runtime_core.GuideUltimeManualRuntimeService
        )
        service._quest_name_to_id = {"quest_a": 42}

        chapter = {
            "coverage": {"chapter": "Astrub"},
            "preparation": [{"name": "Potion de rappel"}],
        }
        stage = {
            "id": "AST-1",
            "title": "Départ",
            "start": {"x": 4, "y": -19, "zone": "Astrub"},
            "quests": ["Quest A"],
            "instructions": ["Parler au PNJ."],
            "successes": ["Succès A"],
            "temporal_hooks": ["window-a"],
        }

        with patch.object(
            service,
            "_stage_lines",
            side_effect=AssertionError("hidden compact cards must not render lines"),
        ):
            card = service._stage_to_compact_card(
                "astrub",
                {"label": "Astrub"},
                chapter,
                stage,
                1,
            )

        self.assertEqual(card["manual_stage_id"], "AST-1")
        self.assertEqual(card["manual_quest_ids"], [42])
        self.assertEqual(card["manual_quest_names"], ["quest_a"])
        self.assertTrue(card["manual_has_lines"])
        self.assertEqual(card["manual_lines"], [])
        self.assertNotIn("manual_stage_data", card)
        self.assertNotIn("manual_chapter_preparation", card)
        self.assertNotIn("structured_runtime_lines", card)
        self.assertNotIn("manual_runtime_metadata", card)

    def test_compact_runtime_hydrates_only_current_manual_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = object.__new__(
                guide_ultime_manual_runtime_core.GuideUltimeManualRuntimeService
            )
            service.compact_runtime = True
            service.manual_dir = Path(tmp)
            service._manual_base_lines_cache = ("old", [{"text": "old"}])

            previous = {
                "manual_stage_data": {"id": "previous"},
                "manual_chapter_preparation": [{"name": "old"}],
            }
            service._manual_hydrated_card = previous
            card = {
                "manual_source_file": "chapter.json",
                "manual_stage_position": 1,
            }
            chapter = {
                "stages": [
                    {"id": "first"},
                    {"id": "visible", "instructions": ["Do it"]},
                ]
            }

            with (
                patch.object(
                    guide_ultime_manual_runtime_core,
                    "load_manual_chapter",
                    return_value=chapter,
                ),
                patch.object(
                    service,
                    "_chapter_preparation_schedule",
                    return_value={1: [{"name": "needed"}]},
                ),
            ):
                stage = service._hydrate_manual_card_source(card)

            self.assertIs(stage, chapter["stages"][1])
            self.assertIs(card["manual_stage_data"], chapter["stages"][1])
            self.assertEqual(
                card["manual_chapter_preparation"],
                [{"name": "needed"}],
            )
            self.assertNotIn("manual_stage_data", previous)
            self.assertNotIn("manual_chapter_preparation", previous)
            self.assertIs(service._manual_hydrated_card, card)
            self.assertIsNone(service._manual_base_lines_cache)

    def test_compact_runtime_hydrates_resolved_sheet_without_reloading_chapter(self) -> None:
        service = object.__new__(
            guide_ultime_manual_runtime_core.GuideUltimeManualRuntimeService
        )
        service.compact_runtime = True
        service.manual_dir = Path(".")
        service._manual_base_lines_cache = None
        service._manual_hydrated_card = None

        stage = {"id": "visible", "instructions": ["Do it"], "quests": ["Quest A"]}
        preparation = [{"name": "Potion de rappel"}]
        card = {
            "manual_source_file": "chapter.json",
            "manual_stage_position": 0,
            "_manual_stage_payload": __import__("zlib").compress(
                json.dumps(stage, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                1,
            ),
            "_manual_chapter_preparation_payload": __import__("zlib").compress(
                json.dumps(preparation, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                1,
            ),
        }

        with patch.object(
            guide_ultime_manual_runtime_core,
            "load_manual_chapter",
            side_effect=AssertionError("visible compact sheet must not reload chapter"),
        ):
            hydrated = service._hydrate_manual_card_source(card)

        self.assertEqual(hydrated, stage)
        self.assertEqual(card["manual_stage_data"], stage)
        self.assertEqual(card["manual_chapter_preparation"], preparation)
        self.assertIs(service._manual_hydrated_card, card)

    def test_recursive_resolution_bypasses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapter = Path(tmp) / "chapter.json"
            chapter.write_text("{}", encoding="utf-8")
            calls = 0

            def resolver(path, *, _seen=None, _expand_hooks=True):
                nonlocal calls
                calls += 1
                return {"call": calls}

            seen = {Path(tmp) / "parent.json"}
            with patch.object(
                guide_ultime_manual_route,
                "_load_manual_chapter_uncached",
                resolver,
            ):
                first = guide_ultime_manual_route.load_manual_chapter(
                    chapter,
                    _seen=seen,
                )
                second = guide_ultime_manual_route.load_manual_chapter(
                    chapter,
                    _seen=seen,
                )

            self.assertEqual((first["call"], second["call"]), (1, 2))
            self.assertEqual(calls, 2)

    def test_compact_runtime_disk_cache_roundtrips_bytes_and_rejects_stale_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "chapter.json"
            source.write_text("{}", encoding="utf-8")
            cache = root / "runtime.json"

            class Service:
                manual_dir = root
                _quest_name_to_id = {"quete_test": 42}
                route = {"id": "manual", "steps": []}
                cards = [
                    {
                        "manual_stage_id": "s1",
                        "_manual_stage_payload": b"abc",
                    }
                ]
                manual_audit_data = {"card_count": 1}
                manual_preview_active = True
                manual_preview_chapters = ("c1",)
                manual_manifest_active = True
                manual_chapters = ("c1",)
                _common_quest_ids = (42,)
                _full_success_ids = ()

            guide_ultime_manual_runtime_core.write_manual_runtime_compact_cache(
                Service,
                cache,
            )

            target = Service()
            target.route = {}
            target.cards = []
            target.manual_audit_data = {}
            self.assertTrue(
                guide_ultime_manual_runtime_core.restore_manual_runtime_compact_cache(
                    target,
                    cache,
                )
            )
            self.assertEqual(target.cards[0]["_manual_stage_payload"], b"abc")
            self.assertEqual(target._common_quest_ids, (42,))

            source.write_text('{"changed":true}', encoding="utf-8")
            stale = Service()
            stale.route = {}
            stale.cards = []
            self.assertFalse(
                guide_ultime_manual_runtime_core.restore_manual_runtime_compact_cache(
                    stale,
                    cache,
                )
            )


    def test_short_quest_text_normalization_cache_is_bounded(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            _cached_clean_text,
            clean_text,
        )

        _cached_clean_text.cache_clear()
        raw = "  Bonjour&nbsp;<b>Astrub</b>  {{npc::Meriana}}   "
        self.assertEqual(clean_text(raw), "Bonjour Astrub Meriana")
        self.assertEqual(clean_text(raw), "Bonjour Astrub Meriana")
        self.assertEqual(_cached_clean_text.cache_info().hits, 1)

        # Non-hashable input must remain supported, just like the old function.
        self.assertEqual(clean_text(["Texte", "utile"]), "['Texte', 'utile']")

        # Long walkthroughs must not be pinned by the bounded label cache.
        previous = _cached_clean_text.cache_info()
        long_text = "Le chemin est long. " * 200
        self.assertEqual(clean_text(long_text), long_text.strip())
        self.assertEqual(_cached_clean_text.cache_info().misses, previous.misses)
        self.assertEqual(_cached_clean_text.cache_info().maxsize, 2048)
        _cached_clean_text.cache_clear()



    def test_catalog_position_keys_equivalent_and_cache_bounded(self) -> None:
        from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
            GuideCatalogManualRuntimeService, _position_key_short, _position_key_uncached,
        )
        key = GuideCatalogManualRuntimeService._position_key
        _position_key_short.cache_clear()
        for label in ("  [ 4 , -19 ] ", "[4,-19]", "Astrub nord",
                      "Épave  dans  l'eau", "", ["  Une", "liste  "], None):
            value = " ".join(str(label or "").split()).strip()
            self.assertEqual(key(label), _position_key_uncached(value))
        self.assertEqual(key(" [ 4 , -19 ] "), "4,-19")
        self.assertEqual(key(" [ 4 , -19 ] "), "4,-19")
        self.assertGreater(_position_key_short.cache_info().hits, 0)
        self.assertEqual(_position_key_short.cache_info().maxsize, 4096)
        long_label = "Longue description à préserver. " * 80
        misses = _position_key_short.cache_info().misses
        self.assertEqual(key(long_label), _position_key_uncached(long_label.strip()))
        self.assertEqual(_position_key_short.cache_info().misses, misses)
        _position_key_short.cache_clear()



    def test_catalog_batch_merge_matches_legacy_incremental_render(self) -> None:
        from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
            GuideCatalogManualRuntimeService,
        )

        service = object.__new__(GuideCatalogManualRuntimeService)
        positions = ("[1, 2]", "[1,2]", "[1, 2]", "[3,4]", "[3, 4]")
        raw = []
        for idx, position in enumerate(positions):
            segment = service._new_segment(
                position=position, zone="Astrub", quest_id=40 + idx,
                quest_name=f"Quête {idx}", guide_step_id=f"stage-{idx}",
            )
            segment["sections"]["now"].extend((
                service._line("action", position, "Action commune"),
                service._line("action", position, "Action commune"),
                service._line("action", position, f"Objectif {idx}"),
            ))
            raw.append(segment)
        untouched = copy.deepcopy(raw)

        # Legacy: finalize every quest segment and then every consecutive merge.
        legacy = copy.deepcopy(raw)
        for segment in legacy:
            service._finalize_segment(segment)
        expected = []
        for segment in legacy:
            value = copy.deepcopy(segment)
            key = service._position_key(value["position"])
            if expected and key and key == service._position_key(expected[-1]["position"]):
                service._merge_segment(expected[-1], value)
            else:
                expected.append(value)

        with patch.object(service, "_finalize_segment", wraps=service._finalize_segment) as finalize:
            result = service._merge_consecutive_positions(raw)
        self.assertEqual(result, expected)
        self.assertEqual(finalize.call_count, 2)
        self.assertEqual(raw, untouched)
        self.assertEqual(len(result), 2)
        result[0]["manual_lines"][0]["text"] = "modified"
        self.assertEqual(raw, untouched)
        self.assertNotEqual(result[0]["sections"]["now"][0]["text"], "modified")

    def test_catalog_owned_segments_match_copy_mode_without_shared_output(self) -> None:
        from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
            GuideCatalogManualRuntimeService,
        )
        service = object.__new__(GuideCatalogManualRuntimeService)
        service.guide_id = "dofus_sylvestre"
        service.guide_title = "Sylvestre"
        raw = []
        for idx, position in enumerate(("[1,2]", "[1, 2]", "[3,4]")):
            part = service._new_segment(
                position=position, zone="Astrub", quest_id=42 + idx,
                quest_name=f"Quête {idx}", guide_step_id=f"step-{idx}",
            )
            part["sections"]["now"].append(
                service._line("action", position, f"Parler au PNJ {idx}")
            )
            raw.append(part)

        originals = copy.deepcopy(raw)
        expected = service._merge_consecutive_positions(raw)
        self.assertEqual(raw, originals)
        owned = service._merge_consecutive_positions(copy.deepcopy(raw), consume=True)
        self.assertEqual(expected, owned)
        expected_cards = [
            service._segment_to_card(part, idx)
            for idx, part in enumerate(expected)
        ]
        owned_cards = [
            service._segment_to_card(part, idx, consume=True)
            for idx, part in enumerate(owned)
        ]
        self.assertEqual(owned_cards, expected_cards)
        # Private ownership permits transfer, but public non-consuming methods
        # still return copies and never mutate caller-supplied source segments.
        self.assertIs(owned_cards[0]["manual_sections"], owned[0]["sections"])
        self.assertIsNot(expected_cards[0]["manual_sections"], expected[0]["sections"])
        self.assertEqual(raw, originals)

    def test_catalog_start_metadata_skips_unneeded_image_file_probes(self) -> None:
        from app.modules.encyclopedia.services import guide_quest_view_model as model
        quest = SimpleNamespace(
            level_min=100, zones=("Astrub",), steps=(),
            source_info={
                "launch_position": {"position": "[1, 2]"},
                "source_meta": {
                    "startNpc": "PNJ test", "zone": "Astrub",
                    "startMapImages": ["not-used.jpg"],
                },
            },
        )
        with patch.object(
            model, "_explicit_start_map_paths", return_value=("map.jpg",)
        ) as image_probe:
            rich = model.quest_start_info(quest)
            gps = model.quest_start_info(quest, include_map_images=False)
            image_probe.assert_called_once()
        self.assertEqual((gps.npc, gps.position, gps.zone, gps.level),
                         (rich.npc, rich.position, rich.zone, rich.level))
        self.assertEqual(gps.map_image_paths, ())
        self.assertEqual(rich.map_image_paths, ("map.jpg",))
        with patch.object(model, "quest_start_info", side_effect=AssertionError(
            "GPS must reuse its already extracted start metadata",
        )):
            self.assertEqual(model.first_position_from_quest(quest, start_info=gps), "[1, 2]")

    def test_fast_solution_text_filter_preserves_legacy_double_clean(self) -> None:
        import re
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            MINIMAP_PLACEHOLDER_RE,
            _clean_solution_instruction_text,
            clean_text,
        )
        samples = (
            "Parlez au PNJ.",
            "Action en [4, -19].",
            "&amp;lt;em&amp;gt;Instruction&amp;lt;/em&amp;gt;",
            "{{Potion::Potion de rappel}}",
            "Ligne &amp; élixir",
            "Mini-carte L’aperçu de la carte sera affiché ici sur le site.",
            "Action Mini-carte L'aperçu de la carte sera affiché ici sur le site. Suite.",
            "Achetez 2 × bois.",
        )
        for raw in samples:
            normalized = clean_text(raw)
            legacy = re.sub(
                r"\\s+", " ",
                MINIMAP_PLACEHOLDER_RE.sub("", clean_text(normalized)),
            ).strip()
            self.assertEqual(
                _clean_solution_instruction_text(normalized), legacy,
                msg=f"Guide objective changed for {raw!r}",
            )

    def test_catalog_deferred_quest_segments_keep_identical_cards(self) -> None:
        from app.modules.encyclopedia.services import guide_catalog_manual_runtime_service as catalog_module
        from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
            GuideCatalogManualRuntimeService,
        )

        service = object.__new__(GuideCatalogManualRuntimeService)
        quest = SimpleNamespace(id=42, name="Test", zones=("Astrub",), prerequisites=())
        guide_step = SimpleNamespace(id="guide-step-42")
        solution_step = SimpleNamespace(
            title="Étape", description="Description",
            objectives=(
                SimpleNamespace(text="Action 1", position="[0,0]", combat=False),
                SimpleNamespace(text="Action 2", position="[0,0]", combat=False),
                SimpleNamespace(text="Action 3", position="[1,1]", combat=True),
            ),
        )
        start = SimpleNamespace(position="[0,0]", zone="Astrub", npc="PNJ")
        with (
            patch.object(catalog_module, "quest_start_info", return_value=start),
            patch.object(catalog_module, "quest_items_from_objectives", return_value=()),
            patch.object(catalog_module, "quest_solution_steps", return_value=(solution_step,)),
        ):
            with patch.object(service, "_position_key", wraps=service._position_key) as key:
                deferred = service._quest_segments(guide_step, quest, finalize=False)
            self.assertEqual(key.call_count, 4)  # initial map + three objectives
            self.assertTrue(all(not segment["manual_lines"] for segment in deferred))
            for segment in deferred:
                service._finalize_segment(segment)
            regular = service._quest_segments(guide_step, quest)

        self.assertEqual(deferred, regular)
        self.assertEqual(len(regular), 2)


    def test_release_prebuilt_guide_open_reports_real_path_without_source_fallback(self):
        from app.modules.encyclopedia.services import (
            guide_catalog_manual_runtime_service as catalog_module,
            guide_catalog_prebuilt_route as prebuilt_module,
        )

        service = object.__new__(catalog_module.GuideCatalogManualRuntimeService)
        with (
            patch.object(prebuilt_module, "restore_prebuilt_route", return_value=True) as restore,
            patch.object(catalog_module, "_catalog_route_cache_identity",
                         side_effect=AssertionError("No source fallback on prebuilt")) as identity,
        ):
            service._load_manual_preview()
        restore.assert_called_once_with(service)
        identity.assert_not_called()
        self.assertEqual(service.last_catalog_route_load_ms["mode"], "prebuilt")
        self.assertGreaterEqual(service.last_catalog_route_load_ms["total_ms"], 0)

    def test_catalog_projection_disk_cache_skips_quest_rebuild_and_isolated(self) -> None:
        from app.modules.encyclopedia.services import (
            guide_catalog_manual_runtime_service as catalog_module,
        )
        Service = catalog_module.GuideCatalogManualRuntimeService
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sylvestre.json.gz"
            service = object.__new__(Service)
            service.guide_id = "dofus_sylvestre"
            service.guide_title = "Sylvestre"
            service.route = {
                "id": "catalog_manual_dofus_sylvestre",
                "route_model": "map_segments",
                "steps": [{
                    "index": 1, "manual_stage_id": "stable:001",
                    "manual_sections": {"now": [{"text": "Parler au PNJ"}]},
                    "manual_lines": [{"text": "Parler au PNJ"}],
                }],
            }
            service.cards = service.route["steps"]
            service.manual_audit_data = {"card_count": 1, "quest_count": 198}
            service._common_quest_ids = (42, 43)
            catalog_module._write_catalog_route_cache(service, path, "sources-v1")

            # This exercises the real Guide constructor's override of
            # _load_manual_preview: no Quest detail may be hydrated on a hit.
            restored = object.__new__(Service)
            restored.guide_id = service.guide_id
            restored.guide_title = service.guide_title
            with patch.object(
                catalog_module, "_catalog_route_cache_identity",
                return_value=(path, "sources-v1"),
            ):
                restored._load_manual_preview()
            # The original full gzip cache migrates into an indexed route:
            # metadata matches while bodies are intentionally not retained.
            self.assertEqual(restored.route["id"], service.route["id"])
            self.assertEqual(
                restored.cards[0]["manual_stage_id"],
                service.cards[0]["manual_stage_id"],
            )
            self.assertNotIn("manual_lines", restored.cards[0])
            self.assertEqual(restored._common_quest_ids, (42, 43))
            self.assertTrue(restored.manual_preview_active)
            self.assertEqual(restored.last_catalog_route_load_ms["mode"], "legacy_migration")
            self.assertGreaterEqual(restored.last_catalog_route_load_ms["total_ms"], 0)
            sections = restored.manual_sections_for_card("character:1", restored.cards[0])
            self.assertEqual(sections["now"], [{"text": "Parler au PNJ"}])
            sections["now"][0]["text"] = "Changed"
            self.assertEqual(
                restored.manual_sections_for_card("character:1", restored.cards[0])["now"],
                [{"text": "Parler au PNJ"}],
            )
            self.assertEqual(service.cards[0]["manual_sections"]["now"][0]["text"], "Parler au PNJ")

            self.assertFalse(catalog_module._restore_catalog_route_cache(
                object.__new__(Service), path, "sources-v2",
            ))
            path.write_bytes(b"invalid-cache-not-user-data")
            self.assertFalse(catalog_module._restore_catalog_route_cache(
                object.__new__(Service), path, "sources-v1",
            ))

    def test_catalog_projection_signature_invalidates_guide_and_quest_changes(self) -> None:
        from app.constants import RAW_QUEST_DATA_DIR
        from app.modules.encyclopedia.providers.quest_provider import QuestProvider
        from app.modules.encyclopedia.services import (
            guide_catalog_manual_runtime_service as catalog_module,
        )
        service = object.__new__(catalog_module.GuideCatalogManualRuntimeService)
        service.guide_id = "dofus_sylvestre"
        service.guide_title = "Sylvestre"
        service.use_disk_cache = True
        service.quest_provider = QuestProvider(data_dir=RAW_QUEST_DATA_DIR)
        step = SimpleNamespace(id="step-1", step_type="quest", entity_id=42, order=1)
        service.catalog_guide = SimpleNamespace(required_steps=[step])
        with patch.object(
            catalog_module, "quest_catalog_cache_signature", return_value=(("source", "v1"),),
        ) as signature:
            first = catalog_module._catalog_route_cache_identity(service)
            step.order = 2
            changed_order = catalog_module._catalog_route_cache_identity(service)
            step.order = 1
            signature.return_value = (("source", "v2"),)
            changed_sources = catalog_module._catalog_route_cache_identity(service)
        self.assertEqual(first[0], changed_order[0])
        self.assertNotEqual(first[1], changed_order[1])
        self.assertNotEqual(first[1], changed_sources[1])
        service.use_disk_cache = False
        self.assertIsNone(catalog_module._catalog_route_cache_identity(service))



    def test_enriched_quest_update_invalidates_cached_sylvestre_signature(self) -> None:
        from app.constants import RAW_QUEST_DATA_DIR
        from app.modules.encyclopedia.providers.quest_provider import QuestProvider
        from app.modules.encyclopedia.services import (
            guide_catalog_manual_runtime_service as module,
        )
        service = object.__new__(module.GuideCatalogManualRuntimeService)
        service.guide_id = "dofus_sylvestre"
        service.guide_title = "Sylvestre"
        service.use_disk_cache = True
        service.quest_provider = QuestProvider(data_dir=RAW_QUEST_DATA_DIR)
        service.catalog_guide = SimpleNamespace(required_steps=[
            SimpleNamespace(id="one", step_type="quest", entity_id=1, order=1),
        ])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            enriched = root / "encyclopedia" / "quests" / "quests_enriched.json"
            enriched.parent.mkdir(parents=True, exist_ok=True)
            enriched.write_text("{}", encoding="utf-8")
            with (
                patch.object(module, "DATA_DIR", root),
                patch.object(module, "quest_catalog_cache_signature", return_value=(("raw", "same"),)),
            ):
                first = module._catalog_route_cache_identity(service)
                enriched.write_text('{"quests":{}}', encoding="utf-8")
                second = module._catalog_route_cache_identity(service)
        self.assertEqual(first[0], second[0])
        self.assertNotEqual(first[1], second[1])

    def test_release_route_source_sizes_include_enriched_quest_file(self) -> None:
        from app.modules.encyclopedia.services import (
            guide_catalog_prebuilt_route as prebuilt_module,
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            enriched = root / "encyclopedia" / "quests" / "quests_enriched.json"
            enriched.parent.mkdir(parents=True, exist_ok=True)
            enriched.write_bytes(b"tiny-enrichment")
            with (
                patch.object(prebuilt_module, "DATA_DIR", root),
                patch.object(prebuilt_module, "QUEST_CATALOG_SOURCE_FILES", ()),
            ):
                sizes = prebuilt_module._source_sizes(root)
            self.assertEqual(
                sizes["encyclopedia/quests/quests_enriched.json"],
                len(b"tiny-enrichment"),
            )

    def test_catalog_cards_skip_only_unrelated_manual_branch_policies(self) -> None:
        from app.modules.encyclopedia.services import (
            guide_catalog_manual_runtime_service as module,
        )
        service = object.__new__(module.GuideCatalogManualRuntimeService)
        service.guide_id = "dofus_sylvestre"
        service.guide_title = "Sylvestre"
        segment = service._new_segment(
            position="[1,2]", zone="Astrub", quest_id=42,
            quest_name="Quête test", guide_step_id="step-1",
        )
        segment["sections"]["now"].append(
            service._line("action", "[1,2]", "Parler au PNJ"),
        )
        service._finalize_segment(segment)
        card = service._segment_to_card(segment, 0)

        # Other manual routes retain their original conditional policy:
        # only this catalogue subclass bypasses the manual manifest.
        with (
            patch.object(service, "_manual_manifest", side_effect=AssertionError(
                "catalogue cards must not parse an unrelated manual manifest"
            )),
            patch.object(service, "selected_order_name", side_effect=AssertionError(
                "catalogue completion must not scan manual Order status"
            )),
        ):
            self.assertIsNone(service.manual_class_gate_for_card(card))
            self.assertIsNone(service.manual_order_gate_for_card(card))
            self.assertEqual(service.card_success_ids(card), ())
            self.assertEqual(
                service.card_automatic_values("character:1", card, completed_quests={42}),
                (True,),
            )
            self.assertEqual(
                service.card_automatic_values("character:1", card, completed_quests=set()),
                (False,),
            )


    def test_catalog_indexed_route_restores_only_skeleton_and_one_detail(self) -> None:
        from app.modules.encyclopedia.services import (
            guide_catalog_manual_runtime_service as module,
            guide_catalog_route_store as store,
        )
        Service = module.GuideCatalogManualRuntimeService
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guide.json.gz"
            source = object.__new__(Service)
            source.guide_id = "dofus_sylvestre"
            source.guide_title = "Sylvestre"
            cards = [
                {
                    "index": index + 1,
                    "manual_source": True,
                    "manual_stage_id": f"dofus_sylvestre:gps:{index}",
                    "manual_title": f"Fiche {index}",
                    "manual_quest_ids": [42 + index],
                    "a_preparer": [{"name": "Fée", "quantity": 1}],
                    "manual_lines": [{"text": f"Ligne {index}"}],
                    "manual_sections": {
                        "now": [{"text": f"Parler au PNJ {index}"}],
                        "prepare": [{"text": "Prépare 1 × Fée"}],
                    },
                }
                for index in range(14)
            ]
            source.cards = cards
            source.route = {
                "id": "catalog_manual_dofus_sylvestre",
                "steps": cards,
                "route_model": "map_segments",
            }
            source.manual_audit_data = {"card_count": len(cards)}
            source._common_quest_ids = (42, 43)
            store.write_indexed_route(source, path, "quest-version-1")
            self.assertEqual(source.cards[0]["manual_lines"], [{"text": "Ligne 0"}])

            restored = object.__new__(Service)
            restored.guide_id = source.guide_id
            restored.guide_title = source.guide_title
            self.assertTrue(store.restore_indexed_route(restored, path, "quest-version-1"))
            self.assertEqual(len(restored.cards), 14)
            self.assertEqual(restored._common_quest_ids, (42, 43))
            self.assertEqual(restored.cards[0]["manual_stage_id"], cards[0]["manual_stage_id"])
            self.assertEqual(restored.cards[0]["a_preparer"], cards[0]["a_preparer"])
            self.assertNotIn("manual_lines", restored.cards[0])
            self.assertEqual(
                restored.cards[0]["manual_sections"],
                {"prepare": [{"text": "Prépare 1 × Fée"}]},
            )
            self.assertFalse(restored._catalog_detail_cache)

            # The actual card API hydrates a single body, with no visible
            # mutation of the compact all-route skeleton or source object.
            lines = restored.manual_lines_for_card("character:1", restored.cards[0])
            self.assertEqual(lines, [{"text": "Ligne 0"}])
            lines[0]["text"] = "modified by widget"
            self.assertEqual(
                restored.manual_lines_for_card("character:1", restored.cards[0]),
                [{"text": "Ligne 0"}],
            )
            sections = restored.manual_sections_for_card("character:1", restored.cards[0])
            self.assertEqual(sections["now"], [{"text": "Parler au PNJ 0"}])
            self.assertEqual(source.cards[0]["manual_lines"], [{"text": "Ligne 0"}])
            self.assertFalse(store.restore_indexed_route(
                object.__new__(Service), path, "quest-version-2",
            ))

            # Qt can request just one SQLite row per timer tick; the
            # interrupted prefetch must never materialize the whole route.
            with patch.object(
                module, "load_catalog_card_detail",
                wraps=module.load_catalog_card_detail,
            ) as reader:
                self.assertTrue(restored.prefetch_route_near(11, max_reads=1))
                self.assertEqual(reader.call_count, 1)
                self.assertEqual(len(restored._catalog_detail_cache), 2)
                for _ in range(10):
                    if not restored.prefetch_route_near(11, max_reads=1):
                        break
                else:
                    self.fail("Neighborhood prefetch did not terminate")
                self.assertLessEqual(reader.call_count, 5)
                self.assertLessEqual(len(restored._catalog_detail_cache), 10)
                self.assertEqual(
                    restored.manual_lines_for_card("character:2", restored.cards[11]),
                    [{"text": "Ligne 11"}],
                )

            # Bounded neighboring prefetch never hydrates the full itinerary.
            with patch.object(
                module, "load_catalog_card_detail",
                wraps=module.load_catalog_card_detail,
            ) as reader:
                restored.prefetch_route_near(7)
                self.assertLessEqual(len(restored._catalog_detail_cache), 10)
                self.assertLessEqual(reader.call_count, 9)
                count_after_first = reader.call_count
                restored.prefetch_route_near(7)
                self.assertEqual(reader.call_count, count_after_first)
            self.assertLess(len(restored._catalog_detail_cache), len(restored.cards))

    def test_catalog_indexed_route_invalid_rows_do_not_mask_full_route(self) -> None:
        from app.modules.encyclopedia.services import (
            guide_catalog_manual_runtime_service as module,
            guide_catalog_route_store as store,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sylvestre.json.gz"
            self.assertFalse(store.restore_indexed_route(
                object.__new__(module.GuideCatalogManualRuntimeService), path, "v1",
            ))
            route = object.__new__(module.GuideCatalogManualRuntimeService)
            route.guide_id = "dofus_sylvestre"
            route.cards = [{
                "index": 1, "manual_stage_id": "gps:1", "manual_source": True,
                "manual_lines": [{"text": "all"}],
                "manual_sections": {"now": [{"text": "all"}]},
            }]
            route.route = {"id": "catalog_manual_dofus_sylvestre", "steps": route.cards}
            route.manual_audit_data = {"card_count": 1}
            route._common_quest_ids = (1,)
            stored = store.write_indexed_route(route, path, "v1")
            # Bypass reads after invalid signatures, rather than using stale content.
            reopened = object.__new__(module.GuideCatalogManualRuntimeService)
            reopened.guide_id = "dofus_sylvestre"
            self.assertFalse(store.restore_indexed_route(reopened, path, "v2"))
            stored.write_bytes(b"not-a-sqlite-database")
            self.assertFalse(store.restore_indexed_route(reopened, path, "v1"))


    def test_catalog_index_preparation_is_filtered_before_storing(self) -> None:
        from app.modules.encyclopedia.services import (
            guide_catalog_manual_runtime_service as module,
            guide_catalog_route_store as store,
        )
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "sylvestre.json.gz"
            source = object.__new__(module.GuideCatalogManualRuntimeService)
            source.guide_id = "dofus_sylvestre"
            source.cards = [{
                "index": 1, "manual_stage_id": "stable:1", "manual_source": True,
                "manual_sections": {
                    "prepare": [{"text": "Préparer 1 × Objet acquis sur place"}],
                    "now": [{"text": "Acquérir cet objet sur place"}],
                },
                "manual_lines": [{"text": "Acquérir cet objet sur place"}],
                "a_preparer": [],
            }]
            source.route = {"id": "catalog_manual_dofus_sylvestre", "steps": source.cards}
            source.manual_audit_data = {"card_count": 1}
            source._common_quest_ids = (1,)
            # The already-authoritative sections policy removes a requirement
            # fulfilled on the same map; the compact index must preserve the
            # filtered preparation while the full text remains in SQLite.
            with patch.object(source, "manual_sections_for_card", return_value={
                "prepare": [], "now": [{"text": "Acquérir cet objet sur place"}],
            }) as filter_sections:
                store.write_indexed_route(source, legacy, "v1")
            filter_sections.assert_called_once_with("", source.cards[0])
            restored = object.__new__(module.GuideCatalogManualRuntimeService)
            restored.guide_id = source.guide_id
            self.assertTrue(store.restore_indexed_route(restored, legacy, "v1"))
            self.assertEqual(restored.cards[0].get("manual_sections", {}), {})
            self.assertEqual(
                restored.manual_sections_for_card("character:1", restored.cards[0])["prepare"],
                [{"text": "Préparer 1 × Objet acquis sur place"}],
            )
            # Global metadata can be read without touching disk sheet rows.
            with patch.object(
                module, "load_catalog_card_detail",
                side_effect=AssertionError("global preparation must stay compact"),
            ):
                self.assertEqual(restored.cards[0].get("manual_sections", {}), {})


if __name__ == "__main__":
    unittest.main()
