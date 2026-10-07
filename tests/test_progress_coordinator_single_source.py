from __future__ import annotations

from pathlib import Path
import unittest

from app.core.progress_coordinator import ProgressFileCoordinator, coordinator_for


class ProgressCoordinatorSingleSourceTests(unittest.TestCase):
    def test_encyclopedia_wrapper_stays_retired(self) -> None:
        self.assertFalse(
            Path("app/modules/encyclopedia/services/progress_coordinator.py").exists()
        )

    def test_core_module_remains_the_single_public_implementation(self) -> None:
        self.assertEqual(ProgressFileCoordinator.__module__, "app.core.progress_coordinator")
        self.assertEqual(coordinator_for.__module__, "app.core.progress_coordinator")


if __name__ == "__main__":
    unittest.main()
