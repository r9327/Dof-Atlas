from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.check_generated_files import find_forbidden, find_sensitive_content


class GeneratedFilesGuardTests(unittest.TestCase):
    def test_runtime_and_generated_groups_are_rejected(self) -> None:
        findings = find_forbidden(
            [
                "logs/start_log.txt",
                "logs/ui_capture.png",
                "data/local/progress.sqlite-wal",
                "data/local/progress.sqlite-shm",
                "crash.dmp",
                "profile.pstats",
                "artifacts/report.json",
                ".env",
                "config/zaap_shortcuts.json",
                "data/encyclopedia/progress/achievement_progress.json",
            ]
        )
        self.assertEqual(len(findings), 10)

    def test_canonical_data_and_fixtures_are_not_classified_generated(self) -> None:
        self.assertEqual(
            find_forbidden(
                [
                    "data/routes/guide_ultime_manual/manifest_v1.json",
                    "tests/fixtures/sample.json",
                    "data/dofus_atlas_world.db",
                    ".env.example",
                ]
            ),
            [],
        )

    def test_sensitive_content_rejects_real_user_paths_and_private_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe.py").write_text(r'C:\Users\TestUser\Atlas', encoding="utf-8")
            (root / "unsafe.json").write_text("C:" + r'\Users\Developer\Atlas', encoding="utf-8")
            (root / "key.txt").write_text("-----BEGIN " + "PRIVATE KEY-----", encoding="utf-8")

            findings = find_sensitive_content(root, ["safe.py", "unsafe.json", "key.txt"])

        self.assertEqual({finding["path"] for finding in findings}, {"unsafe.json", "key.txt"})


if __name__ == "__main__":
    unittest.main()
