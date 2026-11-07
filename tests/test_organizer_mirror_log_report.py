from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.organizer_mirror_log_report import compare_reports, main, summarize


class OrganizerMirrorLogReportTests(unittest.TestCase):

    def test_click_worker_status_from_real_engine_logs_without_ui_callback(self):
        # SwitchClick logs these outcomes regardless of whether _emit_status
        # is persisted by the UI. A failed action must not disappear from
        # the latency comparison simply because there is no UI log entry.
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                result = summarize([
                    f"Miroir terminé: envoyés={accounts}/{accounts}",
                    f"Miroir partiel: envoyés=1/{accounts}",
                    f"Miroir interrompu: envoyés=0/{accounts}",
                    f"Miroir terminé: envoyés=1/{8 if accounts != 8 else 2}",
                ], accounts)
                self.assertEqual(result["actions"], {
                    "complete": 1, "partial": 1, "interrupted": 1,
                })
                self.assertEqual(result["roster_mismatch_lines"], 1)
                self.assertIn(
                    "PARTIAL_OR_INTERRUPTED_ACTIONS",
                    compare_reports({accounts: result})
                    ["ratio_exclusion_reasons"][str(accounts)],
                )

    def test_click_worker_fallback_is_not_hidden_by_key_or_wheel_ui(self):
        report = summarize([
            "Miroir Clavier : 4/4 fenêtres.",
            "Miroir Molette incomplet : 2/4 fenêtres.",
            "Miroir terminé: envoyés=4/4",
            "Miroir partiel: envoyés=1/4",
        ], 4)
        self.assertEqual(report["actions"], {
            "complete": 2, "partial": 2, "interrupted": 0,
        })
        self.assertIn(
            "PARTIAL_OR_INTERRUPTED_ACTIONS",
            compare_reports({4: report})["ratio_exclusion_reasons"]["4"],
        )

    def test_click_worker_and_ui_status_do_not_double_count(self):
        report = summarize([
            "Miroir terminé: envoyés=2/2",
            "Miroir : 2/2 fenêtres.",
        ], 2)
        self.assertEqual(report["actions"], {
            "complete": 1, "partial": 0, "interrupted": 0,
        })

    def test_partial_click_ui_logging_keeps_unlogged_worker_outcomes_2_to_8(self):
        # The UI logger may persist one result and omit later callbacks.
        # A single UI line must not hide a failed worker from the report.
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                result = summarize([
                    f"Miroir terminé: envoyés={accounts}/{accounts}",
                    f"Miroir partiel: envoyés=1/{accounts}",
                    f"Miroir interrompu: envoyés=0/{accounts}",
                    f"Miroir : {accounts}/{accounts} fenêtres.",
                ], accounts)
                self.assertEqual(result["actions"], {
                    "complete": 1, "partial": 1, "interrupted": 1,
                })
                self.assertIn(
                    "PARTIAL_OR_INTERRUPTED_ACTIONS",
                    compare_reports({accounts: result})
                    ["ratio_exclusion_reasons"][str(accounts)],
                )

    def test_partial_ui_coverage_deduplicates_per_outcome(self):
        report = summarize([
            "Miroir terminé: envoyés=4/4",
            "Miroir terminé: envoyés=4/4",
            "Miroir terminé: envoyés=4/4",
            "Miroir partiel: envoyés=1/4",
            "Miroir partiel: envoyés=2/4",
            "Miroir interrompu: envoyés=0/4",
            "Miroir : 4/4 fenêtres.",
            "Miroir incomplet : 1/4 fenêtres.",
            "Miroir interrompu : 0/4 fenêtres.",
            "Miroir Clavier : 4/4 fenêtres.",
            "Miroir Molette incomplet : 2/4 fenêtres.",
        ], 4)
        self.assertEqual(report["actions"], {
            "complete": 4, "partial": 3, "interrupted": 1,
        })
        self.assertEqual(report["roster_mismatch_lines"], 0)

    def test_key_and_wheel_workers_count_without_ui_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                report = summarize([
                    f"Miroir key: envoyés={accounts}/{accounts} worker_total_ms=21.0 "
                    "delivery_step_ms=None focus_activation_ms=None",
                    f"Miroir key: envoyés=1/{accounts} worker_total_ms=22.0 "
                    "delivery_step_ms=None focus_activation_ms=None",
                    f"Miroir wheel: envoyés=0/{accounts} worker_total_ms=13.0 "
                    "delivery_step_ms=None focus_activation_ms=None",
                    f"Miroir wheel: envoyés={accounts}/{accounts} worker_total_ms=30.0 "
                    "delivery_step_ms=None focus_activation_ms=None",
                    f"Miroir key: envoyés=7/{8 if accounts != 8 else 2} "
                    "worker_total_ms=999.0",
                ], accounts)
                self.assertEqual(report["actions"], {
                    "complete": 2, "partial": 2, "interrupted": 0,
                })
                self.assertEqual(report["roster_mismatch_lines"], 1)
                self.assertIn(
                    "PARTIAL_OR_INTERRUPTED_ACTIONS",
                    compare_reports({accounts: report})
                    ["ratio_exclusion_reasons"][str(accounts)],
                )

    def test_key_wheel_partial_ui_coverage_does_not_double_count(self):
        report = summarize([
            "Miroir key: envoyés=4/4 worker_total_ms=21.0",
            "Miroir key: envoyés=4/4 worker_total_ms=22.0",
            "Miroir wheel: envoyés=1/4 worker_total_ms=30.0",
            "Miroir wheel: envoyés=2/4 worker_total_ms=31.0",
            "Miroir Clavier : 4/4 fenêtres.",
            "Miroir Molette incomplet : 1/4 fenêtres.",
            "Miroir terminé: envoyés=4/4",
            "Miroir : 4/4 fenêtres.",
        ], 4)
        self.assertEqual(report["actions"], {
            "complete": 3, "partial": 2, "interrupted": 0,
        })

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


    def test_key_and_wheel_dispatch_metrics_are_account_scoped_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                foreign_count = 8 if count != 8 else 2
                report = summarize([
                    # These legacy records have no session size, so cannot
                    # be attributed after an Organizer roster change.
                    "Miroir key: dispatch_to_worker_ms=1.0 dispatch_to_last_emit_ms=999.0",
                    "Miroir wheel: dispatch_to_worker_ms=1.0 dispatch_to_last_emit_ms=999.0",
                    f"Miroir key: dispatch_to_worker_ms=3.0 "
                    f"dispatch_to_last_emit_ms=40.0 cibles={count} (envoi, pas rendu Unity)",
                    f"Miroir wheel: dispatch_to_worker_ms=4.0 "
                    f"dispatch_to_last_emit_ms=50.0 cibles={count} (envoi, pas rendu Unity)",
                    f"Miroir key: dispatch_to_worker_ms=5.0 "
                    f"dispatch_to_last_emit_ms=NOT_MEASURED cibles={count}",
                    f"Miroir wheel: dispatch_to_worker_ms=6.0 "
                    f"dispatch_to_last_emit_ms=NOT_MEASURED cibles={count}",
                    f"Miroir key: dispatch_to_worker_ms=1.0 "
                    f"dispatch_to_last_emit_ms=999.0 cibles={foreign_count}",
                ], count)
                metrics = report["metrics"]
                self.assertEqual(metrics["key_dispatch_to_worker_ms"]["n"], 2)
                self.assertEqual(metrics["key_dispatch_to_worker_ms"]["p95_ms"], 5.0)
                self.assertEqual(metrics["wheel_dispatch_to_worker_ms"]["p95_ms"], 6.0)
                self.assertEqual(metrics["key_dispatch_to_last_emit_ms"], {
                    "n": 1, "p50_ms": 40.0, "p95_ms": 40.0, "p99_ms": 40.0,
                })
                self.assertEqual(metrics["wheel_dispatch_to_last_emit_ms"]["p99_ms"], 50.0)
                self.assertEqual(report["roster_mismatch_lines"], 2)
                self.assertEqual(report["unity_render_latency"], "NOT_MEASURED")

    def test_dispatch_to_last_emit_p95_compares_separate_keyboard_sessions(self):
        reports = {
            count: summarize([
                f"Miroir key: dispatch_to_worker_ms=2.0 "
                f"dispatch_to_last_emit_ms={delay}.0 cibles={count}"
                for _ in range(5)
            ], count)
            for count, delay in ((2, 20), (4, 30), (6, 40), (8, 60))
        }
        compare = compare_reports(reports)
        self.assertEqual(compare["p95_ratio_vs_2_accounts"]
                         ["key_dispatch_to_last_emit_ms"], {
                             "2": 1.0, "4": 1.5, "6": 2.0, "8": 3.0,
                         })
        # A missing final emission must never be interpreted as a fast input.
        reports[8] = summarize([
            "Miroir key: dispatch_to_worker_ms=2.0 "
            "dispatch_to_last_emit_ms=NOT_MEASURED cibles=8"
            for _ in range(5)
        ], 8)
        self.assertIsNone(compare_reports(reports)["p95_ratio_vs_2_accounts"]
                          ["key_dispatch_to_last_emit_ms"]["8"])


    def test_click_worker_runtime_counts_only_actual_emission_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                other = 8 if count != 8 else 2
                report = summarize([
                    # An early abort with no sent click must not look fast.
                    f"Miroir mesures: n=0 total_ms=2.0 envoyés=0/{count}",
                    f"Miroir mesures delivery_step: n={count} "
                    f"p50_ms=5.0 p95_ms=7.0 p99_ms=7.0 "
                    f"total_ms=80.0 envoyés={count}/{count}",
                    f"Miroir mesures delivery_step: n=1 "
                    f"p50_ms=2.0 p95_ms=2.0 p99_ms=2.0 "
                    f"total_ms=90.0 envoyés=1/{count}",
                    f"Miroir mesures delivery_step: n=1 "
                    f"p50_ms=2.0 p95_ms=2.0 p99_ms=2.0 "
                    f"total_ms=1.0 envoyés=1/{other}",
                ], count)
                self.assertEqual(report["metrics"]["click_worker_ms"], {
                    "n": 2, "p50_ms": 80.0, "p95_ms": 90.0, "p99_ms": 90.0,
                })
                self.assertEqual(report["roster_mismatch_lines"], 1)
                self.assertEqual(report["unity_render_latency"], "NOT_MEASURED")

    def test_click_worker_comparison_excludes_partial_and_early_aborts(self):
        clean = summarize([
            "Miroir mesures delivery_step: n=2 p50_ms=5 p95_ms=8 "
            "p99_ms=8 total_ms=20 envoyés=2/2"
        ] * 5, 2)
        faster = summarize([
            "Miroir mesures delivery_step: n=8 p50_ms=5 p95_ms=8 "
            "p99_ms=8 total_ms=10 envoyés=8/8"
        ] * 5, 8)
        comparison = compare_reports({2: clean, 8: faster})
        self.assertEqual(comparison["p95_ratio_vs_2_accounts"]
                         ["click_worker_ms"]["8"], 0.5)
        faster = summarize([
            "Miroir mesures: n=0 total_ms=1 envoyés=0/8",
        ] * 5, 8)
        self.assertIsNone(compare_reports({2: clean, 8: faster})
                          ["p95_ratio_vs_2_accounts"]["click_worker_ms"]["8"])

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

    def test_mixed_roster_logs_cannot_be_attributed_to_one_size(self):
        report = summarize([
            "Miroir key: envoyés=2/2 worker_total_ms=21.0",
            "Miroir key: envoyés=8/8 worker_total_ms=90.0",
            "Miroir wheel: envoyés=2/2 worker_total_ms=35.0",
            "Miroir clic dispatch_to_worker_ms=1 dispatch_to_last_emit_ms=45",
        ], 2)
        self.assertEqual(report["metrics"]["key_worker_ms"]["n"], 1)
        self.assertEqual(report["metrics"]["key_worker_ms"]["p50_ms"], 21.0)
        self.assertEqual(report["metrics"]["wheel_worker_ms"]["n"], 1)
        self.assertIsNone(report["metrics"]["click_dispatch_to_last_emit_ms"])
        self.assertEqual(report["roster_mismatch_lines"], 1)

    def test_click_dispatch_metric_requires_explicit_roster_size(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                report = summarize([
                    # Legacy unscoped diagnostic: its account count cannot be
                    # reconstructed after a session's roster was changed.
                    "Miroir clic dispatch_to_worker_ms=4.00 dispatch_to_last_emit_ms=999.00 (envoi, pas rendu Unity)",
                    f"Miroir clic dispatch_to_worker_ms=3.00 dispatch_to_last_emit_ms=19.00 cibles={count} (envoi, pas rendu Unity)",
                    "Miroir clic dispatch_to_worker_ms=2.00 dispatch_to_last_emit_ms=88.00 cibles=1 (envoi, pas rendu Unity)",
                    f"Miroir clic dispatch_to_worker_ms=5.00 dispatch_to_last_emit_ms=NOT_MEASURED cibles={count} (envoi, pas rendu Unity)",
                ], count)
                self.assertEqual(
                    report["metrics"]["click_dispatch_to_last_emit_ms"],
                    {"n": 1, "p50_ms": 19.0, "p95_ms": 19.0, "p99_ms": 19.0},
                )
                # The worker and last-emission metrics both reject
                # this foreign action; the count is per rejected metric.
                self.assertEqual(report["roster_mismatch_lines"], 2)
        self.assertIsNone(summarize([
            "Miroir clic dispatch_to_worker_ms=4.00 dispatch_to_last_emit_ms=999.00 (envoi, pas rendu Unity)",
        ], 8)["metrics"]["click_dispatch_to_last_emit_ms"])

    def test_profile_changed_after_full_send_is_not_reported_complete(self):
        # Runtime explicitly distinguishes delivery count from final profile
        # integrity. A full counter must never silently become a green action.
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                result = summarize([
                    f"Miroir Clavier : {accounts}/{accounts} fenêtres (profil modifié après envoi).",
                    f"Miroir Molette : {accounts}/{accounts} fenêtres (profil modifié après envoi).",
                    f"Miroir : {accounts}/{accounts} fenêtres.",
                    f"Miroir Clavier : {accounts - 1}/{accounts} fenêtres.",
                    "Miroir Clavier : 8/8 fenêtres (profil modifié après envoi)." if accounts != 8
                    else "Miroir Clavier incomplet : 0/8 fenêtres.",
                ], accounts)
                self.assertEqual(result["actions"]["complete"], 1)
                self.assertEqual(result["actions"]["partial"], 4 if accounts == 8 else 3)
                self.assertEqual(result["profile_changed_after_send"], 2)
                self.assertEqual(result["roster_mismatch_lines"], 0 if accounts == 8 else 1)

    def test_unreadable_pointer_latch_is_interruption_not_invented_physical_loss(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                r = summarize([
                    f"Miroir interrompu : 0/{accounts} fenêtres "
                    "(contrôle souris indisponible).",
                    f"Miroir Molette interrompu : 0/{accounts} fenêtres "
                    "(contrôle souris indisponible).",
                ], accounts)
                self.assertEqual(r["actions"], {
                    "complete": 0, "partial": 0, "interrupted": 2,
                })
                self.assertEqual(r["non_replayed_statuses"], 0)
                self.assertEqual(
                    r["observed_blocked_inputs_per_mirror_action"],
                    {"click": 0, "wheel": 0},
                )
                self.assertIn(
                    "PARTIAL_OR_INTERRUPTED_ACTIONS",
                    compare_reports({2: r})["ratio_exclusion_reasons"]["2"],
                )

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

    def test_atomic_lease_loss_counters_remain_scoped_per_roster(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                r = summarize([
                    f"Miroir clic collisions_physiques=3 cibles={count}",
                    f"Miroir molette collisions_physiques=2 cibles={count}",
                    f"Miroir clic collisions_physiques=20 cibles={8 if count != 8 else 2}",
                ], count)
                self.assertEqual(r["observed_blocked_inputs_per_mirror_action"], {
                    "click": 3, "wheel": 2,
                })
                self.assertEqual(r["observed_blocked_physical_inputs"], {
                    "clicks": 0, "wheel_ticks": 0,
                })
                self.assertEqual(r["roster_mismatch_lines"], 1)

    def test_loss_counter_excludes_fast_p95_even_without_throttled_hook_logs(self):
        clean = summarize(["Miroir blocage_souris_ms=10 cibles=2"] * 5, 2)
        fast_but_lost = summarize(
            ["Miroir blocage_souris_ms=5 cibles=8"] * 5 + [
                "Miroir clic collisions_physiques=2 cibles=8",
            ], 8,
        )
        result = compare_reports({2: clean, 8: fast_but_lost})
        self.assertEqual(result["reports"]["8"]
                         ["observed_blocked_inputs_per_mirror_action"]["click"], 2)
        self.assertIsNone(result["p95_ratio_vs_2_accounts"]
                          ["click_pointer_block_ms"]["8"])
        self.assertIn(
            "BLOCKED_PHYSICAL_INPUTS_PER_ACTION",
            result["ratio_exclusion_reasons"]["8"],
        )
        self.assertEqual(
            result["reports"]["8"]["metrics"]["click_pointer_block_ms"]["p95_ms"],
            5.0,
        )

    def test_compare_p95_ratios_requires_five_samples_and_two_account_baseline(self):
        reports = {}
        for accounts, duration in ((2, 10), (4, 12), (6, 14), (8, 20)):
            reports[accounts] = summarize(
                (f"Miroir blocage_souris_ms={duration}.0 cibles={accounts}"
                 for _ in range(5)), accounts,
            )
        comparison = compare_reports(reports)
        self.assertEqual(
            comparison["p95_ratio_vs_2_accounts"]["click_pointer_block_ms"],
            {"2": 1.0, "4": 1.2, "6": 1.4, "8": 2.0},
        )
        self.assertEqual(comparison["minimum_samples_for_ratio"], 5)
        reports[8] = summarize(["Miroir blocage_souris_ms=20 cibles=8"], 8)
        self.assertIsNone(compare_reports(reports)["p95_ratio_vs_2_accounts"]
                          ["click_pointer_block_ms"]["8"])
        reports.pop(2)
        self.assertIsNone(compare_reports(reports)["p95_ratio_vs_2_accounts"]
                          ["click_pointer_block_ms"]["4"])

    def test_lossy_mirror_session_never_gets_a_favorable_p95_ratio(self):
        clean_2 = summarize([
            "Miroir blocage_souris_ms=10 cibles=2",
        ] * 5, 2)
        clean_8 = summarize([
            "Miroir blocage_souris_ms=5 cibles=8",
        ] * 5, 8)
        good = compare_reports({2: clean_2, 8: clean_8})
        self.assertEqual(good["p95_ratio_vs_2_accounts"]
                         ["click_pointer_block_ms"]["8"], 0.5)

        # Faster observed sends are not evidence of responsiveness when
        # another physical click was intercepted and never replayed.
        lossy_8 = summarize([
            "Miroir blocage_souris_ms=5 cibles=8",
        ] * 5 + [
            "Organizer entrées physiques bloquées: clics=1 molettes=0",
            "Miroir interrompu : 1/8 fenêtres (geste physique non rejoué).",
            "Miroir Molette : 8/8 fenêtres (profil modifié après envoi).",
        ], 8)
        result = compare_reports({2: clean_2, 8: lossy_8})
        self.assertIsNone(result["p95_ratio_vs_2_accounts"]
                          ["click_pointer_block_ms"]["8"])
        self.assertEqual(result["reports"]["8"]["metrics"]
                         ["click_pointer_block_ms"]["p95_ms"], 5.0)
        self.assertEqual(set(result["ratio_exclusion_reasons"]["8"]), {
            "PARTIAL_OR_INTERRUPTED_ACTIONS", "BLOCKED_PHYSICAL_INPUTS_IN_LOG",
            "PROFILE_CHANGED_AFTER_SEND", "UNREPLAYED_PHYSICAL_GESTURES",
        })
        lossy_2 = summarize([
            "Miroir blocage_souris_ms=10 cibles=2",
        ] * 5 + ["Organizer entrées physiques bloquées: clics=1 molettes=0"], 2)
        baseline_bad = compare_reports({2: lossy_2, 8: clean_8})
        self.assertIsNone(baseline_bad["p95_ratio_vs_2_accounts"]
                          ["click_pointer_block_ms"]["8"])

    def test_compare_cli_reads_separate_logs_and_keeps_evidence_uncertified(self):
        with tempfile.TemporaryDirectory() as directory:
            args = []
            for count in (2, 8):
                path = Path(directory) / f"atlas_{count}.log"
                path.write_text(
                    (f"Miroir blocage_souris_ms={count * 10}.0 cibles={count}\n" * 5),
                    encoding="utf-8",
                )
                args.extend(["--compare", f"{count}={path}"])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(args), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["p95_ratio_vs_2_accounts"]
                             ["click_pointer_block_ms"]["8"], 4.0)
            self.assertEqual(result["evidence"], "LOG_ONLY_NOT_UNITY_CERTIFIED")

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
