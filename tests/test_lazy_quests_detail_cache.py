from __future__ import annotations

import json
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

def test_bulk_compact_quest_evidence_matches_point_results_with_two_sql_chunks() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "details.sqlite3"
        with sqlite3.connect(path) as connection:
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


def test_quest_provider_keeps_optional_pack_semantics_in_bulk_mode() -> None:
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
        with patch.object(provider, "guide_evidence", return_value={"pack": True}) as point:
            assert provider.guide_evidence_many([4, 4]) == {4: {"pack": True}}
        point.assert_called_once_with(4)
        batch.assert_called_once()
