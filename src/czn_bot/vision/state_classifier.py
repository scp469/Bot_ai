"""
state_classifier.py - Phân loại state màn hình bằng bằng chứng chéo (evidence fusion).

Thay cho chuỗi if "khớp đầu tiên thắng" trong detector.detect():
  1. Mỗi State khai báo nhiều "neo" (anchor): neo dương (phải thấy) và neo âm (không được thấy).
  2. Chấm điểm TẤT CẢ state, không dừng ở state đầu tiên vượt ngưỡng.
  3. Hai state điểm sát nhau -> AMBIGUOUS (không hành động, chụp lại khung hình).
  4. TemporalFilter: chỉ chốt state khi ổn định trên nhiều khung hình.
  5. screen_changed(): kiểm chứng sau khi tap có làm màn hình đổi không.

`matcher(screen, key, region) -> (score, point)` chính là ScreenDetector.match() hiện có.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Set, Any
import logging

import cv2
import numpy as np

logger = logging.getLogger("ChaosBot.StateClassifier")

Region = Tuple[int, int, int, int]  # x, y, w, h
Matcher = Callable[[np.ndarray, str, Optional[Region]], Tuple[float, Optional[Tuple[int, int]]]]

AMBIGUOUS = "AMBIGUOUS"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Anchor:
    key: str                 # tên template
    region: Region           # vùng tìm kiếm (x, y, w, h)
    threshold: float         # ngưỡng khớp tối thiểu
    weight: float = 1.0
    negative: bool = False   # True: nếu khớp thì LOẠI state này


@dataclass(frozen=True)
class StateSpec:
    state: str
    anchors: Tuple[Anchor, ...]
    min_hits: int = 1        # số neo dương tối thiểu phải khớp
    priority: int = 0        # chỉ dùng để phá hòa, không quyết định


@dataclass
class Result:
    state: str
    confidence: float = 0.0
    margin: float = 0.0
    ranked: List[Tuple[str, float]] = field(default_factory=list)
    evidence: Dict[str, float] = field(default_factory=dict)  # key -> score (để debug)
    best_coords: Dict[str, Tuple[int, int]] = field(default_factory=dict)  # key -> coord


# ── Bộ đặc tả State chuẩn cho Chaos Zero Nightmare (1600x900) ─────────────────
DEFAULT_STATE_SPECS: Tuple[StateSpec, ...] = (
    # 1. CHAOS_SAFE_ZONE: Trạm nghỉ đốm lửa (Layout 1: Camp chính có nút Skip và nút Rest)
    StateSpec(
        state="CHAOS_SAFE_ZONE",
        anchors=(
            Anchor("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.75, weight=1.0),
            Anchor("chaos_safe_zone_rest_icon", (250, 620, 350, 130), 0.75, weight=1.2),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("card_reward_title", (500, 50, 600, 130), 0.65, negative=True),
            Anchor("epiphany_title", (500, 50, 600, 130), 0.65, negative=True),
            Anchor("choose_fate_title", (600, 800, 400, 100), 0.65, negative=True),
            Anchor("chaos_event_badge", (0, 100, 160, 200), 0.65, negative=True),
            Anchor("chaos_event_icon", (0, 100, 160, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=10,
    ),

    # 1b. CHAOS_SAFE_ZONE: Popup Modal Rest (Layout 2: Hộp thoại xác nhận nghỉ ngơi / hồi máu)
    StateSpec(
        state="CHAOS_SAFE_ZONE",
        anchors=(
            Anchor("chaos_safe_zone_confirm_btn", (800, 590, 510, 100), 0.75, weight=1.5),
            Anchor("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.75, weight=0.8),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("card_reward_title", (500, 50, 600, 130), 0.65, negative=True),
            Anchor("epiphany_title", (500, 50, 600, 130), 0.65, negative=True),
            Anchor("choose_fate_title", (600, 800, 400, 100), 0.65, negative=True),
            Anchor("chaos_event_badge", (0, 100, 160, 200), 0.65, negative=True),
            Anchor("chaos_event_icon", (0, 100, 160, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=10,
    ),

    # 2. CHAOS_EQUIPMENT: Màn hình gắn trang bị
    StateSpec(
        state="CHAOS_EQUIPMENT",
        anchors=(
            Anchor("equipment_title", (650, 70, 350, 110), 0.75, weight=1.2),
            Anchor("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.65, negative=True),
            Anchor("chaos_safe_zone_rest_icon", (250, 620, 350, 130), 0.65, negative=True),
            Anchor("chaos_safe_zone_confirm_btn", (800, 590, 510, 100), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("card_reward_title", (500, 50, 600, 130), 0.65, negative=True),
            Anchor("epiphany_title", (500, 50, 600, 130), 0.65, negative=True),
        ),
        min_hits=1,
        priority=10,
    ),

    # 3. CHAOS_EVENT: Sự kiện ngẫu nhiên (Layout 1: Badge thú / Cá cược)
    StateSpec(
        state="CHAOS_EVENT",
        anchors=(
            Anchor("chaos_event_badge", (0, 100, 160, 200), 0.75, weight=1.0),
            Anchor("chaos_event_icon", (0, 100, 160, 200), 0.75, weight=1.0),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.65, negative=True),
            Anchor("chaos_settlement_button", (1200, 750, 400, 150), 0.70, negative=True),
            Anchor("chaos_leave_button", (1200, 750, 400, 150), 0.70, negative=True),
        ),
        min_hits=1,
        priority=9,
    ),
    # 3b. CHAOS_EVENT: Sự kiện Waypoint / Di tích / Thần điện (Layout 2: Badge Ngôi sao 8 cánh)
    StateSpec(
        state="CHAOS_EVENT",
        anchors=(
            Anchor("chaos_event_star_icon", (0, 100, 160, 200), 0.70, weight=1.2),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.65, negative=True),
            Anchor("chaos_settlement_button", (1200, 750, 400, 150), 0.70, negative=True),
            Anchor("chaos_leave_button", (1200, 750, 400, 150), 0.70, negative=True),
        ),
        min_hits=1,
        priority=9,
    ),
    # 3c. CHAOS_EVENT: Sự kiện giao tranh có nút Battle
    StateSpec(
        state="CHAOS_EVENT",
        anchors=(
            Anchor("chaos_event_battle_btn", (1380, 750, 200, 140), 0.75, weight=1.0),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.65, negative=True),
            Anchor("chaos_settlement_button", (1200, 750, 400, 150), 0.70, negative=True),
            Anchor("chaos_leave_button", (1200, 750, 400, 150), 0.70, negative=True),
        ),
        min_hits=1,
        priority=9,
    ),

    # 4. CHAOS_MAP: Bản đồ chọn đường
    StateSpec(
        state="CHAOS_MAP",
        anchors=(
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.70, weight=1.0),
            Anchor("chaos_node_boss", (0, 500, 700, 400), 0.70, weight=1.0),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.65, negative=True),
            Anchor("card_reward_title", (500, 50, 600, 130), 0.65, negative=True),
            Anchor("epiphany_title", (500, 50, 600, 130), 0.65, negative=True),
            Anchor("chaos_event_badge", (0, 100, 160, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=8,
    ),

    # 5. CHAOS_CHOOSE_EPIPHANY: Chọn Thẻ Khai Sáng / Thẻ bài / Lựa chọn định mệnh (Tách theo từng sub-layout)
    StateSpec(
        state="CHAOS_CHOOSE_EPIPHANY",
        anchors=(
            Anchor("epiphany_title", (500, 50, 600, 130), 0.75, weight=1.0),
            Anchor("view_original", (1200, 20, 380, 160), 0.75, weight=1.0),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        min_hits=1,
        priority=7,
    ),
    StateSpec(
        state="CHAOS_CHOOSE_EPIPHANY",
        anchors=(
            Anchor("card_epiphany_title", (500, 50, 600, 130), 0.75, weight=1.0),
            Anchor("view_original", (1200, 20, 380, 160), 0.75, weight=1.0),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        min_hits=1,
        priority=7,
    ),
    StateSpec(
        state="CHAOS_CHOOSE_EPIPHANY",
        anchors=(
            Anchor("epiphany_text_white", (600, 750, 350, 130), 0.75, weight=1.0),
            Anchor("view_original_white", (1200, 20, 380, 160), 0.75, weight=1.0),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        min_hits=1,
        priority=7,
    ),
    StateSpec(
        state="CHAOS_CHOOSE_EPIPHANY",
        anchors=(
            Anchor("card_reward_title", (500, 50, 600, 130), 0.78, weight=1.2),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        min_hits=1,
        priority=7,
    ),
    StateSpec(
        state="CHAOS_CHOOSE_EPIPHANY",
        anchors=(
            Anchor("choose_fate_title", (600, 800, 400, 100), 0.75, weight=1.2),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        min_hits=1,
        priority=7,
    ),
    StateSpec(
        state="CHAOS_CHOOSE_EPIPHANY",
        anchors=(
            Anchor("select_attribute_title", (600, 80, 400, 80), 0.78, weight=1.2),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        min_hits=1,
        priority=7,
    ),
    StateSpec(
        state="CHAOS_CHOOSE_EPIPHANY",
        anchors=(
            Anchor("etched_memory_title", (550, 70, 500, 100), 0.75, weight=1.2),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        min_hits=1,
        priority=7,
    ),
    StateSpec(
        state="CHAOS_CHOOSE_EPIPHANY",
        anchors=(
            Anchor("remove_card_title", (80, 10, 470, 80), 0.75, weight=1.2),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
        ),
        min_hits=1,
        priority=7,
    ),

    # 6. CHAOS_OBTAIN_REWARD: Nút Obtain sau nhận thưởng
    StateSpec(
        state="CHAOS_OBTAIN_REWARD",
        anchors=(
            Anchor("chaos_obtain_button", (1100, 750, 490, 140), 0.78, weight=1.2),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("chaos_event_badge", (0, 100, 160, 200), 0.65, negative=True),
            Anchor("card_reward_title", (500, 50, 600, 130), 0.65, negative=True),
        ),
        min_hits=1,
        priority=8,
    ),

    # 7. CHAOS_AFTER_BATTLE: Kết thúc trận Chaos (Leave / Continue / Settlement riêng từng layout)
    StateSpec(
        state="CHAOS_AFTER_BATTLE",
        anchors=(
            Anchor("chaos_leave_button", (1250, 750, 350, 150), 0.72, weight=1.2),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("chaos_event_badge", (0, 100, 160, 200), 0.65, negative=True),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
        ),
        min_hits=1,
        priority=8,
    ),
    StateSpec(
        state="CHAOS_AFTER_BATTLE",
        anchors=(
            Anchor("chaos_continue_button", (1200, 750, 380, 140), 0.75, weight=1.2),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("chaos_event_badge", (0, 100, 160, 200), 0.65, negative=True),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
        ),
        min_hits=1,
        priority=8,
    ),
    StateSpec(
        state="CHAOS_AFTER_BATTLE",
        anchors=(
            Anchor("chaos_settlement_button", (1250, 750, 350, 150), 0.75, weight=1.2),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("chaos_event_badge", (0, 100, 160, 200), 0.65, negative=True),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
        ),
        min_hits=1,
        priority=8,
    ),

    # 8. IN_MATCH: Đang trong trận chiến
    StateSpec(
        state="IN_MATCH",
        anchors=(
            Anchor("in_match_check", (1320, 680, 200, 200), 0.70, weight=1.2),
            Anchor("chaos_node_pin", (0, 500, 700, 400), 0.65, negative=True),
            Anchor("equipment_title", (650, 70, 350, 110), 0.65, negative=True),
            Anchor("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.65, negative=True),
            Anchor("chaos_leave_button", (1250, 750, 350, 150), 0.65, negative=True),
            Anchor("chaos_continue_button", (1200, 750, 380, 140), 0.65, negative=True),
        ),
        min_hits=1,
        priority=9,
    ),

    # 9. STORY_DIALOGUE: Hội thoại nhân vật
    StateSpec(
        state="STORY_DIALOGUE",
        anchors=(
            Anchor("story_dialogue_skip", (1200, 15, 140, 80), 0.78, weight=1.0),
            Anchor("story_dialogue_auto", (1330, 15, 140, 80), 0.78, weight=1.0),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("chaos_continue_button", (1200, 750, 380, 140), 0.65, negative=True),
            Anchor("chaos_leave_button", (1250, 750, 350, 150), 0.65, negative=True),
            Anchor("chaos_obtain_button", (1100, 750, 490, 140), 0.65, negative=True),
            Anchor("chaos_safe_zone_skip", (1200, 750, 380, 140), 0.65, negative=True),
        ),
        min_hits=1,
        priority=7,
    ),

    # 10. STORY_MAP: Bản đồ cốt truyện
    StateSpec(
        state="STORY_MAP",
        anchors=(
            Anchor("story_title", (60, 10, 130, 70), 0.85, weight=1.2),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
            Anchor("close_x", (1350, 0, 240, 120), 0.75, negative=True),
            Anchor("chaos_leave_button", (1250, 750, 350, 150), 0.65, negative=True),
            Anchor("chaos_continue_button", (1200, 750, 380, 140), 0.65, negative=True),
        ),
        min_hits=1,
        priority=6,
    ),

    # 11. PRE_MATCH_TEAM: Đội hình trước trận
    StateSpec(
        state="PRE_MATCH_TEAM",
        anchors=(
            Anchor("pre_enter_team", (1050, 750, 520, 140), 0.75, weight=1.2),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=6,
    ),

    # 12. PRE_MATCH_MISSION: Chuẩn bị nhiệm vụ
    StateSpec(
        state="PRE_MATCH_MISSION",
        anchors=(
            Anchor("pre_enter_mission", (1000, 750, 570, 140), 0.75, weight=1.0),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=6,
    ),
    StateSpec(
        state="PRE_MATCH_MISSION",
        anchors=(
            Anchor("chaos_enter_lobby", (1200, 800, 390, 100), 0.80, weight=1.0),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=6,
    ),

    # 13. Popups:
    StateSpec(
        state="POPUP_EFFECT",
        anchors=(
            Anchor("effect_title", (80, 10, 250, 80), 0.75, weight=1.0),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=6,
    ),
    StateSpec(
        state="POPUP_EFFECT",
        anchors=(
            Anchor("memory_obtained_title", (700, 70, 300, 100), 0.75, weight=1.0),
            Anchor("tap_to_close", (500, 800, 600, 100), 0.75, weight=1.0),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=6,
    ),
    StateSpec(
        state="POPUP_DRAW_PILE",
        anchors=(
            Anchor("draw_pile_title", (80, 10, 250, 80), 0.75, weight=1.0),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=6,
    ),
    StateSpec(
        state="POPUP_STAGE_INFO",
        anchors=(
            Anchor("stage_info_title", (80, 10, 260, 80), 0.75, weight=1.0),
            Anchor("close_x", (1350, 0, 240, 120), 0.75, weight=1.0),
            Anchor("pre_enter_mission", (1000, 750, 570, 140), 0.75, negative=True),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=6,
    ),
    StateSpec(
        state="POPUP_MONSTER_INFO",
        anchors=(
            Anchor("monster_info_title", (30, 15, 260, 80), 0.75, weight=1.0),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=6,
    ),
    StateSpec(
        state="POPUP_PAUSE",
        anchors=(
            Anchor("pause_title", (80, 10, 300, 100), 0.75, weight=1.0),
            Anchor("close_x", (1350, 0, 240, 120), 0.75, weight=0.8),
            Anchor("modal_close_button", (650, 750, 300, 150), 0.75, weight=0.8),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=6,
    ),

    # 14. MATCH_DONE: Kết thúc màn chơi (chế độ Replay/Progress/Story)
    StateSpec(
        state="MATCH_DONE",
        anchors=(
            Anchor("reward_text", (600, 100, 400, 100), 0.75, weight=1.0),
            Anchor("retry_button", (900, 750, 400, 150), 0.70, weight=1.0),
            Anchor("retry_button_new", (900, 750, 400, 150), 0.70, weight=1.0),
            Anchor("next_mission_button", (900, 750, 400, 150), 0.70, weight=1.0),
            Anchor("confirm_button", (1250, 750, 350, 150), 0.75, weight=1.0),
            Anchor("confirm_button_purple", (1250, 750, 350, 150), 0.75, weight=1.0),
            Anchor("in_match_check", (1320, 680, 200, 200), 0.65, negative=True),
        ),
        min_hits=1,
        priority=5,
    ),
)


# Đồ thị chuyển trạng thái hợp lệ trong game
DEFAULT_ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "CHAOS_MAP": {
        "IN_MATCH", "CHAOS_EVENT", "CHAOS_SAFE_ZONE", "CHAOS_EQUIPMENT",
        "CHAOS_CHOOSE_EPIPHANY", "CHAOS_OBTAIN_REWARD", "POPUP_EFFECT",
        "TRANSITIONING", "CHAOS_MAP"
    },
    "IN_MATCH": {
        "CHAOS_AFTER_BATTLE", "CHAOS_OBTAIN_REWARD", "MATCH_DONE",
        "POPUP_PAUSE", "POPUP_DRAW_PILE", "TRANSITIONING", "IN_MATCH"
    },
    "CHAOS_AFTER_BATTLE": {
        "CHAOS_EQUIPMENT", "CHAOS_CHOOSE_EPIPHANY", "CHAOS_OBTAIN_REWARD",
        "CHAOS_MAP", "CHAOS_EVENT", "POPUP_EFFECT", "TRANSITIONING", "CHAOS_AFTER_BATTLE"
    },
    "CHAOS_EQUIPMENT": {
        "CHAOS_MAP", "CHAOS_CHOOSE_EPIPHANY", "CHAOS_AFTER_BATTLE",
        "POPUP_EFFECT", "TRANSITIONING", "CHAOS_EQUIPMENT"
    },
    "CHAOS_SAFE_ZONE": {
        "CHAOS_MAP", "POPUP_EFFECT", "TRANSITIONING", "CHAOS_SAFE_ZONE"
    },
    "CHAOS_EVENT": {
        "CHAOS_MAP", "CHAOS_AFTER_BATTLE", "IN_MATCH", "CHAOS_CHOOSE_EPIPHANY", "CHAOS_OBTAIN_REWARD",
        "POPUP_EFFECT", "TRANSITIONING", "CHAOS_EVENT"
    },
    "CHAOS_CHOOSE_EPIPHANY": {
        "CHAOS_MAP", "CHAOS_EQUIPMENT", "CHAOS_OBTAIN_REWARD",
        "POPUP_EFFECT", "TRANSITIONING", "CHAOS_CHOOSE_EPIPHANY"
    },
    "CHAOS_OBTAIN_REWARD": {
        "CHAOS_MAP", "CHAOS_AFTER_BATTLE", "POPUP_EFFECT", "TRANSITIONING", "CHAOS_OBTAIN_REWARD"
    },
    "PRE_MATCH_MISSION": {
        "PRE_MATCH_TEAM", "IN_MATCH", "CHAOS_MAP", "POPUP_STAGE_INFO", "POPUP_MONSTER_INFO",
        "POPUP_EFFECT", "TRANSITIONING", "PRE_MATCH_MISSION"
    },
    "PRE_MATCH_TEAM": {
        "IN_MATCH", "PRE_MATCH_MISSION", "POPUP_EFFECT", "TRANSITIONING", "PRE_MATCH_TEAM"
    },
    "MATCH_DONE": {
        "PRE_MATCH_MISSION", "STORY_MAP", "IN_MATCH", "POPUP_EFFECT", "TRANSITIONING", "MATCH_DONE"
    },
    "STORY_MAP": {
        "STORY_DIALOGUE", "PRE_MATCH_MISSION", "IN_MATCH", "POPUP_STAGE_INFO", "POPUP_EFFECT",
        "TRANSITIONING", "STORY_MAP"
    },
    "STORY_DIALOGUE": {
        "STORY_MAP", "IN_MATCH", "POPUP_EFFECT", "TRANSITIONING", "STORY_DIALOGUE"
    },
    "POPUP_EFFECT": {
        "CHAOS_MAP", "IN_MATCH", "STORY_MAP", "CHAOS_AFTER_BATTLE", "CHAOS_EVENT",
        "CHAOS_SAFE_ZONE", "CHAOS_CHOOSE_EPIPHANY", "CHAOS_OBTAIN_REWARD", "CHAOS_EQUIPMENT",
        "PRE_MATCH_MISSION", "PRE_MATCH_TEAM", "MATCH_DONE", "STORY_DIALOGUE",
        "POPUP_EFFECT", "TRANSITIONING"
    },
    "POPUP_DRAW_PILE": {"IN_MATCH", "POPUP_DRAW_PILE", "TRANSITIONING"},
    "POPUP_STAGE_INFO": {"STORY_MAP", "PRE_MATCH_MISSION", "POPUP_STAGE_INFO", "TRANSITIONING"},
    "POPUP_MONSTER_INFO": {"STORY_MAP", "PRE_MATCH_MISSION", "IN_MATCH", "POPUP_MONSTER_INFO", "TRANSITIONING"},
    "POPUP_PAUSE": {"IN_MATCH", "POPUP_PAUSE", "TRANSITIONING"},
    "TRANSITIONING": {
        "IN_MATCH", "CHAOS_MAP", "CHAOS_AFTER_BATTLE", "CHAOS_EQUIPMENT",
        "CHAOS_OBTAIN_REWARD", "CHAOS_CHOOSE_EPIPHANY", "CHAOS_SAFE_ZONE",
        "CHAOS_EVENT", "STORY_MAP", "STORY_DIALOGUE", "MATCH_DONE",
        "PRE_MATCH_MISSION", "PRE_MATCH_TEAM", "POPUP_EFFECT", "TRANSITIONING"
    },
}


class StateClassifier:
    def __init__(
        self,
        specs: Sequence[StateSpec] = DEFAULT_STATE_SPECS,
        matcher: Optional[Matcher] = None,
        min_confidence: float = 0.35,
        min_margin: float = 0.15,
    ):
        self.specs = list(specs)
        self.matcher = matcher
        self.min_confidence = min_confidence
        self.min_margin = min_margin

    def set_matcher(self, matcher: Matcher):
        self.matcher = matcher

    def classify(self, screen: Optional[np.ndarray]) -> Result:
        if screen is None or screen.size == 0 or self.matcher is None:
            return Result(UNKNOWN)

        cache: Dict[Tuple[str, Region], Tuple[float, Optional[Tuple[int, int]]]] = {}
        evidence: Dict[str, float] = {}
        best_coords: Dict[str, Tuple[int, int]] = {}
        best_coord_scores: Dict[str, float] = {}

        def match_anchor(a: Anchor) -> Tuple[float, Optional[Tuple[int, int]]]:
            k = (a.key, a.region)
            if k not in cache:
                try:
                    if a.region is not None:
                        res = self.matcher(screen, a.key, a.region)
                    else:
                        res = self.matcher(screen, a.key)
                except TypeError:
                    res = self.matcher(screen, a.key)
                except Exception:
                    res = (0.0, None)

                if isinstance(res, (tuple, list)) and len(res) >= 2:
                    score, pt = float(res[0]), res[1]
                elif isinstance(res, (int, float)):
                    score, pt = float(res), None
                else:
                    score, pt = 0.0, None

                cache[k] = (score, pt)
                prev_score = evidence.get(a.key, 0.0)
                evidence[a.key] = max(prev_score, score)
                if pt and (a.key not in best_coords or score > best_coord_scores.get(a.key, -1.0)):
                    best_coords[a.key] = pt
                    best_coord_scores[a.key] = score
            return cache[k]

        state_best: Dict[str, Tuple[float, int]] = {}
        for spec in self.specs:
            # 1. Kiểm tra neo âm: nếu bất kỳ neo âm nào khớp -> loại bỏ state này ngay
            if any(a.negative and match_anchor(a)[0] >= a.threshold for a in spec.anchors):
                continue

            # 2. Đếm các neo dương khớp
            pos = [a for a in spec.anchors if not a.negative]
            hits = [a for a in pos if match_anchor(a)[0] >= a.threshold]
            if len(hits) < spec.min_hits:
                continue

            # 3. Tính điểm tích lũy có trọng số
            total_w = sum(a.weight for a in pos) or 1.0
            got = sum(
                a.weight * min(1.0, (match_anchor(a)[0] - a.threshold) / max(1e-6, 1.0 - a.threshold) * 0.5 + 0.5)
                for a in hits
            )
            score_normalized = got / total_w
            if spec.state not in state_best or score_normalized > state_best[spec.state][0]:
                state_best[spec.state] = (score_normalized, spec.priority)

        if not state_best:
            return Result(UNKNOWN, evidence=evidence, best_coords=best_coords)

        ranked = [(st, sc, pri) for st, (sc, pri) in state_best.items()]

        # Sắp xếp theo (điểm số giảm dần, priority giảm dần)
        ranked.sort(key=lambda r: (r[1], r[2]), reverse=True)
        top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top[1] - second
        view = [(s, round(c, 3)) for s, c, _ in ranked]

        if top[1] < self.min_confidence:
            return Result(UNKNOWN, top[1], margin, view, evidence, best_coords)
        if len(ranked) > 1 and margin < self.min_margin:
            return Result(AMBIGUOUS, top[1], margin, view, evidence, best_coords)
        return Result(top[0], top[1], margin, view, evidence, best_coords)


class TemporalFilter:
    """
    Chốt state khi >= need/window khung hình gần nhất đồng thuận.
    AMBIGUOUS/UNKNOWN không được tính là phiếu cho bất kỳ state nào.
    Hỗ trợ đồ thị chuyển đổi hợp lệ để ngăn chặn các bước nhảy bất khả thi.
    """

    def __init__(
        self,
        window: int = 5,
        need: int = 3,
        allowed: Optional[Dict[str, Set[str]]] = None
    ):
        self.buf: deque = deque(maxlen=window)
        self.need = need
        self.allowed = allowed if allowed is not None else DEFAULT_ALLOWED_TRANSITIONS
        self.stable: Optional[str] = None
        self.last_settled: Optional[str] = None

    def push(self, r: Any) -> Optional[str]:
        state_str = r.state if hasattr(r, "state") else (r.value if hasattr(r, "value") else str(r))
        self.buf.append(state_str)
        votes = Counter(s for s in self.buf if s not in (AMBIGUOUS, UNKNOWN))
        if not votes:
            return self.stable
        cand, n = votes.most_common(1)[0]
        if n < self.need:
            return self.stable

        # Ràng buộc bước nhảy hợp lệ: đối chiếu với state ổn định gần nhất
        ref = self.last_settled if (self.last_settled and self.last_settled not in (AMBIGUOUS, UNKNOWN, "TRANSITIONING")) else self.stable
        if ref and cand != ref and cand not in (AMBIGUOUS, UNKNOWN, "TRANSITIONING") and self.allowed:
            if cand not in self.allowed.get(ref, {cand}):
                logger.debug(f"[TemporalFilter] Chuyển state {ref} -> {cand} không hợp lệ, giữ nguyên {self.stable}")
                return self.stable

        self.stable = cand
        if cand not in (AMBIGUOUS, UNKNOWN, "TRANSITIONING"):
            self.last_settled = cand
        return self.stable

    def reset(self):
        self.buf.clear()
        self.stable = None
        self.last_settled = None


def screen_changed(
    a: Optional[np.ndarray],
    b: Optional[np.ndarray],
    thresh: float = 4.0,
    region: Optional[Region] = None
) -> bool:
    """
    Sau khi tap: màn hình có thật sự đổi không?
    Dùng để phân biệt 'nhận diện sai' với 'tap không ăn' (nguyên nhân của việc kẹt hành động).
    """
    if a is None or b is None or a.size == 0 or b.size == 0:
        return True  # Không thể so sánh, giả định có thay đổi
    if a.shape != b.shape:
        return True

    if region:
        x, y, w, h = region
        x = max(0, min(a.shape[1] - 1, x))
        y = max(0, min(a.shape[0] - 1, y))
        w = max(1, min(a.shape[1] - x, w))
        h = max(1, min(a.shape[0] - y, h))
        a, b = a[y:y + h, x:x + w], b[y:y + h, x:x + w]

    sa = cv2.resize(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), (160, 90))
    sb = cv2.resize(cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), (160, 90))
    diff_val = float(np.mean(cv2.absdiff(sa, sb)))
    return diff_val >= thresh


def calibrate_threshold(
    pos_scores: Sequence[float],
    neg_scores: Sequence[float],
    safety: float = 0.5
) -> Optional[float]:
    """
    Ngưỡng nằm giữa (max điểm trên ảnh SAI) và (min điểm trên ảnh ĐÚNG).
    Trả None nếu hai nhóm chồng lấn -> template này không đủ phân biệt, cần cắt lại.
    """
    if not pos_scores or not neg_scores:
        return None
    lo, hi = max(neg_scores), min(pos_scores)
    if hi <= lo:
        return None
    return round(lo + (hi - lo) * safety, 3)