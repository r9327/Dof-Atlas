"""Read public GitHub Releases and download immutable release assets without a token."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .manifest import MAX_MANIFEST_BYTES, ManifestError, ReleaseManifest, parse_manifest

REPO = "r9327/Dof-Atlas-App"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
MANIFEST_NAME = "atlas-manifest.json"
ARCHIVE_NAME = "atlas-windows.zip"
LAUNCHER_NAME = "DofusAtlas.exe"
# GitHub Releases requires every individual asset to be strictly below 2 GiB.
MAX_ARCHIVE_BYTES = 2 * 1024**3 - 1
_ALLOWED_REDIRECT_HOSTS = frozenset({
    "github.com", "api.github.com", "release-assets.githubusercontent.com",
    "objects.githubusercontent.com", "github-releases.githubusercontent.com",
})
_AGENT = "DofusAtlas-Updater/1"
Progress = Callable[[int, int], None]


class UpdateError(RuntimeError):
    """The release could not be checked, transferred or installed."""


@dataclass(frozen=True)
class RemoteRelease:
    tag: str
    archive_url: str
    archive_size: int
    manifest: ReleaseManifest
    launcher_url: str | None = None


def _safe_url(url: str, *, asset: bool = False) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password or parts.port:
        raise UpdateError("Untrusted update URL")
    if (parts.hostname or "").lower() not in _ALLOWED_REDIRECT_HOSTS:
        raise UpdateError("Unexpected update host")
    if asset:
        if (parts.hostname or "").lower() != "github.com":
            raise UpdateError("Update assets must come from the official GitHub release")
        prefix = f"/{REPO}/releases/download/"
        if not parts.path.startswith(prefix) or parts.query or parts.fragment:
            raise UpdateError("Unexpected release asset path")
    return url


class _StrictRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_StrictRedirect())


def _open(url: str, headers: dict[str, str] | None = None):
    request = urllib.request.Request(
        _safe_url(url),
        headers={"User-Agent": _AGENT, "Accept": "application/octet-stream", **(headers or {})},
    )
    return _OPENER.open(request, timeout=20)


def _read_limited(url: str, limit: int) -> bytes:
    try:
        with _open(url) as response:
            data = response.read(limit + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError(f"Unable to contact GitHub: {exc}") from exc
    if len(data) > limit:
        raise UpdateError("Metadata exceeds allowed size")
    return data


def latest_release() -> RemoteRelease:
    """Read ONLY the official stable GitHub Releases API endpoint."""
    try:
        doc = json.loads(_read_limited(API_URL, 1024 * 1024))
        if not isinstance(doc, dict) or doc.get("draft") or doc.get("prerelease"):
            raise UpdateError("No stable release available")
        assets = doc["assets"]
        if not isinstance(assets, list):
            raise UpdateError("Invalid release assets")
        tag = doc["tag_name"]
        if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9._+-]{1,100}", tag):
            raise UpdateError("Invalid release tag")
        indexed = {item["name"]: item for item in assets if isinstance(item, dict) and
                   item.get("name") in (MANIFEST_NAME, ARCHIVE_NAME, LAUNCHER_NAME)}
        if not {MANIFEST_NAME, ARCHIVE_NAME}.issubset(indexed):
            raise UpdateError("Release assets missing")
        manifest_asset = indexed[MANIFEST_NAME]
        archive_asset = indexed[ARCHIVE_NAME]
        manifest_url = _safe_url(manifest_asset["browser_download_url"], asset=True)
        archive_url = _safe_url(archive_asset["browser_download_url"], asset=True)
        if not manifest_url.endswith("/" + MANIFEST_NAME) or not archive_url.endswith("/" + ARCHIVE_NAME):
            raise UpdateError("Asset names do not match expected release")
        if not isinstance(archive_asset.get("size"), int) or not 0 < archive_asset["size"] <= MAX_ARCHIVE_BYTES:
            raise UpdateError("Invalid release archive size")
        manifest = parse_manifest(_read_limited(manifest_url, MAX_MANIFEST_BYTES))
        launcher_url = None
        if manifest.launcher_sha256 is not None:
            launcher_asset = indexed.get(LAUNCHER_NAME)
            if not launcher_asset or type(launcher_asset.get("size")) is not int:
                raise UpdateError("Launcher asset missing")
            if launcher_asset["size"] != manifest.launcher_size:
                raise UpdateError("Launcher asset size mismatch")
            launcher_url = _safe_url(launcher_asset["browser_download_url"], asset=True)
            if not launcher_url.endswith("/" + LAUNCHER_NAME):
                raise UpdateError("Launcher asset URL mismatch")
        return RemoteRelease(tag, archive_url, archive_asset["size"], manifest, launcher_url)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, ManifestError) as exc:
        raise UpdateError("Invalid release metadata") from exc


def download_archive(release: RemoteRelease, directory: Path, progress: Progress | None = None) -> Path:
    """Resume a partial HTTP download only if a valid Content-Range is returned."""
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{release.manifest.source_sha[:20]}.zip.part"
    target = directory / filename
    previous = target.stat().st_size if target.is_file() else 0
    if previous > release.archive_size:
        target.unlink()
        previous = 0
    if previous == release.archive_size:
        if progress:
            progress(previous, release.archive_size)
        return target
    headers = {"Range": f"bytes={previous}-"} if previous else {}
    try:
        with _open(release.archive_url, headers) as response:
            status = getattr(response, "status", 200)
            ranged = previous > 0 and status == 206
            if ranged:
                content_range = response.headers.get("Content-Range", "")
                expected = f"bytes {previous}-{release.archive_size - 1}/{release.archive_size}"
                if content_range != expected:
                    raise UpdateError("Invalid HTTP resume range")
            elif status != 200:
                raise UpdateError("Unexpected HTTP response")
            done = previous if ranged else 0
            with target.open("ab" if ranged else "wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    done += len(block)
                    if done > release.archive_size:
                        raise UpdateError("Download exceeds declared size")
                    output.write(block)
                    if progress:
                        progress(done, release.archive_size)
        if target.stat().st_size != release.archive_size:
            raise UpdateError("Incomplete release archive; download can resume later")
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError(f"Release download interrupted: {exc}") from exc
    return target
