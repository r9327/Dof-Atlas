"""Repackage JSON-only certified updates without recompiling Windows executables."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from app.distribution.install import _validate_archive
from app.distribution.archive_parts import assemble_archive_parts
from app.distribution.manifest import parse_manifest
from scripts.windows.package_release import _publishable, package_release


def repackage_data_only(previous_zip: Path, previous_manifest: Path,
                        source_root: Path, changed_paths: list[str],
                        output: Path, source_sha: str, data_version: str,
                        launcher: Path | None = None) -> tuple[Path, Path]:
    """Copy a trusted previous frozen bundle; only apply validated data/*.json changes.

    Calling workflow MUST prove from git diff that no runtime Python, UI, worker,
    packaging or schema contracts changed since the previous released SHA.
    """
    old = parse_manifest(previous_manifest.read_bytes())
    if old.schema_version != 1 or old.source_sha == source_sha:
        raise ValueError("Incompatible previous Windows release")
    if not changed_paths:
        raise ValueError("No JSON changes to publish")
    for name in changed_paths:
        relative = Path(name)
        if (not name.startswith("data/") or relative.suffix.lower() != ".json"
                or not _publishable(Path("_internal") / relative)
                or relative.is_absolute() or ".." in relative.parts):
            raise ValueError(f"Not an independently publishable JSON path: {name}")

    with tempfile.TemporaryDirectory(prefix="atlas-data-repackage-") as directory:
        temporary = Path(directory)
        if old.archive_parts:
            previous_zip = assemble_archive_parts(old, previous_zip.parent,
                                                  temporary / "previous-assembled.zip")
        with zipfile.ZipFile(previous_zip) as archive:
            _validate_archive(archive, old)
            for entry in old.files:
                target = temporary / entry.path
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                count = 0
                with archive.open(entry.path) as stream, target.open("xb") as dest:
                    while True:
                        block = stream.read(1024 * 1024)
                        if not block:
                            break
                        count += len(block)
                        if count > entry.size:
                            raise ValueError("Previous release decompression exceeded manifest")
                        digest.update(block)
                        dest.write(block)
                if count != entry.size or digest.hexdigest() != entry.sha256:
                    raise ValueError("Previous release failed SHA-256 verification")

        for name in changed_paths:
            source = source_root / name
            target = temporary / "AtlasApp" / "_internal" / name
            if source.exists():
                if source.is_symlink() or not source.is_file():
                    raise ValueError("Unsafe source JSON file")
                # Refuse JSON parse regressions before producing any public asset.
                json.loads(source.read_text(encoding="utf-8"))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            else:
                target.unlink(missing_ok=True)
        return package_release(
            temporary / "AtlasApp", output, source_sha, old.app_version,
            data_version, old.schema_version, launcher=launcher,
            base_manifest=previous_manifest,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous-zip", required=True, type=Path,
                        help="Previous ZIP, or sibling path to the previous multipart assets")
    parser.add_argument("--previous-manifest", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--changed-list", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--launcher", type=Path)
    args = parser.parse_args()
    paths = [p.strip() for p in args.changed_list.read_text().splitlines() if p.strip()]
    repackage_data_only(args.previous_zip, args.previous_manifest, args.source,
                        paths, args.output, args.source_sha, args.data_version,
                        launcher=args.launcher)


if __name__ == "__main__":
    main()
