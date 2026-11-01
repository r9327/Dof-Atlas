from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.windows.release_lfs_assets import (
    _download_part,
    hydrate,
    read_lock as read_release_lock,
)
from scripts.windows.runtime_visual_assets import provision, read_lock as read_visual_lock


class Reply(io.BytesIO):
    status = 200
    headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class RuntimeVisualAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _visual_lock(self) -> tuple[dict, dict[str, bytes]]:
        names = (
            "cra", "ecaflip", "eliotrope", "eniripsa", "enutrof", "feca", "forgelance",
            "huppermage", "iop", "osamodas", "ouginak", "pandawa", "roublard", "sacrieur",
            "sadida", "sram", "steamer", "xelor", "zobal",
        )
        payloads = {f"data/images/classes/{name}.png": f"PNG:{name}".encode() for name in names}
        payloads["data/images/misc/dofus_atlas_logo.png"] = b"PNG:logo"
        lock = {
            "schema_version": 1,
            "source_repo": "r9327/Dof-Atlas-App",
            "source_commit": "1" * 40,
            "assets": {
                path: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for path, data in payloads.items()
            },
        }
        target = self.root / "scripts/windows/runtime_visual_assets_lock.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(lock), encoding="utf-8")
        return lock, payloads

    def test_checked_in_visual_and_release_locks_are_strict(self):
        repo = Path(__file__).resolve().parents[1]
        self.assertEqual(len(read_visual_lock(repo)["assets"]), 20)
        release = read_release_lock(repo)
        self.assertTrue(release["source_sha"].startswith(release["tag"].removeprefix("sha-")))
        self.assertEqual(sum(part["size"] for part in release["parts"]),
                         release["archive"]["size"])

    def test_visual_download_is_hash_verified_and_atomic(self):
        _lock, payloads = self._visual_lock()

        def response(request, timeout):
            path = request.full_url.split("/" + "1" * 40 + "/", 1)[1]
            return Reply(payloads[path])

        with patch("scripts.windows.runtime_visual_assets.urllib.request.urlopen",
                   side_effect=response) as fetch:
            self.assertEqual(provision(self.root, lock_root=self.root, download=True), 20)
            self.assertEqual(fetch.call_count, 20)
        self.assertEqual(provision(self.root, lock_root=self.root, download=False), 20)

    def test_visual_download_rejects_unpinned_bytes(self):
        self._visual_lock()
        with patch("scripts.windows.runtime_visual_assets.urllib.request.urlopen",
                   return_value=Reply(b"wrong")):
            with self.assertRaises(ValueError):
                provision(self.root, lock_root=self.root, download=True)
        self.assertFalse((self.root / "data/images/classes/cra.png").exists())


class CertifiedReleaseHydrationTests(unittest.TestCase):
    def test_release_part_resumes_only_from_exact_content_range(self):
        payload = b"0123456789"

        class PartialReply(Reply):
            status = 206

            def __init__(self, data: bytes, start: int):
                super().__init__(data)
                self.headers = {"Content-Range": f"bytes {start}-{len(payload) - 1}/{len(payload)}"}

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "part.download"
            target.write_bytes(payload[:4])

            def response(request, timeout):
                self.assertEqual(request.get_header("Range"), "bytes=4-")
                self.assertEqual(timeout, 120)
                return PartialReply(payload[4:], 4)

            with patch("scripts.windows.release_lfs_assets.urllib.request.urlopen",
                       side_effect=response) as fetch:
                digest = _download_part(
                    "https://example.invalid/part",
                    target,
                    expected_size=len(payload),
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                )
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
            self.assertEqual(target.read_bytes(), payload)

    def test_release_archive_must_match_candidate_pointer_before_activation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            relative = "data/images/example.png"
            payload = b"real reviewed image"
            digest = hashlib.sha256(payload).hexdigest()
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_text(
                "version https://git-lfs.github.com/spec/v1\n"
                f"oid sha256:{digest}\nsize {len(payload)}\n",
                encoding="ascii",
            )
            archive_stream = io.BytesIO()
            with zipfile.ZipFile(archive_stream, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr(f"AtlasApp/_internal/{relative}", payload)
            archive = archive_stream.getvalue()
            split = len(archive) // 2
            parts = [archive[:split], archive[split:]]
            manifest = json.dumps({
                "source_sha": "a" * 40,
                "archive_size": len(archive),
                "archive_sha256": hashlib.sha256(archive).hexdigest(),
                "files": [{"path": f"AtlasApp/_internal/{relative}",
                           "size": len(payload), "sha256": digest}],
            }, separators=(",", ":")).encode()
            lock = {
                "source_repo": "r9327/Dof-Atlas-App", "tag": "sha-test",
                "source_sha": "a" * 40,
                "manifest": {"name": "atlas-manifest.json", "size": len(manifest),
                             "sha256": hashlib.sha256(manifest).hexdigest()},
                "archive": {"size": len(archive), "sha256": hashlib.sha256(archive).hexdigest()},
                "parts": [
                    {"name": f"atlas-windows.part000{index + 1}", "size": len(data),
                     "sha256": hashlib.sha256(data).hexdigest()}
                    for index, data in enumerate(parts)
                ],
            }

            def response(request, timeout):
                if request.full_url.endswith("atlas-manifest.json"):
                    return Reply(manifest)
                for info, data in zip(lock["parts"], parts):
                    if request.full_url.endswith(info["name"]):
                        return Reply(data)
                raise AssertionError(request.full_url)

            with (patch("scripts.windows.release_lfs_assets.read_lock", return_value=lock),
                  patch("scripts.windows.release_lfs_assets.pointer_inventory",
                        return_value={relative: (digest, len(payload))}),
                  patch("scripts.windows.release_lfs_assets.urllib.request.urlopen",
                        side_effect=response)):
                self.assertEqual(hydrate(root, lock_root=root, work_dir=root / "work"), 1)
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(list((root / "work").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
