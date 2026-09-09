from __future__ import annotations

import json
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from local_dofus_data.compatibility_adapter import LocalCompatibilityAdapter


class CompatibilityAdapterLazyImportTests(unittest.TestCase):
    def test_clean_class_import_does_not_load_store_or_repositories(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = (
            "import json, sys; "
            "from local_dofus_data.compatibility_adapter import LocalCompatibilityAdapter; "
            "print(json.dumps({"
            "'store': 'local_dofus_data.data_store' in sys.modules, "
            "'repos': 'local_dofus_data.repositories' in sys.modules, "
            "'import_manager': 'local_dofus_data.import_manager' in sys.modules"
            "}))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(
            payload,
            {"store": False, "repos": False, "import_manager": False},
        )

    def test_constructor_still_initializes_store_and_all_repositories(self) -> None:
        events: list[str] = []

        class FakeStore:
            def __init__(self, config=None):
                self.config = config
                events.append("store:init")

            def initialize(self):
                events.append("store:initialize")

            def close(self):
                events.append("store:close")

        def repository_type(name: str):
            class Repository:
                def __init__(self, store, config):
                    self.store = store
                    self.config = config
                    events.append(name)

            return Repository

        fake_store_module = types.ModuleType("local_dofus_data.data_store")
        fake_store_module.DataStore = FakeStore
        fake_repositories_module = types.ModuleType("local_dofus_data.repositories")
        fake_repositories_module.ImageRepository = repository_type("images")
        fake_repositories_module.ItemRepository = repository_type("items")
        fake_repositories_module.ItemSetRepository = repository_type("item_sets")
        fake_repositories_module.JobRepository = repository_type("jobs")
        fake_repositories_module.RecipeRepository = repository_type("recipes")
        fake_repositories_module.ResourceRepository = repository_type("resources")
        fake_config = object()

        with patch.dict(
            sys.modules,
            {
                "local_dofus_data.data_store": fake_store_module,
                "local_dofus_data.repositories": fake_repositories_module,
            },
        ):
            adapter = LocalCompatibilityAdapter(config=fake_config, auto_initialize=False)
            try:
                self.assertIs(adapter.config, fake_config)
                self.assertIs(adapter.items.store, adapter.store)
                self.assertIs(adapter.resources.store, adapter.store)
                self.assertIs(adapter.recipes.store, adapter.store)
                self.assertIs(adapter.item_sets.store, adapter.store)
                self.assertIs(adapter.jobs.store, adapter.store)
                self.assertIs(adapter.images.store, adapter.store)
            finally:
                adapter.close()

        self.assertEqual(
            events,
            [
                "store:init",
                "store:initialize",
                "items",
                "resources",
                "recipes",
                "item_sets",
                "jobs",
                "images",
                "store:close",
            ],
        )


if __name__ == "__main__":
    unittest.main()
