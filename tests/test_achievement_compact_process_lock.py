"""Prove the real OS cache lock serializes independent Atlas workers.

No mocked lock and no business-data mutation: all writes stay in a temporary
test directory. This also validates Windows byte-range locking specifically.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app.modules.encyclopedia.services.achievement_index_warmup import (
    _replace_name_index_with_windows_retry,
)

from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
    _achievement_compact_write_lock,
)


class AchievementNameIndexWindowsSharingTests(unittest.TestCase):
    def test_transient_windows_share_violation_retries_and_replaces(self):
        with tempfile.TemporaryDirectory(prefix="atlas-success-names-") as directory:
            root = Path(directory)
            temporary, target = root / "new.json", root / "names.json"
            temporary.write_text('{"1": "Success"}', encoding="utf-8")
            original_replace = Path.replace
            attempts = []

            def simulated_replace(self, destination):
                attempts.append(self)
                if len(attempts) < 3:
                    error = PermissionError(13, "Windows sharing violation")
                    error.winerror = 32
                    raise error
                return original_replace(self, destination)

            with patch.object(Path, "replace", simulated_replace), patch(
                "app.modules.encyclopedia.services.achievement_index_warmup.sleep"
            ) as pause:
                _replace_name_index_with_windows_retry(temporary, target, windows=True)
            self.assertEqual(len(attempts), 3)
            self.assertEqual(pause.call_count, 2)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"1": "Success"}')
            self.assertFalse(temporary.exists())

    def test_persistent_share_violation_is_not_waived(self):
        with tempfile.TemporaryDirectory(prefix="atlas-success-names-") as directory:
            root = Path(directory)
            temporary, target = root / "new.json", root / "names.json"
            temporary.write_text("value", encoding="utf-8")
            error = PermissionError(13, "Windows sharing violation")
            error.winerror = 32
            with patch.object(Path, "replace", side_effect=error) as replace, patch(
                "app.modules.encyclopedia.services.achievement_index_warmup.sleep"
            ):
                with self.assertRaises(PermissionError):
                    _replace_name_index_with_windows_retry(temporary, target, windows=True)
            self.assertEqual(replace.call_count, 10)
            self.assertFalse(target.exists())

    def test_non_sharing_permission_error_is_not_retried(self):
        with tempfile.TemporaryDirectory(prefix="atlas-success-names-") as directory:
            root = Path(directory)
            temporary, target = root / "new.json", root / "names.json"
            temporary.write_text("value", encoding="utf-8")
            with patch.object(Path, "replace", side_effect=PermissionError(13, "denied")) as replace:
                with self.assertRaises(PermissionError):
                    _replace_name_index_with_windows_retry(temporary, target, windows=True)
            self.assertEqual(replace.call_count, 1)


class SharedSuccessCacheLockTests(unittest.TestCase):
    def test_lock_is_released_when_owner_raises(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-success-lock-") as directory:
            cache = Path(directory) / "catalog.jsonl"
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                with _achievement_compact_write_lock(cache):
                    raise RuntimeError("synthetic")
            with _achievement_compact_write_lock(cache, timeout_seconds=1):
                self.assertTrue(cache.with_suffix(".jsonl.lock").is_file())

    def test_three_independent_workers_never_overlap(self) -> None:
        with tempfile.TemporaryDirectory(prefix="atlas-success-lock-") as directory:
            root = Path(directory)
            trace = root / "trace.txt"
            cache = root / "catalog.jsonl"
            worker = r"""
import sys, time
from pathlib import Path
from app.modules.encyclopedia.providers.memory_bound_achievement_provider import _achievement_compact_write_lock
root, ident = Path(sys.argv[1]), sys.argv[2]
(root / ('ready_' + ident)).write_text('1', encoding='utf-8')
deadline = time.monotonic() + 10
while len(list(root.glob('ready_*'))) < 3:
    if time.monotonic() > deadline:
        raise SystemExit('start barrier timeout')
    time.sleep(0.01)
with _achievement_compact_write_lock(root / 'catalog.jsonl', timeout_seconds=10):
    with (root / 'trace.txt').open('a', encoding='utf-8') as out:
        out.write('enter:' + ident + chr(10))
    time.sleep(0.2)
    with (root / 'trace.txt').open('a', encoding='utf-8') as out:
        out.write('exit:' + ident + chr(10))
"""
            processes = []
            try:
                for number in range(3):
                    processes.append(subprocess.Popen(
                        [sys.executable, "-c", worker, str(root), str(number)],
                        cwd=Path(__file__).resolve().parents[1],
                        env={**os.environ, "PYTHONUTF8": "1"},
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True,
                    ))
                for proc in processes:
                    try:
                        out, err = proc.communicate(timeout=25)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate(timeout=5)
                        self.fail("Deadlock in cross-process achievement cache lock")
                    self.assertEqual(proc.returncode, 0, err or out)
                events = trace.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(events), 6, events)
                for i in range(0, 6, 2):
                    self.assertTrue(events[i].startswith("enter:"), events)
                    self.assertEqual(events[i + 1],
                                     "exit:" + events[i].partition(":")[2], events)
                self.assertEqual(len({row for row in events if row.startswith("enter:")}), 3)
            finally:
                for proc in processes:
                    if proc.poll() is None:
                        proc.kill()
                        proc.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
