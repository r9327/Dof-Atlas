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
PLACEHOLDER_MARKERS = (
    "<your",
    "<token",
    "<secret",
    "example",
    "placeholder",
    "changeme",
    "replace_me",
    "replace-me",
    "dummy",
    "fake",
    "redacted",
    "not-a-real",
    "not_real",
    "test-token",
    "test_token",
)
JWT_VALUE = r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
SENSITIVE_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GitHub personal access token", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("GitHub fine-grained personal access token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Supabase secret key", re.compile(r"\bsb_secret_[A-Za-z0-9_-]{20,}\b", re.IGNORECASE)),
    (
        "Supabase service-role JWT",
        re.compile(
            rf"(?i)\b(?:SUPABASE_SERVICE_ROLE_KEY|service[_-]?role(?:[_-]?key)?)\b"
            rf"\s*[\"']?\s*[:=]\s*[\"']?({JWT_VALUE})"
        ),
    ),
    (
        "JWT assigned to a secret/token field",
        re.compile(
            rf"(?i)\b(?:jwt|access[_-]?token|auth[_-]?token|api[_-]?key|secret)\b"
            rf"\s*[\"']?\s*[:=]\s*[\"']?({JWT_VALUE})"
        ),
    ),
)


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


def _looks_like_placeholder(line: str) -> bool:
    lowered = line.casefold()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _read_text_content(root: Path, relative_path: str, *, staged: bool) -> str | None:
    if staged:
        completed = subprocess.run(
            ["git", "show", f":{relative_path}"],
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if completed.returncode != 0:
            return None
        return completed.stdout

    path = root / relative_path
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="ignore")


def find_sensitive_content(
    root: Path,
    paths: Iterable[str],
    *,
    staged: bool = False,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for relative_path in normalize_paths(paths):
        if Path(relative_path).suffix.lower() not in TEXT_SUFFIXES:
            continue
        content = _read_text_content(root, relative_path, staged=staged)
        if content is None:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
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
            if _looks_like_placeholder(line):
                continue
            token_reason = next(
                (reason for reason, pattern in SENSITIVE_TOKEN_PATTERNS if pattern.search(line)),
                None,
            )
            if token_reason:
                findings.append(
                    {
                        "path": relative_path,
                        "reason": f"probable {token_reason} at line {line_number}",
                    }
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
    findings = find_forbidden(paths) + find_sensitive_content(root, paths, staged=args.staged)
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
