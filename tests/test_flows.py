"""
Unit tests for modular Flows: ReplayFlow, ProgressFlow, StoryFlow, and ChaosFlow.
Tests state handling, action generation, and decision boundaries without requiring ADB or emulator.
"""
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from czn_bot.states import State, LeftButton
from czn_bot.coords import TAP_COORDS
from czn_bot.flows.base import ActionType
from czn_bot.flows.replay import ReplayFlow
from czn_bot.flows.progress import ProgressFlow
from czn_bot.flows.story import StoryFlow
from czn_bot.flows.chaos import ChaosFlow
from czn_bot.chaos.pathfinder import IslandChoice


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


class TestChaosFlow(unittest.TestCase):
    def setUp(self):
        self.flow = ChaosFlow(strategy="balanced", auto_pick_epiphany=True, enable_dynamic_islands=False)
        self.dummy_screen = np.zeros((100, 100, 3), dtype=np.uint8)

    @patch("czn_bot.flows.chaos.get_team_hp", return_value=(0.9, False))
    @patch("czn_bot.flows.chaos.parse_chaos_minimap", return_value=([], {}, {}, []))
    def test_chaos_map_empty_minimap_stops(self, mock_map, mock_hp):
        self.flow.max_map_retries = 1
        action = self.flow.handle(State.CHAOS_MAP, {}, self.dummy_screen)
        self.assertEqual(action.type, ActionType.STOP)
        self.assertIn("Không thể phân tích", action.reason)

    @patch("czn_bot.flows.chaos.get_team_hp", return_value=(0.9, False))
    @patch("czn_bot.flows.chaos.parse_chaos_minimap", return_value=([], {}, {}, []))
    def test_chaos_map_empty_minimap_waits_initially(self, mock_map, mock_hp):
        self.flow.max_map_retries = 5
        action = self.flow.handle(State.CHAOS_MAP, {}, self.dummy_screen)
        self.assertEqual(action.type, ActionType.WAIT)
        self.assertIn("Chờ minimap ổn định", action.name)

    @patch("czn_bot.flows.chaos.get_team_hp", return_value=(0.9, False))
    @patch("czn_bot.flows.chaos.parse_chaos_minimap", return_value=({IslandChoice.MIDDLE: "c1"}, {}, {}, ["boss"]))
    @patch("czn_bot.flows.chaos.select_best_island", return_value=(None, {}))
    def test_chaos_map_single_island_fallback(self, mock_path, mock_map, mock_hp):
        action = self.flow.handle(State.CHAOS_MAP, {}, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual(action.x, TAP_COORDS["chaos_island_1_middle"][0])
        self.assertEqual(action.y, TAP_COORDS["chaos_island_1_middle"][1])

    def test_chaos_equipment_selection(self):
        details = {"confirm_coord": (1360, 806)}
        action = self.flow.handle(State.CHAOS_EQUIPMENT, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        # Extra actions include equipping character and confirming
        self.assertTrue(len(action.extra.get("extra_actions", [])) >= 2)
        confirm_tap = action.extra["extra_actions"][-1]
        self.assertEqual(confirm_tap[0], "tap")
        self.assertEqual(confirm_tap[1], (1360, 806))

    def test_chaos_safe_zone_always_heals(self):
        details = {
            "rest_coord": TAP_COORDS["chaos_safe_zone_rest"],
            "confirm_coord": TAP_COORDS["chaos_safe_zone_confirm"],
            "skip_coord": TAP_COORDS["chaos_safe_zone_skip"]
        }
        action = self.flow.handle(State.CHAOS_SAFE_ZONE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        # Must tap Rest coord, NOT skip
        self.assertEqual(action.x, TAP_COORDS["chaos_safe_zone_rest"][0])
        self.assertEqual(action.y, TAP_COORDS["chaos_safe_zone_rest"][1])
        # Extra actions confirm rest
        confirm_tap = action.extra["extra_actions"][0]
        self.assertEqual(confirm_tap[0], "tap")
        self.assertEqual(confirm_tap[1], TAP_COORDS["chaos_safe_zone_confirm"])

    def test_chaos_safe_zone_modal_open_confirms_directly(self):
        """When Rest modal popup is already open, flow taps confirm directly."""
        details = {
            "is_modal_open": True,
            "confirm_coord": TAP_COORDS["chaos_safe_zone_confirm"],
            "rest_coord": TAP_COORDS["chaos_safe_zone_rest"],
            "skip_coord": TAP_COORDS["chaos_safe_zone_skip"]
        }
        action = self.flow.handle(State.CHAOS_SAFE_ZONE, details, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        # Must tap confirm coord directly (1055, 642)
        self.assertEqual(action.x, TAP_COORDS["chaos_safe_zone_confirm"][0])
        self.assertEqual(action.y, TAP_COORDS["chaos_safe_zone_confirm"][1])
        self.assertIn("Confirm Rest", action.name)

    def test_chaos_choose_epiphany_waits_when_disabled(self):
        self.flow.auto_pick_epiphany = False
        action = self.flow.handle(State.CHAOS_CHOOSE_EPIPHANY, {}, self.dummy_screen)
        self.assertEqual(action.type, ActionType.NONE)

    def test_chaos_choose_epiphany_autopick_stages(self):
        self.flow.auto_pick_epiphany = True
        # Stage 1: Waits for screen stabilization
        act1 = self.flow.handle(State.CHAOS_CHOOSE_EPIPHANY, {}, self.dummy_screen)
        self.assertEqual(act1.type, ActionType.NONE)

        # Stage 2: Selects card & confirms
        act2 = self.flow.handle(State.CHAOS_CHOOSE_EPIPHANY, {}, self.dummy_screen)
        self.assertEqual(act2.type, ActionType.TAP)
        self.assertEqual(act2.x, 390)
        self.assertEqual(act2.y, 450)
        self.assertEqual(act2.extra["extra_actions"][0], ("tap", (1425, 835)))

        # Stage 2 fallback (no screen / no cards): verify center fallback (800, 450)
        self.flow._epiphany_wait_count = 2
        act_fb = self.flow.handle(State.CHAOS_CHOOSE_EPIPHANY, {}, None)
        self.assertEqual(act_fb.type, ActionType.TAP)
        self.assertEqual(act_fb.x, 800)
        self.assertEqual(act_fb.y, 450)
        self.assertEqual(act_fb.extra["extra_actions"][0], ("tap", (1425, 835)))

    def test_chaos_choose_epiphany_subscreens(self):
        """Verify distinct sub-screen handling for choose_fate, select_attribute, remove_card, etched_memory."""
        self.flow.auto_pick_epiphany = True

        # 1. choose_fate
        self.flow._epiphany_wait_count = 2
        act_fate = self.flow.handle(State.CHAOS_CHOOSE_EPIPHANY, {"type": "choose_fate"}, self.dummy_screen)
        self.assertEqual(act_fate.type, ActionType.TAP)
        self.assertIn("Choose Fate", act_fate.name)
        self.assertEqual(act_fate.extra["extra_actions"][0], ("tap", (1425, 835)))

        # 2. select_attribute
        self.flow._epiphany_wait_count = 2
        act_attr = self.flow.handle(State.CHAOS_CHOOSE_EPIPHANY, {"type": "select_attribute"}, self.dummy_screen)
        self.assertEqual(act_attr.type, ActionType.TAP)
        self.assertEqual(act_attr.x, 800)
        self.assertEqual(act_attr.y, 500)
        self.assertEqual(act_attr.extra["extra_actions"][0], ("tap", (1425, 835)))

        # 3. remove_card
        self.flow._epiphany_wait_count = 2
        act_rem = self.flow.handle(State.CHAOS_CHOOSE_EPIPHANY, {"type": "remove_card"}, self.dummy_screen)
        self.assertEqual(act_rem.type, ActionType.TAP)
        self.assertEqual(act_rem.x, 400)
        self.assertEqual(act_rem.y, 450)
        self.assertEqual(act_rem.extra["extra_actions"][0], ("tap", (1360, 806)))

        # 4. etched_memory
        self.flow._epiphany_wait_count = 2
        act_mem = self.flow.handle(State.CHAOS_CHOOSE_EPIPHANY, {"type": "etched_memory"}, self.dummy_screen)
        self.assertEqual(act_mem.type, ActionType.TAP)
        self.assertEqual(act_mem.x, 800)
        self.assertEqual(act_mem.y, 500)
        self.assertEqual(act_mem.extra["extra_actions"][0], ("tap", (800, 850)))

    def test_chaos_after_battle(self):
        action = self.flow.handle(State.CHAOS_AFTER_BATTLE, {}, self.dummy_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual(action.x, TAP_COORDS["chaos_leave_button"][0])
        self.assertEqual(action.y, TAP_COORDS["chaos_leave_button"][1])
        self.assertEqual(self.flow.matches_completed, 1)


if __name__ == "__main__":
    unittest.main()
