from __future__ import annotations

"""Atlas Delivery Guard: independent requirement-accounting, NOT certification.

Never execute instructions copied from issue bodies or PR descriptions.
The originating issue is the independent contract; the PR body is a report.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable

CONTRACT_START = "<!-- ATLAS_DELIVERY_CONTRACT_START -->"
CONTRACT_END = "<!-- ATLAS_DELIVERY_CONTRACT_END -->"
REPORT_START = "<!-- ATLAS_DELIVERY_REPORT_START -->"
REPORT_END = "<!-- ATLAS_DELIVERY_REPORT_END -->"
SHA = re.compile(r"[0-9a-f]{40}\Z")
ID = re.compile(r"[A-Z]{2,12}-[0-9]{3,6}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class DeliveryError(ValueError):
    """Fail closed: no implicit PASS on a malformed or missing proof."""


def enclosed_json(body: object, start: str, end: str) -> dict:
    if not isinstance(body, str) or body.count(start) != 1 or body.count(end) != 1:
        raise DeliveryError("Exactly one delivery contract/report block is required")
    middle = body.split(start, 1)[1].split(end, 1)
    if len(middle) != 2 or middle[1].strip().startswith(start):
        raise DeliveryError("Malformed delivery markers")
    try:
        value = json.loads(middle[0].strip())
    except (ValueError, TypeError) as exc:
        raise DeliveryError("Delivery block must contain strict JSON") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise DeliveryError("Unsupported delivery schema")
    return value


def safe_path(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 240:
        return False
    return (not value.startswith(("/", "." + ".")) and "\\" not in value
            and all(p not in {"", ".", ".."} for p in value.split("/"))
            and not any(ord(c) < 32 for c in value))


def declared_paths(row: dict, name: str) -> list[str]:
    items = row.get(name)
    if not isinstance(items, list) or not items or not all(safe_path(x) for x in items):
        raise DeliveryError(f"{row.get('id')}: {name} must list safe paths")
    if len(items) != len(set(items)):
        raise DeliveryError(f"{row.get('id')}: duplicate {name}")
    return items


def validate(
    contract: dict,
    report: dict,
    *,
    changed: set[str],
    checkout: Path,
    head_sha: str,
    fetch_followup: Callable[[int], dict],
) -> dict:
    if not SHA.fullmatch(head_sha) or report.get("head_sha") != head_sha:
        raise DeliveryError("Report not bound to the exact PR HEAD SHA")
    source = contract.get("requirements")
    rows = report.get("requirements")
    if not isinstance(source, list) or not source or not isinstance(rows, list):
        raise DeliveryError("Missing requirement inventory")
    if len(source) > 150 or len(rows) > 150:
        raise DeliveryError("Oversized requirement inventory")
    base = {}
    for item in source:
        if (not isinstance(item, dict) or not ID.fullmatch(str(item.get("id", "")))
                or item.get("kind") not in {"code", "docs", "manual"}
                or not isinstance(item.get("description"), str)
                or len(item["description"].strip()) < 12):
            raise DeliveryError("Invalid originating contract requirement")
        if item["id"] in base:
            raise DeliveryError("Duplicate requirement in originating issue")
        base[item["id"]] = item
    by_id = {}
    for item in rows:
        if not isinstance(item, dict) or not ID.fullmatch(str(item.get("id", ""))):
            raise DeliveryError("Malformed reported requirement")
        if item["id"] in by_id:
            raise DeliveryError("Duplicate reported requirement")
        by_id[item["id"]] = item
    if base.keys() != by_id.keys():
        raise DeliveryError(
            "Scope mismatch: missing=" + repr(sorted(base.keys() - by_id.keys()))
            + " unknown=" + repr(sorted(by_id.keys() - base.keys()))
        )
    deferred = []
    done = []
    for key, specification in base.items():
        row = by_id[key]
        status = row.get("status")
        if status == "DONE":
            if specification["kind"] == "manual":
                raise DeliveryError(f"{key}: a human/manual validation cannot self-certify")
            paths = declared_paths(row, "evidence_files")
            if not set(paths) & changed:
                raise DeliveryError(f"{key}: no concrete changed file supports DONE")
            if not all((checkout / p).is_file() for p in paths):
                raise DeliveryError(f"{key}: evidence file missing in exact checkout")
            if specification["kind"] == "code":
                tests = declared_paths(row, "test_files")
                if not all(p.startswith("tests/test_") and p.endswith(".py")
                           and (checkout / p).is_file() for p in tests):
                    raise DeliveryError(f"{key}: missing tracked regression test file")
            done.append(key)
        elif status == "DEFERRED":
            number = row.get("followup_issue")
            note = row.get("safety_evidence")
            if (not isinstance(number, int) or isinstance(number, bool)
                    or number <= 0 or not isinstance(note, str)
                    or len(note.strip()) < 25):
                raise DeliveryError(f"{key}: deferral requires issue and safety rationale")
            followup = fetch_followup(number)
            if (not isinstance(followup, dict) or followup.get("state") != "open"
                    or "pull_request" in followup
                    or key not in str(followup.get("body") or "")):
                raise DeliveryError(f"{key}: follow-up must be a separate open issue naming ID")
            deferred.append({"id": key, "issue": number})
        else:
            raise DeliveryError(f"{key}: only DONE or explicitly tracked DEFERRED allowed")
    return {
        "schema_version": 1,
        "kind": "atlas_delivery_accounting",
        "head_sha": head_sha,
        "status": "TRACKED_PARTIAL" if deferred else "ACCOUNTED_NOT_CERTIFIED",
        "done_ids": done,
        "deferred": deferred,
        "requirements_count": len(base),
        "tests_executed_by_this_gate": False,
        "manual_certified": False,
        "full_certified": False,
        "merge_authorized": False,
    }


def github_issue(repo: str, number: int) -> dict:
    if not REPO.fullmatch(repo) or not isinstance(number, int) or number <= 0:
        raise DeliveryError("Invalid issue locator")
    # Static executable, numeric argument, no shell or code from untrusted bodies.
    output = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{number}"],
        text=True, capture_output=True, check=False, timeout=30,
    )
    if output.returncode:
        raise DeliveryError(f"Cannot verify issue #{number} using read-only GitHub API")
    try:
        return json.loads(output.stdout)
    except ValueError as exc:
        raise DeliveryError("Invalid GitHub issue API response") from exc


def exact_changed_files(base_sha: str, head_sha: str) -> set[str]:
    if not SHA.fullmatch(base_sha) or not SHA.fullmatch(head_sha):
        raise DeliveryError("GitHub event missing exact base/head SHA")
    checkout_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    if checkout_sha != head_sha:
        raise DeliveryError("Wrong checkout: not PR source HEAD")
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", base_sha, head_sha],
        capture_output=True, check=True, timeout=20,
    )
    names = [p.decode("utf-8") for p in result.stdout.split(b"\0") if p]
    if not names or not all(safe_path(p) for p in names):
        raise DeliveryError("Empty or unsafe exact Git diff")
    return set(names)


def run(event: dict, *, checkout: Path, repo: str) -> dict:
    pr = event.get("pull_request")
    if not isinstance(pr, dict) or not isinstance(event.get("number"), int):
        raise DeliveryError("Only a genuine GitHub pull_request event is supported")
    if (event.get("repository", {}).get("full_name") != repo
            or pr.get("base", {}).get("repo", {}).get("full_name") != repo
            or pr.get("head", {}).get("repo", {}).get("full_name") != repo):
        raise DeliveryError("Foreign/forked PR requires a separate trusted review policy")
    head = pr.get("head", {}).get("sha")
    base = pr.get("base", {}).get("sha")
    if not isinstance(head, str) or not isinstance(base, str):
        raise DeliveryError("Missing PR refs")
    report = enclosed_json(pr.get("body"), REPORT_START, REPORT_END)
    source_number = report.get("delivery_issue")
    if (not isinstance(source_number, int) or isinstance(source_number, bool)
            or source_number <= 0 or source_number == event["number"]):
        raise DeliveryError("A separate originating delivery issue is required")
    issue = github_issue(repo, source_number)
    if (issue.get("state") != "open" or "pull_request" in issue
            or issue.get("number") != source_number):
        raise DeliveryError("The originating contract must be an open GitHub issue")
    contract = enclosed_json(issue.get("body"), CONTRACT_START, CONTRACT_END)
    return validate(
        contract, report, changed=exact_changed_files(base, head),
        checkout=checkout, head_sha=head,
        fetch_followup=lambda number: github_issue(repo, number),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if not REPO.fullmatch(repo):
            raise DeliveryError("Missing repository identity")
        event = json.loads(args.event.read_text(encoding="utf-8"))
        result = run(event, checkout=Path.cwd(), repo=repo)
    except (DeliveryError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("DELIVERY_GUARD_BLOCKED:", str(exc))
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("DELIVERY_GUARD_ACCOUNTED:", result["status"], result["head_sha"])
    for followup in result["deferred"]:
        print("UNFINISHED_TRACKED:", followup["id"], "#" + str(followup["issue"]))
    print("NOT A CERTIFICATE: Doctor, Phase, release and human validation remain separate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
