"""
ADB interface for BlueStacks emulator.
Includes ADBClient and ChaosADBController with human-like input jitter.
"""
import os
import re
import time
import random
import logging
import subprocess
from typing import Optional, Tuple
import cv2
import numpy as np

from czn_bot.constants import SCREEN_WIDTH, SCREEN_HEIGHT, LOGS_DIR
from czn_bot.settings import ADB_HOST, ADB_PORT, ADB_PATH

logger = logging.getLogger("ChaosBot.ADB")

# Hide console window on Windows when invoking subprocess
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


class ADBClient:
    """Thin wrapper around ADB subprocess commands."""

    def __init__(self, host: str = ADB_HOST, port: int = ADB_PORT, adb_path: Optional[str] = None):
        self.device = f"{host}:{port}"
        self.adb_path = adb_path or ADB_PATH or self._find_adb()

    @staticmethod
    def _find_adb() -> str:
        """Try to locate adb.exe in PATH or common install directories."""
        for d in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(d, "adb.exe")
            if os.path.isfile(candidate):
                return candidate

        candidates = [
            r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
            r"C:\Program Files (x86)\BlueStacks_nxt\HD-Adb.exe",
            r"C:\Program Files\BlueStacks\HD-Adb.exe",
            r"C:\Program Files (x86)\BlueStacks\HD-Adb.exe",
            os.path.expanduser(r"~\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c

        return "adb"

    def _run(self, *args, **kwargs):
        timeout = kwargs.pop("timeout", 15)
        cmd = [self.adb_path, "-s", self.device] + list(args)
        creationflags = kwargs.pop("creationflags", CREATE_NO_WINDOW)
        return subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            creationflags=creationflags,
            **kwargs
        )

    def connect(self) -> bool:
        """Connect to the emulator. Returns True on success."""
        cmd = [self.adb_path, "connect", self.device]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW
            )
            return "connected" in result.stdout.lower() or "already" in result.stdout.lower()
        except Exception:
            return False

    def is_connected(self) -> bool:
        try:
            result = self._run("get-state")
            return result.returncode == 0 and b"device" in result.stdout
        except Exception:
            return False

    def screencap(self) -> np.ndarray:
        """Capture the screen. Returns a BGR numpy array (OpenCV format)."""
        result = self._run("exec-out", "screencap", "-p")
        if result.returncode != 0 or len(result.stdout) < 100:
            raise RuntimeError(
                f"screencap failed (rc={result.returncode}): {result.stderr[:200]}"
            )
        arr = np.frombuffer(result.stdout, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Failed to decode screencap via cv2.imdecode")
        return img

    def tap(self, x: int, y: int) -> bool:
        """Send a tap event at (x, y). Returns True on success."""
        try:
            res = self._run("shell", "input", "tap", str(int(x)), str(int(y)), timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 400) -> bool:
        """Send a swipe gesture from (x1, y1) to (x2, y2). Returns True on success."""
        try:
            res = self._run(
                "shell", "input", "swipe",
                str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(duration_ms)),
                timeout=8
            )
            return res.returncode == 0
        except Exception:
            return False

    def send_keyevent(self, keycode: int) -> bool:
        """Send an Android keyevent (e.g. 4 for KEYCODE_BACK). Returns True on success."""
        try:
            res = self._run("shell", "input", "keyevent", str(int(keycode)), timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def get_screen_size(self) -> Optional[Tuple[int, int]]:
        """Query emulator display resolution via 'adb shell wm size'."""
        try:
            res = self._run("shell", "wm", "size", timeout=5)
            if res.returncode == 0 and res.stdout:
                text = res.stdout.decode("utf-8", errors="ignore").strip()
                matches = re.findall(r"(\d+)x(\d+)", text)
                if matches:
                    w, h = map(int, matches[-1])
                    return w, h
        except Exception:
            pass
        return None

    def check_resolution(self, expected_w: int = SCREEN_WIDTH, expected_h: int = SCREEN_HEIGHT):
        """Verifies emulator resolution matches expected width and height."""
        actual = self.get_screen_size()
        if actual is None:
            return True, None, "Không đọc được độ phân giải qua wm size."
        w, h = actual
        if (w, h) == (expected_w, expected_h):
            return True, actual, f"Độ phân giải chuẩn: {w}x{h}"
        return False, actual, f"Độ phân giải hiện tại là {w}x{h} (Chuẩn yêu cầu: {expected_w}x{expected_h})"


class ChaosADBController:
    """Core controller wrapper around ADB with anti-cheat human-like actions."""

    def __init__(self, host: str = ADB_HOST, port: int = ADB_PORT, client: Optional[ADBClient] = None):
        self.host = host
        self.port = port
        self.client = client or ADBClient(host=host, port=port)
        self.temp_dir = os.path.join(LOGS_DIR, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

    def connect_adb(self) -> Tuple[bool, str]:
        """Check connection and resolution."""
        connected = self.client.connect() or self.client.is_connected()
        if not connected:
            msg = f"Không thể kết nối đến ADB tại {self.host}:{self.port}. Vui lòng bật ADB trong BlueStacks."
            logger.error(msg)
            return False, msg

        ok_res, actual_res, res_msg = self.client.check_resolution(SCREEN_WIDTH, SCREEN_HEIGHT)
        if not ok_res and actual_res is not None:
            msg = f"Đã kết nối ADB nhưng độ phân giải hiện tại là {actual_res[0]}x{actual_res[1]} (Yêu cầu: 1600x900)."
            logger.warning(msg)
            return True, msg

        msg = f"Kết nối ADB thành công ({self.host}:{self.port}) - Độ phân giải chuẩn 1600x900."
        logger.info(msg)
        return True, msg

    def capture_screen(self, save_to_disk: bool = False, filename: Optional[str] = None) -> Optional[np.ndarray]:
        """Capture screen as BGR numpy array."""
        try:
            img = self.client.screencap()
            if img is None:
                return None

            if img.shape[:2] != (SCREEN_HEIGHT, SCREEN_WIDTH):
                img = cv2.resize(img, (SCREEN_WIDTH, SCREEN_HEIGHT), interpolation=cv2.INTER_LINEAR)

            if save_to_disk:
                fname = filename or f"cap_{int(time.time() * 1000)}.png"
                out_path = os.path.join(self.temp_dir, fname)
                cv2.imwrite(out_path, img)

            return img
        except Exception as e:
            logger.error(f"Lỗi chụp màn hình ADB: {e}")
            return None

    def tap_location(
        self,
        x: int,
        y: int,
        random_offset: bool = True,
        offset_range: int = 5,
        action_name: str = ""
    ) -> bool:
        """Send tap with slight random offset for human-like interaction."""
        target_x = x
        target_y = y
        if random_offset:
            target_x += random.randint(-offset_range, offset_range)
            target_y += random.randint(-offset_range, offset_range)

        target_x = max(0, min(SCREEN_WIDTH - 1, target_x))
        target_y = max(0, min(SCREEN_HEIGHT - 1, target_y))

        log_prefix = f"[{action_name}] " if action_name else ""
        logger.info(f"{log_prefix}Chạm vào ({target_x}, {target_y}) [gốc: ({x}, {y})]")
        return self.client.tap(target_x, target_y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 400) -> bool:
        """Send swipe gesture."""
        return self.client.swipe(x1, y1, x2, y2, duration_ms)

    def human_sleep(self, min_s: float = 0.5, max_s: float = 1.2) -> None:
        """Pause execution randomly."""
        delay = random.uniform(min_s, max_s)
        time.sleep(delay)

    def send_back(self) -> bool:
        """Send Android back button (KEYCODE_BACK = 4)."""
        logger.info("Gửi phím BACK (Thoát popup/modal)")
        return self.client.send_keyevent(4)


_default_controller: Optional[ChaosADBController] = None

def get_adb_controller(host: str = "127.0.0.1", port: int = 5555) -> ChaosADBController:
    """Singleton getter for ChaosADBController."""
    global _default_controller
    if _default_controller is None or _default_controller.host != host or _default_controller.port != port:
        _default_controller = ChaosADBController(host=host, port=port)
    return _default_controller

def connect_adb(host: str = "127.0.0.1", port: int = 5555) -> Tuple[bool, str]:
    return get_adb_controller(host, port).connect_adb()

def capture_screen(save_to_disk: bool = False) -> Optional[np.ndarray]:
    return get_adb_controller().capture_screen(save_to_disk=save_to_disk)

