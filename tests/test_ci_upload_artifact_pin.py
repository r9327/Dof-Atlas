"""Regress the exact upload-artifact pin in the short app journey."""
from pathlib import Path
import unittest

FILE = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "atlas-short-full-app.yml"
PIN = "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2"


class UploadArtifactPinTests(unittest.TestCase):
    def test_artifact_upload_keeps_single_pinned_action(self):
        content = FILE.read_text(encoding="utf-8")
        self.assertEqual(content.count("uses: " + PIN), 1)
        self.assertIn("name: Upload full-app JSON evidence even when blocked", content)
        self.assertIn("path: artifacts/quick_app/**", content)
        self.assertNotIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", content)


if __name__ == "__main__":
    unittest.main()
