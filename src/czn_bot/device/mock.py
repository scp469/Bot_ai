"""
Mock ADB Client for offline simulation and automated unit testing.
Allows testing flows and runner against static screenshots without BlueStacks.
"""
import os
import glob
import logging
from typing import List, Optional, Union
import cv2
import numpy as np

from czn_bot.constants import LOGS_DIR

logger = logging.getLogger("ChaosBot.MockADB")


class MockADBClient:
    """Offline mock of ADBClient for headless and unit testing."""

    def __init__(
        self,
        scenario_path: Union[str, List[str], np.ndarray, List[np.ndarray]],
        output_dir: Optional[str] = None,
        auto_advance_on_tap: bool = True,
    ):
        self.output_dir = output_dir or os.path.join(LOGS_DIR, "sim_output")
        os.makedirs(self.output_dir, exist_ok=True)
        self.auto_advance_on_tap = auto_advance_on_tap
        self.tap_history = []
        self.current_idx = 0
        self.step_count = 0

        self.frames: List[np.ndarray] = []

        if isinstance(scenario_path, np.ndarray):
            self.frames = [scenario_path]
        elif isinstance(scenario_path, list) and len(scenario_path) > 0 and isinstance(scenario_path[0], np.ndarray):
            self.frames = scenario_path
        else:
            self.image_files: List[str] = []
            if isinstance(scenario_path, list):
                self.image_files = scenario_path
            elif isinstance(scenario_path, str) and os.path.isdir(scenario_path):
                extensions = ["*.png", "*.jpg", "*.jpeg"]
                for ext in extensions:
                    self.image_files.extend(glob.glob(os.path.join(scenario_path, ext)))
                self.image_files.sort()
            elif isinstance(scenario_path, str) and os.path.isfile(scenario_path):
                self.image_files = [scenario_path]

            for path in self.image_files:
                img = cv2.imread(path)
                if img is not None:
                    self.frames.append(img)
                else:
                    logger.warning(f"MockADB: Could not load image at {path}")

        if not self.frames:
            logger.warning("MockADB: No images loaded. Using default black frame.")
            self.frames.append(np.zeros((900, 1600, 3), dtype=np.uint8))

    def connect(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return True

    def screencap(self) -> np.ndarray:
        """Returns the current scenario frame."""
        idx = min(self.current_idx, len(self.frames) - 1)
        return self.frames[idx].copy()

    def tap(self, x: int, y: int) -> bool:
        """Record tap at (x, y) and advance to next frame."""
        self.step_count += 1
        x, y = int(x), int(y)
        self.tap_history.append((self.step_count, self.current_idx, x, y))

        cur_frame = self.screencap()
        h, w = cur_frame.shape[:2]
        if 0 <= x < w and 0 <= y < h:
            cv2.circle(cur_frame, (x, y), 24, (0, 0, 255), 3)
            cv2.circle(cur_frame, (x, y), 4, (0, 0, 255), -1)
            cv2.putText(
                cur_frame,
                f"TAP #{self.step_count} ({x}, {y})",
                (max(10, x - 80), max(30, y - 35)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        out_name = f"step_{self.step_count:03d}_frame_{self.current_idx:02d}_tap_{x}_{y}.png"
        out_path = os.path.join(self.output_dir, out_name)
        try:
            cv2.imwrite(out_path, cur_frame)
        except Exception:
            pass

        logger.info(f"[SIMULATOR] Tap recorded at ({x}, {y}) -> Saved: {out_name}")

        if self.auto_advance_on_tap and self.current_idx < len(self.frames) - 1:
            self.current_idx += 1
            logger.info(f"[SIMULATOR] Advanced to frame {self.current_idx + 1}/{len(self.frames)}")

        return True

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 400) -> bool:
        """Simulate swipe gesture."""
        self.step_count += 1
        logger.info(f"[SIMULATOR] Swipe simulated: ({x1}, {y1}) -> ({x2}, {y2}) in {duration_ms}ms")
        if self.auto_advance_on_tap and self.current_idx < len(self.frames) - 1:
            self.current_idx += 1
        return True

    def send_keyevent(self, keycode: int) -> bool:
        """Simulate Android keyevent."""
        logger.info(f"[SIMULATOR] Keyevent simulated: {keycode}")
        if self.auto_advance_on_tap and self.current_idx < len(self.frames) - 1:
            self.current_idx += 1
        return True

    def reset(self) -> None:
        """Reset simulator to the first frame."""
        self.current_idx = 0
        self.step_count = 0
        self.tap_history.clear()

