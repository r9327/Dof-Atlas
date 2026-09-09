from __future__ import annotations

import unittest

from app.network.current_protocol_profile import (
    DOFUS_361010_PROFILE,
    LEGACY_UNSAFE_QUEST_COMPLETION_TYPE_URL,
    dofus_361010_candidate_manifest,
    dofus_361010_candidate_mapping_payload,
)


class CurrentProtocolProfileTests(unittest.TestCase):
    def test_profile_matches_reviewed_current_wire_contract(self) -> None:
        self.assertEqual(DOFUS_361010_PROFILE.game_version, "3.6.10.10")
        self.assertEqual(
            DOFUS_361010_PROFILE.evidence_revision,
            "jondo-401-quest-captures-2026-08-idz-final-step",
        )
        self.assertEqual(
            DOFUS_361010_PROFILE.source_commit,
            "cd97a887718b1d19eb449f096098511549947e3c",
        )
        self.assertEqual(DOFUS_361010_PROFILE.character_roster_type_url, "type.ankama.com/kvi")
        self.assertEqual(DOFUS_361010_PROFILE.character_selected_type_url, "type.ankama.com/kva")
        self.assertEqual(DOFUS_361010_PROFILE.quest_step_validated_type_url, "type.ankama.com/idz")
        self.assertEqual(DOFUS_361010_PROFILE.quest_journal_type_url, "type.ankama.com/idr")
        self.assertEqual(LEGACY_UNSAFE_QUEST_COMPLETION_TYPE_URL, "type.ankama.com/lqn")

    def test_candidate_defaults_to_idz_live_only_until_journal_calibration(self) -> None:
        payload = dofus_361010_candidate_mapping_payload("ab" * 32)
        self.assertEqual(payload["game_version"], "3.6.10.10")
        self.assertEqual(payload["build_sha256"], "ab" * 32)
        self.assertEqual(payload["character_identity"]["roster_type_url"], "type.ankama.com/kvi")
        self.assertEqual(payload["character_identity"]["selected_type_url"], "type.ankama.com/kva")
        self.assertEqual(
            payload["character_identity"]["selected_character_name_path"],
            [1, 1, 1, 2],
        )
        self.assertNotIn("quest_completion_info", payload)

        self.assertEqual(set(payload["messages"]), {"type.ankama.com/idz"})
        live = payload["messages"]["type.ankama.com/idz"]
        self.assertEqual(live["event_type"], "quest_completed")
        self.assertEqual(
            live["fields"],
            [
                {
                    "output_name": "quest_id",
                    "path": [1],
                    "kind": "positive_int",
                    "required": True,
                },
                {
                    "output_name": "validated_step_id",
                    "path": [2],
                    "kind": "positive_int",
                    "required": True,
                },
            ],
        )
        self.assertNotIn("quest_journal_snapshot", payload)
        self.assertNotIn("finished_quests_snapshot", payload)

    def test_reviewed_journal_is_added_only_when_explicitly_enabled(self) -> None:
        payload = dofus_361010_candidate_mapping_payload(
            "ab" * 32,
            include_quest_journal=True,
        )
        journal = payload["quest_journal_snapshot"]
        self.assertEqual(journal["type_url"], "type.ankama.com/idr")
        self.assertEqual(journal["active_entry_field"], 1)
        self.assertEqual(journal["active_body_field"], 2)
        self.assertEqual(journal["active_quest_id_field"], 3)
        self.assertEqual(journal["finished_entry_field"], 3)
        self.assertEqual(journal["finished_marker_field"], 1)
        self.assertEqual(journal["finished_quest_id_field"], 2)
        self.assertEqual(journal["additional_finished_packed_field"], 4)

        manifest = dofus_361010_candidate_manifest(
            "ab" * 32,
            include_quest_journal=True,
        )
        self.assertIn("quest_completed", manifest.provided_event_types)
        self.assertIn("quest_journal_snapshot", manifest.provided_event_types)
        self.assertIn("quest_completion", manifest.provided_event_types)
        self.assertIsNone(manifest.quest_completion_info)

    def test_legacy_snapshot_alias_remains_compatibility_only(self) -> None:
        payload = dofus_361010_candidate_mapping_payload(
            "ab" * 32,
            finished_quests_snapshot_type_url="type.ankama.com/qzx",
        )
        snapshot = payload["finished_quests_snapshot"]
        self.assertEqual(snapshot["type_url"], "type.ankama.com/qzx")
        self.assertEqual(snapshot["finished_entry_field"], 1)
        self.assertEqual(snapshot["quest_id_path_from_entry"], [1])
        self.assertEqual(snapshot["player_id_field"], 4)
        manifest = dofus_361010_candidate_manifest(
            "ab" * 32,
            finished_quests_snapshot_type_url="type.ankama.com/qzx",
        )
        self.assertIn("finished_quests_snapshot", manifest.provided_event_types)
        self.assertIn("quest_completion", manifest.provided_event_types)

    def test_candidate_manifest_satisfies_runtime_capabilities(self) -> None:
        manifest = dofus_361010_candidate_manifest("ab" * 32)
        self.assertIn("character_identified", manifest.provided_event_types)
        self.assertIn("quest_completed", manifest.provided_event_types)
        self.assertIn("quest_completion", manifest.provided_event_types)

    def test_rejects_invalid_build_hash(self) -> None:
        for value in ("", "abc", "g" * 64, "a" * 63):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    dofus_361010_candidate_mapping_payload(value)

    def test_rejects_invalid_or_conflicting_legacy_snapshot_alias(self) -> None:
        for value in (
            "ankama.com/qzx",
            "type.ankama.com/TOO-LONG",
            "type.ankama.com/kvi",
            "type.ankama.com/kva",
            "type.ankama.com/idz",
            "type.ankama.com/lqn",
            "type.ankama.com/idr",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    dofus_361010_candidate_mapping_payload(
                        "ab" * 32,
                        finished_quests_snapshot_type_url=value,
                    )

    def test_returned_payloads_do_not_share_mutable_path_lists(self) -> None:
        first = dofus_361010_candidate_mapping_payload("ab" * 32)
        second = dofus_361010_candidate_mapping_payload("cd" * 32)
        first["character_identity"]["roster_character_id_path"].append(999)
        first["character_identity"]["selected_character_name_path"].append(999)
        first["messages"]["type.ankama.com/idz"]["fields"][0]["path"].append(999)
        self.assertEqual(second["character_identity"]["roster_character_id_path"], [2])
        self.assertEqual(
            second["character_identity"]["selected_character_name_path"],
            [1, 1, 1, 2],
        )
        self.assertEqual(
            second["messages"]["type.ankama.com/idz"]["fields"][0]["path"],
            [1],
        )


if __name__ == "__main__":
    unittest.main()
