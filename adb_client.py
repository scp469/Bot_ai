"""
Thin ADB wrapper using subprocess.
Finds adb.exe automatically from PATH or common BlueStacks locations.
"""
import subprocess
import os
import cv2
import numpy as np

# Hide console window on Windows when invoking subprocess
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


class ADBClient:
    def __init__(self, host="127.0.0.1", port=5555, adb_path=None):
        self.device = f"{host}:{port}"
        self.adb_path = adb_path or self._find_adb()

    # ── ADB discovery ──────────────────────────────────────────

    @staticmethod
    def _find_adb():
        """Try to locate adb.exe in PATH or common install directories."""
        # Check PATH
        for d in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(d, "adb.exe")
            if os.path.isfile(candidate):
                return candidate

        # Common BlueStacks / Android SDK locations
        candidates = [
            r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
            r"C:\Program Files (x86)\BlueStacks_nxt\HD-Adb.exe",
            r"C:\Program Files\BlueStacks\HD-Adb.exe",
            r"C:\Program Files (x86)\BlueStacks\HD-Adb.exe",
            os.path.expanduser(
                r"~\AppData\Local\Android\Sdk\platform-tools\adb.exe"
            ),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c

        # Last resort – hope it's on PATH as 'adb'
        return "adb"

    # ── Helpers ─────────────────────────────────────────────────

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

    # ── Public API ──────────────────────────────────────────────

    def connect(self):
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

    def is_connected(self):
        try:
            result = self._run("get-state")
            return result.returncode == 0 and b"device" in result.stdout
        except Exception:
            return False

    def screencap(self):
        """Capture the screen. Returns a BGR numpy array (OpenCV format)."""
        result = self._run("exec-out", "screencap", "-p")
        if result.returncode != 0 or len(result.stdout) < 100:
            raise RuntimeError(
                f"screencap failed (rc={result.returncode}): "
                f"{result.stderr[:200]}"
            )
        arr = np.frombuffer(result.stdout, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Failed to decode screencap via cv2.imdecode")
        return img

    def tap(self, x, y):
        """Send a tap event at (x, y). Returns True on success, False otherwise."""
        try:
            res = self._run("shell", "input", "tap", str(int(x)), str(int(y)), timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def swipe(self, x1, y1, x2, y2, duration_ms=400):
        """Send a swipe gesture from (x1, y1) to (x2, y2) in duration_ms. Returns True on success."""
        try:
            res = self._run(
                "shell", "input", "swipe",
                str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(duration_ms)),
                timeout=8
            )
            return res.returncode == 0
        except Exception:
            return False

    def send_keyevent(self, keycode: int):
        """Send an Android keyevent (e.g. 4 for KEYCODE_BACK). Returns True on success."""
        try:
            res = self._run("shell", "input", "keyevent", str(int(keycode)), timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def get_screen_size(self):
        """
        Query emulator display resolution via 'adb shell wm size'.
        Returns (width, height) tuple or None on error.
        """
        import re
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

    def check_resolution(self, expected_w=1600, expected_h=900):
        """
        Verifies emulator resolution matches expected width and height.
        Returns (is_valid, actual_size_tuple, message).
        """
        actual = self.get_screen_size()
        if actual is None:
            return True, None, "Không đọc được độ phân giải qua wm size."
        w, h = actual
        if (w, h) == (expected_w, expected_h):
            return True, actual, f"Độ phân giải chuẩn: {w}x{h}"
        return False, actual, f"Độ phân giải hiện tại là {w}x{h} (Chuẩn yêu cầu: {expected_w}x{expected_h})"

