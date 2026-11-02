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
    count: Optional[int] = None                 # Số đếm panel OCR (3, 2, 1)
    obtain_btn_center: Tuple[int, int] = (1426, 825)
    battle_end_detected: bool = False
    skip_detected: bool = False
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


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
    sword_button_detected: bool = False         # Nút tròn kiếm góc dưới phải
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
    settlement_title_score: float = 0.0
    temporary_return_detected: bool = False
    voucher_detected: bool = False
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SafeZoneFacts:
    rest_available: bool = False
    skip_available: bool = False
    rest_center: Tuple[int, int] = (380, 680)
    skip_center: Tuple[int, int] = (1426, 825)
    interactions_count: int = 0
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)


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
class DuplicateCardFacts:
    title_detected: bool = False
    skip_detected: bool = False
    cards: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    raw_details: Dict[str, Any] = field(default_factory=dict)

