"""
Integration tests for BotEngine running in Mode.CHAOS.
Simulates ADB capture and verifies state dispatching, island selection, and safety guards.
"""
import os
import unittest
from unittest.mock import MagicMock, patch
import cv2

from czn_bot.states import Mode
from czn_bot.coords import TAP_COORDS
from czn_bot.runner import BotRunner as BotEngine
from czn_bot.vision.detector import ScreenDetector


class TestChaosIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        cls.map_3 = cv2.imread(os.path.join(cls.fixture_dir, "chaos_map_3_islands.png"))
        cls.map_2 = cv2.imread(os.path.join(cls.fixture_dir, "chaos_map_2_islands.png"))
        cls.map_1 = cv2.imread(os.path.join(cls.fixture_dir, "chaos_map_1_island.png"))
        cls.leave = cv2.imread(os.path.join(cls.fixture_dir, "chaos_reward_leave.png"))
        cls.obtain = cv2.imread(os.path.join(cls.fixture_dir, "chaos_reward_obtain.png"))

    def setUp(self):
        self.mock_adb = MagicMock()
        self.detector = ScreenDetector()
        self.engine = BotEngine(adb_client=self.mock_adb, detector=self.detector)
        self.engine.is_running = True
        self.engine.loop_delay = 0.0
        self.engine.beep = MagicMock()
        self.engine.enable_dynamic_islands = False
        self.engine.enable_chaos_ai = False
        self.engine.enable_hybrid_verification = False

    @patch("time.sleep", return_value=None)
    def test_chaos_mode_shows_under_construction_and_stops(self, mock_sleep=None):
        """Mode.CHAOS should display notice and stop safely without crashing."""
        self.engine.is_running = False
        self.engine.mode = Mode.CHAOS
        self.engine.start()
        self.assertFalse(self.engine.is_running)

    @patch("time.sleep", return_value=None)
    def test_replay_mode_ignores_chaos_map(self, mock_sleep):
        """Verify that in Mode.REPLAY, chaos map is IGNORED (zero taps)."""
        self.engine.mode = Mode.REPLAY

        frames = [self.map_3, self.map_3, self.map_3, self.map_3]
        frame_idx = 0

        def fake_screencap():
            nonlocal frame_idx
            if frame_idx < len(frames):
                img = frames[frame_idx]
                frame_idx += 1
                return img
            self.engine._stop_event.set()
            self.engine.stop("Test finished")
            return self.map_3

        self.mock_adb.screencap = fake_screencap
        self.engine._run_loop()

        self.assertFalse(self.mock_adb.tap.called)


if __name__ == "__main__":
    unittest.main()
