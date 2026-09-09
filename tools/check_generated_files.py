from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_EXACT = {
    "logs/start_log.txt",
    ".coverage",
    "coverage.xml",
    "config/zaap_shortcuts.json",
    "data/bootstrap_status.txt",
    "data/encyclopedia/progress/achievement_progress.json",
    "data/encyclopedia/progress/guide_progress.json",
    "data/encyclopedia/quests/enrichment_report.json",
    "data/encyclopedia/quests/orphan_images_report.json",
    "data/local/craft_selection.json",
}
FORBIDDEN_PREFIXES = ("artifacts/", "htmlcov/")
FORBIDDEN_SUFFIXES = (
    ".sqlite-wal",
    ".sqlite-shm",
    ".dmp",
    ".dump",
    ".prof",
    ".pstats",
)
TEXT_SUFFIXES = {
    "",
    ".bat",
    ".cfg",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".key",
    ".md",
    ".pem",
    ".ps1",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
WINDOWS_USER_PATH = re.compile(r"(?i)[a-z]:[\\/]{1,2}users[\\/]{1,2}([^\\/\s\"']+)")
PRIVATE_KEY_HEADER = re.compile(r"-----BEGIN (?:EC |OPENSSH |RSA )?PRIVATE KEY-----")
SYNTHETIC_WINDOWS_USERS = {"default", "public", "testuser"}


def normalize_paths(paths: Iterable[str]) -> list[str]:
    normalized: set[str] = set()
    for path in paths:
        value = str(path).strip().replace("\\", "/")
        while value.startswith("./"):
            value = value[2:]
        if value:
            normalized.add(value)
    return sorted(normalized)


def forbidden_reason(path: str) -> str | None:
    normalized = normalize_paths([path])[0]
    lowered = normalized.lower()
    if lowered in FORBIDDEN_EXACT:
        return "runtime/generated file"
    env_name = Path(lowered).name
    if (env_name == ".env" or env_name.startswith(".env.")) and env_name not in {
        ".env.example",
        ".env.sample",
        ".env.template",
    }:
        return "local environment file"
    if lowered.startswith(FORBIDDEN_PREFIXES):
        return "generated artifact"
    if lowered.endswith(FORBIDDEN_SUFFIXES):
        return "runtime sidecar/dump/profile"
    if lowered.startswith("logs/") and lowered.endswith((".log", ".old", ".png")):
        return "runtime log/UI capture"
    return None


def find_forbidden(paths: Iterable[str]) -> list[dict[str, str]]:
    findings = []
    for path in normalize_paths(paths):
        reason = forbidden_reason(path)
        if reason:
            findings.append({"path": path, "reason": reason})
    return findings


def find_sensitive_content(root: Path, paths: Iterable[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for relative_path in normalize_paths(paths):
        path = root / relative_path
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line_number, line in enumerate(handle, start=1):
                match = WINDOWS_USER_PATH.search(line)
                if match and match.group(1).casefold() not in SYNTHETIC_WINDOWS_USERS:
                    findings.append(
                        {
                            "path": relative_path,
                            "reason": f"developer-specific Windows user path at line {line_number}",
                        }
                    )
                    break
                if PRIVATE_KEY_HEADER.search(line):
                    findings.append(
                        {"path": relative_path, "reason": f"private key header at line {line_number}"}
                    )
                    break
    return findings


def git_paths(root: Path, staged: bool) -> list[str]:
    arguments = ["diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged else ["ls-files"]
    completed = subprocess.run(
        ["git", *arguments], cwd=root, text=True, encoding="utf-8", errors="replace", capture_output=True
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git path inventory failed")
    return completed.stdout.splitlines()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject generated/runtime files from Git.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--staged", action="store_true", help="Check files staged for commit.")
    source.add_argument("--tracked", action="store_true", help="Check every tracked file (default).")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    paths = git_paths(root, staged=args.staged)
    findings = find_forbidden(paths) + find_sensitive_content(root, paths)
    report = {"status": "BLOCKED" if findings else "PASS", "findings": findings}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Generated/runtime files: {report['status']}")
        for finding in findings:
            print(f"- {finding['path']}: {finding['reason']}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
