"""
czn_bot.chaos2.loop - Vòng lặp cố định kiểm soát Chaos mode.
Tuân thủ đầy đủ 9 nguyên tắc:
  - Capture -> Ổn định K frame -> Classify -> Handler trả ĐÚNG 1 Action kèm expected_next
  - Guard độc lập chặn vùng cấm
  - Dry-run không gửi tap
  - Tự động dừng an toàn và lưu ảnh vào debug_captures/ khi có sự cố.
"""

from __future__ import annotations
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional
import cv2
import numpy as np

from .action import ChaosAction
from .classifier import ChaosClassifier, ClassificationResult
from .config import (
    DEBUG_CAPTURES_DIR,
    DEFAULT_DRY_RUN,
    K_FRAMES_DEFAULT,
    MAX_ACTION_RETRIES,
    MAX_UNKNOWN_FRAMES,
)
from .guard import TapGuard
from .registry import SCREEN_REGISTRY, ScreenDef

logger = logging.getLogger("ChaosBot.Chaos2.Loop")


class ChaosLoop:
    def __init__(
        self,
        classifier: Optional[ChaosClassifier] = None,
        guard: Optional[TapGuard] = None,
        registry: Optional[Dict[str, ScreenDef]] = None,
        dry_run: bool = DEFAULT_DRY_RUN,
    ):
        self.registry = registry or SCREEN_REGISTRY
        self.classifier = classifier or ChaosClassifier(self.registry)
        self.guard = guard or TapGuard(self.registry)
        self.dry_run = dry_run

        # Biến trạng thái vòng lặp (Single Source of Truth)
        self._current_state: str = "UNKNOWN"
        self._last_raw_state: str = "UNKNOWN"
        self._consecutive_state_count: int = 0
        self._unknown_streak: int = 0
        self._retry_count: int = 0
        self._pending_action: Optional[ChaosAction] = None
        self._action_history: List[Dict[str, Any]] = []

    def reset(self):
        """Reset trạng thái vòng lặp."""
        self._current_state = "UNKNOWN"
        self._last_raw_state = "UNKNOWN"
        self._consecutive_state_count = 0
        self._unknown_streak = 0
        self._retry_count = 0
        self._pending_action = None

    def save_debug_capture(self, screen: np.ndarray, prefix: str) -> Optional[str]:
        """Lưu ảnh màn hình vào debug_captures khi phát hiện bất thường."""
        if screen is None or screen.size == 0:
            return None
        try:
            os.makedirs(DEBUG_CAPTURES_DIR, exist_ok=True)
            timestamp = int(time.time() * 1000)
            filename = f"{prefix}_{timestamp}.png"
            path = os.path.join(DEBUG_CAPTURES_DIR, filename)
            cv2.imwrite(path, screen)
            logger.info(f"Đã lưu ảnh debug: {path}")
            return path
        except Exception as ex:
            logger.error(f"Lỗi khi lưu ảnh debug: {ex}")
            return None

    def step(self, screen: np.ndarray, context: Any = None) -> ChaosAction:
        """
        Thực hiện một bước trong vòng lặp điều khiển cố định.
        Nhận: screen (ảnh khung hình hiện tại).
        Trả về: ChaosAction (tap, wait, hoặc stop).
        """
        if screen is None or screen.size == 0:
            return ChaosAction.wait(0.2, reason="Khung hình rỗng, chờ capture tiếp theo")

        # 1. Classify màn hình
        res = self.classifier.classify(screen)
        raw_state = res.state

        # 2. Xử lý UNKNOWN / AMBIGUOUS ngay (không tích lũy ổn định hợp lệ)
        if raw_state in ("UNKNOWN", "AMBIGUOUS"):
            self._consecutive_state_count = 0
            self._last_raw_state = raw_state
            self._current_state = raw_state
            self._unknown_streak += 1
            if self._unknown_streak >= MAX_UNKNOWN_FRAMES:
                self.save_debug_capture(screen, f"unknown_stuck_{raw_state}")
                return ChaosAction.stop(
                    f"Kẹt trạng thái {raw_state} quá {MAX_UNKNOWN_FRAMES} frames liên tiếp -> Dừng an toàn"
                )
            return ChaosAction.wait(0.3, reason=f"Màn hình {raw_state}, chờ nhận diện lại")

        self._unknown_streak = 0

        # 3. Kiểm tra ổn định K frames cho state hợp lệ (Single Source of Truth)
        if raw_state == self._last_raw_state:
            self._consecutive_state_count += 1
        else:
            self._last_raw_state = raw_state
            self._consecutive_state_count = 1

        sdef = self.registry.get(raw_state)
        required_k = sdef.k_frames if sdef else K_FRAMES_DEFAULT

        if self._consecutive_state_count < required_k:
            return ChaosAction.wait(
                0.2,
                reason=f"Chờ ổn định màn hình {raw_state} ({self._consecutive_state_count}/{required_k} frames)",
            )

        self._current_state = raw_state

        # 4. Xác minh (Verification) hành động trước đó nếu có
        if self._pending_action is not None:
            expected = self._pending_action.expected_next
            verified = False
            if expected == "SCREEN_CHANGED":
                verified = (self._current_state != self._pending_action.details.get("prev_state"))
            elif expected is not None:
                verified = (self._current_state == expected)
            else:
                verified = True

            if verified:
                logger.info(f"[VERIFIED] Đạt state mong đợi: {self._current_state}")
                self._pending_action = None
                self._retry_count = 0
            else:
                self._retry_count += 1
                if self._retry_count >= MAX_ACTION_RETRIES:
                    self.save_debug_capture(screen, "action_verify_failed")
                    msg = (
                        f"Hết số lần thử ({MAX_ACTION_RETRIES}) cho action mong đợi '{expected}' "
                        f"(hiện tại là '{self._current_state}') -> Dừng an toàn"
                    )
                    logger.warning(msg)
                    return ChaosAction.stop(msg)
                logger.warning(
                    f"[RETRY {self._retry_count}/{MAX_ACTION_RETRIES}] "
                    f"Chưa đạt state mong đợi '{expected}', đang ở '{self._current_state}'"
                )

        # 5. Tra cứu Handler trong Registry
        if sdef is None or sdef.handler is None:
            # Giai đoạn 0: Registry rỗng handler -> Safe wait
            return ChaosAction.wait(
                0.5,
                reason=f"State {self._current_state} đã nhận diện ổn định, nhưng chưa có handler được đăng ký (Giai đoạn 0)",
            )

        # 6. Gọi Handler (Handler trả về đúng 1 Action kèm expected_next)
        action = sdef.handler(screen, context)
        if action.type == "stop":
            return action

        # 7. Guard độc lập kiểm tra Action
        guard_res = self.guard.validate_action(action, self._current_state)
        if not guard_res.allowed:
            self.save_debug_capture(screen, "tap_blocked_by_guard")
            logger.warning(f"[TAP BLOCKED] {guard_res.reason}")
            return ChaosAction.stop(f"Guard CHẶN hành động: {guard_res.reason}")

        # 8. Chế độ Dry-Run
        if self.dry_run:
            logger.info(
                f"[DRY-RUN] Sẽ thực hiện {action.type} tại {action.target} "
                f"vì '{action.reason}', mong đợi state '{action.expected_next}'"
            )
            self._action_history.append({
                "state": self._current_state,
                "action": action,
                "dry_run": True,
            })
            self._pending_action = action
            return action

        # 9. Thực thi thật
        self._pending_action = action
        self._action_history.append({
            "state": self._current_state,
            "action": action,
            "dry_run": False,
        })
        return action
