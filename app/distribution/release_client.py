"""Read public GitHub Releases and download immutable release assets without a token."""
from __future__ import annotations

import json
import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .manifest import MAX_MANIFEST_BYTES, ManifestError, ReleaseFile, ReleaseManifest, parse_manifest, verify_file
from .archive_parts import assemble_archive_parts

REPO = "r9327/Dof-Atlas-App"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
MANIFEST_NAME = "atlas-manifest.json"
ARCHIVE_NAME = "atlas-windows.zip"
LAUNCHER_NAME = "DofusAtlas.exe"
DELTA_NAME = "atlas-delta.zip"
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
    delta_url: str | None = None
    part_urls: tuple[str, ...] = ()


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
                   isinstance(item.get("name"), str) and
                   (item["name"] in (MANIFEST_NAME, ARCHIVE_NAME, LAUNCHER_NAME, DELTA_NAME)
                    or re.fullmatch(r"atlas-windows[.]part[0-9]{4}", item["name"]))}
        if MANIFEST_NAME not in indexed or len(indexed) != len([
            item for item in assets if isinstance(item, dict) and item.get("name") in indexed
        ]):
            raise UpdateError("Release assets missing or duplicate")
        manifest_asset = indexed[MANIFEST_NAME]
        manifest_url = _safe_url(manifest_asset["browser_download_url"], asset=True)
        if not manifest_url.endswith("/" + MANIFEST_NAME):
            raise UpdateError("Manifest URL does not match expected release")
        manifest = parse_manifest(_read_limited(manifest_url, MAX_MANIFEST_BYTES))
        archive_url = ""
        archive_size = 0
        part_urls: tuple[str, ...] = ()
        if manifest.archive_parts:
            URLs = []
            for part in manifest.archive_parts:
                item = indexed.get(part.name)
                if not item or type(item.get("size")) is not int or item["size"] != part.size:
                    raise UpdateError("Missing or incorrectly sized archive part")
                url = _safe_url(item["browser_download_url"], asset=True)
                if not url.endswith("/" + part.name):
                    raise UpdateError("Archive part URL mismatch")
                URLs.append(url)
            part_urls = tuple(URLs)
            archive_size = manifest.archive_size
        else:
            archive_asset = indexed.get(ARCHIVE_NAME)
            if not archive_asset:
                raise UpdateError("Release archive asset missing")
            archive_url = _safe_url(archive_asset["browser_download_url"], asset=True)
            if not archive_url.endswith("/" + ARCHIVE_NAME):
                raise UpdateError("Archive asset URL mismatch")
            if type(archive_asset.get("size")) is not int or not 0 < archive_asset["size"] <= MAX_ARCHIVE_BYTES:
                raise UpdateError("Invalid release archive size")
            archive_size = archive_asset["size"]
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
        delta_url = None
        if manifest.delta is not None:
            asset = indexed.get(DELTA_NAME)
            if not asset or type(asset.get("size")) is not int or asset["size"] != manifest.delta.archive_size:
                raise UpdateError("Differential asset size mismatch")
            delta_url = _safe_url(asset["browser_download_url"], asset=True)
            if not delta_url.endswith("/" + DELTA_NAME):
                raise UpdateError("Differential asset URL mismatch")
        return RemoteRelease(tag, archive_url, archive_size, manifest,
                             launcher_url, delta_url, part_urls)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, ManifestError) as exc:
        raise UpdateError("Invalid release metadata") from exc


def _download_multipart(release: RemoteRelease, directory: Path,
                        progress: Progress | None) -> Path:
    """Resume each authenticated part, then atomically reconstruct the ZIP."""
    manifest = release.manifest
    if not manifest.archive_parts or len(release.part_urls) != len(manifest.archive_parts):
        raise UpdateError("Incomplete multipart release metadata")
    target = directory / (manifest.source_sha[:20] + ".zip")
    if target.is_file() and verify_file(
        target, ReleaseFile(target.name, manifest.archive_size, manifest.archive_sha256)
    ):
        if progress:
            progress(manifest.archive_size, manifest.archive_size)
        return target
    target.unlink(missing_ok=True)
    progress_base = 0
    parts_dir = directory / (manifest.source_sha[:20] + "-parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    total = manifest.archive_size
    for part, url in zip(manifest.archive_parts, release.part_urls):
        finished = parts_dir / part.name
        entry = ReleaseFile(part.name, part.size, part.sha256)
        if verify_file(finished, entry):
            progress_base += part.size
            if progress:
                progress(progress_base, total)
            continue
        finished.unlink(missing_ok=True)
        partial = parts_dir / (part.name + ".download")
        offset = partial.stat().st_size if partial.is_file() else 0
        if offset >= part.size:
            partial.unlink(missing_ok=True)
            offset = 0
        try:
            with _open(url, {"Range": f"bytes={offset}-"} if offset else {}) as response:
                status = getattr(response, "status", 200)
                resumed = offset > 0 and status == 206
                if resumed:
                    expected = f"bytes {offset}-{part.size - 1}/{part.size}"
                    if response.headers.get("Content-Range", "") != expected:
                        raise UpdateError("Invalid multipart HTTP range")
                elif status != 200:
                    raise UpdateError("Unexpected multipart HTTP status")
                done = offset if resumed else 0
                with partial.open("ab" if resumed else "wb") as output:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        done += len(block)
                        if done > part.size:
                            raise UpdateError("Multipart download exceeded asset size")
                        output.write(block)
                        if progress:
                            progress(progress_base + done, total)
                    output.flush()
            if partial.stat().st_size != part.size or not verify_file(partial, entry):
                partial.unlink(missing_ok=True)
                raise UpdateError("Multipart archive SHA-256 mismatch or incomplete download")
            partial.replace(finished)
        except (OSError, urllib.error.URLError) as exc:
            raise UpdateError("Multipart download interrupted") from exc
        progress_base += part.size
    try:
        assemble_archive_parts(manifest, parts_dir, target)
    except (OSError, ValueError) as exc:
        raise UpdateError("Unable to verify assembled multipart ZIP") from exc
    for part in manifest.archive_parts:
        (parts_dir / part.name).unlink(missing_ok=True)
    return target


def download_archive(release: RemoteRelease, directory: Path, progress: Progress | None = None,
                     *, differential: bool = False) -> Path:
    """Resume HTTP downloads only after validating the server's Content-Range."""
    directory.mkdir(parents=True, exist_ok=True)
    if not differential and release.manifest.archive_parts:
        return _download_multipart(release, directory, progress)
    if differential and (release.delta_url is None or release.manifest.delta is None):
        raise UpdateError("No differential archive available")
    size = release.manifest.delta.archive_size if differential else release.archive_size
    url = release.delta_url if differential else release.archive_url
    suffix = ".delta.zip.part" if differential else ".zip.part"
    target = directory / (release.manifest.source_sha[:20] + suffix)
    previous = target.stat().st_size if target.is_file() else 0
    if previous > size:
        target.unlink()
        previous = 0
    if previous != size:
        headers = {"Range": f"bytes={previous}-"} if previous else {}
        try:
            with _open(url, headers) as response:
                status = getattr(response, "status", 200)
                ranged = previous > 0 and status == 206
                if ranged:
                    content_range = response.headers.get("Content-Range", "")
                    expected = f"bytes {previous}-{size - 1}/{size}"
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
                        if done > size:
                            raise UpdateError("Download exceeds declared size")
                        output.write(block)
                        if progress:
                            progress(done, size)
            if target.stat().st_size != size:
                raise UpdateError("Incomplete archive; download can resume later")
        except (OSError, urllib.error.URLError) as exc:
            raise UpdateError(f"Release download interrupted: {exc}") from exc
    elif progress:
        progress(previous, size)
    if differential:
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != release.manifest.delta.archive_sha256:
            target.unlink(missing_ok=True)
            raise UpdateError("Differential archive SHA-256 mismatch")
    return target
