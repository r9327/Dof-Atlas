import ast
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from app.distribution.data_pack_plan import DataPack, InvalidDataPack
from app.distribution.data_pack_store import (
    acknowledge_pack, active_pack, install_pack,
)
from app.distribution.launch_pack_recovery import recover_data_packs_on_launch


class LauncherPackRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "installed-atlas"
        self.staging = self.base / "staged"
        self.user = self.root / "user" / "characters.json"
        self.user.parent.mkdir(parents=True)
        self.user.write_text('{"favorite":"Panda"}', encoding="utf-8")
        self.messages = []

    def pack(self, revision, data):
        digest = sha256(data).hexdigest()
        artifact = f"data/quests/v{revision}.json"
        path = self.staging / artifact
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return DataPack("quests", revision, 1, digest, artifact)

    def test_normal_start_has_zero_pack_index_reads_or_directory_creation(self):
        found = recover_data_packs_on_launch(self.root, self.messages.append)
        self.assertEqual(found, ())
        self.assertFalse((self.root / "data-pack-store").exists())
        self.assertEqual(self.messages, [])

    def test_cold_start_restores_previous_verified_pack(self):
        old = self.pack(1, b"old")
        install_pack(self.root, self.staging, old)
        acknowledge_pack(self.root, "quests")
        new = self.pack(2, b"new")
        install_pack(self.root, self.staging, new)
        found = recover_data_packs_on_launch(
            self.root, lambda label, pct: self.messages.append((label, pct)))
        self.assertEqual(found, ("quests",))
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"old")
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(self.messages[0][1], 2)
        self.assertEqual(self.user.read_text(encoding="utf-8"), '{"favorite":"Panda"}')

    def test_healthy_acknowledged_pack_is_not_rolled_back(self):
        current = self.pack(1, b"healthy")
        install_pack(self.root, self.staging, current)
        acknowledge_pack(self.root, "quests")
        found = recover_data_packs_on_launch(
            self.root, lambda label, pct: self.messages.append((label, pct)))
        self.assertEqual(found, ())
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"healthy")
        self.assertEqual(self.messages, [])

    def test_corrupt_existing_pack_index_must_not_be_ignored(self):
        index = self.root / "data-pack-store" / "state.json"
        index.parent.mkdir()
        index.write_text("{corrupted", encoding="utf-8")
        with self.assertRaises(InvalidDataPack):
            recover_data_packs_on_launch(self.root, lambda *_: None)
        self.assertEqual(index.read_text(encoding="utf-8"), "{corrupted")

    def test_real_launcher_invokes_recovery_before_remote_check(self):
        launcher = Path(__file__).resolve().parents[1] / "app" / "distribution" / "launcher.py"
        tree = ast.parse(launcher.read_text(encoding="utf-8"))
        run_update = next(node for node in tree.body
                          if isinstance(node, ast.FunctionDef) and node.name == "run_update")
        calls = [
            (node.lineno, node.func.id)
            for node in ast.walk(run_update)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"recover_data_packs_on_launch", "latest_release"}
        ]
        recovered = [line for line, name in calls if name == "recover_data_packs_on_launch"]
        fetched = [line for line, name in calls if name == "latest_release"]
        self.assertEqual(len(recovered), 1)
        self.assertEqual(len(fetched), 1)
        self.assertLess(recovered[0], fetched[0])


if __name__ == "__main__":
    unittest.main()
