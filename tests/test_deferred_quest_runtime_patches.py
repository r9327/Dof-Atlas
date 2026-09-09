from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


class DeferredQuestRuntimePatchesTests(unittest.TestCase):
    def test_pages_package_import_does_not_materialize_quests_ui(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
import app.pages
print(json.dumps({
    "quests": "app.pages.quests_page" in sys.modules,
    "detail": "app.modules.encyclopedia.widgets.quest_detail_view" in sys.modules,
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
        self.assertFalse(payload["quests"])
        self.assertFalse(payload["detail"])

    def test_public_quests_page_access_returns_the_effective_class(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json
from app.pages import QuestsPage
from app.pages.quests_page import QuestsPage as RealQuestsPage
print(json.dumps({
    "same": QuestsPage is RealQuestsPage,
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
        self.assertTrue(payload["same"])


if __name__ == "__main__":
    unittest.main()
