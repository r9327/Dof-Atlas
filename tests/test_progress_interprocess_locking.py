from __future__ import annotations

import multiprocessing
import tempfile
import unittest
from pathlib import Path

from app.core.progress_coordinator import (
    InterProcessResourceLock,
    ProgressLockTimeoutError,
    coordinator_for,
)
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.quest_catalog import load_quest_progress, save_quest_progress


def _hold_stale_quest_snapshot(
    raw_path: str,
    quest_id: int,
    ready,
    allow_commit,
) -> None:
    path = Path(raw_path)
    coordinator = coordinator_for(path)
    with coordinator.lock:
        payload = load_quest_progress(path)
        ready.set()
        if not allow_commit.wait(10):
            raise TimeoutError("test controller never released the first writer")
        character = payload.setdefault("characters", {}).setdefault("character:1", {})
        character.setdefault("done", {})[str(quest_id)] = True
        save_quest_progress(payload, path)


def _mutate_quest(raw_path: str, quest_id: int, started, finished) -> None:
    started.set()
    QuestProgressService(Path(raw_path)).set_quest_completed("character:1", quest_id, True)
    finished.set()


def _hold_resource_lock(raw_path: str, ready, release) -> None:
    with InterProcessResourceLock(Path(raw_path), timeout=5):
        ready.set()
        if not release.wait(10):
            raise TimeoutError("test controller never released the resource lock")


class ProgressInterprocessLockingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.context = multiprocessing.get_context("spawn")

    def test_two_processes_preserve_both_mutations_after_stale_read(self) -> None:
        for first_id, second_id in ((101, 202), (202, 101)):
            with self.subTest(first_id=first_id), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "quest_progress.json"
                ready = self.context.Event()
                allow_commit = self.context.Event()
                contender_started = self.context.Event()
                contender_finished = self.context.Event()
                first = self.context.Process(
                    target=_hold_stale_quest_snapshot,
                    args=(str(path), first_id, ready, allow_commit),
                )
                second = self.context.Process(
                    target=_mutate_quest,
                    args=(str(path), second_id, contender_started, contender_finished),
                )

                first.start()
                self.assertTrue(ready.wait(10))
                second.start()
                self.assertTrue(contender_started.wait(10))
                self.assertFalse(
                    contender_finished.wait(0.5),
                    "the second process entered the transaction before the first released it",
                )
                allow_commit.set()
                first.join(10)
                second.join(10)

                self.assertEqual(first.exitcode, 0)
                self.assertEqual(second.exitcode, 0)
                self.assertEqual(
                    QuestProgressService(path).completed_quest_ids("character:1"),
                    {101, 202},
                )

    def test_lock_timeout_is_explicit_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quest_progress.json"
            ready = self.context.Event()
            release = self.context.Event()
            holder = self.context.Process(
                target=_hold_resource_lock,
                args=(str(path), ready, release),
            )
            holder.start()
            self.assertTrue(ready.wait(10))
            try:
                with self.assertRaisesRegex(ProgressLockTimeoutError, "remained locked"):
                    InterProcessResourceLock(path, timeout=0.2).acquire()
            finally:
                release.set()
                holder.join(10)
            self.assertEqual(holder.exitcode, 0)

    def test_crashed_holder_does_not_leave_a_dead_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quest_progress.json"
            ready = self.context.Event()
            release = self.context.Event()
            holder = self.context.Process(
                target=_hold_resource_lock,
                args=(str(path), ready, release),
            )
            holder.start()
            self.assertTrue(ready.wait(10))
            holder.terminate()
            holder.join(10)
            self.assertFalse(holder.is_alive())

            lock = InterProcessResourceLock(path, timeout=2)
            with lock:
                self.assertTrue(lock.lock_path.exists())

    def test_different_resources_do_not_block_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            held_path = Path(tmp) / "quests.json"
            independent_path = Path(tmp) / "achievements.json"
            ready = self.context.Event()
            release = self.context.Event()
            holder = self.context.Process(
                target=_hold_resource_lock,
                args=(str(held_path), ready, release),
            )
            holder.start()
            self.assertTrue(ready.wait(10))
            try:
                with InterProcessResourceLock(independent_path, timeout=0.2):
                    pass
            finally:
                release.set()
                holder.join(10)
            self.assertEqual(holder.exitcode, 0)


if __name__ == "__main__":
    unittest.main()
