from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path

from app.network.contracts import _is_sha256
from app.network.mapping_manifest import ProtocolMappingError, parse_protocol_mapping
from app.network.mapping_registry import ProtocolMappingRegistry
from tests.test_network_mapping_registry import mapping_payload


# This is the full inventory from the audited source, not a hand-picked subset.
NETWORK_VALIDATOR_MODULES = (
    "bootstrap",
    "calibrated_mapping_install",
    "calibration_bootstrap",
    "correlated_identity_decoder",
    "current_protocol_profile",
    "deobfs_bundle",
    "discovery_evidence",
    "mapped_decoder",
    "mapping_manifest",
    "mapping_registry",
    "protocol_calibration",
    "protocol_extract",
    "protocol_status",
    "quest_completion_info_decoder",
    "quest_journal_decoder",
    "quest_snapshot_decoder",
)


def validators_in_module(short_name: str):
    module = importlib.import_module(f"app.network.{short_name}")
    found = []
    if callable(getattr(module, "_is_sha256", None)):
        found.append(module._is_sha256)
    for value in vars(module).values():
        if (
            isinstance(value, type)
            and value.__module__ == module.__name__
            and "_is_sha256" in value.__dict__
        ):
            found.append(getattr(value, "_is_sha256"))
    return found


class SharedNetworkShaContractTests(unittest.TestCase):
    def test_shared_active_build_and_decoder_lifecycle_are_fail_closed(self):
        from unittest.mock import Mock
        from app.network.contracts import (
            active_build_matches, forward_decoder_session_closed,
            forward_decoder_reset, is_current_ankama_alias,
        )

        fingerprint = "aB" * 32
        self.assertTrue(active_build_matches(lambda: " AB" * 32, fingerprint.casefold()) is False)
        self.assertTrue(active_build_matches(lambda: fingerprint.upper(), fingerprint.casefold()))
        self.assertFalse(active_build_matches(lambda: None, fingerprint.casefold()))
        self.assertFalse(active_build_matches(
            Mock(side_effect=RuntimeError("build not available")), fingerprint.casefold(),
        ))
        delegate = Mock()
        forward_decoder_session_closed(delegate, "session:1")
        forward_decoder_reset(delegate)
        delegate.session_closed.assert_called_once_with("session:1")
        delegate.reset.assert_called_once_with()
        forward_decoder_session_closed(object(), "session:2")
        forward_decoder_reset(object())
        for value, expected in (
            ("type.ankama.com/idr", True), ("type.ankama.com/IDR", False),
            ("type.ankama.com/abcd", False), ("ankama.com/idr", False),
            ("type.ankama.com/idé", False), ("type.ankama.com/idz", True),
        ):
            with self.subTest(value=value):
                self.assertEqual(is_current_ankama_alias(value), expected)

    def test_canonical_validator_rejects_legacy_whitespace_bypass(self):
        wrong = "aa" + " " * 60 + "bb"
        self.assertEqual(len(wrong), 64)
        self.assertEqual(len(bytes.fromhex(wrong)), 2)
        self.assertFalse(_is_sha256(wrong))
        for value in (None, True, 1, "a" * 63, "a" * 65,
                      "a" * 63 + " ", "a" * 63 + "é", "\u2007" * 64):
            with self.subTest(value=value):
                self.assertFalse(_is_sha256(value))
        self.assertTrue(_is_sha256("AB" * 32))
        self.assertTrue(_is_sha256("01" * 32))

    def test_all_sixteen_network_validators_share_strict_semantics(self):
        malformed = "aa" + " " * 60 + "bb"
        for name in NETWORK_VALIDATOR_MODULES:
            with self.subTest(name=name):
                validators = validators_in_module(name)
                self.assertEqual(len(validators), 1)
                for validator in validators:
                    self.assertFalse(validator(malformed))
                    self.assertFalse(validator(None))
                    self.assertFalse(validator("a" * 63))
                    self.assertTrue(validator("AB" * 32))

    def test_parser_and_registry_reject_fake_digest(self):
        forged = "aa" + " " * 60 + "bb"
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(mapping_payload(forged))
        with tempfile.TemporaryDirectory() as directory:
            mapping_file = Path(directory) / "mapping.json"
            mapping_file.write_text(json.dumps(mapping_payload(forged)), encoding="utf-8")
            registry = ProtocolMappingRegistry((directory,))
            self.assertFalse(registry.select(forged).usable)
            result = registry.select("a" * 64)
            self.assertFalse(result.usable)
            self.assertIn(mapping_file, result.invalid_paths)


if __name__ == "__main__":
    unittest.main()
