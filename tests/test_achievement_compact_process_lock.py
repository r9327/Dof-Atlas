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

from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
    _achievement_compact_write_lock,
)


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
