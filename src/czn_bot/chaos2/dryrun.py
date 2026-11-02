"""
czn_bot.chaos2.dryrun - Tiện ích và Runner hỗ trợ chạy thử nghiệm (Dry-Run mode).
Không gửi bất kỳ lệnh tap nào tới thiết bị thật, ghi nhận toàn bộ log dự định hành động.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
import numpy as np

from .action import ChaosAction
from .loop import ChaosLoop

logger = logging.getLogger("ChaosBot.Chaos2.DryRun")


class DryRunSession:
    def __init__(self, loop: Optional[ChaosLoop] = None):
        self.loop = loop or ChaosLoop(dry_run=True)
        self.loop.dry_run = True
        self.history: List[Dict[str, Any]] = []

    def feed_frame(self, screen: np.ndarray, frame_name: str = "") -> ChaosAction:
        """Nạp một khung hình vào phiên dry-run."""
        action = self.loop.step(screen)
        record = {
            "frame_name": frame_name,
            "state": self.loop._current_state,
            "action_type": action.type,
            "target": action.target,
            "expected_next": action.expected_next,
            "reason": action.reason,
        }
        self.history.append(record)
        logger.info(
            f"[DryRun] Frame '{frame_name}' -> State={self.loop._current_state} -> "
            f"Action={action.type} target={action.target} expected_next={action.expected_next} reason='{action.reason}'"
        )
        return action

    def summary(self) -> str:
        """Tóm tắt lịch sử chạy dry-run."""
        lines = [f"=== TỔNG KẾT DRY-RUN ({len(self.history)} bước) ==="]
        for idx, item in enumerate(self.history):
            lines.append(
                f"[{idx+1:02d}] {item['frame_name']:25s} | State: {item['state']:20s} | "
                f"Action: {item['action_type']:5s} {str(item['target']):15s} | "
                f"Expected: {str(item['expected_next']):20s} | Reason: {item['reason']}"
            )
        return "\n".join(lines)

