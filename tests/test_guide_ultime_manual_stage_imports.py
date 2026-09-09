from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


class GuideUltimeManualStageImportTests(unittest.TestCase):
    @staticmethod
    def _write(root: Path, name: str, payload: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_import_moves_authored_stage_with_patch_and_new_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {"stages": [{"id": "A"}, {"id": "B"}]})
            self._write(root, "source.json", {
                "stages": [
                    {"id": "S", "quests": ["Quête source"], "route": [{"do": "source"}]},
                ]
            })
            path = self._write(root, "v2.json", {
                "base_file": "base.json",
                "stage_imports": [
                    {
                        "file": "source.json",
                        "stage_id": "S",
                        "new_id": "S-MOVED",
                        "after": "A",
                        "replace": {"title": "Déplacé"},
                        "append": {"route": [{"do": "patch"}]},
                    }
                ],
            })
            resolved = load_manual_chapter(path)
            self.assertEqual([row["id"] for row in resolved["stages"]], ["A", "S-MOVED", "B"])
            moved = resolved["stages"][1]
            self.assertEqual(moved["quests"], ["Quête source"])
            self.assertEqual(moved["title"], "Déplacé")
            self.assertEqual([row["do"] for row in moved["route"]], ["source", "patch"])
            self.assertEqual(resolved["_stage_imports_resolved"], ["source.json#S"])

    def test_removal_then_reimport_relocates_same_id_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {"stages": [{"id": "A"}, {"id": "MOVE"}, {"id": "B"}]})
            path = self._write(root, "v2.json", {
                "base_file": "base.json",
                "stage_removals": ["MOVE"],
                "stage_imports": [
                    {"file": "base.json", "stage_id": "MOVE", "after": "B"}
                ],
            })
            resolved = load_manual_chapter(path)
            ids = [row["id"] for row in resolved["stages"]]
            self.assertEqual(ids, ["A", "B", "MOVE"])
            self.assertEqual(ids.count("MOVE"), 1)

    def test_import_can_anchor_to_local_insertion_resolved_later(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {"stages": [{"id": "A"}, {"id": "B"}]})
            self._write(root, "source.json", {"stages": [{"id": "S"}]})
            path = self._write(root, "v2.json", {
                "base_file": "base.json",
                "stage_imports": [
                    {"file": "source.json", "stage_id": "S", "after": "MID"}
                ],
                "insertions": [
                    {"after": "A", "stage": {"id": "MID"}}
                ],
            })
            resolved = load_manual_chapter(path)
            self.assertEqual([row["id"] for row in resolved["stages"]], ["A", "MID", "S", "B"])

    def test_import_rejects_unknown_source_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {"stages": [{"id": "A"}]})
            self._write(root, "source.json", {"stages": [{"id": "S"}]})
            path = self._write(root, "v2.json", {
                "base_file": "base.json",
                "stage_imports": [
                    {"file": "source.json", "stage_id": "MISSING", "after": "A"}
                ],
            })
            with self.assertRaises(KeyError):
                load_manual_chapter(path)


if __name__ == "__main__":
    unittest.main()
