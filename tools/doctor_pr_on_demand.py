from __future__ import annotations

"""Resolve an explicitly requested, non-certifying PR diagnostic.

This file is executed from the trusted default branch BEFORE checking out a
PR. No token is passed to the later source/tests or Graphify process.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

SHA = re.compile(r"[0-9a-f]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
COMMENT = re.compile(r"/atlas (doctor|graphify|tools|audit|ponytail|oss|bench (?:quick|runtime|memory|preload|8|full))(?: ([0-9a-fA-F]{40}))?\Z")
LOT_COMMENT = re.compile(r"/atlas doctor-lot ([0-9a-fA-F]{40}) ([0-9a-fA-F]{40})\Z")
MODES = frozenset({"doctor", "doctor-lot", "graphify", "tools", "audit", "ponytail", "oss",
                   "bench-quick", "bench-runtime", "bench-memory",
                   "bench-preload", "bench-8", "bench-full"})
TRUSTED_ROLES = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


class RequestRejected(ValueError):
    """An untrusted, stale or malformed on-demand request."""


def parse_request(event_name: str, event: dict[str, Any]) -> tuple[int, str, str, str]:
    lot_base = ""
    if event_name == "issue_comment":
        issue = event.get("issue") or {}
        comment = event.get("comment") or {}
        if not issue.get("pull_request"):
            raise RequestRejected("Not a pull-request comment")
        if comment.get("author_association") not in TRUSTED_ROLES:
            raise RequestRejected("Only repository collaborators can request diagnostics")
        body = str(comment.get("body", "")).strip()
        lot = LOT_COMMENT.fullmatch(body)
        match = COMMENT.fullmatch(body) if lot is None else None
        if not lot and not match:
            raise RequestRejected("Unknown /atlas command or invalid 40-hex SHA")
        number = issue.get("number")
        if lot is not None:
            mode = "doctor-lot"
            lot_base, expected = lot.group(1).lower(), lot.group(2).lower()
        else:
            mode = match.group(1).replace("bench ", "bench-")
            expected = (match.group(2) or "").lower()
    elif event_name == "workflow_dispatch":
        inputs = event.get("inputs") or {}
        number = inputs.get("pr_number")
        mode = inputs.get("mode")
        expected = str(inputs.get("expected_sha") or "").strip().lower()
        lot_base = str(inputs.get("lot_base_sha") or "").strip().lower()
    else:
        raise RequestRejected("Unsupported event")
    try:
        number = int(str(number))
    except (ValueError, TypeError) as exc:
        raise RequestRejected("Invalid PR number") from exc
    if not 0 < number < 1_000_000_000:
        raise RequestRejected("Invalid PR number")
    if mode not in MODES:
        raise RequestRejected("Unknown diagnostic mode")
    if expected and not SHA.fullmatch(expected):
        raise RequestRejected("Invalid expected SHA")
    if mode == "doctor-lot":
        if not expected or not SHA.fullmatch(lot_base):
            raise RequestRejected("Development lot needs base and exact HEAD SHA")
        if lot_base == expected:
            raise RequestRejected("Development lot cannot be empty")
    elif lot_base:
        raise RequestRejected("Lot base is allowed only for doctor-lot")
    return number, mode, expected, lot_base


def resolve(
    repository: str,
    event_name: str,
    event: dict[str, Any],
    fetch_pr: Callable[[int], dict[str, Any]],
) -> dict[str, Any]:
    if not REPO.fullmatch(repository):
        raise RequestRejected("Invalid repository")
    number, mode, expected, lot_base = parse_request(event_name, event)
    pr = fetch_pr(number)
    if pr.get("state") != "open":
        raise RequestRejected("The PR must be open (Draft is accepted)")
    head, base = pr.get("head") or {}, pr.get("base") or {}
    if (head.get("repo") or {}).get("full_name") != repository:
        raise RequestRejected("Fork PR execution is not permitted")
    if (base.get("repo") or {}).get("full_name") != repository:
        raise RequestRejected("Cross-repository base is not permitted")
    head_sha = str(head.get("sha") or "").lower()
    base_sha = str(base.get("sha") or "").lower()
    if not SHA.fullmatch(head_sha) or not SHA.fullmatch(base_sha):
        raise RequestRejected("Missing or invalid PR commit")
    if expected and head_sha != expected:
        raise RequestRejected("Requested SHA is stale")
    return {
        "schema_version": 1,
        "status": "READY",
        "repository": repository,
        "pr_number": number,
        "mode": mode,
        "candidate_sha": head_sha,
        "base_sha": base_sha,
        "lot_base_sha": lot_base,
        "draft": bool(pr.get("draft")),
        "request_event": event_name,
        "certified": False,
        "full_suite_executed": False,
    }


def github_pr(repository: str, number: int, token: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repository}/pulls/{number}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "atlas-doctor-on-demand",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise RequestRejected("Malformed GitHub response")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        event = json.loads(args.event_path.read_text(encoding="utf-8"))
        if not isinstance(event, dict):
            raise RequestRejected("Invalid event JSON")
        repository = os.environ["GITHUB_REPOSITORY"]
        token = os.environ["GH_TOKEN"]
        report = resolve(repository, os.environ["GITHUB_EVENT_NAME"], event,
                         lambda number: github_pr(repository, number, token))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        with args.github_output.open("a", encoding="utf-8") as stream:
            for name, key in (
                ("pr_number", "pr_number"), ("mode", "mode"),
                ("head_sha", "candidate_sha"), ("base_sha", "base_sha"),
                ("lot_base_sha", "lot_base_sha"),
            ):
                stream.write(f"{name}={report[key]}\n")
        print(f"PR #{report['pr_number']} {report['mode']} on {report['candidate_sha']}")
        return 0
    except (RequestRejected, KeyError, OSError, ValueError, urllib.error.URLError) as exc:
        # Never echo tokens or event payload into publicly visible logs.
        print(f"On-demand request rejected: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
