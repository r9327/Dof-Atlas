"""Materialize the small public runtime visual set without Git LFS bandwidth."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_NAME = "runtime_visual_assets_lock.json"
_MAX_ASSET = 4 * 1024 * 1024


def _digest(path: Path, size: int) -> str:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != size:
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_lock(lock_root: Path) -> dict:
    lock = json.loads((lock_root / "scripts/windows" / LOCK_NAME).read_text(encoding="utf-8"))
    repo = lock.get("source_repo")
    commit = lock.get("source_commit")
    assets = lock.get("assets")
    if (lock.get("schema_version") != 1 or repo != "r9327/Dof-Atlas-App"
            or not isinstance(commit, str) or len(commit) != 40
            or any(c not in "0123456789abcdef" for c in commit)
            or not isinstance(assets, dict) or len(assets) != 20):
        raise ValueError("Invalid runtime visual asset lock")
    expected = {"data/images/misc/dofus_atlas_logo.png"}
    expected.update(f"data/images/classes/{name}.png" for name in (
        "cra", "ecaflip", "eliotrope", "eniripsa", "enutrof", "feca", "forgelance",
        "huppermage", "iop", "osamodas", "ouginak", "pandawa", "roublard", "sacrieur",
        "sadida", "sram", "steamer", "xelor", "zobal",
    ))
    if set(assets) != expected:
        raise ValueError("Runtime visual lock does not match the export allowlist")
    for path, info in assets.items():
        if (not isinstance(info, dict) or type(info.get("size")) is not int
                or not 0 < info["size"] <= _MAX_ASSET
                or not isinstance(info.get("sha256"), str) or len(info["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in info["sha256"])
                or Path(path).is_absolute() or ".." in Path(path).parts):
            raise ValueError(f"Invalid runtime visual pin: {path}")
    return lock


def provision(root: Path, *, lock_root: Path, download: bool) -> int:
    lock = read_lock(lock_root)
    for relative, info in lock["assets"].items():
        target = root / relative
        if _digest(target, info["size"]) == info["sha256"]:
            continue
        if not download:
            raise FileNotFoundError(f"Runtime visual missing or stale: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        quoted = "/".join(urllib.parse.quote(part) for part in Path(relative).parts)
        url = (f"https://raw.githubusercontent.com/{lock['source_repo']}/"
               f"{lock['source_commit']}/{quoted}")
        request = urllib.request.Request(url, headers={"User-Agent": "DofusAtlas-Build/1.0"})
        fd, filename = tempfile.mkstemp(prefix=".atlas-visual-", suffix=".tmp", dir=target.parent)
        try:
            size = 0
            digest = hashlib.sha256()
            with os.fdopen(fd, "wb") as output:
                try:
                    with urllib.request.urlopen(request, timeout=60) as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            size += len(block)
                            if size > info["size"]:
                                raise ValueError(f"Oversized runtime visual: {relative}")
                            output.write(block)
                            digest.update(block)
                except (urllib.error.URLError, OSError) as exc:
                    raise RuntimeError(f"Cannot retrieve pinned runtime visual {relative}: {exc}") from exc
                output.flush()
                os.fsync(output.fileno())
            if size != info["size"] or digest.hexdigest() != info["sha256"]:
                raise ValueError(f"Runtime visual failed SHA-256 verification: {relative}")
            os.replace(filename, target)
        finally:
            Path(filename).unlink(missing_ok=True)
    print(f"VERIFIED: {len(lock['assets'])} pinned runtime visuals ({lock['source_commit'][:12]})")
    return len(lock["assets"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--lock-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    try:
        provision(args.root.resolve(), lock_root=args.lock_root.resolve(), download=args.download)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"RUNTIME VISUAL CERTIFICATION FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
