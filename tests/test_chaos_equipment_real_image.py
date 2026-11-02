import os
import unittest
import cv2
import numpy as np

from czn_bot.states import State
from czn_bot.flows.base import Action, ActionType
from czn_bot.flows.chaos import ChaosFlow
from czn_bot.constants import EQUIP_CONFIRM_ORANGE_THRESHOLD, EQUIP_CONFIRM_COORD


class TestChaosEquipmentRealImage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_path = os.path.join("tests", "fixtures", "chaos_equipment_ready.png")
        if not os.path.exists(cls.fixture_path):
            raise unittest.SkipTest(f"Fixture image {cls.fixture_path} chưa tồn tại")
        cls.real_screen = cv2.imread(cls.fixture_path)
        assert cls.real_screen is not None, "Không thể đọc ảnh fixture chaos_equipment_ready.png"
        assert cls.real_screen.shape[:2] == (900, 1600), f"Độ phân giải phải là 1600x900, nhận được: {cls.real_screen.shape}"

    def setUp(self):
        self.flow = ChaosFlow()

    def test_real_image_screen_readiness(self):
        """Màn hình sẵn sàng được nhận diện trên ảnh thật (Select combatant / Extract / Avg Sig Cost)."""
        is_ready = self.flow._is_equip_screen_ready(self.real_screen, {})
        self.assertTrue(is_ready, "Màn hình thực tế phải được nhận diện là sẵn sàng chọn nhân vật")

    def test_real_image_detect_selected_combatant_row(self):
        """_detect_selected_combatant_row trả hàng index 1 (thẻ giữa có viền cam trên ảnh thật)."""
        selected_row = self.flow._detect_selected_combatant_row(self.real_screen)
        self.assertEqual(selected_row, 1, "Thẻ giữa (index 1) đang được viền cam chọn sẵn trên ảnh thật")

    def test_real_image_find_recommended_row(self):
        """Tìm nhãn Recommended trả hàng index 1 (thẻ giữa)."""
        rec_row = self.flow._find_recommended_row(self.real_screen)
        self.assertEqual(rec_row, 1, "Nhãn Recommended nằm ở thẻ giữa (index 1) trên ảnh thật")

    def test_real_image_confirm_button_orange_ratio(self):
        """Tỷ lệ cam của nút Confirm >= ngưỡng hằng số EQUIP_CONFIRM_ORANGE_THRESHOLD (0.15)."""
        is_orange, ratio = self.flow._check_confirm_button_orange(self.real_screen, {})
        self.assertTrue(is_orange, f"Nút Confirm phải đạt ngưỡng cam (thực tế: {ratio:.1%})")
        self.assertGreaterEqual(ratio, EQUIP_CONFIRM_ORANGE_THRESHOLD)

    def test_real_image_full_flow_skips_card_tap_and_confirms(self):
        """
        Quy trình đầy đủ trên ảnh thật:
        Vì thẻ Recommended đã được chọn sẵn từ trước (viền cam), bot bỏ qua tap thẻ
        và chuyển thẳng sang Confirm tại (1425, 838).
        """
        action = self.flow.handle(State.CHAOS_EQUIPMENT, {}, self.real_screen)
        self.assertEqual(action.type, ActionType.TAP)
        self.assertEqual((action.x, action.y), (1425, 838))
        self.assertEqual(self.flow._equip_step, "WAIT_LEAVE_EQUIPMENT")
        self.assertIn(State.CHAOS_EQUIPMENT, action.extra.get("allowed_states", set()))



    # ── Test Ảnh Thật Ca Âm: Không nhận diện nhầm các màn khác thành EQUIPMENT ──
    def test_negative_fixture_images_not_ready_for_equipment(self):
        """
        [Mục 3 Test Ảnh Thật Ca Âm]
        Khẳng định _is_equip_screen_ready() trả False với mọi ảnh thật khác trong tests/fixtures/
        (map, battle, reward, safe_zone, fate, card_reward...).
        Đặc biệt: chaos_card_reward.png cũng chứa 'Avg. Sig. Card Cost' nhưng KHÔNG được nhận diện nhầm!
        """
        negative_fixtures = [
            "chaos_map_1_island.png",
            "chaos_continue.png",
            "chaos_reward_leave.png",
            "chaos_safe_zone.png",
            "chaos_choose_fate.png",
            "chaos_card_reward.png",
            "chaos_choose_epiphany.png",
            "chaos_memory_obtained.png",
            "chaos_remove_card.png",
        ]
        fixtures_dir = os.path.join("tests", "fixtures")
        for fname in negative_fixtures:
            fpath = os.path.join(fixtures_dir, fname)
            if not os.path.exists(fpath):
                continue
            img = cv2.imread(fpath)
            self.assertIsNotNone(img, f"Không thể đọc ảnh fixture {fname}")
            is_ready = self.flow._is_equip_screen_ready(img, {})
            self.assertFalse(
                is_ready,
                f"Ảnh fixture {fname} bị nhận diện nhầm thành màn hình CHAOS_EQUIPMENT ready!"
            )

    # ── Test Sub-step WAIT_LEAVE_EQUIPMENT sau khi bấm Confirm ──────────────
    def test_wait_leave_equipment_after_confirm(self):
        """
        [Mục 4 Test Sub-step Chờ Rời Màn Hình]
        Sau khi bấm Confirm:
        1. Sub-step chuyển sang 'WAIT_LEAVE_EQUIPMENT'.
        2. Nếu frame tiếp theo vẫn ở CHAOS_EQUIPMENT: bot KHÔNG tap lại Confirm mà chờ.
        3. Nếu quá MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS (4 lần): reset về IDLE + log cảnh báo.
        4. Nếu state rời sang CHAOS_MAP: sub-step được reset an toàn về IDLE.
        """
        from czn_bot.constants import MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS

        # 1. Bấm Confirm ban đầu
        act1 = self.flow.handle(State.CHAOS_EQUIPMENT, {}, self.real_screen)
        self.assertEqual(act1.type, ActionType.TAP)
        self.assertEqual(self.flow._equip_step, "WAIT_LEAVE_EQUIPMENT")

        # 2. Frame tiếp theo vẫn còn ở CHAOS_EQUIPMENT -> bot chờ, không tap lại
        act2 = self.flow.handle(State.CHAOS_EQUIPMENT, {}, self.real_screen)
        self.assertEqual(act2.type, ActionType.WAIT)
        self.assertEqual(self.flow._equip_step, "WAIT_LEAVE_EQUIPMENT")
        self.assertEqual(self.flow._equip_attempts, 1)

        # 3. Quá MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS -> reset an toàn về IDLE
        for i in range(MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS - 1):
            act_wait = self.flow.handle(State.CHAOS_EQUIPMENT, {}, self.real_screen)
            self.assertEqual(act_wait.type, ActionType.WAIT)

        # Lần thứ 4 đạt ngưỡng max -> reset
        self.assertEqual(self.flow._equip_step, "IDLE")

        # 4. Khi state chuyển sang CHAOS_MAP -> sub-step reset về IDLE ngay lập tức
        self.flow._equip_step = "WAIT_LEAVE_EQUIPMENT"
        self.flow.handle(State.CHAOS_MAP, {}, self.real_screen)
        self.assertEqual(self.flow._equip_step, "IDLE")

    # ── Test Đo Độ Trễ TemporalFilter sau TRANSITIONING ──────────────────────
    def test_temporal_filter_latency_after_transitioning(self):
        """
        [Mục 6 Test Đo Độ Trễ TemporalFilter]
        Đo: sau khi màn hình vừa chuyển từ TRANSITIONING sang ổn định,
        TemporalFilter mất bao nhiêu frame để is_settled() trả True cho state mới?
        Khẳng định:
        - is_settled(min_frames=1) đạt được ngay tại FRAME 1 (độ trễ ~300ms)
        - is_settled(min_frames=2) đạt được tại FRAME 2 (độ trễ ~600ms)
        - Đạt tiêu chuẩn <= 2 frame theo yêu cầu.
        """
        from czn_bot.vision.state_classifier import TemporalFilter
        tf = TemporalFilter(window=5, need=3)

        # Đang trong giai đoạn chuyển cảnh TRANSITIONING (3 frame)
        for _ in range(3):
            tf.push(State.CHAOS_MAP, is_unstable=True)
        self.assertEqual(tf.stable, "TRANSITIONING")
        self.assertFalse(tf.is_settled(1))

        # Frame 1: Màn hình đã ổn định với state mới CHAOS_MAP
        st1 = tf.push(State.CHAOS_MAP, is_unstable=False)
        self.assertEqual(st1, "CHAOS_MAP")
        self.assertTrue(tf.is_settled(1), "is_settled(1) phải True ngay tại Frame 1")
        self.assertFalse(tf.is_settled(2), "is_settled(2) cần thêm 1 frame")

        # Frame 2: Frame tiếp theo ổn định
        st2 = tf.push(State.CHAOS_MAP, is_unstable=False)
        self.assertEqual(st2, "CHAOS_MAP")
        self.assertTrue(tf.is_settled(2), "is_settled(2) phải True tại Frame 2")


if __name__ == "__main__":
    unittest.main()

