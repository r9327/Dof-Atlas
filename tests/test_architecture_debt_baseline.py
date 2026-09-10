from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.source_guardrails import (
    baseline_keys,
    format_unexpected,
    legacy_import_violations,
    read_source,
    runtime_patch_violations,
    runtime_version_violations,
)
from tests.test_character_identity_guardrails import KNOWN_SLOT_BUSINESS_DEBT


ROOT = Path(__file__).resolve().parents[1]


LEGACY_IMPORT_BASELINE: tuple[str, ...] = ()

RUNTIME_PATCH_BASELINE: tuple[str, ...] = ()

RUNTIME_VERSION_BASELINE = (
)

REMOVED_PAGE_VARIANTS = (
    "app.pages.home_optimized_page",
    "app.pages.organizer_lazy_page",
)


class ArchitectureDebtBaselineTests(unittest.TestCase):
    def assert_matches_baseline(self, actual, expected) -> None:
        actual_keys = baseline_keys(actual)
        expected_keys = tuple(sorted(expected))
        unexpected = [violation for violation in actual if violation.baseline_key not in expected]
        self.assertEqual(
            expected_keys,
            actual_keys,
            "La dette architecturale courante ne correspond plus a la baseline. "
            "Retirer les exceptions resolues ou refuser les nouvelles violations.\n"
            + format_unexpected(unexpected or actual),
        )

    def test_existing_legacy_imports_are_an_exact_closed_baseline(self) -> None:
        self.assert_matches_baseline(legacy_import_violations(ROOT), LEGACY_IMPORT_BASELINE)

    def test_existing_runtime_patches_are_an_exact_closed_baseline(self) -> None:
        self.assert_matches_baseline(runtime_patch_violations(ROOT), RUNTIME_PATCH_BASELINE)

    def test_existing_runtime_versions_are_an_exact_closed_baseline(self) -> None:
        self.assert_matches_baseline(runtime_version_violations(ROOT), RUNTIME_VERSION_BASELINE)

    def test_baseline_keys_are_unique_in_every_category(self) -> None:
        baselines = {
            "legacy configuree": LEGACY_IMPORT_BASELINE,
            "legacy generee": baseline_keys(legacy_import_violations(ROOT)),
            "runtime patches configures": RUNTIME_PATCH_BASELINE,
            "runtime patches generes": baseline_keys(runtime_patch_violations(ROOT)),
            "versions runtime configurees": RUNTIME_VERSION_BASELINE,
            "versions runtime generees": baseline_keys(runtime_version_violations(ROOT)),
            "identite metier legacy": KNOWN_SLOT_BUSINESS_DEBT,
        }
        for category, keys in baselines.items():
            with self.subTest(category=category):
                duplicates = sorted({key for key in keys if keys.count(key) > 1})
                self.assertEqual(
                    [],
                    duplicates,
                    f"Cles dupliquees dans la baseline {category}: {duplicates}",
                )

    def test_removed_page_variants_are_not_imported(self) -> None:
        offenders: list[str] = []
        for source in sorted((ROOT / "app").rglob("*.py")):
            text = read_source(source)
            for module_name in REMOVED_PAGE_VARIANTS:
                if module_name in text:
                    offenders.append(f"{source.relative_to(ROOT)} -> {module_name}")
        self.assertEqual(
            [],
            offenders,
            "Les variantes de pages supprimees ne doivent pas revenir dans le graphe d'import.",
        )

    def test_source_reader_accepts_plain_utf8_and_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plain = root / "plain.py"
            bom = root / "bom.py"
            plain.write_text("value = 'plain'\n", encoding="utf-8")
            bom.write_text("value = 'bom'\n", encoding="utf-8-sig")
            self.assertEqual("value = 'plain'\n", read_source(plain))
            self.assertEqual("value = 'bom'\n", read_source(bom))

    def test_scanners_report_new_debt_with_file_line_and_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "app"
            app.mkdir()
            source = app / "optimized_new_page_v7.py"
            source.write_text(
                "from app.views.guides_view_legacy import GuidesView\n"
                "def replacement(): pass\n"
                "def install_extra_runtime_patch(): pass\n"
                "GuidesView.render = replacement\n"
                "class PageV7: pass\n",
                encoding="utf-8-sig",
            )

            legacy = legacy_import_violations(root)
            patches = runtime_patch_violations(root)
            versions = runtime_version_violations(root)

            self.assertEqual(1, len(legacy), format_unexpected(legacy))
            self.assertEqual(2, len(patches), format_unexpected(patches))
            self.assertEqual(2, len(versions), format_unexpected(versions))
            diagnostics = format_unexpected([*legacy, *patches, *versions])
            self.assertIn("app/optimized_new_page_v7.py ligne 1", diagnostics)
            self.assertIn("GuidesView.render", diagnostics)
            self.assertIn("class:PageV7", diagnostics)

if __name__ == "__main__":
    unittest.main()
