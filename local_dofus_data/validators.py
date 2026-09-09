from __future__ import annotations

from typing import Any

from .data_store import DataStore


class Validator:
    def __init__(self, store: DataStore):
        self.store = store

    def run_all(self) -> dict[str, Any]:
        warnings: list[str] = []
        warnings.extend(self._missing("items", "name_fr", "item sans nom"))
        warnings.extend(self._missing("resources", "ankama_id", "ressource sans id"))
        warnings.extend(self._recipes_without_ingredients())
        warnings.extend(self._unknown_ingredients())
        warnings.extend(self._missing("maps", "map_id", "map sans mapId"))
        warnings.extend(self._invalid_cells())
        warnings.extend(self._duplicates("items", "ankama_id", "doublon item ankama_id suspect"))
        warnings.extend(self._missing("texts", "text", "texte manquant"))
        warnings.extend(self._missing_images())
        warnings.extend(self._unknown_sources())
        return {"status": "ok", "warning_count": len(warnings), "warnings": warnings}

    def _missing(self, table: str, column: str, label: str) -> list[str]:
        rows = self.store.query_all(f"SELECT id FROM {table} WHERE {column} IS NULL OR {column}=''", ())
        return [f"{label}: {table}.id={row['id']}" for row in rows[:200]]

    def _recipes_without_ingredients(self) -> list[str]:
        rows = self.store.query_all(
            """
            SELECT r.id, r.result_ankama_id, r.result_name_fr
            FROM recipes r
            LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id
            GROUP BY r.id
            HAVING COUNT(ri.id)=0
            """
        )
        return [f"recette sans ingredients: {row.get('result_name_fr') or row.get('result_ankama_id')}" for row in rows[:200]]

    def _unknown_ingredients(self) -> list[str]:
        rows = self.store.query_all(
            """
            SELECT ri.ingredient_ankama_id, ri.name_fr
            FROM recipe_ingredients ri
            LEFT JOIN items i ON i.ankama_id = ri.ingredient_ankama_id
            WHERE ri.ingredient_ankama_id IS NOT NULL AND i.id IS NULL
            LIMIT 200
            """
        )
        return [f"ingredient inconnu: {row.get('name_fr') or row.get('ingredient_ankama_id')}" for row in rows]

    def _invalid_cells(self) -> list[str]:
        rows = self.store.query_all(
            "SELECT map_id, cell_id FROM cells WHERE cell_id IS NULL OR cell_id < 0 OR cell_id > 559 LIMIT 200"
        )
        return [f"cellule invalide: map={row['map_id']} cell={row['cell_id']}" for row in rows]

    def _duplicates(self, table: str, column: str, label: str) -> list[str]:
        rows = self.store.query_all(
            f"SELECT {column}, COUNT(*) AS count FROM {table} WHERE {column} IS NOT NULL GROUP BY {column} HAVING COUNT(*) > 1 LIMIT 200"
        )
        return [f"{label}: {row[column]} ({row['count']})" for row in rows]

    def _missing_images(self) -> list[str]:
        rows = self.store.query_all(
            "SELECT ankama_id, name_fr FROM items WHERE image_path='' AND name_fr!='' LIMIT 200"
        )
        return [f"image manquante: {row.get('name_fr') or row.get('ankama_id')}" for row in rows]

    def _unknown_sources(self) -> list[str]:
        rows = self.store.query_all(
            """
            SELECT source FROM (
                SELECT source FROM items
                UNION SELECT source FROM recipes
                UNION SELECT source FROM maps
                UNION SELECT source FROM texts
            )
            WHERE source!='' AND source NOT IN (SELECT type FROM sources)
            LIMIT 200
            """
        )
        return [f"source inconnue: {row['source']}" for row in rows]
