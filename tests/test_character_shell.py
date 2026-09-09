from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox

from app.constants import KEY_SELECTED_CHARACTER, KEY_SESSION_ORDER
from app.network.character_runtime_state import CharacterRuntimeStateStore
from app.pages.character_page import CharacterPage as RealCharacterPage
from app.quest_catalog import QuestCharacter
import main as app_main


class CharacterShellCanonicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_canonical_home_lists_connected_only_while_character_page_keeps_all_known(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profiles.json"
            clients = root / "clients.json"
            bindings = root / "network_character_bindings.json"
            profile.write_text(
                json.dumps({KEY_SELECTED_CHARACTER: "character:42"}),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps(
                    {
                        "characters": {
                            "42": {
                                "name": "Alpha",
                                "pid": 111,
                                "organizer_slot": 1,
                                "source": "verified_network_identity",
                            },
                            "84": {
                                "name": "Beta",
                                "organizer_slot": 2,
                                "source": "verified_network_identity",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            clients.write_text(
                json.dumps(
                    {
                        "clients": [
                            {"character_name": "Alpha", "pid": 111, "slot": 1}
                        ]
                    }
                ),
                encoding="utf-8",
            )

            class TestCharacterPage(RealCharacterPage):
                constructed = 0

                def __init__(self):
                    self.__class__.constructed += 1
                    super().__init__(
                        profile_path=profile,
                        client_index_path=clients,
                        binding_path=bindings,
                        icon_resolver=lambda _label: "",
                    )

            class HomeStub:
                def __init__(self) -> None:
                    self.last_character = None

                def set_character(self, key: str, label: str, icon_path: str) -> None:
                    self.last_character = (key, label, icon_path)

            class DummyWindow:
                def __init__(self) -> None:
                    self.current_character_key = "character:42"
                    self.current_character_label = "Alpha"
                    self.characters = []
                    self.character_combo = QComboBox()
                    self.character_combo.currentIndexChanged.connect(
                        lambda _index: self.on_global_character_changed()
                    )
                    self.page_widgets = {}
                    self.page_nav_group = {}
                    self.home_page = HomeStub()
                    self.persist_count = 0
                    self.original_sync_count = 0
                    self.last_page = ""
                    self.quit_requested = False
                    self._background_services_stopped = False
                    self.runtime = None

                open_character_selector = app_main.AtlasWindow.open_character_selector
                refresh_global_characters = app_main.AtlasWindow.refresh_global_characters
                _ordered_characters = staticmethod(app_main.AtlasWindow._ordered_characters)
                _known_characters = app_main.AtlasWindow._known_characters
                _connected_characters = app_main.AtlasWindow._connected_characters
                _activate_character_from_page = app_main.AtlasWindow._activate_character_from_page
                _delete_character_from_page = app_main.AtlasWindow._delete_character_from_page
                _apply_character_order_from_page = app_main.AtlasWindow._apply_character_order_from_page
                _refresh_runtime_hotkeys_for_client_mapping = (
                    app_main.AtlasWindow._refresh_runtime_hotkeys_for_client_mapping
                )
                _runtime_client_mapping_signature = (
                    app_main.AtlasWindow._runtime_client_mapping_signature
                )
                _loaded_runtime_client_mapping_signature = (
                    app_main.AtlasWindow._loaded_runtime_client_mapping_signature
                )
                _int_value = staticmethod(app_main.AtlasWindow._int_value)

                def character_icon_path(self, _label: str) -> str:
                    return ""

                def persist_selected_character(self) -> None:
                    self.persist_count += 1

                def sync_selected_character_to_pages(self) -> None:
                    self.original_sync_count += 1

                def on_global_character_changed(self) -> None:
                    character = self.character_combo.currentData()
                    if character is None:
                        return
                    key = str(getattr(character, "key", "") or "")
                    label = str(getattr(character, "label", "") or "")
                    if not key or (
                        key == self.current_character_key
                        and label == self.current_character_label
                    ):
                        return
                    self.current_character_key = key
                    self.current_character_label = label
                    self.persist_selected_character()
                    self.home_page.set_character(key, label, self.character_icon_path(label))
                    self.sync_selected_character_to_pages()

                def register_page(self, name: str, page) -> int:
                    self.page_widgets[name] = page
                    return len(self.page_widgets) - 1

                def show_page(self, name: str) -> None:
                    self.last_page = name

            with (
                patch.object(app_main, "PROFILE_FILE", profile),
                patch.object(app_main, "CLIENT_INDEX_JSON", clients),
                patch.object(app_main, "NETWORK_CHARACTER_BINDINGS_FILE", bindings),
                patch.object(
                    app_main,
                    "character_runtime_state",
                    return_value=CharacterRuntimeStateStore(),
                ),
                patch.object(app_main, "CharacterPage", TestCharacterPage),
            ):
                original_sync = DummyWindow.sync_selected_character_to_pages
                original_selector = DummyWindow.open_character_selector
                self.assertIs(DummyWindow.sync_selected_character_to_pages, original_sync)
                self.assertIs(
                    DummyWindow.refresh_global_characters,
                    app_main.AtlasWindow.refresh_global_characters,
                )
                self.assertIs(DummyWindow.open_character_selector, original_selector)
                window = DummyWindow()
                window.refresh_global_characters()

                self.assertEqual(
                    [window.character_combo.itemText(index) for index in range(window.character_combo.count())],
                    ["Alpha"],
                )
                self.assertEqual(window.current_character_key, "character:42")

                window.open_character_selector()
                self.assertEqual(window.last_page, "Personnage")
                page = window.page_widgets["Personnage"]
                window.open_character_selector()
                self.assertIs(window.page_widgets["Personnage"], page)
                self.assertEqual(TestCharacterPage.constructed, 1)
                self.assertEqual(page.character_selector.count(), 2)
                self.assertEqual(
                    [
                        page.character_selector.itemData(index)
                        for index in range(page.character_selector.count())
                    ],
                    ["character:42", "character:84"],
                )

                beta_index = next(
                    index
                    for index in range(page.character_selector.count())
                    if page.character_selector.itemData(index) == "character:84"
                )
                persist_before_selection = window.persist_count
                page.character_selector.setCurrentIndex(beta_index)
                self.app.processEvents()
                self.assertEqual(window.current_character_key, "character:84")
                self.assertEqual(window.current_character_label, "Beta")
                self.assertEqual(window.character_combo.currentIndex(), -1)
                self.assertEqual(page.active_character_key, "character:84")
                self.assertEqual(window.persist_count, persist_before_selection + 1)

                alpha_index = next(
                    index
                    for index in range(page.character_selector.count())
                    if page.character_selector.itemData(index) == "character:42"
                )
                persist_before_connected_selection = window.persist_count
                page.character_selector.setCurrentIndex(alpha_index)
                self.app.processEvents()
                self.assertEqual(window.current_character_key, "character:42")
                self.assertEqual(window.current_character_label, "Alpha")
                self.assertEqual(window.character_combo.currentIndex(), 0)
                self.assertEqual(
                    window.persist_count,
                    persist_before_connected_selection + 1,
                )

                page.character_selector.setCurrentIndex(beta_index)
                self.app.processEvents()
                self.assertEqual(window.current_character_key, "character:84")
                self.assertEqual(window.current_character_label, "Beta")
                self.assertEqual(window.character_combo.currentIndex(), -1)
                self.assertGreaterEqual(window.original_sync_count, 2)

                page.deleteLater()
                self.app.processEvents()

    def test_connection_proofs_reject_stale_pid_and_accept_runtime_or_current_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            client_index = Path(temporary) / "client_index.json"
            known = [QuestCharacter("character:42", "Élise", 1)]

            class ConnectionShell:
                _ordered_characters = staticmethod(app_main.AtlasWindow._ordered_characters)
                _connected_characters = app_main.AtlasWindow._connected_characters

            shell = ConnectionShell()
            runtime_state = CharacterRuntimeStateStore()

            with (
                patch.object(app_main, "CLIENT_INDEX_JSON", client_index),
                patch.object(
                    app_main,
                    "character_runtime_state",
                    return_value=runtime_state,
                ),
            ):
                client_index.write_text(
                    json.dumps(
                        {
                            "clients": [
                                {
                                    "name": "Dofus",
                                    "pid": 111,
                                    "character_id": 42,
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                self.assertEqual(shell._connected_characters(known), [])
                self.assertFalse(known[0].connected)

                runtime_state.identify(
                    session_id="session-verified",
                    character_key="character:42",
                    character_id=42,
                    name="Élise",
                )
                self.assertEqual(
                    [row.key for row in shell._connected_characters(known)],
                    ["character:42"],
                )

                runtime_state.reset()
                known[0].connected = False
                client_index.write_text(
                    json.dumps({"clients": [{"character_name": "elise"}]}),
                    encoding="utf-8",
                )
                self.assertEqual(
                    [row.key for row in shell._connected_characters(known)],
                    ["character:42"],
                )

    def test_connected_projection_uses_character_order_service(self):
        characters = [
            QuestCharacter("character:42", "Alpha", 1),
            QuestCharacter("character:84", "Beta", 2),
        ]

        class ReverseOrderService:
            def sort_rows(self, rows, *, label_getter):
                self.labels = [label_getter(row) for row in rows]
                return tuple(reversed(rows))

        with patch.object(
            app_main,
            "CharacterOrderService",
            return_value=ReverseOrderService(),
        ):
            ordered = app_main.AtlasWindow._ordered_characters(characters)

        self.assertEqual([row.key for row in ordered], ["character:84", "character:42"])

    def test_explicit_order_change_refreshes_organizer_and_global_selector(self):
        events: list[str] = []

        class FakeOrganizer:
            def __init__(self) -> None:
                self.sessions = [
                    {"nom": "Alpha", "hwnd": 1},
                    {"nom": "Beta", "hwnd": 2},
                ]
                self.profiles = {"old": True}
                self.export_calls = 0
                self.render_calls = 0
                self.watcher_calls = 0
                self.sessions_seen_during_apply: list[dict[str, object]] = []

            def load_profiles(self):
                return {KEY_SESSION_ORDER: ["beta", "alpha"]}

            def apply_saved_session_order(self, sessions):
                self.sessions_seen_during_apply = list(self.sessions)
                return list(reversed(sessions))

            def export_client_index(self) -> None:
                events.append("export")
                self.export_calls += 1

            def request_sessions_render(self) -> None:
                events.append("render")
                self.render_calls += 1

            def sync_event_watcher_sessions(self) -> None:
                events.append("watcher")
                self.watcher_calls += 1

        class FakeRuntime:
            def __init__(self) -> None:
                self.reload_calls: list[bool] = []

            def reload_hotkeys(self, force_restart: bool = False) -> None:
                events.append("reload_hotkeys")
                self.reload_calls.append(force_restart)

        class FakeWindow:
            def __init__(self) -> None:
                self.organizer = FakeOrganizer()
                self.runtime = FakeRuntime()
                self.page_widgets = {"Organizer": self.organizer}
                self.global_refresh_calls = 0

            def refresh_global_characters(self) -> None:
                events.append("refresh_global")
                self.global_refresh_calls += 1

        window = FakeWindow()

        window.quit_requested = False
        window._background_services_stopped = False
        window._refresh_runtime_hotkeys_for_client_mapping = (
            app_main.AtlasWindow._refresh_runtime_hotkeys_for_client_mapping.__get__(window)
        )
        window._runtime_client_mapping_signature = (
            app_main.AtlasWindow._runtime_client_mapping_signature.__get__(window)
        )
        window._loaded_runtime_client_mapping_signature = (
            app_main.AtlasWindow._loaded_runtime_client_mapping_signature.__get__(window)
        )
        window._int_value = app_main.AtlasWindow._int_value

        app_main.AtlasWindow._apply_character_order_from_page(window)

        organizer = window.organizer
        self.assertEqual(
            [row["nom"] for row in organizer.sessions_seen_during_apply],
            ["Alpha", "Beta"],
        )
        self.assertEqual([row["nom"] for row in organizer.sessions], ["Beta", "Alpha"])
        self.assertEqual(organizer.profiles, {KEY_SESSION_ORDER: ["beta", "alpha"]})
        self.assertEqual(organizer.export_calls, 1)
        self.assertEqual(organizer.render_calls, 1)
        self.assertEqual(organizer.watcher_calls, 1)
        self.assertEqual(window.global_refresh_calls, 1)
        self.assertEqual(window.runtime.reload_calls, [False])
        self.assertLess(events.index("export"), events.index("refresh_global"))
        self.assertLess(events.index("refresh_global"), events.index("reload_hotkeys"))

    def test_order_change_without_organizer_still_refreshes_global_selector(self):
        events: list[str] = []

        class FakeRuntime:
            def __init__(self) -> None:
                self.reload_calls: list[bool] = []

            def reload_hotkeys(self, force_restart: bool = False) -> None:
                events.append("reload_hotkeys")
                self.reload_calls.append(force_restart)

        class FakeWindow:
            def __init__(self) -> None:
                self.page_widgets = {}
                self.runtime = FakeRuntime()
                self.global_refresh_calls = 0

            def refresh_global_characters(self) -> None:
                events.append("refresh_global")
                self.global_refresh_calls += 1

        window = FakeWindow()

        app_main.AtlasWindow._apply_character_order_from_page(window)

        self.assertEqual(window.global_refresh_calls, 1)
        self.assertEqual(window.runtime.reload_calls, [])
        self.assertEqual(events, ["refresh_global"])

    def test_character_deletion_refreshes_and_clears_only_the_active_selection(self):
        deleted: list[str] = []

        class FakeCharacterDataService:
            def delete_character(self, character_key: str) -> None:
                deleted.append(character_key)

        class FakeWindow:
            def __init__(self, active_key: str) -> None:
                self.current_character_key = active_key
                self.current_character_label = "Alpha"
                self.refresh_states: list[tuple[str, str]] = []

            def refresh_global_characters(self) -> None:
                self.refresh_states.append(
                    (self.current_character_key, self.current_character_label)
                )

        with patch.object(app_main, "CharacterDataService", FakeCharacterDataService):
            inactive = FakeWindow("character:42")
            app_main.AtlasWindow._delete_character_from_page(inactive, "character:84")
            self.assertEqual(inactive.refresh_states, [("character:42", "Alpha")])

            active = FakeWindow("character:42")
            app_main.AtlasWindow._delete_character_from_page(active, "character:42")
            self.assertEqual(active.refresh_states, [("", "")])

        self.assertEqual(deleted, ["character:84", "character:42"])


if __name__ == "__main__":
    unittest.main()
