"""
Tests for Giai đoạn 2.5: Real Image Verification and Safety Guardrails.
Tests run on real fixture images in tests/fixtures/states/ and tests/fixtures/ without mocking.
"""
import os
import cv2
import pytest
import numpy as np

from czn_bot.states import State
from czn_bot.vision.detector import ScreenDetector
from czn_bot.vision.map_reader import detect_3d_island_coords
from czn_bot.chaos.pathfinder import IslandChoice
from czn_bot.runner import BotRunner
from czn_bot.flows.chaos import ChaosFlow
from czn_bot.flows.base import ActionType
from czn_bot.constants import (
    SETTLEMENT_TEMP_RETURN_BOX,
    SETTLEMENT_OBTAIN_VOUCHER_BOX,
    OBTAIN_SKIP_BOX,
    DUPLICATE_SKIP_BOX,
    EVENT_SWORD_BTN_BOX,
)

FIXTURES_DIR = os.path.join("tests", "fixtures", "states")


@pytest.fixture(scope="module")
def detector():
    return ScreenDetector()


@pytest.fixture(scope="module")
def chaos_flow():
    return ChaosFlow()


@pytest.fixture(scope="module")
def runner():
    return BotRunner()


class TestStateClassification21Fixtures:
    """Verifies that all 21 new fixture images classify into the correct State with high confidence."""

    def test_choose_fate(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "choose_fate.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_CHOOSE_FATE
        assert details["confidence"] >= 0.75

    def test_equipment_row1_selected(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "equipment_row1_selected.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_EQUIPMENT
        assert details["confidence"] >= 0.75

    def test_equipment_row3_selected(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "equipment_row3_selected.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_EQUIPMENT
        assert details["confidence"] >= 0.75

    def test_event_3choices(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "event_3choices.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_EVENT
        assert details["confidence"] >= 0.75

    def test_event_waypoint_single(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "event_waypoint_single.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_EVENT
        assert details["confidence"] >= 0.75

    def test_map_1island(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "map_1island.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_MAP
        assert details["confidence"] >= 0.75

    def test_map_2islands(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "map_2islands.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_MAP
        assert details["confidence"] >= 0.75

    def test_map_3islands(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "map_3islands.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_MAP
        assert details["confidence"] >= 0.75

    def test_obtain_credits_only(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "obtain_credits_only.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_OBTAIN_REWARD
        assert details["confidence"] >= 0.75

    def test_obtain_duplicate_card(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "obtain_duplicate_card.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_OBTAIN_REWARD
        assert details["confidence"] >= 0.75

    def test_obtain_equipment_credits(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "obtain_equipment_credits.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_OBTAIN_REWARD
        assert details["confidence"] >= 0.75

    def test_obtain_equipment_done(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "obtain_equipment_done.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_OBTAIN_REWARD
        assert details["confidence"] >= 0.75

    def test_obtain_equipment_highlight(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "obtain_equipment_highlight.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_OBTAIN_REWARD
        assert details["confidence"] >= 0.70

    def test_rest_dialog(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "rest_dialog.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_SAFE_ZONE
        assert details.get("is_modal_open") is True
        assert details.get("confirm_coord") == (1055, 642)

    def test_safe_zone(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "safe_zone.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_SAFE_ZONE
        assert details["confidence"] >= 0.75

    def test_safe_zone_shop(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "safe_zone_shop.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_SAFE_ZONE
        assert details["confidence"] >= 0.75

    def test_select_duplicate_card(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "select_duplicate_card.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_SELECT_DUPLICATE_CARD
        assert details["confidence"] >= 0.75

    def test_settlement_button(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "settlement_button.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_AFTER_BATTLE
        assert details["confidence"] >= 0.75

    def test_settlement_confirm_dialog(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "settlement_confirm_dialog.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_SETTLEMENT
        assert details.get("is_modal_open") is True
        assert details.get("confirm_coord") == (1055, 569)

    def test_settlement_screen_1(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "settlement_screen_1.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_SETTLEMENT
        assert details["confidence"] >= 0.75

    def test_settlement_screen_2(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "settlement_screen_2.png"))
        state, details = detector.detect(img)
        assert state == State.CHAOS_SETTLEMENT
        assert details["confidence"] >= 0.75


class TestModalDialogDetection:
    """Verifies HSV modal confirmation button detection in region (800, 500, 1300, 700)."""

    def test_detect_modal_dialog_loot(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "settlement_confirm_dialog.png"))
        is_modal, pt = detector.detect_modal_dialog(img)
        assert is_modal is True
        assert pt == (1055, 569)

    def test_detect_modal_dialog_rest(self, detector):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "rest_dialog.png"))
        is_modal, pt = detector.detect_modal_dialog(img)
        assert is_modal is True
        assert pt == (1055, 642)

    def test_detect_modal_dialog_false_positives(self, detector):
        non_dialogs = [
            "map_1island.png",
            "map_3islands.png",
            "event_3choices.png",
            "settlement_screen_1.png",
            "equipment_row1_selected.png",
        ]
        for fn in non_dialogs:
            img = cv2.imread(os.path.join(FIXTURES_DIR, fn))
            is_modal, pt = detector.detect_modal_dialog(img)
            assert is_modal is False, f"False positive modal detection on {fn}"
            assert pt is None


class TestMap3DIslandDetection:
    """Verifies arrow + flag lane detection and safe body tap points."""

    def test_map_1island_lane(self):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "map_1island.png"))
        res = detect_3d_island_coords(img)
        assert IslandChoice.MIDDLE in res
        assert IslandChoice.TOP not in res
        assert IslandChoice.BOTTOM not in res
        assert res[IslandChoice.MIDDLE] == (1290, 475)

    def test_map_2islands_lanes(self):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "map_2islands.png"))
        res = detect_3d_island_coords(img)
        assert IslandChoice.TOP in res
        assert IslandChoice.MIDDLE in res
        assert IslandChoice.BOTTOM not in res
        assert res[IslandChoice.TOP] == (1070, 200)
        assert res[IslandChoice.MIDDLE] == (1290, 475)

    def test_map_3islands_lanes(self):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "map_3islands.png"))
        res = detect_3d_island_coords(img)
        assert IslandChoice.TOP in res
        assert IslandChoice.MIDDLE in res
        assert IslandChoice.BOTTOM in res
        assert res[IslandChoice.TOP] == (1070, 200)
        assert res[IslandChoice.MIDDLE] == (1290, 475)
        assert res[IslandChoice.BOTTOM] == (1090, 730)

    def test_map_negative_pin_score(self):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "map_3islands.png"))
        res = detect_3d_island_coords(img, pin_score=0.60)
        assert res == {}

    def test_map_negative_settlement_title(self):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "settlement_screen_1.png"))
        res = detect_3d_island_coords(img)
        assert res == {}

    def test_map_negative_equipment_title(self):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "equipment_row1_selected.png"))
        res = detect_3d_island_coords(img)
        assert res == {}


class TestCombatantRowSelection:
    """Verifies 2-signal border + connecting bar detection of selected combatant row."""

    def test_row1_selected(self, chaos_flow):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "equipment_row1_selected.png"))
        row = chaos_flow._detect_selected_combatant_row(img)
        assert row == 0

    def test_row3_selected(self, chaos_flow):
        img = cv2.imread(os.path.join(FIXTURES_DIR, "equipment_row3_selected.png"))
        row = chaos_flow._detect_selected_combatant_row(img)
        assert row == 2

    def test_row2_selected(self, chaos_flow):
        img = cv2.imread(os.path.join("tests", "fixtures", "chaos_equipment_ready.png"))
        row = chaos_flow._detect_selected_combatant_row(img)
        assert row == 1


class TestTapGuards:
    """Verifies that taps into dangerous boxes are strictly blocked."""

    def test_settlement_temporary_return_blocked(self, runner):
        runner.current_state = State.CHAOS_SETTLEMENT
        x = (SETTLEMENT_TEMP_RETURN_BOX[0] + SETTLEMENT_TEMP_RETURN_BOX[2]) // 2
        y = (SETTLEMENT_TEMP_RETURN_BOX[1] + SETTLEMENT_TEMP_RETURN_BOX[3]) // 2
        allowed, reason = runner._check_tap_guards("Tap Temp Return", x, y)
        assert allowed is False
        assert "Temporary Return" in reason

    def test_settlement_obtain_voucher_blocked(self, runner):
        runner.current_state = State.CHAOS_SETTLEMENT
        x = (SETTLEMENT_OBTAIN_VOUCHER_BOX[0] + SETTLEMENT_OBTAIN_VOUCHER_BOX[2]) // 2
        y = (SETTLEMENT_OBTAIN_VOUCHER_BOX[1] + SETTLEMENT_OBTAIN_VOUCHER_BOX[3]) // 2
        allowed, reason = runner._check_tap_guards("Tap Voucher", x, y)
        assert allowed is False
        assert "Obtain-voucher" in reason

    def test_obtain_skip_blocked(self, runner):
        runner.current_state = State.CHAOS_OBTAIN_REWARD
        x = (OBTAIN_SKIP_BOX[0] + OBTAIN_SKIP_BOX[2]) // 2
        y = (OBTAIN_SKIP_BOX[1] + OBTAIN_SKIP_BOX[3]) // 2
        allowed, reason = runner._check_tap_guards("Tap Skip", x, y)
        assert allowed is False
        assert "Skip của Obtain Reward" in reason

    def test_duplicate_skip_blocked(self, runner):
        runner.current_state = State.CHAOS_SELECT_DUPLICATE_CARD
        x = (DUPLICATE_SKIP_BOX[0] + DUPLICATE_SKIP_BOX[2]) // 2
        y = (DUPLICATE_SKIP_BOX[1] + DUPLICATE_SKIP_BOX[3]) // 2
        allowed, reason = runner._check_tap_guards("Tap Skip", x, y)
        assert allowed is False
        assert "Skip của Duplicate Card" in reason

    def test_event_sword_button_blocked_without_flag(self, runner):
        runner.current_state = State.CHAOS_EVENT
        x = (EVENT_SWORD_BTN_BOX[0] + EVENT_SWORD_BTN_BOX[2]) // 2
        y = (EVENT_SWORD_BTN_BOX[1] + EVENT_SWORD_BTN_BOX[3]) // 2
        allowed, reason = runner._check_tap_guards("Tap Sword Fallback", x, y)
        assert allowed is False
        assert "explicit_battle=True" in reason

    def test_event_sword_button_allowed_with_explicit_flag(self, runner):
        runner.current_state = State.CHAOS_EVENT
        x = (EVENT_SWORD_BTN_BOX[0] + EVENT_SWORD_BTN_BOX[2]) // 2
        y = (EVENT_SWORD_BTN_BOX[1] + EVENT_SWORD_BTN_BOX[3]) // 2
        allowed, reason = runner._check_tap_guards("Tap Sword Explicit", x, y, action_extra={"explicit_battle": True})
        assert allowed is True


class TestFlowHandlersPhase25:
    """Verifies ChaosFlow handlers for CHAOS_SETTLEMENT, CHAOS_SELECT_DUPLICATE_CARD, CHAOS_OBTAIN_REWARD, and CHAOS_CHOOSE_FATE."""

    def test_settlement_handler_modal(self, chaos_flow):
        act = chaos_flow.handle(State.CHAOS_SETTLEMENT, {"is_modal_open": True, "confirm_coord": (1055, 569)}, None)
        assert act.type == ActionType.TAP
        assert (act.x, act.y) == (1055, 569)
        assert "Modal Confirm" in act.name

    def test_settlement_handler_continue(self, chaos_flow):
        act = chaos_flow.handle(State.CHAOS_SETTLEMENT, {"is_modal_open": False, "continue_coord": (1426, 825)}, None)
        assert act.type == ActionType.TAP
        assert (act.x, act.y) == (1426, 825)
        assert "Continue" in act.name

    def test_duplicate_card_handler(self, chaos_flow):
        act = chaos_flow.handle(State.CHAOS_SELECT_DUPLICATE_CARD, {}, None)
        assert act.type == ActionType.TAP
        assert (act.x, act.y) == (400, 480)
        assert "Duplicate Card" in act.name

    def test_choose_fate_confirm_gray_guard(self, chaos_flow):
        img_fate = cv2.imread(os.path.join(FIXTURES_DIR, "choose_fate.png"))
        # First frame waits for animation
        act1 = chaos_flow.handle(State.CHAOS_CHOOSE_FATE, {"type": "choose_fate"}, img_fate)
        assert act1.type == ActionType.NONE
        # Second frame selects card, extra_actions must NOT contain confirm when gray
        act2 = chaos_flow.handle(State.CHAOS_CHOOSE_FATE, {"type": "choose_fate"}, img_fate)
        assert act2.type == ActionType.TAP
        extra_acts = act2.extra.get("extra_actions", [])
        assert extra_acts == []

    def test_obtain_reward_stall_guard(self, chaos_flow):
        img_ob = cv2.imread(os.path.join(FIXTURES_DIR, "obtain_credits_only.png"))
        # Reset flow obtain state
        chaos_flow._obtain_last_count = None
        chaos_flow._obtain_same_count_taps = 0
        chaos_flow._obtain_total_taps = 0

        # Taps 1, 2, 3 should succeed
        act1 = chaos_flow.handle(State.CHAOS_OBTAIN_REWARD, {}, img_ob)
        assert act1.type == ActionType.TAP
        assert (act1.x, act1.y) == (1426, 825)

        act2 = chaos_flow.handle(State.CHAOS_OBTAIN_REWARD, {}, img_ob)
        assert act2.type == ActionType.TAP

        act3 = chaos_flow.handle(State.CHAOS_OBTAIN_REWARD, {}, img_ob)
        assert act3.type == ActionType.TAP

        # Tap 4 should trigger stall guard (count did not decrement after 3 consecutive taps)
        act4 = chaos_flow.handle(State.CHAOS_OBTAIN_REWARD, {}, img_ob)
        assert act4.type == ActionType.NONE
        assert "Stall Guard" in act4.name

