from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import startup_cache_warmup as warmup


class StartupWorkerSubprocessFlagsTests(unittest.TestCase):

    def test_domain_progress_is_atomic_and_quest_is_published_first(self) -> None:
        order = []
        publications = []
        payloads = {
            "quest": {"quest_count": 1976},
            "guide": {"tasks": {"guide": {"ok": True}, "guide_items": {"ok": True}}},
            "success": {"tasks": {"success": {"ok": True}, "success_names": {"ok": True}}},
        }

        def fake_domain(name, _manifest):
            order.append(name)
            return payloads[name], "reused", 1.0

        with (
            patch.object(warmup, "_write_result", side_effect=lambda payload: publications.append(dict(payload))),
            patch.object(warmup, "_load_manifest", return_value={}),
            patch.object(warmup, "_run_or_reuse_domain", side_effect=fake_domain),
            patch.dict(warmup.os.environ, {"DOFUS_ATLAS_WARMUP_GO_FILE": ""}),
        ):
            final = warmup.run_warmup("exact-session")

        self.assertEqual(order, ["quest", "guide", "success"])
        self.assertEqual(publications[0]["status"], "running")
        self.assertEqual(publications[1]["completed_domains"], ["quest"])
        self.assertEqual(publications[1]["quest_count"], 1976)
        self.assertFalse(publications[1]["encyclopedia_ready"])
        self.assertEqual(publications[-1]["completed_domains"], ["quest", "guide", "success"])
        self.assertTrue(publications[-1]["encyclopedia_ready"])
        self.assertEqual(final["status"], "ready")
        self.assertEqual(final["completed_domains"], order)

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
