"""
Unit tests for Story Mode auto-progression:
- Detection of STORY_MAP and STORY_DIALOGUE states
- Finding active stage node on chapter map
- Engine handlers for STORY_MAP, STORY_DIALOGUE, and MATCH_DONE in Mode.STORY
"""
import os
import unittest
from unittest.mock import MagicMock
import cv2
import numpy as np

from config import State, Mode, LeftButton, TAP_COORDS
from detector import ScreenDetector
from bot_engine import BotEngine


class TestStoryMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = ScreenDetector()
        cls.fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")

    def setUp(self):
        self.mock_adb = MagicMock()
        self.engine = BotEngine(adb_client=self.mock_adb, detector=self.detector)
        self.engine.mode = Mode.STORY
        self.engine.is_running = True
        self.engine.beep = MagicMock()
        self.dummy_screen = np.zeros((100, 100, 3), dtype=np.uint8)

    # ── Detection Tests ──────────────────────────────────────────────

    def test_detect_story_map_screen(self):
        """Verify that chapter map screen is recognized as State.STORY_MAP."""
        current_screen_path = os.path.join(self.fixture_dir, "story_map_screen.png")
        if os.path.exists(current_screen_path):
            img = cv2.imread(current_screen_path)
            state, details = self.detector.detect(img)
            self.assertEqual(state, State.STORY_MAP)
            self.assertIsNotNone(details.get("active_node"))

    def test_detect_story_map_node2_screen(self):
        """Verify that node #02 at screen right edge is correctly detected as State.STORY_MAP with active_node."""
        node2_path = os.path.join(os.path.dirname(__file__), "..", "logs", "story_map_node2_1600.png")
        if os.path.exists(node2_path):
            img = cv2.imread(node2_path)
            state, details = self.detector.detect(img)
            self.assertEqual(state, State.STORY_MAP)
            self.assertEqual(details.get("active_node"), (1550, 452))

    def test_detect_story_dialogue_screen(self):
        """Verify that story cutscene/dialogue screen is recognized as State.STORY_DIALOGUE."""
        dialogue_screen_path = os.path.join(os.path.dirname(__file__), "..", "logs", "story_battle_active.png")
        if os.path.exists(dialogue_screen_path):
            img = cv2.imread(dialogue_screen_path)
            state, details = self.detector.detect(img)
            self.assertEqual(state, State.STORY_DIALOGUE)
            self.assertIn("skip_coord", details)

    def test_detect_story_stage_info_screen(self):
        """Verify that story stage info screen with Enter button is detected as PRE_MATCH_MISSION, not closed as popup."""
        stage_info_path = os.path.join(self.fixture_dir, "story_stage_info_screen.png")
        if os.path.exists(stage_info_path):
            img = cv2.imread(stage_info_path)
            state, details = self.detector.detect(img)
            self.assertEqual(state, State.PRE_MATCH_MISSION)
            self.assertGreaterEqual(details.get("score", 0), 0.85)
            self.assertIn("coord", details)

    def test_find_story_active_node_synthetic(self):
        """Verify that orange play button contour is correctly located."""
        screen = np.full((900, 1600, 3), 200, dtype=np.uint8)
        # Draw circular orange play button at (800, 450)
        # Orange in BGR: (30, 140, 240) -> HSV: (16, 223, 240)
        cv2.circle(screen, (800, 450), 20, (30, 140, 240), -1)
        node_pt = self.detector.find_story_active_node(screen)
        self.assertIsNotNone(node_pt)
        self.assertAlmostEqual(node_pt[0], 800, delta=15)
        self.assertAlmostEqual(node_pt[1], 450, delta=15)

    # ── Engine Handler Tests ──────────────────────────────────────────

    def test_handle_story_map_active_node(self):
        """When an active stage node is found on the map, tap it to open stage info."""
        details = {"active_node": (1337, 452)}
        result = self.engine._handle_story_map(self.dummy_screen, details)
        self.assertTrue(result)
        self.mock_adb.tap.assert_called_once_with(1337, 452)
        self.assertEqual(self.engine._story_swipe_count, 0)

    def test_handle_story_map_swipes_when_no_active_node(self):
        """When active node is not on screen, bot swipes left to search further right."""
        details = {"active_node": None}
        self.engine._story_swipe_count = 0

        # Swipe 1
        self.engine._handle_story_map(self.dummy_screen, details)
        self.mock_adb.swipe.assert_called_with(1200, 500, 400, 500, duration_ms=500)
        self.assertEqual(self.engine._story_swipe_count, 1)

        # Swipe 2
        self.engine._handle_story_map(self.dummy_screen, details)
        self.assertEqual(self.engine._story_swipe_count, 2)

        # Swipe 3
        self.engine._handle_story_map(self.dummy_screen, details)
        self.assertEqual(self.engine._story_swipe_count, 3)

        # After 3 swipes, taps next chapter button [>]
        self.engine._handle_story_map(self.dummy_screen, details)
        self.mock_adb.tap.assert_called_with(*TAP_COORDS["story_chapter_next"])
        self.assertEqual(self.engine._story_swipe_count, 0)

    def test_handle_story_dialogue_fast_forwards(self):
        """Dialogue handler taps auto and repeatedly taps skip button."""
        details = {
            "skip_coord": (1272, 48),
            "auto_coord": (1395, 48),
        }
        result = self.engine._handle_story_dialogue(self.dummy_screen, details)
        self.assertTrue(result)
        # Should tap auto once and skip 3 times
        self.assertGreaterEqual(self.mock_adb.tap.call_count, 4)
        self.mock_adb.tap.assert_any_call(1395, 48)
        self.mock_adb.tap.assert_any_call(1272, 48)
        self.assertIsNone(self.engine._last_action)

    def test_handle_story_dialogue_does_not_skip_in_chaos_mode(self):
        """In Chaos mode, STORY_DIALOGUE should NOT skip dialogues or tap buttons."""
        self.engine.mode = Mode.CHAOS
        details = {
            "skip_coord": (1272, 48),
            "auto_coord": (1395, 48),
        }
        result = self.engine._handle_story_dialogue(self.dummy_screen, details)
        self.assertTrue(result)
        self.assertEqual(self.mock_adb.tap.call_count, 0)
        self.assertIsNone(self.engine._last_action)

    def test_detect_story_victory_screen(self):
        """Verify that Story Mode victory screen is recognized as MATCH_DONE with purple confirm button and no retry."""
        victory_screen_path = os.path.join(os.path.dirname(__file__), "..", "logs", "story_victory_1600.png")
        if os.path.exists(victory_screen_path):
            img = cv2.imread(victory_screen_path)
            state, details = self.detector.detect(img)
            self.assertEqual(state, State.MATCH_DONE)
            self.assertEqual(details.get("left_button"), LeftButton.NONE)
            self.assertGreaterEqual(details.get("confirm_score", 0), 0.90)
            self.assertGreaterEqual(details.get("reward_score", 0), 0.90)
            self.assertEqual(details.get("confirm_coord"), (1403, 826))

    def test_handle_match_done_story_victory(self):
        """In Story Mode, victory (no retry button) taps Confirm and records completion."""
        details = {"left_button": LeftButton.NONE}
        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertTrue(result)
        self.mock_adb.tap.assert_called_once_with(*TAP_COORDS["right_button"])
        self.assertEqual(self.engine.retries_done, 1)

    def test_handle_match_done_story_victory_with_dynamic_confirm_coord(self):
        """In Story Mode, victory with dynamic confirm_coord taps exact button coordinate."""
        details = {
            "left_button": LeftButton.NONE,
            "reward_score": 1.0,
            "confirm_score": 1.0,
            "confirm_coord": (1403, 826),
        }
        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertTrue(result)
        self.mock_adb.tap.assert_called_once_with(1403, 826)
        self.assertEqual(self.engine.retries_done, 1)

    def test_handle_match_done_story_victory_with_rewards_overrides_retry(self):
        """If reward_score is high, match is recognized as victory even if noisy retry was flagged."""
        details = {
            "left_button": LeftButton.RETRY,
            "reward_score": 0.95,
            "confirm_score": 0.95,
            "confirm_coord": (1403, 826),
        }
        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertTrue(result)
        self.mock_adb.tap.assert_called_once_with(1403, 826)
        self.assertEqual(self.engine.retries_done, 1)

    def test_handle_match_done_story_defeat_halts(self):
        """In Story Mode, defeat (retry button present and NO rewards/confirm) halts bot with notification."""
        self.engine.notifier = MagicMock()
        details = {"left_button": LeftButton.RETRY, "reward_score": 0.0, "confirm_score": 0.0}
        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertFalse(result)
        self.assertFalse(self.engine.is_running)
        self.engine.notifier.notify_match_failed.assert_called_once()
        self.engine.beep.assert_called_once()
        self.mock_adb.tap.assert_not_called()

    def test_handle_match_done_story_max_stages(self):
        """In Story Mode, reaching max_retries halts bot."""
        self.engine.notifier = MagicMock()
        self.engine.max_retries = 3
        self.engine.retries_done = 3
        details = {"left_button": LeftButton.NONE}
        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertFalse(result)
        self.assertFalse(self.engine.is_running)
        self.engine.notifier.notify_max_retries.assert_called_once_with(3)


if __name__ == "__main__":
    unittest.main()

