import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from czn_bot.states import State, Mode
from czn_bot.vision.state_classifier import (
    Anchor, StateSpec, StateClassifier, DEFAULT_STATE_SPECS, TemporalFilter
)
from czn_bot.vision.detector import ScreenDetector
from czn_bot.runner import BotRunner


class TestPhase2StateFixes(unittest.TestCase):
    def setUp(self):
        self.specs_by_name = {}
        for s in DEFAULT_STATE_SPECS:
            self.specs_by_name.setdefault(s.state, []).append(s)

    # ── 1. Negative Anchors Verification ──────────────────────────────────────
    def test_chaos_equipment_has_negative_anchors_for_after_battle(self):
        """CHAOS_EQUIPMENT phải có neo âm cho chaos_leave_button, chaos_continue_button, chaos_settlement_button."""
        eq_specs = self.specs_by_name["CHAOS_EQUIPMENT"]
        self.assertTrue(len(eq_specs) > 0)
        eq_anchors = eq_specs[0].anchors

        neg_keys = {a.key for a in eq_anchors if a.negative}
        self.assertIn("chaos_leave_button", neg_keys)
        self.assertIn("chaos_continue_button", neg_keys)
        self.assertIn("chaos_settlement_button", neg_keys)

        # Giả lập: Nếu xuất hiện equipment_title (0.90) NHƯNG cũng thấy chaos_leave_button (0.80)
        def matcher(screen, key, region=None):
            if key == "equipment_title":
                return (0.90, (800, 120))
            if key == "chaos_leave_button":
                return (0.80, (1400, 820))
            return (0.0, None)

        clf = StateClassifier(specs=eq_specs, matcher=matcher)
        res = clf.classify(np.zeros((900, 1600, 3), dtype=np.uint8))
        self.assertEqual(res.state, "UNKNOWN")  # Bị neo âm loại bỏ hoàn toàn

    def test_chaos_safe_zone_has_negative_anchors(self):
        """CHAOS_SAFE_ZONE phải có neo âm cho chaos_leave, continue, settlement, obtain."""
        sz_specs = self.specs_by_name["CHAOS_SAFE_ZONE"]
        for spec in sz_specs:
            neg_keys = {a.key for a in spec.anchors if a.negative}
            self.assertIn("chaos_leave_button", neg_keys)
            self.assertIn("chaos_continue_button", neg_keys)
            self.assertIn("chaos_settlement_button", neg_keys)
            self.assertIn("chaos_obtain_button", neg_keys)

    def test_chaos_obtain_reward_has_negative_anchors(self):
        """CHAOS_OBTAIN_REWARD phải có neo âm cho equipment_title, leave, continue, settlement."""
        obtain_specs = self.specs_by_name["CHAOS_OBTAIN_REWARD"]
        for spec in obtain_specs:
            neg_keys = {a.key for a in spec.anchors if a.negative}
            self.assertIn("equipment_title", neg_keys)
            self.assertIn("chaos_leave_button", neg_keys)
            self.assertIn("chaos_continue_button", neg_keys)
            self.assertIn("chaos_settlement_button", neg_keys)

    # ── 2. OCR Cross-Check cho Nút Cam Góc Dưới Phải ─────────────────────────
    def test_ocr_cross_check_boosts_score_when_verified(self):
        """Khi template matching mơ hồ (gần ngưỡng th), nếu OCR xác nhận từ khóa -> nâng score lên >= 0.88."""
        detector = ScreenDetector()
        dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)

        # Giả lập cv2.matchTemplate trả về 0.72 (ngưỡng chaos_continue_button là 0.75, điểm mơ hồ)
        with patch.object(detector, "verify_button", return_value=True), \
             patch("cv2.matchTemplate", return_value=np.array([[0.72]], dtype=np.float32)), \
             patch("cv2.minMaxLoc", return_value=(0.0, 0.72, (0, 0), (10, 10))):
            score, pt = detector.match(dummy_screen, "chaos_continue_button", region=(1200, 750, 380, 140))
            self.assertGreaterEqual(score, 0.88)

    def test_ocr_cross_check_drops_score_when_not_verified(self):
        """Khi template matching mơ hồ, nếu OCR không xác nhận -> hạ score xuống dưới ngưỡng."""
        detector = ScreenDetector()
        dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)

        # Giả lập cv2.matchTemplate trả về 0.73 (gần 0.75) nhưng OCR không tìm thấy "continue"
        with patch.object(detector, "verify_button", return_value=False), \
             patch("cv2.matchTemplate", return_value=np.array([[0.73]], dtype=np.float32)), \
             patch("cv2.minMaxLoc", return_value=(0.0, 0.73, (0, 0), (10, 10))):
            score, pt = detector.match(dummy_screen, "chaos_continue_button", region=(1200, 750, 380, 140))
            self.assertLess(score, 0.75)  # Bị kéo xuống dưới ngưỡng để không kích hoạt nhầm

    def test_ocr_cross_check_skipped_when_score_high_or_low(self):
        """Khi điểm rất cao (0.92) hoặc rất thấp (0.40), không gọi OCR cross-check (tiết kiệm hiệu năng)."""
        detector = ScreenDetector()
        dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)

        with patch.object(detector, "verify_button") as mock_verify:
            # Case high score (0.92)
            with patch("cv2.matchTemplate", return_value=np.array([[0.92]], dtype=np.float32)), \
                 patch("cv2.minMaxLoc", return_value=(0.0, 0.92, (0, 0), (10, 10))):
                sc_high, _ = detector.match(dummy_screen, "chaos_continue_button", region=(1200, 750, 380, 140))
                self.assertEqual(sc_high, 0.92)
                mock_verify.assert_not_called()

            # Case low score (0.40)
            with patch("cv2.matchTemplate", return_value=np.array([[0.40]], dtype=np.float32)), \
                 patch("cv2.minMaxLoc", return_value=(0.0, 0.40, (0, 0), (10, 10))):
                sc_low, _ = detector.match(dummy_screen, "chaos_continue_button", region=(1200, 750, 380, 140))
                self.assertEqual(sc_low, 0.40)
                mock_verify.assert_not_called()

    # ── 3. Frame Settling & TemporalFilter Latency ─────────────────────────────
    def test_temporal_filter_latency_elimination_after_transitioning(self):
        """Sau khi vừa hết TRANSITIONING, TemporalFilter loại bỏ lag buffer và cập nhật ngay state ổn định."""
        tf = TemporalFilter(window=5, need=3)

        # 3 frame đầu đang chuyển cảnh
        tf.push(State.TRANSITIONING, is_unstable=True)
        tf.push(State.TRANSITIONING, is_unstable=True)
        self.assertEqual(tf.stable, "TRANSITIONING")

        # Frame kế tiếp màn hình đã ổn định và nhận diện thấy CHAOS_MAP
        res_state = tf.push(State.CHAOS_MAP, is_unstable=False)
        self.assertEqual(res_state, "CHAOS_MAP")
        self.assertTrue(tf.is_settled(min_frames=1))

    # ── 4. Tách CHAOS_CHOOSE_FATE thành State riêng ──────────────────────────
    def test_chaos_choose_fate_enum_and_spec(self):
        """CHAOS_CHOOSE_FATE tồn tại độc lập trong State enum và StateSpec."""
        self.assertIn("CHAOS_CHOOSE_FATE", State.__members__)
        fate_specs = self.specs_by_name.get("CHAOS_CHOOSE_FATE", [])
        self.assertTrue(len(fate_specs) > 0)
        self.assertEqual(fate_specs[0].anchors[0].key, "choose_fate_title")


if __name__ == "__main__":
    unittest.main()

