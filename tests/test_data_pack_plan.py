import unittest

from app.distribution.data_pack_plan import (
    DataPack, InstalledPack, InvalidDataPack, plan_pack_updates,
)

A = "a" * 64
B = "b" * 64


class DataPackUpdatePlanTests(unittest.TestCase):
    def test_only_changed_pack_downloads(self):
        plans = plan_pack_updates(
            {"guides": InstalledPack(7, 1, A), "quests": InstalledPack(3, 1, A)},
            [DataPack("guides", 8, 1, B, "data/guides/8.json"),
             DataPack("quests", 3, 1, A, "data/quests/3.json")],
        )
        self.assertEqual([(p.kind, p.action) for p in plans],
                         [("guides", "download"), ("quests", "keep")])
        self.assertIsNone(plans[-1].artifact_path)

    def test_refuse_version_rollback(self):
        with self.assertRaises(InvalidDataPack):
            plan_pack_updates(
                {"quests": InstalledPack(7, 1, A)},
                [DataPack("quests", 6, 1, B, "data/quests/6.json")],
            )

    def test_refuse_same_revision_different_content(self):
        with self.assertRaises(InvalidDataPack):
            plan_pack_updates(
                {"quests": InstalledPack(7, 1, A)},
                [DataPack("quests", 7, 1, B, "data/quests/7.json")],
            )

    def test_refuse_schema_downgrade(self):
        with self.assertRaises(InvalidDataPack):
            plan_pack_updates(
                {"guides": InstalledPack(1, 3, A)},
                [DataPack("guides", 2, 2, B, "data/guides/2.json")],
            )

    def test_refuse_traversal_and_unknown_kind(self):
        for pack in (DataPack("guides", 2, 1, B, "data/../secret"),
                     DataPack("other", 2, 1, B, "data/other/x.json"),
                     DataPack("guides", True, 1, B, "data/guides/x.json")):
            with self.subTest(pack=pack), self.assertRaises(InvalidDataPack):
                plan_pack_updates({}, [pack])

    def test_refuse_duplicate_pack(self):
        pack = DataPack("quests", 1, 1, A, "data/quests/1.json")
        with self.assertRaises(InvalidDataPack):
            plan_pack_updates({}, [pack, pack])


if __name__ == "__main__":
    unittest.main()
