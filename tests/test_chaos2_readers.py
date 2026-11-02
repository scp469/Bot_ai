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
        """Sự kiện Waypoint đơn: 1 lựa chọn ở giữa (795, 765), nút kiếm xám (present=True, active=False), không có curse."""
        img = self._load_state_img("event_waypoint_single.png")
        facts = read_event_facts(img)

        self.assertTrue(facts.is_waypoint)
        self.assertEqual(len(facts.choices), 1)
        self.assertEqual(facts.choices[0].center, (795, 765))
        self.assertTrue(facts.sword_button_present)
        self.assertFalse(facts.sword_button_active)
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

    def test_a1_read_equipment_recommended_rows(self):
        """Hàng recommended_row đọc từ ảnh thật (Item 9): row 0, 1, 2."""
        cases = [
            ("equipment_row1_selected.png", 0),
            ("equipment_row3_selected.png", 2),
        ]
        for fname, exp_rec in cases:
            with self.subTest(fixture=fname):
                img = self._load_state_img(fname)
                facts = read_equipment_facts(img, detector=self.detector)
                self.assertEqual(facts.recommended_row, exp_rec)

        ready_img = cv2.imread("tests/fixtures/chaos_equipment_ready.png")
        if ready_img is not None:
            facts_ready = read_equipment_facts(ready_img, detector=self.detector)
            self.assertEqual(facts_ready.selected_row, 1)
            self.assertEqual(facts_ready.recommended_row, 1)

    # ── A7. SAFE ZONE FACTS ───────────────────────────────────────────────────
    def test_a7_read_safe_zone_facts(self):
        """Trạm nghỉ: cả Rest icon và Skip đều sẵn sàng, interactions_left=1 (Item 9)."""
        for fname in ["safe_zone.png", "safe_zone_shop.png"]:
            with self.subTest(fixture=fname):
                img = self._load_state_img(fname)
                facts = read_safe_zone_facts(img, detector=self.detector)

                self.assertTrue(facts.rest_available)
                self.assertTrue(facts.skip_available)
                self.assertEqual(facts.rest_center, (380, 680))
                self.assertEqual(facts.skip_center, (1426, 825))
                self.assertEqual(facts.interactions_left, 1)
                self.assertEqual(facts.interactions_count, 1)

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
        """Thanh máu HUD đọc từ ảnh thật không mock (Item 1): trả về None khi không có HUD."""
        # 1. Các màn CÓ HUD hợp lệ:
        hud_cases = [
            ("map_1island.png", 1.00, False),
            ("map_2islands.png", 0.88, False),
            ("safe_zone_shop.png", 0.81, False),
            ("settlement_dialog_leave.png", 0.55, True),
            ("in_match.png", 1.00, False),
        ]
        for fname, expected_hp, expected_is_low in hud_cases:
            with self.subTest(fixture=fname):
                img = self._load_state_img(fname)
                facts = read_hp_facts(img)

                self.assertIsNotNone(facts, f"{fname} phải có HpFacts hợp lệ")
                self.assertAlmostEqual(facts.hp_fraction, expected_hp, places=1)
                self.assertEqual(facts.is_low_hp, expected_is_low)

        # 2. Các màn KHÔNG CÓ HUD -> HpFacts PHẢI là None (Item 1)
        no_hud_cases = [
            "choose_fate.png",
            "select_duplicate_card.png",
            "select_duplicate_card_2.png",
            "copy_card_complete.png",
            "epiphany_choose_effect.png",
            "remove_card_none_selected.png",
            "remove_card_selected.png",
        ]
        for fname in no_hud_cases:
            with self.subTest(no_hud=fname):
                img = self._load_state_img(fname)
                facts = read_hp_facts(img)
                self.assertIsNone(facts, f"{fname} không có HUD nên HpFacts phải là None")


class TestChaos2ClassifierRealFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures_dir = Path("tests/fixtures/states")
        cls.detector = ScreenDetector()
        cls.classifier = ChaosClassifier(matcher=cls.detector.match)

    def test_classifier_accuracy_on_all_21_fixtures(self):
        """Toàn bộ 28 ảnh thật (21 cũ + 7 đợt 2) đều phân loại đúng 100%, margin > 0.15, không UNKNOWN."""
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
            # 7 Round 2 Fixtures (Item 6):
            "settlement_dialog_leave.png": "CHAOS_SETTLEMENT",
            "select_duplicate_card_2.png": "CHAOS_SELECT_DUPLICATE_CARD",
            "copy_card_complete.png": "CHAOS_COPY_COMPLETE",
            "epiphany_choose_effect.png": "CHAOS_CHOOSE_EPIPHANY",
            "in_match.png": "IN_MATCH",
            "remove_card_none_selected.png": "CHAOS_REMOVE_CARD",
            "remove_card_selected.png": "CHAOS_REMOVE_CARD",
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
        self.fixtures_dir = Path("tests/fixtures/states")

    def test_part_c_real_fixtures_facts(self):
        """Kiểm tra Facts trên 7 fixture đợt 2 theo đúng Ground Truth (Item 6)."""
        # 1. settlement_dialog_leave: SETTLEMENT, có Leave, dialog confirm y≈569
        img_leave = cv2.imread(str(self.fixtures_dir / "settlement_dialog_leave.png"))
        dfacts_leave = read_dialog_facts(img_leave)
        self.assertEqual(dfacts_leave.dialog_type, "loot")
        self.assertEqual(dfacts_leave.confirm_center, (1055, 569))

        # 2. select_duplicate_card_2: 3 thẻ Nia's Curiosity / G Chord / Quantum Seed; cost 0/1/0; pin ở Quantum Seed
        img_dup2 = cv2.imread(str(self.fixtures_dir / "select_duplicate_card_2.png"))
        dup_facts = read_duplicate_card_facts(img_dup2)
        self.assertEqual(len(dup_facts.cards), 3)
        self.assertEqual(dup_facts.cards[0].name, "Nia's Curiosity")
        self.assertEqual(dup_facts.cards[0].cost, 0)
        self.assertFalse(dup_facts.cards[0].has_pin)
        self.assertEqual(dup_facts.cards[1].name, "G Chord")
        self.assertEqual(dup_facts.cards[1].cost, 1)
        self.assertFalse(dup_facts.cards[1].has_pin)
        self.assertEqual(dup_facts.cards[2].name, "Quantum Seed")
        self.assertEqual(dup_facts.cards[2].cost, 0)
        self.assertTrue(dup_facts.cards[2].has_pin)

        # 3. copy_card_complete: COPY_COMPLETE, 2 thẻ Quantum Seed, thẻ phải có [Duplicated]
        img_copy = cv2.imread(str(self.fixtures_dir / "copy_card_complete.png"))
        copy_facts = read_copy_complete_facts(img_copy)
        self.assertTrue(copy_facts.has_copy_complete)
        self.assertEqual(copy_facts.duplicated_card_name, "Quantum Seed")
        self.assertEqual(copy_facts.close_center, (800, 845))

        # 4. epiphany_choose_effect: EPIPHANY, 3 thẻ Dual Creation, 3 tag, 3 effect
        img_epi = cv2.imread(str(self.fixtures_dir / "epiphany_choose_effect.png"))
        epi_facts = read_epiphany_facts(img_epi)
        self.assertEqual(len(epi_facts.cards), 3)
        for c in epi_facts.cards:
            self.assertEqual(c.name, "Dual Creation")
            self.assertTrue(len(c.effect_text) > 0)
        self.assertEqual(epi_facts.cards[0].tag, "[Unique]")
        self.assertEqual(epi_facts.cards[1].tag, "[Unique / Initiation]")
        self.assertEqual(epi_facts.cards[2].tag, "[Unique / Initiation]")

        # 5. in_match: HUD HP 1800/1800
        img_match = cv2.imread(str(self.fixtures_dir / "in_match.png"))
        hp_match = read_hp_facts(img_match)
        self.assertIsNotNone(hp_match)
        self.assertEqual(hp_match.current_hp, 1800)
        self.assertEqual(hp_match.max_hp, 1800)
        self.assertEqual(hp_match.hp_fraction, 1.0)

        # 6. remove_card_none_selected: remove_enabled=False, selected_count=0, 0/130pt, 0/5
        img_rem_none = cv2.imread(str(self.fixtures_dir / "remove_card_none_selected.png"))
        rem_none_facts = read_remove_facts(img_rem_none)
        self.assertFalse(rem_none_facts.remove_enabled)
        self.assertEqual(rem_none_facts.selected_count, 0)
        self.assertEqual(rem_none_facts.budget_used, 0)
        self.assertEqual(rem_none_facts.budget_max, 130)
        self.assertEqual(rem_none_facts.removals_used, 0)
        self.assertEqual(rem_none_facts.removals_max, 5)
        self.assertIsNone(rem_none_facts.selected_card_name)

        # 7. remove_card_selected: remove_enabled=True, selected_count=1, 20/130pt, 1/5, Standing Blade
        img_rem_sel = cv2.imread(str(self.fixtures_dir / "remove_card_selected.png"))
        rem_sel_facts = read_remove_facts(img_rem_sel)
        self.assertTrue(rem_sel_facts.remove_enabled)
        self.assertEqual(rem_sel_facts.selected_count, 1)
        self.assertEqual(rem_sel_facts.budget_used, 20)
        self.assertEqual(rem_sel_facts.budget_max, 130)
        self.assertEqual(rem_sel_facts.removals_used, 1)
        self.assertEqual(rem_sel_facts.removals_max, 5)
        self.assertEqual(rem_sel_facts.selected_card_name, "Standing Blade")
        self.assertEqual(rem_sel_facts.cards_visible, 8)
        self.assertEqual(rem_sel_facts.has_pin_cards, ["Sword Slash", "Sword Slash", "Standing Blade"])

    def test_tap_guard_blocks_forbidden_zones(self):
        """TapGuard từ chối mặc định mọi tap rơi vào forbidden_tap_zones (Item 4)."""
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

        # 6. Event: Nút tròn kiếm cấm tap (G6)
        res_sword = self.guard.validate_coords(1515, 780, "CHAOS_EVENT")
        self.assertFalse(res_sword.allowed)

        # 7. Safe Zone: Shop và Training cấm tap (Item 5)
        res_shop = self.guard.validate_coords(800, 300, "CHAOS_SAFE_ZONE")
        self.assertFalse(res_shop.allowed)
        res_train = self.guard.validate_coords(1200, 250, "CHAOS_SAFE_ZONE")
        self.assertFalse(res_train.allowed)

        # 8. Choose Fate: Nút tròn ▶ cạnh Confirm cấm tap
        res_play = self.guard.validate_coords(1220, 835, "CHAOS_CHOOSE_FATE")
        self.assertFalse(res_play.allowed)

        # 9. Settlement: Temporary Return và Obtain-voucher cấm tap
        res_temp = self.guard.validate_coords(950, 825, "CHAOS_SETTLEMENT")
        self.assertFalse(res_temp.allowed)
        res_vouch = self.guard.validate_coords(1400, 350, "CHAOS_SETTLEMENT")
        self.assertFalse(res_vouch.allowed)

    def test_tap_guard_modal_dialog_overlay(self):
        """Khi modal dialog đang mở (Item 5): Chỉ Confirm/Cancel được tap, tap ngoài bị chặn."""
        ctx_dialog = {"dialog_active": True}
        # Tap Confirm dialog (1055, 569) -> ALLOWED
        res_conf = self.guard.validate_coords(1055, 569, "CHAOS_SETTLEMENT", context=ctx_dialog)
        self.assertTrue(res_conf.allowed)

        # Tap Cancel dialog (545, 569) -> ALLOWED
        res_canc = self.guard.validate_coords(545, 569, "CHAOS_SETTLEMENT", context=ctx_dialog)
        self.assertTrue(res_canc.allowed)

        # Tap vào vùng nền ngoài dialog (1426, 825 - nút Continue cũ) -> BLOCKED
        res_bg = self.guard.validate_coords(1426, 825, "CHAOS_SETTLEMENT", context=ctx_dialog)
        self.assertFalse(res_bg.allowed)
        self.assertIn("Hộp thoại Modal đang mở", res_bg.reason)

    def test_tap_guard_map_lane_restriction(self):
        """Trên CHAOS_MAP (Item 5): map_1island chỉ cho phép tap làn giữa (lane 1), chặn làn 0 và 2."""
        ctx_1island = {"active_lanes": [1]}
        # Tap làn 1 (Mid: 1250, 480) -> ALLOWED
        res_mid = self.guard.validate_coords(1250, 480, "CHAOS_MAP", context=ctx_1island)
        self.assertTrue(res_mid.allowed)

        # Tap làn 0 (Top: 1080, 200) -> BLOCKED vì lane 0 không tồn tại
        res_top = self.guard.validate_coords(1080, 200, "CHAOS_MAP", context=ctx_1island)
        self.assertFalse(res_top.allowed)
        self.assertIn("Làn 0 không tồn tại", res_top.reason)

        # Tap làn 2 (Bot: 1080, 720) -> BLOCKED vì lane 2 không tồn tại
        res_bot = self.guard.validate_coords(1080, 720, "CHAOS_MAP", context=ctx_1island)
        self.assertFalse(res_bot.allowed)
        self.assertIn("Làn 2 không tồn tại", res_bot.reason)

    def test_irreversible_allowlist_and_rate_limiting(self):
        """Item 8: IRREVERSIBLE_ALLOW mở hành động thật; log_only dedupe và giới hạn ảnh."""
        from czn_bot.chaos2 import config
        classifier = ChaosClassifier(matcher=ScreenDetector().match)
        loop = ChaosLoop(classifier=classifier, dry_run=False)

        real_screen = cv2.imread("tests/fixtures/chaos_choose_epiphany.png")

        # 1. Khi chưa allow: action có is_irreversible=True bị chặn
        act_blocked = ChaosAction.tap(
            400, 480, expected_next="CHAOS_MAP", reason="Chọn thẻ Epiphany",
            action_name="choose_epiphany", is_irreversible=True
        )
        SCREEN_REGISTRY["CHAOS_CHOOSE_EPIPHANY"].handler = lambda s, c: act_blocked
        try:
            for _ in range(3):
                res = loop.step(real_screen)
            self.assertEqual(res.type, "wait")
            self.assertIn("IRREVERSIBLE_MODE='log_only'", res.reason)

            # 2. Khi thêm vào IRREVERSIBLE_ALLOW -> Được tap thật
            config.IRREVERSIBLE_ALLOW.append("choose_epiphany")
            for _ in range(3):
                res_allowed = loop.step(real_screen)
            self.assertEqual(res_allowed.type, "tap")
            self.assertEqual(res_allowed.target, (400, 480))
        finally:
            config.IRREVERSIBLE_ALLOW.clear()
            SCREEN_REGISTRY["CHAOS_CHOOSE_EPIPHANY"].handler = None

    def test_irreversible_mode_log_only_suppresses_tap(self):
        """Khi IRREVERSIBLE_MODE = 'log_only', ChaosLoop không phát tap cho màn/hành động irreversible."""
        detector = ScreenDetector()
        classifier = ChaosClassifier(matcher=detector.match)
        loop = ChaosLoop(classifier=classifier, dry_run=False)

        real_screen = cv2.imread("tests/fixtures/chaos_choose_epiphany.png")
        self.assertIsNotNone(real_screen)

        action = ChaosAction.tap(400, 480, expected_next="CHAOS_MAP", reason="Chọn thẻ Epiphany")

        SCREEN_REGISTRY["CHAOS_CHOOSE_EPIPHANY"].handler = lambda s, c: action
        try:
            for _ in range(3):
                res_action = loop.step(real_screen)

            self.assertEqual(res_action.type, "wait")
            self.assertIn("IRREVERSIBLE_MODE='log_only'", res_action.reason)
        finally:
            SCREEN_REGISTRY["CHAOS_CHOOSE_EPIPHANY"].handler = None


if __name__ == "__main__":
    unittest.main()
