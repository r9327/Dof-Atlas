"""Guard that importing the Encyclopedia provider package stays lightweight.

This probes the actual Python import system in new processes, and confirms that
requesting QuestProvider still returns the original class (never a proxy).
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EncyclopediaProviderLazyBoundaryTests(unittest.TestCase):
    def _in_clean_process(self, source: str) -> None:
        p = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", source],
            cwd=ROOT, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(p.returncode, 0, p.stdout + "\n" + p.stderr)

    def test_importing_package_and_guide_facade_does_not_load_quest_catalog(self):
        self._in_clean_process("""
import sys
import app.modules.encyclopedia.providers as p
assert 'app.modules.encyclopedia.providers.quest_provider' not in sys.modules
assert 'app.quest_catalog' not in sys.modules
assert 'QuestProvider' in p.__all__
from app.modules.encyclopedia.providers import GuideProvider, AchievementProvider
assert GuideProvider is p.GuideProvider
assert AchievementProvider is p.AchievementProvider
assert 'app.modules.encyclopedia.providers.quest_provider' not in sys.modules
assert 'app.quest_catalog' not in sys.modules
""")

    def test_explicit_quest_provider_load_retains_exact_class_identity(self):
        self._in_clean_process("""
import sys
from app.modules.encyclopedia import providers as p
assert 'QuestProvider' not in vars(p)
from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.providers.quest_provider import QuestProvider as Original
assert QuestProvider is Original
assert p.QuestProvider is Original
assert p.QuestProvider.__module__ == 'app.modules.encyclopedia.providers.quest_provider'
assert 'app.quest_catalog' in sys.modules
assert isinstance(Original, type)
""")

    def test_unknown_provider_name_fails_without_dynamic_import(self):
        self._in_clean_process("""
import sys
import app.modules.encyclopedia.providers as p
try:
    getattr(p, 'NonexistentProvider')
except AttributeError:
    pass
else:
    raise AssertionError('unknown provider unexpectedly resolved')
assert 'app.modules.encyclopedia.providers.quest_provider' not in sys.modules
""")

if __name__ == "__main__":
    unittest.main()
