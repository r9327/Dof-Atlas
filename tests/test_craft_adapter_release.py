from __future__ import annotations

"""Craft must not import SQLite adapter code merely while returning Home."""

import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from app import local_data_cache


ADAPTER_MODULE = "local_dofus_data.compatibility_adapter"


class CraftAdapterReleaseTests(unittest.TestCase):
    def test_release_does_not_import_adapter_when_never_constructed(self):
        # None is a sys.modules sentinel for an unavailable module. Any
        # attempted import raises ImportError, so a passing test cannot
        # accidentally hide a warmup/import footprint.
        with patch.dict(sys.modules, {ADAPTER_MODULE: None}):
            with patch.object(local_data_cache, "_compatibility_adapter",
                              side_effect=AssertionError("unexpected SQL adapter import")):
                local_data_cache.release_adapter()

    def test_release_calls_existing_module_without_reimporting(self):
        stub = ModuleType(ADAPTER_MODULE)
        stub.release_adapter = Mock()
        with patch.dict(sys.modules, {ADAPTER_MODULE: stub}):
            with patch.object(local_data_cache, "_compatibility_adapter",
                              side_effect=AssertionError("unexpected import")):
                local_data_cache.release_adapter()
        stub.release_adapter.assert_called_once_with()

    def test_live_adapter_is_closed_and_cleared(self):
        from local_dofus_data import compatibility_adapter

        active = Mock()
        with patch.object(compatibility_adapter, "_ADAPTER", active):
            local_data_cache.release_adapter()
            active.close.assert_called_once_with()
            self.assertIsNone(compatibility_adapter._ADAPTER)

    def test_release_stays_idempotent_for_live_adapter(self):
        from local_dofus_data import compatibility_adapter

        active = Mock()
        with patch.object(compatibility_adapter, "_ADAPTER", active):
            local_data_cache.release_adapter()
            local_data_cache.release_adapter()
            active.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
