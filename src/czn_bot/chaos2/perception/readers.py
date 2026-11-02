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
    MAP_FLAG_ROIS,
    COORD_SAFE_ZONE_REST,
    COORD_SAFE_ZONE_SKIP,
    ZONE_EPIPHANY_VIEW_ORIGINAL,
    ZONE_REMOVE_CANCEL,
    ZONE_REMOVE_EXECUTE,
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
    DuplicateFacts,
    DuplicateCardFacts,
    DuplicateCardItem,
    HpFacts,
    EpiphanyFacts,
    EpiphanyCard,
    RemoveFacts,
    CopyCompleteFacts,
)


# ── A1. EQUIPMENT FACTS ───────────────────────────────────────────────────────
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

    # 2. Tìm hàng Recommended bằng template matching nếu detector có
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


# ── A2. OBTAIN FACTS ──────────────────────────────────────────────────────────
def read_obtain_facts(screen: np.ndarray, ocr_service: Any = None) -> ObtainFacts:
    """Đọc dữ kiện từ màn hình CHAOS_OBTAIN_REWARD."""
    facts = ObtainFacts(obtain_btn_center=COORD_OBTAIN_BUTTON)
    if screen is None or screen.size == 0:
        return facts

    # 1. OCR số đếm trong nút Obtain: crop [790:860, 1340:1580]
    crop = screen[790:860, 1340:1580]
    txt = ""
    if ocr_service is not None and hasattr(ocr_service, "read_text"):
        txt = ocr_service.read_text(crop)
    else:
        try:
            from czn_bot.vision.ocr import read_text
            txt = read_text(crop)
        except Exception:
            pass

    if txt:
        m = re.search(r"(\d+)", txt)
        if m:
            val = int(m.group(1))
            facts.button_count = val
            facts.count = val

    # 2. Kiểm tra Skip button
    sx1, sy1, sx2, sy2 = ZONE_OBTAIN_SKIP
    skip_crop = screen[sy1:sy2, sx1:sx2]
    gray = cv2.cvtColor(skip_crop, cv2.COLOR_BGR2GRAY)
    facts.skip_detected = (np.count_nonzero(gray > 200) > 3000)

    facts.battle_end_detected = True
    return facts


# ── A3. MAP FACTS ─────────────────────────────────────────────────────────────
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

    # Đọc loại cờ theo làn từ MAP_FLAG_ROIS:
    # Pink/red flag -> combat / battle; Blue/cyan flag -> event
    lane_types: Dict[int, str] = {}
    for lane_id, (fx, fy, fw, fh) in MAP_FLAG_ROIS.items():
        roi = screen[fy:fy + fh, fx:fx + fw]
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        combat_mask = cv2.inRange(hsv_roi, np.array([140, 60, 60]), np.array([175, 255, 255]))
        event_mask = cv2.inRange(hsv_roi, np.array([90, 60, 60]), np.array([130, 255, 255]))
        c_cnt = int(np.count_nonzero(combat_mask))
        e_cnt = int(np.count_nonzero(event_mask))
        if c_cnt > 2000 and c_cnt > e_cnt:
            lane_types[lane_id] = "battle"
        elif e_cnt > 2000 and e_cnt > c_cnt:
            lane_types[lane_id] = "event"
    facts.lane_types = lane_types

    # Độ sáng thân đảo
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    active_lanes = []
    for lane_id, (bx, by, bw, bh) in MAP_FLAG_ROIS.items():
        roi = gray[by:by + bh, bx:bx + bw]
        if roi.mean() > 55.0 or lane_id in arrows:
            active_lanes.append(lane_id)

    facts.lanes = active_lanes or [1]
    return facts


# ── A4. EVENT FACTS ───────────────────────────────────────────────────────────
def read_event_facts(screen: np.ndarray, ocr_service: Any = None) -> EventFacts:
    """Đọc dữ kiện từ màn hình CHAOS_EVENT."""
    facts = EventFacts()
    if screen is None or screen.size == 0:
        return facts

    # 1. Kiểm tra nút tròn kiếm góc dưới phải (1460, 725, 1570, 835), tâm (1515, 780)
    x1, y1, x2, y2 = ZONE_EVENT_ROUND_SWORD
    crop = screen[y1:y2, x1:x2]
    if crop.mean() > 70.0:
        facts.sword_button_detected = True

    # 2. Phân biệt Waypoint đơn vs 3 lựa chọn
    left_mean = screen[700:830, 200:550].mean()
    right_mean = screen[700:830, 1040:1390].mean()
    mid_mean = screen[700:830, 620:970].mean()

    # Nếu ô trái và phải tối/rỗng (< 34) còn ô giữa sáng (>= 35) -> Waypoint đơn
    if left_mean < 34.0 and right_mean < 30.0 and mid_mean >= 35.0:
        facts.is_waypoint = True
        facts.choices.append(EventChoice(index=0, center=EVENT_WAYPOINT_CENTER, text="Activate Waypoint"))
    else:
        facts.is_waypoint = False
        hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
        purple_mask = cv2.inRange(hsv, np.array([125, 40, 40]), np.array([155, 255, 255]))

        for idx, pt in enumerate(EVENT_3CHOICES_CENTERS):
            bx1, bx2 = [(200, 550), (600, 1000), (1050, 1400)][idx]
            curse_cnt = np.count_nonzero(purple_mask[700:850, bx1:bx2])
            has_curse = (curse_cnt > 500)
            if has_curse:
                facts.has_curse = True
            facts.choices.append(EventChoice(index=idx, center=pt, has_curse=has_curse))

    return facts


# ── A5. DIALOG FACTS ──────────────────────────────────────────────────────────
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
                cx = bx + bw // 2
                cy = by + bh // 2
                facts.confirm_center = (cx, cy)
                facts.cancel_center = (cx - 510, cy)
                if cy > 600:
                    facts.dialog_type = "rest"
                else:
                    facts.dialog_type = "loot"
                break

    return facts


# ── A6. SETTLEMENT FACTS ──────────────────────────────────────────────────────
def read_settlement_facts(screen: np.ndarray, detector: Any = None) -> SettlementFacts:
    """Đọc dữ kiện từ màn hình CHAOS_SETTLEMENT."""
    facts = SettlementFacts(continue_center=COORD_SETTLEMENT_CONTINUE)
    if screen is None or screen.size == 0:
        return facts

    if detector is not None and "settlement_title" in detector.templates:
        sc, _ = detector.match(screen, "settlement_title")
        facts.settlement_title_score = sc

    # Nút Temporary Return trắng: (824, 792, 1126, 858)
    tr_crop = screen[792:858, 824:1126]
    facts.temporary_return_detected = bool(tr_crop.mean() > 100.0)

    # Nút Obtain voucher: (1272, 318, 1572, 378)
    vc_crop = screen[318:378, 1272:1572]
    facts.voucher_detected = bool(vc_crop.mean() > 70.0)

    return facts


# ── A7. SAFE ZONE FACTS ───────────────────────────────────────────────────────
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
    else:
        # Fallback kiểm tra độ sáng biểu tượng Rest và Skip
        rest_crop = screen[620:750, 250:600]
        facts.rest_available = bool(rest_crop.mean() > 40.0)
        skip_crop = screen[750:890, 1200:1580]
        facts.skip_available = bool(skip_crop.mean() > 40.0)

    return facts


# ── A8. FATE FACTS ────────────────────────────────────────────────────────────
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
    facts.confirm_ready = (orange_pixels > 5000 and gray.mean() < 160)
    return facts


# ── A9. DUPLICATE CARD FACTS ──────────────────────────────────────────────────
def read_duplicate_card_facts(screen: np.ndarray, ocr_service: Any = None) -> DuplicateFacts:
    """Đọc dữ kiện từ màn hình CHAOS_SELECT_DUPLICATE_CARD."""
    facts = DuplicateFacts(title_detected=True, skip_detected=True)
    if screen is None or screen.size == 0:
        return facts

    # 3 thẻ tại x ≈ [400, 800, 1200], y ≈ 480
    card_centers = [(400, 480), (800, 480), (1200, 480)]
    for idx, pt in enumerate(card_centers):
        facts.cards.append(
            DuplicateCardItem(
                index=idx,
                center=pt,
                card_type="Skill",
            )
        )
    facts.num_cards = len(facts.cards)
    return facts


# ── A10. HP FACTS ─────────────────────────────────────────────────────────────
def read_hp_facts(screen: np.ndarray, ocr_service: Any = None) -> Optional[HpFacts]:
    """Đọc dữ kiện thanh máu HUD đội hình (HpFacts). Trả về None nếu không có HUD."""
    if screen is None or screen.size == 0:
        return None

    # Màn overlay không có HUD: top-bar tối đen hoặc bị che hoàn toàn
    top_bar = screen[20:60, 30:650]
    if top_bar.mean() < 10.0:
        return None

    try:
        from czn_bot.vision.hp_reader import get_team_hp
        hp_pct, is_low = get_team_hp(screen)
    except Exception:
        hp_pct, is_low = 1.0, False

    current_hp, max_hp = 0, 0
    txt = ""
    if ocr_service is not None and hasattr(ocr_service, "read_text"):
        txt = ocr_service.read_text(screen[15:55, 30:650])
    else:
        try:
            from czn_bot.vision.ocr import read_text
            txt = read_text(screen[15:55, 30:650])
        except Exception:
            pass

    if txt:
        m = re.search(r"(\d+)\s*/\s*(\d+)", txt)
        if m:
            current_hp = int(m.group(1))
            max_hp = int(m.group(2))
            if max_hp > 0:
                hp_pct = round(current_hp / max_hp, 2)
                is_low = hp_pct < 0.60

    return HpFacts(
        current_hp=current_hp,
        max_hp=max_hp,
        hp_fraction=hp_pct,
        is_low_hp=is_low,
    )


# ── PHẦN C READERS: EPIPHANY, REMOVE, COPY_COMPLETE ───────────────────────────
def read_epiphany_facts(screen: np.ndarray, ocr_service: Any = None) -> EpiphanyFacts:
    """Đọc dữ kiện từ màn hình CHAOS_CHOOSE_EPIPHANY."""
    facts = EpiphanyFacts(title_detected=True, has_view_original=True)
    if screen is None or screen.size == 0:
        return facts

    # 3 thẻ tại x ≈ [400, 800, 1200], y ≈ 480
    card_centers = [(400, 480), (800, 480), (1200, 480)]
    for idx, pt in enumerate(card_centers):
        facts.cards.append(
            EpiphanyCard(
                index=idx,
                center=pt,
            )
        )
    return facts


def read_remove_facts(screen: np.ndarray, ocr_service: Any = None) -> RemoveFacts:
    """Đọc dữ kiện từ màn hình CHAOS_REMOVE_CARD."""
    facts = RemoveFacts()
    if screen is None or screen.size == 0:
        return facts

    # Kiểm tra nút Remove cam hay xám tại ZONE_REMOVE_EXECUTE
    x1, y1, x2, y2 = ZONE_REMOVE_EXECUTE
    crop = screen[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([5, 120, 120]), np.array([25, 255, 255]))
    orange_pixels = np.count_nonzero(mask)

    facts.remove_enabled = (orange_pixels > 5000)
    facts.selected_count = 1 if facts.remove_enabled else 0
    facts.budget_used = 20 if facts.remove_enabled else 0
    facts.removals_used = 1 if facts.remove_enabled else 0
    return facts


def read_copy_complete_facts(screen: np.ndarray) -> CopyCompleteFacts:
    """Đọc dữ kiện từ màn hình CHAOS_COPY_COMPLETE."""
    facts = CopyCompleteFacts(has_copy_complete=True)
    return facts
