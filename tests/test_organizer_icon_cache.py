from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.pages import organizer_page
from app.pages.organizer_icon_cache import (
    cached_dofus_class_key_for_character_name,
    clear_organizer_icon_cache,
)


def _payload(class_key: str) -> dict[str, object]:
    return {
        "clients": [
            {
                "character_name": "Testeur",
                "name": "Testeur",
                "class_key": class_key,
            }
        ]
    }


def test_character_class_cache_reads_client_index_once_until_file_changes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "client_index.json"
        path.write_text(json.dumps(_payload("pandawa")), encoding="utf-8")
        clear_organizer_icon_cache()

        original_read = organizer_page.read_json
        calls = 0

        def counted_read(target, default):
            nonlocal calls
            calls += 1
            return original_read(target, default)

        with (
            patch.object(organizer_page, "CLIENT_INDEX_JSON", path),
            patch.object(organizer_page, "read_json", side_effect=counted_read),
        ):
            assert cached_dofus_class_key_for_character_name("Testeur") == "pandawa"
            assert cached_dofus_class_key_for_character_name("Testeur") == "pandawa"
            assert cached_dofus_class_key_for_character_name("Testeur") == "pandawa"
            assert calls == 1

            # Different size guarantees a signature change even on filesystems
            # whose mtime resolution is coarse.
            path.write_text(json.dumps(_payload("huppermage"), indent=2), encoding="utf-8")
            assert cached_dofus_class_key_for_character_name("Testeur") == "huppermage"
            assert calls == 2

        clear_organizer_icon_cache()


def test_ambiguous_character_class_remains_unresolved() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "client_index.json"
        payload = {
            "clients": [
                {"character_name": "Testeur", "class_key": "pandawa"},
                {"character_name": "Testeur", "class_key": "huppermage"},
            ]
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        clear_organizer_icon_cache()

        with patch.object(organizer_page, "CLIENT_INDEX_JSON", path):
            assert cached_dofus_class_key_for_character_name("Testeur") is None

        clear_organizer_icon_cache()
