from __future__ import annotations

import unittest

from app.network.deobfs_report import (
    DeobfuscationReportError,
    ankama_type_alias,
    parse_deobfuscation_report,
)


class NetworkDeobfuscationReportTests(unittest.TestCase):
    def report_text(self) -> str:
        return """Message Matches Report
======================

Obf  →  Orig                       File                 [conf:   0.00%]
-----------------------------------------------------------------------
irj  →  QuestValidatedMessage      quest.proto          [conf: 100.00%]
abc  →  ???                        ???                  [conf: 100.00%]
    Possible matches: FooMessage, BarMessage

Total matches: 2
"""

    def test_definitive_and_uncertain_rows_are_separated(self) -> None:
        report = parse_deobfuscation_report(self.report_text())
        self.assertEqual(report.total_declared, 2)
        self.assertEqual(len(report.matches), 1)
        match = report.definitive_for_alias("irj")
        self.assertIsNotNone(match)
        self.assertEqual(match.original_message, "QuestValidatedMessage")
        self.assertEqual(match.original_file, "quest.proto")
        self.assertEqual(match.confidence, 100.0)
        self.assertIsNone(report.definitive_for_alias("abc"))
        self.assertEqual(report.uncertain_aliases, ("abc",))

    def test_minimum_confidence_is_enforced_by_lookup(self) -> None:
        text = """Message Matches Report
======================

Obf  →  Orig          File          [conf:   0.00%]
---------------------------------------------------
a    →  SomeMessage   some.proto    [conf:  99.50%]

Total matches: 1
"""
        report = parse_deobfuscation_report(text)
        self.assertIsNone(report.definitive_for_alias("a"))
        self.assertIsNotNone(report.definitive_for_alias("a", minimum_confidence=99.0))

    def test_truncated_or_duplicate_alias_report_is_rejected(self) -> None:
        truncated = self.report_text().replace("Total matches: 2", "Total matches: 3")
        with self.assertRaises(DeobfuscationReportError):
            parse_deobfuscation_report(truncated)

        duplicate = """Message Matches Report
======================

a → One one.proto [conf: 100.00%]
a → Two two.proto [conf: 100.00%]
Total matches: 2
"""
        with self.assertRaises(DeobfuscationReportError):
            parse_deobfuscation_report(duplicate)

    def test_missing_total_or_partial_uncertainty_is_rejected(self) -> None:
        with self.assertRaises(DeobfuscationReportError):
            parse_deobfuscation_report("a → One one.proto [conf: 100.00%]")
        with self.assertRaises(DeobfuscationReportError):
            parse_deobfuscation_report(
                "a → ??? one.proto [conf: 100.00%]\nTotal matches: 1\n"
            )

    def test_type_url_alias_requires_single_ankama_component(self) -> None:
        self.assertEqual(ankama_type_alias("ankama.com/irj"), "irj")
        self.assertEqual(ankama_type_alias("other/irj"), "")
        self.assertEqual(ankama_type_alias("ankama.com/a/b"), "")
        self.assertEqual(ankama_type_alias("ankama.com/"), "")


if __name__ == "__main__":
    unittest.main()
