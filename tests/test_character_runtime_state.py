from __future__ import annotations

import unittest

from app.network.character_runtime_state import CharacterRuntimeStateStore


class CharacterRuntimeStateStoreTests(unittest.TestCase):
    def test_profile_facts_are_scoped_to_verified_session_identity(self):
        state = CharacterRuntimeStateStore()

        self.assertTrue(
            state.identify(
                session_id="session-a",
                character_key="character:42",
                character_id=42,
                name="Alpha",
            )
        )
        self.assertEqual(
            state.snapshot_for_session("session-a"),
            state.snapshot("character:42"),
        )
        self.assertTrue(
            state.update_verified_profile(
                "session-a",
                level=199,
                achievement_points=12345,
            )
        )
        alpha = state.snapshot("character:42")
        self.assertIsNotNone(alpha)
        self.assertEqual(alpha.level, 199)
        self.assertEqual(alpha.achievement_points, 12345)
        self.assertTrue(alpha.connected)

        # The same transport session can select another character. Facts from
        # the previous identity must not bleed into the new one.
        self.assertTrue(
            state.identify(
                session_id="session-a",
                character_key="character:84",
                character_id=84,
                name="Beta",
            )
        )
        beta = state.snapshot("character:84")
        self.assertIsNotNone(beta)
        self.assertIsNone(beta.level)
        self.assertIsNone(beta.achievement_points)
        self.assertFalse(state.snapshot("character:42").connected)
        self.assertEqual(state.snapshot_for_session("session-a"), beta)

        self.assertTrue(state.update_verified_profile("session-a", level=80))
        self.assertEqual(state.snapshot("character:84").level, 80)
        self.assertEqual(state.snapshot("character:42").level, 199)

    def test_invalid_or_unrouted_profile_updates_are_rejected(self):
        state = CharacterRuntimeStateStore()
        self.assertIsNone(state.snapshot_for_session("missing"))
        self.assertFalse(state.update_verified_profile("missing", level=200))
        self.assertFalse(
            state.identify(
                session_id="session-a",
                character_key="character:99",
                character_id=42,
                name="Mismatch",
            )
        )
        self.assertTrue(
            state.identify(
                session_id="session-a",
                character_key="character:42",
                character_id=42,
                name="Alpha",
            )
        )
        self.assertFalse(state.update_verified_profile("session-a", level=0))
        self.assertFalse(state.update_verified_profile("session-a", level=201))
        self.assertFalse(
            state.update_verified_profile("session-a", achievement_points=-1)
        )
        self.assertIsNone(state.snapshot("character:42").level)
        self.assertIsNone(state.snapshot("character:42").achievement_points)

    def test_session_close_and_character_delete_do_not_destroy_other_snapshots(self):
        state = CharacterRuntimeStateStore()
        state.identify(
            session_id="session-a",
            character_key="character:42",
            character_id=42,
            name="Alpha",
        )
        state.identify(
            session_id="session-b",
            character_key="character:84",
            character_id=84,
            name="Beta",
        )
        state.update_verified_profile("session-a", level=100)
        state.update_verified_profile("session-b", level=150)

        self.assertTrue(state.close_session("session-a"))
        self.assertIsNone(state.snapshot_for_session("session-a"))
        self.assertFalse(state.snapshot("character:42").connected)
        self.assertTrue(state.snapshot("character:84").connected)
        self.assertEqual(state.snapshot("character:42").level, 100)

        self.assertTrue(state.remove_character("character:42"))
        self.assertIsNone(state.snapshot("character:42"))
        self.assertEqual(state.snapshot("character:84").level, 150)


if __name__ == "__main__":
    unittest.main()
