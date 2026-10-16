from __future__ import annotations

import os
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.check_generated_files import (
    SECRET_CANDIDATE_MARKER,
    SENSITIVE_TOKEN_PATTERNS,
    find_forbidden,
    find_sensitive_content,
    git_paths,
)
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
        git_environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_") or key == "GIT_EXEC_PATH"
        }
        with patch.dict(os.environ, git_environment, clear=True), tempfile.TemporaryDirectory() as directory:
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

    def test_fast_secret_filter_covers_every_signature_without_false_negatives(self) -> None:
        jwt = "eyJ" + "A" * 14 + "." + "B" * 14 + "." + "C" * 14
        fixtures = {
            "GitHub personal access token": "ghp_" + "A" * 36,
            "GitHub OAuth token": "gho_" + "A" * 36,
            "GitHub user token": "ghu_" + "A" * 36,
            "GitHub server token": "ghs_" + "A" * 36,
            "GitHub refresh token": "ghr_" + "A" * 36,
            "GitHub fine-grained personal access token": "github_pat_" + "A" * 42,
            "OpenAI API key": "sk-" + "A" * 25,
            "AWS access key id": "AKIA" + "A" * 16,
            "Google API key": "AIza" + "A" * 35,
            "npm access token": "npm_" + "A" * 30,
            "Slack token": "xoxb-" + "A" * 25,
            "Stripe live secret key": "sk_live_" + "A" * 25,
            "Supabase secret key": "sb_secret_" + "A" * 25,
            "Supabase service-role JWT": "SUPABASE_SERVICE_ROLE_KEY = " + jwt,
            "JWT assigned to a secret/token field": "auth_token = " + jwt,
        }
        self.assertEqual(set(fixtures), {name for name, _ in SENSITIVE_TOKEN_PATTERNS})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, (name, pattern) in enumerate(SENSITIVE_TOKEN_PATTERNS):
                content = fixtures[name]
                self.assertIsNotNone(pattern.search(content), name)
                self.assertIsNotNone(SECRET_CANDIDATE_MARKER.search(content), name)
                (root / f"secret_{index}.txt").write_text(content, encoding="utf-8")
            found = find_sensitive_content(
                root, [f"secret_{index}.txt" for index in range(len(fixtures))]
            )
        self.assertEqual(len(found), len(fixtures))
        self.assertEqual(
            {finding["path"] for finding in found},
            {f"secret_{index}.txt" for index in range(len(fixtures))},
        )

    def test_fast_secret_filter_does_not_disable_windows_path_or_private_key_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "personal.txt").write_text("C:" + "\\Users\\Developer\\Atlas", encoding="utf-8")
            (root / "private.txt").write_text("-----BEGIN " + "PRIVATE KEY-----", encoding="utf-8")
            found = find_sensitive_content(root, ["personal.txt", "private.txt"])
        self.assertEqual(len(found), 2)

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
