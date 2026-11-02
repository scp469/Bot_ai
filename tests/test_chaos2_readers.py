"""
tests/test_chaos2_readers.py - Kiểm thử toàn diện các Reader Perception và Classifier của Chaos2.
Tuân thủ nghiêm ngặt:
  - 100% kiểm thử trên ảnh thật (fixtures thật), ZERO mock dữ liệu hình ảnh.
  - Ground truth lấy từ giá trị đo đạc vật lý trên ảnh, KHÔNG lấy từ output của hàm.
  - Kiểm tra chéo trên toàn bộ tập ảnh cũ (16 ảnh gốc) và 21 ảnh mới (tests/fixtures/states/).
"""

import os
import unittest
from pathlib import Path
import cv2
import numpy as np

from czn_bot.vision.detector import ScreenDetector
from czn_bot.chaos2.classifier import ChaosClassifier
from czn_bot.chaos2.registry import SCREEN_REGISTRY
from czn_bot.chaos2.guard import TapGuard
from czn_bot.chaos2.action import ChaosAction
from czn_bot.chaos2.loop import ChaosLoop
from czn_bot.chaos2.config import (
    IRREVERSIBLE_MODE,
    ZONE_EPIPHANY_VIEW_ORIGINAL,
    ZONE_REMOVE_CANCEL,
    ZONE_REMOVE_EXECUTE,
    ZONE_DUPLICATE_SKIP,
    ZONE_OBTAIN_SKIP,
    ZONE_EQUIP_EXTRACT,
)
from czn_bot.chaos2.perception.readers import (
    read_equipment_facts,
    read_obtain_facts,
    read_map_facts,
    read_event_facts,
    read_dialog_facts,
    read_settlement_facts,
    read_safe_zone_facts,
    read_fate_facts,
    read_duplicate_card_facts,
    read_hp_facts,
    read_epiphany_facts,
    read_remove_facts,
    read_copy_complete_facts,
)


class TestChaos2Readers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures_dir = Path("tests/fixtures/states")
        cls.detector = ScreenDetector()
        cls.classifier = ChaosClassifier(matcher=cls.detector.match)

    def _load_state_img(self, name: str) -> np.ndarray:
        p = self.fixtures_dir / name
        self.assertTrue(p.exists(), f"Fixture không tồn tại: {p}")
        img = cv2.imread(str(p))
        self.assertIsNotNone(img, f"Không đọc được ảnh: {p}")
        self.assertEqual(img.shape[:2], (900, 1600), f"Ảnh phải đúng 1600x900: {p}")
        return img

    # ── A1. EQUIPMENT FACTS ───────────────────────────────────────────────────
    def test_a1_read_equipment_facts_row1_selected(self):
        """Hàng 1 đang được chọn (viền cam + thanh nối cam), Confirm và Extract đều có."""
        img = self._load_state_img("equipment_row1_selected.png")
        facts = read_equipment_facts(img, detector=self.detector)

        self.assertEqual(facts.selected_row, 0)
        self.assertTrue(facts.confirm_ready)
        self.assertTrue(facts.extract_detected)
        self.assertEqual(facts.confirm_center, (1426, 837))

    def test_a1_read_equipment_facts_row3_selected(self):
        """Hàng 3 đang được chọn (viền cam + thanh nối cam), Confirm và Extract đều có."""
        img = self._load_state_img("equipment_row3_selected.png")
        facts = read_equipment_facts(img, detector=self.detector)

        self.assertEqual(facts.selected_row, 2)
        self.assertTrue(facts.confirm_ready)
        self.assertTrue(facts.extract_detected)
        self.assertEqual(facts.confirm_center, (1426, 837))

    # ── A2. OBTAIN FACTS ──────────────────────────────────────────────────────
    def test_a2_read_obtain_facts_all_variations(self):
        """Số đếm đọc từ nút Obtain phải đúng tuyệt đối theo giá trị vật lý trên từng ảnh."""
        test_cases = [
            ("obtain_credits_only.png", 1, True),
            ("obtain_duplicate_card.png", 3, True),
            ("obtain_equipment_credits.png", 2, True),
            ("obtain_equipment_done.png", 1, True),
            ("obtain_equipment_highlight.png", 2, True),
        ]
        for fname, expected_count, expected_skip in test_cases:
            with self.subTest(fixture=fname):
                img = self._load_state_img(fname)
                facts = read_obtain_facts(img)

                self.assertEqual(facts.button_count, expected_count)
                self.assertEqual(facts.count, expected_count)
                self.assertEqual(facts.skip_detected, expected_skip)
                self.assertEqual(facts.obtain_btn_center, (1426, 825))

    # ── A3. MAP FACTS ─────────────────────────────────────────────────────────
    def test_a3_read_map_facts_1island(self):
        """Map 1 đảo: chỉ có làn giữa (làn 1), cờ chiến đấu màu hồng."""
        img = self._load_state_img("map_1island.png")
        facts = read_map_facts(img)

        self.assertEqual(facts.lanes, [1])
        self.assertEqual(facts.arrows_detected, [1])
        self.assertEqual(facts.lane_types.get(1), "battle")

    def test_a3_read_map_facts_2islands(self):
        """Map 2 đảo: làn trên (0) cờ sự kiện xanh, làn giữa (1) cờ chiến đấu hồng."""
        img = self._load_state_img("map_2islands.png")
        facts = read_map_facts(img)

        self.assertEqual(facts.lanes, [0, 1])
        self.assertEqual(facts.arrows_detected, [0, 1])
        self.assertEqual(facts.lane_types.get(0), "event")
        self.assertEqual(facts.lane_types.get(1), "battle")

    def test_a3_read_map_facts_3islands(self):
        """Map 3 đảo: cả 3 làn [0, 1, 2] đều kích hoạt, đều là cờ chiến đấu."""
        img = self._load_state_img("map_3islands.png")
        facts = read_map_facts(img)

        self.assertEqual(facts.lanes, [0, 1, 2])
        self.assertEqual(facts.arrows_detected, [0, 1, 2])
        self.assertEqual(facts.lane_types.get(0), "battle")
        self.assertEqual(facts.lane_types.get(1), "battle")
        self.assertEqual(facts.lane_types.get(2), "battle")

    # ── A4. EVENT FACTS ───────────────────────────────────────────────────────
    def test_a4_read_event_facts_3choices(self):
        """Sự kiện 3 lựa chọn: có nút tròn kiếm (1515, 780), lựa chọn thứ 3 có lời nguyền (chữ tím)."""
        img = self._load_state_img("event_3choices.png")
        facts = read_event_facts(img)

        self.assertFalse(facts.is_waypoint)
        self.assertEqual(len(facts.choices), 3)
        self.assertTrue(facts.sword_button_detected)
        self.assertTrue(facts.has_curse)
        self.assertFalse(facts.choices[0].has_curse)
        self.assertFalse(facts.choices[1].has_curse)
        self.assertTrue(facts.choices[2].has_curse)

    def test_a4_read_event_facts_waypoint_single(self):
        """Sự kiện Waypoint đơn: 1 lựa chọn ở giữa (795, 765), không có nút kiếm, không có curse."""
        img = self._load_state_img("event_waypoint_single.png")
        facts = read_event_facts(img)

        self.assertTrue(facts.is_waypoint)
        self.assertEqual(len(facts.choices), 1)
        self.assertEqual(facts.choices[0].center, (795, 765))
        self.assertFalse(facts.sword_button_detected)
        self.assertFalse(facts.has_curse)

    # ── A5. DIALOG FACTS ──────────────────────────────────────────────────────
    def test_a5_read_dialog_facts_rest(self):
        """Dialog Rest: nút Confirm ở y=642, nút Cancel ở y=642, x=545."""
        img = self._load_state_img("rest_dialog.png")
        facts = read_dialog_facts(img)

        self.assertEqual(facts.dialog_type, "rest")
        self.assertEqual(facts.confirm_center, (1055, 642))
        self.assertEqual(facts.cancel_center, (545, 642))

    def test_a5_read_dialog_facts_loot(self):
        """Dialog Loot: nút Confirm ở y=569, nút Cancel ở y=569, x=545."""
        img = self._load_state_img("settlement_confirm_dialog.png")
        facts = read_dialog_facts(img)

        self.assertEqual(facts.dialog_type, "loot")
        self.assertEqual(facts.confirm_center, (1055, 569))
        self.assertEqual(facts.cancel_center, (545, 569))

    # ── A6. SETTLEMENT FACTS ──────────────────────────────────────────────────
    def test_a6_read_settlement_facts_full_screens(self):
        """Màn settlement 1 và 2: có Temporary Return trắng (mean > 100) và Voucher."""
        for fname in ["settlement_screen_1.png", "settlement_screen_2.png"]:
            with self.subTest(fixture=fname):
                img = self._load_state_img(fname)
                facts = read_settlement_facts(img, detector=self.detector)

                self.assertEqual(facts.continue_center, (1426, 825))
                self.assertTrue(facts.temporary_return_detected)
                self.assertTrue(facts.voucher_detected)
                self.assertGreater(facts.settlement_title_score, 0.70)

    def test_a6_read_settlement_facts_button_only(self):
        """Màn settlement_button (sau trận): chưa mở bảng settlement nên Temporary Return = False."""
        img = self._load_state_img("settlement_button.png")
        facts = read_settlement_facts(img, detector=self.detector)

        self.assertEqual(facts.continue_center, (1426, 825))
        self.assertFalse(facts.temporary_return_detected)

    # ── A7. SAFE ZONE FACTS ───────────────────────────────────────────────────
    def test_a7_read_safe_zone_facts(self):
        """Trạm nghỉ: cả Rest icon và Skip đều sẵn sàng."""
        for fname in ["safe_zone.png", "safe_zone_shop.png"]:
            with self.subTest(fixture=fname):
                img = self._load_state_img(fname)
                facts = read_safe_zone_facts(img, detector=self.detector)

                self.assertTrue(facts.rest_available)
                self.assertTrue(facts.skip_available)
                self.assertEqual(facts.rest_center, (380, 680))
                self.assertEqual(facts.skip_center, (1426, 825))

    # ── A8. FATE FACTS ────────────────────────────────────────────────────────
    def test_a8_read_fate_facts(self):
        """Màn Choose Fate: 3 thẻ buff, Confirm chưa sáng (xám)."""
        img = self._load_state_img("choose_fate.png")
        facts = read_fate_facts(img)

        self.assertEqual(len(facts.cards), 3)
        self.assertFalse(facts.confirm_ready)
        self.assertEqual(facts.confirm_center, (1426, 837))

    # ── A9. DUPLICATE CARD FACTS ──────────────────────────────────────────────
    def test_a9_read_duplicate_card_facts(self):
        """Màn Duplicate Card: có tiêu đề, có Skip, 3 thẻ bài tại [400, 800, 1200]."""
        img = self._load_state_img("select_duplicate_card.png")
        facts = read_duplicate_card_facts(img)

        self.assertTrue(facts.title_detected)
        self.assertTrue(facts.skip_detected)
        self.assertEqual(facts.num_cards, 3)
        centers = [c.center for c in facts.cards]
        self.assertEqual(centers, [(400, 480), (800, 480), (1200, 480)])

    # ── A10. HP FACTS ─────────────────────────────────────────────────────────
    def test_a10_read_hp_facts_variations(self):
        """Thanh máu HUD đọc từ ảnh thật không mock."""
        cases = [
            ("map_1island.png", 1.00, False),
            ("map_2islands.png", 0.88, False),
            ("choose_fate.png", 0.79, False),
            ("safe_zone_shop.png", 0.81, False),
        ]
        for fname, expected_hp, expected_is_low in cases:
            with self.subTest(fixture=fname):
                img = self._load_state_img(fname)
                facts = read_hp_facts(img)

                self.assertIsNotNone(facts)
                self.assertAlmostEqual(facts.hp_fraction, expected_hp, places=1)
                self.assertEqual(facts.is_low_hp, expected_is_low)


class TestChaos2ClassifierRealFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures_dir = Path("tests/fixtures/states")
        cls.detector = ScreenDetector()
        cls.classifier = ChaosClassifier(matcher=cls.detector.match)

    def test_classifier_accuracy_on_all_21_fixtures(self):
        """Toàn bộ 21 ảnh thật đều phân loại đúng 100%, margin > 0.15, không UNKNOWN."""
        expected_states = {
            "choose_fate.png": "CHAOS_CHOOSE_FATE",
            "equipment_row1_selected.png": "CHAOS_EQUIPMENT",
            "equipment_row3_selected.png": "CHAOS_EQUIPMENT",
            "event_3choices.png": "CHAOS_EVENT",
            "event_waypoint_single.png": "CHAOS_EVENT",
            "map_1island.png": "CHAOS_MAP",
            "map_2islands.png": "CHAOS_MAP",
            "map_3islands.png": "CHAOS_MAP",
            "obtain_credits_only.png": "CHAOS_OBTAIN_REWARD",
            "obtain_duplicate_card.png": "CHAOS_OBTAIN_REWARD",
            "obtain_equipment_credits.png": "CHAOS_OBTAIN_REWARD",
            "obtain_equipment_done.png": "CHAOS_OBTAIN_REWARD",
            "obtain_equipment_highlight.png": "CHAOS_OBTAIN_REWARD",
            "rest_dialog.png": "CHAOS_SAFE_ZONE",
            "safe_zone.png": "CHAOS_SAFE_ZONE",
            "safe_zone_shop.png": "CHAOS_SAFE_ZONE",
            "select_duplicate_card.png": "CHAOS_SELECT_DUPLICATE_CARD",
            "settlement_button.png": "CHAOS_AFTER_BATTLE",
            "settlement_confirm_dialog.png": "CHAOS_SETTLEMENT",
            "settlement_screen_1.png": "CHAOS_SETTLEMENT",
            "settlement_screen_2.png": "CHAOS_SETTLEMENT",
        }

        for fname, expected in expected_states.items():
            with self.subTest(fixture=fname):
                img = cv2.imread(str(self.fixtures_dir / fname))
                res = self.classifier.classify(img)

                self.assertEqual(res.state, expected, f"Sai state cho {fname}")
                self.assertGreaterEqual(res.confidence, 0.70, f"Confidence quá thấp: {res.confidence}")
                self.assertGreaterEqual(res.margin, 0.15, f"Margin quá hẹp: {res.margin}")

    def test_cross_validation_on_original_chaos_fixtures(self):
        """Kiểm tra chéo trên tập fixture cũ: không nhận sai chéo giữa các màn."""
        orig_dir = Path("tests/fixtures")
        cross_cases = {
            "chaos_card_reward.png": "CHAOS_CHOOSE_EPIPHANY",
            "chaos_choose_epiphany.png": "CHAOS_CHOOSE_EPIPHANY",
            "chaos_choose_fate.png": "CHAOS_CHOOSE_FATE",
            "chaos_continue.png": "CHAOS_AFTER_BATTLE",
            "chaos_equipment_ready.png": "CHAOS_EQUIPMENT",
            "chaos_map_1_island.png": "CHAOS_MAP",
            "chaos_map_2_islands.png": "CHAOS_MAP",
            "chaos_map_3_islands.png": "CHAOS_MAP",
            "chaos_map_diagonal.png": "CHAOS_MAP",
            "chaos_map_seraph.png": "CHAOS_MAP",
            "chaos_remove_card.png": "CHAOS_REMOVE_CARD",
            "chaos_reward_leave.png": "CHAOS_AFTER_BATTLE",
            "chaos_reward_obtain.png": "CHAOS_OBTAIN_REWARD",
            "chaos_safe_zone.png": "CHAOS_SAFE_ZONE",
        }
        for fname, expected in cross_cases.items():
            p = orig_dir / fname
            if not p.exists():
                continue
            with self.subTest(fixture=fname):
                img = cv2.imread(str(p))
                res = self.classifier.classify(img)
                self.assertEqual(res.state, expected, f"Sai cross-validation cho {fname}")


class TestPartCBehaviorAndGuard(unittest.TestCase):
    def setUp(self):
        self.guard = TapGuard()

    def test_tap_guard_blocks_forbidden_zones(self):
        """TapGuard từ chối mặc định mọi tap rơi vào forbidden_tap_zones."""
        # 1. Epiphany: View original cấm tap
        res = self.guard.validate_coords(1400, 115, "CHAOS_CHOOSE_EPIPHANY")
        self.assertFalse(res.allowed)
        self.assertIn("VÙNG CẤM", res.reason)

        # 2. Remove card: Cancel và Execute đều bị cấm tap mặc định
        res_cancel = self.guard.validate_coords(200, 830, "CHAOS_REMOVE_CARD")
        self.assertFalse(res_cancel.allowed)
        res_exec = self.guard.validate_coords(1400, 830, "CHAOS_REMOVE_CARD")
        self.assertFalse(res_exec.allowed)

        # 3. Duplicate card: Skip cấm tap
        res_skip = self.guard.validate_coords(1400, 835, "CHAOS_SELECT_DUPLICATE_CARD")
        self.assertFalse(res_skip.allowed)

        # 4. Equipment: Extract đỏ cấm tap
        res_extract = self.guard.validate_coords(1000, 835, "CHAOS_EQUIPMENT")
        self.assertFalse(res_extract.allowed)

        # 5. Obtain: Skip trắng cấm tap
        res_ob_skip = self.guard.validate_coords(1050, 825, "CHAOS_OBTAIN_REWARD")
        self.assertFalse(res_ob_skip.allowed)

    def test_irreversible_mode_log_only_suppresses_tap(self):
        """Khi IRREVERSIBLE_MODE = 'log_only', ChaosLoop không phát tap cho màn irreversible."""
        detector = ScreenDetector()
        classifier = ChaosClassifier(matcher=detector.match)
        loop = ChaosLoop(classifier=classifier, dry_run=False)

        real_screen = cv2.imread("tests/fixtures/chaos_choose_epiphany.png")
        self.assertIsNotNone(real_screen)

        # Giả lập handler yêu cầu tap vào thẻ 1 (400, 480)
        action = ChaosAction.tap(400, 480, expected_next="CHAOS_MAP", reason="Chọn thẻ Epiphany")

        # Đăng ký handler tạm thời
        SCREEN_REGISTRY["CHAOS_CHOOSE_EPIPHANY"].handler = lambda s, c: action
        try:
            # Chạy K frames để ổn định màn hình
            for _ in range(3):
                res_action = loop.step(real_screen)

            # Vì IRREVERSIBLE_MODE = "log_only", loop PHẢI trả về wait, KHÔNG được phát tap
            self.assertEqual(res_action.type, "wait")
            self.assertIn("IRREVERSIBLE_MODE='log_only'", res_action.reason)
        finally:
            SCREEN_REGISTRY["CHAOS_CHOOSE_EPIPHANY"].handler = None


if __name__ == "__main__":
    unittest.main()
