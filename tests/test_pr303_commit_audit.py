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

    def test_file_suffixes_and_typed_except_have_signals(self):
        paths = [".json", ".png", ".qss", ".webp", ".svg",
                 ".jpg", ".jpeg", ".ico", ".ttf", ".otf"]
        for suffix in paths:
            with self.subTest(suffix=suffix):
                report = scan_patch("+asset = 'assets/example" + suffix + "'\n")
                self.assertEqual(report["risk_leads"].get("DATA"), 1)
        report = scan_patch("+except OSError:\n+    pass\n")
        self.assertEqual(report["risk_leads"]["EXCEPTION"], 1)

    def test_performance_does_not_match_general_words(self):
        report = scan_patch("+program = 1\n+framework = 2\n+parameter = 3\n")
        self.assertNotIn("PERFORMANCE", report["risk_leads"])
        self.assertEqual(scan_patch("+ram = 2\n")["risk_leads"]["PERFORMANCE"], 1)

    def test_only_removed_real_assertions_are_counted(self):
        patch = ("-# assert noted in documentation\n"
                 "-label = 'assert passed'\n"
                 "-assert ready\n"
                 "-self.assertTrue(ready)\n"
                 "-with pytest.raises(ValueError):\n"
                 "-self.fail('unexpected')\n")
        self.assertEqual(scan_patch(patch)["deleted_assertions"], 4)

    def test_dynamic_expected_commit_count(self):
        from unittest.mock import patch
        from tools.audit_pr303_commits import review
        a = "a" * 40
        b = "b" * 40
        calls = {
            ("rev-parse", "--verify", a + "^{commit}"): a,
            ("rev-parse", "--verify", b + "^{commit}"): b,
            ("rev-list", "--reverse", a + ".." + b): b,
            ("rev-list", "--parents", "-n", "1", b): b + " " + a,
            ("diff", "--name-status", "--find-renames", a, b): "M\tapp/view.py",
            ("diff", "--no-ext-diff", "--unified=0", "--find-renames", a, b): "+ram = 1",
            ("log", "-1", "--format=%s", b): "fix memory",
        }
        with (
            patch("tools.audit_pr303_commits.git", side_effect=lambda *args: calls[args]),
            patch("tools.audit_pr303_commits.subprocess.run") as run,
        ):
            report = review(a, b)
            self.assertEqual(report["expected"], 1)
            self.assertEqual(report["expected_policy"], "DYNAMIC_RANGE")
            self.assertEqual(report["inspected"], 1)
            self.assertEqual(report["status"], "PATCH_INVENTORY_COMPLETE_HUMAN_REVIEW_REQUIRED")
            self.assertEqual(report["records"][0]["human_review"], "NOT_RUN")
            run.assert_called_once()



if __name__ == "__main__":
    unittest.main()
