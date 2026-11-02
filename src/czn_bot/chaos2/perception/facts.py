"""
czn_bot.chaos2.perception.facts - Các dataclass Facts đại diện cho dữ kiện nhận biết được từ mỗi màn hình.
Tuân thủ Nguyên tắc 1: Perception tách rời hoàn toàn khỏi Hành động.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class EquipmentFacts:
    selected_row: Optional[int] = None           # 0, 1, hoặc 2
    recommended_row: Optional[int] = None       # 0, 1, hoặc 2
    confirm_ready: bool = False                 # Nút confirm đã sáng cam chưa
    extract_detected: bool = False              # Nút extract đỏ nguy hiểm
    confirm_center: Tuple[int, int] = (1426, 837)
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MapFacts:
    lanes: List[int] = field(default_factory=list)               # [1] hoặc [0, 1] hoặc [0, 1, 2]
    lane_types: Dict[int, str] = field(default_factory=dict)     # {0: "battle", 1: "event"}
    recommended_lane: Optional[int] = None
    arrows_detected: List[int] = field(default_factory=list)
    lane_body_points: Dict[int, Tuple[int, int]] = field(default_factory=dict)
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ObtainFacts:
    button_count: Optional[int] = None          # Số đếm trên nút Obtain đọc bằng OCR (3, 2, 1)
    count: Optional[int] = None                 # Giữ tương thích ngược với code cũ
    obtain_btn_center: Tuple[int, int] = (1426, 825)
    battle_end_detected: bool = False
    skip_detected: bool = False
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.button_count is not None and self.count is None:
            self.count = self.button_count
        elif self.count is not None and self.button_count is None:
            self.button_count = self.count


@dataclass
class EventChoice:
    index: int                                  # 0, 1, 2
    center: Tuple[int, int]
    text: str = ""
    has_curse: bool = False                     # Chữ tím (lời nguyền)
    is_battle: bool = False


@dataclass
class EventFacts:
    choices: List[EventChoice] = field(default_factory=list)
    is_waypoint: bool = False                   # Sự kiện chỉ có 1 waypoint ở giữa
    has_curse: bool = False
    sword_button_detected: bool = False         # Nút tròn kiếm góc dưới phải (tương thích ngược)
    sword_button_present: bool = False          # Nút kiếm có mặt trên màn hình (Item 7 / G6)
    sword_button_active: bool = False           # Nút kiếm đang sáng (active) vs xám (inactive)
    battle_btn_detected: bool = False           # Nút Battle cam
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DialogFacts:
    confirm_center: Optional[Tuple[int, int]] = None
    cancel_center: Optional[Tuple[int, int]] = None
    dialog_type: str = "generic"                # "rest" | "loot" | "generic"
    has_checkbox: bool = False                  # "Do not show until next login"
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SettlementFacts:
    continue_center: Tuple[int, int] = (1426, 825)
    continue_btn_center: Tuple[int, int] = (1426, 825)  # Alias rõ nghĩa (Item 9)
    settlement_title_score: float = 0.0
    temporary_return_detected: bool = False
    voucher_detected: bool = False
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.continue_btn_center != (1426, 825) and self.continue_center == (1426, 825):
            self.continue_center = self.continue_btn_center
        elif self.continue_center != (1426, 825) and self.continue_btn_center == (1426, 825):
            self.continue_btn_center = self.continue_center


@dataclass
class SafeZoneFacts:
    rest_available: bool = False
    skip_available: bool = False
    rest_center: Tuple[int, int] = (380, 680)
    skip_center: Tuple[int, int] = (1426, 825)
    interactions_count: int = 1
    interactions_left: int = 1                  # Số lượt tương tác còn lại (Item 9)
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.interactions_left != 1 and self.interactions_count == 1:
            self.interactions_count = self.interactions_left
        elif self.interactions_count != 1 and self.interactions_left == 1:
            self.interactions_left = self.interactions_count


@dataclass
class FateCard:
    index: int                                  # 0, 1, 2
    center: Tuple[int, int]
    text: str = ""
    is_selected: bool = False


@dataclass
class FateFacts:
    cards: List[FateCard] = field(default_factory=list)
    confirm_ready: bool = False                 # Nút confirm màu cam hay xám
    confirm_center: Tuple[int, int] = (1426, 837)
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DuplicateCardItem:
    index: int                                  # 0, 1, 2
    name: str = ""
    cost: int = 0
    card_type: str = "Skill"
    center: Tuple[int, int] = (0, 0)
    has_pin: bool = False                       # Biểu tượng ghim ở góc phải trên


@dataclass
class DuplicateFacts:
    title_detected: bool = False
    skip_detected: bool = False
    cards: List[DuplicateCardItem] = field(default_factory=list)
    num_cards: int = 0
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


# Alias tương thích ngược
DuplicateCardFacts = DuplicateFacts


@dataclass
class HpFacts:
    current_hp: int = 0
    max_hp: int = 0
    hp_fraction: float = 1.0
    is_low_hp: bool = False
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EpiphanyCard:
    index: int                                  # 0, 1, 2
    name: str = ""                              # vd: "Dual Creation"
    tag: str = ""                               # vd: "[Unique]" hoặc "[Unique / Initiation]"
    effect_text: str = ""                       # Nội dung hiệu ứng đầy đủ
    center: Tuple[int, int] = (0, 0)


@dataclass
class EpiphanyFacts:
    title_detected: bool = False
    cards: List[EpiphanyCard] = field(default_factory=list)
    has_view_original: bool = False
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RemoveFacts:
    cards_visible: int = 8                      # Lưới 4 cột x 2 hàng nhìn thấy (Item 7 / G7)
    remove_enabled: bool = False                # False = Nút Remove xám; True = sáng cam sau khi đã chọn thẻ
    selected_count: int = 0                     # 0 hoặc 1
    budget_used: int = 0                        # 0pt hoặc 20pt
    budget_max: int = 130
    removals_used: int = 0                      # 0 hoặc 1
    removals_max: int = 5
    scroll_ratio: float = 0.0                   # Vị trí thanh cuộn (0.0 = top)
    at_top: bool = True
    at_bottom: bool = False
    cancel_center: Tuple[int, int] = (205, 830)
    remove_center: Tuple[int, int] = (1400, 830)
    selected_card_name: Optional[str] = None    # vd: "Standing Blade" khi selected
    has_pin_cards: List[str] = field(default_factory=list) # Danh sách thẻ có ghim
    has_scroll_bar: bool = True                 # Lưới thẻ cuộn được
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CopyCompleteFacts:
    has_copy_complete: bool = False
    duplicated_card_name: Optional[str] = None
    close_center: Tuple[int, int] = (800, 845)  # "Tap to close the window"
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)

