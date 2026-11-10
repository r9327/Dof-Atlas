from __future__ import annotations

"""Optional real Hypothesis owner checks; never imported by Atlas runtime.

Skipped when Hypothesis is absent, which is NOT a qualification witness.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.atlas_doctor_lib.oss_router import _safe_files

try:
    from hypothesis import given, settings, strategies as st
except ImportError:
    @unittest.skip("NOT_AVAILABLE: Hypothesis is not installed in the dev environment")
    class DoctorOssHypothesisTests(unittest.TestCase):
        def test_hypothesis_not_installed(self):
            self.fail("Hypothesis was not installed")
else:
    class DoctorOssHypothesisTests(unittest.TestCase):
        @settings(max_examples=24, deadline=None)
        @given(st.lists(st.text(alphabet="abc123", min_size=1, max_size=10),
                        min_size=1, max_size=12, unique=True))
        def test_guide_manual_steps_keep_characters_isolated(self, steps):
            from app.modules.encyclopedia.services.guide_progress_service import (
                GuideProgressService,
            )
            with TemporaryDirectory() as directory:
                path = Path(directory) / "guide_progress.json"
                service = GuideProgressService(path)
                for step in steps:
                    service.set_manual_step_completed(
                        "character:1", "hypothesis-route", step, True)
                service.set_manual_step_completed(
                    "character:2", "hypothesis-route", "other", True)
                self.assertEqual(
                    service.manual_steps("character:1", "hypothesis-route"),
                    set(steps))
                self.assertEqual(
                    service.manual_steps("character:2", "hypothesis-route"),
                    {"other"})
                # A fresh service must preserve per-character persisted state.
                fresh = GuideProgressService(path)
                self.assertEqual(
                    fresh.manual_steps("character:1", "hypothesis-route"),
                    set(steps))
                self.assertEqual(
                    fresh.manual_steps("character:2", "hypothesis-route"),
                    {"other"})

        @settings(max_examples=40, deadline=None)
        @given(
            st.lists(st.integers(min_value=1, max_value=2**32 - 1),
                     min_size=2, max_size=8, unique=True),
            st.lists(st.booleans(), min_size=8, max_size=8),
        )
        def test_organizer_mirror_never_replays_unselected_or_source(self, handles, choices):
            from app.macros.mirror_plan import mirror_targets, mirror_delivery_targets

            selected = {hwnd for hwnd, yes in zip(handles, choices) if yes}
            source = handles[0]
            others = tuple(hwnd for hwnd in handles[1:] if hwnd in selected)
            self.assertEqual(mirror_targets(handles, selected, source), others)
            self.assertEqual(
                mirror_delivery_targets(
                    handles, selected, source, source_was_consumed=False),
                others if selected else ())
            self.assertEqual(
                mirror_delivery_targets(
                    handles, selected, source, source_was_consumed=True),
                tuple(hwnd for hwnd in handles
                      if hwnd == source or hwnd in selected) if selected else ())

        @settings(max_examples=40, deadline=None)
        @given(st.lists(st.integers(min_value=0, max_value=100000),
                        min_size=0, max_size=16),
               st.integers(min_value=0, max_value=100000))
        def test_launcher_disk_budget_never_drops_file_bytes(self, sizes, reserve):
            from types import SimpleNamespace
            from app.distribution.disk_space import remaining_space_needed
            manifest = SimpleNamespace(
                files=[SimpleNamespace(size=size) for size in sizes],
                archive_parts=(), archive_size=None)
            total = remaining_space_needed(manifest, Path("unused"),
                                           reserve_bytes=reserve)
            self.assertEqual(total, sum(sizes) + reserve)
            self.assertGreaterEqual(total, sum(sizes))

        @settings(max_examples=32, deadline=None)
        @given(st.text(alphabet="abc012-_", min_size=1, max_size=24))
        def test_launcher_refuses_relative_install_root(self, name):
            from app.distribution.install_location import _valid_root
            from app.distribution.release_client import UpdateError
            with self.assertRaises(UpdateError):
                _valid_root(Path("relative") / name)

        @settings(max_examples=32, deadline=None)
        @given(st.text(alphabet="abc012", min_size=1, max_size=12))
        def test_safe_relative_module_path(self, stem):
            with TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "tools" / f"{stem}.py"
                source.parent.mkdir(parents=True)
                source.write_text("pass\n", encoding="utf-8")
                self.assertEqual(_safe_files(root, [f"tools/{stem}.py"]),
                                 [f"tools/{stem}.py"])

        @settings(max_examples=32, deadline=None)
        @given(
            st.sampled_from(["../", "./", "/tmp/", "tools/../",
                             "tools/./", "tools/\\\\", "tools/;"]),
            st.text(alphabet="abc012", min_size=1, max_size=8),
        )
        def test_unsafe_paths_fail_closed(self, prefix, stem):
            with TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    _safe_files(Path(directory), [prefix + stem + ".py"])


if __name__ == "__main__":
    unittest.main()
