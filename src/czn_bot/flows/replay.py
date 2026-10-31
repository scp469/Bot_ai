"""
Replay Flow (Đi lại màn).
Retries the same completed stage repeatedly until max_retries or stamina exhaustion.
"""
from typing import Optional, Dict, Any
import numpy as np

from czn_bot.states import State, LeftButton
from czn_bot.coords import TAP_COORDS
from czn_bot.flows.base import Flow, Action


class ReplayFlow(Flow):
    def __init__(self, max_retries: Optional[int] = None, auto_start_match: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.max_retries = max_retries
        self.auto_start_match = auto_start_match
        self.retries_done = 0

    def handle(self, state: State, details: Dict[str, Any], screen: Optional[np.ndarray]) -> Action:
        if state == State.IN_MATCH:
            return Action.none(name="In Match (waiting for combat)")

        if state == State.MATCH_DONE:
            left_btn = details.get("left_button", LeftButton.NONE)

            if left_btn == LeftButton.RETRY_DISABLED:
                return Action.stop(reason="Hết thể lực (Stamina Exhausted)")

            if left_btn == LeftButton.RETRY:
                if self.max_retries is not None and self.retries_done >= self.max_retries:
                    return Action.stop(reason=f"Đã đạt giới hạn số trận lặp lại ({self.max_retries})")

                self.retries_done += 1
                return Action.tap(
                    *TAP_COORDS["left_button"],
                    name="Retry Button",
                    retry_number=self.retries_done,
                    score=details.get("retry_score", 0.90),
                    expected_words=["retry", "thử lại"]
                )

            # Left button is not retry (e.g. Next Mission or NONE) -> Tap Right Button (Confirm)
            confirm_coord = details.get("confirm_coord") or TAP_COORDS["right_button"]
            return Action.tap(
                *confirm_coord,
                name="Confirm Match Done",
                halt_after=True,
                reason="Hoàn thành màn chơi (Next Mission)",
                score=details.get("confirm_score", 0.90),
                expected_words=["confirm", "xác nhận", "ok"]
            )

        if state in (State.POPUP_EFFECT, State.POPUP_DRAW_PILE, State.POPUP_STAGE_INFO, State.POPUP_PAUSE):
            close_coord = details.get("close_coord") or TAP_COORDS["close_x_default"]
            return Action.tap(*close_coord, name=f"Close {state.value}")

        if state == State.POPUP_MONSTER_INFO:
            coord = details.get("close_coord") or TAP_COORDS["close_monster_info"]
            return Action.tap(*coord, name="Dismiss Monster Info")

        if state in (State.PRE_MATCH_MISSION, State.PRE_MATCH_TEAM):
            if self.auto_start_match:
                coord = details.get("coord")
                if not coord:
                    coord = TAP_COORDS["enter_team"] if state == State.PRE_MATCH_TEAM else TAP_COORDS["enter_mission"]
                return Action.tap(*coord, name=f"Auto Start {state.value}")
            return Action.none(name="Pre-match (waiting for manual start)")

        if state == State.TRANSITIONING:
            return Action.none(name="Transitioning Animation")

        return Action.none(name="Replay Flow: Idle")
