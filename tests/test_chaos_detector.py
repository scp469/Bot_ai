"""
Unit tests for Chaos screen detection in detector.py.
"""
import os
import unittest
import cv2

from detector import ScreenDetector
from config import State


class TestChaosDetector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        cls.detector = ScreenDetector()

    def test_detect_chaos_map_3_islands(self):
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_map_3_islands.png"))
        self.assertIsNotNone(img)
        state, _ = self.detector.detect(img)
        self.assertEqual(state, State.CHAOS_MAP)

    def test_detect_chaos_map_1_island(self):
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_map_1_island.png"))
        self.assertIsNotNone(img)
        state, _ = self.detector.detect(img)
        self.assertEqual(state, State.CHAOS_MAP)

    def test_detect_chaos_reward_leave(self):
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_reward_leave.png"))
        self.assertIsNotNone(img)
        state, details = self.detector.detect(img)
        self.assertEqual(state, State.CHAOS_AFTER_BATTLE)
        self.assertIn("leave_coord", details)

    def test_detect_chaos_continue(self):
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_continue.png"))
        self.assertIsNotNone(img)
        state, details = self.detector.detect(img)
        self.assertEqual(state, State.CHAOS_AFTER_BATTLE)
        self.assertIn("leave_coord", details)

    def test_detect_chaos_choose_epiphany(self):
        """Verify that Choose Epiphany Effect screen is detected as CHAOS_CHOOSE_EPIPHANY."""
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_choose_epiphany.png"))
        if img is not None:
            state, details = self.detector.detect(img)
            self.assertEqual(state, State.CHAOS_CHOOSE_EPIPHANY)

    def test_detect_chaos_card_reward(self):
        """Verify that Card Reward screen is detected as CHAOS_CHOOSE_EPIPHANY."""
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_card_reward.png"))
        self.assertIsNotNone(img)
        state, details = self.detector.detect(img)
        self.assertEqual(state, State.CHAOS_CHOOSE_EPIPHANY)

    def test_detect_chaos_reward_obtain(self):
        """Verify that Obtain screen is detected as State.CHAOS_OBTAIN_REWARD with obtain_coord."""
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_reward_obtain.png"))
        self.assertIsNotNone(img)
        state, details = self.detector.detect(img)
        self.assertEqual(state, State.CHAOS_OBTAIN_REWARD)
        self.assertIn("obtain_coord", details)

    def test_detect_memory_obtained_popup(self):
        """Verify that Memory Obtained modal is detected as POPUP_EFFECT with close_coord (800, 850)."""
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_memory_obtained.png"))
        self.assertIsNotNone(img)
        state, details = self.detector.detect(img)
        self.assertEqual(state, State.POPUP_EFFECT)
        self.assertEqual(details.get("close_coord"), (800, 850))

    def test_detect_transitioning_blank_frame(self):
        """Verify that a frame with no UI elements is detected as TRANSITIONING."""
        import numpy as np
        blank = np.zeros((900, 1600, 3), dtype=np.uint8)
        state, details = self.detector.detect(blank)
        self.assertEqual(state, State.TRANSITIONING)

    def test_detect_transitioning_dark_cutscene(self):
        """Verify that a dark cutscene frame (>65% pixels < 60) returns TRANSITIONING."""
        import numpy as np
        dark = np.full((900, 1600, 3), 30, dtype=np.uint8)
        # Add a small bright shape that doesn't match any template
        dark[400:450, 700:750] = 200
        state, details = self.detector.detect(dark)
        self.assertEqual(state, State.TRANSITIONING)

    def test_detect_in_match_heuristic(self):
        """Verify that green HP bar + dark center background triggers IN_MATCH heuristic."""
        import numpy as np
        screen = np.full((900, 1600, 3), 40, dtype=np.uint8)
        # Add green HP bar at y=5..30, x=150..500 (BGR: [0, 200, 0])
        screen[5:30, 150:500] = [0, 200, 0]
        state, details = self.detector.detect(screen)
        self.assertEqual(state, State.IN_MATCH)
        self.assertTrue(details.get("heuristic"))

    def test_detect_pre_match_heuristics(self):
        """Verify pixel-based heuristics for PRE_MATCH_MISSION and PRE_MATCH_TEAM."""
        import numpy as np
        # Base light background (mean > 160)
        screen = np.full((900, 1600, 3), 200, dtype=np.uint8)
        # Dark back button at top-left: [20:55, 35:85]
        screen[20:55, 35:85] = [20, 20, 20]
        # Dark action button at bottom-right: [780:880, 1100:1550]
        screen[780:880, 1100:1550] = [30, 30, 30]

        # Without preset button -> PRE_MATCH_MISSION
        state_mission, details_m = self.detector.detect(screen)
        self.assertEqual(state_mission, State.PRE_MATCH_MISSION)
        self.assertTrue(details_m.get("heuristic"))

        # With preset button at [780:880, 50:300] -> PRE_MATCH_TEAM
        screen[780:880, 50:300] = [30, 30, 30]
        state_team, details_t = self.detector.detect(screen)
        self.assertEqual(state_team, State.PRE_MATCH_TEAM)
        self.assertTrue(details_t.get("heuristic"))

    def test_per_template_threshold(self):
        """Verify that per-template threshold overrides are respected."""
        from config import TEMPLATE_THRESHOLDS
        self.assertEqual(self.detector._get_threshold("in_match_check"), TEMPLATE_THRESHOLDS["in_match_check"])
        self.assertEqual(self.detector._get_threshold("chaos_leave_button"), TEMPLATE_THRESHOLDS["chaos_leave_button"])
    def test_detect_chaos_safe_zone(self):
        """Verify that Safe Zone / Rest site is detected as CHAOS_SAFE_ZONE."""
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_safe_zone.png"))
        if img is not None:
            state, details = self.detector.detect(img)
            self.assertEqual(state, State.CHAOS_SAFE_ZONE)
            self.assertIn("skip_coord", details)

    def test_detect_choose_fate(self):
        """Verify that Choose your fate screen is detected as CHAOS_CHOOSE_EPIPHANY."""
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_choose_fate.png"))
        self.assertIsNotNone(img)
        state, details = self.detector.detect(img)
        self.assertEqual(state, State.CHAOS_CHOOSE_EPIPHANY)
        self.assertGreaterEqual(details.get("score_choose_fate", 0), 0.75)

    def test_detect_remove_card(self):
        """Verify that Select card to Remove screen is detected as CHAOS_CHOOSE_EPIPHANY."""
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_remove_card.png"))
        self.assertIsNotNone(img)
        state, details = self.detector.detect(img)
        self.assertEqual(state, State.CHAOS_CHOOSE_EPIPHANY)
        self.assertGreaterEqual(details.get("score_remove_card", 0), 0.75)

    def test_detect_tap_to_close_modal(self):
        """Verify that Tap to close the window modal is detected as POPUP_EFFECT with close_coord."""
        img = cv2.imread(os.path.join(self.fixture_dir, "chaos_obtain_pact.png"))
        self.assertIsNotNone(img)
        state, details = self.detector.detect(img)
        self.assertEqual(state, State.POPUP_EFFECT)
        self.assertEqual(details.get("close_coord"), (800, 850))


if __name__ == "__main__":
    unittest.main()



