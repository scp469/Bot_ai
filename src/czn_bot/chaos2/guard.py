"""
czn_bot.chaos2.guard - Hệ thống Tap Guard độc lập với flow.
Quy tắc:
  1. Kiểm tra tọa độ tap so với vùng CẤM (forbidden_tap_zones) của state hiện tại.
  2. Kiểm tra tọa độ tap so với vùng HỢP LỆ (valid_tap_zones) của state hiện tại.
  3. Chặn tap vào vùng đảo 3D (680, 80, 1480, 780) khi KHÔNG ở trong CHAOS_MAP (trừ khi là vùng hợp lệ được định nghĩa rõ).
  4. Flow KHÔNG được tự khai báo allowed_states để qua mặt guard.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .action import ChaosAction
from .config import SCREEN_WIDTH, SCREEN_HEIGHT, ZONE_MAP_3D_ISLANDS
from .registry import SCREEN_REGISTRY, ScreenDef, Zone

logger = logging.getLogger("ChaosBot.Chaos2.Guard")


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason: str
    zone_name: Optional[str] = None


class TapGuard:
    def __init__(self, registry: Optional[Dict[str, ScreenDef]] = None):
        self.registry = registry or SCREEN_REGISTRY

    def validate_action(
        self,
        action: ChaosAction,
        current_state: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> GuardDecision:
        """
        Kiểm tra tính an toàn của Action trước khi thực thi.
        Nếu action không phải là tap -> Luôn cho phép.
        Nếu action là tap -> Kiểm tra tọa độ chặt chẽ.
        """
        if action.type != "tap":
            return GuardDecision(allowed=True, reason=f"Action type '{action.type}' does not require coordinate guard")

        if action.target is None:
            return GuardDecision(allowed=False, reason="Tap action has no target coordinates (None)")

        x, y = action.target
        ctx = context or action.details.get("context")
        return self.validate_coords(x, y, current_state, context=ctx)

    def validate_coords(
        self,
        x: int,
        y: int,
        current_state: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> GuardDecision:
        """
        Kiểm tra tọa độ tap (x, y) độc lập đối với state hiện tại.
        Hỗ trợ context:
          - dialog_active=True: Hộp thoại modal đang mở -> Chỉ cho phép Confirm/Cancel của dialog (Item 5).
          - active_lanes=[...]: Kiểm tra làn hợp lệ trên CHAOS_MAP (Item 5).
        """
        # 1. Kiểm tra biên màn hình 1600x900
        if not (0 <= x < SCREEN_WIDTH and 0 <= y < SCREEN_HEIGHT):
            msg = f"Tọa độ tap ({x}, {y}) nằm ngoài biên màn hình ({SCREEN_WIDTH}x{SCREEN_HEIGHT})"
            logger.warning(f"[GUARD BLOCKED] {msg}")
            return GuardDecision(allowed=False, reason=msg)

        screen_def = self.registry.get(current_state)

        # 2. Nếu state không có trong registry hoặc là UNKNOWN
        if screen_def is None or current_state in ("UNKNOWN", "AMBIGUOUS", "TRANSITIONING"):
            msg = f"Không cho phép tap khi màn hình ở trạng thái chưa xác định: {current_state}"
            logger.warning(f"[GUARD BLOCKED] {msg}")
            return GuardDecision(allowed=False, reason=msg)

        # 2.1 Kiểm tra lớp phủ Modal Dialog (Item 5)
        # Khi có dialog mở (rest_dialog, settlement_confirm_dialog, settlement_dialog_leave):
        # Chỉ có vùng Confirm (800-1310, 500-700) và Cancel (300-800, 500-700) được phép tap!
        # Tọa độ hợp lệ của dialog được cho qua ngay, ghi đè vùng hợp lệ của state nền.
        if context and context.get("dialog_active", False):
            in_dialog_confirm = (800 <= x <= 1310 and 500 <= y <= 700)
            in_dialog_cancel = (300 <= x <= 800 and 500 <= y <= 700)
            if in_dialog_confirm or in_dialog_cancel:
                return GuardDecision(allowed=True, reason=f"Tap ({x}, {y}) hợp lệ vào nút Modal Dialog")
            msg = f"Hộp thoại Modal đang mở: Chỉ được phép tap Confirm hoặc Cancel, chặn tap ngoài dialog ({x}, {y})"
            logger.warning(f"[GUARD BLOCKED] {msg}")
            return GuardDecision(allowed=False, reason=msg, zone_name="MODAL_DIALOG_OVERLAY")

        # 2.2 Kiểm tra giới hạn làn trên CHAOS_MAP (Item 5)
        if current_state == "CHAOS_MAP" and context and "active_lanes" in context:
            active_lanes = context["active_lanes"]
            # Làn 0 (Top: y in 120-280), Làn 1 (Mid: y in 400-550), Làn 2 (Bot: y in 650-800)
            target_lane = None
            if 120 <= y <= 280:
                target_lane = 0
            elif 400 <= y <= 550:
                target_lane = 1
            elif 650 <= y <= 800:
                target_lane = 2

            if target_lane is not None and target_lane not in active_lanes:
                msg = f"Làn {target_lane} không tồn tại trên bản đồ (làn khả dụng: {active_lanes})"
                logger.warning(f"[GUARD BLOCKED] {msg}")
                return GuardDecision(allowed=False, reason=msg, zone_name="MAP_INACTIVE_LANE")

        # 3. Kiểm tra các vùng CẤM (forbidden_tap_zones) của state
        for zone in screen_def.forbidden_tap_zones:
            if zone.contains(x, y):
                msg = f"Tọa độ ({x}, {y}) rơi vào VÙNG CẤM '{zone.name}' của state {current_state}"
                logger.warning(f"[GUARD BLOCKED] {msg}")
                return GuardDecision(allowed=False, reason=msg, zone_name=zone.name)

        # 4. Kiểm tra vùng HỢP LỆ (valid_tap_zones) nếu có khai báo
        if screen_def.valid_tap_zones:
            in_valid_zone = any(zone.contains(x, y) for zone in screen_def.valid_tap_zones)
            if not in_valid_zone:
                msg = (
                    f"Tọa độ ({x}, {y}) KHÔNG nằm trong bất kỳ vùng hợp lệ nào "
                    f"được khai báo cho state {current_state}"
                )
                logger.warning(f"[GUARD BLOCKED] {msg}")
                return GuardDecision(allowed=False, reason=msg)

        # 5. Guard đảo 3D độc lập:
        # Nếu KHÔNG PHẢI CHAOS_MAP mà tap vào vùng đảo (680, 80, 1480, 780),
        # tọa độ BẮT BUỘC phải nằm trong valid_tap_zones của state đó (đã kiểm tra ở bước 4).
        # Nếu state không khai báo valid_tap_zones mà tap vào vùng đảo -> CHẶN NGAY.
        x1_island, y1_island, x2_island, y2_island = ZONE_MAP_3D_ISLANDS
        if current_state != "CHAOS_MAP" and (x1_island <= x <= x2_island and y1_island <= y <= y2_island):
            if not screen_def.valid_tap_zones:
                msg = (
                    f"Tọa độ ({x}, {y}) rơi vào vùng đảo bản đồ {ZONE_MAP_3D_ISLANDS} "
                    f"nhưng state hiện tại là {current_state} (không phải CHAOS_MAP)"
                )
                logger.warning(f"[GUARD BLOCKED] {msg}")
                return GuardDecision(allowed=False, reason=msg, zone_name="3D_ISLAND_ROI")

        return GuardDecision(allowed=True, reason=f"Tap ({x}, {y}) an toàn cho state {current_state}")

