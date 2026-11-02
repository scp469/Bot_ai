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

FIXTURES_DIR = os.path.join("tests", "fixtures", "states")


@pytest.fixture(scope="module")
def detector():
    return ScreenDetector()


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
