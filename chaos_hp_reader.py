import logging
from typing import Tuple
import cv2
import numpy as np

logger = logging.getLogger("ChaosBot")

# Coordinate constants on 1600x900 resolution
HP_BAR_Y_START = 32
HP_BAR_Y_END = 38
HP_BAR_X_START = 34
HP_BAR_X_END = 642
HP_BAR_TOTAL_WIDTH = HP_BAR_X_END - HP_BAR_X_START  # 608 px
LOW_HP_THRESHOLD = 0.60  # 60%


def get_team_hp(screen: np.ndarray) -> Tuple[float, bool]:
    """
    Đo Máu Tổng từ thanh máu ở góc trên bên trái:
    - Trả về: (hp_percent, is_low_hp)
      - hp_percent: Tỷ lệ máu từ 0.0 đến 1.0 (ví dụ: 1.0 = 100%, 0.45 = 45%)
      - is_low_hp: True nếu hp_percent < 0.60, ngược lại False (hp_percent >= 0.60)
    """
    if screen is None or screen.shape[:2] != (900, 1600):
        # Fallback an toàn: nếu ảnh bị lệch resolution thì resize tạm thời
        if screen is not None and screen.shape[0] > 0 and screen.shape[1] > 0:
            screen = cv2.resize(screen, (1600, 900), interpolation=cv2.INTER_LINEAR)
        else:
            # Chế độ Sinh tồn an toàn khi không có ảnh
            return 0.0, True

    try:
        # Cắt vùng thanh máu: 6px chiều cao x 608px chiều rộng
        bar_roi = screen[HP_BAR_Y_START:HP_BAR_Y_END, HP_BAR_X_START:HP_BAR_X_END]
        hsv = cv2.cvtColor(bar_roi, cv2.COLOR_BGR2HSV)

        # Điểm ảnh màu xanh lá cây của thanh máu (Hue 35-85, Sat >= 70)
        is_green = (hsv[:, :, 0] >= 35) & (hsv[:, :, 0] <= 85) & (hsv[:, :, 1] >= 70)

        # Một cột X được coi là chứa máu nếu có ít nhất 2 pixel màu xanh theo chiều dọc
        col_filled = np.sum(is_green, axis=0) >= 2
        filled_cols = np.where(col_filled)[0]

        if len(filled_cols) == 0:
            hp_percent = 0.0
        else:
            # Lấy vị trí cột xa nhất bên phải còn chứa máu xanh
            fill_width = int(filled_cols[-1]) + 1
            raw_hp = float(fill_width) / float(HP_BAR_TOTAL_WIDTH)
            hp_percent = round(max(0.0, min(1.0, raw_hp)), 2)

        is_low_hp = hp_percent < LOW_HP_THRESHOLD
        return hp_percent, is_low_hp

    except Exception as e:
        logger.error(f"Lỗi khi đọc thanh Máu Tổng: {e}")
        # Chế độ Sinh tồn an toàn khi gặp lỗi
        return 0.0, True
