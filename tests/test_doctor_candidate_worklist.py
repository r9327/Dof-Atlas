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
