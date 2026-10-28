"""Read public GitHub Releases and download immutable release assets without a token."""
from __future__ import annotations

import json
import hashlib
import errno
import os
import socket
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .manifest import MAX_MANIFEST_BYTES, ManifestError, ReleaseFile, ReleaseManifest, parse_manifest, verify_file
from .archive_parts import assemble_archive_parts

REPO = "r9327/Dof-Atlas-App"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
WEB_LATEST_URL = f"https://github.com/{REPO}/releases/latest"
CHANNEL_URL = f"https://github.com/{REPO}/releases/latest/download/atlas-channel.json"
CHANNEL_LIMIT = 4096
_DOWNLOAD_ATTEMPTS = 4
# Small releases stay sequential; large multipart bundles use bounded parallel I/O.
_PARALLEL_MIN_BYTES = 32 * 1024**2
_MAX_PARALLEL_PARTS = 3
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


def _open(url: str, headers: dict[str, str] | None = None, *, timeout: float = 20):
    trusted_url = _safe_url(url)
    destination = urllib.parse.urlsplit(trusted_url)
    if destination.hostname == "api.github.com":
        # The Releases REST API requires JSON negotiation. Treating it like
        # a binary asset caused HTTP 415 on real Windows public-release smoke.
        accept = "application/vnd.github+json"
    elif (destination.hostname == "github.com" and
          destination.path == f"/{REPO}/releases/latest"):
        accept = "text/html"
    else:
        accept = "application/octet-stream"
    request_headers = {"User-Agent": _AGENT, "Accept": accept}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(trusted_url, headers=request_headers)
    return _OPENER.open(request, timeout=timeout)


def _read_limited(url: str, limit: int, *, timeout: float = 20) -> bytes:
    try:
        with _open(url, timeout=timeout) as response:
            data = response.read(limit + 1)
    except (OSError, urllib.error.URLError) as exc:
        endpoint = urllib.parse.urlsplit(url)
        location = f"{endpoint.hostname}/{endpoint.path.rsplit('/', 1)[-1]}"
        raise UpdateError(f"Unable to contact GitHub: {exc} ({location})") from exc
    if len(data) > limit:
        raise UpdateError("Metadata exceeds allowed size")
    return data


def _is_offline_failure(exc: BaseException) -> bool:
    """Recognize network loss, not HTTP errors such as API rate limiting."""
    seen: set[int] = set()
    while isinstance(exc, BaseException) and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, urllib.error.HTTPError):
            return False
        if isinstance(exc, (TimeoutError, socket.gaierror, ConnectionError)):
            return True
        if isinstance(exc, OSError) and exc.errno in {
            errno.ENETDOWN, errno.ENETUNREACH, errno.EHOSTUNREACH,
            errno.ECONNREFUSED, errno.ECONNRESET,
        }:
            return True
        if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, BaseException):
            exc = exc.reason
        else:
            exc = exc.__cause__ or exc.__context__
    return False


def _latest_release_api() -> RemoteRelease:
    """Use GitHub Releases API with verified asset metadata."""
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




def _latest_release_channel() -> RemoteRelease:
    """Resolve the fixed stable-channel URL to one immutable hashed release."""
    try:
        doc = json.loads(_read_limited(CHANNEL_URL, CHANNEL_LIMIT))
        if not isinstance(doc, dict) or set(doc) != {
            "protocol_version", "channel", "tag", "source_sha",
            "manifest_sha256", "archive_size",
        } or doc["protocol_version"] != 1 or doc["channel"] != "stable":
            raise UpdateError("Invalid stable channel metadata")
        tag = doc["tag"]
        if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9._+-]{1,100}", tag):
            raise UpdateError("Invalid stable channel tag")
        source_sha, digest = doc["source_sha"], doc["manifest_sha256"]
        if (not isinstance(source_sha, str) or not re.fullmatch(r"[a-f0-9]{40}", source_sha)
                or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
            raise UpdateError("Invalid stable channel digest")
        size = doc["archive_size"]
        if type(size) is not int or not 0 < size <= 16 * 1024**3 + 512 * 1024**2:
            raise UpdateError("Invalid stable channel archive size")
        base = f"https://github.com/{REPO}/releases/download/{tag}/"
        raw = _read_limited(_safe_url(base + MANIFEST_NAME, asset=True), MAX_MANIFEST_BYTES)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise UpdateError("Stable channel manifest SHA-256 mismatch")
        manifest = parse_manifest(raw)
        if manifest.source_sha != source_sha:
            raise UpdateError("Stable channel source SHA mismatch")
        if manifest.archive_parts:
            if manifest.archive_size != size:
                raise UpdateError("Stable channel multipart size mismatch")
            part_urls = tuple(_safe_url(base + p.name, asset=True) for p in manifest.archive_parts)
            archive_url = ""
        else:
            if size > MAX_ARCHIVE_BYTES:
                raise UpdateError("Single archive exceeds GitHub size limit")
            part_urls = ()
            archive_url = _safe_url(base + ARCHIVE_NAME, asset=True)
        launcher_url = (_safe_url(base + LAUNCHER_NAME, asset=True)
                        if manifest.launcher_sha256 is not None else None)
        delta_url = (_safe_url(base + DELTA_NAME, asset=True)
                     if manifest.delta is not None else None)
        return RemoteRelease(tag, archive_url, size, manifest, launcher_url, delta_url, part_urls)
    except (KeyError, TypeError, ValueError, ManifestError) as exc:
        raise UpdateError("Invalid stable channel metadata") from exc


def _latest_release_web() -> RemoteRelease:
    """Fallback to the official stable-release redirect when the API is unavailable."""
    try:
        with _open(WEB_LATEST_URL) as response:
            final_url = _safe_url(response.geturl())
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError(f"GitHub release page unavailable: {exc}") from exc
    parsed = urllib.parse.urlsplit(final_url)
    prefix = f"/{REPO}/releases/tag/"
    if (parsed.scheme != "https" or parsed.hostname != "github.com" or
            parsed.query or parsed.fragment or not parsed.path.startswith(prefix)):
        raise UpdateError("Untrusted stable release redirect")
    tag = parsed.path[len(prefix):]
    if not re.fullmatch(r"[A-Za-z0-9._+-]{1,100}", tag):
        raise UpdateError("Invalid stable release tag")
    base = f"https://github.com/{REPO}/releases/download/{tag}/"
    try:
        manifest = parse_manifest(_read_limited(base + MANIFEST_NAME, MAX_MANIFEST_BYTES))
    except ManifestError as exc:
        raise UpdateError("Invalid GitHub release manifest") from exc

    part_urls = tuple(_safe_url(base + p.name, asset=True) for p in manifest.archive_parts)
    archive_url = "" if part_urls else _safe_url(base + ARCHIVE_NAME, asset=True)
    if part_urls:
        archive_size = manifest.archive_size
    else:
        # Single-file releases do not declare ZIP size in their manifest.
        try:
            request = urllib.request.Request(
                archive_url, headers={"User-Agent": _AGENT}, method="HEAD"
            )
            with _OPENER.open(request, timeout=20) as response:
                archive_size = int(response.headers["Content-Length"])
        except (OSError, urllib.error.URLError, ValueError, KeyError) as exc:
            raise UpdateError(f"Cannot determine official archive size: {exc}") from exc
        if not 0 < archive_size <= MAX_ARCHIVE_BYTES:
            raise UpdateError("Invalid official release archive size")
    launcher_url = (_safe_url(base + LAUNCHER_NAME, asset=True)
                    if manifest.launcher_sha256 is not None else None)
    delta_url = (_safe_url(base + DELTA_NAME, asset=True)
                 if manifest.delta is not None else None)
    return RemoteRelease(tag, archive_url, archive_size, manifest,
                         launcher_url, delta_url, part_urls)


def _current_launcher_matches_asset(doc: dict) -> bool:
    """Do not skip a pending standalone-launcher self-update on Windows."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return True
    assets = doc.get("assets")
    if not isinstance(assets, list):
        return False
    launcher = next(
        (item for item in assets if isinstance(item, dict)
         and item.get("name") == LAUNCHER_NAME), None
    )
    if not launcher:
        return False
    digest = launcher.get("digest")
    size = launcher.get("size")
    if (not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
            or type(size) is not int):
        return False
    try:
        local = Path(sys.executable)
        if not local.is_file() or local.is_symlink() or local.stat().st_size != size:
            return False
        current = hashlib.sha256()
        with local.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                current.update(block)
        return current.hexdigest() == digest.removeprefix("sha256:")
    except OSError:
        return False


def latest_release(*, installed_source_sha: str | None = None) -> RemoteRelease | None:
    """Skip the large manifest when GitHub's stable release is already installed.

    This advisory shortcut checks the official latest-release tag only. All
    changed/unknown versions still pass through the full validated manifest.
    """
    if (isinstance(installed_source_sha, str)
            and re.fullmatch(r"[a-f0-9]{40}", installed_source_sha)):
        try:
            doc = json.loads(_read_limited(API_URL, 1024 * 1024, timeout=5))
            if (isinstance(doc, dict)
                    and doc.get("draft") is False
                    and doc.get("prerelease") is False
                    and doc.get("tag_name") == f"sha-{installed_source_sha[:12]}"
                    and _current_launcher_matches_asset(doc)):
                return None
        except (ValueError, TypeError, UpdateError, OSError, urllib.error.URLError) as exc:
            # An installed, already-verified version must not wait on two more
            # 20-second GitHub fallbacks after a real network outage.
            if _is_offline_failure(exc):
                raise UpdateError("GitHub inaccessible — lancement local") from exc
            # HTTP 403/429 or malformed metadata may still be served by the
            # stable-channel/HTML fallbacks (do not treat them as offline).
            pass
    try:
        return _latest_release_api()
    except UpdateError as api_failure:
        if not str(api_failure).startswith("Unable to contact GitHub:"):
            raise
        try:
            return _latest_release_channel()
        except UpdateError as channel_failure:
            try:
                return _latest_release_web()
            except UpdateError as web_failure:
                raise UpdateError(
                    f"GitHub API: {api_failure}; stable channel: {channel_failure}; "
                    f"official release page: {web_failure}"
                ) from web_failure

def _download_multipart(release: RemoteRelease, directory: Path,
                        progress: Progress | None) -> Path:
    """Download independent verified release parts concurrently, with safe resume.

    At most three large assets are transferred at once. Each part owns its own
    .download file, strict HTTP byte-range contract and SHA-256 verification.
    Progress is monotonic across HTTP restart/retry; callbacks are serialized.
    """
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
    parts_dir = directory / (manifest.source_sha[:20] + "-parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    total = manifest.archive_size
    pieces = manifest.archive_parts
    transferred = [0] * len(pieces)
    progress_lock = threading.Lock()
    cancelled = threading.Event()
    last_reported = -1

    def update(index: int, done: int) -> None:
        nonlocal last_reported
        # Serialise callbacks and never move progress backwards when a server
        # ignores HTTP Range and a partially downloaded part restarts at zero.
        with progress_lock:
            transferred[index] = done
            complete = sum(transferred)
            if progress and complete > last_reported:
                last_reported = complete
                progress(complete, total)

    def fetch_one(index: int, part, url: str) -> None:
        finished = parts_dir / part.name
        entry = ReleaseFile(part.name, part.size, part.sha256)
        if verify_file(finished, entry):
            update(index, part.size)
            return
        finished.unlink(missing_ok=True)
        partial = parts_dir / (part.name + ".download")

        for attempt in range(_DOWNLOAD_ATTEMPTS):
            if cancelled.is_set():
                return
            offset = partial.stat().st_size if partial.is_file() else 0
            if offset == part.size:
                if verify_file(partial, entry):
                    partial.replace(finished)
                    update(index, part.size)
                    return
                partial.unlink(missing_ok=True)
                raise UpdateError(f"Corrupted release part: {part.name}")
            if offset > part.size:
                partial.unlink(missing_ok=True)
                raise UpdateError(f"Downloaded release part exceeded size: {part.name}")
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
                    update(index, done)
                    with partial.open("ab" if resumed else "wb") as output:
                        while not cancelled.is_set():
                            block = response.read(1024 * 1024)
                            if not block:
                                break
                            done += len(block)
                            if done > part.size:
                                raise UpdateError("Multipart download exceeded asset size")
                            output.write(block)
                            update(index, done)
                        output.flush()
                if cancelled.is_set():
                    return  # partial bytes remain resumable next launch
            except (OSError, urllib.error.URLError) as exc:
                if attempt == _DOWNLOAD_ATTEMPTS - 1:
                    raise UpdateError(
                        f"Interrupted download of {part.name}: {exc}"
                    ) from exc
                time.sleep(min(2 ** attempt, 4))
                continue

            if partial.stat().st_size == part.size:
                if not verify_file(partial, entry):
                    partial.unlink(missing_ok=True)
                    raise UpdateError(f"SHA-256 mismatch for {part.name}")
                partial.replace(finished)
                update(index, part.size)
                return
            if attempt == _DOWNLOAD_ATTEMPTS - 1:
                raise UpdateError(
                    f"Incomplete download of {part.name}; saved for next launch"
                )
            time.sleep(min(2 ** attempt, 4))
        raise UpdateError(f"Cannot complete release part: {part.name}")

    workers = (
        min(_MAX_PARALLEL_PARTS, len(pieces))
        if total >= _PARALLEL_MIN_BYTES else 1
    )
    if workers == 1:
        for i, (part, url) in enumerate(zip(pieces, release.part_urls)):
            fetch_one(i, part, url)
    else:
        # The executor joins outstanding workers on failure. Signalling early
        # prevents a doomed update continuing to consume gigabytes.
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="atlas-download") as executor:
            futures = [
                executor.submit(fetch_one, i, part, url)
                for i, (part, url) in enumerate(zip(pieces, release.part_urls))
            ]
            try:
                for future in as_completed(futures):
                    future.result()
            except BaseException:
                cancelled.set()
                for future in futures:
                    future.cancel()
                raise
    try:
        assemble_archive_parts(manifest, parts_dir, target)
    except (OSError, ValueError) as exc:
        raise UpdateError("Unable to verify assembled multipart ZIP") from exc
    for part in pieces:
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
