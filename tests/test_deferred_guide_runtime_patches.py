from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


class DeferredGuideRuntimePatchesTests(unittest.TestCase):
    def test_pages_import_does_not_materialize_manual_guide_runtime_or_caches(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
import app.pages
names = (
    "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service",
    "app.modules.encyclopedia.services.guide_ultime_manual_route",
    "app.modules.encyclopedia.services.guide_auto_validation_contract",
)
print(json.dumps({name: name in sys.modules for name in names}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(payload)
        self.assertFalse(any(payload.values()), payload)

    def test_auto_validation_cache_is_owned_by_the_canonical_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json
from app.modules.encyclopedia.services import guide_auto_validation_contract
print(json.dumps({
    "cache": isinstance(guide_auto_validation_contract._CONTRACT_CACHE, dict),
    "builder": callable(guide_auto_validation_contract.build_route_auto_validation_contract),
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
        self.assertTrue(all(payload.values()), payload)

    def test_public_encyclopedia_import_stays_guide_runtime_lazy(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
from app.modules.encyclopedia.views import EncyclopediaPage
print(json.dumps({
    "proxy": EncyclopediaPage.__name__,
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
        self.assertEqual(payload["proxy"], "EncyclopediaPage")
        self.assertFalse(payload["manual_runtime"])


if __name__ == "__main__":
    unittest.main()
