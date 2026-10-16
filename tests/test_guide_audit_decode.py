from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtGui import QImage
from app.modules.encyclopedia.tools import audit_quests_guides as audit


class GuideImageDecodeAuditTests(unittest.TestCase):
    def test_real_png_and_corrupt_copy_have_different_decode_verdicts(self):
        with tempfile.TemporaryDirectory() as temp:
            valid = Path(temp) / "valid.png"
            corrupt = Path(temp) / "corrupt.png"
            raster = QImage(64, 32, QImage.Format_ARGB32)
            raster.fill(0xFF5476AA)
            self.assertTrue(raster.save(str(valid), "PNG"))
            corrupt.write_bytes(valid.read_bytes()[:40])
            self.assertTrue(audit.is_exploitable_image(valid))
            self.assertTrue(audit.is_exploitable_image(corrupt))
            self.assertTrue(audit.is_exploitable_image(valid, decode=True))
            self.assertFalse(audit.is_exploitable_image(corrupt, decode=True))
            with patch.object(audit, "image_files", return_value=[]):
                signature, _ = audit.audit_images(None, [], {str(valid), str(corrupt)})
                decoded, issues = audit.audit_images(None, [], {str(valid), str(corrupt)}, decode_images=True)
            self.assertEqual(signature["image_validation_level"], "SIGNATURE_ONLY")
            self.assertEqual(signature["bad_format_referenced_images"], 0)
            self.assertEqual(decoded["image_validation_level"], "DECODE")
            self.assertEqual(decoded["bad_format_referenced_images"], 1)
            self.assertTrue(any(issue.field == "image_decode" and issue.severity == "critical" for issue in issues))
