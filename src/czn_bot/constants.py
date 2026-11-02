"""
Constants for Chaos Zero Nightmare Bot.
Target resolution: 1600x900.
"""
import os

# ── Resolution ────────────────────────────────────────────────
SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900

# ── Base & Data Directories ───────────────────────────────────
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SRC_DIR, "..", ".."))

# Primary data directories
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DATA_TEMPLATES_DIR = os.path.join(DATA_DIR, "templates")
DATA_RULES_DIR = os.path.join(DATA_DIR, "rules")

# Legacy compatibility paths
LEGACY_TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
TEMPLATES_DIR = DATA_TEMPLATES_DIR if os.path.exists(DATA_TEMPLATES_DIR) else LEGACY_TEMPLATES_DIR

LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# ── Detection & Timing Constants ──────────────────────────────
MATCH_THRESHOLD = 0.80        # cv2.matchTemplate confidence threshold
CONFIRM_FRAMES = 3            # Consecutive identical frames before acting
MAX_SAME_ACTION = 3           # Stop after N repeated actions with no change
MAX_UNKNOWN_SCREENSHOTS = 50  # Keep up to 50 latest unknown screenshots
DEFAULT_LOOP_DELAY = 1.5      # Delay between decision cycles (seconds)
STALL_TIMEOUT = 30.0          # Watchdog default timeout in seconds

# Per-state watchdog timeouts (replaces indefinite STALL_EXEMPT)
STATE_STALL_TIMEOUTS = {
    "IN_MATCH": 300.0,              # Max 5 minutes for active battle
    "CHAOS_CHOOSE_EPIPHANY": 60.0,   # Max 60 seconds for card choice
    "CHAOS_CHOOSE_FATE": 60.0,       # Max 60 seconds for fate choice
    "CHAOS_EVENT": 60.0,             # Max 60 seconds for random event choice
    "STORY_DIALOGUE": 90.0,         # Max 90 seconds for dialogue progression
    "CHAOS_SETTLEMENT": 60.0,       # Max 60 seconds for settlement screen
    "CHAOS_SELECT_DUPLICATE_CARD": 60.0, # Max 60 seconds for duplicate card choice
}

# ── Chaos Mode Safety Guards (P0) ──────────────────────────────
CHAOS_MAP_MIN_PIN_SCORE = 0.75           # Ngưỡng tin cậy tối thiểu của ghim minimap (ngăn cách 0.607 âm và 0.889 dương)
EQUIP_SUBSTEP_TIMEOUT = 5.0              # Timeout tối đa (giây) cho mỗi bước chọn trang bị
MAX_EQUIP_SUBSTEP_ATTEMPTS = 5           # Số lần thử tối đa cho mỗi sub-step trang bị
MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS = 4      # Số lần chờ tối đa màn hình rời khỏi CHAOS_EQUIPMENT sau khi Confirm (~1.2s)
STATE_SETTLING_FRAMES = 1                # Số frame ổn định tối thiểu trước khi cho phép tap nhạy cảm
# Nguồn sự thật duy nhất (single source of truth) về số frame ổn định yêu cầu theo state
PER_STATE_SETTLING_FRAMES = {
    "CHAOS_MAP": 1,
    "CHAOS_EQUIPMENT": 1,
    "CHAOS_SAFE_ZONE": 1,
    "CHAOS_EVENT": 1,
    "CHAOS_CHOOSE_FATE": 1,
    "CHAOS_CHOOSE_EPIPHANY": 1,
    "CHAOS_CARD_REWARD": 1,
    "CHAOS_OBTAIN_REWARD": 1,
    "CHAOS_AFTER_BATTLE": 1,
    "CHAOS_SETTLEMENT": 2,
    "CHAOS_SELECT_DUPLICATE_CARD": 2,
}

# ── Chaos Equipment Screen Constants (1600x900) ───────────────
EQUIP_CHAR_ROWS = [(1100, 270), (1100, 470), (1100, 670)]      # Tâm 3 hàng thẻ combatant
EQUIP_COMBATANT_CARD_TOPS = [183, 383, 583]                     # Tọa độ đỉnh y của 3 thẻ combatant
EQUIP_RECOMMENDED_LABEL_OFFSET_Y = 5                            # Offset nhãn Recommended từ đỉnh thẻ (~+5)
EQUIP_SELECT_COMBATANT_ROI = (1365, 105, 1575, 138)             # Dòng "Select combatant." (1365,105,1575,138)
EQUIP_EXTRACT_BTN_ROI = (912, 805, 1260, 870)                   # Nút Extract màu đỏ (912-1260, 805-870)
EQUIP_CONFIRM_BTN_ROI = (1275, 805, 1577, 870)                  # Nút Confirm màu cam (1275-1577, 805-870)
EQUIP_CONFIRM_COORD = (1425, 838)                               # Tọa độ tap tâm nút Confirm (1425, 838)
EQUIP_AVG_SIG_COST_ROI = (110, 820, 360, 855)                  # Vùng nhãn Avg. Sig. Card Cost (110,820,360,855)
EQUIP_RECOMMENDED_TAG_CROP = (1330, 362, 1520, 394)             # Vùng crop nhãn Recommended trên thẻ giữa
EQUIP_RECOMMENDED_SEARCH_ROI = (1320, 160, 1525, 760)           # Vùng TÌM nhãn Recommended trên cả 3 thẻ
EQUIP_COMBATANTS_BOX = (972, 183, 1508, 758)                    # Bounding box của cả 3 thẻ combatant
EQUIP_CONFIRM_ORANGE_THRESHOLD = 0.15                           # Ngưỡng tỷ lệ pixel cam HSV của nút Confirm


# ── Chaos Mode Guard Boxes & Constants (Giai đoạn 2.5) ────────
AUTO_CONFIRM_LOOT_DIALOG = True          # Tự động Confirm loot dialog (không dùng thẻ loot voucher)
SETTLEMENT_TEMP_RETURN_BOX = (824, 792, 1126, 858)   # Nút Temporary Return ở Settlement
SETTLEMENT_OBTAIN_VOUCHER_BOX = (1272, 318, 1572, 378) # Nút Obtain-voucher ở Settlement
OBTAIN_SKIP_BOX = (945, 790, 1247, 860)              # Nút Skip trắng ở Obtain
DUPLICATE_SKIP_BOX = (1450, 810, 1560, 870)          # Nút Skip ở Duplicate Card
EVENT_SWORD_BTN_BOX = (1450, 715, 1580, 845)         # Nút tròn chiến đấu (kiếm) ở Event
MAX_OBTAIN_SAME_COUNT_TAPS = 3           # Số lần tap Obtain tối đa nếu số đếm không đổi
MAX_OBTAIN_TOTAL_TAPS = 6                # Giới hạn tổng số lần tap Obtain mỗi màn

# ── Feature Flags ─────────────────────────────────────────────
ENABLE_DYNAMIC_ISLAND_DETECTION = True
ENABLE_HYBRID_VERIFICATION = os.getenv("ENABLE_HYBRID_VERIFICATION", "true").lower() in ("1", "true", "yes")
HYBRID_VERIFICATION_PAD = 25  # ROI expansion padding in px for secondary verification

# ── Frame Stability & Transition Validation ───────────────────
ENABLE_FRAME_STABILITY = True
FRAME_STABILITY_THRESHOLD = 10.0      # cv2.absdiff mean pixel difference threshold
FRAME_STABILITY_DELAY = 0.18          # Delay between 2 frames for consecutive capture (seconds)
ENABLE_TRANSITION_VALIDATION = True
INVALID_TRANSITION_CONFIRM_FRAMES = 6 # Confirmation frames required for invalid state jumps

# ── Per-template Threshold Overrides ───────────────────────────
TEMPLATE_THRESHOLDS = {
    "in_match_check":       0.70,
    "retry_button":         0.70,
    "retry_button_new":     0.70,
    "retry_button_text":    0.70,
    "retry_button_refresh": 0.70,
    "retry_button_alt":     0.70,
    "retry_button_grey":    0.70,
    "chaos_leave_button":   0.72,
    "story_node_play":      0.70,
    "story_title":          0.85,
    "story_dialogue_skip":  0.78,
    "story_dialogue_auto":  0.78,
    "confirm_button_purple": 0.75,
    "story_reward_text":    0.75,
    "view_original":        0.75,
    "epiphany_title":       0.75,
    "card_epiphany_title":  0.75,
    "card_reward_title":    0.78,
    "chaos_safe_zone_skip": 0.75,
    "chaos_safe_zone_rest_icon": 0.75,
    "chaos_safe_zone_confirm_btn": 0.75,
    "chaos_obtain_button":  0.80,
    "chaos_continue_button": 0.78,
    "view_original_white":  0.75,
    "epiphany_text_white":  0.75,
    "equipment_title":      0.75,
    "select_attribute_title": 0.78,
    "modal_close_button":   0.80,
    "chaos_info_title":     0.75,
    "chaos_settlement_button": 0.80,
    "etched_memory_title":   0.75,
    "tap_to_close":          0.75,
    "choose_fate_title":     0.75,
    "remove_card_title":     0.75,
    "chaos_event_icon":      0.75,
    "chaos_event_badge":     0.75,
    "chaos_event_star_icon": 0.70,
    "chaos_event_battle_btn": 0.75,
    "equip_select_combatant": 0.75,
    "equip_extract_button":   0.75,
    "equip_avg_sig_cost":     0.75,
    "equip_recommended_tag":  0.75,
    "equip_confirm_ready":    0.75,
    "equip_confirm_disabled": 0.75,
    "settlement_title":        0.75,
    "duplicate_card_title":    0.75,
}

# ── Template File Names ───────────────────────────────────────
TEMPLATES = {
    "effect_title":         "effect_title.png",
    "draw_pile_title":      "draw_pile_title.png",
    "stage_info_title":     "stage_info_title.png",
    "monster_info_title":   "monster_info_title.png",
    "pause_title":          "pause_title.png",
    "reward_text":          "reward_text.png",
    "retry_button":         "retry_button.png",
    "retry_button_alt":     "retry_button_alt.png",
    "retry_button_grey":    "retry_button_grey.png",
    "retry_button_new":     "retry_button_new.png",
    "retry_button_text":    "retry_button_text.png",
    "retry_button_refresh": "retry_button_refresh.png",
    "next_mission_button":  "next_mission_button.png",
    "confirm_button":       "confirm_button.png",
    "in_match_check":       "in_match_check.png",
    "close_x":              "close_x.png",
    "pre_enter_mission":    "pre_enter_mission.png",
    "pre_enter_team":       "pre_enter_team.png",
    "chaos_leave_button":   "chaos_leave_button.png",
    "chaos_node_pin":       "chaos_node_pin.png",
    "chaos_node_boss":      "chaos_node_boss.png",
    "chaos_node_sword":     "chaos_node_sword.png",
    "chaos_node_fire":      "chaos_node_fire.png",
    "chaos_node_event":     "chaos_node_event.png",
    "chaos_node_elite":     "chaos_node_elite.png",
    "chaos_node_waypoint":  "chaos_node_waypoint.png",
    "story_node_play":      "story_node_play.png",
    "story_title":          "story_title.png",
    "story_dialogue_skip":  "story_dialogue_skip.png",
    "story_dialogue_auto":  "story_dialogue_auto.png",
    "confirm_button_purple": "confirm_button_purple.png",
    "story_reward_text":    "story_reward_text.png",
    "view_original":        "view_original.png",
    "epiphany_title":       "epiphany_title.png",
    "card_epiphany_title":  "card_epiphany_title.png",
    "chaos_safe_zone_skip": "chaos_safe_zone_skip.png",
    "chaos_safe_zone_rest_icon": "chaos_safe_zone_rest_icon.png",
    "chaos_safe_zone_confirm_btn": "chaos_safe_zone_confirm_btn.png",
    "chaos_obtain_button":  "chaos_obtain_button.png",
    "chaos_continue_button": "chaos_continue_button.png",
    "card_reward_title":    "card_reward_title.png",
    "memory_obtained_title": "memory_obtained_title.png",
    "view_original_white":  "view_original_white.png",
    "epiphany_text_white":  "epiphany_text_white.png",
    "equipment_title":      "equipment_title.png",
    "select_attribute_title": "select_attribute_title.png",
    "modal_close_button":   "modal_close_button.png",
    "chaos_info_title":     "chaos_info_title.png",
    "chaos_settlement_button": "chaos_settlement_button.png",
    "etched_memory_title":   "etched_memory_title.png",
    "tap_to_close":          "tap_to_close.png",
    "choose_fate_title":     "choose_fate_title.png",
    "remove_card_title":     "remove_card_title.png",
    "chaos_enter_lobby":     "chaos_enter_lobby.png",
    "chaos_event_icon":      "chaos_event_icon.png",
    "chaos_event_badge":     "chaos_event_badge.png",
    "chaos_event_star_icon": "chaos_event_star_icon.png",
    "chaos_event_battle_btn": "chaos_event_battle_btn.png",
    # TODO: User cung cấp 6 template trang bị mới dưới đây
    "equip_select_combatant": "equip_select_combatant.png",
    "equip_extract_button":   "equip_extract_button.png",
    "equip_avg_sig_cost":     "equip_avg_sig_cost.png",
    "equip_recommended_tag":  "equip_recommended_tag.png",
    "equip_confirm_ready":    "equip_confirm_ready.png",
    "equip_confirm_disabled": "equip_confirm_disabled.png",
    "settlement_title":        "settlement_title.png",
    "duplicate_card_title":    "duplicate_card_title.png",
}

