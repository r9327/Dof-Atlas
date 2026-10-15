"""Regression tests for the missing Doduda sources in frozen first installs."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.windows.quest_assets import REPO_ROOT, RELATIVE_ROOT, provision, read_lock

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
        compact = self.root / "app/modules/encyclopedia/providers/memory_bound_achievement_provider.py"
        compact.parent.mkdir(parents=True)
        compact.write_text("_ACHIEVEMENT_COMPACT_SOURCES = ('languages/fr.json',)\n", encoding="utf-8")
        detail = self.root / "app/modules/encyclopedia/providers/achievement_provider.py"
        detail.write_text("_DETAIL_SOURCE_FILES = ('quest_categories.json',)\n", encoding="utf-8")
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

    def test_lock_fails_when_catalog_adds_an_unpinned_source(self):
        module = self.root / "app/quest_catalog.py"
        module.write_text("QUEST_CATALOG_SOURCE_FILES = (('quests','quests.json'),)\n")
        with self.assertRaises(ValueError):
            read_lock(self.root)

    def test_lock_rejects_new_success_compact_source(self):
        compact = self.root / "app/modules/encyclopedia/providers/memory_bound_achievement_provider.py"
        compact.write_text(
            "_ACHIEVEMENT_COMPACT_SOURCES = ('languages/fr.json', 'dungeons.json')\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            read_lock(self.root)

    def test_lock_rejects_new_success_detail_source(self):
        detail = self.root / "app/modules/encyclopedia/providers/achievement_provider.py"
        detail.write_text(
            "_DETAIL_SOURCE_FILES = ('quest_categories.json', 'achievement_rewards.json')\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            read_lock(self.root)

    def test_real_lock_covers_success_source_requirements(self):
        assets = read_lock(REPO_ROOT)["assets"]
        self.assertTrue({
            "dungeons.json", "achievement_rewards.json", "ornaments.json", "alterations.json",
        }.issubset(assets))

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
