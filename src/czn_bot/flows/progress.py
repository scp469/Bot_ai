"""
Progress Flow (Cày màn).
Advances through campaign stages sequentially by pressing Next Mission.
"""
from typing import Optional, Dict, Any
import numpy as np

from czn_bot.states import State, LeftButton
from czn_bot.coords import TAP_COORDS
from czn_bot.flows.base import Flow, Action


class ProgressFlow(Flow):
    def __init__(self, max_stages: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        self.max_stages = max_stages
        self.stages_done = 0

    def handle(self, state: State, details: Dict[str, Any], screen: Optional[np.ndarray]) -> Action:
        if state == State.IN_MATCH:
            return Action.none(name="In Match (waiting for combat)")

        if state == State.MATCH_DONE:
            left_btn = details.get("left_button", LeftButton.NONE)

            if left_btn == LeftButton.NEXT_MISSION:
                if self.max_stages is not None and self.stages_done >= self.max_stages:
                    return Action.stop(reason=f"Đã đạt giới hạn số màn tiến trình ({self.max_stages})", max_stages=True)

                self.stages_done += 1
                return Action.tap(
                    *TAP_COORDS["left_button"],
                    name="Next Mission Button",
                    stage_number=self.stages_done,
                    score=details.get("next_score", 0.90),
                    expected_words=["next", "mission", "tiếp"]
                )

            # Fallback: Tap Right Button (Confirm)
            confirm_coord = details.get("confirm_coord") or TAP_COORDS["right_button"]
            return Action.tap(
                *confirm_coord,
                name="Confirm Match Done",
                halt_after=True,
                reason="Dừng do màn kết thúc với Retry",
                score=details.get("confirm_score", 0.90),
                expected_words=["confirm", "xác nhận", "ok"]
            )

        if state in (State.PRE_MATCH_MISSION, State.PRE_MATCH_TEAM):
            coord = details.get("coord")
            if not coord:
                coord = TAP_COORDS["enter_team"] if state == State.PRE_MATCH_TEAM else TAP_COORDS["enter_mission"]
            return Action.tap(*coord, name=f"Enter {state.value}")

        if state in (State.POPUP_EFFECT, State.POPUP_DRAW_PILE, State.POPUP_STAGE_INFO, State.POPUP_PAUSE):
            close_coord = details.get("close_coord") or TAP_COORDS["close_x_default"]
            return Action.tap(*close_coord, name=f"Close {state.value}")

        if state == State.POPUP_MONSTER_INFO:
            coord = details.get("close_coord") or TAP_COORDS["close_monster_info"]
            return Action.tap(*coord, name="Dismiss Monster Info")

        if state == State.TRANSITIONING:
            return Action.none(name="Transitioning Animation")

        return Action.none(name="Progress Flow: Idle")
