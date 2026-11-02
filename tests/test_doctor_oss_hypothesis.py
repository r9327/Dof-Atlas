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
