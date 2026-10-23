"""Prune obsolete Atlas App releases only after the new certified release exists.

This is a post-publication maintenance step, never an installer/update bypass.
The still-working previous release must survive until the replacement is
uploaded, public, the latest stable, and complete.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

APP_REPOSITORY = "r9327/Dof-Atlas-App"
_RELEASE_TAG = re.compile(r"sha-[a-f0-9]{12}\Z")
_SOURCE_SHA = re.compile(r"[a-f0-9]{40}\Z")
_REQUIRED = frozenset({
    "atlas-manifest.json", "atlas-channel.json",
    "DofusAtlas.exe", "DofusAtlasSetup.exe",
})


class PruneRefused(RuntimeError):
    """Precondition failed: preserve every previous public release."""


def _gh(*arguments: str) -> str:
    result = subprocess.run(
        ["gh", *arguments], capture_output=True, check=True, text=True,
        encoding="utf-8", timeout=90,
    )
    return result.stdout


def _release(uri: str) -> dict:
    data = json.loads(_gh("api", uri))
    if not isinstance(data, dict):
        raise PruneRefused("Invalid GitHub release metadata")
    return data


def _all_releases() -> list[dict]:
    pages = json.loads(_gh(
        "api", "--paginate", "--slurp",
        f"repos/{APP_REPOSITORY}/releases?per_page=100",
    ))
    if not isinstance(pages, list) or not all(isinstance(x, list) for x in pages):
        raise PruneRefused("Cannot enumerate all release pages")
    result = [r for page in pages for r in page]
    if not all(isinstance(r, dict) for r in result):
        raise PruneRefused("Invalid paginated GitHub release response")
    return result


def _verify_current(
    expected_tag: str, source_sha: str, latest: dict, published: dict,
    all_releases: list[dict],
) -> list[str]:
    if not _SOURCE_SHA.fullmatch(source_sha):
        raise PruneRefused("Invalid exact source SHA")
    if expected_tag != f"sha-{source_sha[:12]}":
        raise PruneRefused("Tag differs from the certified source SHA")
    if latest.get("id") != published.get("id") or latest.get("tag_name") != expected_tag:
        raise PruneRefused("New release is not the latest stable release")
    if published.get("draft") is not False or published.get("prerelease") is not False:
        raise PruneRefused("Replacement release is not a public stable release")
    if not published.get("published_at") or source_sha not in str(published.get("body") or ""):
        raise PruneRefused("Replacement lacks source provenance")
    assets = published.get("assets")
    if not isinstance(assets, list):
        raise PruneRefused("Missing assets")
    names = {
        x.get("name") for x in assets
        if isinstance(x, dict) and type(x.get("size")) is int
        and x["size"] > 0 and x.get("state") == "uploaded"
    }
    if not _REQUIRED.issubset(names):
        raise PruneRefused(f"Replacement assets incomplete: {_REQUIRED - names}")
    if not (
        "atlas-windows.zip" in names
        or (
            "atlas-windows.part0001" in names
            and "atlas-windows.part0002" in names
        )
    ):
        raise PruneRefused("Replacement lacks a complete Windows archive")
    current_id = published.get("id")
    if not any(x.get("id") == current_id for x in all_releases):
        raise PruneRefused("Replacement missing from paginated releases")
    older: list[str] = []
    for item in all_releases:
        tag = str(item.get("tag_name") or "")
        if item.get("id") == current_id:
            continue
        # Do not remove unrelated/manual releases without a separate review.
        if not _RELEASE_TAG.fullmatch(tag):
            continue
        if item.get("draft") is False and item.get("prerelease") is False:
            if str(item.get("published_at") or "") > str(published["published_at"]):
                raise PruneRefused("Newer published release exists; abort cleanup")
        older.append(tag)
    return list(dict.fromkeys(older))


def prune(expected_tag: str, source_sha: str, *, dry_run: bool = False) -> list[str]:
    latest = _release(f"repos/{APP_REPOSITORY}/releases/latest")
    current = _release(f"repos/{APP_REPOSITORY}/releases/tags/{expected_tag}")
    all_releases = _all_releases()
    old_tags = _verify_current(expected_tag, source_sha, latest, current, all_releases)
    for tag in old_tags:
        if dry_run:
            print(f"DRY-RUN obsolete release: {tag}", flush=True)
            continue
        # GitHub CLI provides an authenticated write operation. Also remove
        # the old tag so the public release list cannot contain dead version IDs.
        _gh("release", "delete", tag, "--repo", APP_REPOSITORY,
            "--yes", "--cleanup-tag")
        print(f"Removed obsolete release and tag: {tag}", flush=True)
    print(f"Atlas App release cleanup: {len(old_tags)} obsolete releases "
          f"{'identified' if dry_run else 'deleted'}, retaining {expected_tag}",
          flush=True)
    return old_tags


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        prune(args.tag, args.source_sha, dry_run=args.dry_run)
    except (PruneRefused, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError, OSError) as error:
        print(f"Atlas App release cleanup REFUSED/FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
