"""
tests/test_chaos2_harness.py - Test Harness cho Chaos2 Giai đoạn 0.
1. Tải toàn bộ fixture ảnh thật từ tests/fixtures/states/ (1600x900).
2. Phân loại màn hình và in bảng điểm chi tiết của MỌI neo dương / âm.
3. Kiểm tra TapGuard độc lập chặn chính xác các vùng CẤM (Extract, Skip, Temp Return, v.v.).
4. Kiểm tra ChaosLoop với 0 handler thật: không phát tap mù, dừng an toàn.
"""

import glob
import os
import pytest
import cv2
import numpy as np

from czn_bot.vision.detector import ScreenDetector
from czn_bot.chaos2.registry import SCREEN_REGISTRY
from czn_bot.chaos2.classifier import ChaosClassifier
from czn_bot.chaos2.guard import TapGuard
from czn_bot.chaos2.action import ChaosAction
from czn_bot.chaos2.loop import ChaosLoop
from czn_bot.chaos2.dryrun import DryRunSession
from czn_bot.chaos2.config import (
    COORD_EQUIP_CONFIRM,
    COORD_OBTAIN_BUTTON,
    COORD_SETTLEMENT_CONTINUE,
    MAP_LANE_SAFE_TAPS,
)


@pytest.fixture(scope="module")
def detector():
    return ScreenDetector()


@pytest.fixture(scope="module")
def classifier(detector):
    return ChaosClassifier(SCREEN_REGISTRY, matcher=detector.match)


@pytest.fixture(scope="module")
def guard():
    return TapGuard(SCREEN_REGISTRY)


def test_classify_all_fixtures_and_print_anchor_table(classifier):
    """
    Tải toàn bộ 21 fixtures từ tests/fixtures/states/,
    chấm điểm phân loại và in bảng điểm toàn diện của mọi anchor.
    """
    fixtures = sorted(glob.glob("tests/fixtures/states/*.png"))
    assert len(fixtures) >= 18, f"Kỳ vọng ít nhất 18 fixtures nhưng tìm thấy {len(fixtures)}"

    expected_states = {
        "choose_fate.png": "CHAOS_CHOOSE_FATE",
        "equipment_row1_selected.png": "CHAOS_EQUIPMENT",
        "equipment_row3_selected.png": "CHAOS_EQUIPMENT",
        "event_3choices.png": "CHAOS_EVENT",
        "event_waypoint_single.png": "CHAOS_EVENT",
        "map_1island.png": "CHAOS_MAP",
        "map_2islands.png": "CHAOS_MAP",
        "map_3islands.png": "CHAOS_MAP",
        "obtain_credits_only.png": "CHAOS_OBTAIN_REWARD",
        "obtain_duplicate_card.png": "CHAOS_OBTAIN_REWARD",
        "obtain_equipment_credits.png": "CHAOS_OBTAIN_REWARD",
        "obtain_equipment_done.png": "CHAOS_OBTAIN_REWARD",
        "obtain_equipment_highlight.png": "CHAOS_OBTAIN_REWARD",
        "rest_dialog.png": "CHAOS_SAFE_ZONE",
        "safe_zone.png": "CHAOS_SAFE_ZONE",
        "safe_zone_shop.png": "CHAOS_SAFE_ZONE",
        "select_duplicate_card.png": "CHAOS_SELECT_DUPLICATE_CARD",
        "settlement_button.png": "CHAOS_AFTER_BATTLE",
        "settlement_confirm_dialog.png": "CHAOS_SETTLEMENT",
        "settlement_screen_1.png": "CHAOS_SETTLEMENT",
        "settlement_screen_2.png": "CHAOS_SETTLEMENT",
    }

    print("\n" + "=" * 110)
    print(f"{'FIXTURE':<30} | {'PREDICTED STATE':<28} | {'CONF':<5} | {'MARGIN':<6} | {'STATUS'}")
    print("=" * 110)

    results_table = []
    for fpath in fixtures:
        fname = os.path.basename(fpath)
        img = cv2.imread(fpath)
        assert img is not None, f"Không thể đọc file ảnh: {fpath}"
        assert img.shape[:2] == (900, 1600), f"Ảnh {fname} sai kích thước: {img.shape}"

        res = classifier.classify(img)
        expected = expected_states.get(fname)
        status = "PASS" if (expected is None or res.state == expected) else "FAIL"

        print(f"{fname:<30} | {res.state:<28} | {res.confidence:<5.2f} | {res.margin:<6.2f} | {status}")
        results_table.append((fname, res, expected))

        if expected is not None:
            assert res.state == expected, f"{fname}: kỳ vọng {expected} nhưng nhận được {res.state}"
            assert res.confidence >= 0.50, f"{fname}: độ tin cậy quá thấp {res.confidence:.2f}"

    print("=" * 110 + "\n")


def test_independent_tap_guard(guard):
    """
    Kiểm tra TapGuard độc lập:
    1. Chặn tuyệt đối các nút CẤM / NGUY HIỂM.
    2. Chặn tap vào vùng đảo 3D khi không ở CHAOS_MAP.
    3. Chặn tọa độ ngoài biên màn hình.
    4. Cho phép các tọa độ hợp lệ.
    """
    # 1. Chặn Extract đỏ trên EQUIPMENT
    d1 = guard.validate_coords(1086, 837, "CHAOS_EQUIPMENT")
    assert not d1.allowed
    assert "NGUY HIỂM" in d1.reason or "Extract" in d1.reason

    # 2. Chặn Skip trắng trên OBTAIN
    d2 = guard.validate_coords(1096, 824, "CHAOS_OBTAIN_REWARD")
    assert not d2.allowed
    assert "Skip" in d2.reason or "VÙNG CẤM" in d2.reason

    # 3. Chặn Temporary Return trên SETTLEMENT
    d3 = guard.validate_coords(950, 825, "CHAOS_SETTLEMENT")
    assert not d3.allowed
    assert "Temporary Return" in d3.reason or "VÙNG CẤM" in d3.reason

    # 4. Chặn Obtain Voucher trên SETTLEMENT
    d4 = guard.validate_coords(1400, 350, "CHAOS_SETTLEMENT")
    assert not d4.allowed
    assert "Voucher" in d4.reason or "VÙNG CẤM" in d4.reason

    # 5. Chặn Skip trên DUPLICATE CARD
    d5 = guard.validate_coords(1415, 835, "CHAOS_SELECT_DUPLICATE_CARD")
    assert not d5.allowed
    assert "Skip" in d5.reason or "VÙNG CẤM" in d5.reason

    # 6. Chặn nút tròn Play trên CHOOSE FATE
    d6 = guard.validate_coords(1220, 835, "CHAOS_CHOOSE_FATE")
    assert not d6.allowed
    assert "Round play" in d6.reason or "CẤM TAP" in d6.reason

    # 7. Chặn nút tròn kiếm chưa rõ trên EVENT
    d7 = guard.validate_coords(1515, 780, "CHAOS_EVENT")
    assert not d7.allowed
    assert "kiếm" in d7.reason or "CẤM TAP" in d7.reason

    # 8. Chặn tap ngoài biên màn hình
    d8 = guard.validate_coords(1650, 500, "CHAOS_MAP")
    assert not d8.allowed
    assert "ngoài biên" in d8.reason

    # 9. Chặn tap vào vùng đảo khi đang ở CHAOS_EQUIPMENT (lỗi P0 kinh điển)
    # Tọa độ (1150, 520) nằm giữa vùng đảo
    # Nhưng trong CHAOS_EQUIPMENT, vùng thẻ nhân vật hàng 2 là y: 383-583, x: 972-1508.
    # Tọa độ ngoài thẻ nhân vật mà nằm trong đảo: ví dụ (750, 450)
    d9 = guard.validate_coords(750, 450, "CHAOS_EQUIPMENT")
    assert not d9.allowed
    assert "KHÔNG nằm trong bất kỳ vùng hợp lệ nào" in d9.reason

    # 10. Cho phép tap hợp lệ
    # Confirm trên EQUIPMENT
    d_ok1 = guard.validate_coords(COORD_EQUIP_CONFIRM[0], COORD_EQUIP_CONFIRM[1], "CHAOS_EQUIPMENT")
    assert d_ok1.allowed, f"Confirm trên EQUIPMENT phải hợp lệ: {d_ok1.reason}"

    # Obtain trên OBTAIN
    d_ok2 = guard.validate_coords(COORD_OBTAIN_BUTTON[0], COORD_OBTAIN_BUTTON[1], "CHAOS_OBTAIN_REWARD")
    assert d_ok2.allowed, f"Obtain trên OBTAIN phải hợp lệ: {d_ok2.reason}"

    # Continue trên SETTLEMENT
    d_ok3 = guard.validate_coords(COORD_SETTLEMENT_CONTINUE[0], COORD_SETTLEMENT_CONTINUE[1], "CHAOS_SETTLEMENT")
    assert d_ok3.allowed, f"Continue trên SETTLEMENT phải hợp lệ: {d_ok3.reason}"

    # Thân đảo làn giữa trên MAP
    mid_tap = MAP_LANE_SAFE_TAPS[1]
    d_ok4 = guard.validate_coords(mid_tap[0], mid_tap[1], "CHAOS_MAP")
    assert d_ok4.allowed, f"Thân đảo trên MAP phải hợp lệ: {d_ok4.reason}"


def test_loop_with_zero_handlers_safe_behavior(classifier, guard):
    """
    Kiểm tra vòng lặp ChaosLoop với 0 handler thật:
    - Frame 1: Chờ ổn định (1/K) -> Trả về wait
    - Frame 2: Ổn định nhưng không có handler -> Trả về wait an toàn
    - KHÔNG BAO GIỜ phát sinh tap mù!
    """
    loop = ChaosLoop(classifier=classifier, guard=guard, dry_run=True)
    img_equip = cv2.imread("tests/fixtures/states/equipment_row1_selected.png")

    # Frame 1
    action1 = loop.step(img_equip)
    assert action1.type == "wait"
    assert "Chờ ổn định" in action1.reason

    # Frame 2 (đủ K=2 frames cho EQUIPMENT)
    action2 = loop.step(img_equip)
    assert action2.type == "wait"
    assert "chưa có handler" in action2.reason
    assert loop._current_state == "CHAOS_EQUIPMENT"
    # Xác nhận 0 action tap nào được tạo
    assert action2.target is None


def test_loop_unknown_stuck_safe_stop(classifier, guard):
    """
    Kiểm tra nếu màn hình kẹt UNKNOWN quá 5 frame liên tiếp -> Dừng an toàn (Safe Stop).
    """
    loop = ChaosLoop(classifier=classifier, guard=guard)
    black_screen = np.zeros((900, 1600, 3), dtype=np.uint8)

    for i in range(4):
        action = loop.step(black_screen)
        assert action.type == "wait"
        assert "chờ nhận diện lại" in action.reason

    # Frame 5: Phải phát sinh Action STOP
    action5 = loop.step(black_screen)
    assert action5.type == "stop"
    assert "Kẹt trạng thái UNKNOWN" in action5.reason


def test_dry_run_session_workflow(classifier, guard):
    """
    Kiểm tra luồng chạy dry-run mô phỏng chuỗi khung hình thực tế.
    """
    session = DryRunSession(ChaosLoop(classifier=classifier, guard=guard, dry_run=True))
    fpaths = [
        "tests/fixtures/states/map_3islands.png",
        "tests/fixtures/states/map_3islands.png",
        "tests/fixtures/states/map_3islands.png",
        "tests/fixtures/states/equipment_row1_selected.png",
        "tests/fixtures/states/equipment_row1_selected.png",
    ]

    for p in fpaths:
        img = cv2.imread(p)
        session.feed_frame(img, frame_name=os.path.basename(p))

    summary = session.summary()
    assert "TỔNG KẾT DRY-RUN" in summary
    assert "map_3islands.png" in summary
    assert "equipment_row1_selected.png" in summary

