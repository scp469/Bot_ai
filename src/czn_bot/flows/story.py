"""
Story Flow (Cốt truyện).
Navigates the story campaign map, enters stages, and auto-skips dialogues.
"""
from typing import Optional, Dict, Any
import numpy as np

from czn_bot.states import State, LeftButton
from czn_bot.coords import TAP_COORDS
from czn_bot.flows.base import Flow, Action


class StoryFlow(Flow):
    def __init__(self, max_stages: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        self.swipe_count = 0
        self.max_stages = max_stages
        self.stages_done = 0

    def handle(self, state: State, details: Dict[str, Any], screen: Optional[np.ndarray]) -> Action:
        if state == State.IN_MATCH:
            return Action.none(name="In Match (waiting for combat)")

        if state == State.STORY_MAP:
            active_node = details.get("active_node")
            if active_node:
                self.swipe_count = 0
                tap_x = max(100, min(active_node[0], 1520))
                tap_y = active_node[1]
                return Action.tap(tap_x, tap_y, name="Enter Story Stage Node")

            if self.swipe_count < 3:
                self.swipe_count += 1
                return Action.swipe(
                    1200, 500, 400, 500,
                    duration=0.5,
                    name=f"Swipe Map Left ({self.swipe_count}/3)"
                )

            self.swipe_count = 0
            next_chap_coord = TAP_COORDS.get("story_chapter_next", (1194, 40))
            return Action.tap(*next_chap_coord, name="Next Chapter [>]")

        if state == State.STORY_DIALOGUE:
            skip_coord = details.get("skip_coord") or TAP_COORDS.get("story_dialogue_skip", (1272, 48))
            auto_coord = details.get("auto_coord") or TAP_COORDS.get("story_dialogue_auto", (1395, 48))
            return Action.tap(
                *auto_coord,
                name="Dialogue Auto",
                extra_actions=[
                    ("tap", skip_coord),
                    ("tap", skip_coord),
                    ("tap", skip_coord),
                    ("tap", (800, 800)),
                    ("tap", TAP_COORDS.get("story_skip_confirm", (950, 550))),
                ],
                extra={"dialogue_skip": True}
            )

        if state == State.MATCH_DONE:
            left_btn = details.get("left_button")
            reward_score = details.get("reward_score", 0.0)
            confirm_score = details.get("confirm_score", 0.0)
            has_rewards = reward_score >= 0.70
            has_confirm = confirm_score >= 0.70

            # Defeat check: Retry button present and no rewards / confirm
            if left_btn == LeftButton.RETRY and not has_rewards and not has_confirm:
                return Action.stop(
                    reason="Dừng bot do thất bại trong ải cốt truyện (Thua trận)",
                    extra={"defeat": True}
                )

            if self.max_stages is not None and self.stages_done >= self.max_stages:
                return Action.stop(
                    reason=f"Đã đạt giới hạn số màn chơi ({self.max_stages})",
                    extra={"max_stages": True}
                )

            self.stages_done += 1
            confirm_coord = details.get("confirm_coord") or TAP_COORDS["right_button"]
            return Action.tap(
                *confirm_coord,
                name="Confirm Story Match Done",
                extra={"stage_number": self.stages_done}
            )

        if state in (State.PRE_MATCH_MISSION, State.PRE_MATCH_TEAM):
            coord = details.get("coord")
            if not coord:
                coord = TAP_COORDS["enter_team"] if state == State.PRE_MATCH_TEAM else TAP_COORDS["enter_mission"]
            return Action.tap(*coord, name=f"Enter Story {state.value}")

        if state in (State.POPUP_EFFECT, State.POPUP_DRAW_PILE, State.POPUP_STAGE_INFO, State.POPUP_PAUSE):
            close_coord = details.get("close_coord") or TAP_COORDS["close_x_default"]
            return Action.tap(*close_coord, name=f"Close {state.value}")

        if state == State.POPUP_MONSTER_INFO:
            coord = details.get("close_coord") or TAP_COORDS["close_monster_info"]
            return Action.tap(*coord, name="Dismiss Monster Info")

        if state == State.TRANSITIONING:
            return Action.none(name="Transitioning Animation")

        return Action.none(name="Story Flow: Idle")
