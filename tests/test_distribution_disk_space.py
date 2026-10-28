"""Release download budget and multipart resume disk-space contracts."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution.disk_space import ensure_space, ensure_delta_space, remaining_space_needed
from app.distribution.manifest import parse_manifest, DeltaManifest
from dataclasses import replace
from app.distribution.release_client import UpdateError


class FirstInstallSpaceTests(unittest.TestCase):
    def make_manifest(self):
        entries = [b"abc", b"defgh"]
        return parse_manifest(json.dumps({
            "protocol_version": 1, "app_version": "1", "data_version": "1",
            "schema_version": 1, "source_sha": "a" * 40,
            "entrypoint": "AtlasApp/AtlasApp.exe",
            "files": [{"path": "AtlasApp/AtlasApp.exe",
                       "size": 16, "sha256": "a" * 64}],
            "archive_parts": [
                {"name": f"atlas-windows.part{i:04d}", "size": len(data),
                 "sha256": hashlib.sha256(data).hexdigest()}
                for i, data in enumerate(entries, 1)],
            "archive_size": 8,
            "archive_sha256": hashlib.sha256(b"abcdefgh").hexdigest(),
        }).encode())

    def test_new_install_budgets_two_archives_plus_extracted_files(self):
        with tempfile.TemporaryDirectory() as d:
            m = self.make_manifest()
            self.assertEqual(remaining_space_needed(m, Path(d), reserve_bytes=0), 32)

    def test_partial_cache_reduces_space_budget(self):
        with tempfile.TemporaryDirectory() as d:
            m = self.make_manifest()
            cache = Path(d) / ("a" * 20 + "-parts")
            cache.mkdir()
            (cache / "atlas-windows.part0001.download").write_bytes(b"ab")
            self.assertEqual(remaining_space_needed(m, Path(d), reserve_bytes=0), 30)
            (cache / "atlas-windows.part0001.download").unlink()
            (cache / "atlas-windows.part0001").write_bytes(b"abc")
            self.assertEqual(remaining_space_needed(m, Path(d), reserve_bytes=0), 29)

    def test_insufficient_disk_is_actionable_before_download(self):
        with tempfile.TemporaryDirectory() as d:
            m = self.make_manifest()
            with patch("app.distribution.disk_space.shutil.disk_usage",
                       return_value=type("Usage", (), {"free": 10})()):
                with self.assertRaisesRegex(UpdateError, "Espace disque insuffisant"):
                    ensure_space(m, Path(d), reserve_bytes=0)

    def test_delta_preflight_budgets_staging_and_archive_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            m = self.make_manifest()
            m = replace(m, delta=DeltaManifest(
                base_source_sha="b" * 40,
                archive_sha256="c" * 64,
                archive_size=80,
                paths=("AtlasApp/AtlasApp.exe",),
            ))
            with patch("app.distribution.disk_space.shutil.disk_usage",
                       return_value=type("Usage", (), {"free": 95})()):
                with self.assertRaisesRegex(UpdateError, "differentielle"):
                    ensure_delta_space(m, Path(d), reserve_bytes=0)
            with patch("app.distribution.disk_space.shutil.disk_usage",
                       return_value=type("Usage", (), {"free": 96})()):
                ensure_delta_space(m, Path(d), reserve_bytes=0)

    def test_adequate_disk_passes_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("app.distribution.disk_space.shutil.disk_usage",
                       return_value=type("Usage", (), {"free": 1000})()):
                ensure_space(self.make_manifest(), Path(d), reserve_bytes=0)


if __name__ == "__main__":
    unittest.main()
