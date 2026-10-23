import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.atlas_doctor import build_parser, main
from tools.atlas_doctor_lib.local_ai_evidence import prepare_local_evidence

SHA = "a" * 40


class DoctorLocalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.evidence = Path(self.tmp.name) / "advisory.json"
        envelope = prepare_local_evidence(
            source_sha=SHA, affected_paths=["app/example.py"],
            failing_test_ids=["tests.test_widget"], issue_ids=["UI-1"],
        )
        self.evidence.write_text(json.dumps(envelope.to_payload()), encoding="utf-8")

    def test_main_command_exposes_read_only_local_advisor(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            result = main(["local-ai", str(self.evidence),
                           "--model", "example:1.5b", "--validate-only"])
        self.assertEqual(result, 0)
        output = json.loads(buffer.getvalue())
        self.assertEqual(output["status"], "ADVISORY_ONLY")
        self.assertEqual(output["mode"], "validated_without_model")
        self.assertEqual(output["evidence_sha"], SHA)

    def test_global_json_flag_does_not_enable_certificate(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--json", "local-ai", str(self.evidence),
                         "--model", "example", "--validate-only"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "ADVISORY_ONLY")

    def test_malicious_evidence_remains_unavailable(self):
        doc = json.loads(self.evidence.read_text())
        doc["status"] = "PASS"
        self.evidence.write_text(json.dumps(doc), encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = main(["local-ai", str(self.evidence),
                           "--model", "example", "--validate-only"])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(stderr.getvalue())["status"], "UNAVAILABLE")

    def test_original_agent_commands_keep_parser_contract(self):
        parser = build_parser()
        for action in ("plan", "check", "validate", "explain"):
            parsed = parser.parse_args(["agent", action, "app/example.py"])
            self.assertEqual(parsed.command, "agent")
            self.assertEqual(parsed.agent_action, action)


if __name__ == "__main__":
    unittest.main()
