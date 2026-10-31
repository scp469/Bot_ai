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
    "CHAOS_CHOOSE_EPIPHANY": 60.0,   # Max 60 seconds for card / fate choice
    "CHAOS_EVENT": 60.0,             # Max 60 seconds for random event choice
    "STORY_DIALOGUE": 90.0,         # Max 90 seconds for dialogue progression
}

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
}

