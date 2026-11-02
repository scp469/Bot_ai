"""
czn_bot.chaos2.action - Giao ước Action cho chế độ Chaos.
Mỗi hành động phải có đúng MỘT Action kèm expected_next.
Không cho phép chuỗi tap mù hoặc extra_actions.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple, Any, Dict


@dataclass(frozen=True)
class ChaosAction:
    type: str                                  # "tap" | "wait" | "stop" | "swipe"
    target: Optional[Tuple[int, int]] = None   # (x, y) nếu là tap
    expected_next: Optional[str] = None        # State mong đợi tiếp theo hoặc "SCREEN_CHANGED"
    reason: str = ""                           # Lý do thực hiện hành động
    timeout_sec: float = 5.0                   # Thời gian chờ xác nhận hành động
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def tap(
        cls,
        x: int,
        y: int,
        expected_next: Optional[str] = None,
        reason: str = "",
        timeout_sec: float = 5.0,
        **details: Any,
    ) -> ChaosAction:
        return cls(
            type="tap",
            target=(int(x), int(y)),
            expected_next=expected_next,
            reason=reason,
            timeout_sec=timeout_sec,
            details=details,
        )

    @classmethod
    def wait(
        cls,
        duration_sec: float = 1.0,
        expected_next: Optional[str] = None,
        reason: str = "",
    ) -> ChaosAction:
        return cls(
            type="wait",
            target=None,
            expected_next=expected_next,
            reason=reason,
            timeout_sec=duration_sec,
        )

    @classmethod
    def stop(cls, reason: str = "") -> ChaosAction:
        return cls(
            type="stop",
            target=None,
            expected_next=None,
            reason=reason,
            timeout_sec=0.0,
        )

