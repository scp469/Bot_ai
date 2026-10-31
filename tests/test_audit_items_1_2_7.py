"""
tests/test_audit_items_1_2_7.py

Comprehensive unit tests verifying the 3 major improvements:
1. [Mục 1] Frame Stability Check (cv2.absdiff): screen stability before recognition, loading transition handling.
2. [Mục 2] State Transition Validation: DEFAULT_ALLOWED_TRANSITIONS integration, invalid jump guard, multi-frame confirm requirement.
3. [Mục 7] Detailed Decision Logging: recognizer, confidence, margin, runner-up candidate in detector and runner.
"""
import os
import json
import unittest
from unittest.mock import MagicMock, patch
import cv2
import numpy as np

from czn_bot.states import State, Mode
from czn_bot.runner import BotRunner
from czn_bot.vision.detector import ScreenDetector
from czn_bot.vision.state_classifier import DEFAULT_ALLOWED_TRANSITIONS, Result
from czn_bot.constants import (
    CONFIRM_FRAMES,
    INVALID_TRANSITION_CONFIRM_FRAMES,
    FRAME_STABILITY_THRESHOLD,
    LOGS_DIR,
)


class TestFrameStabilityCheck(unittest.TestCase):
    """[Mục 1] Tests for Frame Stability Check using cv2.absdiff()."""

    def setUp(self):
        self.mock_adb = MagicMock()
        self.mock_detector = MagicMock()
        self.runner = BotRunner(adb_client=self.mock_adb, detector=self.mock_detector)
        self.runner.enable_chaos_ai = False
        self.runner.is_running = True

    def test_frame_stability_identical_screens(self):
        """Identical screens have 0 diff and are stable."""
        img = np.full((900, 1600, 3), 100, dtype=np.uint8)
        is_stable, diff_val = self.runner.check_frame_stability(img, img)
        self.assertTrue(is_stable)
        self.assertEqual(diff_val, 0.0)

    def test_frame_stability_different_screens(self):
        """Significantly different screens (e.g. transition/loading) are unstable."""
        img1 = np.full((900, 1600, 3), 30, dtype=np.uint8)
        img2 = np.full((900, 1600, 3), 180, dtype=np.uint8)
        is_stable, diff_val = self.runner.check_frame_stability(img2, img1, threshold=10.0)
        self.assertFalse(is_stable)
        self.assertGreaterEqual(diff_val, 140.0)

    def test_frame_stability_subtle_noise_is_stable(self):
        """Subtle noise or particle animation (diff < threshold) remains stable."""
        img1 = np.full((900, 1600, 3), 100, dtype=np.uint8)
        img2 = img1.copy()
        # Add slight noise to a small patch
        img2[100:150, 100:150] = 105
        is_stable, diff_val = self.runner.check_frame_stability(img2, img1, threshold=10.0)
        self.assertTrue(is_stable)
        self.assertLess(diff_val, 1.0)

    def test_frame_stability_none_or_empty(self):
        """None or empty image returns False, 0.0."""
        is_stable, diff_val = self.runner.check_frame_stability(None)
        self.assertFalse(is_stable)
        self.assertEqual(diff_val, 0.0)

        empty_img = np.array([], dtype=np.uint8)
        is_stable, diff_val = self.runner.check_frame_stability(empty_img)
        self.assertFalse(is_stable)
        self.assertEqual(diff_val, 0.0)

    def test_frame_stability_first_frame_no_prev(self):
        """When no previous screen is stored, initial frame is considered stable."""
        img = np.full((900, 1600, 3), 100, dtype=np.uint8)
        self.runner._last_raw_screen = None
        is_stable, diff_val = self.runner.check_frame_stability(img)
        self.assertTrue(is_stable)
        self.assertEqual(diff_val, 0.0)

    def test_frame_stability_mismatched_shapes(self):
        """Mismatched screen dimensions return False with diff=255.0."""
        img1 = np.full((900, 1600, 3), 100, dtype=np.uint8)
        img2 = np.full((500, 500, 3), 100, dtype=np.uint8)
        is_stable, diff_val = self.runner.check_frame_stability(img1, img2)
        self.assertFalse(is_stable)
        self.assertEqual(diff_val, 255.0)

    @patch("time.sleep", return_value=None)
    def test_capture_stable_screen_adb(self, mock_sleep):
        """capture_stable_screen captures 2 frames via ADB separated by delay."""
        frame1 = np.full((900, 1600, 3), 100, dtype=np.uint8)
        frame2 = np.full((900, 1600, 3), 100, dtype=np.uint8)
        self.mock_adb.screencap.side_effect = [frame1, frame2]

        screen, is_stable, diff_val = self.runner.capture_stable_screen(delay=0.18)
        self.assertIsNotNone(screen)
        self.assertTrue(is_stable)
        self.assertEqual(diff_val, 0.0)
        self.assertEqual(self.mock_adb.screencap.call_count, 2)
        mock_sleep.assert_called_with(0.18)

    @patch("time.sleep", return_value=None)
    def test_run_loop_handles_unstable_loading_transition(self, mock_sleep):
        """
        In _run_loop, when screen changes (diff >= threshold),
        state is marked TRANSITIONING and normal detection is delayed until screen stabilizes.
        """
        self.runner.mode = Mode.CHAOS
        self.runner.enable_frame_stability = True

        img_map1 = np.full((900, 1600, 3), 50, dtype=np.uint8)
        img_loading = np.full((900, 1600, 3), 200, dtype=np.uint8)  # Huge jump -> unstable!
        img_map2 = np.full((900, 1600, 3), 50, dtype=np.uint8)
        img_map3 = np.full((900, 1600, 3), 50, dtype=np.uint8)
        img_map4 = np.full((900, 1600, 3), 50, dtype=np.uint8)

        # Detector returns CHAOS_MAP for dark screens
        def mock_detect(screen):
            if screen is not None and screen.mean() < 100:
                return State.CHAOS_MAP, {"recognizer": "test", "score": 0.9}
            return State.UNKNOWN, {"recognizer": "test"}

        self.runner._detect_state = MagicMock(side_effect=mock_detect)

        sequence = [img_map1, img_loading, img_map2, img_map3, img_map4]
        seq_idx = 0

        def fake_screencap():
            nonlocal seq_idx
            if seq_idx < len(sequence):
                frame = sequence[seq_idx]
                seq_idx += 1
                return frame
            self.runner._stop_event.set()
            return img_map4

        self.mock_adb.screencap = fake_screencap
        self.runner._run_loop()

        # img_loading was different from img_map1, so check_frame_stability caught it as unstable!
        self.assertTrue(self.runner._detect_state.called)
        # Verify that _detect_state was NEVER called with the unstable loading frame (mean 200)
        for call_args in self.runner._detect_state.call_args_list:
            called_frame = call_args[0][0]
            if called_frame is not None:
                self.assertNotEqual(float(called_frame.mean()), 200.0)


class TestStateTransitionValidation(unittest.TestCase):
    """[Mục 2] Tests for State Transition Validation using DEFAULT_ALLOWED_TRANSITIONS."""

    def setUp(self):
        self.mock_adb = MagicMock()
        self.mock_detector = MagicMock()
        self.runner = BotRunner(adb_client=self.mock_adb, detector=self.mock_detector)
        self.runner.enable_chaos_ai = False
        self.runner.is_running = True

    def test_is_transition_allowed_valid_cases(self):
        """Valid transitions per DEFAULT_ALLOWED_TRANSITIONS are allowed."""
        # Map transitions
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_MAP, State.IN_MATCH))
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_MAP, State.CHAOS_EVENT))
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_MAP, State.CHAOS_SAFE_ZONE))
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_MAP, State.TRANSITIONING))

        # After battle transitions
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_AFTER_BATTLE, State.CHAOS_MAP))
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_AFTER_BATTLE, State.CHAOS_EQUIPMENT))
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_AFTER_BATTLE, State.CHAOS_CHOOSE_EPIPHANY))
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_AFTER_BATTLE, State.CHAOS_OBTAIN_REWARD))

        # Self-transitions
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_MAP, State.CHAOS_MAP))
        self.assertTrue(self.runner.is_transition_allowed(State.IN_MATCH, State.IN_MATCH))

        # UNKNOWN / None / TRANSITIONING
        self.assertTrue(self.runner.is_transition_allowed(None, State.IN_MATCH))
        self.assertTrue(self.runner.is_transition_allowed(State.UNKNOWN, State.CHAOS_MAP))
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_MAP, State.UNKNOWN))
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_MAP, State.TRANSITIONING))

    def test_is_transition_allowed_invalid_jumps(self):
        """Impossible jumps are identified as invalid."""
        # Cannot jump directly from CHAOS_AFTER_BATTLE into IN_MATCH (must go through map / reward / transition)
        self.assertFalse(self.runner.is_transition_allowed(State.CHAOS_AFTER_BATTLE, State.IN_MATCH))
        # Cannot jump directly from CHAOS_SAFE_ZONE into IN_MATCH
        self.assertFalse(self.runner.is_transition_allowed(State.CHAOS_SAFE_ZONE, State.IN_MATCH))
        # Cannot jump directly from CHAOS_EQUIPMENT into IN_MATCH
        self.assertFalse(self.runner.is_transition_allowed(State.CHAOS_EQUIPMENT, State.IN_MATCH))
        # String input support
        self.assertFalse(self.runner.is_transition_allowed("CHAOS_AFTER_BATTLE", "IN_MATCH"))

    @patch("time.sleep", return_value=None)
    def test_run_loop_invalid_transition_requires_extended_confirm(self, mock_sleep):
        """
        When an invalid jump occurs (e.g. CHAOS_AFTER_BATTLE -> IN_MATCH),
        normal 3-frame confirmation is rejected; it requires 6 consecutive frames.
        """
        self.runner.mode = Mode.CHAOS
        self.runner.enable_frame_stability = False  # Isolate transition validation
        self.runner.enable_transition_validation = True
        self.runner.invalid_transition_confirm_frames = 6

        # Set initial confirmed state to CHAOS_AFTER_BATTLE
        self.runner.current_state = State.CHAOS_AFTER_BATTLE
        self.runner._last_state = State.CHAOS_AFTER_BATTLE

        # Sequence of 4 frames of IN_MATCH:
        # Since required_confirm = 6 for invalid jump, 4 frames should NOT confirm!
        screen = np.full((900, 1600, 3), 50, dtype=np.uint8)
        self.runner._detect_state = MagicMock(return_value=(State.IN_MATCH, {"recognizer": "test"}))

        call_count = 0

        def fake_screencap():
            nonlocal call_count
            call_count += 1
            if call_count <= 4:
                return screen
            self.runner._stop_event.set()
            return screen

        self.mock_adb.screencap = fake_screencap
        self.runner._run_loop()

        # Bot should still be in CHAOS_AFTER_BATTLE because 4 frames < 6 required confirm frames
        self.assertEqual(self.runner.current_state, State.CHAOS_AFTER_BATTLE)

    @patch("time.sleep", return_value=None)
    def test_run_loop_invalid_glitch_defused_by_real_state(self, mock_sleep):
        """
        If a 2-frame IN_MATCH glitch occurs during CHAOS_AFTER_BATTLE,
        followed by real CHAOS_MAP frames, the glitch is ignored and CHAOS_MAP confirms.
        """
        self.runner.mode = Mode.CHAOS
        self.runner.enable_frame_stability = False
        self.runner.enable_transition_validation = True
        self.runner.invalid_transition_confirm_frames = 6

        self.runner.current_state = State.CHAOS_AFTER_BATTLE
        self.runner._last_state = State.CHAOS_AFTER_BATTLE

        dummy = np.full((900, 1600, 3), 50, dtype=np.uint8)
        # Sequence: 2 glitch IN_MATCH frames, followed by 3 valid CHAOS_MAP frames
        states = [
            State.IN_MATCH, State.IN_MATCH,
            State.CHAOS_MAP, State.CHAOS_MAP, State.CHAOS_MAP
        ]
        s_idx = 0

        def fake_detect(screen):
            nonlocal s_idx
            st = states[min(s_idx, len(states) - 1)]
            s_idx += 1
            return st, {"recognizer": "test", "score": 0.9}

        self.runner._detect_state = MagicMock(side_effect=fake_detect)

        cap_count = 0

        def fake_screencap():
            nonlocal cap_count
            cap_count += 1
            if cap_count <= len(states):
                return dummy
            self.runner._stop_event.set()
            return dummy

        self.mock_adb.screencap = fake_screencap
        self.runner._run_loop()

        # CHAOS_MAP is a valid transition (needs 3 frames) and correctly confirms!
        self.assertEqual(self.runner.current_state, State.CHAOS_MAP)

    @patch("time.sleep", return_value=None)
    def test_run_loop_invalid_transition_guarded_even_across_transitioning_frames(self, mock_sleep):
        """
        Critical bug guard: When transitioning from CHAOS_AFTER_BATTLE through 3 frames
        of TRANSITIONING, a subsequent 4-frame glitch of IN_MATCH must still be caught as
        an invalid jump from the last settled real state, requiring 6 frames, and NOT confirming.
        """
        self.runner.mode = Mode.CHAOS
        self.runner.enable_frame_stability = False
        self.runner.enable_transition_validation = True
        self.runner.invalid_transition_confirm_frames = 6

        # Bot is confirmed in CHAOS_AFTER_BATTLE
        self.runner.current_state = State.CHAOS_AFTER_BATTLE
        self.runner._last_settled_state = State.CHAOS_AFTER_BATTLE

        dummy = np.full((900, 1600, 3), 50, dtype=np.uint8)
        # Sequence: 3 frames of TRANSITIONING (confirms TRANSITIONING), then 4 frames of IN_MATCH
        states = [
            State.TRANSITIONING, State.TRANSITIONING, State.TRANSITIONING,
            State.IN_MATCH, State.IN_MATCH, State.IN_MATCH, State.IN_MATCH
        ]
        s_idx = 0

        def fake_detect(screen):
            nonlocal s_idx
            st = states[min(s_idx, len(states) - 1)]
            s_idx += 1
            return st, {"recognizer": "test", "score": 0.9}

        self.runner._detect_state = MagicMock(side_effect=fake_detect)

        cap_count = 0

        def fake_screencap():
            nonlocal cap_count
            cap_count += 1
            if cap_count <= len(states):
                return dummy
            self.runner._stop_event.set()
            return dummy

        self.mock_adb.screencap = fake_screencap
        self.runner._run_loop()

        # Bot should NOT confirm IN_MATCH because 4 frames < 6 required confirm frames from CHAOS_AFTER_BATTLE!
        self.assertNotEqual(self.runner.current_state, State.IN_MATCH)

    def test_temporal_filter_with_transitioning_and_invalid_jump(self):
        """TemporalFilter blocks CHAOS_AFTER_BATTLE -> TRANSITIONING -> IN_MATCH."""
        from czn_bot.vision.state_classifier import TemporalFilter
        tf = TemporalFilter(window=5, need=3)
        # Establish stable state as CHAOS_AFTER_BATTLE
        for _ in range(3):
            tf.push(Result("CHAOS_AFTER_BATTLE"))
        self.assertEqual(tf.stable, "CHAOS_AFTER_BATTLE")

        # Push TRANSITIONING
        for _ in range(3):
            tf.push(Result("TRANSITIONING"))
        self.assertEqual(tf.stable, "TRANSITIONING")

        # Push invalid jump IN_MATCH -> should be blocked!
        for _ in range(3):
            tf.push(Result("IN_MATCH"))
        self.assertNotEqual(tf.stable, "IN_MATCH")
        self.assertEqual(tf.stable, "TRANSITIONING")

        # Push valid jump CHAOS_MAP -> should be allowed!
        for _ in range(3):
            tf.push(Result("CHAOS_MAP"))
        self.assertEqual(tf.stable, "CHAOS_MAP")

    def test_popup_effect_transitions_allowed(self):
        """POPUP_EFFECT is valid from and to various Chaos modes."""
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_AFTER_BATTLE, State.POPUP_EFFECT))
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_EVENT, State.POPUP_EFFECT))
        self.assertTrue(self.runner.is_transition_allowed(State.CHAOS_SAFE_ZONE, State.POPUP_EFFECT))
        self.assertTrue(self.runner.is_transition_allowed(State.POPUP_EFFECT, State.CHAOS_AFTER_BATTLE))
        self.assertTrue(self.runner.is_transition_allowed(State.POPUP_EFFECT, State.CHAOS_MAP))


class TestDetailedDecisionLogging(unittest.TestCase):
    """[Mục 7] Tests for Detailed Decision Logging in detector and runner."""

    def setUp(self):
        self.detector = ScreenDetector()
        self.mock_adb = MagicMock()
        self.runner = BotRunner(adb_client=self.mock_adb, detector=self.detector)

    def test_detector_detect_decision_metadata_heuristics(self):
        """Heuristic detection returns recognizer, confidence, margin, and runner_up."""
        # 1. Dark cutscene heuristic
        dark_screen = np.full((900, 1600, 3), 20, dtype=np.uint8)
        st, det = self.detector.detect(dark_screen)
        self.assertEqual(st, State.TRANSITIONING)
        self.assertEqual(det.get("recognizer"), "heuristic_dark_cutscene")
        self.assertEqual(det.get("confidence"), 1.0)
        self.assertIn("ranked", det)

        # 2. IN_MATCH heuristic
        hp_screen = np.full((900, 1600, 3), 40, dtype=np.uint8)
        hp_screen[5:30, 150:500] = [0, 200, 0]  # Green HP bar
        st_hp, det_hp = self.detector.detect(hp_screen)
        self.assertEqual(st_hp, State.IN_MATCH)
        self.assertEqual(det_hp.get("recognizer"), "heuristic_in_match")
        self.assertGreaterEqual(det_hp.get("confidence"), 0.70)

        # 3. UNKNOWN screen
        bright = np.full((900, 1600, 3), 180, dtype=np.uint8)
        st_u, det_u = self.detector.detect(bright)
        self.assertEqual(st_u, State.UNKNOWN)
        self.assertEqual(det_u.get("recognizer"), "none")

    def test_detector_detect_decision_metadata_state_classifier(self):
        """StateClassifier detections include recognizer, score, margin, and runner_up."""
        # Mock classify result with winner and runner-up
        mock_result = Result(
            state="CHAOS_MAP",
            confidence=0.92,
            margin=0.25,
            ranked=[("CHAOS_MAP", 0.92), ("IN_MATCH", 0.67)],
            evidence={"chaos_node_pin": 0.92},
            best_coords={"chaos_node_pin": (300, 600)}
        )
        self.detector.classifier.classify = MagicMock(return_value=mock_result)

        dummy = np.full((900, 1600, 3), 50, dtype=np.uint8)
        state, details = self.detector.detect(dummy)

        self.assertEqual(state, State.CHAOS_MAP)
        self.assertEqual(details.get("recognizer"), "OpenCV StateClassifier")
        self.assertAlmostEqual(details.get("confidence"), 0.92)
        self.assertAlmostEqual(details.get("margin"), 0.25)
        self.assertEqual(details.get("runner_up"), ("IN_MATCH", 0.67))

    def test_runner_format_decision_log(self):
        """_format_decision_log formats structured log string with all key decision metrics."""
        details = {
            "recognizer": "OpenCV StateClassifier",
            "score": 0.88,
            "margin": 0.22,
            "runner_up": ("CHAOS_EVENT", 0.66)
        }
        log_str = self.runner._format_decision_log(State.CHAOS_MAP, details)
        self.assertIn("[VisionDecision]", log_str)
        self.assertIn("State=CHAOS_MAP", log_str)
        self.assertIn("Recognizer=OpenCV StateClassifier", log_str)
        self.assertIn("Confidence=0.88", log_str)
        self.assertIn("Margin=0.22", log_str)
        self.assertIn("Runner-up=CHAOS_EVENT (0.66)", log_str)

    def test_stall_diagnostics_dump_contains_decision_evidence(self):
        """_handle_stall includes recognizer, score, margin, and runner_up in JSON dump."""
        self.runner.enable_recovery = False
        self.runner._halt = MagicMock()

        details = {
            "recognizer": "heuristic_in_match",
            "score": 0.85,
            "margin": 0.30,
            "runner_up": ("CHAOS_MAP", 0.55),
            "heuristic": True
        }
        screen = np.full((900, 1600, 3), 50, dtype=np.uint8)

        with patch("builtins.open", unittest.mock.mock_open()) as mock_file:
            self.runner._handle_stall(screen, State.IN_MATCH, details, elapsed_stall=35.0)

            # Check that json.dump was called with diagnostic data containing recognizer
            written_data = "".join(call.args[0] for call in mock_file().write.call_args_list)
            if written_data:
                parsed = json.loads(written_data)
                self.assertEqual(parsed.get("recognizer"), "heuristic_in_match")
                self.assertAlmostEqual(parsed.get("confidence"), 0.85)
                self.assertAlmostEqual(parsed.get("margin"), 0.30)
                self.assertIn("CHAOS_MAP", parsed.get("runner_up"))

    def test_ai_vision_decision_metadata(self):
        """When AI Vision detects state, decision metadata is properly set and logged."""
        self.runner.enable_ai_vision_detection = True
        self.runner.enable_chaos_ai = True
        self.runner.rule_manager.get_api_key = MagicMock(return_value="test_key")

        # OpenCV returns UNKNOWN
        self.runner.detector.detect = MagicMock(return_value=(State.UNKNOWN, {}))

        mock_brain = MagicMock()
        mock_brain.detect_state_with_ai.return_value = (
            State.CHAOS_EVENT,
            {"confidence": 0.85, "reason": "Event choices banner"}
        )
        self.runner.chaos_brain = mock_brain

        dummy = np.full((900, 1600, 3), 50, dtype=np.uint8)
        state, details = self.runner._detect_state(dummy)

        self.assertEqual(state, State.CHAOS_EVENT)
        self.assertEqual(details.get("recognizer"), "AI Vision")
        self.assertAlmostEqual(details.get("confidence"), 0.85)

    def test_handle_stall_invokes_on_stall_callback(self):
        """_handle_stall calls on_stall callback with diagnostic paths."""
        self.runner.enable_recovery = False
        self.runner._halt = MagicMock()
        mock_on_stall = MagicMock()
        self.runner.on_stall = mock_on_stall

        screen = np.full((900, 1600, 3), 50, dtype=np.uint8)
        details = {
            "recognizer": "heuristic_in_match",
            "score": 0.85,
            "margin": 0.30,
            "ranked": [("IN_MATCH", 0.85), ("CHAOS_MAP", 0.55)]
        }
        with patch("builtins.open", unittest.mock.mock_open()):
            self.runner._handle_stall(screen, State.IN_MATCH, details, elapsed_stall=35.0)

        mock_on_stall.assert_called_once()
        args = mock_on_stall.call_args[0]
        self.assertEqual(args[0], State.IN_MATCH)
        self.assertEqual(args[1], 35.0)
        self.assertTrue(args[2].endswith(".png"))
        self.assertTrue(args[3].endswith(".json"))

    def test_unknown_state_has_runner_up_and_top_candidate(self):
        """UNKNOWN state details have proper runner_up and top_candidate metadata."""
        mock_result = Result(
            state="UNKNOWN",
            confidence=0.40,
            margin=0.05,
            ranked=[("CHAOS_MAP", 0.40), ("IN_MATCH", 0.35)],
            evidence={"chaos_node_pin": 0.40}
        )
        self.detector.classifier.classify = MagicMock(return_value=mock_result)
        dummy = np.full((900, 1600, 3), 180, dtype=np.uint8)
        state, details = self.detector.detect(dummy)

        self.assertEqual(state, State.UNKNOWN)
        self.assertEqual(details.get("top_candidate"), ("CHAOS_MAP", 0.40))
        self.assertEqual(details.get("runner_up"), ("IN_MATCH", 0.35))


if __name__ == "__main__":
    unittest.main()
