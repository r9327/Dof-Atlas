from __future__ import annotations

import hashlib
import io
import json
import unittest
import zipfile

from tools.doctor_github_provenance import verify_archive_origin
from tools.atlas_doctor_lib.certification_engine import fingerprint

SHA = "a" * 40
REPO = "r9327/Dof-Atlas"
RUN = 12345
ARTIFACT = 9876


def zip_passport(*, candidate=SHA, mutate=None):
    record = {
        "kind": "doctor_certification_passport",
        "candidate_sha": candidate,
        "authority": "ADVISORY_ONLY",
        "phase_certified": False, "release_certified": False,
        "full_suite_waived": False, "merge_authorized": False,
        "verdict": "FULL_PENDING",
    }
    record["content_digest"] = fingerprint(record)
    if mutate:
        mutate(record)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("passport.json", json.dumps(record))
    return out.getvalue()


def details(blob):
    run = {
        "id": RUN, "repository": {"id": 100, "full_name": REPO},
        "head_sha": SHA, "status": "completed", "conclusion": "success",
        "name": "Doctor Adaptive Certification",
        "path": ".github/workflows/doctor-certification.yml@refs/pull/1/merge",
    }
    artifact = {
        "id": ARTIFACT, "expired": False,
        "name": "doctor-plan-12345-1",
        "digest": "sha256:" + hashlib.sha256(blob).hexdigest(),
        "workflow_run": {"id": RUN, "repository_id": 100, "head_sha": SHA},
    }
    return run, artifact


class GitHubProvenanceTests(unittest.TestCase):
    def verify(self, blob, **changes):
        run, artifact = details(blob)
        run.update(changes.get("run", {}))
        artifact.update(changes.get("artifact", {}))
        return verify_archive_origin(
            repository=REPO, run_id=RUN, artifact_id=ARTIFACT,
            expected_sha=SHA, workflow_name="Doctor Adaptive Certification",
            run=run, artifact=artifact, zip_bytes=blob,
        )

    def test_real_github_artifact_contract_is_not_release_trust(self):
        report = self.verify(zip_passport())
        self.assertEqual(report["status"], "ARTIFACT_ORIGIN_VERIFIED_NOT_POLICY_TRUSTED")
        self.assertTrue(report["github_archive_digest_verified"])
        self.assertFalse(report["workflow_source_trusted_for_release"])
        self.assertFalse(report["automated_test_reuse_authorized"])
        self.assertFalse(report["phase_certified"])

    def test_expired_failed_or_cross_repo_artifact_is_rejected(self):
        blob = zip_passport()
        for overrides in (
            {"artifact": {"expired": True}},
            {"artifact": {"workflow_run": {"id": RUN, "repository_id": 99, "head_sha": SHA}}},
            {"run": {"status": "completed", "conclusion": "failure"}},
            {"run": {"repository": {"id": 100, "full_name": "attacker/fork"}}},
            {"run": {"head_sha": "b" * 40}},
            {"run": {"name": "Completely Different Workflow"}},
        ):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.verify(blob, **overrides)["status"], "BLOCKED")

    def test_wrong_archive_digest_and_sha_are_blocked(self):
        data = zip_passport()
        self.assertIn("GITHUB_ARTIFACT_DIGEST_MISMATCH",
                      self.verify(data, artifact={"digest": "sha256:" + "0" * 64})["errors"])
        self.assertIn("PASSPORT_CANDIDATE_SHA_MISMATCH",
                      self.verify(zip_passport(candidate="b" * 40))["errors"])

    def test_forged_certificate_and_invalid_zip_blocked(self):
        bad = zip_passport(mutate=lambda p: p.update(merge_authorized=True))
        self.assertEqual(self.verify(bad)["status"], "BLOCKED")
        invalid = b"not a zip file"
        self.assertEqual(self.verify(invalid)["status"], "BLOCKED")

    def test_ambiguous_zip_passports_are_blocked(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            z.writestr("passport.json", "{}")
            z.writestr("plan_passport.json", "{}")
        self.assertIn("UNREADABLE_OR_AMBIGUOUS_ARCHIVE",
                      self.verify(data.getvalue())["errors"])

    def test_missing_github_artifact_digest_is_fatal(self):
        result = self.verify(zip_passport(), artifact={"digest": None})
        self.assertIn("NO_GITHUB_SHA256_DIGEST", result["errors"])


if __name__ == "__main__":
    unittest.main()
