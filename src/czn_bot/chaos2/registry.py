"""
czn_bot.chaos2.registry - Registry duy nhất định nghĩa mọi màn hình chế độ Chaos.
Mỗi màn hình có:
  - id, tên
  - positive_layouts: Các biến thể layout (vd: Event 3 lựa chọn vs Waypoint; After Battle Leave vs Settlement)
  - negative_anchors: Các neo âm (khớp là loại bỏ ngay lập tức)
  - k_frames: K frame ổn định tối thiểu
  - handler: (Giai đoạn 0: None - CHƯA viết handler)
  - valid_tap_zones: Vùng tap hợp lệ
  - forbidden_tap_zones: Vùng CẤM TUYỆT ĐỐI (Extract, Skip, Temp Return, v.v.)
  - allowed_next_states: Danh sách state được phép chuyển tiếp
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Set, Tuple, Any

from .action import ChaosAction
from .config import (
    K_FRAMES_DEFAULT,
    K_FRAMES_MAP,
    K_FRAMES_DIALOG,
    K_FRAMES_OBTAIN,
    K_FRAMES_EQUIPMENT,
    K_FRAMES_SETTLEMENT,
    K_FRAMES_REMOVE,
    K_FRAMES_EPIPHANY,
    ZONE_EQUIP_CONFIRM,
    ZONE_EQUIP_EXTRACT,
    ZONE_OBTAIN_BUTTON,
    ZONE_OBTAIN_SKIP,
    ZONE_SETTLEMENT_CONTINUE,
    ZONE_SETTLEMENT_TEMP_RETURN,
    ZONE_SETTLEMENT_VOUCHER,
    ZONE_DUPLICATE_SKIP,
    ZONE_FATE_CONFIRM,
    ZONE_FATE_ROUND_PLAY,
    ZONE_EVENT_ROUND_SWORD,
    ZONE_EPIPHANY_VIEW_ORIGINAL,
    ZONE_REMOVE_CANCEL,
    ZONE_REMOVE_EXECUTE,
    ZONE_SAFE_ZONE_SHOP,
    ZONE_SAFE_ZONE_TRAINING,
)


@dataclass(frozen=True)
class AnchorDef:
    key: str                                   # Tên template trong TEMPLATES
    region: Tuple[int, int, int, int]          # (x, y, w, h)
    threshold: float                           # Ngưỡng khớp tối thiểu
    weight: float = 1.0                        # Trọng số điểm
    negative: bool = False                     # True nếu là neo âm (khớp là LOẠI BỎ)


@dataclass(frozen=True)
class Zone:
    x1: int
    y1: int
    x2: int
    y2: int
    name: str = ""

    def contains(self, x: int, y: int) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.x1, self.y1, self.x2, self.y2)


# Signature của handler: (facts, context) -> ChaosAction
HandlerFn = Callable[[Any, Any], ChaosAction]


@dataclass
class ScreenDef:
    id: str                                                 # Mã State (vd "CHAOS_EQUIPMENT")
    name: str                                               # Tên mô tả màn hình
    positive_layouts: Tuple[Tuple[AnchorDef, ...], ...]    # Các biến thể layout neo dương
    negative_anchors: Tuple[AnchorDef, ...]                 # Danh sách neo âm
    k_frames: int = K_FRAMES_DEFAULT                        # Số khung hình đồng nhất cần thiết
    handler: Optional[HandlerFn] = None                     # Giai đoạn 0: None (CHƯA viết handler)
    valid_tap_zones: Tuple[Zone, ...] = ()                  # Bounding boxes được phép tap
    forbidden_tap_zones: Tuple[Zone, ...] = ()              # Bounding boxes CẤM TUYỆT ĐỐI tap
    allowed_next_states: Set[str] = field(default_factory=set)
    is_irreversible: bool = False                           # True nếu hành động trên màn này không thể hoàn tác (G5)

    @property
    def positive_anchors(self) -> Tuple[AnchorDef, ...]:
        """Tất cả neo dương gộp lại (dùng cho bảng thống kê)."""
        anchors = []
        for layout in self.positive_layouts:
            anchors.extend(layout)
        return tuple(anchors)


# ── ĐĂNG KÝ DUY NHẤT MỌI MÀN HÌNH (SCREEN REGISTRY) ─────────────────────────

SCREEN_REGISTRY: Dict[str, ScreenDef] = {
    # 1. CHAOS_MAP: Bản đồ chọn đường
    "CHAOS_MAP": ScreenDef(
        id="CHAOS_MAP",
        name="Bản đồ chọn đảo",
        positive_layouts=(
            (AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.70, weight=1.0),),
            (AnchorDef("chaos_node_boss", (0, 500, 700, 400), 0.70, weight=1.0),),
        ),
        negative_anchors=(
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.65, negative=True),
            AnchorDef("chaos_safe_zone_rest_icon", (250, 620, 350, 130), 0.65, negative=True),
            AnchorDef("card_reward_title", (500, 50, 600, 130), 0.65, negative=True),
            AnchorDef("epiphany_title", (500, 50, 600, 130), 0.65, negative=True),
            AnchorDef("chaos_event_badge", (0, 100, 160, 200), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_MAP,
        handler=None,  # Phase 0: Chưa viết handler
        valid_tap_zones=(
            Zone(980, 120, 1180, 280, "Thân đảo làn trên (Top)"),
            Zone(1200, 400, 1380, 550, "Thân đảo làn giữa (Mid)"),
            Zone(1000, 650, 1180, 800, "Thân đảo làn dưới (Bot)"),
        ),
        forbidden_tap_zones=(),
        allowed_next_states={
            "CHAOS_EVENT",
            "CHAOS_SAFE_ZONE",
            "CHAOS_EQUIPMENT",
            "CHAOS_CHOOSE_EPIPHANY",
            "CHAOS_CHOOSE_FATE",
            "CHAOS_OBTAIN_REWARD",
            "CHAOS_SETTLEMENT",
            "IN_MATCH",
            "CHAOS_MAP",
        },
    ),

    # 2. CHAOS_EQUIPMENT: Gắn trang bị nhận được
    "CHAOS_EQUIPMENT": ScreenDef(
        id="CHAOS_EQUIPMENT",
        name="Gắn trang bị nhân vật",
        positive_layouts=(
            (AnchorDef("equipment_title", (650, 70, 350, 110), 0.75, weight=1.2),),
        ),
        negative_anchors=(
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("chaos_settlement_button", (1200, 750, 400, 150), 0.70, negative=True),
            AnchorDef("chaos_safe_zone_rest_icon", (250, 620, 350, 130), 0.65, negative=True),
            AnchorDef("chaos_safe_zone_confirm_btn", (800, 590, 510, 100), 0.65, negative=True),
            AnchorDef("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.65, negative=True),
            AnchorDef("chaos_leave_button", (1200, 750, 400, 150), 0.70, negative=True),
            AnchorDef("chaos_continue_button", (1200, 750, 380, 140), 0.70, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_EQUIPMENT,
        handler=None,
        valid_tap_zones=(
            Zone(972, 183, 1508, 383, "Thẻ nhân vật hàng 1"),
            Zone(972, 383, 1508, 583, "Thẻ nhân vật hàng 2"),
            Zone(972, 583, 1508, 783, "Thẻ nhân vật hàng 3"),
            Zone(*ZONE_EQUIP_CONFIRM, "Nút Confirm cam"),
        ),
        forbidden_tap_zones=(
            Zone(*ZONE_EQUIP_EXTRACT, "Nút Extract đỏ - NGUY HIỂM HỦY TRANG BỊ"),
        ),
        allowed_next_states={
            "CHAOS_MAP",
            "CHAOS_CHOOSE_EPIPHANY",
            "CHAOS_CHOOSE_FATE",
            "CHAOS_SETTLEMENT",
            "CHAOS_EQUIPMENT",
        },
        is_irreversible=True,
    ),

    # 3. CHAOS_OBTAIN_REWARD: Nhận phần thưởng sau trận
    "CHAOS_OBTAIN_REWARD": ScreenDef(
        id="CHAOS_OBTAIN_REWARD",
        name="Nhận phần thưởng trận đấu",
        positive_layouts=(
            (AnchorDef("chaos_obtain_button", (1100, 750, 490, 140), 0.78, weight=1.2),),
        ),
        negative_anchors=(
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("chaos_settlement_button", (1200, 750, 400, 150), 0.70, negative=True),
            AnchorDef("chaos_leave_button", (1200, 750, 400, 150), 0.70, negative=True),
            AnchorDef("chaos_continue_button", (1200, 750, 380, 140), 0.70, negative=True),
            AnchorDef("chaos_safe_zone_rest_icon", (250, 620, 350, 130), 0.65, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_OBTAIN,
        handler=None,
        valid_tap_zones=(
            Zone(*ZONE_OBTAIN_BUTTON, "Nút Obtain cam"),
        ),
        forbidden_tap_zones=(
            Zone(*ZONE_OBTAIN_SKIP, "Nút Skip trắng - CẤM TAP"),
        ),
        allowed_next_states={
            "CHAOS_OBTAIN_REWARD",
            "CHAOS_SELECT_DUPLICATE_CARD",
            "CHAOS_SETTLEMENT",
            "CHAOS_MAP",
        },
    ),

    # 4. CHAOS_EVENT: Sự kiện ngẫu nhiên / Waypoint
    "CHAOS_EVENT": ScreenDef(
        id="CHAOS_EVENT",
        name="Sự kiện ngẫu nhiên",
        positive_layouts=(
            # Layout 1: Sự kiện 3 lựa chọn có icon hoặc badge
            (
                AnchorDef("chaos_event_icon", (0, 100, 160, 200), 0.75, weight=1.0),
                AnchorDef("chaos_event_badge", (0, 100, 160, 200), 0.75, weight=1.0),
            ),
            # Layout 2: Sự kiện Waypoint / Thần điện có ngôi sao
            (
                AnchorDef("chaos_event_star_icon", (0, 100, 160, 200), 0.70, weight=1.2),
            ),
            # Layout 3: Sự kiện có nút Battle
            (
                AnchorDef("chaos_event_battle_btn", (1380, 750, 200, 140), 0.75, weight=1.0),
            ),
        ),
        negative_anchors=(
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.65, negative=True),
            AnchorDef("chaos_safe_zone_rest_icon", (250, 620, 350, 130), 0.65, negative=True),
            AnchorDef("chaos_settlement_button", (1200, 750, 400, 150), 0.70, negative=True),
            AnchorDef("chaos_leave_button", (1200, 750, 400, 150), 0.70, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_DEFAULT,
        handler=None,
        valid_tap_zones=(
            Zone(200, 700, 550, 830, "Lựa chọn 1"),
            Zone(620, 700, 970, 830, "Lựa chọn 2 / Waypoint đơn"),
            Zone(1040, 700, 1390, 830, "Lựa chọn 3"),
            Zone(1380, 750, 1580, 890, "Nút Battle"),
        ),
        forbidden_tap_zones=(
            Zone(*ZONE_EVENT_ROUND_SWORD, "Nút tròn kiếm góc dưới phải - CHƯA RÕ VAI TRÒ CẤM TAP"),
        ),
        allowed_next_states={
            "CHAOS_MAP",
            "IN_MATCH",
            "CHAOS_CHOOSE_EPIPHANY",
            "CHAOS_CHOOSE_FATE",
            "CHAOS_EVENT",
        },
        is_irreversible=True,
    ),

    # 5. CHAOS_SAFE_ZONE: Trạm nghỉ đốm lửa
    "CHAOS_SAFE_ZONE": ScreenDef(
        id="CHAOS_SAFE_ZONE",
        name="Trạm nghỉ an toàn (Safe Zone)",
        positive_layouts=(
            # Layout 1: Camp chính có biểu tượng Rest
            (
                AnchorDef("chaos_safe_zone_rest_icon", (250, 620, 350, 130), 0.75, weight=1.5),
                AnchorDef("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.75, weight=0.5),
            ),
            # Layout 2: Dialog Modal Rest có nút Confirm
            (
                AnchorDef("chaos_safe_zone_confirm_btn", (800, 590, 510, 100), 0.75, weight=1.5),
                AnchorDef("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.75, weight=0.8),
            ),
        ),
        negative_anchors=(
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("chaos_obtain_button", (1100, 750, 490, 140), 0.78, negative=True),
            AnchorDef("chaos_settlement_button", (1200, 750, 400, 150), 0.70, negative=True),
            AnchorDef("chaos_leave_button", (1200, 750, 400, 150), 0.70, negative=True),
            AnchorDef("chaos_continue_button", (1200, 750, 380, 140), 0.70, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_DEFAULT,
        handler=None,
        valid_tap_zones=(
            Zone(250, 620, 600, 750, "Nút Rest hồi máu"),
            Zone(800, 590, 1310, 700, "Nút Confirm Rest"),
            Zone(1200, 750, 1580, 890, "Nút Skip rời Safe Zone"),
        ),
        forbidden_tap_zones=(
            Zone(*ZONE_SAFE_ZONE_SHOP, "Khu vực Shop Delilang - CẤM TAP"),
            Zone(*ZONE_SAFE_ZONE_TRAINING, "Khu vực Training - CẤM TAP"),
        ),
        allowed_next_states={
            "CHAOS_MAP",
            "CHAOS_SAFE_ZONE",
        },
    ),

    # 6. CHAOS_CHOOSE_FATE: Lựa chọn định mệnh (Buff)
    "CHAOS_CHOOSE_FATE": ScreenDef(
        id="CHAOS_CHOOSE_FATE",
        name="Chọn Thẻ Định Mệnh (Fate)",
        positive_layouts=(
            (AnchorDef("choose_fate_title", (600, 800, 400, 100), 0.75, weight=1.2),),
        ),
        negative_anchors=(
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_DEFAULT,
        handler=None,
        valid_tap_zones=(
            Zone(250, 250, 560, 550, "Thẻ buff trái"),
            Zone(640, 250, 960, 550, "Thẻ buff giữa"),
            Zone(1030, 250, 1350, 550, "Thẻ buff phải"),
            Zone(*ZONE_FATE_CONFIRM, "Nút Confirm cam"),
        ),
        forbidden_tap_zones=(
            Zone(*ZONE_FATE_ROUND_PLAY, "Nút tròn ▶ cạnh Confirm - CẤM TAP"),
        ),
        allowed_next_states={
            "CHAOS_MAP",
            "CHAOS_EQUIPMENT",
            "CHAOS_OBTAIN_REWARD",
            "CHAOS_CHOOSE_FATE",
        },
        is_irreversible=True,
    ),

    # 7. CHAOS_SELECT_DUPLICATE_CARD: Chọn thẻ sao chép
    "CHAOS_SELECT_DUPLICATE_CARD": ScreenDef(
        id="CHAOS_SELECT_DUPLICATE_CARD",
        name="Chọn thẻ bài nhân bản",
        positive_layouts=(
            (AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.75, weight=1.5),),
        ),
        negative_anchors=(
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("remove_card_title", (80, 10, 470, 80), 0.65, negative=True),
            AnchorDef("chaos_event_icon", (0, 100, 160, 200), 0.65, negative=True),
            AnchorDef("chaos_safe_zone_rest_icon", (250, 620, 350, 130), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_DEFAULT,
        handler=None,
        valid_tap_zones=(
            Zone(100, 200, 1500, 750, "Vùng thẻ bài hiển thị"),
        ),
        forbidden_tap_zones=(
            Zone(*ZONE_DUPLICATE_SKIP, "Nút Skip bên phải - CẤM TAP BỎ QUA DUPLICATE"),
        ),
        allowed_next_states={
            "CHAOS_COPY_COMPLETE",
            "CHAOS_OBTAIN_REWARD",
            "CHAOS_SETTLEMENT",
            "CHAOS_MAP",
        },
        is_irreversible=True,
    ),

    # 8. CHAOS_SETTLEMENT: Màn hình kết toán phần thưởng
    "CHAOS_SETTLEMENT": ScreenDef(
        id="CHAOS_SETTLEMENT",
        name="Màn hình kết toán phần thưởng (Settlement)",
        positive_layouts=(
            (AnchorDef("settlement_title", (800, 30, 280, 80), 0.75, weight=1.5),),
        ),
        negative_anchors=(
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("remove_card_title", (80, 10, 470, 80), 0.65, negative=True),
            AnchorDef("chaos_event_icon", (0, 100, 160, 200), 0.65, negative=True),
            AnchorDef("choose_fate_title", (600, 800, 400, 100), 0.65, negative=True),
            AnchorDef("chaos_safe_zone_rest_icon", (250, 620, 350, 130), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_SETTLEMENT,
        handler=None,
        valid_tap_zones=(
            Zone(*ZONE_SETTLEMENT_CONTINUE, "Nút Continue cam"),
        ),
        forbidden_tap_zones=(
            Zone(*ZONE_SETTLEMENT_TEMP_RETURN, "Nút Temporary Return - NGUY HIỂM RỜI MÀN"),
            Zone(*ZONE_SETTLEMENT_VOUCHER, "Nút Obtain voucher - NGUY HIỂM"),
        ),
        allowed_next_states={
            "CHAOS_MAP",
            "CHAOS_SETTLEMENT",
        },
    ),

    # 9. CHAOS_AFTER_BATTLE: Nút Leave / Continue / Settlement sau trận
    "CHAOS_AFTER_BATTLE": ScreenDef(
        id="CHAOS_AFTER_BATTLE",
        name="Sau trận chiến (Leave / Continue / Settlement)",
        positive_layouts=(
            (AnchorDef("chaos_settlement_button", (1250, 750, 350, 150), 0.75, weight=1.2),),
            (AnchorDef("chaos_leave_button", (1250, 750, 350, 150), 0.72, weight=1.2),),
            (AnchorDef("chaos_continue_button", (1200, 750, 380, 140), 0.75, weight=1.2),),
        ),
        negative_anchors=(
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("remove_card_title", (80, 10, 470, 80), 0.65, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_DEFAULT,
        handler=None,
        valid_tap_zones=(
            Zone(1200, 750, 1580, 880, "Nút cam chuyển tiếp góc dưới phải"),
        ),
        forbidden_tap_zones=(),
        allowed_next_states={
            "CHAOS_SETTLEMENT",
            "CHAOS_OBTAIN_REWARD",
            "CHAOS_MAP",
        },
    ),

    # 10. CHAOS_CHOOSE_EPIPHANY: Chọn Thẻ Khai Sáng (Epiphany)
    "CHAOS_CHOOSE_EPIPHANY": ScreenDef(
        id="CHAOS_CHOOSE_EPIPHANY",
        name="Chọn Thẻ Khai Sáng (Epiphany)",
        positive_layouts=(
            (AnchorDef("epiphany_title", (500, 50, 600, 130), 0.75, weight=1.0),),
            (AnchorDef("card_epiphany_title", (500, 50, 600, 130), 0.75, weight=1.0),),
            (AnchorDef("card_reward_title", (500, 50, 600, 130), 0.78, weight=1.2),),
            (AnchorDef("epiphany_text_white", (600, 750, 350, 130), 0.75, weight=1.0),),
            (AnchorDef("select_attribute_title", (600, 80, 400, 80), 0.78, weight=1.2),),
            (AnchorDef("etched_memory_title", (550, 70, 500, 100), 0.75, weight=1.2),),
        ),
        negative_anchors=(
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("remove_card_title", (80, 10, 470, 80), 0.65, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_EPIPHANY,
        handler=None,
        valid_tap_zones=(
            Zone(200, 200, 1400, 800, "Vùng thẻ lựa chọn"),
        ),
        forbidden_tap_zones=(
            Zone(*ZONE_EPIPHANY_VIEW_ORIGINAL, "Nút View original - CẤM TAP"),
        ),
        allowed_next_states={
            "CHAOS_MAP",
            "CHAOS_EQUIPMENT",
            "CHAOS_OBTAIN_REWARD",
        },
        is_irreversible=True,
    ),

    # 11. CHAOS_REMOVE_CARD: Xóa thẻ bài
    "CHAOS_REMOVE_CARD": ScreenDef(
        id="CHAOS_REMOVE_CARD",
        name="Xóa thẻ bài (Remove Card)",
        positive_layouts=(
            (AnchorDef("remove_card_title", (80, 10, 470, 80), 0.75, weight=1.2),),
        ),
        negative_anchors=(
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("epiphany_title", (500, 50, 600, 130), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_REMOVE,
        handler=None,
        valid_tap_zones=(
            Zone(100, 120, 1500, 780, "Vùng thẻ bài hiển thị"),
        ),
        forbidden_tap_zones=(
            Zone(*ZONE_REMOVE_CANCEL, "Nút Cancel xóa thẻ - CẤM TAP"),
            Zone(*ZONE_REMOVE_EXECUTE, "Nút Remove xóa thẻ - CẤM TAP MẶC ĐỊNH"),
        ),
        allowed_next_states={
            "CHAOS_MAP",
            "CHAOS_REMOVE_CARD",
            "CHAOS_CHOOSE_EPIPHANY",
        },
        is_irreversible=True,
    ),

    # 12. CHAOS_COPY_COMPLETE: Hoàn tất nhân bản thẻ
    "CHAOS_COPY_COMPLETE": ScreenDef(
        id="CHAOS_COPY_COMPLETE",
        name="Nhân bản thẻ hoàn tất (Copy Complete)",
        positive_layouts=(
            (AnchorDef("tap_to_close", (600, 800, 400, 100), 0.70, weight=1.2),),
        ),
        negative_anchors=(
            AnchorDef("duplicate_card_title", (600, 85, 450, 70), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            AnchorDef("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        k_frames=K_FRAMES_DEFAULT,
        handler=None,
        valid_tap_zones=(
            Zone(650, 800, 960, 880, "Vùng chạm để đóng Tap to close"),
        ),
        forbidden_tap_zones=(),
        allowed_next_states={
            "CHAOS_OBTAIN_REWARD",
            "CHAOS_MAP",
            "CHAOS_SETTLEMENT",
        },
    ),

    # 13. IN_MATCH: Đang trong trận đấu
    "IN_MATCH": ScreenDef(
        id="IN_MATCH",
        name="Đang trong trận đấu",
        positive_layouts=(
            (AnchorDef("in_match_check", (1320, 680, 200, 200), 0.70, weight=1.2),),
        ),
        negative_anchors=(
            AnchorDef("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            AnchorDef("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            AnchorDef("settlement_title", (800, 30, 280, 80), 0.65, negative=True),
        ),
        k_frames=1,
        handler=None,
        valid_tap_zones=(),
        forbidden_tap_zones=(),
        allowed_next_states={
            "CHAOS_AFTER_BATTLE",
            "CHAOS_OBTAIN_REWARD",
            "IN_MATCH",
        },
    ),
}
