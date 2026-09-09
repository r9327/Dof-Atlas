from __future__ import annotations

import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from app.network.bootstrap import NetworkBootstrapResult
from app.network.controller import NetworkRuntimeController
from app.quest_catalog import QuestCatalog, QuestRecord


class FakeRuntime:
    def __init__(self, *, start_result: bool = True, stop_result: bool = True) -> None:
        self.start_result = start_result
        self.stop_result = stop_result
        self.is_running = False
        self.start_calls = 0
        self.stop_calls = 0
        self.results = []

    def start(self) -> bool:
        self.start_calls += 1
        if self.start_result:
            self.is_running = True
        return self.start_result

    def stop(self) -> bool:
        self.stop_calls += 1
        if self.stop_result:
            self.is_running = False
        return self.stop_result

    def drain_results(self, limit: int = 100):
        rows = self.results[:limit]
        self.results = self.results[limit:]
        return rows


class NetworkControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = QuestCatalog(
            [
                QuestRecord(
                    id=10,
                    name="Quest A",
                    category="Test",
                    level_min=1,
                    level_max=200,
                    start_criterion="",
                )
            ]
        )
        self.logger = logging.getLogger(f"network-controller-{id(self)}")
        self.logger.addHandler(logging.NullHandler())
        self.controller = NetworkRuntimeController(
            lambda: (123,),
            logger=self.logger,
        )

    def configure(self) -> None:
        self.controller.configure_context(
            quest_catalog=self.catalog,
            achievement_provider=object(),
        )

    def test_without_context_bootstrap_is_not_called(self) -> None:
        with patch("app.network.bootstrap.build_windows_network_runtime") as build:
            status = self.controller.start_if_ready()
        self.assertFalse(status.running)
        self.assertEqual(status.reason, "waiting_context")
        build.assert_not_called()

    def test_disabled_bootstrap_remains_optional_and_stopped(self) -> None:
        self.configure()
        disabled = NetworkBootstrapResult(
            None,
            "mapping_no_exact_match",
            build_sha256="a" * 64,
        )
        with patch(
            "app.network.bootstrap.build_windows_network_runtime",
            return_value=disabled,
        ) as build:
            status = self.controller.start_if_ready()
        self.assertFalse(status.running)
        self.assertEqual(status.reason, "mapping_no_exact_match")
        self.assertEqual(status.build_sha256, "a" * 64)
        build.assert_called_once()

    def test_live_only_ready_runtime_starts_once_without_idr_catchup_and_is_reused(self) -> None:
        self.configure()
        runtime = FakeRuntime()
        ready = NetworkBootstrapResult(
            runtime,
            "ready",
            build_sha256="a" * 64,
            mapping_path=Path("mapping.json"),
            catchup_ready=False,
        )
        with patch(
            "app.network.bootstrap.build_windows_network_runtime",
            return_value=ready,
        ) as build:
            first = self.controller.start_if_ready()
            second = self.controller.start_if_ready()
        self.assertTrue(first.running)
        self.assertTrue(second.running)
        self.assertFalse(first.catchup_ready)
        self.assertEqual(runtime.start_calls, 1)
        build.assert_called_once()

    def test_stop_failure_keeps_runtime_reference_and_blocks_replacement(self) -> None:
        self.configure()
        runtime = FakeRuntime(stop_result=False)
        runtime.is_running = True
        self.controller._runtime = runtime

        self.assertFalse(self.controller.stop())
        self.assertTrue(self.controller.is_running)
        with patch("app.network.bootstrap.build_windows_network_runtime") as build:
            status = self.controller.start_if_ready()
        self.assertTrue(status.running)
        build.assert_not_called()

    def test_stale_runtime_cleanup_failure_blocks_new_bootstrap(self) -> None:
        self.configure()
        runtime = FakeRuntime(stop_result=False)
        runtime.is_running = False
        self.controller._runtime = runtime
        with patch("app.network.bootstrap.build_windows_network_runtime") as build:
            status = self.controller.start_if_ready()
        self.assertFalse(status.running)
        self.assertEqual(status.reason, "stale_runtime_stop_failed")
        build.assert_not_called()

    def test_failed_start_with_failed_cleanup_is_retained(self) -> None:
        self.configure()
        runtime = FakeRuntime(start_result=False, stop_result=False)
        ready = NetworkBootstrapResult(runtime, "ready", build_sha256="a" * 64)
        with patch(
            "app.network.bootstrap.build_windows_network_runtime",
            return_value=ready,
        ):
            status = self.controller.start_if_ready()
        self.assertFalse(status.running)
        self.assertEqual(status.reason, "runtime_start_cleanup_failed")
        self.assertIs(self.controller._runtime, runtime)

    def test_successful_stop_allows_clean_restart(self) -> None:
        self.configure()
        first_runtime = FakeRuntime()
        second_runtime = FakeRuntime()
        responses = [
            NetworkBootstrapResult(first_runtime, "ready", build_sha256="a" * 64),
            NetworkBootstrapResult(second_runtime, "ready", build_sha256="a" * 64),
        ]
        with patch(
            "app.network.bootstrap.build_windows_network_runtime",
            side_effect=responses,
        ) as build:
            self.assertTrue(self.controller.start_if_ready().running)
            self.assertTrue(self.controller.stop())
            self.assertFalse(self.controller.is_running)
            self.assertTrue(self.controller.start_if_ready().running)
        self.assertEqual(build.call_count, 2)
        self.assertEqual(first_runtime.stop_calls, 1)
        self.assertEqual(second_runtime.start_calls, 1)


if __name__ == "__main__":
    unittest.main()
