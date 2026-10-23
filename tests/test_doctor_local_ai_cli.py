import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.atlas_doctor_lib.local_ai_cli import main
from tools.atlas_doctor_lib.local_ai_evidence import prepare_local_evidence

SHA = "a" * 40


class LocalDoctorCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "evidence.json"
        self.file.write_text(json.dumps(prepare_local_evidence(
            source_sha=SHA, affected_paths=["app/ui.py"],
            failing_test_ids=["test.ui"], issue_ids=["BUG-123"],
        ).to_payload()), encoding="utf-8")

    def test_validation_only_without_model_or_network(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main([str(self.file), "--model", "example", "--validate-only"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "ADVISORY_ONLY")
        self.assertEqual(json.loads(stdout.getvalue())["mode"], "validated_without_model")

    def test_reject_forged_doctor_pass(self):
        data = json.loads(self.file.read_text())
        data["status"] = "PASS"
        self.file.write_text(json.dumps(data))
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = main([str(self.file), "--model", "example", "--validate-only"])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(stderr.getvalue())["status"], "UNAVAILABLE")

    def test_reject_extraneous_mutating_field(self):
        data = json.loads(self.file.read_text())
        data["shell_command"] = "echo danger"
        self.file.write_text(json.dumps(data))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.file), "--model", "example", "--validate-only"]), 2)

    def test_missing_evidence_stays_unavailable(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.file.with_name("missing.json")),
                                   "--model", "example", "--validate-only"]), 2)


if __name__ == "__main__":
    unittest.main()
