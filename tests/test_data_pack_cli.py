from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PackCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.root = self.path / "installed"
        self.stage = self.path / "staging"
        self.payload = b'{"records":[{"id":"q1"}]}'
        self.digest = sha256(self.payload).hexdigest()
        self.blob = self.stage / "data" / "quests" / "v1.json"
        self.blob.parent.mkdir(parents=True)
        self.blob.write_bytes(self.payload)
        self.user = self.root / "user" / "favorites.json"
        self.user.parent.mkdir(parents=True)
        self.user.write_text('{"fav":"Eca"}', encoding="utf-8")

    def cli(self, command, *extra):
        argv = [sys.executable, "-m", "app.distribution.data_pack_cli",
                command, "--root", str(self.root), "--kind", "quests", *extra]
        return subprocess.run(argv, capture_output=True, text=True, check=False)

    def install(self, **overrides):
        params = {
            "revision": 1, "schema_version": 1,
            "sha256": self.digest, "artifact_path": "data/quests/v1.json",
        }
        params.update(overrides)
        return self.cli(
            "install", "--staging-root", str(self.stage),
            "--revision", str(params["revision"]),
            "--schema-version", str(params["schema_version"]),
            "--sha256", params["sha256"],
            "--artifact-path", params["artifact_path"],
        )

    def test_full_operator_lifecycle_and_preserve_user_data(self):
        self.assertEqual(json.loads(self.cli("status").stdout)["status"], "NOT_INSTALLED")
        created = self.install()
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertEqual(json.loads(created.stdout)["status"], "INSTALLED")
        self.assertEqual(json.loads(self.cli("status").stdout)["status"], "ACTIVE_VERIFIED")
        self.assertEqual(json.loads(self.cli("acknowledge").stdout)["status"], "ACKNOWLEDGED")
        self.assertEqual(json.loads(self.install().stdout)["status"], "ALREADY_ACTIVE")
        self.assertEqual(self.user.read_text(), '{"fav":"Eca"}')

    def test_manual_rollback_clears_unhealthy_initial_pack(self):
        self.assertEqual(self.install().returncode, 0)
        rollback = self.cli("rollback")
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertEqual(json.loads(rollback.stdout)["status"], "ROLLED_BACK")
        self.assertEqual(json.loads(self.cli("status").stdout)["status"], "NOT_INSTALLED")
        self.assertEqual(self.user.read_text(), '{"fav":"Eca"}')

    def test_launcher_can_recover_interrupted_pending_pack(self):
        self.assertEqual(self.install().returncode, 0)
        recovery = subprocess.run(
            [sys.executable, "-m", "app.distribution.data_pack_cli",
             "recover", "--root", str(self.root)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(recovery.returncode, 0, recovery.stderr)
        self.assertEqual(json.loads(recovery.stdout), {
            "status": "ROLLED_BACK_PENDING", "recovered": ["quests"],
        })
        self.assertEqual(json.loads(self.cli("status").stdout)["status"], "NOT_INSTALLED")
        self.assertEqual(self.user.read_text(), '{"fav":"Eca"}')

    def test_recovery_is_idempotent(self):
        result = subprocess.run(
            [sys.executable, "-m", "app.distribution.data_pack_cli",
             "recover", "--root", str(self.root)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "NO_PENDING")

    def test_bad_stage_hash_never_installs(self):
        result = self.install(sha256="f"*64)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["status"], "BLOCKED")
        self.assertEqual(json.loads(self.cli("status").stdout)["status"], "NOT_INSTALLED")

    def test_reject_traversal_from_untrusted_manifest(self):
        result = self.install(artifact_path="../secrets.json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["status"], "BLOCKED")
        self.assertEqual(self.user.read_text(), '{"fav":"Eca"}')


if __name__ == "__main__":
    unittest.main()
