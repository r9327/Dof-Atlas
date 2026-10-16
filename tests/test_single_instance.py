from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.windows.single_instance import ATLAS_MUTEX_NAME, SingleInstanceGuard


ROOT = Path(__file__).resolve().parents[1]


class _FakeMutexBackend:
    def __init__(self, *, already_exists: bool = False) -> None:
        self.already_exists = already_exists
        self.created: list[str] = []
        self.closed: list[int] = []

    def create(self, name: str) -> tuple[int, bool]:
        self.created.append(name)
        return 42, self.already_exists

    def close(self, handle: int) -> None:
        self.closed.append(handle)


class SingleInstanceTests(unittest.TestCase):
    def test_platform_probe_and_real_windows_mutex_across_two_processes(self) -> None:
        name = "Local\\DofusAtlas.Audit." + uuid4().hex
        if os.name != "nt":
            # Check the portability contract, but explicitly do not report this
            # as native Windows evidence in a Linux/local run.
            with patch("app.windows.single_instance._WindowsMutexBackend",
                       side_effect=AssertionError("Win32 must not run on this platform")):
                guard = SingleInstanceGuard(name)
                self.assertTrue(guard.acquire())
                self.assertIsNone(guard._handle)
                guard.release()
            print('PC03_NATIVE {"status":"BLOCKED","reason":"Windows required"}', flush=True)
            return
        child = (
            "import json,sys; from app.windows.single_instance import SingleInstanceGuard; "
            "g=SingleInstanceGuard(sys.argv[1]); acquired=g.acquire(); "
            "print(json.dumps({'acquired':acquired}),flush=True); g.release()"
        )
        guard = SingleInstanceGuard(name)
        self.assertTrue(guard.acquire())
        processes = []
        try:
            for _ in range(2):
                processes.append(subprocess.Popen(
                    [sys.executable, "-c", child, name], cwd=ROOT, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                ))
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertFalse(json.loads(stdout)["acquired"])
        finally:
            guard.release()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)
        after = subprocess.run([sys.executable, "-c", child, name], cwd=ROOT,
                               text=True, capture_output=True, timeout=20, check=True)
        self.assertTrue(json.loads(after.stdout)["acquired"])
        print('PC03_NATIVE {"status":"PASS","second_processes_rejected":2,"reacquired_after_release":true}',
              flush=True)

    def test_first_instance_owns_mutex_until_release(self) -> None:
        backend = _FakeMutexBackend()
        guard = SingleInstanceGuard(backend=backend)

        self.assertTrue(guard.acquire())
        self.assertTrue(guard.acquire())
        self.assertEqual(backend.created, [ATLAS_MUTEX_NAME])
        self.assertEqual(backend.closed, [])

        guard.release()
        guard.release()
        self.assertEqual(backend.closed, [42])

    def test_existing_mutex_rejects_second_instance_and_closes_probe_handle(self) -> None:
        backend = _FakeMutexBackend(already_exists=True)
        guard = SingleInstanceGuard(backend=backend)

        self.assertFalse(guard.acquire())
        self.assertEqual(backend.created, [ATLAS_MUTEX_NAME])
        self.assertEqual(backend.closed, [42])

    def test_main_acquires_guard_before_qapplication_and_releases_in_finally(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        main_function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        segment = ast.get_source_segment(source, main_function) or ""

        self.assertLess(segment.index("guard.acquire()"), segment.index("QApplication(sys.argv)"))
        self.assertIn("finally:", segment)
        self.assertIn("guard.release()", segment)


if __name__ == "__main__":
    unittest.main()
