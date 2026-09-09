from __future__ import annotations

import inspect
import os
import unittest
from contextlib import contextmanager
from queue import Queue
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import main
from app.preload import StartupPreloader
from main import AtlasWindow


class ShellReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.runtime_patch = patch.object(AtlasWindow, "start_runtime", return_value=None)
        self.tray_patch = patch.object(AtlasWindow, "setup_tray", return_value=None)
        self.runtime_patch.start()
        self.tray_patch.start()

    def tearDown(self) -> None:
        self.tray_patch.stop()
        self.runtime_patch.stop()

    def test_set_status_keeps_last_message_instead_of_discarding_it(self) -> None:
        window = AtlasWindow(initial_preload={})
        window.set_status("Runtime Python actif.")
        self.assertEqual(window.last_status_text, "Runtime Python actif.")
        window.deleteLater()

    def test_preload_worker_has_fatal_completion_path(self) -> None:
        source = inspect.getsource(AtlasWindow.start_preload)
        self.assertIn("_fatal_error", source)
        self.assertIn('"_complete": True', source)
        self.assertIn("LOGGER.exception", source)

    def test_default_preload_request_is_a_strict_no_op(self) -> None:
        class Timer:
            started = False

            def start(self) -> None:
                self.started = True

        shell = type(
            "Shell",
            (),
            {
                "preload_started": False,
                "preload_finished": False,
                "preload_queue": Queue(),
                "preload_poll_timer": Timer(),
            },
        )()
        with (
            patch.object(main, "Thread") as thread,
            patch.object(main, "build_craft_preload") as craft,
            patch.object(main, "build_quest_preload") as quests,
        ):
            AtlasWindow.start_preload(shell)

        thread.assert_not_called()
        craft.assert_not_called()
        quests.assert_not_called()
        self.assertFalse(shell.preload_started)
        self.assertFalse(shell.preload_poll_timer.started)

    def test_craft_preload_runs_once_in_background_priority_and_queues_result(self) -> None:
        events: list[str] = []

        @contextmanager
        def priority():
            events.append("priority-enter")
            try:
                yield
            finally:
                events.append("priority-exit")

        class ImmediateThread:
            created = 0

            def __init__(self, *, target, name: str, daemon: bool) -> None:
                self.target = target
                self.name = name
                self.daemon = daemon
                self.__class__.created += 1

            def start(self) -> None:
                events.append("worker-start")
                self.target()

        class Timer:
            starts = 0

            def start(self) -> None:
                self.starts += 1

        shell = type(
            "Shell",
            (),
            {
                "preload_started": False,
                "preload_finished": True,
                "preload_queue": Queue(),
                "preload_poll_timer": Timer(),
            },
        )()
        with (
            patch.object(main, "Thread", ImmediateThread),
            patch.object(main, "background_io_priority", priority),
            patch.object(
                main,
                "build_craft_preload",
                side_effect=lambda: events.append("craft") or {"items": [42]},
            ) as craft,
            patch.object(main, "build_quest_preload") as quests,
        ):
            AtlasWindow.start_preload(shell, prefer_quests=False)
            AtlasWindow.start_preload(shell, prefer_quests=False)

        self.assertEqual(ImmediateThread.created, 1)
        self.assertEqual(craft.call_count, 1)
        quests.assert_not_called()
        self.assertEqual(shell.preload_poll_timer.starts, 1)
        self.assertEqual(
            shell.preload_queue.get_nowait(),
            {"craft": {"items": [42]}, "_complete": True},
        )
        self.assertEqual(events, ["worker-start", "priority-enter", "craft", "priority-exit"])

    def test_craft_preload_error_keeps_the_existing_queue_contract(self) -> None:
        class ImmediateThread:
            def __init__(self, *, target, name: str, daemon: bool) -> None:
                self.target = target

            def start(self) -> None:
                self.target()

        class Timer:
            def start(self) -> None:
                return None

        shell = type(
            "Shell",
            (),
            {
                "preload_started": False,
                "preload_finished": True,
                "preload_queue": Queue(),
                "preload_poll_timer": Timer(),
            },
        )()
        with (
            patch.object(main, "Thread", ImmediateThread),
            patch.object(
                main,
                "build_craft_preload",
                side_effect=RuntimeError("craft indisponible"),
            ),
            patch.object(main.LOGGER, "exception") as logged,
        ):
            AtlasWindow.start_preload(shell, prefer_quests=False)

        logged.assert_called_once()
        self.assertEqual(
            shell.preload_queue.get_nowait(),
            {
                "craft": {"errors": ["craft indisponible"]},
                "_fatal_error": "craft indisponible",
                "_complete": True,
            },
        )

    def test_startup_preload_has_timeout_guard(self) -> None:
        entrypoint_source = inspect.getsource(main.run_startup_preload)
        runner_source = inspect.getsource(StartupPreloader.run)
        self.assertIn("STARTUP_PRELOAD_TIMEOUT_SECONDS", entrypoint_source)
        self.assertIn("monotonic() - started_at", runner_source)

    def test_startup_preload_keeps_heavy_modules_lazy(self) -> None:
        entrypoint_source = inspect.getsource(main.run_startup_preload)
        main_source = inspect.getsource(main.main)
        self.assertIn("Index des quêtes", entrypoint_source)
        self.assertNotIn("build_craft_preload", entrypoint_source)
        self.assertNotIn("build_quest_related_preload", entrypoint_source)
        self.assertNotIn("finish_startup_preload", main_source)

    def test_shell_source_no_longer_contains_known_mojibake_labels(self) -> None:
        source = inspect.getsource(main.AtlasWindow)
        for broken in ("Encyclop?die", "Qu?tes", "Succ?s", "Chasse au tr?sor", "int?gr?"):
            self.assertNotIn(broken, source)


if __name__ == "__main__":
    unittest.main()
