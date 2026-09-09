from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import quest_catalog
from app.constants import KEY_SELECTED_CHARACTER, KEY_SESSION_ORDER
from app.pages.quest_character_cache import (
    cached_load_quest_characters,
    clear_quest_character_cache,
)


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class QuestCharacterCacheTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_quest_character_cache()

    def test_selected_character_only_change_reuses_cached_slot_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            clients = root / "client_index.json"
            bindings = root / "bindings.json"
            _write(profile, {KEY_SESSION_ORDER: ["Testeur"]})
            _write(clients, {"clients": [{"character_name": "Testeur", "slot": 1}]})
            _write(bindings, {"slots": {}})
            clear_quest_character_cache()

            calls = 0

            def fake_loader(*_args, **_kwargs):
                nonlocal calls
                calls += 1
                return [quest_catalog.QuestCharacter("character:1", "Testeur", 1, True)]

            with patch(
                "app.pages.quest_character_cache._ORIGINAL_LOAD_QUEST_CHARACTERS",
                side_effect=fake_loader,
            ):
                first = cached_load_quest_characters(profile, clients, 8, bindings)
                self.assertEqual(first[0].label, "Testeur")
                self.assertEqual(calls, 1)

                _write(
                    profile,
                    {
                        KEY_SESSION_ORDER: ["Testeur"],
                        KEY_SELECTED_CHARACTER: "slot:1",
                        "padding": "make-file-size-change-visible",
                    },
                )
                second = cached_load_quest_characters(profile, clients, 8, bindings)
                self.assertEqual(second[0].label, "Testeur")
                self.assertEqual(calls, 1)

                _write(profile, {KEY_SESSION_ORDER: ["Autre"]})
                cached_load_quest_characters(profile, clients, 8, bindings)
                self.assertEqual(calls, 2)

                _write(
                    clients,
                    {
                        "clients": [
                            {"character_name": "Autre", "slot": 1},
                            {"character_name": "Second", "slot": 2},
                        ]
                    },
                )
                cached_load_quest_characters(profile, clients, 8, bindings)
                self.assertEqual(calls, 3)

    def test_character_order_change_beyond_eight_slots_invalidates_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            clients = root / "client_index.json"
            bindings = root / "bindings.json"
            order = [f"Character {index}" for index in range(1, 10)]
            _write(profile, {KEY_SESSION_ORDER: order})
            _write(clients, {"clients": []})
            _write(bindings, {"slots": {}})
            clear_quest_character_cache()

            calls = 0

            def fake_loader(*_args, **_kwargs):
                nonlocal calls
                calls += 1
                return []

            with patch(
                "app.pages.quest_character_cache._ORIGINAL_LOAD_QUEST_CHARACTERS",
                side_effect=fake_loader,
            ):
                cached_load_quest_characters(profile, clients, 8, bindings)
                self.assertEqual(calls, 1)

                changed_order = list(order)
                changed_order[8] = "Character Nine Changed"
                _write(profile, {KEY_SESSION_ORDER: changed_order})

                cached_load_quest_characters(profile, clients, 8, bindings)
                self.assertEqual(calls, 2)

    def test_cached_loader_applies_canonical_order_after_connected_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            clients = root / "client_index.json"
            bindings = root / "bindings.json"
            _write(profile, {KEY_SESSION_ORDER: ["Beta", "Alpha", "Gamma"]})
            _write(clients, {"clients": []})
            _write(bindings, {"slots": {}})
            clear_quest_character_cache()

            all_rows = [
                quest_catalog.QuestCharacter("character:1", "Alpha", 1, True),
                quest_catalog.QuestCharacter("character:3", "Gamma", 3, True),
                quest_catalog.QuestCharacter("character:2", "Beta", 2, False),
            ]

            def fake_loader(
                _profile,
                _clients,
                _slot_count,
                _bindings,
                connected_only,
            ):
                if connected_only:
                    return [row for row in all_rows if row.connected]
                return list(all_rows)

            with patch(
                "app.pages.quest_character_cache._ORIGINAL_LOAD_QUEST_CHARACTERS",
                side_effect=fake_loader,
            ):
                known = cached_load_quest_characters(
                    profile,
                    clients,
                    8,
                    bindings,
                    False,
                )
                self.assertEqual(
                    [row.label for row in known],
                    ["Beta", "Alpha", "Gamma"],
                )

                connected = cached_load_quest_characters(
                    profile,
                    clients,
                    8,
                    bindings,
                    True,
                )
                self.assertEqual(
                    [row.label for row in connected],
                    ["Alpha", "Gamma"],
                )

if __name__ == "__main__":
    unittest.main()
