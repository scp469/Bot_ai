"""
Comprehensive verification test suite for all 16 audit fixes.
Tests real logic and edge cases against the actual codebase.
"""
import unittest
import numpy as np
import cv2
import os
import re
from unittest.mock import MagicMock, patch

from czn_bot.states import State, LeftButton
from czn_bot.settings import DEFAULT_AI_CONFIG
from czn_bot.chaos.ai_brain import _normalize_model_name, ChaosAIBrain
from czn_bot.chaos.rules import ChaosRuleManager
from czn_bot.chaos.pathfinder import IslandChoice
from czn_bot.chaos.decisions import ChaosVision, EventChoiceInfo
from czn_bot.chaos.state_machine import ChaosStateMachine
from czn_bot.flows.progress import ProgressFlow
from czn_bot.flows.base import ActionType
from czn_bot.vision.detector import ScreenDetector
from czn_bot.vision.state_classifier import Anchor, StateClassifier, StateSpec, DEFAULT_STATE_SPECS
import tools.package_project as pkg_tool


class TestAuditFixes16(unittest.TestCase):

    # ── Item 1: Model Normalization & Defaults ────────────────────────
    def test_item1_model_normalization(self):
        self.assertEqual(_normalize_model_name("gemini-3.5-flash"), "gemini-2.5-flash")
        self.assertEqual(_normalize_model_name("gemini-3.5-flash-lite"), "gemini-2.5-flash")
        self.assertEqual(_normalize_model_name("gemini-2.5-flash"), "gemini-2.5-flash")
        self.assertEqual(_normalize_model_name("gemini-2.5-pro"), "gemini-2.5-flash")
        self.assertEqual(_normalize_model_name("gemini-2.0-flash"), "gemini-2.0-flash")
        self.assertEqual(_normalize_model_name("gemini-1.5-flash"), "gemini-1.5-flash")
        self.assertEqual(_normalize_model_name(""), "gemini-2.5-flash")
        self.assertEqual(_normalize_model_name(None), "gemini-2.5-flash")
        self.assertEqual(DEFAULT_AI_CONFIG.get("model_name"), "gemini-2.5-flash")

    # ── Item 2: Stall Recovery Continuation ───────────────────────────
    def test_item2_stall_recovery_attempt_continuation(self):
        from czn_bot.runner import BotRunner
        runner = BotRunner(adb_client=MagicMock(), detector=MagicMock())
        runner.enable_recovery = True
        runner.recovery = MagicMock()
        runner._stall_recovered_count = 0

        # Attempt 1 fails to recover -> continue loop
        runner.recovery.attempt_recovery.return_value = (False, State.IN_MATCH)
        res1 = runner._handle_stall(None, State.IN_MATCH, {}, 10.0)
        self.assertTrue(res1)
        self.assertEqual(runner._stall_recovered_count, 1)

        # Attempt 2 fails to recover -> continue loop to stage 3
        res2 = runner._handle_stall(None, State.IN_MATCH, {}, 20.0)
        self.assertTrue(res2)
        self.assertEqual(runner._stall_recovered_count, 2)

        # Attempt 3 fails to recover -> halt and return False
        runner._halt = MagicMock()
        res3 = runner._handle_stall(None, State.IN_MATCH, {}, 30.0)
        self.assertFalse(res3)
        runner._halt.assert_called_once()

    def test_item2_stall_recovery_stage3_success(self):
        from czn_bot.runner import BotRunner
        runner = BotRunner(adb_client=MagicMock(), detector=MagicMock())
        runner.enable_recovery = True
        runner.recovery = MagicMock()
        runner._stall_recovered_count = 2  # Stage 3 is next

        # Stage 3 succeeds! Should reset stall count and return True
        runner.recovery.attempt_recovery.return_value = (True, State.CHAOS_MAP)
        runner._halt = MagicMock()
        res = runner._handle_stall(None, State.IN_MATCH, {}, 30.0)
        self.assertTrue(res)
        self.assertEqual(runner._stall_recovered_count, 0)
        runner._halt.assert_not_called()

    # ── Item 3: Unknown vs Transitioning ──────────────────────────────
    def test_item3_unknown_screen_classification(self):
        detector = ScreenDetector()
        bright_screen = np.full((900, 1600, 3), 180, dtype=np.uint8)
        state, details = detector.detect(bright_screen)
        self.assertEqual(state, State.UNKNOWN)

        dark_screen = np.full((900, 1600, 3), 20, dtype=np.uint8)
        state_dark, details_dark = detector.detect(dark_screen)
        self.assertEqual(state_dark, State.TRANSITIONING)
        self.assertTrue(details_dark.get("dark_cutscene"))

    # ── Item 4: Offline UI scan ───────────────────────────────────────
    def test_item4_offline_ui_scan_with_active_flow(self):
        from czn_bot.runner import BotRunner
        runner = BotRunner(adb_client=MagicMock(), detector=MagicMock())
        mock_choice = EventChoiceInfo(slot=0, name="Choice 1", tap_coord=(375, 765))
        mock_vision = MagicMock()
        mock_vision.extract_event_choices.return_value = [mock_choice]

        runner.active_flow = MagicMock()
        runner.active_flow.vision = mock_vision

        screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        res = runner._scan_unknown_screen_elements(screen)
        self.assertIsNotNone(res)
        name, x, y = res
        self.assertEqual(name, "Ô lựa chọn sự kiện")
        self.assertEqual(x, 375)
        self.assertEqual(y, 765)

    def test_item4_offline_ui_scan_fallback_without_active_flow(self):
        from czn_bot.runner import BotRunner
        runner = BotRunner(adb_client=MagicMock(), detector=MagicMock())
        runner.active_flow = None
        runner.rule_manager = ChaosRuleManager()

        screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        # Should execute without throwing AttributeError on ChaosRuleManager
        res = runner._scan_unknown_screen_elements(screen)
        # On a blank screen without OCR matches, res is None, but no exception was raised
        self.assertIsNone(res)

    def test_item4_chaos_vision_positional_init_safety(self):
        rm = ChaosRuleManager()
        # Even if called positionally, rule_manager is not assigned to ocr
        v = ChaosVision(rm)
        self.assertNotIsInstance(v.ocr, ChaosRuleManager)
        self.assertIsInstance(v.rule_manager, ChaosRuleManager)

    # ── Item 5: StateClassifier Anchor Coordinates ────────────────────
    def test_item5_state_classifier_coords_update(self):
        # Matcher returns 3 anchors:
        # a1 (score 0.88, no coord), a2 (score 0.70, coord 100,100), a3 (score 0.80, coord 200,200)
        def matcher(screen, key, region=None):
            if region == (10, 10, 50, 50):
                return (0.88, None)
            if region == (100, 100, 50, 50):
                return (0.70, (100, 100))
            if region == (200, 200, 50, 50):
                return (0.80, (200, 200))
            return (0.0, None)

        spec = StateSpec(
            state="TEST_STATE",
            anchors=(
                Anchor("btn", (10, 10, 50, 50), 0.60),
                Anchor("btn", (100, 100, 50, 50), 0.60),
                Anchor("btn", (200, 200, 50, 50), 0.60),
            ),
            min_hits=1
        )
        classifier = StateClassifier(specs=[spec], matcher=matcher)
        dummy = np.zeros((900, 1600, 3), dtype=np.uint8)
        res = classifier.classify(dummy)
        # Best coord should be (200, 200) from the 0.80 match, NOT (100, 100) from 0.70
        self.assertEqual(res.best_coords.get("btn"), (200, 200))

    # ── Item 6: POPUP_PAUSE Fallback Anchors ───────────────────────────
    def test_item6_popup_pause_anchors(self):
        specs_by_name = {s.state: s for s in DEFAULT_STATE_SPECS}
        self.assertIn("POPUP_PAUSE", specs_by_name)
        pause_spec = specs_by_name["POPUP_PAUSE"]
        anchor_keys = [a.key for a in pause_spec.anchors]
        self.assertIn("close_x", anchor_keys)
        self.assertIn("modal_close_button", anchor_keys)
        self.assertIn("in_match_check", anchor_keys)

    # ── Item 7: Enum Lookup in 3D Island Detection ────────────────────
    def test_item7_enum_lookup_in_dynamic_islands(self):
        mock_adb = MagicMock()
        mock_det = MagicMock()
        mock_vision = MagicMock()
        mock_brain = MagicMock()
        mock_brain.decide_island.return_value = {"target_island": "bottom", "reason": "Path to Boss"}

        sm = ChaosStateMachine(adb=mock_adb, detector=mock_det, vision=mock_vision, brain=mock_brain)
        dummy = np.zeros((900, 1600, 3), dtype=np.uint8)

        with patch("czn_bot.vision.map_reader.detect_3d_island_coords") as mock_3d, \
             patch("czn_bot.vision.map_reader.parse_chaos_minimap") as mock_parse, \
             patch("czn_bot.chaos.pathfinder.select_best_island") as mock_select:
            mock_parse.return_value = (["root1"], {"root1": []}, {"root1": "sword"}, ["root1"])
            mock_select.return_value = (IslandChoice.BOTTOM, {})
            mock_3d.return_value = {IslandChoice.BOTTOM: (1350, 680)}

            sm.handle_map_choosing(dummy, {})
            mock_adb.tap_location.assert_called_with(1350, 680, random_offset=True)

    # ── Item 8: Currency Regex Parsing with Thousand Separators ───────
    def test_item8_currency_thousand_separators(self):
        v = ChaosVision(rule_manager=None)
        c1 = v._parse_event_choice(0, "Choice 1", (100, 100), "Nhận 1,500 credits để tăng sức mạnh", None)
        self.assertEqual(c1.cost_credits, 1500)

        c2 = v._parse_event_choice(1, "Choice 2", (200, 100), "Chi tiêu 2.500 credits", None)
        self.assertEqual(c2.cost_credits, 2500)

        mock_ocr = MagicMock()
        mock_ocr.read_text.return_value = "Credits: 1,500"
        v2 = ChaosVision(ocr_service=mock_ocr)
        dummy = np.zeros((900, 1600, 3), dtype=np.uint8)
        res = v2.extract_resources(dummy)
        self.assertEqual(res.credits, 1500)

    # ── Item 9: Toast PowerShell Quoting & Timeout ─────────────────────
    def test_item9_toast_single_quote_escaping(self):
        from czn_bot.notifier import Notifier
        n = Notifier(enable_toast=True)
        title = "ChaosBot's Alert: Don't panic"
        text = "It's all good 'n fine"

        with patch("subprocess.run") as mock_run, patch("sys.platform", "win32"):
            res = n.send_windows_toast(title, text)
            self.assertTrue(res)
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            self.assertEqual(kwargs.get("timeout"), 5.0)
            ps_cmd = args[0][3]
            self.assertIn("ChaosBot''s Alert: Don''t panic", ps_cmd)
            self.assertIn("It''s all good ''n fine", ps_cmd)

    # ── Item 10: Packaging Exclusion of Sensitive Files ───────────────
    def test_item10_package_sensitive_exclusions(self):
        self.assertFalse(pkg_tool.should_include_file(".env"))
        self.assertFalse(pkg_tool.should_include_file(".env.local"))
        self.assertFalse(pkg_tool.should_include_file(".env.production"))
        self.assertFalse(pkg_tool.should_include_file("ai_config.json"))
        self.assertFalse(pkg_tool.should_include_file("subfolder/.env"))
        self.assertFalse(pkg_tool.should_include_file("subfolder/ai_config.json"))
        self.assertFalse(pkg_tool.should_include_file(".vscode/settings.json"))
        self.assertFalse(pkg_tool.should_include_file(".antigravity/state.json"))
        self.assertTrue(pkg_tool.should_include_file("src/czn_bot/runner.py"))
        self.assertTrue(pkg_tool.should_include_file(".env.example"))

    # ── Item 11: Prevent Live Gemini API Calls in Tests ────────────────
    def test_item11_test_notifier_disables_chaos_ai(self):
        import inspect
        from tests import test_notifier
        src = inspect.getsource(test_notifier.TestBotEngineNotifierIntegration.setUp)
        self.assertIn("self.engine.enable_chaos_ai = False", src)

    # ── Item 12: Hidden Imports in PyInstaller ────────────────────────
    def test_item12_hidden_imports(self):
        from tools import build_exe
        import inspect
        src = inspect.getsource(build_exe.build_executable)
        for expected in ["apps", "apps.cli", "apps.gui", "czn_bot.vision.state_classifier", "czn_bot.chaos.state_machine"]:
            self.assertIn(f'"{expected}"', src)

    # ── Item 13: Requirements Check ───────────────────────────────────
    def test_item13_requirements(self):
        with open("requirements.txt", "r", encoding="utf-8") as f:
            reqs = f.read()
        self.assertIn("customtkinter>=6.0.0", reqs)
        self.assertNotIn("google-genai", reqs)
        self.assertNotIn("requests", reqs)

    # ── Item 14: LOGS_DIR in Runner ───────────────────────────────────
    def test_item14_runner_logs_dir(self):
        import inspect
        from czn_bot import runner
        src = inspect.getsource(runner.BotRunner._cleanup_unknown_screenshots)
        self.assertIn("logs_dir: str = LOGS_DIR", src)
        src_stall = inspect.getsource(runner.BotRunner._handle_stall)
        self.assertIn("os.makedirs(LOGS_DIR", src_stall)

    # ── Item 15: max_stages in ProgressFlow ────────────────────────────
    def test_item15_progress_flow_max_stages_flag(self):
        flow = ProgressFlow(max_stages=3)
        flow.stages_done = 3
        act = flow.handle(State.MATCH_DONE, {"left_button": LeftButton.NEXT_MISSION}, None)
        self.assertEqual(act.type, ActionType.STOP)
        self.assertTrue(act.extra.get("max_stages"))

    # ── Item 16: Stale Templates Deleted & Clean Code ─────────────────
    def test_item16_stale_templates_deleted(self):
        for stale in ["card_rules.json", "event_rules.json", "equipment_rules.json"]:
            path = os.path.join("data", "templates", stale)
            self.assertFalse(os.path.exists(path), f"{path} should be deleted")

    def test_item16_obfuscation_methods_deleted(self):
        import inspect
        from czn_bot.chaos import rules
        src = inspect.getsource(rules)
        self.assertNotIn("_encrypt_key", src)
        self.assertNotIn("_decrypt_key", src)
        self.assertNotIn("_OBFUSCATION_SALT", src)

    def test_item16_gui_duplicate_var_deleted(self):
        with open("apps/gui.py", "r", encoding="utf-8") as f:
            content = f.read()
        matches = re.findall(r"self\.auto_pick_epiphany_var\s*=", content)
        self.assertEqual(len(matches), 1, "self.auto_pick_epiphany_var defined more than once in apps/gui.py")


if __name__ == "__main__":
    unittest.main()
