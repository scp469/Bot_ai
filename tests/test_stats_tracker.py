"""
Unit tests for StatsTracker and its integration with BotEngine.
"""
import os
import json
import unittest
from unittest.mock import MagicMock
import numpy as np

from stats_tracker import StatsTracker
from bot_engine import BotEngine
from config import Mode, LeftButton


class TestStatsTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = StatsTracker()

    def test_initial_state(self):
        self.assertEqual(self.tracker.actions_done, 0)
        self.assertEqual(self.tracker.retries_done, 0)
        self.assertEqual(self.tracker.matches_completed, 0)
        self.assertEqual(self.tracker.avg_path_score, 0.0)
        self.assertEqual(self.tracker.avg_team_hp, 0.0)

    def test_record_actions_and_matches(self):
        self.tracker.record_action()
        self.tracker.record_action()
        self.assertEqual(self.tracker.actions_done, 2)

        self.tracker.record_retry()
        self.assertEqual(self.tracker.retries_done, 1)
        self.assertEqual(self.tracker.matches_completed, 1)

        self.tracker.record_match_completed()
        self.assertEqual(self.tracker.matches_completed, 2)

    def test_record_chaos_choices(self):
        self.tracker.record_chaos_choice("top", 1.5, 0.9)
        self.tracker.record_chaos_choice("Đảo Dưới (2 đảo)", 2.5, 0.7)
        self.tracker.record_chaos_choice("middle", 1.0, 0.8)
        self.tracker.record_chaos_choice("Đảo duy nhất", 0.0, 0.6)

        self.assertEqual(self.tracker.island_picks["top"], 1)
        self.assertEqual(self.tracker.island_picks["bottom"], 1)
        self.assertEqual(self.tracker.island_picks["middle"], 1)
        self.assertEqual(self.tracker.island_picks["single"], 1)

        # Average calculations
        self.assertAlmostEqual(self.tracker.avg_path_score, 1.25)
        self.assertAlmostEqual(self.tracker.avg_team_hp, 0.75)

    def test_format_summary_and_export_json(self):
        self.tracker.record_retry()
        self.tracker.record_action()
        self.tracker.record_chaos_choice("top", 2.0, 0.85)
        self.tracker.record_stop("Test complete")

        summary = self.tracker.format_summary()
        self.assertIn("BÁO CÁO PHIÊN CHẠY BOT", summary)
        self.assertIn("Test complete", summary)
        self.assertIn("Retries: 1", summary)
        self.assertIn("Thống kê Chế độ Chaos", summary)

        # Export JSON test
        tmp_json = os.path.join(os.path.dirname(__file__), "test_stats_export.json")
        try:
            exported_path = self.tracker.export_json(tmp_json)
            self.assertTrue(os.path.exists(exported_path))
            with open(exported_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["matches_completed"], 1)
            self.assertEqual(data["stop_reason"], "Test complete")
            self.assertEqual(data["chaos_stats"]["total_islands_selected"], 1)
        finally:
            if os.path.exists(tmp_json):
                os.remove(tmp_json)

    def test_bot_engine_stats_integration(self):
        """Verify that BotEngine interacts with its StatsTracker instance."""
        mock_adb = MagicMock()
        mock_det = MagicMock()
        engine = BotEngine(adb_client=mock_adb, detector=mock_det)
        engine.is_running = True
        engine.beep = MagicMock()
        dummy_screen = np.zeros((10, 10, 3), dtype=np.uint8)

        # Test action recording
        engine._execute_tap("TestTap", 100, 200)
        self.assertEqual(engine.stats.actions_done, 1)

        # Test retry recording in MATCH_DONE
        engine.mode = Mode.REPLAY
        engine._handle_match_done(dummy_screen, {"left_button": LeftButton.RETRY})
        self.assertEqual(engine.stats.retries_done, 1)

        # Test stop recording
        engine.stop("Integration test stop")
        self.assertEqual(engine.stats.stop_reason, "Integration test stop")


if __name__ == "__main__":
    unittest.main()
