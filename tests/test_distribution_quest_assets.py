"""Regression tests for the missing Doduda sources in frozen first installs."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.windows.quest_assets import RELATIVE_ROOT, provision, read_lock

_CATS = b'{"references":{"RefIds":[{"rid":1,"data":{"id":1}}]}}'
_LANG = b'{"entries":{"1":"Quete"}}'


class PinnedQuestSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        module = self.root / "app/quest_catalog.py"
        module.parent.mkdir(parents=True)
        module.write_text(
            "QUEST_CATALOG_SOURCE_FILES = ("
            "('language', 'languages/fr.json'), "
            "('quest_categories', 'quest_categories.json'),)\n", encoding="utf-8"
        )
        # Full frozen inventory is the union of the real provider contracts,
        # not only the Quests list verified in the previous fix.
        warmup = self.root / "app/startup_cache_warmup.py"
        warmup.write_text(
            "_QUEST_SOURCE_FILES = ('languages/fr.json', 'quest_categories.json')\\n"
            "_SUCCESS_SOURCE_FILES = ('quest_categories.json',)\\n"
            "_GUIDE_EXTRA_SOURCE_FILES = ()\\n",
            encoding="utf-8",
        )
        providers = self.root / "app/modules/encyclopedia/providers"
        providers.mkdir(parents=True)
        (providers / "memory_bound_achievement_provider.py").write_text(
            "_ACHIEVEMENT_COMPACT_SOURCES = ('quest_categories.json',)\\n", encoding="utf-8"
        )
        (providers / "achievement_provider.py").write_text(
            "_DETAIL_SOURCE_FILES = ('quest_categories.json',)\\n", encoding="utf-8"
        )
        lock_file = self.root / "scripts/windows/quest_assets_lock.json"
        lock_file.parent.mkdir(parents=True)
        lock = {
            "schema_version": 1, "source_repo": "dofusdude/dofus3-main",
            "tag": "3.7.10.10",
            "assets": {
                name: {"asset": Path(name).name, "size": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in [("languages/fr.json", _LANG), ("quest_categories.json", _CATS)]
            }
        }
        lock_file.write_text(json.dumps(lock), encoding="utf-8")

    def test_missing_sources_block_packaging(self):
        with self.assertRaises(FileNotFoundError):
            provision(self.root, download=False)

    def test_correct_offline_sources_are_certified(self):
        for name, data in [("languages/fr.json", _LANG), ("quest_categories.json", _CATS)]:
            path = self.root / RELATIVE_ROOT / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.assertEqual(provision(self.root, download=False), 2)
        (self.root / RELATIVE_ROOT / "quest_categories.json").write_bytes(_LANG)
        with self.assertRaises(FileNotFoundError):
            provision(self.root, download=False)

    def test_lock_fails_when_guide_or_success_adds_source(self):
        for filename, contents in (
            ("app/startup_cache_warmup.py",
             "_QUEST_SOURCE_FILES = ('languages/fr.json', 'quest_categories.json')\\n"
             "_SUCCESS_SOURCE_FILES = ('dungeons.json',)\\n"
             "_GUIDE_EXTRA_SOURCE_FILES = ('effects.json',)\\n"),
            ("app/modules/encyclopedia/providers/achievement_provider.py",
             "_DETAIL_SOURCE_FILES = ('achievement_rewards.json',)\\n"),
        ):
            with self.subTest(contract=filename):
                target = self.root / filename
                original = target.read_text(encoding="utf-8")
                target.write_text(contents, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_lock(self.root)
                target.write_text(original, encoding="utf-8")

    def test_lock_fails_when_catalog_adds_an_unpinned_source(self):
        module = self.root / "app/quest_catalog.py"
        module.write_text("QUEST_CATALOG_SOURCE_FILES = (('quests','quests.json'),)\n")
        with self.assertRaises(ValueError):
            read_lock(self.root)

    def test_network_download_must_match_pinned_sha(self):
        class Reply(io.BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                self.close()

        def response(request, timeout):
            self.assertIn("github.com/dofusdude/dofus3-main/releases/download/3.7.10.10/",
                          request.full_url)
            return Reply(_LANG if request.full_url.endswith("/fr.json") else _CATS)

        with patch("scripts.windows.quest_assets.urllib.request.urlopen", side_effect=response) as fetch:
            self.assertEqual(provision(self.root, download=True), 2)
            self.assertEqual(fetch.call_count, 2)
        self.assertEqual(provision(self.root, download=False), 2)

    def test_download_rejects_bad_bytes_without_activation(self):
        with patch("scripts.windows.quest_assets.urllib.request.urlopen",
                   return_value=io.BytesIO(b'{"wrong":true}')):
            with self.assertRaises(ValueError):
                provision(self.root, download=True)
        self.assertFalse((self.root / RELATIVE_ROOT / "languages/fr.json").exists())


if __name__ == "__main__":
    unittest.main()
