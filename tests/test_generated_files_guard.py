from __future__ import annotations

import tempfile
import subprocess
import unittest
from pathlib import Path

from tools.check_generated_files import find_forbidden, find_sensitive_content, git_paths
from tools import atlas_integrity


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

    def test_runtime_outputs_are_ignored_but_real_new_data_still_affects_risk(self) -> None:
        outputs = [
            "manifest.json",
            "quest_progress.json.lock",
            "achievement_progress.json.lock",
            "guide_progress.json.lock",
            "data/client_profiles.json.lock",
            "data/local/quest_progress.json.lock",
            "data/encyclopedia/progress/achievement_progress.json.lock",
            "data/encyclopedia/progress/guide_progress.json.lock",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for args in (
                ["init"],
                ["config", "user.email", "atlas@example.invalid"],
                ["config", "user.name", "Atlas Tests"],
                ["config", "commit.gpgsign", "false"],
            ):
                subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
            (root / ".gitignore").write_bytes(
                (Path(__file__).resolve().parents[1] / ".gitignore").read_bytes())
            subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=root, check=True, capture_output=True)
            for relative in outputs:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            self.assertEqual(atlas_integrity.changed_files(root, "HEAD"), [])
            genuine = root / "data/routes/manifest.json"
            genuine.parent.mkdir(parents=True, exist_ok=True)
            genuine.write_text("{}", encoding="utf-8")
            self.assertIn("data/routes/manifest.json", atlas_integrity.changed_files(root, "HEAD"))
            self.assertEqual(find_forbidden(["data/routes/manifest.json"]), [])
            subprocess.run(["git", "add", "--force", *outputs], cwd=root,
                           check=True, capture_output=True)
            self.assertEqual({item["path"] for item in find_forbidden(git_paths(root, True))},
                             set(outputs))
            self.assertTrue(all((root / path).exists() for path in outputs))

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
