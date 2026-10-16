"""Official GitHub fallback and resilient multipart first-install downloads."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from app.distribution import release_client as client
from app.distribution.manifest import parse_manifest


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, status=200, headers=None, url=""):
        super().__init__(payload)
        self.status = status
        self.headers = headers or {}
        self.url = url

    def geturl(self):
        return self.url


class TruncatedResponse(FakeResponse):
    def __init__(self, payload: bytes):
        super().__init__(payload)
        self._once = False

    def read(self, n=-1):
        if self._once:
            raise urllib.error.URLError("connection reset")
        self._once = True
        return super().read(2)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        parts = (b"abc", b"defg")
        self.parts = parts
        self.manifest_bytes = json.dumps({
            "protocol_version": 1, "app_version": "1.0", "data_version": "1",
            "schema_version": 1, "source_sha": "a" * 40,
            "entrypoint": "AtlasApp/AtlasApp.exe",
            "files": [{"path": "AtlasApp/AtlasApp.exe", "size": 2,
                       "sha256": hashlib.sha256(b"MZ").hexdigest()}],
            "archive_parts": [
                {"name": f"atlas-windows.part{i:04d}", "size": len(data),
                 "sha256": hashlib.sha256(data).hexdigest()}
                for i, data in enumerate(parts, 1)
            ],
            "archive_size": 7,
            "archive_sha256": hashlib.sha256(b"abcdefg").hexdigest(),
        }).encode()
        self.manifest = parse_manifest(self.manifest_bytes)
        self.base = ("https://github.com/r9327/Dof-Atlas-App/releases/"
                     "download/v1/")

    def remote(self):
        return client.RemoteRelease(
            "v1", "", 7, self.manifest,
            part_urls=tuple(self.base + p.name for p in self.manifest.archive_parts)
        )

    def test_api_failure_uses_official_web_latest_without_untrusted_host(self):
        page = "https://github.com/r9327/Dof-Atlas-App/releases/tag/v1"
        with patch.object(client, "_latest_release_api",
                          side_effect=client.UpdateError("Unable to contact GitHub: HTTP 403")), \
             patch.object(client, "_open", return_value=FakeResponse(b"", url=page)), \
             patch.object(client, "_read_limited", return_value=self.manifest_bytes) as get:
            got = client.latest_release()
        self.assertEqual(got.tag, "v1")
        self.assertEqual(got.archive_size, 7)
        self.assertEqual(got.part_urls[0], self.base + "atlas-windows.part0001")
        get.assert_called_once_with(self.base + "atlas-manifest.json",
                                    client.MAX_MANIFEST_BYTES)

    def test_web_redirect_rejects_untrusted_repository(self):
        fake = "https://github.com/not-our-repo/releases/tag/v1"
        with patch.object(client, "_open", return_value=FakeResponse(b"", url=fake)):
            with self.assertRaisesRegex(client.UpdateError, "Untrusted"):
                client._latest_release_web()

    def test_multipart_retries_interrupted_part_from_saved_offset(self):
        with tempfile.TemporaryDirectory() as d:
            urls = self.remote().part_urls
            calls = []
            def serve(url, headers=None):
                calls.append((url, headers))
                if url == urls[0] and not headers:
                    return TruncatedResponse(self.parts[0])
                if url == urls[0]:
                    self.assertEqual(headers, {"Range": "bytes=2-"})
                    return FakeResponse(b"c", status=206, headers={
                        "Content-Range": "bytes 2-2/3"
                    })
                return FakeResponse(self.parts[1])
            with patch.object(client, "_open", side_effect=serve), \
                 patch.object(client.time, "sleep", return_value=None):
                archive = client.download_archive(self.remote(), Path(d))
            self.assertEqual(archive.read_bytes(), b"abcdefg")
            self.assertEqual(len(calls), 3)

    def test_cleanly_truncated_response_resumes_without_discarding_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            urls = self.remote().part_urls
            def serve(url, headers=None):
                if url == urls[0] and not headers:
                    return FakeResponse(b"ab")
                if url == urls[0]:
                    self.assertEqual(headers, {"Range": "bytes=2-"})
                    return FakeResponse(b"c", status=206, headers={
                        "Content-Range": "bytes 2-2/3"
                    })
                return FakeResponse(self.parts[1])
            with patch.object(client, "_open", side_effect=serve), \
                 patch.object(client.time, "sleep", return_value=None):
                archive = client.download_archive(self.remote(), Path(d))
            self.assertEqual(archive.read_bytes(), b"abcdefg")

    def test_fully_received_part_in_download_cache_is_verified_and_reused(self):
        with tempfile.TemporaryDirectory() as d:
            parts_dir = Path(d) / ("a" * 20 + "-parts")
            parts_dir.mkdir()
            (parts_dir / "atlas-windows.part0001.download").write_bytes(b"abc")
            with patch.object(client, "_open",
                              return_value=FakeResponse(self.parts[1])) as opener:
                result = client.download_archive(self.remote(), Path(d))
            self.assertEqual(result.read_bytes(), b"abcdefg")
            self.assertEqual(opener.call_count, 1)


if __name__ == "__main__":
    unittest.main()
