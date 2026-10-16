from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import startup_cache_warmup as warmup


class StartupWorkerSubprocessFlagsTests(unittest.TestCase):
    def test_cold_warmup_wait_requires_real_sampler_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            go_file = Path(temp_dir) / "memory-sampler.ready"
            with self.assertRaisesRegex(TimeoutError, "sampler"):
                warmup._wait_for_memory_sampler(str(go_file), timeout=0.0)
            go_file.touch()
            warmup._wait_for_memory_sampler(str(go_file), timeout=0.0)

    def test_windows_worker_does_not_create_a_hidden_console(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")
        with (
            patch.object(warmup.os, "name", "nt"),
            patch.object(warmup.subprocess, "DETACHED_PROCESS", 0x00000008, create=True),
            patch.object(warmup.subprocess, "run", return_value=completed) as run,
        ):
            self.assertEqual(warmup._run_module("fake.worker", "--example"), '{"ok":true}')
        command, = run.call_args.args
        self.assertEqual(command[1:], ["-m", "fake.worker", "--example"])
        options = run.call_args.kwargs
        self.assertEqual(options["creationflags"], 0x00000008)
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(options["stdout"], subprocess.PIPE)
        self.assertEqual(options["stderr"], subprocess.PIPE)
        self.assertEqual(options["timeout"], 180)

    def test_non_windows_worker_keeps_standard_child_flags(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="done", stderr="")
        with (
            patch.object(warmup.os, "name", "posix"),
            patch.object(warmup.subprocess, "run", return_value=completed) as run,
        ):
            self.assertEqual(warmup._run_module("fake.worker"), "done")
        self.assertNotIn("creationflags", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
