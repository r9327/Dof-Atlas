"""One worklist row for every Doctor resource candidate; no automatic approvals."""
import unittest
from scripts.windows.export_app_repository import selected_runtime_path
from tools.doctor_candidate_worklist import build_worklists


class DoctorCandidateWorklistTests(unittest.TestCase):
    def report(self):
        sha = "a" * 40
        return {
            "candidate_sha": sha, "worktree_clean": True,
            "resource_link_audit": {
                "all_link_candidates_exported": True,
                "all_candidates_exported": True,
                "triage_counts_complete": True,
                "automatic_deletion_authorized": False,
                "counts": {"unresolved_literals": 3, "unsafe_literals": 1, "possible_edges": 1},
                "unresolved_literal_all_candidates": [
                    {"source": "app/constants.py", "literal": "client_profiles.json",
                     "kind": "UNRESOLVED_RESOURCE_LITERAL_REVIEW"},
                    {"source": "app/modules/encyclopedia/providers/guide_provider.py",
                     "literal": "*.json", "kind": "UNRESOLVED_RESOURCE_LITERAL_REVIEW"},
                    {"source": "scripts/windows/craft_seed.py",
                     "literal": "recipes.json", "kind": "UNRESOLVED_RESOURCE_LITERAL_REVIEW"},
                    {"source": "app/distribution/release_client.py",
                     "literal": "/releases/latest/download/atlas-channel.json",
                     "kind": "UNSAFE_RESOURCE_LITERAL_REVIEW"},
                ],
                "ambiguous_literal_all_candidates": [{
                    "source": "app/main.py", "literal": "logo.png",
                    "kind": "BASENAME_ONLY_REVIEW",
                    "candidate_count": 2, "candidates": ["data/logo.png", "data/icons/logo.png"]
                }],
                "no_static_consumer_total": 3,
                "no_static_consumer_all_candidates": [
                    "data/images/archive/unmatched/1.png",
                    "data/images/items/10.png",
                    "data/encyclopedia/guides/catalog.json",
                ],
            },
        }

    def test_exact_counts_review_every_candidate_without_falsely_passing(self):
        links, assets, summary = build_worklists(self.report())
        self.assertEqual((len(links), len(assets)), (5, 3))
        self.assertEqual(summary["links_count"], 5)
        self.assertEqual(summary["assets_count"], 3)
        self.assertEqual(summary["closed_without_proof"], 0)
        self.assertEqual(summary["open_link_reviews"], 5)
        self.assertEqual(summary["open_asset_reviews"], 3)
        self.assertFalse(summary["automatic_deletion_authorized"])
        self.assertTrue(all(x["review_status"].startswith("OPEN_") for x in links + assets))
        self.assertEqual(len({x["id"] for x in links}), 5)

    def test_glob_remote_endpoint_and_user_state_are_not_called_missing_assets(self):
        links, _, summary = build_worklists(self.report())
        self.assertEqual(links[0]["triage_family"], "LOCAL_OR_INSTALL_STATE_REVIEW")
        self.assertEqual(links[1]["triage_family"], "GLOB_PATTERN_NOT_AN_EXACT_FILE_REVIEW")
        self.assertEqual(links[2]["source_scope"], "WINDOWS_PACKAGING")
        self.assertEqual(links[3]["triage_family"], "REMOTE_RELEASE_ENDPOINT_REVIEW")
        self.assertEqual(links[4]["candidate_count"], 2)
        self.assertEqual(links[4]["possible_targets"], "data/logo.png|data/icons/logo.png")
        self.assertEqual(sum(summary["links_by_family"].values()), 5)

    def test_real_app_mirror_allowlist_is_used_instead_of_guessed(self):
        _, assets, summary = build_worklists(self.report())
        self.assertFalse(selected_runtime_path("data/images/items/10.png"))
        self.assertTrue(selected_runtime_path("data/encyclopedia/guides/catalog.json"))
        self.assertEqual([x["app_mirror_allowlist"] for x in assets],
                         ["EXCLUDED", "EXCLUDED", "INCLUDED"])
        self.assertEqual(summary["assets_by_mirror_allowlist"],
                         {"EXCLUDED": 2, "INCLUDED": 1})
        self.assertTrue(all(x["packaged_in_exe_verified"] == "NOT_RUN" for x in assets))

    def test_truncated_ambiguous_results_cannot_be_certified(self):
        report = self.report()
        report["resource_link_audit"]["ambiguous_literal_all_candidates"][0]["candidate_count"] = 4
        with self.assertRaisesRegex(ValueError, "truncated"):
            build_worklists(report)

    def test_dynamic_ganymede_cutover_never_becomes_disposable(self):
        report = self.report()
        names = [
            "data/encyclopedia/guides/replacement_drafts/cutovers/dofus_cawotte.json",
            "data/encyclopedia/guides/replacement_drafts/dofus_cawotte.json",
            "data/encyclopedia/guides/ganymede_2203_action_candidates.json",
            "data/images/classes/pandawa.png",
        ]
        report["resource_link_audit"]["no_static_consumer_all_candidates"] = names
        report["resource_link_audit"]["no_static_consumer_total"] = len(names)
        _, assets, summary = build_worklists(report)
        self.assertEqual(assets[0]["triage_family"],
                         "GANYMEDE_TRUSTED_CUTOVER_ROUTE_DYNAMIC_CONSUMER_REVIEW")
        self.assertEqual(assets[1]["triage_family"],
                         "GANYMEDE_REPLACEMENT_ROUTE_DYNAMIC_CONSUMER_REVIEW")
        self.assertEqual(assets[2]["triage_family"],
                         "GANYMEDE_DIAGNOSTIC_INPUT_REVIEW")
        self.assertEqual(assets[3]["triage_family"], "CLASS_PORTRAIT_BUNDLE_REVIEW")
        for asset in assets[:2]:
            self.assertIn("select_verified_replacement_path", asset["known_dynamic_loader"])
        self.assertTrue(all(asset["review_status"].startswith("OPEN_") for asset in assets))
        self.assertEqual(summary["closed_without_proof"], 0)

    def test_existing_link_review_ids_survive_unrelated_findings(self):
        baseline = self.report()
        first, _, _ = build_worklists(baseline)
        newer = self.report()
        candidate = {"source": "tools/extra.py", "literal": "new-data.json",
                     "line": 9, "kind": "UNRESOLVED_RESOURCE_LITERAL_REVIEW"}
        newer["resource_link_audit"]["unresolved_literal_all_candidates"].insert(0, candidate)
        newer["resource_link_audit"]["counts"]["unresolved_literals"] += 1
        second, _, _ = build_worklists(newer)
        self.assertEqual({item["id"] for item in first},
                         {item["id"] for item in second[1:]})
        self.assertNotIn(second[0]["id"], {item["id"] for item in first})

    def test_same_source_and_literal_at_same_line_still_get_unique_ids(self):
        duplicate = self.report()
        entry = duplicate["resource_link_audit"]["unresolved_literal_all_candidates"][0]
        duplicate["resource_link_audit"]["unresolved_literal_all_candidates"].append(dict(entry))
        duplicate["resource_link_audit"]["counts"]["unresolved_literals"] += 1
        rows, _, _ = build_worklists(duplicate)
        self.assertEqual(len(rows), len({row["id"] for row in rows}))

    def test_missing_rows_and_stale_worktree_are_rejected(self):
        report = self.report()
        report["resource_link_audit"]["counts"]["unresolved_literals"] += 1
        with self.assertRaisesRegex(ValueError, "cardinality"):
            build_worklists(report)
        report = self.report()
        report["worktree_clean"] = False
        with self.assertRaisesRegex(ValueError, "incomplete"):
            build_worklists(report)


if __name__ == "__main__":
    unittest.main()
