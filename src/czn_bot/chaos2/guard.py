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

    def validate_action(self, action: ChaosAction, current_state: str) -> GuardDecision:
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
        return self.validate_coords(x, y, current_state)

    def validate_coords(self, x: int, y: int, current_state: str) -> GuardDecision:
        """
        Kiểm tra tọa độ tap (x, y) độc lập đối với state hiện tại.
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

