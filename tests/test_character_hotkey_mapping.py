from __future__ import annotations

import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.constants import KEY_SESSION_ORDER
import app.core.settings as settings_module
from app.input.hotkeys import build_hotkey_actions
import app.macros.switch_character as switch_character_module
from app.macros.switch_character import SwitchCharacterMacro
import app.pages.organizer_page as organizer
import main as app_main


class _HotkeyWindowMixin:
    _int_value = staticmethod(app_main.AtlasWindow._int_value)
    _runtime_client_mapping_signature = app_main.AtlasWindow._runtime_client_mapping_signature
    _loaded_runtime_client_mapping_signature = (
        app_main.AtlasWindow._loaded_runtime_client_mapping_signature
    )
    _refresh_runtime_hotkeys_for_client_mapping = (
        app_main.AtlasWindow._refresh_runtime_hotkeys_for_client_mapping
    )


class CharacterHotkeyMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_mapping_change_reloads_running_runtime_once_without_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            client_index = Path(temporary) / "client_index.json"
            client_index.write_text(
                json.dumps(
                    {
                        "clients": [
                            {
                                "index": 1,
                                "slot": 1,
                                "handle": 101,
                                "binding": "F5",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            class FakeRuntime:
                def __init__(self) -> None:
                    self._running = True
                    self.is_starting = False
                    self.reload_calls: list[bool] = []
                    self.start_calls = 0
                    self.settings = SimpleNamespace(
                        clients=(
                            SimpleNamespace(index=1, handle=101, binding="F5"),
                        )
                    )

                def reload_hotkeys(self, force_restart: bool = False) -> None:
                    self.reload_calls.append(force_restart)
                    payload = json.loads(client_index.read_text(encoding="utf-8"))
                    self.settings = SimpleNamespace(
                        clients=tuple(
                            SimpleNamespace(
                                index=int(row.get("index") or 0),
                                handle=int(row.get("handle") or 0),
                                binding=str(row.get("binding") or ""),
                            )
                            for row in payload.get("clients", [])
                        )
                    )

                def start(self) -> None:
                    self.start_calls += 1

            class FakeWindow(_HotkeyWindowMixin):
                def __init__(self) -> None:
                    self.runtime = FakeRuntime()
                    self.quit_requested = False
                    self._background_services_stopped = False

            window = FakeWindow()
            with patch.object(app_main, "CLIENT_INDEX_JSON", client_index):
                self.assertFalse(
                    window._refresh_runtime_hotkeys_for_client_mapping()
                )
                self.assertEqual(window.runtime.reload_calls, [])
                self.assertEqual(window.runtime.start_calls, 0)

                client_index.write_text(
                    json.dumps(
                        {
                            "clients": [
                                {
                                    "index": 1,
                                    "slot": 1,
                                    "handle": 202,
                                    "binding": "F5",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )

                self.assertTrue(
                    window._refresh_runtime_hotkeys_for_client_mapping()
                )
                self.assertEqual(window.runtime.reload_calls, [False])
                self.assertEqual(window.runtime.start_calls, 0)

                self.assertFalse(
                    window._refresh_runtime_hotkeys_for_client_mapping()
                )
                self.assertEqual(window.runtime.reload_calls, [False])
                self.assertEqual(window.runtime.start_calls, 0)

    def test_mapping_change_during_startup_queues_existing_startup_reload(self):
        with tempfile.TemporaryDirectory() as temporary:
            client_index = Path(temporary) / "client_index.json"
            client_index.write_text(
                json.dumps(
                    {
                        "clients": [
                            {
                                "index": 1,
                                "slot": 1,
                                "handle": 101,
                                "binding": "F5",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            class FakeRuntime:
                def __init__(self) -> None:
                    self._running = False
                    self.is_starting = False
                    self.reload_calls: list[bool] = []
                    self.start_calls = 0

                def reload_hotkeys(self, force_restart: bool = False) -> None:
                    self.reload_calls.append(force_restart)

                def start(self) -> None:
                    self.start_calls += 1

            class FakeWindow(_HotkeyWindowMixin):
                def __init__(self) -> None:
                    self.runtime = FakeRuntime()
                    self.quit_requested = False
                    self._background_services_stopped = False

            window = FakeWindow()
            with patch.object(app_main, "CLIENT_INDEX_JSON", client_index):
                self.assertFalse(
                    window._refresh_runtime_hotkeys_for_client_mapping()
                )
                window.runtime.is_starting = True
                client_index.write_text(
                    json.dumps(
                        {
                            "clients": [
                                {
                                    "index": 1,
                                    "slot": 1,
                                    "handle": 202,
                                    "binding": "F5",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )

                self.assertTrue(
                    window._refresh_runtime_hotkeys_for_client_mapping()
                )
                self.assertFalse(
                    window._refresh_runtime_hotkeys_for_client_mapping()
                )

            self.assertEqual(window.runtime.start_calls, 1)
            self.assertEqual(window.runtime.reload_calls, [])

    def test_reordered_slot_hotkey_targets_new_handle_end_to_end(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "client_profiles.json"
            client_index = root / "client_index.json"
            client_ini = root / "client_index.ini"
            profile.write_text(
                json.dumps(
                    {
                        KEY_SESSION_ORDER: ["alpha", "beta"],
                        organizer.client_slot_hotkey_key(0): "F5",
                        organizer.client_slot_hotkey_key(1): "F6",
                    }
                ),
                encoding="utf-8",
            )
            client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")

            with (
                patch.object(organizer, "PROFILE_FILE", profile),
                patch.object(organizer, "CLIENT_INDEX_JSON", client_index),
                patch.object(organizer, "CLIENT_INDEX_INI", client_ini),
                patch.object(organizer, "scan_unity_sessions", return_value=[]),
                patch.object(organizer.UnityWindowEventWatcher, "start", return_value=None),
                patch.object(organizer.UnityWindowEventWatcher, "stop", return_value=None),
            ):
                page = organizer.OrganizerPage(
                    lambda _text: None,
                    lambda *_args: None,
                )
                try:
                    page.sessions = page.build_session_slots(
                        [
                            {"nom": "Alpha - Iop", "hwnd": 101, "pid": 11},
                            {"nom": "Beta - Cra", "hwnd": 202, "pid": 22},
                        ]
                    )
                    page.reorder_session(0, 1)

                    exported = json.loads(client_index.read_text(encoding="utf-8"))
                    self.assertEqual(
                        [
                            (
                                row["character_name"],
                                row["slot"],
                                row["handle"],
                                row["binding"],
                            )
                            for row in exported["clients"]
                        ],
                        [
                            ("Beta", 1, 202, "F5"),
                            ("Alpha", 2, 101, "F6"),
                        ],
                    )

                    with (
                        patch.object(settings_module, "PROFILE_FILE", profile),
                        patch.object(settings_module, "CLIENT_INDEX_JSON", client_index),
                    ):
                        settings = settings_module.load_settings()

                    client_actions = [
                        action
                        for action in build_hotkey_actions(settings)
                        if action.action_id.startswith("client:")
                    ]
                    f5_action = next(
                        action for action in client_actions if action.hotkey_text == "F5"
                    )
                    self.assertEqual(f5_action.payload["client_index"], 1)
                    self.assertEqual(f5_action.payload["handle"], 202)

                    class MacroLock:
                        @staticmethod
                        def should_stop() -> bool:
                            return False

                    class FakeRuntime:
                        def __init__(self) -> None:
                            self.settings = settings
                            self.logger = logging.getLogger("character-hotkey-mapping-test")
                            self.macro_lock = MacroLock()
                            self.active_client_handle = 0

                        def _spawn_macro(self, _label: str, target) -> bool:
                            target()
                            return True

                    fake_runtime = FakeRuntime()
                    macro = SwitchCharacterMacro(fake_runtime)
                    with (
                        patch.object(
                            switch_character_module,
                            "is_unity_window",
                            return_value=True,
                        ),
                        patch.object(
                            switch_character_module,
                            "activate_window",
                            return_value=True,
                        ) as activate_window,
                    ):
                        self.assertTrue(
                            macro.activate_by_index(
                                int(f5_action.payload["client_index"])
                            )
                        )

                    self.assertEqual(activate_window.call_args.args[0], 202)
                    self.assertEqual(fake_runtime.active_client_handle, 202)
                finally:
                    page.deleteLater()
                    self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
