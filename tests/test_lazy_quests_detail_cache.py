from __future__ import annotations

import json
from contextlib import closing
import unittest
import os
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.quest_catalog_details import QuestDetails
from app.modules.encyclopedia.providers.quest_provider import QuestProvider
import app.quest_catalog_details as quest_details_module

from app.pages.lazy_quests_page import LazyQuestsPage
from app.pages.quests_page import QuestsPage


def test_same_quest_detail_signature_skips_full_rerender() -> None:
    signature = (42, "slot:1", "series", (1, 2, 3))
    fake = SimpleNamespace(
        _last_quest_detail_signature=signature,
        _quest_detail_signature=lambda _quest_id: signature,
        catalog=SimpleNamespace(deferred_details=False),
        quest_detail_view=SimpleNamespace(current_quest_id=42),
    )

    with patch.object(QuestsPage, "show_quest_detail") as base_render:
        LazyQuestsPage.show_quest_detail(fake, 42)

    base_render.assert_not_called()


def test_changed_quest_detail_signature_renders_once_and_caches_result() -> None:
    old_signature = (42, "slot:1", "series", "old")
    new_signature = (42, "slot:1", "series", "new")
    detail_view = SimpleNamespace(current_quest_id=None)
    fake = SimpleNamespace(
        _last_quest_detail_signature=old_signature,
        _quest_detail_signature=lambda _quest_id: new_signature,
        catalog=SimpleNamespace(deferred_details=False),
        quest_detail_view=detail_view,
    )

    def render(_self, quest_id: int) -> None:
        detail_view.current_quest_id = int(quest_id)

    with patch.object(QuestsPage, "show_quest_detail", autospec=True, side_effect=render) as base_render:
        LazyQuestsPage.show_quest_detail(fake, 42)

    base_render.assert_called_once_with(fake, 42)
    assert fake._last_quest_detail_signature == new_signature


def test_existing_last_quest_id_skips_profile_write() -> None:
    fake = SimpleNamespace(load_last_quest_id=lambda: 42)

    with patch.object(QuestsPage, "save_last_quest_id") as base_save:
        LazyQuestsPage.save_last_quest_id(fake, 42)

    base_save.assert_not_called()


def test_changed_last_quest_id_persists_once() -> None:
    fake = SimpleNamespace(load_last_quest_id=lambda: 41)

    with patch.object(QuestsPage, "save_last_quest_id", autospec=True) as base_save:
        LazyQuestsPage.save_last_quest_id(fake, 42)

    base_save.assert_called_once_with(fake, 42)



class QuestObjectiveStepIndexTests(unittest.TestCase):
    def test_first_rich_detail_primes_index_once_without_intermediate_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quests.sqlite3"
            raw = {"15": [101, 102], "16": [103]}
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
                connection.execute(
                    "INSERT INTO metadata VALUES ('objective_step_ids', ?)",
                    (json.dumps(raw),),
                )
                connection.commit()
            details = QuestDetails(Path(directory), path, ())
            prime = Mock()
            details._sources = SimpleNamespace(prime_objective_steps=prime)
            details._prime_objective_step_index()
            prime.assert_called_once_with(raw)
            self.assertTrue(details._objective_step_index_checked)
            details._prime_objective_step_index()
            prime.assert_called_once()

    def test_invalid_step_index_does_not_mark_ready_or_prime_partial_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quests.sqlite3"
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
                connection.execute(
                    "INSERT INTO metadata VALUES ('objective_step_ids', ?)",
                    (json.dumps({"15": ["not-an-id"]}),),
                )
                connection.commit()
            details = QuestDetails(Path(directory), path, ())
            prime = Mock()
            details._sources = SimpleNamespace(prime_objective_steps=prime)
            with self.assertRaises(ValueError):
                details._prime_objective_step_index()
            prime.assert_not_called()
            self.assertFalse(details._objective_step_index_checked)


class QuestEvidenceBatchTests(unittest.TestCase):
    def test_bulk_compact_quest_evidence_matches_point_results_with_two_sql_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "details.sqlite3"
            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    "CREATE TABLE quests(id INTEGER PRIMARY KEY, guide_evidence TEXT)"
                )
                connection.executemany(
                    "INSERT INTO quests VALUES (?, ?)",
                    [
                        (qid, json.dumps({"combats": [{"objective_id": qid}]}))
                        for qid in range(1, 451)
                    ],
                )
                connection.execute(
                    "UPDATE quests SET guide_evidence=? WHERE id=4",
                    ("malformed",),
                )
                connection.commit()
            details = QuestDetails(Path(directory), path, ())
            expected = {
                qid: details.guide_evidence(qid)
                for qid in (1, 4, 401, 450)
            }
            with patch.object(
                quest_details_module, "_connect",
                wraps=quest_details_module._connect,
            ) as connect:
                batch = details.guide_evidence_many(
                    [1, 4, 401, 450, 1] + list(range(1, 451))
                )
            assert connect.call_count == 1  # 450 records, 2 SQL batches, 1 handle.
            assert len(batch) == 450
            assert {qid: batch[qid] for qid in expected} == expected
            assert details.guide_evidence_many([9999]) == {}
    
    
    def test_quest_provider_keeps_optional_pack_semantics_in_bulk_mode(self) -> None:
        batch = Mock(return_value={4: {"combats": [{"objective_id": 77}]}})
        fake_catalog = SimpleNamespace(
            guide_evidence_many=batch,
            guide_evidence=Mock(return_value={}),
            by_id={4: object()},
        )
        with tempfile.TemporaryDirectory() as directory:
            provider = QuestProvider(catalog=fake_catalog, data_dir=Path(directory))
            assert provider.guide_evidence_many([4, 4]) == {
                4: {"combats": [{"objective_id": 77}]}
            }
            batch.assert_called_once_with((4,))
    
            provider._pack_guide_evidence = {4: {"combats": [{"objective_id": 99}]}}
            # Optional accepted packs are only active for the canonical data
            # directory; the bulk method must preserve that exact boundary.
            with patch("app.modules.encyclopedia.providers.quest_provider._is_default_data_dir", return_value=True):
                assert provider.guide_evidence_many([4, 4, 777]) == {
                    4: {"combats": [{"objective_id": 99}]},
                    777: {},
                }
            batch.assert_called_with((4, 777))
            assert batch.call_count == 2
    
    def test_pack_root_environment_keeps_bulk_sql_read_enabled(self) -> None:
        baseline = {"combats": [{"objective_id": 37, "monster": "Tofu"}]}
        batch = Mock(return_value={4: baseline})
        catalogue = SimpleNamespace(
            guide_evidence_many=batch,
            guide_evidence=Mock(side_effect=AssertionError("no per-quest SQL")),
            by_id={4: object()},
        )
        with tempfile.TemporaryDirectory() as directory:
            provider = QuestProvider(catalog=catalogue, data_dir=Path(directory))
            with (
                patch("app.modules.encyclopedia.providers.quest_provider._is_default_data_dir", return_value=True),
                patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": directory}),
                patch(
                    "app.distribution.quest_evidence_pack.load_accepted_quest_guide_evidence",
                    return_value={},
                ) as loader,
            ):
                self.assertEqual(provider.guide_evidence_many([4, 4]), {4: baseline})
                self.assertEqual(provider.guide_evidence_many([4]), {4: baseline})
            loader.assert_called_once()
            self.assertEqual(batch.call_count, 2)

    def test_pack_root_overrides_only_canonical_ids_and_copies_values(self) -> None:
        baseline = {"combats": [{"objective_id": 37, "monster": "Tofu"}]}
        offered = {"combats": [{"objective_id": 88, "monster": "Bouftou"}]}
        pack = {4: offered, 9: {"fake": True}}
        catalogue = SimpleNamespace(
            guide_evidence_many=Mock(return_value={4: baseline}),
            guide_evidence=Mock(side_effect=AssertionError("no per-quest SQL")),
            by_id={4: object()},
        )
        with tempfile.TemporaryDirectory() as directory:
            provider = QuestProvider(catalog=catalogue, data_dir=Path(directory))
            with (
                patch("app.modules.encyclopedia.providers.quest_provider._is_default_data_dir", return_value=True),
                patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": directory}),
                patch(
                    "app.distribution.quest_evidence_pack.load_accepted_quest_guide_evidence",
                    return_value=pack,
                ) as loader,
            ):
                result = provider.guide_evidence_many([4, 9, 10])
                self.assertEqual(result[4], offered)
                self.assertEqual(result[9], {})
                self.assertEqual(result[10], {})
                self.assertIsNot(result[4], offered)
                result[4]["combats"].clear()
                self.assertTrue(offered["combats"])
            loader.assert_called_once()

    def test_home_release_drops_optional_guide_pack_and_loads_it_only_on_reentry(self) -> None:
        pack = {4: {"combats": [{"objective_id": 1, "monster": "Tofu"}]}}
        with tempfile.TemporaryDirectory() as directory:
            provider = QuestProvider(catalog=object(), data_dir=Path(directory))
            with (
                patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": directory}),
                patch(
                    "app.distribution.quest_evidence_pack.load_accepted_quest_guide_evidence",
                    return_value=pack,
                ) as loader,
            ):
                self.assertIs(provider._accepted_guide_evidence_pack(), pack)
                self.assertIs(provider._accepted_guide_evidence_pack(), pack)
                loader.assert_called_once()
                provider.release_catalogue()
                self.assertIsNone(provider._catalog)
                self.assertIsNone(provider._pack_guide_evidence)
                self.assertIs(provider._accepted_guide_evidence_pack(), pack)
                self.assertEqual(loader.call_count, 2)


class AchievementPreparationBatchTests(unittest.TestCase):
    def test_preparation_batches_only_canonical_quest_refs_in_order(self) -> None:
        from app.modules.encyclopedia.models.entity_ref import EntityRef
        from app.modules.encyclopedia.providers.achievement_provider import AchievementProvider

        refs = (
            EntityRef("quest", 4, "Première quête"),
            EntityRef("monster", 18, "Monstre"),
            EntityRef("quest", 5, "Deuxième quête"),
            EntityRef("quest", 4, "Doublon ignoré"),
            EntityRef("quest", "not-an-id", "Référence invalide"),
        )
        evidence = {
            4: {"items": [{"id": 7, "quantity": 3}], "combats": []},
            5: {"items": [], "combats": [{"objective_id": 9, "monster": "Tofu"}]},
        }
        bulk = Mock(return_value=evidence)
        individual = Mock(side_effect=AssertionError("no per-quest SQL"))
        owner = SimpleNamespace(
            get_by_id=Mock(return_value=SimpleNamespace(
                resolved_linked_quests=refs, linked_quests=(),
            )),
            quest_provider=SimpleNamespace(
                guide_evidence_many=bulk,
                guide_evidence=individual,
            ),
        )

        result = AchievementProvider.get_quest_preparation(owner, 42)
        self.assertEqual(list(bulk.call_args.args[0]), [4, 5])
        individual.assert_not_called()
        self.assertEqual(result, (
            {
                "quest_id": 4, "quest_name": "Première quête",
                "items": [{"id": 7, "quantity": 3}], "combats": [],
            },
            {
                "quest_id": 5, "quest_name": "Deuxième quête",
                "items": [], "combats": [{"objective_id": 9, "monster": "Tofu"}],
            },
        ))
        result[0]["items"][0]["quantity"] = 100
        self.assertEqual(evidence[4]["items"][0]["quantity"], 3)

    def test_preparation_supports_old_quest_provider_without_batch_api(self) -> None:
        from app.modules.encyclopedia.models.entity_ref import EntityRef
        from app.modules.encyclopedia.providers.achievement_provider import AchievementProvider

        point = Mock(return_value={
            "items": [{"id": 3, "quantity": 1}], "combats": [],
        })
        owner = SimpleNamespace(
            get_by_id=lambda _id: SimpleNamespace(
                resolved_linked_quests=(), linked_quests=(
                    EntityRef("quest", 42, "Quête"),
                ),
            ),
            quest_provider=SimpleNamespace(guide_evidence=point),
        )
        result = AchievementProvider.get_quest_preparation(owner, 99)
        point.assert_called_once_with(42)
        self.assertEqual(result[0]["quest_id"], 42)
        self.assertEqual(result[0]["items"][0]["quantity"], 1)
