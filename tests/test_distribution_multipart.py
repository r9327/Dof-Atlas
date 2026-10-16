"""Multipart GitHub Release contracts: no assets over 2 GiB, SHA-256 and resumability."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution.archive_parts import assemble_archive_parts
from app.distribution.install import install_release, active_executable
from app.distribution.manifest import ManifestError, parse_manifest
from app.distribution.release_client import RemoteRelease, UpdateError, download_archive, latest_release
from scripts.windows.package_release import package_release
from scripts.windows.repackage_data_only import repackage_data_only


class Response(io.BytesIO):
    def __init__(self, data: bytes, status: int = 200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


class MultipartDistributionTests(unittest.TestCase):
    def _package(self, base: Path):
        frozen = base / "frozen"
        frozen.mkdir(parents=True)
        original = b"MZ" + bytes(range(256)) * 8
        (frozen / "AtlasApp.exe").write_bytes(original)
        with patch("scripts.windows.package_release._MAX_GITHUB_RELEASE_ASSET_BYTES", 120), \
             patch("scripts.windows.package_release._CHUNK_BYTES", 90):
            archive, manifest_path = package_release(
                frozen, base / "release", "a" * 40, "1.0", "2026.10", 1
            )
        manifest = parse_manifest(manifest_path.read_bytes())
        self.assertGreaterEqual(len(manifest.archive_parts), 2)
        self.assertEqual(manifest.archive_size, archive.stat().st_size)
        self.assertEqual(sum(x.size for x in manifest.archive_parts), archive.stat().st_size)
        self.assertLessEqual(max(x.size for x in manifest.archive_parts), 90)
        return archive, manifest_path, manifest, original

    def _remote(self, manifest):
        prefix = "https://github.com/r9327/Dof-Atlas-App/releases/download/v1/"
        return RemoteRelease(
            "v1", "", manifest.archive_size, manifest,
            part_urls=tuple(prefix + part.name for part in manifest.archive_parts),
        )

    def test_package_assemble_then_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive, _, manifest, original = self._package(base)
            assembled = assemble_archive_parts(manifest, archive.parent, base / "joined.zip")
            self.assertEqual(archive.read_bytes(), assembled.read_bytes())
            self.assertTrue(install_release(base / "installed", assembled, manifest))
            self.assertEqual(active_executable(base / "installed").read_bytes(), original)

    def test_corrupted_part_never_activates_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive, _, manifest, _ = self._package(base)
            target = archive.parent / manifest.archive_parts[0].name
            target.write_bytes(target.read_bytes()[:-1] + b"x")
            with self.assertRaises(ValueError):
                assemble_archive_parts(manifest, archive.parent, base / "joined.zip")
            self.assertFalse((base / "joined.zip").exists())

    def test_multipart_download_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive, _, manifest, _ = self._package(base)
            remote = self._remote(manifest)
            chunks = {url: (archive.parent / part.name).read_bytes()
                      for url, part in zip(remote.part_urls, manifest.archive_parts)}
            observed = []
            def serve(url, headers=None):
                observed.append((url, headers))
                return Response(chunks[url])
            with patch("app.distribution.release_client._open", side_effect=serve):
                result = download_archive(remote, base / "downloads")
            self.assertEqual(result.read_bytes(), archive.read_bytes())
            self.assertEqual(len(observed), len(chunks))
            with patch("app.distribution.release_client._open", side_effect=AssertionError("network")):
                self.assertEqual(download_archive(remote, base / "downloads"), result)

    def test_corrupt_download_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive, _, manifest, _ = self._package(base)
            remote = self._remote(manifest)
            chunks = {url: (archive.parent / part.name).read_bytes()
                      for url, part in zip(remote.part_urls, manifest.archive_parts)}
            chunks[remote.part_urls[0]] = b"x" * len(chunks[remote.part_urls[0]])
            with patch("app.distribution.release_client._open",
                       side_effect=lambda url, headers=None: Response(chunks[url])):
                with self.assertRaises(UpdateError):
                    download_archive(remote, base / "downloads")
            self.assertFalse((base / "downloads" / ("a" * 20 + ".zip")).exists())

    def test_multipart_http_resume_uses_checked_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive, _, manifest, _ = self._package(base)
            remote = self._remote(manifest)
            chunks = {url: (archive.parent / part.name).read_bytes()
                      for url, part in zip(remote.part_urls, manifest.archive_parts)}
            pieces = base / "downloads" / ("a" * 20 + "-parts")
            pieces.mkdir(parents=True)
            first = manifest.archive_parts[0]
            (pieces / (first.name + ".download")).write_bytes(chunks[remote.part_urls[0]][:11])
            def serve(url, headers=None):
                data = chunks[url]
                if headers and "Range" in headers:
                    self.assertEqual(headers["Range"], "bytes=11-")
                    return Response(data[11:], 206, {"Content-Range": f"bytes 11-{len(data) - 1}/{len(data)}"})
                return Response(data)
            with patch("app.distribution.release_client._open", side_effect=serve):
                result = download_archive(remote, base / "downloads")
            self.assertEqual(result.read_bytes(), archive.read_bytes())

    def test_release_discovery_rejects_missing_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, manifest_path, manifest, _ = self._package(base)
            release_api = {
                "tag_name": "v1", "draft": False, "prerelease": False,
                "assets": [{"name": "atlas-manifest.json",
                            "browser_download_url": "https://github.com/r9327/Dof-Atlas-App/releases/download/v1/atlas-manifest.json",
                            "size": manifest_path.stat().st_size}],
            }
            api_url = "https://api.github.com/repos/r9327/Dof-Atlas-App/releases/latest"
            manifest_url = release_api["assets"][0]["browser_download_url"]
            def serve(url, limit):
                return json.dumps(release_api).encode() if url == api_url else manifest_path.read_bytes()
            with patch("app.distribution.release_client._read_limited", side_effect=serve):
                with self.assertRaises(UpdateError):
                    latest_release()
            for part in manifest.archive_parts:
                release_api["assets"].append({
                    "name": part.name, "size": part.size,
                    "browser_download_url": f"https://github.com/r9327/Dof-Atlas-App/releases/download/v1/{part.name}",
                })
            with patch("app.distribution.release_client._read_limited", side_effect=serve):
                remote = latest_release()
            self.assertEqual(remote.archive_size, manifest.archive_size)
            self.assertEqual(len(remote.part_urls), len(manifest.archive_parts))

    def test_manifest_rejects_missing_or_misordered_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, path, _, _ = self._package(base)
            document = json.loads(path.read_text())
            bad = dict(document)
            bad["archive_parts"] = list(reversed(document["archive_parts"]))
            with self.assertRaises(ManifestError):
                parse_manifest(json.dumps(bad).encode())
            bad = dict(document)
            del bad["archive_sha256"]
            with self.assertRaises(ManifestError):
                parse_manifest(json.dumps(bad).encode())

    def test_data_only_works_from_split_previous_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, previous_manifest, _, original = self._package(base)
            source = base / "source" / "data" / "raw"
            source.mkdir(parents=True)
            (source / "quests.json").write_text('{"ok":true}', encoding="utf-8")
            with patch("scripts.windows.package_release._MAX_GITHUB_RELEASE_ASSET_BYTES", 120), \
                 patch("scripts.windows.package_release._CHUNK_BYTES", 90):
                updated_zip, updated_manifest = repackage_data_only(
                    base / "release" / "atlas-windows.zip", previous_manifest,
                    base / "source", ["data/raw/quests.json"], base / "next",
                    "b" * 40, "2026.11"
                )
            self.assertTrue(updated_zip.is_file())
            parsed = parse_manifest(updated_manifest.read_bytes())
            self.assertTrue(parsed.archive_parts)
            rejoined = assemble_archive_parts(parsed, updated_zip.parent, base / "rejoined.zip")
            self.assertTrue(install_release(base / "installed", rejoined, parsed))
            self.assertEqual(active_executable(base / "installed").read_bytes(), original)
            with self.assertRaises(ValueError):
                assemble_archive_parts(parsed, base / "release", base / "wrong.zip")


if __name__ == "__main__":
    unittest.main()
