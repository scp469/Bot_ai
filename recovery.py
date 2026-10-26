"""
Automated state recovery strategies for Chaos Zero Nightmare Bot.
When the bot is stuck or encounters UNKNOWN screens, this module executes
staged recovery actions (multi-point popup closing, dismiss clicks, and Android Back key)
before resorting to a full halt.
"""
import time
import logging
from typing import Optional, List, Tuple

from config import State, TAP_COORDS
from adb_client import ADBClient
from detector import ScreenDetector

logger = logging.getLogger("ChaosBot.Recovery")


class RecoveryManager:
    # Potential dismiss / close coordinates to attempt sequentially
    CANDIDATE_DISMISS_COORDS: List[Tuple[int, int]] = [
        TAP_COORDS.get("close_x_default", (1528, 44)),
        TAP_COORDS.get("close_monster_info", (1385, 115)),
        (1550, 50),     # Alternate top-right corner
        (800, 450),      # Screen center click-away dismiss
    ]

    def __init__(
        self,
        adb_client: Optional[ADBClient] = None,
        detector: Optional[ScreenDetector] = None,
    ) -> None:
        self.adb = adb_client or ADBClient()
        self.detector = detector or ScreenDetector()
        self.recovery_attempts_done: int = 0
        self.recovery_successes: int = 0

    def attempt_recovery(self, attempt_number: int) -> Tuple[bool, Optional[State]]:
        """
        Execute a staged recovery action based on the attempt number.
        Returns:
            (is_recovered: bool, new_state: Optional[State])
        """
        self.recovery_attempts_done += 1

        if attempt_number == 1:
            # Stage 1: Try primary top-right popup close
            x, y = self.CANDIDATE_DISMISS_COORDS[0]
            logger.info(f"[RECOVERY Stage 1] Thử đóng popup tại ({x}, {y})")
            self.adb.tap(x, y)
            time.sleep(1.0)

        elif attempt_number == 2:
            # Stage 2: Try alternate popup / center dismiss tap
            x, y = self.CANDIDATE_DISMISS_COORDS[1]
            logger.info(f"[RECOVERY Stage 2] Thử bấm góc phụ/hủy tại ({x}, {y})")
            self.adb.tap(x, y)
            time.sleep(1.0)

        else:
            # Stage 3: Send Android Back key (KEYEVENT_BACK = 4)
            logger.info("[RECOVERY Stage 3] Thử gửi tín hiệu phím Android BACK (Keyevent 4)")
            self.adb.send_keyevent(4)
            time.sleep(1.5)

        # Re-check screen after recovery action
        try:
            screen = self.adb.screencap()
            new_state, _ = self.detector.detect(screen)
            if new_state != State.UNKNOWN:
                self.recovery_successes += 1
                logger.info(f"[RECOVERY THÀNH CÔNG] Bot đã phục hồi về trạng thái: {new_state.value}")
                return True, new_state
        except Exception as e:
            logger.warning(f"[RECOVERY] Lỗi khi kiểm tra lại màn hình: {e}")

        return False, State.UNKNOWN
