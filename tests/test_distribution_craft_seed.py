"""Frozen Craft first-install seed regression tests, no remote download."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution.user_data import prepare_user_data
from scripts.windows.craft_seed import (
    LOCK, RAW, SEED, build_seed, ensure_recipe_asset, validate_seed,
)

def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _source(rows):
    return {"references": {"RefIds": [{"data": row} for row in rows]}}


class CraftFirstInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        data = self.root / RAW
        _write_json(data / "languages/fr.json", {"entries":{
            "1":"Pelle", "2":"Fer", "3":"Mineur", "4":"Arme"}})
        _write_json(data / "item_types.json", _source([{"id": 99, "nameId":4}]))
        _write_json(data / "items.json", _source([
            {"id": 200, "nameId":1, "level":20, "typeId":99, "iconId":200},
            {"id": 201, "nameId":2, "level":1, "typeId":99, "iconId":201},
        ]))
        _write_json(data / "jobs.json", _source([{"id":12,"nameId":3}]))
        recipes = _source([{"resultId":200,"resultLevel":20,
                            "ingredientIds":{"Array":[201]},
                            "quantities":{"Array":[3]},"jobId":12}])
        _write_json(data / "recipes.json", recipes)
        payload=(data/"recipes.json").read_bytes()
        _write_json(self.root / LOCK, {
            "schema_version":1,"tag":"3.7.10.10","source_repo":"dofusdude/dofus3-main",
            "assets":{"recipes.json":{"asset":"recipes.json","size":len(payload),
                                      "sha256":hashlib.sha256(payload).hexdigest()}}})

    def test_public_seed_has_named_items_recipes_jobs_and_ingredients(self):
        output=self.root / SEED
        expected={"items":2,"jobs":1,"recipes":1,"recipe_ingredients":1}
        self.assertEqual(build_seed(self.root,output,minimums=expected),expected)
        self.assertEqual(validate_seed(output,minimums=expected),expected)
        with sqlite3.connect(output) as conn:
            rows=conn.execute(
                "SELECT r.result_name_fr, ri.name_fr, ri.quantity "
                "FROM recipes r JOIN recipe_ingredients ri ON ri.recipe_id=r.id"
            ).fetchall()
        self.assertEqual(rows,[("Pelle","Fer",3)])

    def test_invalid_source_fails_closed_before_publication(self):
        recipe=self.root / RAW / "recipes.json"
        recipe.write_text("{}",encoding="utf-8")
        with self.assertRaises(FileNotFoundError):
            ensure_recipe_asset(self.root)
        with self.assertRaises(FileNotFoundError):
            build_seed(self.root,self.root/SEED,minimums={})
        self.assertFalse((self.root/SEED).exists())

    def test_existing_user_database_not_overwritten_by_new_release(self):
        seed=self.root / SEED
        build_seed(self.root,seed,minimums={"items":2,"jobs":1,
                                           "recipes":1,"recipe_ingredients":1})
        frozen=self.root/"runtime/versions/v1/AtlasApp/AtlasApp.exe"
        frozen.parent.mkdir(parents=True,exist_ok=True)
        frozen.write_bytes(b"MZ")
        asset=frozen.parent/"_internal"/"data"/"bootstrap"/"craft_seed.sqlite"
        asset.parent.mkdir(parents=True,exist_ok=True)
        asset.write_bytes(seed.read_bytes())
        user=self.root/"user"
        with self.assertRaises(ValueError):
            # Missing sources or invalid package must not plant a user DB.
            bad=asset.with_name("corrupt.sqlite")
            bad.write_bytes(b"junk")
            asset.write_bytes(b"junk")
            prepare_user_data(frozen,user)
        self.assertFalse((user/"data/local/dofus_data.sqlite").exists())
        asset.write_bytes(seed.read_bytes())
        prepare_user_data(frozen,user)
        dest=user/"data/local/dofus_data.sqlite"
        self.assertTrue(dest.is_file())
        with sqlite3.connect(dest) as conn:
            conn.execute("UPDATE items SET name_fr='Utilisateur' WHERE ankama_id=200")
            conn.commit()
        prepare_user_data(frozen,user)
        with sqlite3.connect(dest) as conn:
            self.assertEqual(conn.execute(
                "SELECT name_fr FROM items WHERE ankama_id=200").fetchone()[0],
                "Utilisateur")


if __name__ == "__main__":
    unittest.main()
