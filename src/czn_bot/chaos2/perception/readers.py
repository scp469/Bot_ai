"""
czn_bot.chaos2.perception.readers - Các hàm thuần đọc màn hình trả về Facts dataclass.
Nhận ảnh numpy và phụ thuộc (detector, ocr), không thực hiện hành động tap.
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

from ..config import (
    ROW_Y_RANGES,
    ROW_ORANGE_BORDER_X,
    ROW_ORANGE_CONNECTOR_X,
    ZONE_EQUIP_CONFIRM,
    ZONE_EQUIP_EXTRACT,
    COORD_EQUIP_CONFIRM,
    ZONE_OBTAIN_BUTTON,
    ZONE_OBTAIN_SKIP,
    COORD_OBTAIN_BUTTON,
    CROP_OBTAIN_COUNT,
    ZONE_SETTLEMENT_CONTINUE,
    ZONE_SETTLEMENT_TEMP_RETURN,
    ZONE_SETTLEMENT_VOUCHER,
    COORD_SETTLEMENT_CONTINUE,
    DIALOG_SEARCH_ROI,
    DIALOG_HSV_ORANGE_LOWER,
    DIALOG_HSV_ORANGE_UPPER,
    ZONE_DUPLICATE_SKIP,
    ZONE_FATE_CONFIRM,
    FATE_CARD_CENTERS,
    EVENT_3CHOICES_CENTERS,
    EVENT_WAYPOINT_CENTER,
    ZONE_EVENT_ROUND_SWORD,
    MAP_LANE_SAFE_TAPS,
    MAP_ARROW_ROIS,
    COORD_SAFE_ZONE_REST,
    COORD_SAFE_ZONE_SKIP,
)
from .facts import (
    EquipmentFacts,
    MapFacts,
    ObtainFacts,
    EventFacts,
    EventChoice,
    DialogFacts,
    SettlementFacts,
    SafeZoneFacts,
    FateFacts,
    FateCard,
    DuplicateCardFacts,
)


def read_equipment_facts(screen: np.ndarray, detector: Any = None) -> EquipmentFacts:
    """Đọc dữ kiện từ màn hình CHAOS_EQUIPMENT."""
    facts = EquipmentFacts()
    if screen is None or screen.size == 0:
        return facts

    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)

    # 1. Đo tín hiệu cam cho từng hàng để tìm hàng được chọn
    # H: 5-25, S: 120-255, V: 120-255
    orange_mask = cv2.inRange(hsv, np.array([5, 120, 120]), np.array([25, 255, 255]))
    row_scores = []
    for y1, y2 in ROW_Y_RANGES:
        border_roi = orange_mask[y1:y2, ROW_ORANGE_BORDER_X[0]:ROW_ORANGE_BORDER_X[1]]
        conn_roi = orange_mask[y1:y2, ROW_ORANGE_CONNECTOR_X[0]:ROW_ORANGE_CONNECTOR_X[1]]
        score = int(np.count_nonzero(border_roi) + 2 * np.count_nonzero(conn_roi))
        row_scores.append(score)

    best_idx = int(np.argmax(row_scores))
    best_score = row_scores[best_idx]
    other_scores = [s for i, s in enumerate(row_scores) if i != best_idx]
    second_best = max(other_scores) if other_scores else 0

    if best_score >= 150 and (second_best == 0 or best_score >= 1.8 * second_best):
        facts.selected_row = best_idx

    # 2. Tìm hàng Recommended bằng template matching
    if detector is not None and "equip_recommended_tag" in detector.templates:
        for idx, (y1, y2) in enumerate(ROW_Y_RANGES):
            row_screen = screen[y1:y2, 970:1510]
            sc, _ = detector.match(row_screen, "equip_recommended_tag")
            if sc >= 0.70:
                facts.recommended_row = idx
                break

    # 3. Kiểm tra nút Confirm cam
    x1, y1, x2, y2 = ZONE_EQUIP_CONFIRM
    conf_crop = orange_mask[y1:y2, x1:x2]
    facts.confirm_ready = (np.count_nonzero(conf_crop) > 5000)
    facts.confirm_center = COORD_EQUIP_CONFIRM

    # 4. Kiểm tra nút Extract đỏ
    ex1, ey1, ex2, ey2 = ZONE_EQUIP_EXTRACT
    red_mask = (
        cv2.inRange(hsv[ey1:ey2, ex1:ex2], np.array([0, 100, 100]), np.array([10, 255, 255])) |
        cv2.inRange(hsv[ey1:ey2, ex1:ex2], np.array([170, 100, 100]), np.array([180, 255, 255]))
    )
    facts.extract_detected = (np.count_nonzero(red_mask) > 5000)
    facts.raw_details = {"row_scores": row_scores}
    return facts


def read_obtain_facts(screen: np.ndarray, ocr_service: Any = None) -> ObtainFacts:
    """Đọc dữ kiện từ màn hình CHAOS_OBTAIN_REWARD."""
    facts = ObtainFacts(obtain_btn_center=COORD_OBTAIN_BUTTON)
    if screen is None or screen.size == 0:
        return facts

    # 1. OCR số đếm trong nút Obtain
    if ocr_service is not None:
        cx, cy, cw, ch = CROP_OBTAIN_COUNT
        crop = screen[cy:cy + ch, cx:cx + cw]
        text = ocr_service.read_text(crop) if hasattr(ocr_service, "read_text") else ""
        m = re.search(r"\b([0-9])\b", text)
        if m:
            facts.count = int(m.group(1))

    # 2. Kiểm tra Skip button
    sx1, sy1, sx2, sy2 = ZONE_OBTAIN_SKIP
    skip_crop = screen[sy1:sy2, sx1:sx2]
    gray = cv2.cvtColor(skip_crop, cv2.COLOR_BGR2GRAY)
    facts.skip_detected = (np.count_nonzero(gray > 200) > 3000)

    facts.battle_end_detected = True
    return facts


def read_map_facts(screen: np.ndarray) -> MapFacts:
    """Đọc dữ kiện làn đường và đảo từ màn hình CHAOS_MAP."""
    facts = MapFacts(lane_body_points=MAP_LANE_SAFE_TAPS)
    if screen is None or screen.size == 0:
        return facts

    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    # Mũi tên Cyan: H: 75-110, S: 30-255, V: 80-255
    cyan_mask = cv2.inRange(hsv, np.array([75, 30, 80]), np.array([110, 255, 255]))

    arrows = []
    for lane_id, (rx, ry, rw, rh) in MAP_ARROW_ROIS.items():
        roi = cyan_mask[ry:ry + rh, rx:rx + rw]
        if np.count_nonzero(roi) > 50:
            arrows.append(lane_id)
    facts.arrows_detected = arrows

    # Độ sáng thân đảo (Vùng cờ / thân đảo)
    # TOP: (1150-1260, 65-200), MID: (1390-1490, 316-460), BOT: (1150-1260, 585-735)
    body_rois = {
        0: (1150, 65, 110, 135),
        1: (1390, 316, 100, 144),
        2: (1150, 585, 110, 150),
    }
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    active_lanes = []
    for lane_id, (bx, by, bw, bh) in body_rois.items():
        roi = gray[by:by + bh, bx:bx + bw]
        if roi.mean() > 55.0 or lane_id in arrows:
            active_lanes.append(lane_id)

    facts.lanes = active_lanes or [1]  # Mặc định ít nhất làn giữa
    return facts


def read_dialog_facts(screen: np.ndarray, ocr_service: Any = None) -> DialogFacts:
    """Đo nút Confirm và Cancel trong hộp thoại Modal (Rest / Loot)."""
    facts = DialogFacts()
    if screen is None or screen.size == 0:
        return facts

    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(DIALOG_HSV_ORANGE_LOWER), np.array(DIALOG_HSV_ORANGE_UPPER))

    # Tìm nút cam trong vùng dialog
    dx, dy, dw, dh = DIALOG_SEARCH_ROI
    crop_mask = np.zeros_like(mask)
    crop_mask[dy:dy + dh, dx:dx + dw] = mask[dy:dy + dh, dx:dx + dw]

    contours, _ = cv2.findContours(crop_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        area = cv2.contourArea(c)
        if 15000 <= area <= 45000:
            bx, by, bw, bh = cv2.boundingRect(c)
            aspect = float(bw) / max(1, bh)
            if 4.0 <= aspect <= 9.0:
                facts.confirm_center = (bx + bw // 2, by + bh // 2)
                facts.cancel_center = (bx - 500, by + bh // 2)
                if by > 600:
                    facts.dialog_type = "rest"
                else:
                    facts.dialog_type = "loot"
                break

    return facts


def read_settlement_facts(screen: np.ndarray, detector: Any = None) -> SettlementFacts:
    """Đọc dữ kiện từ màn hình CHAOS_SETTLEMENT."""
    facts = SettlementFacts(continue_center=COORD_SETTLEMENT_CONTINUE)
    if screen is None or screen.size == 0:
        return facts

    if detector is not None and "settlement_title" in detector.templates:
        sc, _ = detector.match(screen, "settlement_title")
        facts.settlement_title_score = sc

    # Báo diện diện các nút nguy hiểm
    facts.temporary_return_detected = True
    facts.voucher_detected = True
    return facts


def read_safe_zone_facts(screen: np.ndarray, detector: Any = None) -> SafeZoneFacts:
    """Đọc dữ kiện từ màn hình CHAOS_SAFE_ZONE."""
    facts = SafeZoneFacts(rest_center=COORD_SAFE_ZONE_REST, skip_center=COORD_SAFE_ZONE_SKIP)
    if screen is None or screen.size == 0:
        return facts

    if detector is not None:
        if "chaos_safe_zone_rest_icon" in detector.templates:
            sc, _ = detector.match(screen, "chaos_safe_zone_rest_icon")
            facts.rest_available = (sc >= 0.70)
        if "chaos_safe_zone_skip" in detector.templates:
            sc, _ = detector.match(screen, "chaos_safe_zone_skip")
            facts.skip_available = (sc >= 0.70)
    return facts


def read_fate_facts(screen: np.ndarray) -> FateFacts:
    """Đọc dữ kiện từ màn hình CHAOS_CHOOSE_FATE."""
    facts = FateFacts(confirm_center=(1426, 837))
    if screen is None or screen.size == 0:
        return facts

    for idx, pt in enumerate(FATE_CARD_CENTERS):
        facts.cards.append(FateCard(index=idx, center=pt))

    # Kiểm tra nút Confirm xám hay cam
    x1, y1, x2, y2 = ZONE_FATE_CONFIRM
    crop = screen[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([5, 120, 120]), np.array([25, 255, 255]))
    orange_pixels = np.count_nonzero(mask)

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    # Nút xám: gray mean ~192, orange_pixels ~ 0
    facts.confirm_ready = (orange_pixels > 5000 and gray.mean() < 160)
    return facts


def read_event_facts(screen: np.ndarray, ocr_service: Any = None) -> EventFacts:
    """Đọc dữ kiện từ màn hình CHAOS_EVENT."""
    facts = EventFacts()
    if screen is None or screen.size == 0:
        return facts

    # Kiểm tra nút tròn kiếm
    x1, y1, x2, y2 = ZONE_EVENT_ROUND_SWORD
    crop = screen[y1:y2, x1:x2]
    if crop.mean() > 70.0:
        facts.sword_button_detected = True

    # 3 lựa chọn hoặc 1 waypoint
    for idx, pt in enumerate(EVENT_3CHOICES_CENTERS):
        facts.choices.append(EventChoice(index=idx, center=pt))
    return facts


def read_duplicate_card_facts(screen: np.ndarray) -> DuplicateCardFacts:
    """Đọc dữ kiện từ màn hình CHAOS_SELECT_DUPLICATE_CARD."""
    facts = DuplicateCardFacts(title_detected=True, skip_detected=True)
    return facts

