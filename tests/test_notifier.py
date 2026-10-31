"""
Unit tests for Notifier service and its integration with BotEngine.
"""
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from czn_bot.notifier import Notifier
from czn_bot.runner import BotRunner as BotEngine
from czn_bot.states import Mode, LeftButton


class TestNotifier(unittest.TestCase):
    def setUp(self):
        self.notifier = Notifier(
            telegram_token="fake_token",
            telegram_chat_id="fake_chat",
            discord_webhook="https://discord.com/api/webhooks/fake",
            enable_toast=True,
        )

    def test_channel_detection(self):
        self.assertTrue(self.notifier.has_telegram)
        self.assertTrue(self.notifier.has_discord)

        empty_notifier = Notifier(telegram_token="", telegram_chat_id="", discord_webhook="", enable_toast=False)
        self.assertFalse(empty_notifier.has_telegram)
        self.assertFalse(empty_notifier.has_discord)

    @patch("urllib.request.urlopen")
    def test_send_telegram_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = self.notifier.send_telegram("Hello Telegram")
        self.assertTrue(result)
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_send_discord_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = self.notifier.send_discord("Hello Discord")
        self.assertTrue(result)
        mock_urlopen.assert_called_once()

    @patch("subprocess.run")
    def test_send_windows_toast(self, mock_run):
        with patch("sys.platform", "win32"):
            result = self.notifier.send_windows_toast("Alert", "Bot stopped")
            self.assertTrue(result)
            mock_run.assert_called_once()

    @patch.object(Notifier, "notify")
    def test_alert_helpers(self, mock_notify):
        self.notifier.notify_stamina_depleted()
        mock_notify.assert_called_with(
            title="ĐÃ HẾT THỂ LỰC!",
            message="Nút Retry bị xám. Bot đã tự động dừng an toàn để chờ hồi thể lực.",
            is_alert=True,
        )

        self.notifier.notify_unknown_halt()
        mock_notify.assert_called_with(
            title="DỪNG AN TOÀN (UNKNOWN)",
            message="Phát hiện màn hình lạ 3 lần liên tiếp. Ảnh đã được lưu vào thư mục logs.",
            is_alert=True,
        )

        self.notifier.notify_max_retries(10)
        mock_notify.assert_called_with(
            title="HOÀN THÀNH MỤC TIÊU",
            message="Đã đạt giới hạn 10 lượt Retry thành công. Bot dừng hoạt động.",
            is_alert=False,
        )


class TestBotEngineNotifierIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_adb = MagicMock()
        self.mock_det = MagicMock()
        self.mock_notifier = MagicMock()
        self.engine = BotEngine(
            adb_client=self.mock_adb,
            detector=self.mock_det,
            notifier=self.mock_notifier,
        )
        self.engine.enable_chaos_ai = False
        self.engine.is_running = True
        self.engine.beep = MagicMock()
        self.dummy_screen = np.zeros((10, 10, 3), dtype=np.uint8)

    def test_stamina_alert_trigger(self):
        self.engine._handle_match_done(self.dummy_screen, {"left_button": LeftButton.RETRY_DISABLED})
        self.mock_notifier.notify_stamina_depleted.assert_called_once()

    def test_max_retries_alert_trigger(self):
        self.engine.mode = Mode.REPLAY
        self.engine.retries_done = 5
        self.engine.max_retries = 5
        self.engine._handle_match_done(self.dummy_screen, {"left_button": LeftButton.RETRY})
        self.mock_notifier.notify_max_retries.assert_called_once_with(5)

    def test_unknown_halt_alert_trigger(self):
        self.engine._unknown_streak = 2
        self.engine._handle_unknown(self.dummy_screen, {})
        self.mock_notifier.notify_unknown_halt.assert_called_once()

    def test_stop_notification_trigger(self):
        self.engine.stop("Test reason")
        self.mock_notifier.notify_bot_stopped.assert_called_once()


if __name__ == "__main__":
    unittest.main()
