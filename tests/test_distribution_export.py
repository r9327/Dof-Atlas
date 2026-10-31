"""App-only export must exclude development and private data."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.windows.export_app_repository import export, selected_runtime_path


class ExportTests(unittest.TestCase):
    def test_unlicensed_unity_references_never_enter_app_mirror(self):
        for path in (
            "app/assets/themes/dofus_unity/background_selection_original.png",
            "app/assets/themes/dofus_unity/fonts/Lexend-Regular.ttf",
            "app/assets/themes/dofus_unity/sprites/btn_green_normal.png",
            "app/assets/themes/dofus_unity/references/logoDofus.png",
            "docs/design/dofus-unity/sources/atlas_unity_background_original.zip",
        ):
            self.assertFalse(selected_runtime_path(path), path)
        self.assertTrue(selected_runtime_path("app/ui/unity_skin.py"))

    def test_export_runtime_and_keep_essential_icons(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            examples = {
                "main.py": "def main(): pass\n",
                "launch.py": "import main\n",
                "app/runtime.py": "VALUE=1\n",
                "app/modules/encyclopedia/tools/dev.py": "# dev only\n",
                "local_dofus_data/store.py": "VALUE=1\n",
                "data/encyclopedia/quests/quests_enriched.json": "{}\n",
                "data/images/misc/dofus_atlas_logo.png": "PNG\n",
                "data/images/classes/feca.png": "PNG-class-icon\n",
                "data/images/breeds/pandawa.webp": "WEBP-class-icon\n",
                "data/images/misc/classes/zobal.ico": "ICO-class-icon\n",
                "data/images/classes/README.txt": "not an icon\n",
                "data/images/items/unrelated.png": "not part of class portrait bundle\n",
                "data/local/zaaps.json": '{"zaaps":[]}',
                "data/local/quest_progress.json": '{"progress":8}\n',
                "tests/test_private.py": "secret\n",
                "tools/doctor.py": "dev\n",
            }
            for filename, content in examples.items():
                file = source / filename
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            subprocess.run(["git", "add", "-A"], cwd=source, check=True)
            destination = base / "app-only"
            copied = export(source, destination, "a" * 40)
            self.assertGreaterEqual(copied, 5)
            for rel in ("main.py", "launch.py", "app/runtime.py",
                        "local_dofus_data/store.py",
                        "data/encyclopedia/quests/quests_enriched.json",
                        "data/images/misc/dofus_atlas_logo.png",
                        "data/images/classes/feca.png",
                        "data/images/breeds/pandawa.webp",
                        "data/images/misc/classes/zobal.ico",
                        "data/local/zaaps.json"):
                self.assertTrue((destination / rel).is_file(), rel)
            for rel in ("tools/doctor.py", "tests/test_private.py",
                        "app/modules/encyclopedia/tools/dev.py",
                        "data/local/quest_progress.json",
                        "data/images/classes/README.txt",
                        "data/images/items/unrelated.png"):
                self.assertFalse((destination / rel).exists(), rel)
            metadata = json.loads((destination / "SOURCE_PROVENANCE.json").read_text())
            self.assertEqual(metadata["source_sha"], "a" * 40)

    def test_do_not_remove_runtime_ganymede_cutovers_while_triaging_assets(self):
        # The runtime selector resolves replacement_drafts/cutovers/<guide_id>.json
        # using a dynamic guide_id, so AST literal-path scans cannot prove unused.
        for name in (
            "data/encyclopedia/guides/replacement_drafts/cutovers/dofus_cawotte.json",
            "data/encyclopedia/guides/replacement_drafts/dofus_cawotte.json",
            "data/images/classes/pandawa.png",
        ):
            self.assertTrue(selected_runtime_path(name), name)
        # Intermediate evidence is currently allowed too. Its removal requires
        # separate source/bundle tests, not an automatic Doctor orphan decision.
        self.assertTrue(selected_runtime_path(
            "data/encyclopedia/guides/ganymede_2203_action_candidates.json"))

    def test_reject_unmaterialized_lfs_icon(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            icon = source / "data/images/misc/dofus_atlas_logo.png"
            icon.parent.mkdir(parents=True)
            icon.write_text("version https://git-lfs.github.com/spec/v1\n")
            (source / "main.py").write_text("pass\n")
            subprocess.run(["git", "add", "-A"], cwd=source, check=True)
            with self.assertRaises(RuntimeError):
                export(source, base / "out", "b" * 40)


if __name__ == "__main__":
    unittest.main()
