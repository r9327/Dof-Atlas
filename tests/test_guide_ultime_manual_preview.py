from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import GuideUltimeManualRuntimeService
from app.modules.encyclopedia.views.guide_ultime_manual_view import (
    NPC_COLOR,
    RESOURCE_COLOR,
    GuideUltimeManualCard,
    GuideUltimeManualView,
)
from app.modules.encyclopedia.views.guides_view import GuidesView
from app.quest_catalog import normalize_text


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = MANUAL / "manifest_v1.json"


def canonical_manifest_rows() -> list[dict]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    canonical = payload.get("canonical") if isinstance(payload.get("canonical"), dict) else {}
    rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    rows.sort(key=lambda row: int(row.get("order") or 0))
    return rows


class _FakeQuestProgress:
    def __init__(self, completed=()):
        self.completed = {int(value) for value in completed}

    def is_quest_completed(self, _character_key: str, quest_id: int) -> bool:
        return int(quest_id) in self.completed

    def completed_quest_ids(self, _character_key: str) -> set[int]:
        return set(self.completed)


class _FakeAchievementProgress:
    def __init__(self):
        self.choice: tuple[str, str] | None = None

    def alignment_order_choice(self, _character_key: str):
        return self.choice

    def set_alignment_order_choice(self, _character_key: str, side: str, order_name: str) -> None:
        self.choice = (str(side), str(order_name))


class GuideUltimeManualPreviewTests(unittest.TestCase):
    def _bare_service(self) -> GuideUltimeManualRuntimeService:
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.manual_dir = MANUAL
        service.quest_provider = None
        service._quest_name_to_id = {}
        service.quest_progress = _FakeQuestProgress()
        service.achievement_progress = _FakeAchievementProgress()
        return service

    def test_manifest_drives_all_canonical_chapters_without_hardcoded_preview(self):
        rows = canonical_manifest_rows()
        self.assertGreater(len(rows), 2)
        ids = [str(row.get("id") or "") for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(ids))

        actual_total = 0
        for row in rows:
            chapter = load_manual_chapter(MANUAL / str(row["file"]))
            stages = [stage for stage in chapter.get("stages", []) or [] if isinstance(stage, dict)]
            self.assertEqual(
                len(stages),
                int(row["stage_count"]),
                f"stage_count incohérent pour {row.get('id')}",
            )
            actual_total += len(stages)

        self.assertEqual(actual_total, sum(int(row["stage_count"]) for row in rows))

        source = inspect.getsource(GuideUltimeManualRuntimeService._load_manual_preview_uncached)
        self.assertNotIn("PREVIEW_CHAPTER_IDS", source)
        self.assertIn('canonical.get("chapters"', source)
        self.assertIn("load_manual_chapter", source)

    def test_every_canonical_stage_renders_real_player_instructions(self):
        service = self._bare_service()
        empty: list[str] = []

        for row in canonical_manifest_rows():
            chapter_id = str(row.get("id") or "")
            chapter = load_manual_chapter(MANUAL / str(row["file"]))
            for stage in chapter.get("stages", []) or []:
                if not isinstance(stage, dict):
                    continue
                names = service._stage_quest_names(stage)
                lines = service._stage_lines(stage, names)
                if not lines:
                    empty.append(f"{chapter_id}:{stage.get('id')}")

        self.assertEqual(empty, [], f"Fiches canoniques sans instructions joueur: {empty}")

    def test_compact_route_pos_do_format_is_supported(self):
        astrub = load_manual_chapter(MANUAL / "astrub_v4.json")
        stage = next(row for row in astrub["stages"] if row.get("id") == "AST-00")
        self.assertTrue(stage.get("route"))
        service = self._bare_service()
        lines = service._stage_lines(stage, service._stage_quest_names(stage))
        self.assertGreaterEqual(len(lines), 2)
        self.assertTrue(any(row.get("position") == "[6,-19]" for row in lines))
        self.assertTrue(any("Prendre" in str(row.get("text")) for row in lines))

    def test_advanced_take_preparation_progress_and_exit_dialects_are_supported(self):
        stage = {
            "quests": ["Une quête de test"],
            "take": ["Prendre Une quête de test auprès de Testeur."],
            "preparation": [
                {"name": "Ressource Test", "quantity": 3, "policy": "Garder en banque jusqu'au passage."},
                {"requirement": "Métier Alchimiste niveau 50 avant le prochain craft."},
            ],
            "progress_also": ["Tuer les monstres de la zone pendant le trajet."],
            "before_leave": ["Vérifier que les trois objets sont dans l'inventaire."],
            "hard_stop": "Ne pas quitter la zone avant le dialogue final.",
        }
        service = self._bare_service()
        lines = service._stage_lines(stage, service._stage_quest_names(stage))
        text = "\n".join(str(row.get("text") or "") for row in lines)
        self.assertIn("Prendre Une quête de test", text)
        self.assertIn("Prépare 3 × Ressource Test", text)
        self.assertIn("Alchimiste niveau 50", text)
        self.assertIn("Tuer les monstres", text)
        self.assertIn("Ne pas quitter la zone", text)

    def test_manual_order_routes_come_from_manifest_and_keep_same_choice(self):
        service = self._bare_service()
        service._quest_name_to_id = {
            normalize_text("Le fantôme de Tsog"): 200,
            normalize_text("C'est stupéfiant"): 201,
            normalize_text("Apprentissage : Disciple de Ménalt"): 300,
            normalize_text("Apprentissage : Écuyer"): 301,
        }
        routes = service._manual_order_routes()
        self.assertEqual([row["rank"] for row in routes], [20, 40, 60, 80, 100])
        self.assertEqual(service.bonta_order_names(), ("Cœur Vaillant", "Œil Attentif", "Esprit Salvateur"))

        card20 = {
            "manual_stage_id": "order-rank-20",
            "manual_quest_ids": [200],
            "manual_lines": [{"kind": "action", "position": "Bonta", "text": "Finir le rang 20."}],
            "manual_quest_names": [normalize_text("Le fantôme de Tsog")],
        }
        self.assertTrue(service.manual_order_choice_blocking("character:1", card20))
        self.assertFalse(service.manual_order_choice_required("character:1", card20))
        service.quest_progress.completed.add(200)
        self.assertTrue(service.manual_order_choice_required("character:1", card20))

        service.set_bonta_order("character:1", "Cœur Vaillant")
        self.assertEqual(service.selected_order_name("character:1"), "Cœur Vaillant")
        self.assertFalse(service.manual_order_choice_required("character:1", card20))
        branch_text = "\n".join(row["text"] for row in service.manual_lines_for_card("character:1", card20))
        self.assertIn("Jerhyn Gholein", branch_text)
        self.assertNotIn("Ebru of El", branch_text)
        self.assertNotIn("Elviana Tirips", branch_text)

        with self.assertRaises(ValueError):
            service.set_bonta_order("character:1", "Œil Attentif")

        card40 = {
            "manual_stage_id": "order-rank-40",
            "manual_quest_ids": [201],
            "manual_lines": [],
            "manual_quest_names": [normalize_text("C'est stupéfiant")],
        }
        rank40_text = "\n".join(row["text"] for row in service.manual_lines_for_card("character:1", card40))
        self.assertIn("Jerhyn Gholein", rank40_text)
        self.assertIn("Écuyer", rank40_text)
        self.assertNotIn("Ebru of El", rank40_text)
        self.assertNotIn("Elviana Tirips", rank40_text)

    def test_temporal_hook_resolves_to_player_policy_not_raw_id(self):
        service = self._bare_service()
        card = {
            "manual_lines": [],
            "manual_quest_ids": [],
            "manual_quest_names": [],
            "manual_temporal_hooks": ["frigost_depot_lulu_day_window"],
        }
        text = "\n".join(row["text"] for row in service.manual_lines_for_card("slot:1", card))
        self.assertIn("08:00", text)
        self.assertIn("20:00", text)
        self.assertIn("n'attends pas sur place", text)
        self.assertNotIn("frigost_depot_lulu_day_window", text)

    def test_manual_resource_names_come_from_authored_resource_plans_and_preparation(self):
        incarnam = load_manual_chapter(MANUAL / "incarnam_v1.json")
        resources = GuideUltimeManualRuntimeService._stage_resource_names(incarnam, incarnam["stages"][0])
        self.assertIn("Lailait", resources)
        self.assertIn("Blé", resources)
        self.assertIn("Poudre de Perlinpainpain", resources)

        post_200 = load_manual_chapter(MANUAL / "level_200_plus_v4.json")
        stage = next(row for row in post_200["stages"] if row.get("id") == "P200-23")
        advanced_resources = GuideUltimeManualRuntimeService._stage_resource_names(post_200, stage)
        self.assertIn("Pépite", advanced_resources)
        self.assertIn("Métronome du Début-Temps", advanced_resources)

    def test_npc_and_resource_are_bold_with_distinct_colors(self):
        text = "Parler à Ganymède puis acheter 1 Lailait."
        npc_names = GuideUltimeManualCard._npc_names(text)
        self.assertEqual(npc_names, ["Ganymède"])
        rich = GuideUltimeManualCard._format_line_html(
            "• ",
            "[1,1]",
            text,
            npc_names,
            ["Lailait"],
        )
        self.assertIn(f"color:{NPC_COLOR}", rich)
        self.assertIn("<b>Ganymède</b>", rich)
        self.assertIn(f"color:{RESOURCE_COLOR}", rich)
        self.assertIn("<b>Lailait</b>", rich)

    def test_generic_role_is_not_highlighted_as_npc(self):
        self.assertEqual(
            GuideUltimeManualCard._npc_names("Parler au tavernier pour acheter une bière."),
            [],
        )

    def test_guides_view_constructs_manual_runtime_lazily(self):
        init_source = inspect.getsource(GuidesView.__init__)
        lazy_source = inspect.getsource(GuidesView.ensure_guide_ultime_view)
        self.assertIn("self.guide_ultime_service: GuideUltimeManualRuntimeService | None = None", init_source)
        self.assertIn("self.guide_ultime_view: GuideUltimeManualView | None = None", init_source)
        self.assertNotIn("GuideUltimeManualRuntimeService(", init_source)
        self.assertIn("GuideUltimeManualRuntimeService(", lazy_source)
        self.assertIn("GuideUltimeManualView(", lazy_source)
        self.assertIn("quest_provider=self.quest_provider", lazy_source)
        self.assertIn("build_route_auto_validation_contract", lazy_source)

    def test_manual_service_reads_canonical_manifest(self):
        source = inspect.getsource(GuideUltimeManualRuntimeService._load_manual_preview_uncached)
        self.assertIn("manifest_v1.json", source)
        self.assertIn("load_manual_chapter", source)
        self.assertIn("manual_manifest", source)
        self.assertIn("empty_cards", source)

    def test_breadcrumb_matches_quests_page_construction_and_uses_theme_tokens(self):
        source = inspect.getsource(GuideUltimeManualView._build_ui)
        render = inspect.getsource(GuideUltimeManualView._render_breadcrumb)
        view_source = inspect.getsource(GuideUltimeManualView)
        style_source = (ROOT / "app" / "ui" / "theme.py").read_text(encoding="utf-8")

        self.assertIn('setObjectName("GuideBreadcrumb")', source)
        self.assertIn("setContentsMargins(8, 5, 8, 5)", source)
        self.assertIn("setSpacing(5)", source)
        self.assertIn('setObjectName("GuideBreadcrumbButton")', render)
        self.assertIn(
            'setObjectName("GuideBreadcrumbSeparator")',
            inspect.getsource(GuideUltimeManualView._add_breadcrumb_separator),
        )
        self.assertIn('setObjectName("GuideBreadcrumbCurrent")', render)
        self.assertNotIn("setStyleSheet(", view_source)
        self.assertNotIn("_apply_manual_style", view_source)

        self.assertIn("QFrame#GuideBreadcrumb", style_source)
        self.assertIn("QPushButton#GuideBreadcrumbButton", style_source)
        self.assertIn("background: @PANEL;", style_source)
        self.assertIn("border: 1px solid @BORDER;", style_source)
        self.assertIn("background: transparent;", style_source)
        self.assertIn("font-size: @FONT_SMALL;", style_source)
        self.assertIn("min-height: 22px;", style_source)
        self.assertIn("max-height: 22px;", style_source)

    def test_no_permanent_order_picker_and_no_old_section_titles(self):
        build = inspect.getsource(GuideUltimeManualView._build_ui)
        whole = inspect.getsource(GuideUltimeManualView)
        inline = inspect.getsource(GuideUltimeManualView._add_manual_order_choice)
        self.assertNotIn("order_combo", build)
        self.assertNotIn("GuideManualOrderChoice", build)
        self.assertIn("manual_order_choice_required", inline)
        self.assertIn("Choisis ton Ordre Bonta", inline)
        self.assertNotIn("FAIS ÇA ICI", whole)
        self.assertNotIn('"ENSUITE"', whole)


if __name__ == "__main__":
    unittest.main()
