import unittest

from tools.atlas_data_plan import AtlasDataPlanError, DataRecord, plan_data_changes

A = "a" * 64
B = "b" * 64


class DataImportPlanTests(unittest.TestCase):
    def test_non_destructive_delta(self):
        old = [DataRecord("quest", "1", A), DataRecord("quest", "2", A)]
        new = [DataRecord("quest", "2", B), DataRecord("success", "3", A,
                                                      (("quest", "2"),))]
        result = plan_data_changes(old, new)
        self.assertEqual([(r.kind, r.identifier, r.action) for r in result], [
            ("quest", "1", "absent_in_batch"), ("quest", "2", "update"),
            ("success", "3", "add"),
        ])
        self.assertEqual(result[0].old_sha256, A)
        self.assertIsNone(result[0].new_sha256)

    def test_link_to_existing_quest_is_allowed(self):
        result = plan_data_changes(
            [DataRecord("quest", "42", A)],
            [DataRecord("guide", "g", B, (("quest", "42"),))],
        )
        self.assertEqual(result[-1].action, "add")

    def test_unknown_reference_fails(self):
        with self.assertRaises(AtlasDataPlanError):
            plan_data_changes([], [DataRecord("guide", "g", B, (("quest", "missing"),))])

    def test_duplicate_ids_fail_even_if_hash_same(self):
        with self.assertRaises(AtlasDataPlanError):
            plan_data_changes([], [DataRecord("quest", "1", A), DataRecord("quest", "1", A)])

    def test_invalid_ids_domains_hashes_fail(self):
        for row in (DataRecord("unknown", "1", A), DataRecord("quest", "../bad", A),
                    DataRecord("quest", "1", "broken"),
                    DataRecord("quest", "1", A, (("unknown", "2"),))):
            with self.subTest(row=row), self.assertRaises(AtlasDataPlanError):
                plan_data_changes([], [row])

    def test_explicit_reference_resolved(self):
        result = plan_data_changes(
            [], [DataRecord("success", "88", B, (("quest", "42"),))],
            known_references=[("quest", "42")],
        )
        self.assertEqual(result[0].action, "add")


if __name__ == "__main__":
    unittest.main()
