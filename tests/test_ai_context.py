from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import ai_context


ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _git_path_exists(root: Path, path: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{path.rstrip('/')}"],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _commit_all(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-m", message)


def _context_map_lists(path: Path) -> tuple[list[str], dict[str, dict[str, list[str]]]]:
    defaults: list[str] = []
    scopes: dict[str, dict[str, list[str]]] = {}
    section = ""
    current_scope = ""
    current_list = ""

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line == "rule_defaults:":
            section = "rule_defaults"
            current_scope = ""
            current_list = ""
            continue
        if raw_line == "scopes:":
            section = "scopes"
            current_scope = ""
            current_list = ""
            continue

        if section == "rule_defaults" and raw_line.startswith("  - "):
            defaults.append(raw_line[4:])
            continue

        if section != "scopes":
            continue

        if raw_line.startswith("  ") and not raw_line.startswith("    ") and raw_line.endswith(":"):
            current_scope = raw_line.strip()[:-1]
            scopes[current_scope] = {}
            current_list = ""
            continue

        if not current_scope or not raw_line.startswith("    ") or raw_line.startswith("      "):
            if current_scope and current_list and raw_line.startswith("      - "):
                scopes[current_scope][current_list].append(raw_line[8:])
            continue

        field = raw_line.strip()
        if field.endswith(": []"):
            key = field.removesuffix(": []")
            scopes[current_scope][key] = []
            current_list = ""
        elif field.endswith(":"):
            current_list = field[:-1]
            scopes[current_scope][current_list] = []
        else:
            current_list = ""

    return defaults, scopes


class AiContextTests(unittest.TestCase):
    def test_route_classifies_major_project_areas(self) -> None:
        cases = {
            "app/core/character_identity.py": "core",
            "app/modules/encyclopedia/views/guides_view.py": "guide",
            "app/modules/encyclopedia/providers/achievement_provider.py": "encyclopedia",
            "app/ui/theme.py": "ui",
            "app/preload.py": "runtime",
            "local_dofus_data/catalog.py": "runtime",
            "data/local/example.json": "data",
            "config/example.json": "data",
            "tests/test_repository_git_hooks.py": "tests",
            "tools/atlas_integrity.py": "quality",
            ".github/workflows/app-ci.yml": "quality",
            ".githooks/pre-commit": "quality",
            "ROAD_IA.md": "quality",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(ai_context.classify_path(path), expected)

    def test_context_recommendations_are_scoped(self) -> None:
        guide_docs = ai_context.recommended_context(
            ["app/modules/encyclopedia/views/guides_view.py"]
        )
        self.assertIn("GUIDE_ULTIME_STATUS.md", guide_docs)
        self.assertIn("PERFORMANCE_GUARDRAILS.md", guide_docs)
        self.assertNotIn("ZERO_TRUST_RULES.md", guide_docs)

        quality_docs = ai_context.recommended_context(["tools/atlas_integrity.py"])
        self.assertIn("ZERO_TRUST_RULES.md", quality_docs)
        self.assertIn("PHASE_CERTIFICATION.md", quality_docs)

    def test_v2_scope_rule_routes_reference_existing_contracts(self) -> None:
        defaults, scopes = _context_map_lists(ROOT / ".ai/context-map.yaml")
        self.assertEqual(
            defaults,
            ["AGENTS.md", "DEVELOPMENT_GUARDRAILS.md", "ZERO_TRUST_RULES.md"],
        )

        expected_scopes = {
            "home",
            "character",
            "organizer",
            "equipment",
            "craft",
            "zaap",
            "travel",
            "world_scan",
            "encyclopedia_shell",
            "encyclopedia_quests",
            "encyclopedia_achievements",
            "encyclopedia_guide",
            "encyclopedia_bestiary",
            "cartography",
            "persistence_identity",
            "startup_lifecycle",
            "network_capture",
            "dofus_data",
            "shared_ui",
            "windows_qt_runtime",
            "input_hotkeys",
            "macro_runtime",
            "quality_ci",
        }
        self.assertEqual(set(scopes), expected_scopes)

        for entry in defaults:
            self.assertTrue(_git_path_exists(ROOT, entry), entry)

        for scope, payload in scopes.items():
            self.assertIn("rule_entries", payload, scope)
            self.assertIn("canonical_entries", payload, scope)
            for key in ("rule_entries", "canonical_entries"):
                for entry in payload[key]:
                    self.assertTrue(
                        _git_path_exists(ROOT, entry),
                        f"{scope}: missing {entry}",
                    )

        self.assertIn("data/AGENTS.md", scopes["encyclopedia_guide"]["rule_entries"])
        self.assertIn("PHASE_CERTIFICATION.md", scopes["encyclopedia_guide"]["rule_entries"])
        self.assertIn("PERFORMANCE_GUARDRAILS.md", scopes["shared_ui"]["rule_entries"])
        self.assertIn("tools/AGENTS.md", scopes["quality_ci"]["rule_entries"])
        self.assertIn("tests/AGENTS.md", scopes["quality_ci"]["rule_entries"])
        self.assertEqual(scopes["encyclopedia_bestiary"]["canonical_entries"], [])

    def test_impact_recommendations_use_existing_tests_and_canonical_anchors(self) -> None:
        guide_path = "app/modules/encyclopedia/views/guides_view.py"
        guide_tests = ai_context.recommended_tests(ROOT, [guide_path])
        guide_anchors = ai_context.recommended_canonical_paths(ROOT, [guide_path])
        self.assertIn("tests.test_guide_ultime_manual_prerequisites", guide_tests)
        self.assertIn("data/routes/guide_ultime_manual/manifest_v1.json", guide_anchors)

        quality_tests = ai_context.recommended_tests(ROOT, ["tools/ai_context.py"])
        self.assertIn("tests.test_ai_context", quality_tests)
        self.assertIn("tests.test_repository_git_hooks", quality_tests)

    def test_committed_context_index_matches_head(self) -> None:
        index_path = ROOT / ai_context.INDEX_PATH
        self.assertTrue(index_path.is_file(), index_path)
        actual = json.loads(index_path.read_text(encoding="utf-8"))
        expected = ai_context.build_index(ROOT, ai_context.committed_tree_sha(ROOT))
        self.assertEqual(actual, expected)
        self.assertEqual(actual["schema_version"], 2)
        self.assertNotIn(".ai", actual["entries"])
        self.assertIn("app", actual["entries"])
        self.assertIn("local_dofus_data", actual["entries"])

    def test_git_fingerprint_tracks_create_modify_rename_and_delete(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-ai-context-") as directory:
            root = Path(directory)
            _git(root, "init")
            _git(root, "config", "user.email", "atlas-tests@example.invalid")
            _git(root, "config", "user.name", "Dofus Atlas Tests")

            app = root / "app"
            app.mkdir()
            tracked = app / "example.txt"
            tracked.write_text("v1\n", encoding="utf-8")
            _commit_all(root, "baseline")
            baseline = ai_context.build_index(root, ai_context.committed_tree_sha(root))
            baseline_sha = baseline["entries"]["app"]["sha"]

            tracked.write_text("v2\n", encoding="utf-8")
            _commit_all(root, "modify")
            modified = ai_context.build_index(root, ai_context.committed_tree_sha(root))
            modified_sha = modified["entries"]["app"]["sha"]
            self.assertNotEqual(baseline_sha, modified_sha)

            created = app / "created.txt"
            created.write_text("new\n", encoding="utf-8")
            _commit_all(root, "create")
            created_index = ai_context.build_index(root, ai_context.committed_tree_sha(root))
            created_sha = created_index["entries"]["app"]["sha"]
            self.assertNotEqual(modified_sha, created_sha)

            renamed = app / "renamed.txt"
            created.rename(renamed)
            _commit_all(root, "rename")
            renamed_index = ai_context.build_index(root, ai_context.committed_tree_sha(root))
            renamed_sha = renamed_index["entries"]["app"]["sha"]
            self.assertNotEqual(created_sha, renamed_sha)

            renamed.unlink()
            _commit_all(root, "delete")
            deleted_index = ai_context.build_index(root, ai_context.committed_tree_sha(root))
            deleted_sha = deleted_index["entries"]["app"]["sha"]
            self.assertNotEqual(renamed_sha, deleted_sha)

    def test_ai_directory_is_excluded_from_fingerprint_and_sync_stages_index(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-ai-context-") as directory:
            root = Path(directory)
            _git(root, "init")
            _git(root, "config", "user.email", "atlas-tests@example.invalid")
            _git(root, "config", "user.name", "Dofus Atlas Tests")

            app = root / "app"
            app.mkdir()
            tracked = app / "example.txt"
            tracked.write_text("v1\n", encoding="utf-8")
            _commit_all(root, "baseline")

            baseline = ai_context.build_index(root, ai_context.committed_tree_sha(root))
            self.assertNotIn(".ai", baseline["entries"])

            ai_dir = root / ".ai"
            ai_dir.mkdir()
            (ai_dir / "note.txt").write_text("ignored fingerprint source\n", encoding="utf-8")
            _commit_all(root, "ai-only")
            after_ai_only = ai_context.build_index(root, ai_context.committed_tree_sha(root))
            self.assertEqual(baseline, after_ai_only)

            tracked.write_text("v2\n", encoding="utf-8")
            _git(root, "add", "app/example.txt")
            changed = ai_context.sync_index(root, stage=True)
            self.assertTrue(changed)
            staged_paths = _git(root, "diff", "--cached", "--name-only").splitlines()
            self.assertIn("app/example.txt", staged_paths)
            self.assertIn(".ai/context_index.json", staged_paths)
            actual = json.loads((root / ai_context.INDEX_PATH).read_text(encoding="utf-8"))
            expected = ai_context.build_index(root, ai_context.staged_tree_sha(root))
            self.assertEqual(actual, expected)

    def test_drift_warns_without_blocking_unknown_routes(self) -> None:
        report = ai_context.drift_report(ROOT, ["future_area/new_service.py"])
        self.assertTrue(report["index_current"])
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["unclassified_changes"], ["future_area/new_service.py"])

    def test_handoff_render_is_compact_and_explicit(self) -> None:
        payload = {
            "branch": "feature/example",
            "sha": "abc123",
            "base_ref": "main",
            "objective": "Fix example",
            "changed_files": ["app/example.py"],
            "working_tree": [],
            "verified": ["root cause confirmed"],
            "tests_run": ["tests.test_example"],
            "blockers": [],
            "next_action": "Run full validation.",
            "suggested_tests": ["tests.test_example"],
        }
        rendered = ai_context.render_handoff(payload)
        self.assertIn("Branch: `feature/example`", rendered)
        self.assertIn("SHA: `abc123`", rendered)
        self.assertIn("root cause confirmed", rendered)
        self.assertIn("Run full validation.", rendered)
        self.assertNotIn("full logs", rendered.casefold())

    def test_agent_contract_routes_through_compact_context(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("tools.ai_context status", agents)
        self.assertIn("AI_CONTEXT.md", agents)
        hook = (ROOT / "tools/git_hook.py").read_text(encoding="utf-8")
        self.assertIn("sync_index", hook)


if __name__ == "__main__":
    unittest.main()
