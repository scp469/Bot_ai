"""
Unit tests specifically verifying the 3 major operational bug fixes:
1. Hybrid OCR high-confidence bypass & 2-strike Force Tap fallback.
2. OpenCV-first priority, AI Stale Frame Guard, and removal of AI 1-frame bypass.
3. IN_MATCH heuristic hardening (rejecting loading screen noise & Chaos map minimap).
"""
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from czn_bot.states import State, Mode
from czn_bot.runner import BotRunner
from czn_bot.vision.detector import ScreenDetector


class TestFixesVerification(unittest.TestCase):
    def setUp(self):
        self.mock_adb = MagicMock()
        self.detector = ScreenDetector()
        self.engine = BotRunner(adb_client=self.mock_adb, detector=self.detector)
        self.engine.enable_hybrid_verification = True
        self.engine.enable_chaos_ai = False

    # ── Bug 1: Hybrid OCR High-Confidence Bypass & 2-Strike Force Tap ──

    def test_hybrid_ocr_high_confidence_bypass(self):
        """When template match score is >= 0.88, OCR check is bypassed and tap succeeds immediately."""
        screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        # Even with wrong or missing OCR text, score=0.95 bypasses OCR check
        result = self.engine._execute_tap(
            "Bấm Obtain", 1380, 830,
            screen=screen,
            expected_words=["obtain", "nhận"],
            score=0.95
        )
        self.assertTrue(result)
        self.mock_adb.tap.assert_called_once_with(1380, 830)
        self.assertEqual(self.engine.actions_done, 1)

    def test_hybrid_ocr_two_strike_force_tap_fallback(self):
        """
        Strike 1: OCR mismatch rejects tap and returns True (waiting for next frame).
        Strike 2: Second consecutive OCR rejection forces tap to prevent endless stall.
        """
        screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        self.engine._ocr_reject_count = 0

        # Strike 1: Rejection
        r1 = self.engine._execute_tap(
            "Bấm Confirm", 1440, 830,
            screen=screen,
            expected_words=["confirm", "xác nhận"],
            score=0.75
        )
        self.assertTrue(r1)
        self.assertEqual(self.engine._ocr_reject_count, 1)
        self.mock_adb.tap.assert_not_called()
        self.assertEqual(self.engine.actions_done, 0)

        # Strike 2: Force tap executed!
        r2 = self.engine._execute_tap(
            "Bấm Confirm", 1440, 830,
            screen=screen,
            expected_words=["confirm", "xác nhận"],
            score=0.75
        )
        self.assertTrue(r2)
        self.assertEqual(self.engine._ocr_reject_count, 0)
        self.mock_adb.tap.assert_called_once_with(1440, 830)
        self.assertEqual(self.engine.actions_done, 1)

    # ── Bug 2: OpenCV-First Priority & AI Stale Frame Guard ───────────

    def test_opencv_first_priority_over_ai(self):
        """When OpenCV detects a valid state, AI Vision is NOT called."""
        self.engine.enable_ai_vision_detection = True
        self.engine.enable_chaos_ai = True
        self.engine.rule_manager.get_api_key = MagicMock(return_value="test_key")

        mock_brain = MagicMock()
        self.engine.chaos_brain = mock_brain

        # Screen where detector finds a valid state (e.g. mock detector detect)
        self.engine.detector.detect = MagicMock(return_value=(State.CHAOS_SAFE_ZONE, {"score": 0.95}))

        dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        state, details = self.engine._detect_state(dummy_screen)

        self.assertEqual(state, State.CHAOS_SAFE_ZONE)
        mock_brain.detect_state_with_ai.assert_not_called()

    def test_ai_stale_frame_guard_discards_outdated_result(self):
        """When AI takes >1.5s and screen changes >15%, stale AI result is discarded."""
        self.engine.enable_ai_vision_detection = True
        self.engine.enable_chaos_ai = True
        self.engine.rule_manager.get_api_key = MagicMock(return_value="test_key")

        # OpenCV returns UNKNOWN
        self.engine.detector.detect = MagicMock(return_value=(State.UNKNOWN, {}))

        # AI mock that simulates 2.0s delay and returns an old state
        mock_brain = MagicMock()
        def delayed_ai(*args, **kwargs):
            import time
            time.sleep(1.6)
            return State.CHAOS_MAP, {"ai_detected": True, "confidence": 0.95}

        mock_brain.detect_state_with_ai.side_effect = delayed_ai
        self.engine.chaos_brain = mock_brain

        initial_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        # Screen changes drastically while AI was thinking
        drastically_changed_screen = np.full((900, 1600, 3), 200, dtype=np.uint8)
        self.mock_adb.screencap.return_value = drastically_changed_screen

        # Second detect call on current_screen should be used
        def re_detect(screen):
            if np.array_equal(screen, drastically_changed_screen):
                return State.POPUP_EFFECT, {"re_detected": True}
            return State.UNKNOWN, {}

        self.engine.detector.detect.side_effect = re_detect

        state, details = self.engine._detect_state(initial_screen)
        # Outdated CHAOS_MAP should be discarded in favor of current frame re-detection
        self.assertEqual(state, State.POPUP_EFFECT)
        self.assertTrue(details.get("re_detected"))

    # ── Bug 3: IN_MATCH Heuristic Hardening ────────────────────────────

    def test_in_match_heuristic_rejects_loading_speck(self):
        """Small green noise specks (<100px width) on loading screens are NOT detected as IN_MATCH."""
        screen = np.full((900, 1600, 3), 30, dtype=np.uint8)
        # Small green patch at top (only 30px wide, not a real team HP bar)
        screen[10:30, 200:230] = [0, 200, 0]
        self.assertFalse(self.detector._check_in_match_heuristic(screen))

    def test_in_match_heuristic_rejects_chaos_map_with_minimap(self):
        """Screen with Chaos minimap elements at bottom-left is NOT detected as IN_MATCH."""
        screen = np.full((900, 1600, 3), 30, dtype=np.uint8)
        # Large green bar at top
        screen[10:30, 100:450] = [0, 200, 0]
        # Active minimap elements at bottom-left [680:890, 10:270]
        screen[700:850, 30:250] = [180, 180, 50]  # Cyan / map paths
        self.assertFalse(self.detector._check_in_match_heuristic(screen))

    def test_in_match_heuristic_accepts_genuine_team_hp_bar(self):
        """Long horizontal green bar (w >= 100, aspect >= 3.0) without map elements is accepted."""
        screen = np.full((900, 1600, 3), 40, dtype=np.uint8)
        # Genuine team HP bar: w=300px, h=20px, aspect=15.0
        screen[10:30, 150:450] = [0, 220, 0]
        self.assertTrue(self.detector._check_in_match_heuristic(screen))

    # ── Checklist Items 1-10 Verification ─────────────────────────────

    @patch("czn_bot.flows.chaos.get_team_hp", return_value=(0.85, False))
    @patch("czn_bot.flows.chaos.parse_chaos_minimap", return_value=([], {}, {}, []))
    def test_item1_minimap_transition_retries(self, mock_parse, mock_hp):
        """Item 1: When parse_chaos_minimap is empty, wait for transition up to max_map_retries."""
        from czn_bot.flows.chaos import ChaosFlow
        from czn_bot.flows.base import ActionType
        flow = ChaosFlow(max_map_retries=3)
        screen = np.zeros((900, 1600, 3), dtype=np.uint8)

        # Retry 1 & 2: WAIT
        a1 = flow.handle(State.CHAOS_MAP, {}, screen)
        self.assertEqual(a1.type, ActionType.WAIT)
        a2 = flow.handle(State.CHAOS_MAP, {}, screen)
        self.assertEqual(a2.type, ActionType.WAIT)

        # Retry 3: STOP
        a3 = flow.handle(State.CHAOS_MAP, {}, screen)
        self.assertEqual(a3.type, ActionType.STOP)
        self.assertIn("3 lần thử", a3.reason)

    def test_item2_explicit_stall_timeouts(self):
        """Item 2: Watchdog uses specific timeouts (IN_MATCH 300s, EPIPHANY 60s, STORY 90s)."""
        from czn_bot.constants import STATE_STALL_TIMEOUTS
        self.assertEqual(STATE_STALL_TIMEOUTS.get(State.IN_MATCH, STATE_STALL_TIMEOUTS.get("IN_MATCH")), 300.0)
        self.assertEqual(STATE_STALL_TIMEOUTS.get(State.CHAOS_CHOOSE_EPIPHANY, STATE_STALL_TIMEOUTS.get("CHAOS_CHOOSE_EPIPHANY")), 60.0)
        self.assertEqual(STATE_STALL_TIMEOUTS.get(State.STORY_DIALOGUE, STATE_STALL_TIMEOUTS.get("STORY_DIALOGUE")), 90.0)

    def test_item3_epiphany_subtypes_in_detector(self):
        """Item 3: ScreenDetector sets specific sub-type details for choose_fate, remove_card, etc."""
        # Mock match to simulate choose_fate
        with patch.object(self.detector, "match") as mock_match:
            def side_effect(screen, tpl_name, **kwargs):
                if tpl_name == "choose_fate_title":
                    return 0.85, (650, 810)
                return 0.20, None
            mock_match.side_effect = side_effect

            screen = np.zeros((900, 1600, 3), dtype=np.uint8)
            st, details = self.detector.detect(screen)
            self.assertEqual(st, State.CHAOS_CHOOSE_EPIPHANY)
            self.assertEqual(details.get("type"), "choose_fate")

    def test_item4_safe_zone_always_heals(self):
        """Item 4: Safe Zone flow always chooses Rest and confirms heal, never Skip."""
        from czn_bot.flows.chaos import ChaosFlow
        from czn_bot.coords import TAP_COORDS
        flow = ChaosFlow()
        screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        act = flow.handle(State.CHAOS_SAFE_ZONE, {}, screen)
        self.assertEqual(act.x, TAP_COORDS["chaos_safe_zone_rest"][0])
        self.assertEqual(act.y, TAP_COORDS["chaos_safe_zone_rest"][1])
        # Verifies confirm tap is present
        extra = act.extra.get("extra_actions", [])
        self.assertTrue(any(item[1] == TAP_COORDS["chaos_safe_zone_confirm"] for item in extra))

    def test_item6_chaos_state_machine_safe_zone_always_heals(self):
        """Item 6: Legacy ChaosStateMachine also heals team in Safe Zone instead of skipping."""
        from czn_bot.chaos.state_machine import ChaosStateMachine
        from czn_bot.coords import TAP_COORDS
        sm = ChaosStateMachine()
        mock_adb = MagicMock()
        sm.adb = mock_adb
        sm.handle_event(np.zeros((900, 1600, 3), dtype=np.uint8), {"type": "safe_zone"})
        # Must tap Rest and Confirm, never Skip
        mock_adb.tap_location.assert_any_call(*TAP_COORDS["chaos_safe_zone_rest"], random_offset=True)
        mock_adb.tap_location.assert_any_call(*TAP_COORDS["chaos_safe_zone_confirm"], random_offset=True)


if __name__ == "__main__":
    unittest.main()

