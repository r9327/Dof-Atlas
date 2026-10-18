"""Emit one tiny stable pointer. Canonical file inventories remain in the release manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from app.distribution.manifest import parse_manifest


def build_channel(manifest_path: Path, archive_path: Path, tag: str | None = None) -> bytes:
    raw = manifest_path.read_bytes()
    manifest = parse_manifest(raw)
    tag = tag or "sha-" + manifest.source_sha[:12]
    if not re.fullmatch(r"[A-Za-z0-9._+-]{1,100}", tag):
        raise ValueError("Invalid channel release tag")
    if not archive_path.is_file() or archive_path.is_symlink():
        raise ValueError("Missing certified ZIP")
    size = archive_path.stat().st_size
    if not 0 < size <= 16 * 1024**3 + 512 * 1024**2:
        raise ValueError("Invalid archive size")
    if manifest.archive_parts:
        if size != manifest.archive_size:
            raise ValueError("Multipart manifest size mismatch")
    elif size >= 2 * 1024**3:
        raise ValueError("Single ZIP exceeds GitHub asset limit")
    pointer = {
        "protocol_version": 1, "channel": "stable", "tag": tag,
        "source_sha": manifest.source_sha,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "archive_size": size,
    }
    data = (json.dumps(pointer, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(data) > 4096:
        raise ValueError("Channel metadata exceeds updater limit")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", default=None)
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(build_channel(args.manifest, args.archive, args.tag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
