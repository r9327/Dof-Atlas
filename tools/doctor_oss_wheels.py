"""Explicit Windows developer-only, exact-wheel verified Ruff/zizmor installer.

No imports, network requests, downloads or package mutation happen merely by
importing this module. The user must invoke `--install`. Official PyPI JSON
metadata is the hash authority for the *downloaded exact filenames*; a hash
or wheel selection is never guessed for the host architecture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen

TOOL_SPEC = {
    "schema_version": 1,
    "id": "doctor_oss_windows_wheels",
    "role": "explicit Windows x64 dev-only verified OSS wheel installer",
    "capabilities": ["developer_dependency_installation", "wheel_sha256_validation"],
    "modes": ["install"],
    "cost_hint": "expensive",
    "side_effects": "mutation_unknown",
    "structured_output": True,
    "canonical": False,
    "recommended_tests": ["tests.test_doctor_oss_wheels"],
    "target_scopes": ["tools/setup_doctor_oss.ps1", "tools/atlas_doctor_lib/oss_router.py"],
}

PINS = {"ruff": "0.17.3", "zizmor": "1.30.1"}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_METADATA = 2 * 1024 * 1024
CHUNK = 256 * 1024


def windows_313_x64() -> bool:
    return (sys.platform == "win32" and sys.version_info[:2] == (3, 13)
            and platform.machine().upper() in {"AMD64", "X86_64"}
            and sys.maxsize > 2**32)


def published_wheel_digest(name: str, version: str, filename: str) -> str:
    """Fetch official PyPI metadata with bounded size and exact filename match."""
    if PINS.get(name) != version or not filename.startswith(f"{name}-{version}-"):
        raise ValueError("Package not in the exact approved tool lock")
    if not filename.endswith("-win_amd64.whl") or "/" in filename or "\\" in filename:
        raise ValueError("Only Windows x64 binary wheels are supported")
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urlopen(url, timeout=15) as response:
        if response.geturl() != url:
            raise ValueError("Unexpected PyPI metadata redirect")
        raw = response.read(MAX_METADATA + 1)
    if len(raw) > MAX_METADATA:
        raise ValueError("PyPI metadata response exceeds bounded size")
    document = json.loads(raw)
    if document.get("info", {}).get("version") != version:
        raise ValueError("PyPI metadata version mismatch")
    matching = [
        row for row in document.get("urls", [])
        if row.get("filename") == filename and row.get("packagetype") == "bdist_wheel"
        and row.get("yanked") is not True
    ]
    if len(matching) != 1:
        raise ValueError("Exact wheel missing/ambiguous in PyPI metadata")
    digest = matching[0].get("digests", {}).get("sha256")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        raise ValueError("Invalid official wheel SHA-256")
    return digest


def install_approved_wheels() -> dict:
    """Developer opt-in only. Download, verify and install exactly two wheels."""
    if not windows_313_x64():
        raise RuntimeError("Windows x64 / Python 3.13 required")
    with TemporaryDirectory(prefix="atlas_doctor_oss_") as folder:
        dest = Path(folder)
        download = [
            sys.executable, "-P", "-m", "pip", "--isolated", "download",
            "--only-binary=:all:", "--no-deps", "--no-cache-dir", "--no-input",
            "--disable-pip-version-check", "--index-url", "https://pypi.org/simple",
            "--dest", str(dest),
            *(f"{name}=={version}" for name, version in PINS.items()),
        ]
        subprocess.run(download, check=True, timeout=180)
        wheels = sorted(dest.glob("*.whl"))
        if len(wheels) != len(PINS):
            raise ValueError("Expected precisely two downloaded Windows wheels")
        observed: dict[str, tuple[str, str]] = {}
        for wheel in wheels:
            if wheel.is_symlink() or not wheel.is_file():
                raise ValueError("Invalid downloaded wheel")
            matches = [(name, version) for name, version in PINS.items()
                       if wheel.name.startswith(f"{name}-{version}-")]
            if len(matches) != 1:
                raise ValueError("Unexpected wheel in download directory")
            name, version = matches[0]
            if name in observed:
                raise ValueError("Duplicate wheel for selected package")
            if not wheel.name.endswith("-win_amd64.whl"):
                raise ValueError("Non-Windows x64 wheel returned by pip")
            expected = published_wheel_digest(name, version, wheel.name)
            digest = hashlib.sha256()
            with wheel.open("rb") as handle:
                while chunk := handle.read(CHUNK):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError("Downloaded wheel SHA-256 differs from official PyPI")
            observed[name] = (wheel.name, expected)
        if set(observed) != set(PINS):
            raise ValueError("Incomplete approved wheel selection")
        # pip will perform a second independent --require-hashes check.
        requirements = dest / "requirements-hashes.txt"
        requirements.write_text(
            "".join(f"{name}=={PINS[name]} --hash=sha256:{observed[name][1]}\n"
                    for name in PINS), encoding="ascii")
        subprocess.run([
            sys.executable, "-P", "-m", "pip", "--isolated", "install",
            "--user", "--no-index", "--find-links", str(dest),
            "--require-hashes", "--only-binary=:all:", "--no-deps",
            "--no-cache-dir", "--no-input", "--disable-pip-version-check",
            "-r", str(requirements),
        ], check=True, timeout=180)
        return {
            "status": "INSTALLED_NOT_QUALIFIED", "schema_version": 1,
            "wheels": [{"package": name, "version": PINS[name],
                        "filename": observed[name][0], "sha256": observed[name][1]}
                       for name in PINS],
            "runtime_dependencies_changed": False,
            "windows_runtime_verified": False,
            "license_verified": False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", required=True,
                        help="Explicit developer install; not an Atlas runtime action")
    parser.add_argument("--json", action="store_true",
                        help="Machine-readable stdout (also the default)")
    args = parser.parse_args(argv)
    try:
        report = install_approved_wheels()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
            json.JSONDecodeError) as exc:
        # No URLs, user paths, wheel contents or downloaded metadata in errors.
        print(json.dumps({"schema_version": 1, "status": "ERROR",
                          "error_type": type(exc).__name__,
                          "tools_installed_verified": False}))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
