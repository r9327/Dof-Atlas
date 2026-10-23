from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

import app.storage as storage
from app.core.runtime_state import AtlasRuntime
from app.core.settings import AtlasClient
from app.macros.travel import TravelMacro, normalize_guide_travel_command
from app.macros.zaap import parse_zaap_command, zaap_command
from main import AtlasWindow, find_lookup_item


class RuntimeRegressionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_storage_read_json_backs_up_corrupt_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.json"
            path.write_text("{not-json", encoding="utf-8")

            payload = storage.read_json(path, {"safe": True})

            self.assertEqual(payload, {"safe": True})
            backups = list(path.parent.glob("profiles.json.corrupt.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "{not-json")

    def test_zaap_callback_typeerror_is_not_retried(self) -> None:
        calls: list[tuple[object, ...]] = []

        def callback(search, position, ratios) -> None:
            calls.append((search, position, ratios))
            raise TypeError("bug inside callback")

        widget = storage.ZaapWidget(lambda _text: None, callback)
        try:
            with self.assertRaisesRegex(TypeError, "bug inside callback"):
                widget.launch_zaap(
                    {
                        "label": "Cité d'Astrub [5,-18]",
                        "search": "Cité d'Astrub",
                        "posX": 5,
                        "posY": -18,
                    }
                )
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0], ("/zaap 5,-18", None, None))
        finally:
            # Reset only this widget. A global processEvents() here also runs
            # unrelated callbacks left by earlier Qt tests and can make the
            # Windows runner fail before unittest reports its result.
            widget.reset_launch_guard()
            widget.close()
            widget.deleteLater()
            QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)

    def test_zaap_legacy_zero_argument_callback_still_runs_once(self) -> None:
        calls: list[str] = []

        def callback() -> None:
            calls.append("called")

        widget = storage.ZaapWidget(lambda _text: None, callback)
        try:
            widget.launch_zaap(
                {"label": "Bonta [-32,-56]", "search": "Bonta", "posX": -32, "posY": -56}
            )
            self.assertEqual(calls, ["called"])
        finally:
            widget.reset_launch_guard()
            widget.deleteLater()
            QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)

    def test_zaap_widget_refuses_missing_coordinates(self) -> None:
        calls: list[tuple[object, ...]] = []
        statuses: list[str] = []
        widget = storage.ZaapWidget(statuses.append, lambda *args: calls.append(args))
        try:
            widget.launch_zaap({"label": "Zaap sans coordonnees", "search": "Zaap"})
            self.assertEqual(calls, [])
            self.assertIn("coordonnees absentes", statuses[-1])
        finally:
            widget.reset_launch_guard()
            widget.deleteLater()
            QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)

    def test_zaap_command_parser_accepts_only_one_direct_command(self) -> None:
        self.assertEqual(parse_zaap_command(" /ZAAP -32, -56 "), (-32, -56))
        self.assertEqual(zaap_command(-32, -56), "/zaap -32,-56")
        self.assertIsNone(parse_zaap_command("Bonta"))
        self.assertIsNone(parse_zaap_command("/zaap -32,-56 ; /travel 1,2"))

    def test_guide_travel_command_parser_limits_sequences(self) -> None:
        self.assertEqual(
            normalize_guide_travel_command("/zaap -32, -56; /travel 1, 2"),
            "/zaap -32,-56 ; /travel 1,2",
        )
        self.assertEqual(normalize_guide_travel_command("/travel 1,2"), "/travel 1,2")
        self.assertIsNone(normalize_guide_travel_command("/travel 1,2 ; /travel 3,4"))

    def test_missing_game_coordinates_never_reach_a_chat_command(self) -> None:
        missing = -(2**31)
        for command in (
            f"/travel {missing},0",
            f"/travel 0,{missing}",
            f"/zaap {missing},0 ; /travel 2,3",
            f"/zaap 1,2 ; /travel 3,{missing}",
        ):
            with self.subTest(command=command):
                self.assertIsNone(normalize_guide_travel_command(command))
        self.assertIsNone(parse_zaap_command(f"/zaap {missing},0"))
        self.assertIsNone(parse_zaap_command(f"/zaap 0,{missing}"))
        self.assertEqual(normalize_guide_travel_command("/travel -32,-56"), "/travel -32,-56")
        self.assertEqual(parse_zaap_command("/zaap -32,-56"), (-32, -56))

    @staticmethod
    def _travel_runtime(clients, statuses):
        timings = SimpleNamespace(
            travel_focus_settle_ms=0,
            activate_attempts=1,
            activate_retry_ms=0,
            auto_group_chat_open_ms=0,
            auto_group_key_step_ms=0,
            auto_group_paste_settle_ms=0,
        )
        runtime = SimpleNamespace(
            logger=Mock(),
            settings=SimpleNamespace(clients=tuple(clients), timings=timings),
            macro_lock=SimpleNamespace(should_stop=lambda: False),
            switch_character=SimpleNamespace(
                ordered_clients_from_source=lambda: list(clients),
                restore_preferred_client=lambda _label: None,
            ),
            _emit_status=statuses.append,
        )

        def spawn(_label, callback):
            callback()
            return True

        runtime._spawn_macro = spawn
        return runtime

    def test_guide_travel_targets_only_explicit_online_character_ids(self) -> None:
        statuses: list[str] = []
        clients = [
            AtlasClient(1, "A", "Alpha", 101, character_key="character:1"),
            AtlasClient(2, "B", "Beta", 202, character_key="character:2"),
            AtlasClient(3, "C", "Gamma", 303, character_key="character:3"),
        ]
        runtime = self._travel_runtime(clients, statuses)
        with (
            patch("app.macros.travel.is_unity_window", return_value=True),
            patch("app.macros.travel.activate_window", return_value=True),
            patch("app.macros.travel.send_chat_command", return_value=True) as send,
        ):
            self.assertTrue(
                TravelMacro(runtime).run_async(
                    "/travel 5,-18",
                    ("character:2", "character:4"),
                )
            )

        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[0], "/travel 5,-18")
        self.assertIn("1 hors ligne", statuses[-1])

    def test_guide_combo_submits_two_separate_commands_to_selected_character(self) -> None:
        statuses: list[str] = []
        clients = [
            AtlasClient(1, "A", "Alpha", 101, character_key="character:1"),
            AtlasClient(2, "B", "Beta", 202, character_key="character:2"),
        ]
        runtime = self._travel_runtime(clients, statuses)
        with (
            patch("app.macros.travel.is_unity_window", return_value=True),
            patch("app.macros.travel.activate_window", return_value=True) as activate,
            patch("app.macros.travel.send_chat_command", return_value=True) as send,
        ):
            TravelMacro(runtime).run_async(
                "/zaap -32, -56 ; /travel 5, 6", ("character:2",)
            )
        self.assertEqual(
            [call.args[0] for call in send.call_args_list],
            ["/zaap -32,-56", "/travel 5,6"],
        )
        self.assertEqual(activate.call_count, 1)
        self.assertEqual(activate.call_args.args[0], 202)
        self.assertIn("1 participant", statuses[-1])

    def test_guide_combo_stops_if_zaap_submission_fails(self) -> None:
        statuses: list[str] = []
        clients = [AtlasClient(1, "A", "Alpha", 101, character_key="character:1")]
        runtime = self._travel_runtime(clients, statuses)
        with (
            patch("app.macros.travel.is_unity_window", return_value=True),
            patch("app.macros.travel.activate_window", return_value=True),
            patch("app.macros.travel.send_chat_command", return_value=False) as send,
        ):
            TravelMacro(runtime).run_async(
                "/zaap 1,2 ; /travel 3,4", ("character:1",)
            )
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[0], "/zaap 1,2")
        self.assertIn("0 participant", statuses[-1])

    def test_guide_movement_never_broadcasts_an_empty_participant_selection(self) -> None:
        statuses: list[str] = []
        clients = [AtlasClient(1, "A", "Alpha", 101, character_key="character:1")]
        runtime = self._travel_runtime(clients, statuses)
        with (
            patch("app.macros.travel.activate_window") as activate,
            patch("app.macros.travel.send_chat_command") as send,
        ):
            TravelMacro(runtime).run_async("/travel 5,6", ())
        activate.assert_not_called()
        send.assert_not_called()
        self.assertIn("aucun participant", statuses[-1])

    def test_guide_emergency_stop_between_zaap_and_travel_skips_second_command(self) -> None:
        statuses: list[str] = []
        clients = [AtlasClient(1, "A", "Alpha", 101, character_key="character:1")]
        runtime = self._travel_runtime(clients, statuses)
        state = {"stop": False}
        runtime.macro_lock.should_stop = lambda: state["stop"]

        def send_first(_command, *_args, **_kwargs):
            state["stop"] = True
            return True

        with (
            patch("app.macros.travel.is_unity_window", return_value=True),
            patch("app.macros.travel.activate_window", return_value=True),
            patch("app.macros.travel.send_chat_command", side_effect=send_first) as send,
        ):
            TravelMacro(runtime).run_async("/zaap 1,2 ; /travel 3,4", ("character:1",))
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[0], "/zaap 1,2")

    def test_guide_travel_fails_closed_for_ambiguous_identity(self) -> None:
        statuses: list[str] = []
        clients = [
            AtlasClient(1, "A", "Alpha", 101, character_key="character:1"),
            AtlasClient(2, "A2", "Alpha", 202, character_key="character:1"),
        ]
        runtime = self._travel_runtime(clients, statuses)
        with patch("app.macros.travel.send_chat_command") as send:
            TravelMacro(runtime).run_async("/travel 5,-18", ("character:1",))

        send.assert_not_called()
        self.assertIn("ambiguë", statuses[-1])

    def test_lookup_refuses_ambiguous_partial_match(self) -> None:
        oak = {"name": "Bois de Chêne"}
        soft_oak = {"name": "Bois de Chêne Mou"}
        index = {
            "bois_de_chene": oak,
            "bois_de_chene_mou": soft_oak,
        }

        self.assertIs(find_lookup_item("Bois de Chêne", index), oak)
        self.assertIsNone(find_lookup_item("Chêne", index))

    def test_emergency_stop_does_not_fake_hook_badge_off(self) -> None:
        source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
        method = source.split("    def stop_runtime(self) -> None:", 1)[1].split("\n    def ", 1)[0]
        self.assertIn('runtime.emergency_stop("bouton stop")', method)
        self.assertNotIn("update_runtime_badge(False)", method)

    def test_runtime_joins_cooperative_macro_worker_during_shutdown(self) -> None:
        runtime = AtlasRuntime()

        def cooperative_macro() -> None:
            runtime.macro_lock.stop_event.wait(1.0)

        self.assertTrue(runtime._spawn_macro("test", cooperative_macro))
        worker = runtime._threads[0]
        runtime.macro_lock.request_stop("test shutdown")
        runtime._join_macro_threads()

        self.assertFalse(worker.is_alive())
        self.assertEqual(runtime._threads, [])

    def test_main_explicitly_enables_dpi_before_qapplication(self) -> None:
        source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
        main_body = source.split("def main() -> int:", 1)[1]
        self.assertLess(main_body.index("enable_dpi_awareness()"), main_body.index("QApplication(sys.argv)"))


if __name__ == "__main__":
    unittest.main()
