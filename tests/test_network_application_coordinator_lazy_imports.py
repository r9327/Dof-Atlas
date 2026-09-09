from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_COORDINATOR_HEAVY_MODULES = (
    "app.network.calibration_controller",
    "app.network.controller",
    "app.network.progress_bridge",
    "app.modules.encyclopedia.services.quest_progress_service",
    "app.modules.encyclopedia.services.serialized_achievement_progress_service",
)
_UI_BRIDGE_DEFERRED_MODULES = (
    "app.core.settings",
    "app.quest_catalog",
    "app.network.application_coordinator",
)


def _run_import_probe(import_statement: str, modules: tuple[str, ...]) -> dict[str, object]:
    modules_literal = repr(modules)
    code = (
        "import json, sys; "
        f"{import_statement}; "
        f"mods={modules_literal}; "
        "print(json.dumps({m: (m in sys.modules) for m in mods}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return json.loads(completed.stdout.strip())


class NetworkApplicationCoordinatorLazyImportTests(unittest.TestCase):
    def test_status_import_does_not_load_network_runtime_stacks(self) -> None:
        payload = _run_import_probe(
            "from app.network.application_coordinator import NetworkApplicationStatus; "
            "status=NetworkApplicationStatus(False, False, 'waiting_context')",
            _COORDINATOR_HEAVY_MODULES,
        )
        self.assertEqual(
            payload,
            {module_name: False for module_name in _COORDINATOR_HEAVY_MODULES},
        )

    def test_ui_bridge_module_import_does_not_hydrate_network_context(self) -> None:
        payload = _run_import_probe(
            "import app.ui.network_bridge",
            _UI_BRIDGE_DEFERRED_MODULES,
        )
        self.assertEqual(
            payload,
            {module_name: False for module_name in _UI_BRIDGE_DEFERRED_MODULES},
        )


if __name__ == "__main__":
    unittest.main()
