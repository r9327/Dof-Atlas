"""Test public release live-probe constraints without network calls."""
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution.manifest import ArchivePart, ReleaseManifest
from app.distribution.release_client import RemoteRelease, UpdateError
from scripts.windows.probe_public_release import probe_parts, _published_asset


class Response(io.BytesIO):
    def __init__(self, data, *, code=206, headers=None):
        super().__init__(data)
        self.status = code
        self.headers = headers or {}


class PublicProbeContracts(unittest.TestCase):
    def remote(self):
        manifest = ReleaseManifest(
            app_version="1", data_version="1", schema_version=1,
            source_sha="a" * 40, entrypoint="AtlasApp/AtlasApp.exe",
            files=(), archive_parts=(
                ArchivePart("atlas-windows.part0001", 7, "a" * 64),
                ArchivePart("atlas-windows.part0002", 8, "b" * 64),
            ), archive_size=15, archive_sha256="c" * 64,
        )
        base = ("https://github.com/r9327/Dof-Atlas-App/releases/"
                "download/sha-aaa/")
        return RemoteRelease("sha-aaa", "", 15, manifest,
                             part_urls=tuple(base + p.name for p in manifest.archive_parts))

    def test_actual_cdn_ranges_required_for_both_parts(self):
        def serve(url, headers):
            self.assertEqual(headers, {"Range": "bytes=0-3"})
            size = 7 if url.endswith("part0001") else 8
            return Response(b"abcd", headers={"Content-Range": f"bytes 0-3/{size}"})
        with patch("scripts.windows.probe_public_release._open", side_effect=serve):
            report = probe_parts(self.remote())
        self.assertEqual(len(report), 2)
        self.assertTrue(all(p["http_range"] for p in report))

    def test_cdn_ignoring_range_is_not_misreported_as_resumable(self):
        with patch("scripts.windows.probe_public_release._open",
                   return_value=Response(b"abcd", code=200)):
            with self.assertRaisesRegex(UpdateError, "did not support HTTP Range"):
                probe_parts(self.remote())

    def test_mismatched_range_is_not_accepted(self):
        with patch("scripts.windows.probe_public_release._open",
                   return_value=Response(b"abcd", headers={
                       "Content-Range": "bytes 0-3/10"
                   })):
            with self.assertRaisesRegex(UpdateError, "Wrong public HTTP Range"):
                probe_parts(self.remote())

    def test_setup_asset_is_pinned_to_official_release(self):
        name = "DofusAtlasSetup.exe"
        d = {"assets": [{"name": name, "size": 19,
             "browser_download_url":
              "https://github.com/r9327/Dof-Atlas-App/releases/download/sha-aaa/" + name}]}
        self.assertEqual(_published_asset(d, name, tag="sha-aaa")["size"], 19)
        with self.assertRaisesRegex(UpdateError, "Wrong official release asset URL"):
            _published_asset(d, name, tag="sha-bbb")


if __name__ == "__main__":
    unittest.main()
