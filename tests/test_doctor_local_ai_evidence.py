import unittest

from tools.atlas_doctor_lib.local_ai_evidence import (
    InvalidDiagnostic, parse_local_suggestion, prepare_local_evidence,
)

SHA = "a" * 40


class LocalDoctorEvidenceTests(unittest.TestCase):
    def test_payload_is_bound_to_sha_and_consultative(self):
        pack = prepare_local_evidence(
            source_sha=SHA, affected_paths=["app/home.py", "app/home.py"],
            failing_test_ids=["ui.widgets.test_display"], issue_ids=["RAM-1"],
        )
        self.assertEqual(pack.affected_paths, ("app/home.py",))
        self.assertEqual(pack.to_payload()["status"], "ADVISORY_ONLY")
        self.assertEqual(pack.to_payload()["source_sha"], SHA)

    def test_reject_untrusted_paths_and_unbounded_items(self):
        for bad in ("../secrets", "/etc/passwd", "C:\\tmp\\a.py", "x\nINJECT"):
            with self.subTest(path=bad), self.assertRaises(InvalidDiagnostic):
                prepare_local_evidence(source_sha=SHA, affected_paths=[bad],
                                       failing_test_ids=[], issue_ids=[])
        with self.assertRaises(InvalidDiagnostic):
            prepare_local_evidence(source_sha=SHA, affected_paths=["a"] * 65,
                                   failing_test_ids=[], issue_ids=[])

    def test_reject_bad_sha(self):
        with self.assertRaises(InvalidDiagnostic):
            prepare_local_evidence(source_sha="HEAD", affected_paths=[],
                                   failing_test_ids=[], issue_ids=[])

    def test_suggestion_is_not_certificate(self):
        suggestion = parse_local_suggestion({
            "hypothesis": "A view may retain a worker reference.",
            "recommended_test_ids": ["test.ui.cycle"],
        })
        self.assertEqual(suggestion.status, "ADVISORY_ONLY")
        self.assertEqual(suggestion.recommended_test_ids, ("test.ui.cycle",))

    def test_reject_model_issued_verdict(self):
        for fake in (
            {"hypothesis": "CERTIFIED", "recommended_test_ids": []},
            {"hypothesis": "Possible issue", "recommended_test_ids": [], "status": "PASS"},
            {"hypothesis": "Potential regression", "recommended_test_ids": ["../bad"]},
        ):
            with self.subTest(fake=fake), self.assertRaises(InvalidDiagnostic):
                parse_local_suggestion(fake)


if __name__ == "__main__":
    unittest.main()
