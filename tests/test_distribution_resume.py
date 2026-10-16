"""HTTP range/restart contracts for standalone release downloads."""
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution.release_client import RemoteRelease, UpdateError, download_archive


class FakeHttpResponse(io.BytesIO):
    def __init__(self, payload: bytes, status: int = 200, headers: dict | None = None):
        super().__init__(payload)
        self.status = status
        self.headers = headers or {}


class DownloadRestartTests(unittest.TestCase):
    def make_release(self, total: int) -> RemoteRelease:
        from app.distribution.manifest import parse_manifest
        import hashlib
        import json
        manifest = parse_manifest(json.dumps({
            "protocol_version": 1, "app_version": "1.1", "data_version": "1",
            "schema_version": 1, "source_sha": "a" * 40,
            "entrypoint": "AtlasApp/AtlasApp.exe",
            "files": [{"path": "AtlasApp/AtlasApp.exe", "size": 3,
                       "sha256": hashlib.sha256(b"MZ!").hexdigest()}],
        }).encode())
        return RemoteRelease(
            "v1", "https://github.com/r9327/Dof-Atlas-App/releases/download/v1/atlas-windows.zip",
            total, manifest,
        )

    def test_interrupted_download_resumes_from_exact_byte(self):
        data = b"abcdefghij"
        release = self.make_release(len(data))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ("a" * 20 + ".zip.part")
            target.write_bytes(data[:4])
            headers = {"Content-Range": "bytes 4-9/10"}
            with patch("app.distribution.release_client._open",
                       return_value=FakeHttpResponse(data[4:], 206, headers)) as getter:
                result = download_archive(release, Path(directory))
            self.assertEqual(result.read_bytes(), data)
            self.assertEqual(getter.call_args.args[0], release.archive_url)
            self.assertEqual(getter.call_args.args[1], {"Range": "bytes=4-"})

    def test_http_200_restarts_partial_download_not_appends(self):
        data = b"abcdefghij"
        release = self.make_release(len(data))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ("a" * 20 + ".zip.part")
            target.write_bytes(b"old")
            with patch("app.distribution.release_client._open",
                       return_value=FakeHttpResponse(data)):
                download_archive(release, Path(directory))
            self.assertEqual(target.read_bytes(), data)

    def test_mismatched_range_is_rejected(self):
        data = b"abcdefghij"
        release = self.make_release(len(data))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ("a" * 20 + ".zip.part")
            target.write_bytes(data[:4])
            bad_headers = {"Content-Range": "bytes 3-9/10"}
            with patch("app.distribution.release_client._open",
                       return_value=FakeHttpResponse(data[4:], 206, bad_headers)):
                with self.assertRaises(UpdateError):
                    download_archive(release, Path(directory))
            self.assertEqual(target.read_bytes(), data[:4])


if __name__ == "__main__":
    unittest.main()
