"""
Unit tests for modular Flows: ReplayFlow, ProgressFlow, StoryFlow, and ChaosFlow.
Tests state handling, action generation, and decision boundaries without requiring ADB or emulator.
"""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import cv2

from czn_bot.states import State, LeftButton
from czn_bot.coords import TAP_COORDS
from czn_bot.flows.base import ActionType
from czn_bot.flows.replay import ReplayFlow
from czn_bot.flows.progress import ProgressFlow
from czn_bot.flows.story import StoryFlow


class TestReplayFlow(unittest.TestCase):
    def setUp(self):
        self.flow = ReplayFlow(max_retries=3, auto_start_match=True)
        self.dummy_screen = np.zeros((100, 100, 3), dtype=np.uint8)

    def test_in_match_returns_none(self):
        action = self.flow.handle(State.IN_MATCH, {}, self.dummy_screen)
        self.assertEqual(action.type, ActionType.NONE)

    def test_match_done_retry_success(self):
        details = {"left_button": LeftButton.RETRY}
        action = self.flow.handle(State.MATCH_DONE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual(action.x, TAP_COORDS["left_button"][0])
        self.assertEqual(action.y, TAP_COORDS["left_button"][1])
        self.assertEqual(action.extra.get("retry_number"), 1)
        self.assertEqual(self.flow.retries_done, 1)

    def test_match_done_retry_stamina_exhausted(self):
        details = {"left_button": LeftButton.RETRY_DISABLED}
        action = self.flow.handle(State.MATCH_DONE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.STOP)
        self.assertIn("Hết thể lực", action.reason)

    def test_match_done_max_retries_reached(self):
        self.flow.retries_done = 3
        details = {"left_button": LeftButton.RETRY}
        action = self.flow.handle(State.MATCH_DONE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.STOP)
        self.assertIn("giới hạn", action.reason)

    def test_match_done_next_mission_halts_and_confirms(self):
        details = {"left_button": LeftButton.NEXT_MISSION}
        action = self.flow.handle(State.MATCH_DONE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual(action.x, TAP_COORDS["right_button"][0])
        self.assertEqual(action.y, TAP_COORDS["right_button"][1])
        self.assertTrue(action.extra.get("halt_after"))

    def test_popups_tap_close(self):
        action = self.flow.handle(State.POPUP_EFFECT, {}, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual(action.x, TAP_COORDS["close_x_default"][0])

        action_mon = self.flow.handle(State.POPUP_MONSTER_INFO, {}, self.dummy_screen)
        self.assertEqual(action_mon.type, ActionType.TAP)
        self.assertEqual(action_mon.x, TAP_COORDS["close_monster_info"][0])

    def test_pre_match_auto_start(self):
        action = self.flow.handle(State.PRE_MATCH_MISSION, {}, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual(action.x, TAP_COORDS["enter_mission"][0])


class TestProgressFlow(unittest.TestCase):
    def setUp(self):
        self.flow = ProgressFlow(max_stages=2)
        self.dummy_screen = np.zeros((100, 100, 3), dtype=np.uint8)

    def test_match_done_next_mission(self):
        details = {"left_button": LeftButton.NEXT_MISSION}
        action = self.flow.handle(State.MATCH_DONE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual(action.x, TAP_COORDS["left_button"][0])
        self.assertEqual(action.extra.get("stage_number"), 1)
        self.assertEqual(self.flow.stages_done, 1)

    def test_match_done_max_stages_reached(self):
        self.flow.stages_done = 2
        details = {"left_button": LeftButton.NEXT_MISSION}
        action = self.flow.handle(State.MATCH_DONE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.STOP)
        self.assertIn("Đã đạt giới hạn", action.reason)

    def test_match_done_retry_stops_flow(self):
        details = {"left_button": LeftButton.RETRY}
        action = self.flow.handle(State.MATCH_DONE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual(action.x, TAP_COORDS["right_button"][0])
        self.assertTrue(action.extra.get("halt_after"))


class TestStoryFlow(unittest.TestCase):
    def setUp(self):
        self.flow = StoryFlow(max_stages=3)
        self.dummy_screen = np.zeros((100, 100, 3), dtype=np.uint8)

    def test_dialogue_fast_forward_priority(self):
        details = {
            "skip_coord": (1272, 48),
            "auto_coord": (1395, 48),
        }
        action = self.flow.handle(State.STORY_DIALOGUE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual(action.x, 1395)
        self.assertEqual(action.y, 48)
        self.assertTrue(action.extra.get("dialogue_skip"))
        self.assertTrue(len(action.extra.get("extra_actions", [])) >= 4)

    def test_story_map_swipes_when_no_enter_button(self):
        action = self.flow.handle(State.STORY_MAP, {}, self.dummy_screen)
        self.assertEqual(action.type, ActionType.SWIPE)
        self.assertEqual(self.flow.swipe_count, 1)

    def test_story_map_advances_chapter_after_3_swipes(self):
        self.flow.swipe_count = 3
        action = self.flow.handle(State.STORY_MAP, {}, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual(action.x, TAP_COORDS["story_chapter_next"][0])
        self.assertEqual(self.flow.swipe_count, 0)

    def test_story_defeat_halts(self):
        details = {
            "left_button": LeftButton.RETRY,
            "reward_score": 0.2,
            "confirm_score": 0.3,
        }
        action = self.flow.handle(State.MATCH_DONE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.STOP)
        self.assertTrue(action.extra.get("defeat"))


if __name__ == "__main__":
    unittest.main()
