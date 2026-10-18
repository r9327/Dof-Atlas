"""Stable release URL, tag rotation, integrity and legacy compatibility."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution import release_client as client
from app.distribution.release_client import UpdateError
from scripts.windows.release_channel import build_channel


def fixtures(tag="build-1"):
    raw = json.dumps({
        "protocol_version": 1, "app_version": "1.0", "data_version": "1",
        "schema_version": 1, "source_sha": "a" * 40,
        "entrypoint": "AtlasApp/AtlasApp.exe",
        "files": [{"path": "AtlasApp/AtlasApp.exe", "size": 3,
                   "sha256": hashlib.sha256(b"MZ!").hexdigest()}],
    }).encode()
    pointer = json.dumps({
        "protocol_version": 1, "channel": "stable", "tag": tag,
        "source_sha": "a" * 40,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(), "archive_size": 100,
    }).encode()
    return raw, pointer


class ChannelContractTests(unittest.TestCase):
    def read(self, raw, pointer):
        with patch.object(client, "_read_limited",
                          side_effect=lambda url, limit: (
                              pointer if url == client.CHANNEL_URL else raw
                          )):
            return client._latest_release_channel()

    def test_build_channel_links_exact_certified_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, _ = fixtures()
            (root / "atlas-manifest.json").write_bytes(raw)
            (root / "atlas-windows.zip").write_bytes(b"small-zip")
            doc = json.loads(build_channel(root / "atlas-manifest.json",
                                           root / "atlas-windows.zip"))
            self.assertEqual(doc["tag"], "sha-" + "a" * 12)
            self.assertEqual(doc["archive_size"], 9)
            self.assertEqual(doc["manifest_sha256"], hashlib.sha256(raw).hexdigest())

    def test_rename_release_without_changing_the_updater(self):
        for tag in ("sha-old", "v0.2.5", "build-new"):
            with self.subTest(tag=tag):
                release = self.read(*fixtures(tag))
                self.assertEqual(release.tag, tag)
                self.assertEqual(release.manifest.source_sha, "a" * 40)
                self.assertIn("/releases/download/" + tag + "/", release.archive_url)

    def test_reject_bad_digest_source_tag_and_archive_size(self):
        raw, pointer = fixtures()
        for key, value in (("manifest_sha256", "b" * 64),
                           ("source_sha", "b" * 40),
                           ("tag", "../not-a-tag"),
                           ("archive_size", True)):
            doc = json.loads(pointer)
            doc[key] = value
            with self.subTest(key=key), self.assertRaises(UpdateError):
                self.read(raw, json.dumps(doc).encode())

    def test_unavailable_api_uses_stable_channel(self):
        raw, pointer = fixtures("future-name")
        with patch.object(client, "_latest_release_api", side_effect=UpdateError(
            "Unable to contact GitHub: rate limited"
        )), patch.object(client, "_latest_release_web",
                          side_effect=AssertionError("unexpected legacy fallback")), patch.object(
            client, "_read_limited",
            side_effect=lambda url, limit: pointer if url == client.CHANNEL_URL else raw,
        ):
            self.assertEqual(client.latest_release().tag, "future-name")

    def test_legacy_release_without_channel_retains_web_fallback(self):
        candidate = client.RemoteRelease("legacy", "", 100,
                                        client.parse_manifest(fixtures()[0]))
        with patch.object(client, "_latest_release_api", side_effect=UpdateError(
            "Unable to contact GitHub: offline"
        )), patch.object(client, "_latest_release_channel", side_effect=UpdateError(
            "Unable to contact GitHub: 404"
        )), patch.object(client, "_latest_release_web", return_value=candidate):
            self.assertIs(client.latest_release(), candidate)


if __name__ == "__main__":
    unittest.main()
