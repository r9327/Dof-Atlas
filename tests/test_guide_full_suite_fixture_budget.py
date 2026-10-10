from __future__ import annotations

"""Cheap guards against reintroducing high-cost Guide FULL fixtures."""

import ast
import tempfile
import unittest
from pathlib import Path

from app.quest_catalog import (
    load_quest_progress,
    save_quest_progress,
    set_quest_done,
)


ROOT = Path(__file__).resolve().parents[1]
SLOW_TEST_FILE = ROOT / "tests" / "test_guides_catalog_fill.py"


def _slow_method(name: str) -> ast.FunctionDef:
    tree = ast.parse(SLOW_TEST_FILE.read_text(encoding="utf-8"))
    klass = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GuideCatalogFillTests"
    )
    return next(
        node for node in klass.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _method_calls(method: ast.FunctionDef, name: str) -> int:
    return sum(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == name)
            or (isinstance(node.func, ast.Name) and node.func.id == name)
        )
        for node in ast.walk(method)
    )


class GuideFullSuiteFixtureBudgetTests(unittest.TestCase):
    def test_offline_catalog_and_write_missing_share_one_real_build(self):
        method = _slow_method(
            "test_write_missing_does_not_replace_existing_guide_and_no_network"
        )
        shared = _slow_method("_shared_generated_build")
        self.assertEqual(_method_calls(shared, "build"), 1)
        self.assertEqual(_method_calls(method, "build"), 0)
        self.assertEqual(_method_calls(method, "_shared_generated_build"), 1)
        self.assertEqual(_method_calls(method, "write_missing"), 1)
        self.assertGreaterEqual(_method_calls(method, "assertEqual"), 1)
        self.assertGreaterEqual(_method_calls(method, "assertGreater"), 2)
        shared_source = ast.get_source_segment(
            SLOW_TEST_FILE.read_text(encoding="utf-8"), shared
        )
        source = ast.get_source_segment(
            SLOW_TEST_FILE.read_text(encoding="utf-8"), method
        )
        self.assertIn("socket.socket = forbidden_socket", shared_source)
        self.assertIn("socket.socket = original_socket", shared_source)
        self.assertIn("result = GuideCatalogBuilder().build()", shared_source)
        self.assertIn("_cached_build_verified_offline = True", shared_source)
        self.assertIn("socket.socket = forbidden_socket", source)
        self.assertIn("socket.socket = original_socket", source)
        self.assertIn("assertTrue(self._cached_build_verified_offline)", source)
        self.assertIn("assertNotIn(str(existing), written)", source)

    def test_guide_completion_setup_has_one_atomic_persist(self):
        method = _slow_method("test_partial_draft_hide_completed_and_tools")
        self.assertEqual(_method_calls(method, "load_quest_progress"), 1)
        self.assertEqual(_method_calls(method, "save_quest_progress"), 1)
        self.assertEqual(_method_calls(method, "set_quest_done"), 0)
        self.assertEqual(_method_calls(method, "refresh_external_progress"), 1)
        self.assertEqual(_method_calls(method, "guide_state"), 1)

    def test_batched_fixture_matches_repeated_public_setter(self):
        quest_ids = (1653, 1654, 1654, 1656, 1657)
        with tempfile.TemporaryDirectory() as tmp:
            single = Path(tmp) / "single.json"
            batch = Path(tmp) / "batch.json"
            progress = load_quest_progress(single)
            for quest_id in quest_ids:
                set_quest_done(progress, "character:1", quest_id, True, single)
                progress = load_quest_progress(single)
            batched = load_quest_progress(batch)
            done = batched.setdefault("characters", {}).setdefault(
                "character:1", {"done": {}}
            ).setdefault("done", {})
            for quest_id in quest_ids:
                done[str(quest_id)] = True
            save_quest_progress(batched, batch)
            self.assertEqual(
                load_quest_progress(single), load_quest_progress(batch)
            )


if __name__ == "__main__":
    unittest.main()
