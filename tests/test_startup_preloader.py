from __future__ import annotations

import logging
import time
import unittest

from app.preload import PreloadTask, StartupPreloader


class _Pump:
    def __init__(self) -> None:
        self.calls = 0

    def processEvents(self) -> None:
        self.calls += 1


class StartupPreloaderTests(unittest.TestCase):
    def test_tasks_share_and_merge_one_payload_off_caller_thread(self) -> None:
        pump = _Pump()
        statuses: list[str] = []
        runner = StartupPreloader(pump, logger=logging.getLogger("preload-test"), timeout_seconds=2)

        report = runner.run(
            (
                PreloadTask("one", lambda _payload: {"quests": {"catalog": "ready"}}),
                PreloadTask(
                    "two",
                    lambda payload: {"quests": {"related": payload["quests"]["catalog"]}},
                ),
            ),
            status_callback=statuses.append,
        )

        self.assertFalse(report.timed_out)
        self.assertEqual(report.error, "")
        self.assertEqual(report.payload["quests"], {"catalog": "ready", "related": "ready"})
        self.assertEqual(report.completed_tasks, ("one", "two"))
        self.assertEqual(statuses, ["one", "two"])

    def test_timeout_returns_without_waiting_for_stuck_worker(self) -> None:
        pump = _Pump()
        runner = StartupPreloader(
            pump,
            logger=logging.getLogger("preload-timeout-test"),
            timeout_seconds=1,
            poll_seconds=0.005,
        )

        report = runner.run((PreloadTask("slow", lambda _payload: _slow_payload()),))

        self.assertTrue(report.timed_out)
        self.assertIn("slow", report.error)
        self.assertGreater(pump.calls, 0)


def _slow_payload() -> dict:
    time.sleep(1.2)
    return {"done": True}


if __name__ == "__main__":
    unittest.main()
