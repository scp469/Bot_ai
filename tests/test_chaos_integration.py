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
    def test_chaos_map_3_islands_dispatch(self, mock_sleep):
        """Verify that in Mode.CHAOS with static config, map 3 islands triggers tap on selected island."""
        self.engine.mode = Mode.CHAOS
        
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

        self.assertTrue(self.mock_adb.tap.called)
        tap_args = self.mock_adb.tap.call_args_list[0][0]
        valid_coords = [
            TAP_COORDS["chaos_island_3_top"],
            TAP_COORDS["chaos_island_3_middle"],
            TAP_COORDS["chaos_island_3_bottom"],
        ]
        self.assertIn(tap_args, valid_coords)

    @patch("time.sleep", return_value=None)
    def test_chaos_map_3_islands_dynamic_dispatch(self, mock_sleep):
        """Verify that with dynamic 3D detection enabled, it taps the detected centroid."""
        self.engine.mode = Mode.CHAOS
        self.engine.enable_dynamic_islands = True

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

        self.assertTrue(self.mock_adb.tap.called)
        tap_args = self.mock_adb.tap.call_args_list[0][0]
        # Detected centroids for 3 islands (banner targets)
        valid_dynamic_coords = [(1213, 143), (1441, 402), (1070, 707)]
        self.assertIn(tap_args, valid_dynamic_coords)


    @patch("time.sleep", return_value=None)
    def test_chaos_map_2_islands_dispatch(self, mock_sleep):
        """Verify that in Mode.CHAOS with 2 islands, it taps (1330, 420) or (1250, 240), NEVER (1100, 800)."""
        self.engine.mode = Mode.CHAOS

        frames = [self.map_2, self.map_2, self.map_2, self.map_2]
        frame_idx = 0

        def fake_screencap():
            nonlocal frame_idx
            if frame_idx < len(frames):
                img = frames[frame_idx]
                frame_idx += 1
                return img
            self.engine._stop_event.set()
            self.engine.stop("Test finished")
            return self.map_2

        self.mock_adb.screencap = fake_screencap
        self.engine._run_loop()

        self.assertTrue(self.mock_adb.tap.called)
        tap_args = self.mock_adb.tap.call_args[0]
        # Must tap one of the 2-island locations (allowing small jitter delta if jitter tap was triggered)
        valid_2_island_coords = [
            TAP_COORDS["chaos_island_2_top"],     # (1210, 140)
            TAP_COORDS["chaos_island_2_bottom"],  # (1430, 400)
        ]
        is_valid = any(abs(tap_args[0] - vc[0]) <= 15 and abs(tap_args[1] - vc[1]) <= 15 for vc in valid_2_island_coords)
        self.assertTrue(is_valid, f"tap_args {tap_args} not near {valid_2_island_coords}")
        # MUST NEVER tap the old empty coordinate (1100, 800)
        self.assertNotEqual(tap_args, (1100, 800))

    @patch("time.sleep", return_value=None)
    def test_chaos_leave_button_dispatch(self, mock_sleep):
        """Verify that in Mode.CHAOS, reward screen with Leave button triggers tap on Leave."""
        self.engine.mode = Mode.CHAOS

        frames = [self.leave, self.leave, self.leave, self.leave]
        frame_idx = 0

        def fake_screencap():
            nonlocal frame_idx
            if frame_idx < len(frames):
                img = frames[frame_idx]
                frame_idx += 1
                return img
            self.engine._stop_event.set()
            self.engine.stop("Test finished")
            return self.leave

        self.mock_adb.screencap = fake_screencap
        self.engine._run_loop()

        self.assertTrue(self.mock_adb.tap.called)
        tap_x, tap_y = self.mock_adb.tap.call_args[0]
        self.assertAlmostEqual(tap_x, 1426, delta=60)
        self.assertAlmostEqual(tap_y, 828, delta=60)

    @patch("time.sleep", return_value=None)
    def test_chaos_obtain_screen_taps_obtain(self, mock_sleep):
        """Verify that in Mode.CHAOS, reward screen with Obtain taps obtain button."""
        self.engine.mode = Mode.CHAOS

        frames = [self.obtain, self.obtain, self.obtain, self.obtain]
        frame_idx = 0

        def fake_screencap():
            nonlocal frame_idx
            if frame_idx < len(frames):
                img = frames[frame_idx]
                frame_idx += 1
                return img
            self.engine._stop_event.set()
            self.engine.stop("Test finished")
            return self.obtain

        self.mock_adb.screencap = fake_screencap
        self.engine._run_loop()

        self.assertTrue(self.mock_adb.tap.called)
        tap_x, tap_y = self.mock_adb.tap.call_args[0]
        self.assertAlmostEqual(tap_x, 1380, delta=60)
        self.assertAlmostEqual(tap_y, 830, delta=60)

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
