"""Frozen executable must dispatch every trusted encyclopedia cache worker."""
from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from launch import main

TRUSTED = (
    "app.craft_preload",
    "app.quest_catalog_details",
    "app.startup_cache_warmup",
    "app.startup_cache_domain_worker",
    "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
    "app.modules.encyclopedia.services.achievement_index_warmup",
    "app.modules.encyclopedia.providers.memory_bound_guide_provider",
    "app.modules.encyclopedia.providers.dofus_item_provider",
)


class FrozenWorkerDispatchTests(unittest.TestCase):
    def test_all_runtime_workers_dispatch_without_importing_gui(self):
        for worker in TRUSTED:
            with self.subTest(worker=worker):
                with patch.object(sys, "frozen", True, create=True), \
                     patch.object(sys, "argv", ["AtlasApp.exe", "-m", worker, "--ensure-cache"]), \
                     patch("runpy.run_module") as runner:
                    self.assertEqual(main(), 0)
                    runner.assert_called_once_with(
                        worker, run_name="__main__", alter_sys=True
                    )
                    self.assertEqual(sys.argv, [worker, "--ensure-cache"])

    def test_frozen_capture_helper_dispatches_before_gui(self):
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "argv", ["AtlasApp.exe", "--atlas-capture-helper",
                                        "--port", "4321", "--token", "proof"]), \
             patch("app.network.capture_helper.main", return_value=17) as worker:
            self.assertEqual(main(), 17)
            worker.assert_called_once_with(["--port", "4321", "--token", "proof"])

    def test_frozen_capture_smoke_imports_worker_without_running_it(self):
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "argv", ["AtlasApp.exe", "--atlas-capture-smoke"]), \
             patch("app.network.capture_helper.main") as worker:
            self.assertEqual(main(), 0)
            worker.assert_not_called()

    def test_unknown_worker_is_rejected(self):
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "argv", ["AtlasApp.exe", "-m", "os"]), \
             patch("runpy.run_module") as runner:
            self.assertEqual(main(), 2)
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
