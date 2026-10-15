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

    def test_api_json_header_and_binary_release_asset_header_are_distinct(self):
        from app.distribution import release_client as client
        sources = (
            (client.API_URL, "application/vnd.github+json"),
            (client.WEB_LATEST_URL, "text/html"),
            ("https://github.com/r9327/Dof-Atlas-App/releases/download/"
             "sha-aaa/atlas-manifest.json", "application/octet-stream"),
        )
        with patch.object(client, "_OPENER") as opener:
            for address, expected in sources:
                with self.subTest(address=address):
                    client._open(address)
                    request = opener.open.call_args.args[0]
                    self.assertEqual(request.get_header("Accept"), expected)
                    self.assertEqual(opener.open.call_args.kwargs["timeout"], 20)

    def test_range_headers_preserved_for_real_release_parts(self):
        from app.distribution import release_client as client
        target = ("https://github.com/r9327/Dof-Atlas-App/releases/"
                  "download/sha-aaa/atlas-windows.part0001")
        with patch.object(client, "_OPENER") as opener:
            client._open(target, {"Range": "bytes=0-3"})
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_header("Range"), "bytes=0-3")
            self.assertEqual(request.get_header("Accept"), "application/octet-stream")

    def test_full_first_install_is_triggered_after_successful_publication(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] /
                  ".github/workflows/atlas-public-release-smoke.yml").read_text(
                      encoding="utf-8"
                  )
        full_job = source.split("  complete-first-install:", 1)[1]
        self.assertIn("github.event_name == 'workflow_run'", full_job)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", full_job)
        self.assertIn("needs: [public-windows-install]", full_job)
        self.assertNotIn("if: github.event_name == 'push'", full_job)


    def test_public_e2e_never_runs_before_release_and_is_exact_sha(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] /
                ".github/workflows/atlas-public-release-smoke.yml").read_text(
                    encoding="utf-8"
                )
        header = text.split("permissions:", 1)[0]
        self.assertNotIn("  push:", header)
        self.assertIn("  workflow_run:", header)
        public = text.split("  public-windows-install:", 1)[1].split(
            "  complete-first-install:", 1)[0]
        self.assertNotIn("github.event_name == 'push'", public)
        full = text.split("  complete-first-install:", 1)[1]
        self.assertIn("ref: ${{ github.event.workflow_run.head_sha }}", full)
        self.assertIn("EXPECTED_SHA: ${{ github.event.workflow_run.head_sha }}", full)
        self.assertIn('--expected-source-sha "$env:EXPECTED_SHA" --full-install', full)
        self.assertIn("cancel-in-progress: false", text)

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


    def test_public_asset_digests_must_match_release_manifest(self):
        from scripts.windows.probe_public_release import verify_published_digests
        remote = self.remote()
        base = ("https://github.com/r9327/Dof-Atlas-App/releases/"
                "download/sha-aaa/")
        assets = [
            {"name": part.name, "size": part.size,
             "digest": "sha256:" + part.sha256,
             "browser_download_url": base + part.name}
            for part in remote.manifest.archive_parts
        ]
        verify_published_digests({"assets": assets}, remote)
        assets[1]["digest"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(UpdateError, "Published archive digest"):
            verify_published_digests({"assets": assets}, remote)

    def test_public_setup_must_pass_github_computed_sha256(self):
        import hashlib
        from scripts.windows.probe_public_release import download_public_setup
        remote = self.remote()
        payload = b"MZ" + b"valid-installer-bytes"
        data = {"assets": [
            {"name": "DofusAtlasSetup.exe", "size": len(payload),
             "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
             "browser_download_url":
              "https://github.com/r9327/Dof-Atlas-App/releases/"
              "download/sha-aaa/DofusAtlasSetup.exe"}]}
        with tempfile.TemporaryDirectory() as tmp, patch(
            "scripts.windows.probe_public_release._open",
            return_value=Response(payload, code=200)
        ):
            self.assertEqual(download_public_setup(data, remote, Path(tmp)).read_bytes(),
                             payload)
        data["assets"][0]["digest"] = "sha256:" + "f" * 64
        with tempfile.TemporaryDirectory() as tmp, patch(
            "scripts.windows.probe_public_release._open",
            return_value=Response(payload, code=200)
        ):
            with self.assertRaisesRegex(UpdateError, "tampered"):
                download_public_setup(data, remote, Path(tmp))


if __name__ == "__main__":
    unittest.main()
