"""Regression tests for the metadata-only, per-patch PR303 audit."""
import unittest
from tools.audit_pr303_commits import scan_patch


class CommitAuditTests(unittest.TestCase):
    def test_real_added_lines_and_deleted_assertions(self):
        report = scan_patch(
            "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,3 @@\n"
            "-assert True\n+try:\n+    subprocess.run(cmd, shell=True)\n"
            "+except Exception:\n+    pass\n"
        )
        self.assertEqual(report["deleted_assertions"], 1)
        self.assertEqual(report["risk_leads"]["PROCESS"], 1)
        self.assertEqual(report["risk_leads"]["EXCEPTION"], 1)

    def test_headers_and_deleted_code_are_not_counted_as_added(self):
        report = scan_patch(
            "--- a/file\n+++ b/file\n-except Exception:\n+value = 1\n"
            "Binary files a/icon.png and b/icon.png differ\n"
        )
        self.assertNotIn("EXCEPTION", report["risk_leads"])
        self.assertTrue(report["binary_manual_review"])
        self.assertEqual(report["added_lines"], 1)


if __name__ == "__main__":
    unittest.main()
