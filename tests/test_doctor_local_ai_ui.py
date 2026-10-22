import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.atlas_doctor import main as doctor_main
from tools.atlas_doctor_lib.local_ai_evidence import InvalidDiagnostic
from tools.atlas_doctor_lib.local_ai_ui import from_verified_ui_session, main

SHA = "a" * 40
OTHER = "b" * 40


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def _png() -> bytes:
    # Real structurally valid 2x2 RGB image, not a fake .png extension.
    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    scanline = b"\x00" + b"\x20\x40\x60" * 2
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(scanline * 2))
            + _chunk(b"IEND", b""))


class DoctorLocalUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "ui-session"
        self.folder.mkdir()
        self.report = {
            "candidate_sha": SHA,
            "dirty": False,
            "status": "FAIL",
            "tests_executed": True,
            "required_assertions": ["guides-success/layout-960", "session/qt-exceptions"],
            "assertions": [
                {"assertion_id": "guides-success/layout-960", "assertion_status": "FAIL",
                 "evidence_ids": ["capture.png"]},
                {"assertion_id": "session/qt-exceptions", "assertion_status": "PASS",
                 "evidence_ids": ["capture.png"]},
            ],
            "required_evidence": ["capture.png"],
        }
        self._write()

    def _write(self):
        (self.folder / "capture.png").write_bytes(_png())
        (self.folder / "ui_verdict.json").write_text(json.dumps(self.report), encoding="utf-8")
        for name in ("actions.json", "request.json"):
            (self.folder / name).write_text("{}", encoding="utf-8")
        (self.folder / "worker.log").write_text("UI run recorded", encoding="utf-8")
        artifacts = {}
        for p in self.folder.iterdir():
            if p.is_file() and p.name != "manifest.json":
                artifacts[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        (self.folder / "manifest.json").write_text(json.dumps({
            "candidate_sha": SHA, "dirty": False, "artifacts": artifacts,
        }), encoding="utf-8")

    def test_failed_real_ui_report_produces_exact_sha_advisory_only(self):
        envelope = from_verified_ui_session(
            self.folder, candidate_sha=SHA,
            affected_paths=("app/modules/encyclopedia/views/guides_view.py",),
        )
        self.assertEqual(envelope.status, "ADVISORY_ONLY")
        self.assertEqual(envelope.source_sha, SHA)
        self.assertEqual(envelope.failing_test_ids, ("guides-success/layout-960",))
        self.assertEqual(envelope.issue_ids, ("UI_FAIL",))
        self.assertEqual(envelope.to_payload()["status"], "ADVISORY_ONLY")

    def test_wrong_commit_or_dirty_proof_is_rejected(self):
        with self.assertRaises(InvalidDiagnostic):
            from_verified_ui_session(self.folder, candidate_sha=OTHER)
        self.report["dirty"] = True
        self._write()
        with self.assertRaises(InvalidDiagnostic):
            from_verified_ui_session(self.folder, candidate_sha=SHA)

    def test_tampered_session_artifact_is_rejected(self):
        (self.folder / "worker.log").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(InvalidDiagnostic, "verified exact-SHA"):
            from_verified_ui_session(self.folder, candidate_sha=SHA)

    def test_passing_ui_report_does_not_call_model(self):
        self.report["status"] = "PASS"
        self.report["assertions"][0]["assertion_status"] = "PASS"
        self._write()
        with self.assertRaisesRegex(InvalidDiagnostic, "green"):
            from_verified_ui_session(self.folder, candidate_sha=SHA)

    def test_missing_required_assertion_becomes_investigation_id(self):
        self.report["status"] = "BLOCKED"
        self.report["assertions"] = []
        self._write()
        e = from_verified_ui_session(self.folder, candidate_sha=SHA)
        self.assertEqual(e.issue_ids, ("UI_BLOCKED",))
        self.assertEqual(len(e.failing_test_ids), 2)

    def test_duplicate_assertion_is_refused(self):
        self.report["assertions"].append(dict(self.report["assertions"][0]))
        self._write()
        with self.assertRaisesRegex(InvalidDiagnostic, "duplicate"):
            from_verified_ui_session(self.folder, candidate_sha=SHA)

    def test_cli_exports_to_new_file_never_overwrites(self):
        out = Path(self.tmp.name) / "advisory.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main([str(self.folder), "--candidate-sha", SHA,
                         "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "ADVISORY_ONLY")
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["source_sha"], SHA)
        before = out.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.folder), "--candidate-sha", SHA,
                                   "--out", str(out)]), 2)
        self.assertEqual(out.read_bytes(), before)

    def test_canonical_doctor_entrypoint_builds_real_ui_advisory(self):
        out = Path(self.tmp.name) / "doctor-ui-advisory.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = doctor_main([
                "local-ai-ui-evidence", str(self.folder),
                "--candidate-sha", SHA, "--out", str(out),
                "--affected-path", "app/modules/encyclopedia/views/guides_view.py",
            ])
        self.assertEqual(result, 0)
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "ADVISORY_ONLY")
        self.assertEqual(payload["source_sha"], SHA)
        self.assertEqual(payload["failing_test_ids"], ["guides-success/layout-960"])

    def test_refuse_diagnostics_when_worker_never_ran(self):
        self.report["tests_executed"] = False
        self._write()
        with self.assertRaisesRegex(InvalidDiagnostic, "unexecuted"):
            from_verified_ui_session(self.folder, candidate_sha=SHA)


if __name__ == "__main__":
    unittest.main()
