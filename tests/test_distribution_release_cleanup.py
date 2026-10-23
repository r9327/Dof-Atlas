"""Release retention is fail-closed and never deletes a working fallback early."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.windows.prune_old_app_releases import (
    PruneRefused, _verify_current, prune,
)

SOURCE = "a" * 40
TAG = f"sha-{SOURCE[:12]}"


def release(tag: str, ident: int, *, source: str = SOURCE, assets=True) -> dict:
    return {
        "id": ident, "tag_name": tag, "draft": False, "prerelease": False,
        "published_at": "2026-10-23T22:30:00Z" if ident == 30
        else "2026-10-20T17:00:00Z",
        "body": f"Certified source r9327/Dof-Atlas@{source}",
        "assets": [
            {"name": name, "size": 100, "state": "uploaded"}
            for name in (
                "atlas-channel.json", "atlas-manifest.json", "DofusAtlas.exe",
                "DofusAtlasSetup.exe", "atlas-windows.part0001",
                "atlas-windows.part0002",
            )
        ] if assets else [],
    }


class ReleaseRetentionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.current = release(TAG, 30)
        self.old = release("sha-" + "b" * 12, 29)
        self.unrelated = release("handmade-archive-v1", 28)

    def test_selects_only_obsolete_sha_releases(self):
        ids = _verify_current(
            TAG, SOURCE, self.current, self.current,
            [self.old, self.unrelated, self.current],
        )
        self.assertEqual(ids, [self.old["tag_name"]])

    def test_must_keep_previous_if_latest_not_replacement(self):
        with self.assertRaisesRegex(PruneRefused, "latest stable"):
            _verify_current(TAG, SOURCE, self.old, self.current, [self.current, self.old])

    def test_must_keep_previous_if_assets_incomplete(self):
        incomplete = release(TAG, 30, assets=False)
        with self.assertRaisesRegex(PruneRefused, "assets incomplete"):
            _verify_current(TAG, SOURCE, incomplete, incomplete, [incomplete, self.old])

    def test_must_keep_previous_without_exact_sha_evidence(self):
        wrong = release(TAG, 30, source="c" * 40)
        with self.assertRaisesRegex(PruneRefused, "provenance"):
            _verify_current(TAG, SOURCE, wrong, wrong, [wrong, self.old])

    def test_must_keep_previous_if_tag_mismatch(self):
        with self.assertRaisesRegex(PruneRefused, "certified source SHA"):
            _verify_current("sha-" + "d" * 12, SOURCE, self.current, self.current,
                            [self.current, self.old])

    def test_dry_run_cannot_delete(self):
        with patch("scripts.windows.prune_old_app_releases._release",
                   side_effect=[self.current, self.current]), \
             patch("scripts.windows.prune_old_app_releases._all_releases",
                   return_value=[self.current, self.old]), \
             patch("scripts.windows.prune_old_app_releases._gh",
                   side_effect=AssertionError("deletion not allowed")):
            self.assertEqual(prune(TAG, SOURCE, dry_run=True), [self.old["tag_name"]])

    def test_production_deletes_only_after_full_preflight(self):
        with patch("scripts.windows.prune_old_app_releases._release",
                   side_effect=[self.current, self.current]), \
             patch("scripts.windows.prune_old_app_releases._all_releases",
                   return_value=[self.current, self.old, self.unrelated]), \
             patch("scripts.windows.prune_old_app_releases._gh",
                   return_value="") as cli:
            self.assertEqual(prune(TAG, SOURCE), [self.old["tag_name"]])
            cli.assert_called_once_with(
                "release", "delete", self.old["tag_name"], "--repo",
                "r9327/Dof-Atlas-App", "--yes", "--cleanup-tag",
            )


if __name__ == "__main__":
    unittest.main()
