"""
State and Mode enumerations for Chaos Zero Nightmare Bot.
"""
from enum import Enum


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
    CHAOS_EQUIPMENT = "CHAOS_EQUIPMENT"
    CHAOS_OBTAIN_REWARD = "CHAOS_OBTAIN_REWARD"
    CHAOS_CHOOSE_EPIPHANY = "CHAOS_CHOOSE_EPIPHANY"
    CHAOS_SAFE_ZONE = "CHAOS_SAFE_ZONE"
    CHAOS_EVENT = "CHAOS_EVENT"
    STORY_MAP = "STORY_MAP"
    STORY_DIALOGUE = "STORY_DIALOGUE"
    TRANSITIONING = "TRANSITIONING"
    UNKNOWN = "UNKNOWN"


class Mode(Enum):
    REPLAY = "Đi lại màn"      # Retry the same stage
    PROGRESS = "Cày màn"       # Progress to next stage
    CHAOS = "Chế độ Chaos"     # Chaos mode auto pathfinding & autonomous decision
    STORY = "Cốt truyện"       # Story mode campaign auto-progression


class LeftButton(Enum):
    RETRY = "Retry"
    RETRY_DISABLED = "Retry (Hết thể lực)"
    NEXT_MISSION = "Next Mission"
    NONE = "Không có nút trái"

