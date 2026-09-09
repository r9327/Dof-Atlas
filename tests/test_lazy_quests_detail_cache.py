from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

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
