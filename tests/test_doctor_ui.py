from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor import build_parser
from tools.atlas_doctor_lib.doctor_ui import required_assertions, run_ui


class ScreenshotRasterOracleTests(unittest.TestCase):
    """Synthetic real pixel buffers, not QFont claims or predeclared PASS."""

    @staticmethod
    def pixels(boxes=24, *, stride_pad=4):
        width, height = 264, 90
        stride = width + stride_pad
        data = bytearray([13] * (stride * height))
        for i in range(boxes):
            x = 4 + (i % 18) * 14
            y = 5 + (i // 18) * 17
            for dx in range(8):
                data[y * stride + x + dx] = 220
                data[(y + 7) * stride + x + dx] = 220
            for dy in range(1, 7):
                data[(y + dy) * stride + x] = 220
                data[(y + dy) * stride + x + 7] = 220
        return bytes(data), width, height, stride

    def test_archived_windows_screenshot_with_real_to_fu_glyphs_fails(self):
        """Historic real SHA 0b8ffdc2 screenshot, not hand-drawn synthetic boxes.

        Crop x=0..419 / y=0..74 from `001-achievement-detail.png`:
        https://github.com/r9327/Dof-Atlas/actions/runs/39055013074
        Artifact 12109118441. Full PNG SHA256:
        39de95156af89b204796b7b1f79b53e3158726ca5308a6d4d429598e16f61998.
        The compact grayscale crop is losslessly zlib+b85 packed; it is only
        used as a regression witness, never substituted for a new Qt capture.
        """
        import base64
        import hashlib
        import zlib
        from tools.atlas_doctor_lib.ui_raster_oracle import detect_replacement_squares

        stored = (
            "c-rmTK}y3w6o>J33Q}SyL}O_!DHMW(i*BVB+_>-@Lcs&rjo{83^akbtJ)3KVq*hWF()^#i((hZ;Sq;Pc5uFN&A|fIpA|fK918a~MLDFQ{v)Xa7T$PgE7B}KES`MHVibI;lT}i#{a(rU3<5fAIjS@-M4^J<d^o*7RsEva3l;^=>$MQ50cK@zEquBuJr!v)^@ob>qaWPM%-94($Xf=S!C>NhL&GkDjXIi7%=iJUnI)KWk5dT(=3;m9(k=AImDq=Gu=>RPL9DNn!J5I|)TsiI9r5wP)7zMpizz8FZj?`#f)neH^qHf2H(MMH_Wz(qr8BGVUZWwJp_gwBAQMTi^(e`uC<&IJ7Gnx(nBaAS@2qTO<8gZ|4f3M^F5#M1k!U!XbFv18Uj4;9oBaAS@2qTOz!st&%@(#>sEH3DGG%y<5r5pe+^$-ye5fS}+nZY~Oq<gPCiaL2ejl1Nq4beqN8HR78PGA(?jdGqM??zdlNq9HnG4gLzaHDf?#Ek(X!szIXUh7ypS^sAA;|FU8Ym6{rjS)tyF=D;15%*sAcW>hV41^Izgb`tc5t$iHdQ8H*(J*5Ye)|M7$)AD"
        )
        real_pixels = zlib.decompress(base64.b85decode(stored))
        self.assertEqual(len(real_pixels), 420 * 75)
        self.assertEqual(
            hashlib.sha256(real_pixels).hexdigest(),
            "86773ec263a9c269a800c7dd53c1662e838575f5106975ee171a2c07fe37af2d",
        )
        report = detect_replacement_squares(real_pixels, 420, 75, 420)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["reason"], "REPEATED_HOLLOW_SQUARE_GLYPHS")
        self.assertGreaterEqual(report["box_count"], 60)

    def test_real_grayscale_hollow_box_pattern_is_visual_failure(self):
        from tools.atlas_doctor_lib.ui_raster_oracle import detect_replacement_squares

        frame, width, height, stride = self.pixels(24)
        result = detect_replacement_squares(frame, width, height, stride)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reason"], "REPEATED_HOLLOW_SQUARE_GLYPHS")
        self.assertEqual(result["box_count"], 24)
        self.assertEqual(result["sizes"], {8: 24})
        self.assertTrue(result["examples"])

    def test_legitimate_few_control_squares_do_not_trigger_false_failure(self):
        from tools.atlas_doctor_lib.ui_raster_oracle import detect_replacement_squares

        frame, width, height, stride = self.pixels(4)
        result = detect_replacement_squares(frame, width, height, stride)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["box_count"], 4)
        # A normal glyph stroke is not a hollow square substitution.
        mutable = bytearray(frame)
        for i in range(24):
            x = 4 + (i % 18) * 14
            y = 5 + (i // 18) * 17
            for dy in range(8):
                mutable[(y + dy) * stride + x + 3] = 220
        self.assertEqual(
            detect_replacement_squares(bytes(mutable), width, height, stride)["status"],
            "PASS",
        )

    def test_truncated_or_oversized_raster_fails_closed(self):
        from tools.atlas_doctor_lib.ui_raster_oracle import detect_replacement_squares

        frame, width, height, stride = self.pixels(24)
        for args in (
            (frame[:100], width, height, stride),
            (frame, width, height, width - 1),
            (frame, 12000, 12000, 12000),
        ):
            self.assertEqual(detect_replacement_squares(*args)["status"], "BLOCKED")


class DoctorUiCoordinatorTests(unittest.TestCase):
    def test_cli_is_opt_in_bounded_and_preserves_historical_capture_scenarios(self):
        parser = build_parser()
        args = parser.parse_args(["ui", "guides"])
        self.assertEqual(args.mode, "all")
        self.assertEqual(args.repeats, 2)
        self.assertIsNone(args.select)
        for scenario in ("qt", "equipment", "encyclopedia", "webengine"):
            self.assertEqual(parser.parse_args(["capture-ui", scenario]).scenario, scenario)
        with self.assertRaises(SystemExit):
            parser.parse_args(["ui", "arbitrary-module"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["ui", "guides", "--repeats", "6"])

    def test_selected_scenarios_have_fixed_mandatory_assertions(self):
        required = required_assertions(["guides-success", "guides-lanyel", "guide-quests"])
        self.assertEqual(len(required), len(set(required)))
        self.assertIn("guides-lanyel/combat", required)
        self.assertIn("guides-success/geometry-3-960", required)
        self.assertIn("guide-quests/dofus_sylvestre-quest-1", required)
        success = required_assertions(["achievement-detail"])
        self.assertEqual(
            success,
            ["achievement-detail/first-open-lazy",
             "achievement-detail/click-opens-detail",
             "achievement-detail/geometry-1200",
             "achievement-detail/geometry-960",
             "session/qt-exceptions",
             "session/glyph-rendering"],
        )
        self.assertNotIn("achievement-detail/click-opens-detail",
                         required_assertions(["validator-smoke"]))
        smoke = required_assertions(["validator-smoke"])
        self.assertNotIn("validator-smoke/guide-return", smoke)
        self.assertIn("validator-smoke/manual-persist", smoke)

    def test_timeout_or_native_crash_without_report_is_blocked_with_manifest_and_log(self):
        for effect in (subprocess.TimeoutExpired("worker", 1), subprocess.CompletedProcess([], -11)):
            with self.subTest(effect=type(effect).__name__), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                with patch("tools.atlas_doctor_lib.doctor_ui.git_value", return_value="a" * 40), \
                     patch("tools.atlas_doctor_lib.doctor_ui.subprocess.run", side_effect=effect if isinstance(effect, Exception) else None,
                           return_value=effect):
                    report = run_ui(root, scenarios=["validator-smoke"], timeout=1)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertFalse(report["tests_executed"])
                session = Path(report["session_path"])
                self.assertTrue((session / "worker.log").exists())
                manifest = json.loads((session / "manifest.json").read_text())
                self.assertIn("ui_verdict.json", manifest["artifacts"])

    def test_unknown_scenario_and_out_of_bounds_inputs_rejected_before_process(self):
        with tempfile.TemporaryDirectory() as folder:
            for kwargs in ({"scenarios": ["malicious.module"]}, {"repeats": 0}, {"timeout": 241}):
                with self.assertRaises(ValueError):
                    run_ui(Path(folder), **kwargs)
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
