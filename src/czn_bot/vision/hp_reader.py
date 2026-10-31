"""
Team HP reader from screen crop.
Reads team health bar in top-left region on 1600x900 resolution.
"""
import logging
from typing import Tuple
import cv2
import numpy as np

logger = logging.getLogger("ChaosBot.HPReader")

# Coordinate constants on 1600x900 resolution
HP_BAR_Y_START = 32
HP_BAR_Y_END = 38
HP_BAR_X_START = 34
HP_BAR_X_END = 642
HP_BAR_TOTAL_WIDTH = HP_BAR_X_END - HP_BAR_X_START  # 608 px
LOW_HP_THRESHOLD = 0.60  # 60%


def get_team_hp(screen: np.ndarray) -> Tuple[float, bool]:
    """
    Measure total team HP from the top-left HP bar:
    - Returns: (hp_percent, is_low_hp)
      - hp_percent: Float from 0.0 to 1.0 (e.g. 1.0 = 100%, 0.45 = 45%)
      - is_low_hp: True if hp_percent < 0.60, False otherwise.
    """
    if screen is None or screen.shape[:2] != (900, 1600):
        if screen is not None and screen.shape[0] > 0 and screen.shape[1] > 0:
            screen = cv2.resize(screen, (1600, 900), interpolation=cv2.INTER_LINEAR)
        else:
            return 0.0, True

    try:
        bar_roi = screen[HP_BAR_Y_START:HP_BAR_Y_END, HP_BAR_X_START:HP_BAR_X_END]
        hsv = cv2.cvtColor(bar_roi, cv2.COLOR_BGR2HSV)

        # Green pixels for HP bar (Hue 35-85, Sat >= 70)
        is_green = (hsv[:, :, 0] >= 35) & (hsv[:, :, 0] <= 85) & (hsv[:, :, 1] >= 70)

        # A column is considered filled if at least 2 pixels vertically are green
        col_filled = np.sum(is_green, axis=0) >= 2
        filled_cols = np.where(col_filled)[0]

        if len(filled_cols) == 0:
            hp_percent = 0.0
        else:
            fill_width = int(filled_cols[-1]) + 1
            raw_hp = float(fill_width) / float(HP_BAR_TOTAL_WIDTH)
            hp_percent = round(max(0.0, min(1.0, raw_hp)), 2)

        is_low = hp_percent < LOW_HP_THRESHOLD
        logger.info(f"Team HP: {int(hp_percent * 100)}% ({'LOW HP' if is_low else 'HIGH HP'})")
        return hp_percent, is_low

    except Exception as e:
        logger.error(f"Error measuring team HP: {e}")
        return 0.0, True

