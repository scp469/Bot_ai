"""
Unit tests for MockADBClient offline simulation.
"""
import os
import unittest

from czn_bot.device.mock import MockADBClient


class TestMockADB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        cls.test_img = os.path.join(cls.fixtures_dir, "chaos_map_1_island.png")

    def test_mock_adb_screencap(self):
        client = MockADBClient(self.test_img)
        self.assertTrue(client.connect())
        self.assertTrue(client.is_connected())

        frame = client.screencap()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape[:2], (900, 1600))

    def test_mock_adb_tap_and_advance(self):
        images = [
            os.path.join(self.fixtures_dir, "chaos_map_3_islands.png"),
            os.path.join(self.fixtures_dir, "chaos_reward_leave.png"),
        ]
        client = MockADBClient(images)
        self.assertEqual(client.current_idx, 0)

        # Tap on first frame
        success = client.tap(1150, 240)
        self.assertTrue(success)
        self.assertEqual(client.step_count, 1)
        self.assertEqual(client.current_idx, 1)

        # Tap on second frame
        success = client.tap(1426, 828)
        self.assertTrue(success)
        self.assertEqual(client.step_count, 2)
        # Should stay on last frame
        self.assertEqual(client.current_idx, 1)


if __name__ == "__main__":
    unittest.main()
