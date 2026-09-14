from __future__ import annotations

import ast
import unittest
from pathlib import Path

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
