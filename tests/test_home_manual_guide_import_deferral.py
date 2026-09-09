from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


class HomeManualGuideImportDeferralTests(unittest.TestCase):
    def test_pages_import_does_not_load_manual_guide_runtime_service(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
import app.pages
print(json.dumps({
    "manual_runtime": "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service" in sys.modules,
    "home": "app.pages.home_page" in sys.modules,
    "optimized_home": "app.pages.home_optimized_page" in sys.modules,
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(payload["home"])
        self.assertFalse(payload["optimized_home"])
        self.assertFalse(payload["manual_runtime"])

    def test_base_home_module_alone_does_not_load_manual_runtime(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
import app.pages.home_page
print(json.dumps({
    "manual_runtime": "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service" in sys.modules,
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(payload["manual_runtime"])


if __name__ == "__main__":
    unittest.main()
