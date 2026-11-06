from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.organizer_mirror_log_report import main, summarize


class OrganizerMirrorLogReportTests(unittest.TestCase):
    def test_real_sender_log_families_are_kept_separate_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                lines = [
                    f"Miroir blocage_souris_ms=25.00 cibles={count}",
                    f"Miroir blocage_souris_ms=35.00 cibles={count}",
                    f"Miroir molette blocage_souris_ms=40.00 cibles={count}",
                    "Miroir clic dispatch_to_worker_ms=5.00 dispatch_to_last_emit_ms=90.00 (envoi, pas rendu Unity)",
                    f"Miroir key: envoyés={count}/{count} worker_total_ms=70.00 delivery_step_ms=None focus_activation_ms=None",
                    f"Miroir wheel: envoyés={count}/{count} worker_total_ms=95.00 delivery_step_ms=None focus_activation_ms=None",
                    f"Miroir : {count}/{count} fenêtres.",
                    f"Miroir Clavier : {count}/{count} fenêtres.",
                    f"Miroir Molette : {count}/{count} fenêtres.",
                ]
                summary = summarize(lines, count)
                self.assertEqual(summary["actions"]["complete"], 3)
                self.assertEqual(summary["evidence"], "LOG_ONLY_NOT_UNITY_CERTIFIED")
                self.assertEqual(summary["metrics"]["click_pointer_block_ms"], {
                    "n": 2, "p50_ms": 25.0, "p95_ms": 35.0, "p99_ms": 35.0,
                })
                self.assertEqual(summary["metrics"]["key_worker_ms"]["p99_ms"], 70.0)
                self.assertEqual(summary["metrics"]["wheel_worker_ms"]["p99_ms"], 95.0)
                self.assertEqual(summary["unity_render_latency"], "NOT_MEASURED")

    def test_counts_restarts_no_replay_and_rejects_foreign_rosters(self):
        lines = [
            "Organizer entrées physiques bloquées: clics=2 molettes=1",
            "Organizer entrées physiques bloquées: clics=4 molettes=1",
            "Organizer hooks arrêtés: clics bloqués=4 molettes bloquées=2",
            "Organizer entrées physiques bloquées: clics=1 molettes=3",
            "Miroir interrompu : 1/4 fenêtres (geste physique non rejoué).",
            "Miroir Clavier incomplet : 0/4 fenêtres.",
            "Miroir : 2/8 fenêtres.",
            "Miroir blocage_souris_ms=15.0 cibles=8",
            "Miroir clic dispatch_to_worker_ms=3.0 dispatch_to_last_emit_ms=NOT_MEASURED",
        ]
        s = summarize(lines, 4)
        self.assertEqual(s["observed_blocked_physical_inputs"], {"clicks": 5, "wheel_ticks": 5})
        self.assertEqual(s["non_replayed_statuses"], 1)
        self.assertEqual(s["actions"], {"complete": 0, "partial": 1, "interrupted": 1})
        self.assertEqual(s["roster_mismatch_lines"], 2)
        self.assertIsNone(s["metrics"]["click_pointer_block_ms"])
        self.assertIsNone(s["metrics"]["click_dispatch_to_last_emit_ms"])

    def test_streaming_input_is_consumed_once_without_materializing_list(self):
        count = 0

        def lines():
            nonlocal count
            for n in range(500):
                count += 1
                yield "Miroir blocage_souris_ms=1.0 cibles=8"

        result = summarize(lines(), 8)
        self.assertEqual(count, 500)
        self.assertEqual(result["metrics"]["click_pointer_block_ms"]["n"], 500)

    def test_cli_emits_aggregates_without_exposing_raw_window_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "atlas.log"
            file.write_text("Miroir Clavier : 2/2 fenêtres. hwnd=991 x=123 y=456\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(main(["--logs", str(file), "--accounts", "2"]), 0)
            output = stdout.getvalue()
            parsed = json.loads(output)
            self.assertEqual(parsed["actions"]["complete"], 1)
            self.assertNotIn("hwnd", output)
            self.assertNotIn("991", output)
            self.assertEqual(parsed["cpu_ram"], "NOT_MEASURED")


if __name__ == "__main__":
    unittest.main()
