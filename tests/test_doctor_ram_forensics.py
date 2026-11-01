"""RAM profiler is diagnostic only, bounded and never a fake Qt-native heap estimate."""
from __future__ import annotations

import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.ram_forensics import RamForensics, private_windows_memory


class DoctorRamForensicsTests(unittest.TestCase):
    def test_python_allocation_is_traced_without_claiming_qt_heap(self):
        self.assertFalse(tracemalloc.is_tracing())
        probe = RamForensics(Path(__file__).resolve().parents[1], max_checkpoints=3)
        scratch = []
        with patch(
            "tools.atlas_doctor_lib.ram_forensics.private_windows_memory",
            return_value={"status": "UNAVAILABLE", "reason": "TEST"},
        ):
            probe.start()
            try:
                probe.capture("initial_home")
                scratch.append(bytearray(1_000_000))
                probe.capture("guide_active")
                probe.capture("last_home")
                probe.capture("ignored_over_limit")
            finally:
                result = probe.finish()
        self.assertFalse(tracemalloc.is_tracing())
        self.assertEqual(result["status"], "PARTIAL_PYTHON_ONLY")
        self.assertEqual(len(result["checkpoints"]), 3)
        self.assertEqual(result["checkpoints"][1]["label"], "guide_active")
        self.assertGreater(
            result["checkpoints"][1]["tracked_python_heap_mib"],
            result["checkpoints"][0]["tracked_python_heap_mib"] + 0.5,
        )
        self.assertTrue(
            any(
                row["source"] == "tests/test_doctor_ram_forensics.py"
                and row["delta_mib"] > 0.5
                for row in result["checkpoints"][1]["top_increased_sources_since_previous_checkpoint"]
            )
        )
        self.assertTrue(any("Qt/C++ native" in limit for limit in result["limits"]))
        self.assertTrue(any(
            row["source"] == "tests/test_doctor_ram_forensics.py"
            for row in result["checkpoints"][1]["top_traced_lines_now"]
        ))
        self.assertIn("benchmark_top_sources_traced_mib", result["checkpoints"][1])

    def test_single_frame_retention_and_negative_allocation_deltas(self):
        probe = RamForensics(Path(__file__).resolve().parents[1], max_checkpoints=3)
        retained = []
        with patch(
            "tools.atlas_doctor_lib.ram_forensics.private_windows_memory",
            return_value={"status": "UNAVAILABLE", "reason": "TEST"},
        ):
            probe.start()
            try:
                self.assertEqual(tracemalloc.get_traceback_limit(), 1)
                probe.capture("baseline")
                retained.append(bytearray(800_000))
                probe.capture("allocated")
                retained.clear()
                probe.capture("released")
            finally:
                result = probe.finish()
        self.assertEqual(result["status"], "PARTIAL_PYTHON_ONLY")
        self.assertEqual(len(result["checkpoints"]), 3)
        self.assertIsInstance(probe._previous, dict)
        source = "tests/test_doctor_ram_forensics.py"
        increased = result["checkpoints"][1]["top_increased_sources_since_previous_checkpoint"]
        decreased = result["checkpoints"][2]["top_decreased_sources_since_previous_checkpoint"]
        self.assertTrue(any(row["source"] == source and row["delta_mib"] > 0.5
                            for row in increased))
        self.assertTrue(any(row["source"] == source and row["delta_mib"] < -0.5
                            for row in decreased))
        self.assertFalse(tracemalloc.is_tracing())
        self.assertFalse(any(row["delta_mib"] < 0 for row in increased))
        self.assertFalse(any(row["delta_mib"] > 0 for row in decreased))

    def test_invalid_existing_tracing_is_not_silently_reused(self):
        tracemalloc.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "TRACEMALLOC_ALREADY_ACTIVE"):
                RamForensics(Path(__file__).resolve().parents[1]).start()
        finally:
            tracemalloc.stop()

    def test_unavailable_process_private_bytes_is_explicit(self):
        if __import__("os").name != "nt":
            self.assertEqual(private_windows_memory()["status"], "UNAVAILABLE")

    def test_finish_without_start_does_not_stop_external_tracemalloc(self):
        probe = RamForensics(Path(__file__).resolve().parents[1])
        self.assertFalse(tracemalloc.is_tracing())
        tracemalloc.start()
        try:
            result = probe.finish()
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(tracemalloc.is_tracing())
        finally:
            tracemalloc.stop()

    def test_no_checkpoint_is_blocked_not_false_pass(self):
        self.assertEqual(
            RamForensics(Path(__file__).resolve().parents[1]).finish()["status"],
            "BLOCKED",
        )


if __name__ == "__main__":
    unittest.main()
