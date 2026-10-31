"""
Multi-channel notification service for Chaos Zero Nightmare Bot.
Supports Telegram, Discord Webhook, and Windows Toast notifications.
"""
import sys
import json
import logging
import threading
import subprocess
import urllib.request
from typing import Optional

from czn_bot.settings import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DISCORD_WEBHOOK_URL,
    ENABLE_WINDOWS_TOAST,
)

logger = logging.getLogger("ChaosBot.Notifier")


class Notifier:
    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        discord_webhook: Optional[str] = None,
        enable_toast: Optional[bool] = None,
    ) -> None:
        self.telegram_token = telegram_token or TELEGRAM_BOT_TOKEN
        self.telegram_chat_id = telegram_chat_id or TELEGRAM_CHAT_ID
        self.discord_webhook = discord_webhook or DISCORD_WEBHOOK_URL
        self.enable_toast = enable_toast if enable_toast is not None else ENABLE_WINDOWS_TOAST

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

    @property
    def has_discord(self) -> bool:
        return bool(self.discord_webhook)

    def send_telegram(self, text: str) -> bool:
        """Send message via Telegram Bot API."""
        if not self.has_telegram:
            return False

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"Lỗi gửi Telegram: {e}")
            return False

    def send_discord(self, text: str) -> bool:
        """Send message via Discord Webhook."""
        if not self.has_discord:
            return False

        payload = {"content": text}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.discord_webhook,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                return resp.status in (200, 204)
        except Exception as e:
            logger.warning(f"Lỗi gửi Discord: {e}")
            return False

    def send_windows_toast(self, title: str, text: str) -> bool:
        """Send a Windows desktop Toast/Balloon notification via PowerShell."""
        if not self.enable_toast or sys.platform != "win32":
            return False

        safe_title = title.replace("'", "''")
        safe_text = text.replace("'", "''")
        ps_script = (
            f"[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null; "
            f"$notify = New-Object System.Windows.Forms.NotifyIcon; "
            f"$notify.Icon = [System.Drawing.SystemIcons]::Information; "
            f"$notify.Visible = $True; "
            f"$notify.ShowBalloonTip(4000, '{safe_title}', '{safe_text}', [System.Windows.Forms.ToolTipIcon]::Info)"
        )
        try:
            flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                creationflags=flags,
                timeout=5.0,
                capture_output=True,
            )
            return True
        except Exception as e:
            logger.warning(f"Lỗi hiển thị Windows Toast: {e}")
            return False

    def notify(self, title: str, message: str, is_alert: bool = True) -> None:
        """Dispatch notifications to all enabled channels asynchronously."""
        def _worker():
            prefix = "⚠️ [ChaosBot Cảnh Báo]" if is_alert else "ℹ️ [ChaosBot Thông Báo]"
            formatted_text = f"{prefix}\n<b>{title}</b>\n{message}"
            plain_text = f"{prefix}\n{title}\n{message}"

            if self.has_telegram:
                self.send_telegram(formatted_text)
            if self.has_discord:
                self.send_discord(plain_text)
            if self.enable_toast:
                self.send_windows_toast(title, message)

        threading.Thread(target=_worker, daemon=True).start()

    # ── Convenience Alert Methods ─────────────────────────────────────

    def notify_stamina_depleted(self) -> None:
        """Trigger alert when stamina runs out (gray Retry button)."""
        self.notify(
            title="ĐÃ HẾT THỂ LỰC!",
            message="Nút Retry bị xám. Bot đã tự động dừng an toàn để chờ hồi thể lực.",
            is_alert=True,
        )

    def notify_stamina_exhausted(self, mode_name: str = "") -> None:
        self.notify_stamina_depleted()

    def notify_unknown_halt(self) -> None:
        """Trigger alert when halted due to 3 consecutive unknown screens."""
        self.notify(
            title="DỪNG AN TOÀN (UNKNOWN)",
            message="Phát hiện màn hình lạ 3 lần liên tiếp. Ảnh đã được lưu vào thư mục logs.",
            is_alert=True,
        )

    def notify_unknown_streak(self, count: int = 3) -> None:
        self.notify_unknown_halt()

    def notify_max_retries(self, retries: int) -> None:
        """Trigger alert when reaching target max retry count."""
        self.notify(
            title="HOÀN THÀNH MỤC TIÊU",
            message=f"Đã đạt giới hạn {retries} lượt Retry thành công. Bot dừng hoạt động.",
            is_alert=False,
        )

    def notify_adb_error(self, error: str) -> None:
        """Trigger alert when ADB screencap fails or device disconnects."""
        self.notify(
            title="MẤT KẾT NỐI ADB",
            message=f"Không thể chụp màn hình hoặc kết nối tới BlueStacks bị ngắt: {error}",
            is_alert=True,
        )

    def notify_match_failed(self) -> None:
        """Trigger alert when a story stage or battle is lost."""
        self.notify(
            title="THUA TRẬN CỐT TRUYỆN!",
            message="Đội hình thất bại trong ải cốt truyện. Bot đã dừng hoạt động an toàn.",
            is_alert=True,
        )

    def notify_bot_stopped(self, reason: str, stats_summary: Optional[str] = None) -> None:
        """Trigger notification on any stop with optional performance stats."""
        msg = f"Lý do: {reason}"
        if stats_summary:
            msg += f"\n\n{stats_summary}"
        self.notify(title="BOT ĐÃ DỪNG", message=msg, is_alert=False)
