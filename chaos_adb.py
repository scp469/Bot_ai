"""
Core ADB Controller for Chaos Zero Nightmare.
Provides standard functions requested in the blueprint:
- connect_adb(host, port): Verifies connection to BlueStacks and checks 1600x900 resolution
- capture_screen(save_to_disk=False): Captures screen into RAM (numpy ndarray) or temp file
- tap_location(x, y, random_offset=True): Sends tap with human-like jitter
- human_sleep(min_s, max_s): Humanized pauses between interactions
- send_back(): Presses Android back button for popup dismissal
"""
import os
import time
import random
import logging
from typing import Optional, Tuple
import cv2
import numpy as np

from adb_client import ADBClient

logger = logging.getLogger("ChaosBot.ADB")

STANDARD_WIDTH = 1600
STANDARD_HEIGHT = 900
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5555


class ChaosADBController:
    """Core controller wrapper around ADB with anti-cheat human-like actions."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.client = ADBClient(host=host, port=port)
        self.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

    def connect_adb(self) -> Tuple[bool, str]:
        """
        Kiểm tra kết nối đến thiết bị giả lập (127.0.0.1:5555) và kiểm tra độ phân giải 1600x900.
        Trả về (success, status_message).
        """
        connected = self.client.connect() or self.client.is_connected()
        if not connected:
            msg = f"Không thể kết nối đến ADB tại {self.host}:{self.port}. Vui lòng bật ADB trong BlueStacks."
            logger.error(msg)
            return False, msg

        ok_res, actual_res, res_msg = self.client.check_resolution(STANDARD_WIDTH, STANDARD_HEIGHT)
        if not ok_res and actual_res is not None:
            msg = f"Đã kết nối ADB nhưng độ phân giải hiện tại là {actual_res[0]}x{actual_res[1]} (Yêu cầu: 1600x900)."
            logger.warning(msg)
            return True, msg

        msg = f"Kết nối ADB thành công ({self.host}:{self.port}) - Độ phân giải chuẩn 1600x900."
        logger.info(msg)
        return True, msg

    def capture_screen(self, save_to_disk: bool = False, filename: Optional[str] = None) -> Optional[np.ndarray]:
        """
        Chụp màn hình giả lập, kéo ảnh về RAM dưới dạng BGR numpy array (OpenCV).
        Nếu save_to_disk=True, lưu tạm ảnh vào ổ cứng.
        """
        try:
            img = self.client.screencap()
            if img is None:
                return None

            # Đảm bảo ảnh luôn ở kích thước chuẩn 1600x900
            if img.shape[:2] != (STANDARD_HEIGHT, STANDARD_WIDTH):
                img = cv2.resize(img, (STANDARD_WIDTH, STANDARD_HEIGHT), interpolation=cv2.INTER_LINEAR)

            if save_to_disk:
                target_name = filename or f"screen_{int(time.time() * 1000)}.png"
                target_path = os.path.join(self.temp_dir, target_name)
                cv2.imwrite(target_path, img)

            return img
        except Exception as e:
            logger.error(f"Lỗi chụp màn hình giả lập: {e}")
            return None

    def tap_location(self, x: int, y: int, random_offset: bool = True,
                     offset_range: int = 3) -> bool:
        """
        Gửi lệnh chạm tọa độ (x, y) vào giả lập.
        Áp dụng random offset (± offset_range px) để mô phỏng thao tác người thật, né anti-cheat.
        """
        target_x = int(x)
        target_y = int(y)

        if random_offset and offset_range > 0:
            target_x += random.randint(-offset_range, offset_range)
            target_y += random.randint(-offset_range, offset_range)

        # Giới hạn trong khung 1600x900
        target_x = max(0, min(STANDARD_WIDTH - 1, target_x))
        target_y = max(0, min(STANDARD_HEIGHT - 1, target_y))

        logger.debug(f"Chạm tọa độ: ({target_x}, {target_y}) (gốc: {x}, {y})")
        return self.client.tap(target_x, target_y)

    def human_sleep(self, min_s: float = 0.8, max_s: float = 1.8) -> None:
        """
        Tạm dừng ngẫu nhiên giữa các thao tác (mặc định 0.8s - 1.8s) để đánh lừa anti-cheat.
        """
        duration = random.uniform(min_s, max_s)
        time.sleep(duration)

    def send_back(self) -> bool:
        """Gửi phím BACK (Keycode 4) trên Android để đóng popup hoặc lùi màn hình."""
        return self.client.send_keyevent(4)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 400) -> bool:
        """Vuốt màn hình."""
        return self.client.swipe(x1, y1, x2, y2, duration_ms)


# Global singleton instance for quick usage
_default_controller = None

def get_adb_controller(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ChaosADBController:
    global _default_controller
    if _default_controller is None or _default_controller.host != host or _default_controller.port != port:
        _default_controller = ChaosADBController(host=host, port=port)
    return _default_controller

def connect_adb(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Tuple[bool, str]:
    return get_adb_controller(host, port).connect_adb()

def capture_screen(save_to_disk: bool = False) -> Optional[np.ndarray]:
    return get_adb_controller().capture_screen(save_to_disk=save_to_disk)

def tap_location(x: int, y: int, random_offset: bool = True) -> bool:
    return get_adb_controller().tap_location(x, y, random_offset=random_offset)
