"""
Template loading, caching, scaling, and OpenCV template matching.
"""
import os
import logging
from typing import Dict, Optional, Tuple, Any
import cv2
import numpy as np

from czn_bot.constants import (
    TEMPLATES_DIR,
    DATA_TEMPLATES_DIR,
    LEGACY_TEMPLATES_DIR,
    TEMPLATES,
    MATCH_THRESHOLD,
    TEMPLATE_THRESHOLDS,
)

logger = logging.getLogger("ChaosBot.Templates")


class ScreenScaler:
    """Scales coordinates and ROIs from standard 1600x900 resolution to any resolution."""

    def __init__(
        self,
        actual_width: int,
        actual_height: int,
        base_width: int = 1600,
        base_height: int = 900,
    ):
        self.base_width = base_width
        self.base_height = base_height
        self.actual_width = actual_width
        self.actual_height = actual_height
        self.scale_x = actual_width / float(base_width)
        self.scale_y = actual_height / float(base_height)

    def to_actual_point(self, base_x: int, base_y: int) -> Tuple[int, int]:
        return int(round(base_x * self.scale_x)), int(round(base_y * self.scale_y))

    def to_actual_roi(self, rx: int, ry: int, rw: int, rh: int) -> Tuple[int, int, int, int]:
        return (
            int(round(rx * self.scale_x)),
            int(round(ry * self.scale_y)),
            int(round(rw * self.scale_x)),
            int(round(rh * self.scale_y)),
        )


class TemplateManager:
    """Loads and caches OpenCV template images."""

    def __init__(self, template_dir: Optional[str] = None):
        self.template_dir = template_dir or TEMPLATES_DIR
        self.templates: Dict[str, np.ndarray] = {}
        self.load_all()

    def load_all(self) -> None:
        """Load all templates registered in constants.TEMPLATES."""
        search_dirs = [self.template_dir, DATA_TEMPLATES_DIR, LEGACY_TEMPLATES_DIR]
        for key, fname in TEMPLATES.items():
            for d in search_dirs:
                if not d or not os.path.exists(d):
                    continue
                path = os.path.join(d, fname)
                if os.path.isfile(path):
                    img = cv2.imread(path)
                    if img is not None:
                        self.templates[key] = img
                        break

    def get(self, key: str) -> Optional[np.ndarray]:
        return self.templates.get(key)

    def match(
        self,
        screen: np.ndarray,
        templ_key: str,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> Tuple[float, Optional[Tuple[int, int]]]:
        """
        Match a template against screen or sub-region.
        Returns (score, (center_x, center_y)) or (0.0, None).
        """
        templ = self.get(templ_key)
        if templ is None or screen is None or screen.size == 0:
            return 0.0, None

        if region is not None:
            rx, ry, rw, rh = region
            h, w = screen.shape[:2]
            rx = max(0, min(rx, w - 1))
            ry = max(0, min(ry, h - 1))
            rw = max(1, min(rw, w - rx))
            rh = max(1, min(rh, h - ry))
            crop = screen[ry : ry + rh, rx : rx + rw]
            th, tw = templ.shape[:2]
            if crop.shape[0] < th or crop.shape[1] < tw:
                return 0.0, None
            res = cv2.matchTemplate(crop, templ, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            cx = rx + max_loc[0] + tw // 2
            cy = ry + max_loc[1] + th // 2
            return float(max_val), (cx, cy)
        else:
            th, tw = templ.shape[:2]
            if screen.shape[0] < th or screen.shape[1] < tw:
                return 0.0, None
            res = cv2.matchTemplate(screen, templ, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            return float(max_val), (cx, cy)

