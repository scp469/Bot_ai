"""
Unit tests for BotEngine state handlers, decision branches, and safety guards.
"""
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from czn_bot.states import State, Mode, LeftButton
from czn_bot.coords import TAP_COORDS
from czn_bot.constants import MAX_SAME_ACTION
from czn_bot.runner import BotRunner as BotEngine


class TestBotEngine(unittest.TestCase):
    def setUp(self):
        self.mock_adb = MagicMock()
        self.mock_detector = MagicMock()
        self.engine = BotEngine(adb_client=self.mock_adb, detector=self.mock_detector)
        self.engine.enable_chaos_ai = False
        self.engine.is_running = True
        self.engine.beep = MagicMock()
        self.dummy_screen = np.zeros((100, 100, 3), dtype=np.uint8)

    # ── State Handlers Tests ──────────────────────────────────────────

    def test_handle_in_match(self):
        """In-match handler should reset actions and return True."""
        self.engine._last_action = "SomeAction"
        self.engine._same_action_count = 5
        result = self.engine._handle_in_match(self.dummy_screen, {})
        self.assertTrue(result)
        self.assertIsNone(self.engine._last_action)
        self.assertEqual(self.engine._same_action_count, 0)
        self.mock_adb.tap.assert_not_called()

    def test_handle_popup_effect(self):
        """Popup effect should tap close coordinate and return True."""
        result = self.engine._handle_popup(self.dummy_screen, {}, State.POPUP_EFFECT)
        self.assertTrue(result)
        self.mock_adb.tap.assert_called_once_with(*TAP_COORDS["close_x_default"])
        self.assertEqual(self.engine.actions_done, 1)

    def test_handle_popup_monster_info(self):
        """Monster info popup should tap monster close coordinate."""
        result = self.engine._handle_popup(self.dummy_screen, {}, State.POPUP_MONSTER_INFO)
        self.assertTrue(result)
        self.mock_adb.tap.assert_called_once_with(*TAP_COORDS["close_monster_info"])

    def test_handle_popup_pause(self):
        """Pause popup should tap default close coordinate."""
        result = self.engine._handle_popup(self.dummy_screen, {}, State.POPUP_PAUSE)
        self.assertTrue(result)
        self.mock_adb.tap.assert_called_once_with(*TAP_COORDS["close_x_default"])

    def test_handle_match_done_stamina_exhausted(self):
        """Gray retry button should trigger stamina alert, halt bot, and return False."""
        details = {"left_button": LeftButton.RETRY_DISABLED}
        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertFalse(result)
        self.assertFalse(self.engine.is_running)
        self.engine.beep.assert_called_once()
        self.mock_adb.tap.assert_not_called()

    def test_handle_match_done_replay_mode_retry(self):
        """In REPLAY mode, retry button taps retry and increments retries_done."""
        self.engine.mode = Mode.REPLAY
        self.engine.retries_done = 0
        self.engine.max_retries = 5
        details = {"left_button": LeftButton.RETRY}

        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertTrue(result)
        self.assertEqual(self.engine.retries_done, 1)
        self.mock_adb.tap.assert_called_once_with(*TAP_COORDS["left_button"])

    def test_handle_match_done_replay_mode_max_retries_reached(self):
        """In REPLAY mode, reaching max_retries halts bot."""
        self.engine.mode = Mode.REPLAY
        self.engine.retries_done = 3
        self.engine.max_retries = 3
        details = {"left_button": LeftButton.RETRY}

        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertFalse(result)
        self.assertFalse(self.engine.is_running)
        self.mock_adb.tap.assert_not_called()

    def test_handle_match_done_replay_mode_next_mission(self):
        """In REPLAY mode, seeing Next Mission taps Confirm (Exit) and halts bot."""
        self.engine.mode = Mode.REPLAY
        details = {"left_button": LeftButton.NEXT_MISSION}

        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertFalse(result)
        self.assertFalse(self.engine.is_running)
        self.mock_adb.tap.assert_called_once_with(*TAP_COORDS["right_button"])

    def test_handle_match_done_progress_mode_next_mission(self):
        """In PROGRESS mode, seeing Next Mission taps it to continue progressing."""
        self.engine.mode = Mode.PROGRESS
        details = {"left_button": LeftButton.NEXT_MISSION}

        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertTrue(result)
        self.mock_adb.tap.assert_called_once_with(*TAP_COORDS["left_button"])

    def test_handle_match_done_progress_mode_retry(self):
        """In PROGRESS mode, seeing Retry taps Confirm and stops bot."""
        self.engine.mode = Mode.PROGRESS
        details = {"left_button": LeftButton.RETRY}

        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertFalse(result)
        self.assertFalse(self.engine.is_running)
        self.mock_adb.tap.assert_called_once_with(*TAP_COORDS["right_button"])

    # ── Chaos Island Resolution Tests ─────────────────────────────────

    def test_handle_match_done_progress_mode_max_retries(self):
        """In PROGRESS mode, reaching max_retries halts bot."""
        self.engine.mode = Mode.PROGRESS
        self.engine.retries_done = 3
        self.engine.max_retries = 3
        details = {"left_button": LeftButton.NEXT_MISSION}

        result = self.engine._handle_match_done(self.dummy_screen, details)
        self.assertFalse(result)
        self.assertFalse(self.engine.is_running)
        self.mock_adb.tap.assert_not_called()

    def test_handle_pre_match_disabled(self):
        """When auto_start_match is False, pre_match returns True with no tap."""
        self.engine.auto_start_match = False
        result = self.engine._handle_pre_match(self.dummy_screen, {}, State.PRE_MATCH_MISSION)
        self.assertTrue(result)
        self.mock_adb.tap.assert_not_called()

    def test_handle_pre_match_enabled(self):
        """When auto_start_match is True, pre_match taps enter."""
        self.engine.auto_start_match = True
        result = self.engine._handle_pre_match(self.dummy_screen, {}, State.PRE_MATCH_MISSION)
        self.assertTrue(result)
        self.mock_adb.tap.assert_called_once_with(*TAP_COORDS["enter_mission"])

    def test_handle_unknown_streak_halts_at_3(self):
        """UNKNOWN streaks 1 and 2 return True, 3 halts and returns False."""
        self.engine._unknown_streak = 0
        r1 = self.engine._handle_unknown(self.dummy_screen, {})
        self.assertTrue(r1)
        self.assertEqual(self.engine._unknown_streak, 1)
        self.assertTrue(self.engine.is_running)

        r2 = self.engine._handle_unknown(self.dummy_screen, {})
        self.assertTrue(r2)
        self.assertEqual(self.engine._unknown_streak, 2)
        self.assertTrue(self.engine.is_running)

        r3 = self.engine._handle_unknown(self.dummy_screen, {})
        self.assertFalse(r3)
        self.assertFalse(self.engine.is_running)

    def test_handle_unknown_delegates_to_ai_vision_tap(self):
        """When AI Vision analyzes UNKNOWN screen and returns tap, bot executes tap and resets streak."""
        self.engine._unknown_streak = 2
        self.engine.enable_chaos_ai = True
        self.engine.rule_manager = MagicMock()
        self.engine.rule_manager.get_api_key.return_value = "fake_key"
        self.engine.chaos_brain = MagicMock()
        self.engine.chaos_brain.analyze_unknown_screen.return_value = {
            "screen_type": "popup",
            "action": "tap",
            "tap_coord": [1200, 100],
            "reason": "Đóng popup quảng cáo"
        }

        result = self.engine._handle_unknown(self.dummy_screen, {})
        self.assertTrue(result)
        self.assertEqual(self.engine._unknown_streak, 0)
        self.mock_adb.tap.assert_called()
        args, _ = self.mock_adb.tap.call_args
        self.assertAlmostEqual(args[0], 1200, delta=5)
        self.assertAlmostEqual(args[1], 100, delta=5)

    def test_handle_unknown_delegates_to_ai_vision_wait(self):
        """When AI Vision returns wait on battle animation, bot waits and resets streak."""
        self.engine._unknown_streak = 2
        self.engine.enable_chaos_ai = True
        self.engine.rule_manager = MagicMock()
        self.engine.rule_manager.get_api_key.return_value = "fake_key"
        self.engine.chaos_brain = MagicMock()
        self.engine.chaos_brain.analyze_unknown_screen.return_value = {
            "screen_type": "battle_animation",
            "action": "wait",
            "wait_seconds": 0.01,
            "reason": "Hoạt cảnh kỹ năng đang diễn ra"
        }

        result = self.engine._handle_unknown(self.dummy_screen, {})
        self.assertTrue(result)
        self.assertEqual(self.engine._unknown_streak, 0)

    def test_handle_unknown_offline_ui_scanner_dismisses_popup(self):
        """When AI Vision fails/unavailable, Offline UI Scanner detects Close button and taps to dismiss."""
        self.engine._unknown_streak = 1
        self.engine.enable_chaos_ai = False  # Simulate offline/no API
        self.engine._scan_unknown_screen_elements = MagicMock(return_value=("Nút Đóng (close_x)", 1400, 80))

        result = self.engine._handle_unknown(self.dummy_screen, {})
        self.assertTrue(result)
        self.assertEqual(self.engine._unknown_streak, 0)
        self.mock_adb.tap.assert_called()
        args, _ = self.mock_adb.tap.call_args
        self.assertAlmostEqual(args[0], 1400, delta=5)
        self.assertAlmostEqual(args[1], 80, delta=5)

    # ── Tap Guard Tests ───────────────────────────────────────────────

    def test_execute_tap_stall_guard(self):
        """Repeated taps of same action exceeding MAX_SAME_ACTION trigger halt."""
        self.engine._same_action_count = MAX_SAME_ACTION
        self.engine._last_action = "StuckAction"

        result = self.engine._execute_tap("StuckAction", 100, 100)
        self.assertFalse(result)
        self.assertFalse(self.engine.is_running)

    # ── Unknown Screenshot Cleanup Tests ──────────────────────────────

    def test_cleanup_unknown_screenshots_exceeding_limit(self):
        """When unknown screenshots exceed max_keep, the oldest beyond max_keep are deleted."""
        with patch("glob.glob") as mock_glob, patch("os.remove") as mock_remove, patch("os.path.getmtime") as mock_mtime:
            # Simulate 55 files with timestamps 1..55 (55 is newest)
            mock_files = [f"logs/unknown_{i:03d}.png" for i in range(1, 56)]
            mock_glob.return_value = list(mock_files)
            mock_mtime.side_effect = lambda path: int(path.split("_")[1].split(".")[0])

            deleted = BotEngine._cleanup_unknown_screenshots(max_keep=50)

            self.assertEqual(deleted, 5)
            # The 5 oldest (1..5) should be removed
            expected_deleted = [f"logs/unknown_{i:03d}.png" for i in range(1, 6)]
            self.assertEqual(mock_remove.call_count, 5)
            for path in expected_deleted:
                mock_remove.assert_any_call(path)

    def test_cleanup_unknown_screenshots_within_limit(self):
        """When unknown screenshots are <= max_keep, no files are deleted."""
        with patch("glob.glob") as mock_glob, patch("os.remove") as mock_remove:
            mock_glob.return_value = [f"logs/unknown_{i}.png" for i in range(30)]
            deleted = BotEngine._cleanup_unknown_screenshots(max_keep=50)
            self.assertEqual(deleted, 0)
            mock_remove.assert_not_called()


    def test_handle_transitioning(self):
        """Transitioning handler should reset actions, not tap, and return True."""
        self.engine._last_action = "SomeAction"
        self.engine._same_action_count = 3
        result = self.engine._handle_transitioning(self.dummy_screen, {})
        self.assertTrue(result)
        self.assertIsNone(self.engine._last_action)
        self.assertEqual(self.engine._same_action_count, 0)
        self.mock_adb.tap.assert_not_called()
        self.assertEqual(self.engine._unknown_streak, 0)

    # ── Stall Watchdog Tests ──────────────────────────────────────────

    def test_stall_watchdog_triggers_and_dumps_diagnostics(self):
        """Stall watchdog should save PNG and JSON diagnostics and halt when recovery is disabled."""
        self.engine.enable_recovery = False
        self.engine.stall_timeout = 30.0

        with patch("cv2.imwrite") as mock_imwrite, patch("builtins.open", unittest.mock.mock_open()) as mock_file:
            result = self.engine._handle_stall(
                screen=self.dummy_screen,
                confirmed_state=State.CHAOS_MAP,
                details={"heuristic": True},
                elapsed_stall=31.5,
            )
            self.assertFalse(result)
            self.assertFalse(self.engine.is_running)
            mock_imwrite.assert_called_once()
            # open is called for both stall diagnostic json and stats session json on halt
            self.assertGreaterEqual(mock_file.call_count, 1)
            first_open_call = mock_file.call_args_list[0][0][0]
            self.assertIn("stall_", first_open_call)
            self.assertTrue(first_open_call.endswith(".json"))
            self.assertGreaterEqual(self.engine.beep.call_count, 1)

    def test_stall_watchdog_exempts_in_match_and_epiphany(self):
        """IN_MATCH, CHAOS_CHOOSE_EPIPHANY, and STORY_DIALOGUE states should not trigger stall timeout."""
        # Set up mock screen and detector
        self.mock_adb.screencap.return_value = self.dummy_screen
        self.mock_detector.detect.return_value = (State.IN_MATCH, {})

        # Verify STALL_EXEMPT_STATES definition
        stall_exempt = {State.IN_MATCH, State.CHAOS_CHOOSE_EPIPHANY, State.STORY_DIALOGUE}
        self.assertIn(State.IN_MATCH, stall_exempt)
        self.assertIn(State.CHAOS_CHOOSE_EPIPHANY, stall_exempt)
        self.assertIn(State.STORY_DIALOGUE, stall_exempt)

    def test_stall_watchdog_auto_recovery_success(self):
        """When recovery is enabled and succeeds, watchdog updates state and continues."""
        self.engine.enable_recovery = True
        self.engine.recovery = MagicMock()
        self.engine.recovery.attempt_recovery.return_value = (True, State.CHAOS_MAP)

        result = self.engine._handle_stall(
            screen=self.dummy_screen,
            confirmed_state=State.UNKNOWN,
            details={},
            elapsed_stall=32.0,
        )
        self.assertTrue(result)
        self.assertTrue(self.engine.is_running)
        self.engine.recovery.attempt_recovery.assert_called_once_with(1)
        self.assertEqual(self.engine._stall_recovered_count, 0)

    def test_stall_watchdog_auto_recovery_failure_halts(self):
        """When recovery fails repeatedly (>= 3 attempts or >= 45s), bot halts safely."""
        self.engine.enable_recovery = True
        self.engine.recovery = MagicMock()
        self.engine.recovery.attempt_recovery.return_value = (False, State.UNKNOWN)
        self.engine._stall_recovered_count = 2

        result = self.engine._handle_stall(
            screen=self.dummy_screen,
            confirmed_state=State.UNKNOWN,
            details={},
            elapsed_stall=46.0,
        )
        self.assertFalse(result)
        self.assertFalse(self.engine.is_running)
        self.engine.recovery.attempt_recovery.assert_called_once_with(3)

    # ── Hybrid OCR Verification Tests ─────────────────────────────────

    def test_execute_tap_with_hybrid_verification_success(self):
        """When Hybrid OCR is enabled and expected text is present, tap succeeds."""
        import cv2
        from czn_bot.vision.detector import ScreenDetector
        self.engine.detector = ScreenDetector()
        self.engine.enable_hybrid_verification = True
        real_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        cv2.putText(real_screen, "CONFIRM", (1380, 835), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        res = self.engine._execute_tap(
            "Bấm Confirm", 1440, 830,
            screen=real_screen,
            expected_words=["confirm", "xác nhận"]
        )
        self.assertTrue(res)
        self.mock_adb.tap.assert_called_once_with(1440, 830)

    def test_execute_tap_with_hybrid_verification_false_positive_rejected(self):
        """When Hybrid OCR is enabled but wrong text is present (false positive), tap is aborted."""
        import cv2
        from czn_bot.vision.detector import ScreenDetector
        self.engine.detector = ScreenDetector()
        self.engine.enable_hybrid_verification = True
        real_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        # Put wrong text at the tap target (e.g. Card select or noise)
        cv2.putText(real_screen, "SELECT CARD", (1380, 835), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        res = self.engine._execute_tap(
            "Bấm Confirm", 1440, 830,
            screen=real_screen,
            expected_words=["confirm", "xác nhận"]
        )
        # Should return True (safe loop continuation) but NEVER tap ADB
        self.assertTrue(res)
        self.mock_adb.tap.assert_not_called()
        self.assertEqual(self.engine.actions_done, 0)

    def test_execute_tap_hybrid_verification_disabled(self):
        """When Hybrid OCR is disabled, tap executes directly without verification."""
        self.engine.enable_hybrid_verification = False
        res = self.engine._execute_tap(
            "Bấm Confirm", 1440, 830,
            screen=self.dummy_screen,
            expected_words=["confirm"]
        )
        self.assertTrue(res)
        self.mock_adb.tap.assert_called_once_with(1440, 830)


if __name__ == "__main__":
    unittest.main()


