from __future__ import annotations

import json
import sqlite3
from contextlib import closing
import tempfile
import threading
import time
import unittest
import weakref
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from app import quest_catalog as qc
from app.quest_catalog import QuestCatalog, QuestRecord, QuestStep
from app.quest_catalog_details import (
    _solution_combat_rows,
    ensure_detail_source_offsets,
    load_lazy_catalog,
)
from app.quest_source_index import (
    JsonSourceMapping,
    QuestSources,
    read_selected_json_object_values,
)


def record(quest_id):
    return QuestRecord(quest_id, f"Quête {quest_id}", "Test", 1, 200, "")


class QuestDetailsTests(unittest.TestCase):
    def test_solution_combats_have_stable_compact_evidence_without_rich_detail(self):
        evidence = _solution_combat_rows({
            "solution_steps": [
                {"objectives": [
                    {"text": "Parler au garde", "combat": False},
                    {"text": "  Vaincre   le Bouftou Royal  ", "combat": True},
                ]},
                {"objectives": [
                    {"text": "Vaincre le Bouftou Royal", "combat": True},
                    {"text": "Combat tactique " + "très long " * 30, "combat": True},
                ]},
            ]
        })

        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence[0], {
            "objective_id": 1_500_001_002,
            "monster": "Vaincre le Bouftou Royal",
            "quantity": 1,
        })
        self.assertEqual(evidence[1]["objective_id"], 1_500_002_002)
        self.assertLessEqual(len(evidence[1]["monster"]), 160)

    def build(self, root, limit=32):
        context = {
            "achievement_names": {10: "Succès test"},
            "quest_names": {1: "Quête 1", 2: "Quête 2", 3: "Quête 3"},
            "quest_to_achievements": {1: ["Succès test"]},
        }
        with patch(
            "app.quest_catalog_details._source_index",
            return_value=([record(1), record(2), record(3)], (), context),
        ):
            catalog = load_lazy_catalog(root, cache_root=root / 'cache')
        catalog.quests[0]._details.limit = limit
        return catalog

    @staticmethod
    def compile(data_dir, *, quest_ids, **kwargs):
        records = [record(key) for key in quest_ids]
        for row in records:
            row.steps = [QuestStep(row.id * 10, 'Étape', 'Détail')]
        return QuestCatalog(records)

    def test_guide_evidence_reads_sqlite_without_hydrating_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "cache"

            def write_rows(name, rows):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"references": {"RefIds": [
                    {"rid": row["id"], "data": row} for row in rows
                ]}}, ensure_ascii=False), encoding="utf-8")

            language = root / "languages/fr.json"
            language.parent.mkdir(parents=True)
            language.write_text(json.dumps({"entries": {
                "101": "Quête", "110": "Catégorie",
                "201": "Objet compact", "301": "Monstre compact",
            }}, ensure_ascii=False), encoding="utf-8")
            write_rows("quests.json", [{"id": 1, "nameId": 101, "categoryId": 10, "stepIds": {"Array": [10]}}])
            write_rows("quest_categories.json", [{"id": 10, "nameId": 110}])
            write_rows("achievements.json", [])
            write_rows("achievement_objectives.json", [])
            write_rows("achievement_categories.json", [])
            write_rows("items.json", [{"id": 20, "nameId": 201}])
            write_rows("monsters.json", [{"id": 30, "nameId": 301}])
            write_rows("quest_objectives.json", [
                {"id": 40, "stepId": 10, "typeId": 17, "parameters": {"parameter0": 20, "parameter1": 3}},
                {"id": 41, "stepId": 10, "typeId": 6, "parameters": {"parameter0": 30, "parameter1": 2}},
            ])

            catalog = load_lazy_catalog(root, cache_root=cache_root)
            evidence = catalog.guide_evidence(1)

            self.assertEqual(evidence["items"][0]["name"], "Objet compact")
            self.assertEqual(evidence["items"][0]["quantity"], 3)
            self.assertEqual(evidence["combats"][0]["monster"], "Monstre compact")
            self.assertEqual(evidence["combats"][0]["objective_id"], 41)

            # The Guide indexer already read all objectives during preload.
            # Cold Quest details must reuse that signed SQLite step lookup,
            # not iterate through the whole source a second time.
            details = catalog.by_id[1]._details
            self.assertIsNone(details._sources._objectives_by_step)
            with patch.object(QuestCatalog, "_load_source", side_effect=self.compile):
                catalog.get_detail(1)
            self.assertEqual(
                details._sources._objectives_by_step[10], [40, 41]
            )
            # An explicit source read after get_detail() reopens the JSON
            # stream. Close it before TemporaryDirectory cleanup on Windows.
            with closing(details._sources):
                rows = details._sources.rows(root / "quest_objectives.json")
                with patch.object(
                    rows,
                    "items",
                    side_effect=AssertionError("unexpected full objective scan"),
                ):
                    selected = list(
                        details._sources.objectives_for_steps(
                            root / "quest_objectives.json", {10}
                        )
                    )
                self.assertEqual([row["id"] for row in selected], [40, 41])

            # Force a genuinely cold detail in the reopened catalogue:
            # otherwise the stored rich record would bypass the index lookup.
            # sqlite3.Connection.__exit__ commits but does NOT close the file.
            # Windows refuses TemporaryDirectory cleanup while it is open.
            with closing(sqlite3.connect(details.path)) as connection:
                with connection:
                    connection.execute("UPDATE quests SET detail=NULL WHERE id=1")
            reopened = load_lazy_catalog(root, cache_root=cache_root)
            reopened_details = reopened.by_id[1]._details
            with patch.object(QuestCatalog, "_load_source", side_effect=self.compile):
                reopened.get_detail(1)
            self.assertEqual(
                reopened_details._sources._objectives_by_step[10], [40, 41]
            )

    def test_detail_cache_profile_exposes_source_phases_without_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog = self.build(Path(tmp))
            details = catalog.quests[0]._details
            self.assertEqual(catalog.detail_cache_info()["last_source_phases_ms"], {})
            details._sources.last_detail_phase_ms = {"objective_lookup": 9.5}
            self.assertEqual(
                catalog.detail_cache_info()["last_source_phases_ms"],
                {"objective_lookup": 9.5},
            )
            # No real detail, source traversal, or cache warmup is triggered.
            self.assertEqual(catalog.detail_cache_info()["loads"], 0)

    def test_runtime_details_reuse_preload_source_offset_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "cache"
            catalog = self.build(root)
            details = catalog.quests[0]._details
            self.assertEqual(
                details._sources.cache_root,
                (root / "cache" / "source_offsets"),
            )
            self.assertEqual(details._sources.context, {})
            with patch.object(QuestCatalog, '_load_source', side_effect=self.compile):
                catalog.get_detail(1)
            self.assertEqual(details._sources.context["quest_names"][1], "Quête 1")
            self.assertEqual(
                details._sources.context["quest_to_achievements"][1],
                ["Succès test"],
            )

    def test_controlled_preload_primes_detail_offsets_one_mapping_at_a_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            created = []

            class Mapping:
                def __len__(self):
                    return 1

            class Sources:
                def __init__(self, cache_root, *, disk_backed=False):
                    self.cache_root = cache_root
                    self.disk_backed = disk_backed
                    self.closed = False
                    created.append(self)

                def mapping(self, *_args, **_kwargs):
                    return Mapping()

                def close(self):
                    self.closed = True

            with patch("app.quest_catalog_details.QuestSources", Sources):
                count = ensure_detail_source_offsets(root, cache_root=root / "cache")

            self.assertEqual(count, 21)
            self.assertEqual(len(created), count)
            self.assertTrue(all(source.closed for source in created))
            self.assertTrue(all(source.disk_backed for source in created))

    def test_index_does_not_compile_details_and_a_b_a_reuses_data(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(QuestCatalog, '_load_source', side_effect=self.compile) as load:
            catalog = self.build(Path(tmp))
            self.assertEqual(catalog.detail_cache_info()['loads'], 0)
            self.assertEqual([row.name for row in catalog.quests], ['Quête 1', 'Quête 2', 'Quête 3'])
            load.assert_not_called()
            a = catalog.by_id[1].steps
            self.assertEqual(catalog.by_id[2].steps[0].id, 20)
            self.assertIs(catalog.by_id[1].steps, a)
            self.assertEqual([call.kwargs['quest_ids'] for call in load.call_args_list], [{1}, {2}])

    def test_bounded_cache_reloads_evicted_data_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(QuestCatalog, '_load_source', side_effect=self.compile) as load:
            root = Path(tmp)
            catalog = self.build(root, limit=1)
            a = asdict(catalog.get_detail(1))
            catalog.get_detail(2)
            self.assertEqual(catalog.detail_cache_info()['records'], 1)
            self.assertEqual(asdict(catalog.get_detail(1)), a)
            self.assertEqual(load.call_count, 2)
            reopened = load_lazy_catalog(root, cache_root=root / 'cache')
            self.assertEqual(asdict(reopened.get_detail(1)), a)
            self.assertEqual(load.call_count, 2)

    def test_source_change_cannot_mix_old_list_and_new_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = self.build(root)
            (root / 'quests.json').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'sources Quêtes ont changé'):
                catalog.get_detail(1)

    def test_concurrent_detail_requests_compile_once_without_blocking_cache_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = self.build(Path(tmp))
            entered, release = threading.Event(), threading.Event()
            def compile(*args, **kwargs):
                entered.set()
                release.wait(2)
                return self.compile(*args, **kwargs)
            with patch.object(QuestCatalog, '_load_source', side_effect=compile) as load:
                threads = [threading.Thread(target=catalog.get_detail, args=(1,)) for _ in range(2)]
                for thread in threads:
                    thread.start()
                self.assertTrue(entered.wait(1))
                self.assertFalse(catalog.is_detail_cached(1))
                release.set()
                for thread in threads:
                    thread.join(2)
                    self.assertFalse(thread.is_alive())
                self.assertEqual(load.call_count, 1)

    def test_cold_source_index_reads_only_light_sources_and_preserves_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / 'cache'

            def write_rows(name, rows):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({'references': {'RefIds': [
                    {'rid': row['id'], 'data': row} for row in rows
                ]}}, ensure_ascii=False), encoding='utf-8')

            language = root / 'languages/fr.json'
            language.parent.mkdir(parents=True)
            language.write_text(json.dumps({'entries': {
                '101': 'Quête légère',
                '102': 'Prérequis',
                '110': 'Catégorie test',
                '120': 'Succès test',
                '130': 'Série test',
            }}, ensure_ascii=False), encoding='utf-8')
            write_rows('quests.json', [
                {'id': 1, 'nameId': 101, 'categoryId': 10, 'levelMin': 5, 'levelMax': 20,
                 'startCriterion': 'Qf=2', 'isPartyQuest': 1, 'stepIds': {'Array': [10]}},
                {'id': 2, 'nameId': 102, 'categoryId': 10, 'levelMin': 1, 'levelMax': 2},
            ])
            write_rows('quest_categories.json', [{'id': 10, 'nameId': 110}])
            write_rows('achievements.json', [{'id': 20, 'nameId': 120, 'categoryId': 30, 'order': 1}])
            write_rows('achievement_objectives.json', [
                {'id': 21, 'achievementId': 20, 'criterion': 'Qf=1', 'order': 0},
            ])
            write_rows('achievement_categories.json', [{'id': 30, 'nameId': 130}])

            reads = []
            original_mapping = QuestSources.mapping

            def track_mapping(source, path, field, *, doduda=False, required=None):
                reads.append(Path(path).relative_to(root).as_posix())
                return original_mapping(
                    source,
                    path,
                    field,
                    doduda=doduda,
                    required=required,
                )

            with (
                patch.object(QuestSources, 'mapping', new=track_mapping),
                patch('app.quest_catalog.QuestStep', side_effect=AssertionError('detail loaded')),
                patch('app.quest_catalog.QuestObjective', side_effect=AssertionError('objective loaded')),
            ):
                catalog = load_lazy_catalog(root, cache_root=cache_root)

            self.assertEqual(set(reads), {
                'languages/fr.json',
                'quests.json',
                'quest_categories.json',
                'achievements.json',
                'achievement_objectives.json',
                'achievement_categories.json',
            })
            for heavy_source in (
                'maps_information.json',
                'subareas.json',
                'areas.json',
                'quest_steps.json',
                'quest_objectives.json',
            ):
                self.assertNotIn(heavy_source, reads)

            summary = catalog.by_id[1]
            self.assertEqual(summary.id, 1)
            self.assertEqual(summary.name, 'Quête légère')
            self.assertEqual(summary.category, 'Catégorie test')
            self.assertEqual((summary.level_min, summary.level_max), (5, 20))
            self.assertEqual(summary.start_criterion, 'Qf=2')
            self.assertEqual(summary.zones, ())
            self.assertEqual(summary.achievements, ('Succès test',))
            self.assertEqual(summary.prerequisites, ('Quete terminee: Prérequis',))
            self.assertEqual(summary.info, ('Combat de groupe / quete de groupe',))
            self.assertEqual(catalog.detail_cache_info()['loads'], 0)
            self.assertEqual(len(catalog.achievement_series), 1)
            self.assertEqual(catalog.achievement_series[0].quest_ids, (1,))

    def test_lazy_catalog_search_callback_does_not_pin_released_catalogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalogue = self.build(Path(tmp))
            search = catalogue.load_search_documents
            reference = weakref.ref(catalogue)
            del catalogue
            # No gc.collect(): the catalogue must be freed by reference-count
            # ownership when Home releases it, not at a later GC cycle.
            self.assertIsNone(reference())
            self.assertTrue(callable(search))

    def test_explicit_search_compiles_bounded_batches_without_filling_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                'app.quest_catalog_details._source_index',
                return_value=([record(i) for i in range(70)], (), {
                    "achievement_names": {},
                    "quest_names": {},
                    "quest_to_achievements": {},
                }),
            ):
                catalog = load_lazy_catalog(root, cache_root=root / 'cache')
            with patch.object(QuestCatalog, '_load_source', side_effect=self.compile) as load:
                self.assertEqual(len(catalog.load_search_documents()), 70)
                self.assertEqual([len(call.kwargs['quest_ids']) for call in load.call_args_list], [32, 32, 6])
                self.assertTrue(all(not call.kwargs['include_enrichment'] for call in load.call_args_list))
                self.assertEqual(catalog.detail_cache_info()['records'], 0)
                catalog.load_search_documents()
                self.assertEqual(load.call_count, 3)


class DeferredQuestUiTests(unittest.TestCase):
    def test_fast_selection_renders_only_latest_and_reuses_a(self):
        from PySide6.QtWidgets import QApplication
        from app.pages.lazy_quests_page import LazyQuestsPage
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = QuestDetailsTests().build(root)
            entered, release = threading.Event(), threading.Event()
            def compile(*args, **kwargs):
                if kwargs['quest_ids'] == {1}:
                    entered.set()
                    release.wait(3)
                return QuestDetailsTests.compile(*args, **kwargs)
            page = LazyQuestsPage(lambda _: None, catalog=catalog, progress_path=root/'progress.json',
                achievement_progress_path=root/'success.json', profile_path=root/'profile.json',
                client_index_path=root/'clients.json', owned_items_path=root/'owned.json')
            try:
                self.assertEqual(catalog.detail_cache_info()['loads'], 0)
                with patch.object(QuestCatalog, '_load_source', side_effect=compile) as load:
                    page.select_quest(1, persist=False)
                    self.assertTrue(entered.wait(1))
                    page.select_quest(2, persist=False)
                    release.set()
                    deadline = time.monotonic() + 4
                    while page._detail_pending and time.monotonic() < deadline:
                        app.processEvents()
                        time.sleep(.005)
                    self.assertFalse(page._detail_pending)
                    self.assertEqual(page.quest_detail_view.current_quest_id, 2)
                    page.select_quest(1, persist=False)
                    self.assertEqual(page.quest_detail_view.current_quest_id, 1)
                    self.assertEqual(load.call_count, 2)
                    self.assertEqual(catalog.detail_cache_info()['records'], 2)
            finally:
                release.set()
                if page._detail_worker is not None:
                    page._detail_worker.join(4)
                page.deleteLater()
                app.processEvents()


class SelectedJsonValueTests(unittest.TestCase):
    def test_selected_object_values_preserve_localized_text(self):
        payload = {
            "metadata": {"entries": {"999": "nested decoy"}},
            "entries": {
                "101": "Quêtes",
                "102": "Donjons",
                "103": "Texte avec \"guillemets\" et été",
                "104": {"nested": [1, True, None]},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fr.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            selected = read_selected_json_object_values(
                path,
                "entries",
                {"101", "103", "104"},
            )
        self.assertEqual(
            selected,
            {
                "101": "Quêtes",
                "103": "Texte avec \"guillemets\" et été",
                "104": {"nested": [1, True, None]},
            },
        )


class JsonSourceIndexTests(unittest.TestCase):
    def test_unicode_escaped_quotes_nested_values_and_cache_round_trip(self):
        values = {'1': {'text': 'été \\" [ }', 'nested': [True, None, {'id': 4}]}, '2': 'bonjour'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.json'
            path.write_text(json.dumps({'quests': values}, ensure_ascii=False), encoding='utf-8')
            for _ in range(2):
                mapping = JsonSourceMapping(path, root, 'quests')
                self.assertEqual(dict(mapping), values)
                mapping.close()

    def test_offset_index_build_never_reads_whole_source_bytes(self):
        values = {
            "1": {"text": "été", "nested": [1, {"x": True}]},
            "2": {"text": "bonjour"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "source.json"
            path.write_text(
                json.dumps({"quests": values}, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("monolithic source read forbidden"),
            ):
                mapping = JsonSourceMapping(path, root / "offsets", "quests")
                try:
                    self.assertEqual(dict(mapping), values)
                finally:
                    mapping.close()

    def test_doduda_reads_data_ids_without_confusing_nested_ids(self):
        rows = [{'data': {'nested': {'id': 999}, 'id': 7}}, {'data': {'id': 8}}, {'data': {'value': 3}}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.json'
            path.write_text(json.dumps({'references': {'RefIds': rows}}))
            mapping = JsonSourceMapping(path, root, 'RefIds', doduda=True)
            self.assertEqual(dict(mapping), {7: rows[0]['data'], 8: rows[1]['data']})
            mapping.close()


if __name__ == '__main__':
    unittest.main()
