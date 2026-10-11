from __future__ import annotations

"""Verify GitHub Actions origin + archive SHA256 before considering a passport.

Must query GitHub independently using a restricted, read-only API token.
A successful PR-controlled workflow is NOT proof of trusted test-policy code.
Consequently verification never grants automatic test reuse or FULL waiver.
"""
import argparse
import hashlib
import io
import json
import os
import re
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
MAX_ARCHIVE_BYTES = 20_000_000
API_ROOT = "https://api.github.com"


def verify_archive_origin(
    *, repository: str, run_id: int, artifact_id: int, expected_sha: str,
    workflow_name: str, run: dict[str, Any], artifact: dict[str, Any],
    zip_bytes: bytes,
) -> dict[str, Any]:
    """Pure contract; caller must retrieve GitHub API values independently."""
    errors: list[str] = []
    if not REPO.fullmatch(repository) or not SHA.fullmatch(expected_sha):
        errors.append("INVALID_REPOSITORY_OR_SHA")
    if not isinstance(run_id, int) or run_id <= 0 or not isinstance(artifact_id, int) or artifact_id <= 0:
        errors.append("INVALID_RUN_OR_ARTIFACT_ID")
    if run.get("id") != run_id or (run.get("repository") or {}).get("full_name") != repository:
        errors.append("WORKFLOW_OR_REPOSITORY_MISMATCH")
    if run.get("head_sha") != expected_sha:
        errors.append("RUN_CANDIDATE_SHA_MISMATCH")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        errors.append("WORKFLOW_NOT_SUCCESSFUL")
    if run.get("name") != workflow_name:
        errors.append("WRONG_WORKFLOW")
    if not str(run.get("path", "")).startswith(".github/workflows/"):
        errors.append("WORKFLOW_PATH_UNVERIFIED")
    if artifact.get("id") != artifact_id or artifact.get("expired") is not False:
        errors.append("ARTIFACT_MISSING_OR_EXPIRED")
    origin = artifact.get("workflow_run") or {}
    if origin.get("id") != run_id or origin.get("head_sha") != expected_sha:
        errors.append("ARTIFACT_WORKFLOW_SHA_MISMATCH")
    if origin.get("repository_id") != (run.get("repository") or {}).get("id"):
        errors.append("ARTIFACT_REPOSITORY_MISMATCH")
    if not str(artifact.get("name", "")).startswith(("doctor-plan-", "doctor-scoped-")):
        errors.append("UNEXPECTED_ARTIFACT_KIND")
    if not isinstance(zip_bytes, bytes) or len(zip_bytes) > MAX_ARCHIVE_BYTES:
        errors.append("ARCHIVE_TOO_LARGE_OR_MISSING")
        zip_bytes = b""
    digest = artifact.get("digest")
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
        errors.append("NO_GITHUB_SHA256_DIGEST")
    elif hashlib.sha256(zip_bytes).hexdigest() != DIGEST.fullmatch(digest).group(1):
        errors.append("GITHUB_ARTIFACT_DIGEST_MISMATCH")
    payload: dict[str, Any] | None = None
    if not errors:
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
                selected = [
                    item for item in zip_file.infolist()
                    if item.filename.split("/")[-1] in ("passport.json", "plan_passport.json")
                    and not item.is_dir()
                ]
                if len(selected) != 1 or selected[0].file_size > 1_000_000:
                    raise ValueError("Expected one bounded passport file")
                payload = json.loads(zip_file.read(selected[0]).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Passport is not a JSON object")
                if payload.get("candidate_sha") != expected_sha:
                    errors.append("PASSPORT_CANDIDATE_SHA_MISMATCH")
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, UnicodeError,
                json.JSONDecodeError):
            errors.append("UNREADABLE_OR_AMBIGUOUS_ARCHIVE")
    if not errors and payload is not None:
        from tools.atlas_doctor_lib.certification_engine import fingerprint
        original = dict(payload)
        stored = original.pop("content_digest", None)
        if not isinstance(stored, str) or fingerprint(original) != stored:
            errors.append("PASSPORT_DIGEST_MISMATCH")
        if any(payload.get(k) is not False for k in (
            "phase_certified", "release_certified", "full_suite_waived", "merge_authorized"
        )):
            errors.append("UNAUTHORIZED_CERTIFICATION_CLAIM")
        if payload.get("authority") != "ADVISORY_ONLY":
            errors.append("PASSPORT_NOT_ADVISORY")
    return {
        "kind": "doctor_github_artifact_origin_check",
        "status": "ARTIFACT_ORIGIN_VERIFIED_NOT_POLICY_TRUSTED" if not errors else "BLOCKED",
        "repo": repository,
        "run_id": run_id, "artifact_id": artifact_id,
        "candidate_sha": expected_sha, "errors": sorted(set(errors)),
        "github_archive_digest_verified": not errors,
        "workflow_source_trusted_for_release": False,
        "prior_test_policy_provenance_trusted": False,
        "automated_test_reuse_authorized": False,
        "full_suite_waived": False,
        "phase_certified": False,
        "note": "Verified GitHub artifact bytes and run origin do not attest PR-modifiable workflow code.",
    }


def _api(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Dofus-Atlas-Doctor-Certification",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("GitHub response too large")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("GitHub API response not an object")
    return payload


def check_online(*, repository: str, run_id: int, artifact_id: int,
                 candidate_sha: str, archive_path: Path,
                 workflow_name: str = "Doctor Adaptive Certification") -> dict[str, Any]:
    if not REPO.fullmatch(repository) or not SHA.fullmatch(candidate_sha):
        raise ValueError("Invalid GitHub repository or candidate SHA")
    if run_id <= 0 or artifact_id <= 0:
        raise ValueError("Invalid workflow IDs")
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError("Missing or unsafe ZIP file")
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive larger than 20 MB")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN (read-only Actions permission) is required")
    run = _api(f"{API_ROOT}/repos/{repository}/actions/runs/{run_id}", token)
    artifact = _api(f"{API_ROOT}/repos/{repository}/actions/artifacts/{artifact_id}", token)
    return verify_archive_origin(
        repository=repository, run_id=run_id, artifact_id=artifact_id,
        expected_sha=candidate_sha, workflow_name=workflow_name,
        run=run, artifact=artifact, zip_bytes=archive_path.read_bytes(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--workflow-name", default="Doctor Adaptive Certification")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = check_online(
            repository=args.repo, run_id=args.run_id, artifact_id=args.artifact_id,
            candidate_sha=args.expected_sha, archive_path=args.archive,
            workflow_name=args.workflow_name,
        )
    except (ValueError, OSError, TimeoutError, urllib.error.URLError,
            json.JSONDecodeError) as exc:
        result = {"kind": "doctor_github_artifact_origin_check",
                  "status": "BLOCKED", "error": type(exc).__name__,
                  "automated_test_reuse_authorized": False, "full_suite_waived": False}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ARTIFACT_ORIGIN_VERIFIED_NOT_POLICY_TRUSTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
