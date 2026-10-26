"""
Unit tests for RecoveryManager and its integration with BotEngine.
"""
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from recovery import RecoveryManager
from bot_engine import BotEngine
from config import State


class TestRecoveryManager(unittest.TestCase):
    def setUp(self):
        self.mock_adb = MagicMock()
        self.mock_detector = MagicMock()
        self.recovery = RecoveryManager(adb_client=self.mock_adb, detector=self.mock_detector)

    @patch("time.sleep", return_value=None)
    def test_stage_1_recovery_tap_top_right(self, mock_sleep):
        """Stage 1 attempts to tap primary top-right popup close."""
        self.mock_detector.detect.return_value = (State.IN_MATCH, {})
        recovered, state = self.recovery.attempt_recovery(1)

        expected_coord = RecoveryManager.CANDIDATE_DISMISS_COORDS[0]
        self.mock_adb.tap.assert_called_once_with(*expected_coord)
        self.assertTrue(recovered)
        self.assertEqual(state, State.IN_MATCH)
        self.assertEqual(self.recovery.recovery_successes, 1)

    @patch("time.sleep", return_value=None)
    def test_stage_2_recovery_tap_alternate(self, mock_sleep):
        """Stage 2 attempts to tap alternate dismiss coordinate."""
        self.mock_detector.detect.return_value = (State.UNKNOWN, {})
        recovered, state = self.recovery.attempt_recovery(2)

        expected_coord = RecoveryManager.CANDIDATE_DISMISS_COORDS[1]
        self.mock_adb.tap.assert_called_once_with(*expected_coord)
        self.assertFalse(recovered)
        self.assertEqual(state, State.UNKNOWN)

    @patch("time.sleep", return_value=None)
    def test_stage_3_recovery_send_back_key(self, mock_sleep):
        """Stage 3 sends Android BACK keyevent 4."""
        self.mock_detector.detect.return_value = (State.MATCH_DONE, {})
        recovered, state = self.recovery.attempt_recovery(3)

        self.mock_adb.send_keyevent.assert_called_once_with(4)
        self.assertTrue(recovered)
        self.assertEqual(state, State.MATCH_DONE)


class TestBotEngineRecoveryIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_adb = MagicMock()
        self.mock_det = MagicMock()
        self.mock_recovery = MagicMock()
        self.engine = BotEngine(
            adb_client=self.mock_adb,
            detector=self.mock_det,
            recovery_manager=self.mock_recovery,
        )
        self.engine.enable_recovery = True
        self.engine.is_running = True
        self.engine.beep = MagicMock()
        self.dummy_screen = np.zeros((10, 10, 3), dtype=np.uint8)

    def test_successful_recovery_resets_unknown_streak(self):
        """When recovery succeeds, unknown streak is reset to 0 and loop continues."""
        self.engine._unknown_streak = 0
        self.mock_recovery.attempt_recovery.return_value = (True, State.IN_MATCH)

        result = self.engine._handle_unknown(self.dummy_screen, {})
        self.assertTrue(result)
        self.assertEqual(self.engine._unknown_streak, 0)
        self.assertTrue(self.engine.is_running)

    def test_failed_recovery_progresses_streak_to_halt(self):
        """When recovery fails, streak increases and safely halts at 3."""
        self.mock_recovery.attempt_recovery.return_value = (False, State.UNKNOWN)

        self.engine._unknown_streak = 2
        result = self.engine._handle_unknown(self.dummy_screen, {})
        self.assertFalse(result)
        self.assertFalse(self.engine.is_running)


if __name__ == "__main__":
    unittest.main()
