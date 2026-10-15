"""Probe the *public* release from a clean Windows runner after publication.

This is deliberately distinct from PyInstaller smoke and internal ZIP checks:
it exercises GitHub public access, stable manifest discovery, HTTP Range for
each multipart asset, and the published Setup -> installed launcher path.
It never downloads the full multi-gigabyte payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

from app.distribution.release_client import (
    API_URL, REPO, UpdateError, _open, _read_limited, _safe_url, latest_release,
)
from app.distribution.manifest import verify_file, ReleaseFile


def probe_parts(release) -> list[dict]:
    """Require actual resumable byte ranges on every publicly hosted part."""
    if not release.manifest.archive_parts:
        raise UpdateError("Public release does not declare multipart archive parts")
    if len(release.part_urls) != len(release.manifest.archive_parts):
        raise UpdateError("Incomplete multipart URLs")
    results = []
    for part, url in zip(release.manifest.archive_parts, release.part_urls):
        _safe_url(url, asset=True)
        try:
            with _open(url, {"Range": "bytes=0-3"}) as response:
                status = getattr(response, "status", 0)
                if status != 206:
                    raise UpdateError(
                        f"Public CDN did not support HTTP Range for {part.name}: {status}"
                    )
                expected = f"bytes 0-3/{part.size}"
                if response.headers.get("Content-Range") != expected:
                    raise UpdateError(f"Wrong public HTTP Range for {part.name}")
                if len(response.read(4)) != 4:
                    raise UpdateError(f"Public archive part is unreadable: {part.name}")
        except (OSError, urllib.error.URLError) as exc:
            raise UpdateError(f"Public archive part unavailable: {part.name}: {exc}") from exc
        results.append({"name": part.name, "bytes": part.size, "http_range": True})
    return results


def _published_asset(doc: dict, name: str, *, tag: str) -> dict:
    entries = [asset for asset in doc.get("assets", [])
               if asset.get("name") == name]
    if len(entries) != 1 or type(entries[0].get("size")) is not int:
        raise UpdateError(f"Missing public asset: {name}")
    url = _safe_url(entries[0]["browser_download_url"], asset=True)
    if not url.endswith("/" + tag + "/" + name):
        raise UpdateError(f"Wrong official release asset URL: {name}")
    return entries[0]



def verify_published_digests(doc: dict, release) -> None:
    """Compare GitHub's measured asset digests with the packager's manifest."""
    for part in release.manifest.archive_parts:
        asset = _published_asset(doc, part.name, tag=release.tag)
        expected = "sha256:" + part.sha256
        if asset["size"] != part.size or asset.get("digest") != expected:
            raise UpdateError(f"Published archive digest or size mismatch: {part.name}")

def download_public_setup(doc: dict, release, folder: Path) -> Path:
    asset = _published_asset(doc, "DofusAtlasSetup.exe", tag=release.tag)
    if not 0 < asset["size"] <= 128 * 1024**2:
        raise UpdateError("Invalid published setup size")
    target = folder / "DofusAtlasSetup.exe"
    length = 0
    digest = hashlib.sha256()
    expected_digest = asset.get("digest")
    if not isinstance(expected_digest, str) or not expected_digest.startswith("sha256:"):
        raise UpdateError("Published setup has no GitHub SHA-256 digest")
    try:
        with _open(asset["browser_download_url"]) as source, target.open("wb") as output:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                length += len(block)
                if length > asset["size"]:
                    raise UpdateError("Public setup exceeds declared size")
                output.write(block)
                digest.update(block)
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError(f"Published setup download failed: {exc}") from exc
    with target.open("rb") as stream:
        is_exe = stream.read(2) == b"MZ"
    if (length != asset["size"] or not is_exe or
            expected_digest != "sha256:" + digest.hexdigest()):
        raise UpdateError("Incomplete or tampered public Windows setup")
    return target


def verify_frozen_setup(setup: Path, release) -> None:
    if os.name != "nt":
        raise UpdateError("Frozen Setup smoke requires a Windows runner")
    result = subprocess.run([str(setup), "--no-launch"], timeout=150,
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise UpdateError(f"Published Setup failed: {result.returncode}: {result.stderr[-400:]}")
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise UpdateError("Windows LOCALAPPDATA is missing")
    launcher = Path(local) / "Programs" / "DofusAtlas" / "DofusAtlas.exe"
    manifest = release.manifest
    if (manifest.launcher_sha256 is None or manifest.launcher_size is None or
            not verify_file(launcher, ReleaseFile(launcher.name,
                                                  manifest.launcher_size,
                                                  manifest.launcher_sha256))):
        raise UpdateError("Installed public launcher does not match release manifest")
    check = subprocess.run([str(launcher), "--atlas-self-test"], timeout=60,
                           check=False)
    if check.returncode != 0:
        raise UpdateError("Installed public launcher failed offline bootstrap")



def verify_public_quest_sources(executable: Path, *, env: dict[str, str]) -> None:
    """Check real installed frozen Quest assets before reporting E2E success."""
    try:
        check = subprocess.run([str(executable), "--atlas-package-smoke"],
                               env=env, capture_output=True, text=True,
                               timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError("Installed Quest source smoke could not run") from exc
    if check.returncode != 0:
        raise UpdateError("Installed Quest sources are missing or invalid: " +
                          check.stderr[-300:])


def verify_full_first_install(release, *, deadline_seconds: int = 2700) -> None:
    """Run the published launcher from an empty Windows runtime to healthy Qt.

    This deliberately transfers the entire public multipart payload, verifies
    files and waits until the transactional version leaves pending state.
    Only invoked by the one-time full E2E job, not routine CI.
    """
    if os.name != "nt":
        raise UpdateError("Full initial install requires a Windows runner")
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise UpdateError("Missing Windows LOCALAPPDATA")
    root = Path(local) / "DofusAtlas" / "runtime"
    log = Path(local) / "DofusAtlas" / "logs" / "updater.log"
    launcher = Path(local) / "Programs" / "DofusAtlas" / "DofusAtlas.exe"
    from app.distribution.install import active_executable, read_state
    if read_state(root).get("active"):
        raise UpdateError("Full first-install test requires a clean Windows runtime")
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --no-sandbox",
        "QTWEBENGINE_DISABLE_SANDBOX": "1",
    })
    print("Starting actual public launcher and multi-GB first installation", flush=True)
    proc = subprocess.Popen([str(launcher)], cwd=str(launcher.parent), env=env)
    deadline = time.monotonic() + deadline_seconds
    try:
        while time.monotonic() < deadline:
            state = read_state(root)
            if (state.get("source_sha") and state.get("active") and
                    not state.get("pending")):
                executable = active_executable(root)
                if executable is not None:
                    # Another certified Release can appear while the multi-GB
                    # download runs. Accept the original or the current
                    # public latest; never flag a successful installation
                    # as broken merely because publication raced the probe.
                    installed = state["source_sha"]
                    current = latest_release().manifest.source_sha
                    if installed not in {release.manifest.source_sha, current}:
                        raise UpdateError("Unexpected public source SHA installed")
                    verify_public_quest_sources(executable, env=env)
                    print("VERIFIED: full public download, integrity, Qt health and Quest sources", flush=True)
                    return
            try:
                error_text = log.read_text(encoding="utf-8") if log.is_file() else ""
            except OSError:
                error_text = ""
            if "Updater failed" in error_text:
                raise UpdateError("Actual first installation failed: " + error_text[-900:])
            if proc.poll() is not None:
                raise UpdateError("Public launcher exited before activating Atlas: " +
                                  error_text[-600:])
            time.sleep(8)
        raise UpdateError("Full public installation timed out after 45 minutes")
    finally:
        if proc.poll() is None:
            proc.terminate()

def _ci_release_metadata() -> dict:
    """Use the Actions token for API metadata only; never send it to CDN assets."""
    token = os.environ.get("ATLAS_CI_GITHUB_TOKEN", "")
    if not token:
        return json.loads(_read_limited(API_URL, 1024 * 1024))
    request = urllib.request.Request(API_URL, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "DofusAtlas-PublicSmoke/1",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read(1024 * 1024 + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError(f"Authenticated GitHub release metadata failed: {exc}") from exc
    if len(payload) > 1024 * 1024:
        raise UpdateError("Authenticated release metadata exceeds limit")
    return json.loads(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-source-sha", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-setup", action="store_true")
    parser.add_argument("--full-install", action="store_true")
    args = parser.parse_args(argv)
    report = {"status": "FAILED", "source_sha": "", "parts": []}
    try:
        release = latest_release()
        report["source_sha"] = release.manifest.source_sha
        if args.expected_source_sha and release.manifest.source_sha != args.expected_source_sha:
            raise UpdateError("Latest public Release is not the certified distribution SHA")
        doc = _ci_release_metadata()
        if doc.get("draft") or doc.get("prerelease") or doc.get("tag_name") != release.tag:
            raise UpdateError("Public API release tag does not match latest stable manifest")
        verify_published_digests(doc, release)
        report["parts"] = probe_parts(release)
        if args.verify_setup or args.full_install:
            with tempfile.TemporaryDirectory(prefix="atlas-public-setup-") as temp:
                setup = download_public_setup(doc, release, Path(temp))
                verify_frozen_setup(setup, release)
            if args.full_install:
                verify_full_first_install(release)
        report["status"] = "PASS"
    except (UpdateError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        report["error"] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
