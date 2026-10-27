"""Smart installer: verified local reuse, ReFS CoW isolation and parallel transfers.

All tests use synthetic files: no network, no frozen Atlas binaries.
"""
from __future__ import annotations

import hashlib
import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution import install, release_client
from app.distribution.install import (
    _copy_unchanged_verified, install_release, mark_healthy, read_state,
    rollback_pending, slot_path,
)
from app.distribution.manifest import ReleaseFile, parse_manifest
from app.distribution.release_client import RemoteRelease, UpdateError, download_archive
from scripts.windows.package_release import package_release

class Response(io.BytesIO):
    def __init__(self, payload: bytes, status: int = 200, headers=None):
        super().__init__(payload)
        self.status = status
        self.headers = headers or {}


def multipart_fixture(root: Path):
    app = root / "frozen"
    app.mkdir()
    (app / "AtlasApp.exe").write_bytes(b"MZ" + bytes(range(256)) * 8)
    with (
        patch("scripts.windows.package_release._MAX_GITHUB_RELEASE_ASSET_BYTES", 120),
        patch("scripts.windows.package_release._CHUNK_BYTES", 90),
    ):
        archive, metadata = package_release(
            app, root / "release", "a" * 40, "1.0", "2026.10", 1
        )
    manifest = parse_manifest(metadata.read_bytes())
    prefix = "https://github.com/r9327/Dof-Atlas-App/releases/download/v1/"
    remote = RemoteRelease(
        "v1", "", manifest.archive_size, manifest,
        part_urls=tuple(prefix + part.name for part in manifest.archive_parts),
    )
    return archive, manifest, remote



class ReuseInstallerTests(unittest.TestCase):
    def _package(self, root: Path, sha: str, version: str, *, change: bytes):
        app = root / "frozen"
        app.mkdir(exist_ok=True)
        (app / "AtlasApp.exe").write_bytes(b"MZ-unchanged-release-entrypoint")
        (app / "same.dat").write_bytes(b"unchanged immutable reference bytes" * 100)
        (app / "changed.dat").write_bytes(change)
        archive, manifest_path = package_release(
            app, root / version, sha, version, "2026.10", 1,
        )
        return archive, parse_manifest(manifest_path.read_bytes())

    def test_full_update_reuses_verified_file_and_preserves_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first, original = self._package(root, "a" * 40, "v1", change=b"old")
            target = root / "runtime"
            self.assertTrue(install_release(target, first, original))
            mark_healthy(target)
            old_slot = read_state(target)["active"]
            second, newer = self._package(root, "b" * 40, "v2", change=b"new")
            reused: list[str] = []
            original_copy = install._copy_unchanged_verified

            def tracked(source, destination, entry, progress=None):
                reused.append(entry.path)
                return original_copy(source, destination, entry, progress)

            with patch.object(install, "_copy_unchanged_verified", side_effect=tracked):
                self.assertTrue(install_release(target, second, newer))
            self.assertIn("AtlasApp/same.dat", reused)
            self.assertIn("AtlasApp/AtlasApp.exe", reused)
            self.assertNotIn("AtlasApp/changed.dat", reused)  # no wasted copy
            latest_slot = slot_path(target, read_state(target)["active"])
            self.assertEqual((latest_slot / "AtlasApp/changed.dat").read_bytes(), b"new")
            self.assertEqual(
                (slot_path(target, old_slot) / "AtlasApp/changed.dat").read_bytes(), b"old"
            )
            self.assertTrue(rollback_pending(target))
            self.assertEqual(read_state(target)["active"], old_slot)

    def test_legacy_slot_without_index_avoids_speculative_full_copies(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first, original = self._package(root, "a" * 40, "v1", change=b"old")
            target = root / "runtime"
            install_release(target, first, original)
            mark_healthy(target)
            old_slot = slot_path(target, read_state(target)["active"])
            (old_slot / ".atlas-file-index.json").unlink()
            second, newer = self._package(root, "b" * 40, "v2", change=b"new")
            with patch.object(
                install, "_copy_unchanged_verified",
                side_effect=AssertionError("legacy metadata must not trigger trial copies"),
            ):
                self.assertTrue(install_release(target, second, newer))

    def test_corrupted_reusable_file_falls_back_to_full_zip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first, original = self._package(root, "a" * 40, "v1", change=b"old")
            target = root / "runtime"
            install_release(target, first, original)
            mark_healthy(target)
            old_file = slot_path(target, read_state(target)["active"]) / "AtlasApp/same.dat"
            old_file.write_bytes(b"local damage")
            second, newer = self._package(root, "b" * 40, "v2", change=b"new")
            self.assertTrue(install_release(target, second, newer))
            current = slot_path(target, read_state(target)["active"]) / "AtlasApp/same.dat"
            self.assertEqual(current.read_bytes(), b"unchanged immutable reference bytes" * 100)

    def test_clone_result_is_rehashed_and_old_file_remains_independent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old, copied = root / "source.bin", root / "target.bin"
            old.write_bytes(b"immutable" * 300)
            entry = ReleaseFile("dummy", old.stat().st_size, hashlib.sha256(old.read_bytes()).hexdigest())

            def fake_cow(source, destination, size):
                self.assertEqual(size, entry.size)
                destination.write_bytes(source.read_bytes())  # emulate independent clone
                return True

            with patch.object(install, "clone_unchanged_cow", side_effect=fake_cow):
                _copy_unchanged_verified(old, copied, entry)
            old.write_bytes(b"changed after clone")
            self.assertEqual(copied.read_bytes(), b"immutable" * 300)

    def test_bad_clone_sha_never_becomes_installed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src, dest = root / "src", root / "dst"
            src.write_bytes(b"good")
            entry = ReleaseFile("x", 4, hashlib.sha256(b"good").hexdigest())
            def corrupt_clone(source, destination, size):
                destination.write_bytes(b"evil")
                return True
            with patch.object(install, "clone_unchanged_cow", side_effect=corrupt_clone):
                with self.assertRaisesRegex(UpdateError, "Cloned base file"):
                    _copy_unchanged_verified(src, dest, entry)

    def test_nonwindows_clone_never_hardlinks_or_allocates(self):
        from app.distribution.file_clone import clone_unchanged_cow
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src, dst = root / "original", root / "cloned"
            src.write_bytes(b"source")
            with patch("app.distribution.file_clone.os.name", "posix"):
                self.assertFalse(clone_unchanged_cow(src, dst, 6))
            self.assertFalse(dst.exists())


class CleanupSafetyTests(unittest.TestCase):
    def test_keep_rollback_and_current_cache_remove_only_known_stale_files(self):
        from app.distribution.cleanup import cleanup_verified_runtime
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first, original = ReuseInstallerTests()._package(root, "a" * 40, "v1", change=b"old")
            runtime = root / "runtime"
            install_release(runtime, first, original)
            mark_healthy(runtime)
            first_slot = read_state(runtime)["active"]
            second, newer = ReuseInstallerTests()._package(root, "b" * 40, "v2", change=b"new")
            install_release(runtime, second, newer)
            self.assertEqual(cleanup_verified_runtime(runtime), (0, 0))  # pending
            mark_healthy(runtime)
            third, latest = ReuseInstallerTests()._package(root, "c" * 40, "v3", change=b"newer")
            install_release(runtime, third, latest)
            mark_healthy(runtime)
            state = read_state(runtime)
            self.assertEqual(state["previous"], "v2-" + "b" * 12)
            caches = runtime / "downloads"
            caches.mkdir()
            stale = caches / ("a" * 20 + ".zip")
            stale.write_bytes(b"stale")
            current = caches / ("c" * 20 + ".zip")
            current.write_bytes(b"repair cache")
            unrelated = caches / "personal.zip"
            unrelated.write_bytes(b"keep")
            old_slot = slot_path(runtime, first_slot)
            self.assertTrue(old_slot.is_dir())
            self.assertEqual(cleanup_verified_runtime(runtime), (1, 1))
            self.assertFalse(old_slot.exists())
            self.assertTrue(slot_path(runtime, state["previous"]).is_dir())
            self.assertTrue(slot_path(runtime, state["active"]).is_dir())
            self.assertFalse(stale.exists())
            self.assertEqual(current.read_bytes(), b"repair cache")
            self.assertEqual(unrelated.read_bytes(), b"keep")

    def test_cleanup_never_removes_unmarked_directories(self):
        from app.distribution.cleanup import cleanup_verified_runtime
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first, original = ReuseInstallerTests()._package(root, "a" * 40, "v1", change=b"old")
            runtime = root / "runtime"
            install_release(runtime, first, original)
            mark_healthy(runtime)
            custom = runtime / "versions" / "unknown-custom"
            custom.mkdir()
            (custom / "notes").write_text("mine")
            cleanup_verified_runtime(runtime)
            self.assertTrue((custom / "notes").is_file())


class ParallelTransferTests(unittest.TestCase):
    def test_parallel_multipart_is_bounded_and_sha_verified(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            archive, manifest, remote = multipart_fixture(root)
            payloads = {
                url: (archive.parent / part.name).read_bytes()
                for url, part in zip(remote.part_urls, manifest.archive_parts)
            }
            lock = threading.Lock()
            active = 0
            max_active = 0
            barrier = threading.Barrier(2, timeout=5)
            progress = []

            def serve(url, headers=None):
                nonlocal active, max_active
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                try:
                    barrier.wait() if url in remote.part_urls[:2] else None
                    return Response(payloads[url])
                finally:
                    with lock:
                        active -= 1

            with (
                patch.object(release_client, "_PARALLEL_MIN_BYTES", 0),
                patch.object(release_client, "_MAX_PARALLEL_PARTS", 2),
                patch.object(release_client, "_open", side_effect=serve),
            ):
                result = download_archive(remote, root / "cache", lambda n, total: progress.append(n))
            self.assertEqual(result.read_bytes(), archive.read_bytes())
            self.assertEqual(max_active, 2)
            self.assertEqual(progress[-1], manifest.archive_size)
            self.assertEqual(progress, sorted(progress))
            with patch.object(release_client, "_open", side_effect=AssertionError("network")):
                self.assertEqual(download_archive(remote, root / "cache"), result)

    def test_corrupted_parallel_part_does_not_create_full_archive(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            archive, manifest, remote = multipart_fixture(root)
            payloads = {
                url: (archive.parent / part.name).read_bytes()
                for url, part in zip(remote.part_urls, manifest.archive_parts)
            }
            payloads[remote.part_urls[0]] = b"X" * len(payloads[remote.part_urls[0]])
            with (
                patch.object(release_client, "_PARALLEL_MIN_BYTES", 0),
                patch.object(release_client, "_MAX_PARALLEL_PARTS", 2),
                patch.object(release_client, "_open", side_effect=lambda u, h=None: Response(payloads[u])),
            ):
                with self.assertRaises(UpdateError):
                    download_archive(remote, root / "cache")
            self.assertFalse((root / "cache" / ("a" * 20 + ".zip")).exists())


class FrozenCandidateWorkflowTests(unittest.TestCase):
    def test_windows_candidate_runs_only_for_exact_reviewed_pr_branch(self):
        workflow = (
            Path(__file__).resolve().parents[1] /
            ".github/workflows/atlas-windows-distribution.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "github.head_ref == 'feat/smart-download-safe-cow-install-20261027'",
            workflow,
        )
        self.assertIn("github.event.action == 'ready_for_review'", workflow)
        self.assertIn("atlas-windows-full-candidate-", workflow)
        self.assertIn("if: github.event_name == 'workflow_run'", workflow)
        self.assertIn("--repo r9327/Dof-Atlas-App", workflow)


if __name__ == "__main__":
    unittest.main()
