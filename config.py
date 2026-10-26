"""
Configuration for Chaos Zero Nightmare Bot.
All coordinates and templates are tailored for 1600x900 Android resolution.
"""
from enum import Enum
import os

# ── Base Paths ─────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(LOGS_DIR, exist_ok=True)


# ── State machine ──────────────────────────────────────────────

class State(Enum):
    IN_MATCH = "IN_MATCH"
    POPUP_EFFECT = "POPUP_EFFECT"
    POPUP_DRAW_PILE = "POPUP_DRAW_PILE"
    POPUP_STAGE_INFO = "POPUP_STAGE_INFO"
    POPUP_MONSTER_INFO = "POPUP_MONSTER_INFO"
    POPUP_PAUSE = "POPUP_PAUSE"
    MATCH_DONE = "MATCH_DONE"
    PRE_MATCH_MISSION = "PRE_MATCH_MISSION"
    PRE_MATCH_TEAM = "PRE_MATCH_TEAM"
    CHAOS_MAP = "CHAOS_MAP"
    CHAOS_AFTER_BATTLE = "CHAOS_AFTER_BATTLE"
    CHAOS_OBTAIN_REWARD = "CHAOS_OBTAIN_REWARD"
    CHAOS_CHOOSE_EPIPHANY = "CHAOS_CHOOSE_EPIPHANY"
    CHAOS_SAFE_ZONE = "CHAOS_SAFE_ZONE"
    STORY_MAP = "STORY_MAP"
    STORY_DIALOGUE = "STORY_DIALOGUE"
    TRANSITIONING = "TRANSITIONING"
    UNKNOWN = "UNKNOWN"


class Mode(Enum):
    REPLAY = "Đi lại màn"    # Retry the same stage
    PROGRESS = "Cày màn"     # Progress to next stage
    CHAOS = "Chế độ Chaos"   # Chaos mode auto pathfinding
    STORY = "Cốt truyện"     # Story mode campaign auto-progression


class LeftButton(Enum):
    RETRY = "Retry"
    RETRY_DISABLED = "Retry (Hết thể lực)"
    NEXT_MISSION = "Next Mission"
    NONE = "Không có nút trái"


# ── ADB ────────────────────────────────────────────────────────

ADB_HOST = "127.0.0.1"
ADB_PORT = 5555
SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900


# ── Detection ──────────────────────────────────────────────────

MATCH_THRESHOLD = 0.80      # cv2.matchTemplate confidence threshold
CONFIRM_FRAMES = 3          # Consecutive identical frames before acting
MAX_SAME_ACTION = 3         # Stop after N repeated actions with no change
MAX_UNKNOWN_SCREENSHOTS = 50  # Giữ tối đa 50 ảnh unknown mới nhất, xóa các ảnh vượt quá mốc này

# ── Hybrid Verification (Thẩm định kép OCR) ─────────────────────
ENABLE_HYBRID_VERIFICATION = os.getenv("ENABLE_HYBRID_VERIFICATION", "true").lower() in ("1", "true", "yes")
HYBRID_VERIFICATION_PAD = 25  # Mở rộng vùng crop 25px khi lần đầu không khớp

# Per-template threshold overrides (templates hay bị miss dùng threshold thấp hơn)
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
    # Tất cả template còn lại dùng MATCH_THRESHOLD mặc định (0.80)
}


# Tap coordinates (x, y) for each action on 1600x900.
TAP_COORDS = {
    # Default top-right popup close 'X' (used if dynamic X detection fails)
    "close_x_default":     (1535, 50),
    "close_monster_info":  (1100, 450),   # Tap empty area on right side to dismiss
    "left_button":         (1070, 830),   # Retry or Next Mission button center
    "right_button":        (1405, 830),   # Confirm button center
    "enter_mission":       (1290, 830),   # Enter button on mission info panel
    "enter_team":          (1470, 835),   # Enter button on team formation screen
    # Chaos Mode: Tọa độ khi màn hình có 3 đảo
    "chaos_island_3_top":    (1210, 140),
    "chaos_island_3_middle": (1330, 420),
    "chaos_island_3_bottom": (1350, 680),

    # Chaos Mode: Tọa độ khi màn hình có 2 đảo
    "chaos_island_2_top":    (1210, 140),
    "chaos_island_2_bottom": (1430, 400),
    "chaos_island_2_middle": (1430, 400),  # Đảo giữa khi màn hình có 2 đảo (Top & Mid)

    # Chaos Mode: Tọa độ khi màn hình có 1 đảo
    "chaos_island_1_middle": (1280, 520),

    # Fallback mặc định
    "chaos_island_top":    (1210, 140),
    "chaos_island_middle": (1330, 420),
    "chaos_island_bottom": (1430, 680),
    "chaos_leave_button":  (1426, 828),   # Nút Leave sau trận Chaos
    "chaos_continue_button": (1415, 825), # Nút Continue sau màn sự kiện/trận Chaos
    "chaos_obtain_button": (1380, 830),   # Nút Obtain nhận thưởng sau trận Chaos
    "chaos_settlement_button": (1425, 827), # Nút Settlement sau trận Chaos
    "chaos_safe_zone_skip": (1415, 825),  # Nút Skip tại trạm nghỉ an toàn (Campfire / Safe Zone)
    "chaos_safe_zone_confirm": (956, 568), # Nút Confirm trên popup xác nhận Skip trạm nghỉ
    "equipment_confirm":       (1360, 806), # Nút Confirm trang bị Chaos
    "modal_close_button":      (800, 837),  # Nút Close trên modal thông tin (View Details / Events)
    "tap_to_close":            (800, 850),  # Tọa độ chạm để đóng popup 'Tap to close the window.'

    # Story Mode coordinates
    "story_dialogue_skip":    (1272, 48),    # Nút tua nhanh hội thoại [▷|]
    "story_dialogue_auto":    (1395, 48),    # Nút Auto hội thoại [>>]
    "story_skip_confirm":     (950, 550),    # Nút Confirm trên popup "Skip this story?"
    "story_chapter_next":     (1194, 40),    # Mũi tên chuyển Chapter tiếp theo [>]
    "story_chapter_prev":     (417, 40),     # Mũi tên chuyển Chapter trước [<]
}

# Chaos Mode: Bật nhận diện động tâm đảo 3D bằng OpenCV
ENABLE_DYNAMIC_ISLAND_DETECTION = True



# Template image filenames
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
}


# ── Screen Scaler ──────────────────────────────────────────────

class ScreenScaler:
    """
    Scales coordinates and ROIs from standard 1600x900 resolution
    to any custom resolution if aspect ratio matches.
    """

    def __init__(
        self,
        actual_width: int,
        actual_height: int,
        base_width: int = 1600,
        base_height: int = 900,
    ):
        self.base_width = base_width
        self.base_height = base_height
        self.actual_width = actual_width
        self.actual_height = actual_height
        self.scale_x = actual_width / float(base_width)
        self.scale_y = actual_height / float(base_height)

    def to_actual_point(self, base_x: int, base_y: int):
        """Convert standard coordinate to actual screen coordinate."""
        return int(round(base_x * self.scale_x)), int(round(base_y * self.scale_y))

    def to_actual_roi(self, rx: int, ry: int, rw: int, rh: int):
        """Convert standard ROI (rx, ry, rw, rh) to actual screen ROI."""
        return (
            int(round(rx * self.scale_x)),
            int(round(ry * self.scale_y)),
            int(round(rw * self.scale_x)),
            int(round(rh * self.scale_y)),
        )


# ── Notification Config ────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
ENABLE_WINDOWS_TOAST = os.getenv("ENABLE_WINDOWS_TOAST", "true").lower() in ("1", "true", "yes")

