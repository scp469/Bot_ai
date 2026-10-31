"""
Unit tests for Team HP Reader module.
"""
import unittest
import os
import cv2
from czn_bot.vision.hp_reader import get_team_hp, HP_BAR_X_START, HP_BAR_Y_START, HP_BAR_Y_END, HP_BAR_TOTAL_WIDTH


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class TestChaosHPReader(unittest.TestCase):
    def test_full_hp_real_screenshot(self):
        path = os.path.join(FIXTURES_DIR, "chaos_map_3_islands.png")
        if not os.path.exists(path):
            self.skipTest(f"Fixture not found: {path}")

        img = cv2.imread(path)
        hp, is_low = get_team_hp(img)
        self.assertAlmostEqual(hp, 1.0, delta=0.02)
        self.assertFalse(is_low)

    def test_full_hp_real_screenshot_single_island(self):
        path = os.path.join(FIXTURES_DIR, "chaos_map_1_island.png")
        if not os.path.exists(path):
            self.skipTest(f"Fixture not found: {path}")

        img = cv2.imread(path)
        hp, is_low = get_team_hp(img)
        self.assertAlmostEqual(hp, 1.0, delta=0.02)
        self.assertFalse(is_low)

    def test_simulated_low_hp_45_percent(self):
        path = os.path.join(FIXTURES_DIR, "chaos_map_3_islands.png")
        if not os.path.exists(path):
            self.skipTest(f"Fixture not found: {path}")

        img = cv2.imread(path).copy()
        # Erase HP bar past 45% (cut at x = HP_BAR_X_START + 0.45 * HP_BAR_TOTAL_WIDTH)
        cut_x = int(HP_BAR_X_START + 0.45 * HP_BAR_TOTAL_WIDTH)
        img[HP_BAR_Y_START:HP_BAR_Y_END, cut_x:HP_BAR_X_START + HP_BAR_TOTAL_WIDTH] = [20, 25, 20]

        hp, is_low = get_team_hp(img)
        self.assertAlmostEqual(hp, 0.45, delta=0.03)
        self.assertTrue(is_low)

    def test_boundary_60_percent(self):
        path = os.path.join(FIXTURES_DIR, "chaos_map_3_islands.png")
        if not os.path.exists(path):
            self.skipTest(f"Fixture not found: {path}")

        img = cv2.imread(path).copy()
        # 60% HP boundary
        cut_x = int(HP_BAR_X_START + 0.60 * HP_BAR_TOTAL_WIDTH)
        img[HP_BAR_Y_START:HP_BAR_Y_END, cut_x:HP_BAR_X_START + HP_BAR_TOTAL_WIDTH] = [20, 25, 20]

        hp, is_low = get_team_hp(img)
        self.assertAlmostEqual(hp, 0.60, delta=0.03)
        # 60% is NOT low HP (>= 60% is Attack mode)
        self.assertFalse(is_low)


if __name__ == "__main__":
    unittest.main()
