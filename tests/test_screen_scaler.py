"""
Unit tests for ScreenScaler and resolution check logic.
"""
import unittest
from config import ScreenScaler
from adb_client import ADBClient


class TestScreenScaler(unittest.TestCase):
    def test_identity_scaling_1600x900(self):
        scaler = ScreenScaler(actual_width=1600, actual_height=900)
        self.assertEqual(scaler.to_actual_point(1150, 240), (1150, 240))
        self.assertEqual(scaler.to_actual_roi(100, 200, 300, 400), (100, 200, 300, 400))

    def test_upscaling_1920x1080(self):
        # 16:9 aspect ratio scaling from 1600x900 to 1920x1080 (factor = 1.2)
        scaler = ScreenScaler(actual_width=1920, actual_height=1080)
        self.assertAlmostEqual(scaler.scale_x, 1.2, places=3)
        self.assertAlmostEqual(scaler.scale_y, 1.2, places=3)
        # Point (100, 100) -> (120, 120)
        self.assertEqual(scaler.to_actual_point(100, 100), (120, 120))
        self.assertEqual(scaler.to_actual_roi(100, 200, 300, 400), (120, 240, 360, 480))

    def test_check_resolution_logic(self):
        client = ADBClient()
        # Mock get_screen_size
        client.get_screen_size = lambda: (1600, 900)
        is_ok, size, msg = client.check_resolution()
        self.assertTrue(is_ok)
        self.assertEqual(size, (1600, 900))

        client.get_screen_size = lambda: (1920, 1080)
        is_ok, size, msg = client.check_resolution()
        self.assertFalse(is_ok)
        self.assertEqual(size, (1920, 1080))
        self.assertIn("1920x1080", msg)


if __name__ == "__main__":
    unittest.main()
