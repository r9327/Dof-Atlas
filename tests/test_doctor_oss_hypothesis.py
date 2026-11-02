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
