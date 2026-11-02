import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from czn_bot.states import State, Mode
from czn_bot.flows.base import Action, ActionType
from czn_bot.flows.chaos import ChaosFlow
from czn_bot.runner import BotRunner
from czn_bot.vision.map_reader import detect_3d_island_coords
from czn_bot.constants import (
    CHAOS_MAP_MIN_PIN_SCORE, STATE_SETTLING_FRAMES,
    MAX_EQUIP_SUBSTEP_ATTEMPTS, EQUIP_CHAR_ROWS,
    EQUIP_COMBATANTS_BOX
)


class TestChaosP0Guards(unittest.TestCase):
    def setUp(self):
        self.flow = ChaosFlow()
        self.mock_adb = MagicMock()
        self.runner = BotRunner(adb_client=self.mock_adb)
        self.runner.mode = Mode.CHAOS
        self.dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)

    # ── (a) Màn có Select combatant / Extract mới tap nhân vật ─────────────────
    def test_equip_does_not_tap_character_if_screen_not_ready(self):
        """Màn hình chưa xuất hiện 'Select combatant' hoặc 'Extract' -> bot không tap mù mà chờ."""
        details = {}
        # Màn hình đen, chưa sẵn sàng
        act1 = self.flow.handle(State.CHAOS_EQUIPMENT, details, self.dummy_screen)
        self.assertEqual(act1.type, ActionType.WAIT)
        self.assertEqual(self.flow._equip_step, "IDLE")
        self.assertEqual(self.flow._equip_attempts, 1)

        # Khi màn hình sẵn sàng và chọn đổi sang Hàng 2 (target_row=1)
        ready_details = {"select_combatant": True, "target_row": 1}
        act2 = self.flow.handle(State.CHAOS_EQUIPMENT, ready_details, self.dummy_screen)
        self.assertEqual(act2.type, ActionType.TAP)
        self.assertEqual((act2.x, act2.y), (1100, 470))  # Hàng 2
        self.assertEqual(self.flow._equip_step, "WAIT_ROW_SELECTED")
        self.assertIn(State.CHAOS_EQUIPMENT, act2.extra.get("allowed_states", set()))

    # ── (b) Chọn đúng hàng theo luật / Recommended ───────────────────────────
    def test_equip_selects_correct_row_by_rule_or_recommended(self):
        """[Test Giả Định / Dữ Liệu Mô Phỏng] Chọn đúng hàng: theo luật trang bị (Branch of Eternity -> Nia ở hàng 3) hoặc theo tag Recommended."""
        # Case 1: Theo luật trang bị (Branch of Eternity phù hợp Nia - index 2)
        rule_details = {
            "select_combatant": True,
            "equipment_name": "Branch of Eternity",
            "combatants": ["Rossweisse", "Tiphera", "Nia"]
        }
        self.flow._reset_equip_substep()
        act_rule = self.flow.handle(State.CHAOS_EQUIPMENT, rule_details, self.dummy_screen)
        self.assertEqual(act_rule.type, ActionType.TAP)
        self.assertEqual((act_rule.x, act_rule.y), (1100, 670))  # Hàng 3 (Nia)

        # Case 2: Theo nhãn Recommended (thẻ giữa có nhãn Recommended ở y~380)
        self.flow._reset_equip_substep()
        screen_with_rec = np.zeros((900, 1600, 3), dtype=np.uint8)
        # Giả lập viền cam ở Hàng 1 (đang selected) và nhãn Recommended ở Hàng 2
        screen_with_rec[200:300, 972:1000] = (20, 150, 255)  # Hàng 1 đang selected
        screen_with_rec[370:400, 1340:1500] = (20, 150, 255)  # Nhãn Recommended ở đỉnh Hàng 2 (top 383)
        rec_details = {"select_combatant": True}
        act_rec = self.flow.handle(State.CHAOS_EQUIPMENT, rec_details, screen_with_rec)
        self.assertEqual(act_rec.type, ActionType.TAP)
        self.assertEqual((act_rec.x, act_rec.y), (1100, 470))  # Hàng 2

    # ── (c) Confirm chưa cam thì không tap ────────────────────────────────────
    def test_equip_does_not_tap_confirm_when_not_orange(self):
        """Bước 3: Nếu nút Confirm tại (1275, 805, 1577, 870) chưa sáng màu cam, hết attempts vẫn KHÔNG tap mà reset."""
        import time
        # Tiến vào bước WAIT_CONFIRM_BUTTON
        self.flow._equip_step = "WAIT_CONFIRM_BUTTON"
        self.flow._equip_confirm_coord = (1425, 838)
        self.flow._equip_step_time = time.time()
        self.flow._equip_attempts = 0

        # Màn hình xám/đen (tỷ lệ pixel cam = 0.0)
        unlit_screen = np.full((900, 1600, 3), 50, dtype=np.uint8)
        details = {}

        for i in range(MAX_EQUIP_SUBSTEP_ATTEMPTS - 1):
            act = self.flow.handle(State.CHAOS_EQUIPMENT, details, unlit_screen)
            self.assertEqual(act.type, ActionType.WAIT, f"Lần {i+1} không được tap khi chưa cam")
            self.assertEqual(self.flow._equip_step, "WAIT_CONFIRM_BUTTON")

        # Lần thử cuối cùng: quá số lần thử -> reset an toàn, KHÔNG tap
        final_act = self.flow.handle(State.CHAOS_EQUIPMENT, details, unlit_screen)
        self.assertEqual(final_act.type, ActionType.WAIT)
        self.assertEqual(self.flow._equip_step, "IDLE")

        # Khi nút Confirm thực sự sáng cam (tỷ lệ pixel cam >= 15%)
        self.flow._equip_step = "WAIT_CONFIRM_BUTTON"
        self.flow._equip_confirm_coord = (1425, 838)
        self.flow._equip_step_time = time.time()
        orange_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        # Tạo vùng nút confirm màu cam sáng: BGR (20, 150, 255)
        orange_screen[805:870, 1275:1577] = (20, 150, 255)
        act_orange = self.flow.handle(State.CHAOS_EQUIPMENT, {}, orange_screen)
        self.assertEqual(act_orange.type, ActionType.TAP)
        self.assertEqual((act_orange.x, act_orange.y), (1425, 838))
        self.assertEqual(self.flow._equip_step, "WAIT_LEAVE_EQUIPMENT")

    # ── Guard chặn nút Extract (912, 805, 1260, 870) ──────────────────────────
    def test_guard_blocks_extract_button_tap_unless_explicit(self):
        """Mọi tap rơi vào vùng nút Extract (912-1260, 805-870) đều bị chặn trừ khi có cờ explicit_extract=True."""
        self.runner.current_state = State.CHAOS_EQUIPMENT
        for _ in range(self.runner.temporal_filter.need + STATE_SETTLING_FRAMES):
            self.runner.temporal_filter.push(State.CHAOS_EQUIPMENT)

        # 1. Tap vào Extract box không có explicit_extract -> BỊ CHẶN
        with self.assertLogs("ChaosBot", level="WARNING") as log:
            res1 = self.runner._execute_tap(
                action_name="Accidental Extract Tap",
                x=1000,
                y=835,
                allowed_states={State.CHAOS_EQUIPMENT},
                action_extra={}
            )
        self.assertFalse(res1)
        self.mock_adb.tap.assert_not_called()
        self.assertTrue(any("TAP BLOCKED" in msg and "Extract" in msg for msg in log.output))

        # 2. Tap vào Extract box có cờ explicit_extract=True -> ĐƯỢC PHÉP
        res2 = self.runner._execute_tap(
            action_name="Explicit Extract Tap",
            x=1000,
            y=835,
            allowed_states={State.CHAOS_EQUIPMENT},
            action_extra={"explicit_extract": True}
        )
        self.assertTrue(res2)
        self.mock_adb.tap.assert_called_with(1000, 835)

    # ── (d) Tap vào vùng thẻ nhân vật bị chặn khi state ≠ CHAOS_EQUIPMENT ──────
    def test_guard_blocks_tap_in_combatant_box_when_state_not_chaos_equipment(self):
        """Vùng 3 thẻ nhân vật (972, 183, 1508, 758) bị chặn tap khi đang ở CHAOS_MAP."""
        self.runner.current_state = State.CHAOS_MAP
        for _ in range(self.runner.temporal_filter.need + STATE_SETTLING_FRAMES):
            self.runner.temporal_filter.push(State.CHAOS_MAP)

        # Tap vào tâm thẻ nhân vật Hàng 1 (1100, 270)
        with self.assertLogs("ChaosBot", level="WARNING") as log:
            res = self.runner._execute_tap(
                action_name="Equip Select Combatant Row 1",
                x=1100,
                y=270,
                allowed_states={State.CHAOS_EQUIPMENT}
            )

        self.assertFalse(res)
        self.mock_adb.tap.assert_not_called()
        self.assertTrue(any("TAP BLOCKED" in msg and "CHAOS_EQUIPMENT" in msg for msg in log.output))

        # Thử tap vào vùng box (1100, 470) mà không truyền allowed_states
        with self.assertLogs("ChaosBot", level="WARNING") as log:
            res2 = self.runner._execute_tap(
                action_name="Generic Tap inside Combatant Box",
                x=1100,
                y=470,
                allowed_states=None
            )

        self.assertFalse(res2)
        self.mock_adb.tap.assert_not_called()
        self.assertTrue(any("TAP BLOCKED" in msg and "box đảo" in msg or "CHAOS_EQUIPMENT" in msg for msg in log.output))

    # ── Hủy chuỗi khi State rời khỏi EQUIPMENT ────────────────────────────────
    def test_equip_substep_cancelled_when_state_leaves_equipment(self):
        """Nếu state đột ngột rời khỏi CHAOS_EQUIPMENT giữa chừng, sub-step lập tức bị hủy."""
        details = {"select_combatant": True, "target_row": 1}

        # Bắt đầu vào EQUIPMENT
        self.flow.handle(State.CHAOS_EQUIPMENT, details, self.dummy_screen)
        self.assertEqual(self.flow._equip_step, "WAIT_ROW_SELECTED")

        # State chuyển sang CHAOS_SAFE_ZONE
        self.flow.handle(State.CHAOS_SAFE_ZONE, {}, self.dummy_screen)

        # Kiểm tra máy trạng thái con của equip đã được reset an toàn
        self.assertEqual(self.flow._equip_step, "IDLE")
        self.assertIsNone(self.flow._equip_last_screen)
        self.assertEqual(self.flow._equip_attempts, 0)

    # ── Guard chặn tap đảo khi state ≠ CHAOS_MAP ──────────────────────────────
    def test_guard_blocks_island_tap_when_state_not_chaos_map(self):
        """Guard chặn tap đảo nếu state hiện tại là CHAOS_EQUIPMENT."""
        self.runner.current_state = State.CHAOS_EQUIPMENT
        for _ in range(self.runner.temporal_filter.need + STATE_SETTLING_FRAMES):
            self.runner.temporal_filter.push(State.CHAOS_EQUIPMENT)

        with self.assertLogs("ChaosBot", level="WARNING") as log:
            res = self.runner._execute_tap(
                action_name="Chose Island 1: Battle",
                x=1280,
                y=520,
                allowed_states={State.CHAOS_MAP}
            )

        self.assertFalse(res)
        self.mock_adb.tap.assert_not_called()
        self.assertTrue(any("TAP BLOCKED" in msg and "CHAOS_MAP" in msg for msg in log.output))

    # ── detect_3d_island_coords guards ────────────────────────────────────────
    def test_detect_3d_islands_blocked_when_equipment_title_present(self):
        """detect_3d_island_coords trả về rỗng ngay lập tức khi phát hiện equipment_title."""
        coords = detect_3d_island_coords(
            screen=self.dummy_screen,
            has_equipment_title=True
        )
        self.assertEqual(coords, {})

    def test_detect_3d_islands_blocked_when_pin_score_low(self):
        """detect_3d_island_coords trả về rỗng khi minimap pin_score < 0.80."""
        coords = detect_3d_island_coords(
            screen=self.dummy_screen,
            pin_score=0.72  # < 0.80 threshold
        )
        self.assertEqual(coords, {})

    def test_detect_3d_islands_blocked_when_state_not_chaos_map(self):
        """detect_3d_island_coords trả về rỗng khi state != CHAOS_MAP."""
        coords = detect_3d_island_coords(
            screen=self.dummy_screen,
            state=State.CHAOS_EQUIPMENT
        )
        self.assertEqual(coords, {})

    # ── Guard chặn tap nhạy cảm khi màn hình đang chuyển cảnh ──────────────────
    def test_guard_blocks_tap_when_screen_is_transitioning(self):
        """Nếu TemporalFilter đang ở trạng thái TRANSITIONING, chặn tap nhạy cảm."""
        self.runner.current_state = State.CHAOS_MAP
        self.runner.temporal_filter.push(State.CHAOS_MAP, is_unstable=True)

        res = self.runner._execute_tap(
            action_name="Chose Island 1: Battle",
            x=1280,
            y=520,
            allowed_states={State.CHAOS_MAP}
        )
        self.assertFalse(res)
        self.mock_adb.tap.assert_not_called()

    # ── Box đảo không có allowed_states bị chặn nếu state ≠ CHAOS_MAP ─────────
    def test_island_box_tap_without_allowed_states_blocked_when_not_chaos_map(self):
        """Nếu tap rơi vào box đảo (680, 80, 1480, 780) mà thiếu allowed_states và keyword, state ≠ CHAOS_MAP thì bị chặn."""
        self.runner.current_state = State.CHAOS_EQUIPMENT
        for _ in range(self.runner.temporal_filter.need + STATE_SETTLING_FRAMES):
            self.runner.temporal_filter.push(State.CHAOS_EQUIPMENT)

        with self.assertLogs("ChaosBot", level="WARNING") as log:
            res = self.runner._execute_tap(
                action_name="Generic Tap (1280, 520)",
                x=1280,
                y=520,
                allowed_states=None
            )

        self.assertFalse(res)
        self.mock_adb.tap.assert_not_called()
        self.assertTrue(any("TAP BLOCKED" in msg and "box đảo" in msg for msg in log.output))



    # ── Test Bảng: Mọi tap hợp lệ thật của các state Chaos đều pass Guard ────
    def test_all_chaos_states_valid_taps_pass_guard(self):
        """
        [Mục 1 Test Bảng - Không mock state]
        Với mỗi state Chaos (EVENT, CHOOSE_FATE, CHOOSE_EPIPHANY, card_reward, SAFE_ZONE,
        OBTAIN_REWARD, AFTER_BATTLE, MAP, EQUIPMENT), lấy các tap hợp lệ thật của state đó
        (từ flows/chaos.py, runner.py, TAP_COORDS) và khẳng định _check_tap_guards() cho phép (trả True).
        """
        from czn_bot.coords import TAP_COORDS
        table_cases = [
            # State, action_name, (x, y), extra
            (State.CHAOS_MAP, "Chose Island 1: Battle", TAP_COORDS.get("chaos_island_1_middle", (1280, 520)), {"allowed_states": {State.CHAOS_MAP}}),
            (State.CHAOS_MAP, "Chose Island 2: Top", TAP_COORDS.get("chaos_island_2_top", (1100, 320)), {"allowed_states": {State.CHAOS_MAP}}),
            (State.CHAOS_EQUIPMENT, "Equip Select Combatant Row 1", (1100, 270), {"allowed_states": {State.CHAOS_EQUIPMENT}}),
            (State.CHAOS_EQUIPMENT, "Equip Select Combatant Row 2", (1100, 470), {"allowed_states": {State.CHAOS_EQUIPMENT}}),
            (State.CHAOS_EQUIPMENT, "Equip Confirm", (1425, 838), {"allowed_states": {State.CHAOS_EQUIPMENT}}),
            (State.CHAOS_SAFE_ZONE, "Safe Zone Rest", TAP_COORDS.get("chaos_safe_zone_rest", (455, 690)), {"allowed_states": {State.CHAOS_SAFE_ZONE}}),
            (State.CHAOS_SAFE_ZONE, "Safe Zone Confirm Rest (Modal Open)", TAP_COORDS.get("chaos_safe_zone_confirm", (1055, 642)), {"allowed_states": {State.CHAOS_SAFE_ZONE}}),
            (State.CHAOS_SAFE_ZONE, "Safe Zone Skip", TAP_COORDS.get("chaos_safe_zone_skip", (1415, 825)), {"allowed_states": {State.CHAOS_SAFE_ZONE}}),
            (State.CHAOS_EVENT, "Event Choice 1", (800, 360), {"allowed_states": {State.CHAOS_EVENT}}),
            (State.CHAOS_EVENT, "Event Choice Option 2", (1100, 450), {"allowed_states": {State.CHAOS_EVENT}}),
            (State.CHAOS_CHOOSE_FATE, "Fate Option Middle", (800, 450), {"allowed_states": {State.CHAOS_CHOOSE_FATE}}),
            (State.CHAOS_CHOOSE_EPIPHANY, "Epiphany Option Middle", (800, 450), {"allowed_states": {State.CHAOS_CHOOSE_EPIPHANY}}),
            # Card reward falls under CHAOS_CHOOSE_EPIPHANY in State enum
            (State.CHAOS_CHOOSE_EPIPHANY, "Card Reward Middle", (800, 450), {"allowed_states": {State.CHAOS_CHOOSE_EPIPHANY}}),
            (State.CHAOS_OBTAIN_REWARD, "Chaos Obtain Reward", TAP_COORDS.get("chaos_obtain_button", (800, 800)), {"allowed_states": {State.CHAOS_OBTAIN_REWARD}}),
            (State.CHAOS_AFTER_BATTLE, "Chaos Battle Continue", TAP_COORDS.get("chaos_continue_button", (1350, 830)), {"allowed_states": {State.CHAOS_AFTER_BATTLE}}),
        ]

        for state, act_name, (tx, ty), extra in table_cases:
            # Thiết lập state hiện tại thật của runner (không mock hàm check_tap_guards)
            self.runner.current_state = state
            self.runner.temporal_filter.reset()
            for _ in range(self.runner.temporal_filter.need + STATE_SETTLING_FRAMES):
                self.runner.temporal_filter.push(state)

            allowed_states = extra.get("allowed_states")
            is_ok, reason = self.runner._check_tap_guards(
                action_name=act_name,
                x=tx,
                y=ty,
                allowed_states=allowed_states,
                action_extra=extra,
            )
            self.assertTrue(
                is_ok,
                f"Tap hợp lệ của state {state.value} bị chặn oan: action={act_name}, pos=({tx}, {ty}), reason={reason}"
            )

    # ── Test Bảng: Flow tự động gán allowed_states cho mọi Action sinh ra ─────
    def test_flow_handle_auto_injects_allowed_states(self):
        """Khẳng định mọi Action.tap sinh ra từ ChaosFlow.handle() đều tự động có allowed_states = {state}."""
        test_states = [
            (State.CHAOS_MAP, {"roots": {"TOP": None}}),
            (State.CHAOS_SAFE_ZONE, {"has_rest_btn": True}),
            (State.CHAOS_EVENT, {"choices": [MagicMock(tap_coord=(1000, 400))]}),
            (State.CHAOS_OBTAIN_REWARD, {}),
            (State.CHAOS_AFTER_BATTLE, {}),
        ]
        for st, details in test_states:
            action = self.flow.handle(st, details, self.dummy_screen)
            if action.type == ActionType.TAP:
                self.assertIsNotNone(action.extra, f"Action của state {st} phải có extra")
                self.assertIn("allowed_states", action.extra, f"Action của state {st} phải tự động có allowed_states")
                self.assertIn(st, action.extra["allowed_states"], f"allowed_states phải chứa {st}")


if __name__ == "__main__":
    unittest.main()
