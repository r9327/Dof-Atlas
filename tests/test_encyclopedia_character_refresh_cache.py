from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage


def _fake(signature: tuple[object, ...], *, cached: tuple[object, ...] | None, has_characters: bool = True):
    fake = SimpleNamespace(
        _character_sources_signature=cached,
        characters=[object()] if has_characters else [],
    )
    fake._current_character_sources_signature = lambda: signature
    return fake


def test_unchanged_character_sources_skip_legacy_reload() -> None:
    signature = ("profile", (1, 10), "clients", (2, 20))
    fake = _fake(signature, cached=signature)

    with patch.object(EncyclopediaPage, "_refresh_characters_base") as legacy_refresh:
        EncyclopediaPage.refresh_characters(fake)

    legacy_refresh.assert_not_called()


def test_changed_character_sources_reload_once_and_publish_signature() -> None:
    old_signature = ("profile", (1, 10), "clients", (2, 20))
    new_signature = ("profile", (3, 30), "clients", (4, 40))
    fake = _fake(new_signature, cached=old_signature)

    with patch.object(EncyclopediaPage, "_refresh_characters_base") as legacy_refresh:
        EncyclopediaPage.refresh_characters(fake)

    legacy_refresh.assert_called_once_with(fake)
    assert fake._character_sources_signature == new_signature


def test_empty_character_state_is_reloaded_even_with_same_signature() -> None:
    signature = ("profile", (1, 10), "clients", (2, 20))
    fake = _fake(signature, cached=signature, has_characters=False)

    with patch.object(EncyclopediaPage, "_refresh_characters_base") as legacy_refresh:
        EncyclopediaPage.refresh_characters(fake)

    legacy_refresh.assert_called_once_with(fake)
