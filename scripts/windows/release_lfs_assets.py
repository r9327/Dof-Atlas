"""Hydrate exact candidate data LFS pointers from a pinned certified release.

This is a bandwidth fallback, not cross-SHA evidence reuse: every extracted
file must match the SHA-256 and size encoded in the candidate's own LFS pointer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_NAME = "release_lfs_assets_lock.json"
DOWNLOAD_ATTEMPTS = 5
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def read_lock(lock_root: Path) -> dict:
    lock = json.loads((lock_root / "scripts/windows" / LOCK_NAME).read_text(encoding="utf-8"))
    if (lock.get("schema_version") != 1 or lock.get("source_repo") != "r9327/Dof-Atlas-App"
            or lock.get("tag") != "sha-0ee44aeeb093"
            or lock.get("source_sha") != "0ee44aeeb09358783dcceca799b743c6fb375299"):
        raise ValueError("Invalid certified release asset lock identity")
    for entry in [lock.get("manifest"), lock.get("archive"), *lock.get("parts", [])]:
        if (not isinstance(entry, dict) or type(entry.get("size")) is not int
                or entry["size"] <= 0 or not isinstance(entry.get("sha256"), str)
                or len(entry["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in entry["sha256"])):
            raise ValueError("Invalid certified release asset pin")
    parts = lock.get("parts")
    if (not isinstance(parts, list) or [part.get("name") for part in parts]
            != ["atlas-windows.part0001", "atlas-windows.part0002"]
            or sum(part["size"] for part in parts) != lock["archive"]["size"]):
        raise ValueError("Invalid multipart release contract")
    return lock


def pointer_inventory(root: Path) -> dict[str, tuple[str, int]]:
    raw = subprocess.check_output(["git", "lfs", "ls-files", "--json"], cwd=root)
    payload = json.loads(raw)
    pointers: dict[str, tuple[str, int]] = {}
    for entry in payload.get("files", []):
        if not isinstance(entry, dict):
            raise ValueError("Malformed Git LFS inventory entry")
        item = entry.get("name")
        if not isinstance(item, str) or not item.startswith("data/"):
            continue
        oid = entry.get("oid")
        size = entry.get("size")
        if (entry.get("oid_type") != "sha256" or not isinstance(oid, str) or len(oid) != 64
                or any(c not in "0123456789abcdef" for c in oid)
                or type(size) is not int or size <= 0 or Path(item).is_absolute()
                or ".." in Path(item).parts):
            raise ValueError(f"Malformed candidate Git LFS identity: {item}")
        pointers[item] = (oid, size)
    if not pointers:
        raise ValueError("No candidate data LFS pointers found")
    return pointers


def _content_range(stream) -> str:
    headers = getattr(stream, "headers", None)
    if headers is None:
        return ""
    return str(headers.get("Content-Range", ""))


def _download_part(
    url: str,
    target: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> str:
    """Download one pinned part with bounded retries and strict HTTP resume."""
    target.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        size = target.stat().st_size if target.exists() else 0
        if size > expected_size:
            target.unlink()
            size = 0
        if size == expected_size:
            digest = _file_sha256(target)
            if digest == expected_sha256:
                return digest
            target.unlink()
            size = 0

        headers = {
            "User-Agent": "DofusAtlas-Build/1.0",
            "Accept": "application/octet-stream",
        }
        if size:
            headers["Range"] = f"bytes={size}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as stream:
                status = getattr(stream, "status", None)
                if size:
                    content_range = _content_range(stream)
                    if status != 206 or not content_range.startswith(f"bytes {size}-"):
                        raise ValueError("Pinned release server refused an exact byte-range resume")
                elif status == 206 and not _content_range(stream).startswith("bytes 0-"):
                    raise ValueError("Pinned release server returned an invalid initial byte range")

                read_block = getattr(stream, "read1", stream.read)
                with target.open("ab") as output:
                    while True:
                        block = read_block(DOWNLOAD_CHUNK_SIZE)
                        if not block:
                            break
                        size += len(block)
                        if size > expected_size:
                            raise ValueError("Pinned release asset exceeded its locked size")
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_error = exc
            if attempt == DOWNLOAD_ATTEMPTS:
                break
            continue

        if size < expected_size:
            last_error = ValueError(
                f"Pinned release asset ended early: {size} != {expected_size}"
            )
            continue
        digest = _file_sha256(target)
        if digest == expected_sha256:
            return digest
        target.unlink(missing_ok=True)
        last_error = ValueError("Pinned release asset failed SHA-256 verification")

    raise RuntimeError(
        f"Cannot retrieve pinned release asset after {DOWNLOAD_ATTEMPTS} attempts: {last_error}"
    )


def _preflight(root: Path, *, lock_root: Path) -> tuple[dict, dict[str, tuple[str, int]], str]:
    lock = read_lock(lock_root)
    pointers = pointer_inventory(root)
    base = f"https://github.com/{lock['source_repo']}/releases/download/{lock['tag']}"
    manifest_info = lock["manifest"]
    with urllib.request.urlopen(
        urllib.request.Request(f"{base}/{manifest_info['name']}", headers={"User-Agent": "DofusAtlas-Build/1.0"}),
        timeout=120,
    ) as response:
        manifest_bytes = response.read(manifest_info["size"] + 1)
    if (len(manifest_bytes) != manifest_info["size"]
            or hashlib.sha256(manifest_bytes).hexdigest() != manifest_info["sha256"]):
        raise ValueError("Pinned release manifest failed SHA-256 verification")
    manifest = json.loads(manifest_bytes)
    if (manifest.get("source_sha") != lock["source_sha"]
            or manifest.get("archive_size") != lock["archive"]["size"]
            or manifest.get("archive_sha256") != lock["archive"]["sha256"]):
        raise ValueError("Pinned release manifest identity mismatch")
    files = {entry.get("path"): entry for entry in manifest.get("files", []) if isinstance(entry, dict)}
    for relative, (digest, size) in pointers.items():
        entry = files.get(f"AtlasApp/_internal/{relative}")
        if not entry or entry.get("sha256") != digest or entry.get("size") != size:
            raise ValueError(f"Candidate LFS pointer absent or different in certified release: {relative}")
    return lock, pointers, base


def preflight(root: Path, *, lock_root: Path) -> int:
    lock, pointers, _base = _preflight(root, lock_root=lock_root)
    print(f"VERIFIED: {len(pointers)} candidate data LFS pointers in certified release {lock['tag']}")
    return len(pointers)


def hydrate(root: Path, *, lock_root: Path, work_dir: Path) -> int:
    lock, pointers, base = _preflight(root, lock_root=lock_root)

    work_dir.mkdir(parents=True, exist_ok=True)
    part_paths: list[Path] = []
    for part in lock["parts"]:
        part_path = work_dir / f"{part['name']}.download"
        got = _download_part(
            f"{base}/{part['name']}",
            part_path,
            expected_size=part["size"],
            expected_sha256=part["sha256"],
        )
        if got != part["sha256"]:
            raise ValueError(f"Pinned release part failed SHA-256 verification: {part['name']}")
        part_paths.append(part_path)

    fd, archive_name = tempfile.mkstemp(prefix="atlas-certified-", suffix=".zip", dir=work_dir)
    archive_path = Path(archive_name)
    try:
        archive_digest = hashlib.sha256()
        with os.fdopen(fd, "wb") as archive:
            for part_path in part_paths:
                with part_path.open("rb") as source:
                    for block in iter(lambda: source.read(DOWNLOAD_CHUNK_SIZE), b""):
                        archive.write(block)
                        archive_digest.update(block)
            archive.flush()
            os.fsync(archive.fileno())
        if (archive_path.stat().st_size != lock["archive"]["size"]
                or archive_digest.hexdigest() != lock["archive"]["sha256"]):
            raise ValueError("Reassembled certified release archive failed verification")

        with zipfile.ZipFile(archive_path) as bundle:
            for relative, (digest, size) in pointers.items():
                member = f"AtlasApp/_internal/{relative}"
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                fd, temp_name = tempfile.mkstemp(prefix=".atlas-lfs-", suffix=".tmp", dir=target.parent)
                try:
                    extracted = hashlib.sha256()
                    count = 0
                    with bundle.open(member) as source, os.fdopen(fd, "wb") as output:
                        for block in iter(lambda: source.read(1024 * 1024), b""):
                            count += len(block)
                            if count > size:
                                raise ValueError(f"Oversized release member: {relative}")
                            output.write(block)
                            extracted.update(block)
                        output.flush()
                        os.fsync(output.fileno())
                    if count != size or extracted.hexdigest() != digest:
                        raise ValueError(f"Extracted release member failed candidate LFS verification: {relative}")
                    os.replace(temp_name, target)
                finally:
                    Path(temp_name).unlink(missing_ok=True)
        print(f"VERIFIED: {len(pointers)} candidate data LFS assets from certified release {lock['tag']}")
        for part_path in part_paths:
            part_path.unlink(missing_ok=True)
        return len(pointers)
    finally:
        archive_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--lock-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--work-dir", type=Path, default=Path(tempfile.gettempdir()))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.preflight_only:
            preflight(args.root.resolve(), lock_root=args.lock_root.resolve())
        else:
            hydrate(args.root.resolve(), lock_root=args.lock_root.resolve(), work_dir=args.work_dir.resolve())
        return 0
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"RELEASE LFS ASSET CERTIFICATION FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
