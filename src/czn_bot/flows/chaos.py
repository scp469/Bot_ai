"""
Chaos Mode Flow (Chế độ Chaos).
Autonomous decision-making for Chaos Mode:
- DAG Mini-map pathfinding (normal/elite/rest/boss) with survival & balanced strategies
- Auto card selection (Epiphany & Card Rewards) with AI and Heuristic fallback
- Auto equipment selection (Tier S > A > B) matching 27 Swamp of Judgment items
- Safe Zone Campfire: ALWAYS chooses Rest (Heal team), never skips
- Auto-skips dialogues and events during Chaos progression
"""
import os
import re
from typing import Optional, Dict, Any, List, Tuple
import logging
import cv2
import numpy as np

from czn_bot.states import State
from czn_bot.coords import TAP_COORDS
from czn_bot.flows.base import Flow, Action, ActionType
from czn_bot.chaos.pathfinder import (
    select_best_island,
    IslandChoice,
    get_strategy_profile,
)
from czn_bot.vision.hp_reader import get_team_hp
from czn_bot.vision.map_reader import parse_chaos_minimap, detect_3d_island_coords
from czn_bot.chaos.rules import ChaosRuleManager
from czn_bot.chaos.decisions import ChaosVision, ResourceInfo
from czn_bot.chaos.ai_brain import ChaosAIBrain

logger = logging.getLogger("ChaosBot.ChaosFlow")


class ChaosFlow(Flow):
    def __init__(
        self,
        strategy: str = "balanced",
        auto_pick_epiphany: bool = True,
        enable_dynamic_islands: bool = True,
        rule_manager: Optional[ChaosRuleManager] = None,
        ai_brain: Optional[ChaosAIBrain] = None,
        vision: Optional[ChaosVision] = None,
        max_matches: Optional[int] = None,
        max_map_retries: int = 5,
        active_character: str = "Rossweisse",
        team_characters: Optional[List[str]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.strategy = strategy
        self.auto_pick_epiphany = auto_pick_epiphany
        self.enable_dynamic_islands = enable_dynamic_islands
        self.rule_manager = rule_manager or ChaosRuleManager()
        self.ai_brain = ai_brain or ChaosAIBrain(rule_manager=self.rule_manager)
        self.vision = vision or ChaosVision(rule_manager=self.rule_manager)
        self.max_matches = max_matches
        self.matches_completed = 0
        self.max_map_retries = max_map_retries
        self._minimap_retry_count = 0
        self._map_tap_attempts = 0
        self.active_character = active_character
        if team_characters:
            self.team_characters = list(team_characters)
        elif hasattr(self.rule_manager, "get_team_characters"):
            self.team_characters = self.rule_manager.get_team_characters()
        else:
            self.team_characters = ["Rossweisse", "Tiphera", "Nia"]

        # Initialize starter decks in DeckState if available
        if hasattr(self.ai_brain, "deck_evaluator") and getattr(self.ai_brain.deck_evaluator, "deck_state", None):
            self.ai_brain.deck_evaluator.deck_state.initialize_default_team(
                self.team_characters,
                card_rules=getattr(self.rule_manager, "card_rules", None)
            )

        # Reactive equipment selection sub-step state
        self._equip_step: str = "IDLE"  # "IDLE", "WAIT_CHARACTER_PICKER", "WAIT_CONFIRM_BUTTON"
        self._equip_last_screen: Optional[np.ndarray] = None
        self._equip_step_time: float = 0.0
        self._equip_attempts: int = 0
        self._equip_chosen_name: str = ""
        self._equip_confirm_coord: Tuple[int, int] = (1360, 806)

        # Reactive obtain reward tracking
        self._obtain_last_count: Optional[int] = None
        self._obtain_same_count_taps: int = 0
        self._obtain_total_taps: int = 0

    def _reset_equip_substep(self) -> None:
        self._equip_step = "IDLE"
        self._equip_last_screen = None
        self._equip_step_time = 0.0
        self._equip_attempts = 0
        self._equip_chosen_name = ""

    def _is_equip_screen_ready(self, screen: Optional[np.ndarray], details: Dict[str, Any]) -> bool:
        """
        Xác nhận màn hình CHAOS_EQUIPMENT đã sẵn sàng chọn nhân vật:
        - Template equip_select_combatant trong (1365, 105, 1575, 138)
        - HOẶC Template equip_extract_button trong (912, 805, 1260, 870)
        - HOẶC nhãn "Avg. Sig. Card Cost" trong (110, 820, 360, 855)
        - HOẶC OCR thấy "Select combatant" hoặc "Extract"
        - HOẶC details báo sẵn sàng (khi test mock)
        """
        if details.get("select_combatant") or details.get("extract_button") or details.get("is_screen_ready"):
            return True

        if screen is None or getattr(screen, "size", 0) == 0:
            return False

        from czn_bot.constants import DATA_TEMPLATES_DIR, TEMPLATES_DIR, EQUIP_AVG_SIG_COST_ROI
        h, w = screen.shape[:2]

        # 1. Template matching equip_select_combatant (1365, 105, 1575, 138)
        # TODO: User cung cấp template equip_select_combatant.png
        for d in [DATA_TEMPLATES_DIR, TEMPLATES_DIR]:
            tpl_path = os.path.join(d, "equip_select_combatant.png")
            if os.path.exists(tpl_path):
                pt = self.vision.find_button(screen, "equip_select_combatant", threshold=0.75)
                if pt is not None:
                    return True

        # Fallback OCR cho dòng "Select combatant." (1365, 105, 1575, 138)
        if 138 <= h and 1575 <= w:
            crop_sel = screen[105:138, 1365:1575]
            if hasattr(self.vision, "ocr") and hasattr(self.vision.ocr, "read_text"):
                txt_sel = self.vision.ocr.read_text(crop_sel).lower()
                if "select" in txt_sel or "combatant" in txt_sel:
                    return True

        # 2. Template matching equip_extract_button (912, 805, 1260, 870)
        # TODO: User cung cấp template equip_extract_button.png
        for d in [DATA_TEMPLATES_DIR, TEMPLATES_DIR]:
            tpl_path = os.path.join(d, "equip_extract_button.png")
            if os.path.exists(tpl_path):
                pt = self.vision.find_button(screen, "equip_extract_button", threshold=0.75)
                if pt is not None:
                    return True

        # Fallback OCR hoặc màu đỏ cho nút Extract (912, 805, 1260, 870)
        if 870 <= h and 1260 <= w:
            crop_ext = screen[805:870, 912:1260]
            if hasattr(self.vision, "ocr") and hasattr(self.vision.ocr, "read_text"):
                txt_ext = self.vision.ocr.read_text(crop_ext).lower()
                if "extract" in txt_ext:
                    return True
            # Heuristic màu đỏ nút Extract (HSV: H < 10 hoặc H > 170, S >= 100, V >= 80)
            hsv = cv2.cvtColor(crop_ext, cv2.COLOR_BGR2HSV)
            mask_r1 = cv2.inRange(hsv, np.array([0, 100, 80]), np.array([10, 255, 255]))
            mask_r2 = cv2.inRange(hsv, np.array([170, 100, 80]), np.array([180, 255, 255]))
            red_ratio = (np.count_nonzero(mask_r1) + np.count_nonzero(mask_r2)) / max(1, crop_ext.shape[0] * crop_ext.shape[1])
            if red_ratio >= 0.12:
                return True

        # 3. Lưu ý: Dấu hiệu "Avg. Sig. Card Cost" (110, 820, 360, 855) cũng xuất hiện tại màn hình
        # CARD_REWARD (chaos_card_reward.png), do đó KHÔNG được dùng làm điều kiện độc lập để kích hoạt
        # màn hình trang bị. Chỉ 'Select combatant.' và 'Extract' là 2 dấu hiệu phân biệt 100%.

        return False

    def _recognize_combatant_in_row(self, screen: Optional[np.ndarray], row_idx: int) -> Optional[str]:
        """
        Nhận diện nhân vật tại hàng row_idx (0, 1, 2) bằng so khớp template chân dung (portraits).
        Vùng thẻ: (972, top, 1508, top+175). Vùng chân dung trên thẻ: ~(980, top+10, 1120, top+160).
        LƯU Ý: Không dùng OCR tên nhân vật vì trên giao diện thực tế vùng này không chứa text tên nhân vật (OCR trả '').
        KHÔNG suy đoán từ thứ tự HUD/đội hình (thứ tự HUD ngược với thứ tự hàng).
        """
        if screen is None or getattr(screen, "size", 0) == 0:
            return None
        from czn_bot.constants import EQUIP_COMBATANT_CARD_TOPS, DATA_TEMPLATES_DIR, TEMPLATES_DIR
        top = EQUIP_COMBATANT_CARD_TOPS[row_idx]
        h, w = screen.shape[:2]
        if top + 175 > h or 1508 > w:
            return None

        # TODO: User cung cấp template chân dung nhân vật trong data/templates/portraits/<char_name>.png
        # Ví dụ: data/templates/portraits/rossweisse.png, data/templates/portraits/tiphera.png, data/templates/portraits/nia.png
        portraits_dirs = [
            os.path.join(DATA_TEMPLATES_DIR, "portraits"),
            os.path.join(TEMPLATES_DIR, "portraits"),
        ]
        card_crop = screen[top:top + 175, 975:1120]
        for p_dir in portraits_dirs:
            if os.path.exists(p_dir):
                for fname in os.listdir(p_dir):
                    if fname.endswith(".png"):
                        char_name = os.path.splitext(fname)[0]
                        tpl_path = os.path.join(p_dir, fname)
                        tpl = cv2.imread(tpl_path)
                        if tpl is not None and tpl.shape[0] <= card_crop.shape[0] and tpl.shape[1] <= card_crop.shape[1]:
                            res = cv2.matchTemplate(card_crop, tpl, cv2.TM_CCOEFF_NORMED)
                            _, max_val, _, _ = cv2.minMaxLoc(res)
                            if max_val >= 0.75:
                                logger.info(f"[ChaosFlow] Nhận diện chân dung Hàng {row_idx + 1}: {char_name} (score={max_val:.2f})")
                                return char_name.capitalize()
        return None

    def _resolve_target_combatant_row(self, screen: Optional[np.ndarray], details: Dict[str, Any]) -> Tuple[int, str]:
        """
        Xác định hàng thẻ combatant đích (0, 1, 2) theo thứ tự ưu tiên:
        1. Từ details (nếu có target_row)
        2. Nhận diện nhân vật từng hàng qua OCR/portrait đối chiếu equipment_rules (KHÔNG đoán từ HUD)
        3. Từ nhãn Recommended (thẻ có đỉnh gần nhất trong 183/383/583)
        4. Giữ hàng đang được chọn sẵn (có viền cam)
        """
        if "target_row" in details and 0 <= details["target_row"] <= 2:
            return details["target_row"], f"Details Explicit Row {details['target_row'] + 1}"

        # 1. Nhận diện nhân vật từng hàng trực tiếp từ màn hình (không suy từ HUD)
        row_characters = details.get("combatants") or [self._recognize_combatant_in_row(screen, idx) for idx in range(3)]
        equip_name = details.get("equipment_name")

        matched_eq = None
        if equip_name and self.rule_manager:
            matched_eq = self.rule_manager.match_equipment(equip_name) or self.rule_manager.equipment_rules.get(equip_name)
        elif not equip_name and screen is not None and getattr(screen, "size", 0) > 0:
            h, w = screen.shape[:2]
            if h >= 450 and w >= 600:
                crop_left = screen[150:450, 50:600]
                left_text = self.vision.ocr.read_text(crop_left) if hasattr(self.vision, "ocr") and hasattr(self.vision.ocr, "read_text") else ""
                if self.rule_manager:
                    matched_eq = self.rule_manager.match_equipment(left_text)

        if matched_eq:
            eq_name = matched_eq.get("name", equip_name or "Unknown")
            best_chars = matched_eq.get("best_characters", [])
            for idx, char_name in enumerate(row_characters):
                if char_name and any(bc.lower() in char_name.lower() or char_name.lower() in bc.lower() for bc in best_chars):
                    return idx, f"Rule Match: [{eq_name}] cho nhân vật {char_name} (Hàng {idx + 1})"

        # 2. Tìm nhãn Recommended (thẻ có đỉnh gần nhất: 183/383/583)
        rec_row = self._find_recommended_row(screen)
        if rec_row is not None:
            char_label = row_characters[rec_row] or "Unknown"
            return rec_row, f"Recommended Tag (Hàng {rec_row + 1}, nhân vật={char_label})"

        # 3. Giữ hàng đang được chọn sẵn
        curr_row = self._detect_selected_combatant_row(screen)
        char_label = row_characters[curr_row] or "Unknown"
        return curr_row, f"Current Selected Row {curr_row + 1} (nhân vật={char_label})"

    def _find_recommended_row(self, screen: Optional[np.ndarray]) -> Optional[int]:
        """
        Tìm nhãn Recommended: gán cho thẻ có đỉnh gần nhất (183/383/583, cộng offset nhãn ~+5).
        Vùng tìm kiếm: EQUIP_RECOMMENDED_SEARCH_ROI (1320, 160, 1525, 760).
        Vùng crop chuẩn trên thẻ giữa: EQUIP_RECOMMENDED_TAG_CROP (1330, 362, 1520, 394).
        """
        if screen is None or getattr(screen, "size", 0) == 0:
            return None
        from czn_bot.constants import (
            EQUIP_COMBATANT_CARD_TOPS, EQUIP_RECOMMENDED_LABEL_OFFSET_Y,
            EQUIP_RECOMMENDED_SEARCH_ROI, DATA_TEMPLATES_DIR, TEMPLATES_DIR
        )
        h, w = screen.shape[:2]
        if h < EQUIP_RECOMMENDED_SEARCH_ROI[3] or w < EQUIP_RECOMMENDED_SEARCH_ROI[2]:
            return None

        # 1. Template matching equip_recommended_tag nếu có
        # TODO: User cung cấp template equip_recommended_tag.png (crop ~(1330,362,1520,394))
        for d in [DATA_TEMPLATES_DIR, TEMPLATES_DIR]:
            tpl_path = os.path.join(d, "equip_recommended_tag.png")
            if os.path.exists(tpl_path):
                pt = self.vision.find_button(screen, "equip_recommended_tag", threshold=0.75)
                if pt is not None:
                    py = pt[1]
                    # Tìm thẻ có đỉnh gần nhất
                    return min(range(3), key=lambda idx: abs(py - (EQUIP_COMBATANT_CARD_TOPS[idx] + EQUIP_RECOMMENDED_LABEL_OFFSET_Y)))

        # 2. Fallback OCR tìm chữ "Recommend" trong vùng tìm kiếm (1320, 160, 1525, 760)
        crop_rec = screen[EQUIP_RECOMMENDED_SEARCH_ROI[1]:EQUIP_RECOMMENDED_SEARCH_ROI[3], EQUIP_RECOMMENDED_SEARCH_ROI[0]:EQUIP_RECOMMENDED_SEARCH_ROI[2]]
        if hasattr(self.vision, "ocr") and hasattr(self.vision.ocr, "find_text"):
            pt_ocr = self.vision.ocr.find_text(crop_rec, "Recommend")
            if pt_ocr is not None:
                py = EQUIP_RECOMMENDED_SEARCH_ROI[1] + pt_ocr[1]
                return min(range(3), key=lambda idx: abs(py - (EQUIP_COMBATANT_CARD_TOPS[idx] + EQUIP_RECOMMENDED_LABEL_OFFSET_Y)))

        # 3. Phân tích cụm pixel màu cam của nhãn Recommended tại từng thẻ
        # Đỉnh nhãn tại từng thẻ: top - 25 đến top + 25
        hsv_full = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
        orange_mask = cv2.inRange(hsv_full, np.array([8, 120, 120]), np.array([25, 255, 255]))
        counts = []
        for top in EQUIP_COMBATANT_CARD_TOPS:
            y1 = max(0, top - 25)
            y2 = min(h, top + 25)
            # Vùng nhãn nằm ở khoảng x: 1330 đến 1520
            sub_mask = orange_mask[y1:y2, 1330:1520]
            counts.append(int(np.count_nonzero(sub_mask)))

        max_idx = int(np.argmax(counts))
        if counts[max_idx] >= 20:
            return max_idx

        return None

    def _detect_selected_combatant_row(self, screen: Optional[np.ndarray]) -> int:
        """
        Xác định hàng combatant nào đang được chọn sẵn (viền cam) trong 3 thẻ bằng 2 tín hiệu:
        1. Viền trái (Left Border) x: 972-1015
        2. Thanh nối (Connecting Bar) x: 885-972
        Yêu cầu margin >= 150 & tỷ lệ >= 1.8x; nếu không thỏa fallback về hàng có nhãn Recommended với WARNING.
        """
        if screen is None or getattr(screen, "size", 0) == 0:
            return 0
        h, w = screen.shape[:2]
        if h < 770 or w < 1015:
            return 0

        hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
        orange_mask = cv2.inRange(hsv, np.array([8, 120, 120]), np.array([25, 255, 255]))

        y_ranges = [(170, 370), (370, 570), (570, 770)]
        scores = []
        for y1, y2 in y_ranges:
            border_px = int(np.count_nonzero(orange_mask[y1:y2, 972:1015]))
            conn_px = int(np.count_nonzero(orange_mask[y1:y2, 885:972]))
            total_signal = border_px + conn_px * 2
            scores.append(total_signal)

        sorted_indices = sorted(range(3), key=lambda i: scores[i], reverse=True)
        best_idx = sorted_indices[0]
        second_idx = sorted_indices[1]

        margin = scores[best_idx] - scores[second_idx]
        ratio = scores[best_idx] / max(1, scores[second_idx])

        if margin >= 150 and ratio >= 1.8:
            return best_idx

        logger.warning(
            f"[ChaosFlow] Tín hiệu viền cam không đủ cách biệt (best={best_idx}: {scores[best_idx]}, "
            f"second={second_idx}: {scores[second_idx]}, margin={margin} < 150 hoặc ratio={ratio:.2f} < 1.8). "
            f"Fallback về hàng có nhãn Recommended."
        )
        rec_row = self._find_recommended_row(screen)
        if rec_row is not None:
            return rec_row
        return best_idx

    def _check_confirm_button_orange(self, screen: Optional[np.ndarray], details: Dict[str, Any]) -> Tuple[bool, float]:
        """
        Kiểm tra nút Confirm tại ROI (1275, 805, 1577, 870) có sáng màu cam hay không.
        Trả về (is_orange, ratio). Ngưỡng tối thiểu là EQUIP_CONFIRM_ORANGE_THRESHOLD (0.15).
        """
        from czn_bot.constants import EQUIP_CONFIRM_ORANGE_THRESHOLD, DATA_TEMPLATES_DIR, TEMPLATES_DIR

        if "is_confirm_ready" in details:
            ready = bool(details["is_confirm_ready"])
            return ready, (1.0 if ready else 0.0)

        if screen is None or getattr(screen, "size", 0) == 0:
            return False, 0.0

        h, w = screen.shape[:2]
        if h < 870 or w < 1577:
            return False, 0.0

        # Template matching equip_confirm_ready nếu có
        # TODO: User cung cấp template equip_confirm_ready.png và equip_confirm_disabled.png
        for d in [DATA_TEMPLATES_DIR, TEMPLATES_DIR]:
            tpl_path = os.path.join(d, "equip_confirm_ready.png")
            if os.path.exists(tpl_path):
                pt = self.vision.find_button(screen, "equip_confirm_ready", threshold=0.75)
                if pt is not None:
                    return True, 1.0

        crop = screen[805:870, 1275:1577]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([8, 120, 120]), np.array([25, 255, 255]))
        orange_pixels = int(np.count_nonzero(mask))
        total_pixels = crop.shape[0] * crop.shape[1]
        ratio = orange_pixels / max(1, total_pixels)
        return ratio >= EQUIP_CONFIRM_ORANGE_THRESHOLD, ratio

    def _resolve_island_static_coord(
        self,
        island: IslandChoice,
        num_roots: int,
        available_islands: Optional[set] = None
    ) -> Tuple[Tuple[int, int], str]:
        available = available_islands or set()
        if num_roots == 1:
            return TAP_COORDS["chaos_island_1_middle"], "Đảo Duy Nhất"
        if num_roots == 2:
            if IslandChoice.TOP in available and IslandChoice.MIDDLE in available:
                if island == IslandChoice.TOP:
                    return TAP_COORDS["chaos_island_2_top"], "Đảo Trên"
                return TAP_COORDS["chaos_island_2_middle"], "Đảo Giữa"
            elif IslandChoice.MIDDLE in available and IslandChoice.BOTTOM in available:
                if island == IslandChoice.MIDDLE:
                    return TAP_COORDS["chaos_island_2_middle"], "Đảo Giữa"
                return TAP_COORDS["chaos_island_2_bottom"], "Đảo Dưới"
            else:
                if island == IslandChoice.TOP:
                    return TAP_COORDS["chaos_island_2_top"], "Đảo Trên"
                return TAP_COORDS["chaos_island_2_bottom"], "Đảo Dưới"
        # Default 3 islands
        if island == IslandChoice.TOP:
            return TAP_COORDS["chaos_island_3_top"], "Đảo Trên"
        elif island == IslandChoice.BOTTOM:
            return TAP_COORDS["chaos_island_3_bottom"], "Đảo Dưới"
        return TAP_COORDS["chaos_island_3_middle"], "Đảo Giữa"

    def handle(self, state: State, details: Dict[str, Any], screen: Optional[np.ndarray]) -> Action:
        action = self._handle_flow(state, details, screen)
        # P0 Guard: Tự động gán allowed_states cho mọi Action.tap sinh ra từ Flow
        if action and action.type == ActionType.TAP:
            if action.extra is None:
                action.extra = {}
            if "allowed_states" not in action.extra or not action.extra["allowed_states"]:
                action.extra["allowed_states"] = {state}
            # Preserve extra_actions cleanly without altering tuple shape
        return action

    def _handle_flow(self, state: State, details: Dict[str, Any], screen: Optional[np.ndarray]) -> Action:
        # Reset equipment sub-step if state switched away from CHAOS_EQUIPMENT
        if state != State.CHAOS_EQUIPMENT and getattr(self, "_equip_step", "IDLE") != "IDLE":
            logger.info(
                f"[ChaosFlow] Rời màn hình CHAOS_EQUIPMENT (chuyển sang {state.value}) -> Hủy chuỗi gán trang bị (Reset sub-step về IDLE)"
            )
            self._reset_equip_substep()

        # Reset obtain tracking if state switched away from CHAOS_OBTAIN_REWARD
        if state != State.CHAOS_OBTAIN_REWARD and (self._obtain_total_taps > 0 or self._obtain_last_count is not None):
            self._obtain_last_count = None
            self._obtain_same_count_taps = 0
            self._obtain_total_taps = 0

        if state == State.IN_MATCH:
            return Action.none(name="In Match (waiting for battle completion)")

        # 1. CHAOS_MAP: Mini-map DAG pathfinding & 3D island detection
        if state == State.CHAOS_MAP:
            if screen is None or screen.size == 0:
                return Action.none(name="Chaos Map: Waiting for valid frame")

            hp_percent, is_low_hp = get_team_hp(screen)
            roots, adj, nodes, boss_ids = parse_chaos_minimap(screen)

            # Item 1: Khi camera đang lia hoặc minimap đang chuyển cảnh, chờ 3-5 khung (thay vì dừng bot ngay)
            if not roots:
                self._minimap_retry_count = getattr(self, "_minimap_retry_count", 0) + 1
                if self._minimap_retry_count < self.max_map_retries:
                    return Action.wait(1.0, name=f"Chờ minimap ổn định ({self._minimap_retry_count}/{self.max_map_retries})")
                self._minimap_retry_count = 0
                return Action.stop(reason=f"Không thể phân tích minimap đường đi Chaos sau {self.max_map_retries} lần thử")

            self._minimap_retry_count = 0

            # Item 7: Kiểm soát số lần thử tap liên tiếp trên bản đồ
            self._map_tap_attempts = getattr(self, "_map_tap_attempts", 0) + 1
            if self._map_tap_attempts > 2:
                # Chờ màn hình ổn định rồi mới nhận diện lại, tuyệt đối không trừ 40px bừa bãi
                self._map_tap_attempts = 0
                return Action.wait(1.5, name="Chờ camera/màn hình bản đồ ổn định rồi nhận diện lại")

            best_island, evaluations = select_best_island(
                roots, adj, nodes, boss_ids, hp_percent, strategy=self.strategy
            )

            if best_island is None:
                if roots and len(roots) == 1:
                    best_island = list(roots.keys())[0]
                else:
                    return Action.stop(reason="Không tìm thấy nhánh đường an toàn đến Boss")

            # AI decision override if available
            if self.rule_manager.get_api_key():
                try:
                    res_info = ResourceInfo(hp_percent=hp_percent, is_low_hp=is_low_hp, credits=0)
                    ai_decision = self.ai_brain.decide_island(evaluations, res_info, strategy_mode=self.strategy)
                    if ai_decision and "target_island" in ai_decision:
                        t_str = str(ai_decision["target_island"]).lower()
                        for cand in roots.keys():
                            if cand.value.lower() == t_str:
                                best_island = cand
                                break
                except Exception as e:
                    logger.debug(f"AI decide island error: {e}")

            # Guard kiểm tra độ tin cậy của minimap/ghim và không thấy equipment_title
            from czn_bot.constants import CHAOS_MAP_MIN_PIN_SCORE
            score_pin = float(details.get("score_pin", details.get("evidence", {}).get("chaos_node_pin", details.get("score", 1.0))))
            has_eq = details.get("evidence", {}).get("equipment_title", 0.0) >= 0.65

            if score_pin < CHAOS_MAP_MIN_PIN_SCORE or has_eq:
                logger.warning(
                    f"[ChaosFlow] Guard chặn chọn lối đi đảo: pin_score={score_pin:.2f} (cần >={CHAOS_MAP_MIN_PIN_SCORE}), "
                    f"has_equipment_title={has_eq} -> KHÔNG tap fallback bừa bãi, chờ frame ổn định!"
                )
                return Action.wait(1.0, name="Chờ bản đồ Chaos và vị trí ghim hợp lệ (>0.80)")

            static_coord, name = self._resolve_island_static_coord(
                best_island, len(roots), available_islands=set(roots.keys()) if isinstance(roots, dict) else set(roots)
            )
            target_coord = static_coord

            # Item 7: Ưu tiên nhận diện 3D đảo thực tế
            if self.enable_dynamic_islands:
                try:
                    dyn_coords = detect_3d_island_coords(
                        screen,
                        expected_choices=list(roots.keys()) if isinstance(roots, dict) else list(roots),
                        pin_score=score_pin,
                        has_equipment_title=has_eq,
                        state=state
                    )
                    if best_island in dyn_coords:
                        target_coord = dyn_coords[best_island]
                except Exception as e:
                    logger.debug(f"Dynamic 3D island detection error: {e}")

            best_eval = evaluations.get(best_island)
            score = best_eval.best_score if (best_eval and best_eval.best_score != float("-inf")) else 0.0

            return Action.tap(
                target_coord[0], target_coord[1],
                name=f"Select {name} ({best_island.value})",
                island=best_island.value,
                score=score,
                hp_percent=hp_percent,
                extra={"allowed_states": {State.CHAOS_MAP}}
            )

        # 2. CHAOS_AFTER_BATTLE: Click Leave button
        if state == State.CHAOS_AFTER_BATTLE:
            if self.max_matches is not None and self.matches_completed >= self.max_matches:
                return Action.stop(reason=f"Đã đạt giới hạn số trận Chaos ({self.max_matches})", max_stages=True)

            self.matches_completed += 1
            leave_coord = details.get("leave_coord") or TAP_COORDS["chaos_leave_button"]
            score = details.get("score", 0.95)
            return Action.tap(
                *leave_coord,
                name="Chaos Leave Button",
                stage_number=self.matches_completed,
                score=score,
                expected_words=["leave", "rời", "thoát", "continue", "tiếp", "confirm", "settlement"]
            )

        # 3. CHAOS_EQUIPMENT: Autonomous reactive equipment selection
        if state == State.CHAOS_EQUIPMENT:
            import time
            from czn_bot.vision.state_classifier import screen_changed
            from czn_bot.constants import (
                EQUIP_SUBSTEP_TIMEOUT, MAX_EQUIP_SUBSTEP_ATTEMPTS,
                EQUIP_CHAR_ROWS, EQUIP_CONFIRM_COORD, EQUIP_CONFIRM_ORANGE_THRESHOLD
            )

            now = time.time()

            # Kiểm tra timeout cho sub-step hiện tại
            if self._equip_step != "IDLE":
                if (now - self._equip_step_time) > EQUIP_SUBSTEP_TIMEOUT or self._equip_attempts > MAX_EQUIP_SUBSTEP_ATTEMPTS:
                    logger.warning(
                        f"[ChaosFlow] Timeout/quá số lần thử ở sub-step '{self._equip_step}' ({self._equip_attempts}/{MAX_EQUIP_SUBSTEP_ATTEMPTS}, "
                        f"{now - self._equip_step_time:.1f}s) -> Thoát an toàn, hủy chuỗi gán trang bị"
                    )
                    self._reset_equip_substep()
                    return Action.wait(0.5, name="Equip: Timeout sub-step -> Reset an toàn")

            # Bước 1 (IDLE): Xác nhận màn hình sẵn sàng chọn nhân vật
            if self._equip_step == "IDLE":
                is_ready = self._is_equip_screen_ready(screen, details)
                if not is_ready:
                    self._equip_attempts += 1
                    if self._equip_attempts >= MAX_EQUIP_SUBSTEP_ATTEMPTS:
                        logger.warning(
                            f"[ChaosFlow] Equip Bước 1: Màn hình chưa sẵn sàng sau {MAX_EQUIP_SUBSTEP_ATTEMPTS} lần thử "
                            f"(không thấy Select combatant hoặc Extract) -> Reset an toàn"
                        )
                        self._reset_equip_substep()
                        return Action.wait(0.5, name="Equip Safe Reset: Screen Not Ready")
                    logger.debug(f"[ChaosFlow] Equip Bước 1: Chờ màn hình sẵn sàng (Thử {self._equip_attempts}/{MAX_EQUIP_SUBSTEP_ATTEMPTS})")
                    return Action.wait(0.3, name="Equip: Chờ màn hình sẵn sàng")

                # Màn hình đã sẵn sàng -> Xác định hàng nhân vật cần chọn
                target_row, reason = self._resolve_target_combatant_row(screen, details)
                target_coord = EQUIP_CHAR_ROWS[target_row]
                self._equip_target_row = target_row
                self._equip_confirm_coord = details.get("confirm_coord") or EQUIP_CONFIRM_COORD
                self._equip_last_screen = screen.copy() if screen is not None and getattr(screen, "size", 0) > 0 else None
                self._equip_step_time = now
                self._equip_attempts = 0

                # Item 6: Nếu hàng đích đã đang được chọn: bỏ qua tap thẻ, chuyển thẳng sang Confirm
                current_selected = self._detect_selected_combatant_row(screen)
                if current_selected == target_row:
                    logger.info(
                        f"[ChaosFlow] Equip Bước 1: Hàng đích {target_row + 1} ({reason}) đã được chọn sẵn từ trước "
                        f"(viền cam) -> Bỏ qua tap thẻ, chuyển thẳng sang Confirm"
                    )
                    self._equip_step = "WAIT_CONFIRM_BUTTON"
                    # Kiểm tra xem nút Confirm đã sẵn sàng sáng cam chưa
                    is_orange, orange_ratio = self._check_confirm_button_orange(screen, details)
                    if is_orange:
                        confirm_coord = self._equip_confirm_coord or EQUIP_CONFIRM_COORD
                        logger.info(
                            f"[ChaosFlow] Equip Bước 1: Nút Confirm đã sáng cam (tỷ lệ {orange_ratio:.1%}) "
                            f"tại {confirm_coord} -> Bấm xác nhận trang bị"
                        )
                        from czn_bot.constants import MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS
                        self._equip_step = "WAIT_LEAVE_EQUIPMENT"
                        self._equip_attempts = 0
                        self._equip_step_time = now
                        return Action.tap(
                            confirm_coord[0], confirm_coord[1],
                            name="Equip Confirm",
                            extra={"allowed_states": {State.CHAOS_EQUIPMENT}}
                        )
                    return Action.wait(0.2, name="Equip: Chờ nút Confirm sáng cam")

                self._equip_step = "WAIT_ROW_SELECTED"
                logger.info(
                    f"[ChaosFlow] Equip Bước 1: Màn hình sẵn sàng -> Chạm chọn combatant Hàng {target_row + 1} "
                    f"tại {target_coord} ({reason})"
                )
                return Action.tap(
                    target_coord[0], target_coord[1],
                    name=f"Equip Select Combatant Row {target_row + 1}",
                    extra={"allowed_states": {State.CHAOS_EQUIPMENT}}
                )

            # Bước 2: Chờ xác nhận hàng được chọn đã đổi / đã chọn đúng hàng
            if self._equip_step == "WAIT_ROW_SELECTED":
                if screen is None or getattr(screen, "size", 0) == 0:
                    self._equip_attempts += 1
                    if self._equip_attempts >= MAX_EQUIP_SUBSTEP_ATTEMPTS:
                        logger.warning(f"[ChaosFlow] Equip Bước 2: Không nhận được frame hợp lệ -> Reset an toàn")
                        self._reset_equip_substep()
                        return Action.wait(0.5, name="Equip Safe Reset: Invalid Frame")
                    return Action.wait(0.3, name="Equip: Chờ frame hợp lệ")

                curr_row = self._detect_selected_combatant_row(screen)
                has_changed = screen_changed(self._equip_last_screen, screen, thresh=3.0) if self._equip_last_screen is not None else True
                row_matches = (curr_row == getattr(self, "_equip_target_row", 0))

                if row_matches or has_changed:
                    logger.info(
                        f"[ChaosFlow] Equip Bước 2: Đã xác nhận chọn Hàng {getattr(self, '_equip_target_row', 0) + 1} "
                        f"-> Chuyển sang chờ nút Confirm sáng"
                    )
                    self._equip_step = "WAIT_CONFIRM_BUTTON"
                    self._equip_step_time = now
                    self._equip_attempts = 0
                    self._equip_last_screen = screen.copy()
                    return Action.wait(0.2, name="Equip: Chờ nút Confirm sáng")

                self._equip_attempts += 1
                if self._equip_attempts >= MAX_EQUIP_SUBSTEP_ATTEMPTS:
                    logger.warning(
                        f"[ChaosFlow] Equip Bước 2: Quá {MAX_EQUIP_SUBSTEP_ATTEMPTS} lần thử mà hàng chưa đổi -> Reset an toàn"
                    )
                    self._reset_equip_substep()
                    return Action.wait(0.5, name="Equip Safe Reset: Row Not Changed")
                return Action.wait(0.3, name="Equip: Chờ hàng nhân vật đổi")

            # Bước 3: Chờ nút Confirm sáng màu cam rồi mới bấm
            if self._equip_step == "WAIT_CONFIRM_BUTTON":
                is_orange, orange_ratio = self._check_confirm_button_orange(screen, details)
                if is_orange:
                    confirm_coord = self._equip_confirm_coord or details.get("confirm_coord") or EQUIP_CONFIRM_COORD
                    logger.info(
                        f"[ChaosFlow] Equip Bước 3: Nút Confirm đã sáng màu cam (tỷ lệ {orange_ratio:.1%}) "
                        f"tại {confirm_coord} -> Bấm xác nhận trang bị"
                    )
                    from czn_bot.constants import MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS
                    self._equip_step = "WAIT_LEAVE_EQUIPMENT"
                    self._equip_attempts = 0
                    self._equip_step_time = now
                    return Action.tap(
                        confirm_coord[0], confirm_coord[1],
                        name="Equip Confirm",
                        extra={"allowed_states": {State.CHAOS_EQUIPMENT}}
                    )

                self._equip_attempts += 1
                if self._equip_attempts >= MAX_EQUIP_SUBSTEP_ATTEMPTS:
                    logger.warning(
                        f"[ChaosFlow] Equip Bước 3: Quá {MAX_EQUIP_SUBSTEP_ATTEMPTS} lần thử mà nút Confirm chưa sáng cam "
                        f"(tỷ lệ {orange_ratio:.1%} < {EQUIP_CONFIRM_ORANGE_THRESHOLD:.0%}) -> Hủy chuỗi an toàn, KHÔNG tap mù!"
                    )
                    self._reset_equip_substep()
                    return Action.wait(0.5, name="Equip Safe Reset: Confirm Button Not Ready")

                logger.debug(f"[ChaosFlow] Equip Bước 3: Chờ nút Confirm sáng cam (Thử {self._equip_attempts}/{MAX_EQUIP_SUBSTEP_ATTEMPTS})")
                return Action.wait(0.3, name="Equip: Chờ nút Confirm sáng cam")

            # Bước 4: Chờ màn hình rời khỏi CHAOS_EQUIPMENT sau khi bấm Confirm
            # TODO: Xử lý Popup phụ sau khi Confirm trang bị (ví dụ: "Thay thế trang bị cũ", "Xác nhận trang bị"):
            # Hiện tại game flow chưa có template cho popup này.
            # Nếu game của bạn xuất hiện popup này và bot dừng lại:
            # Hãy chụp ảnh màn hình kích thước 1600x900 và lưu vào:
            # data/templates/equip_replace_confirm.png hoặc tests/fixtures/chaos_equipment_replace_dialog.png
            if self._equip_step == "WAIT_LEAVE_EQUIPMENT":
                self._equip_attempts += 1
                from czn_bot.constants import MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS
                if self._equip_attempts >= MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS:
                    logger.warning(
                        f"[ChaosFlow] Equip Bước 4: Đã bấm Confirm nhưng màn hình vẫn ở CHAOS_EQUIPMENT sau "
                        f"{MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS} lần thử (~{MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS * 0.3:.1f}s). "
                        f"Reset sub-step về IDLE, KHÔNG tap lại để tránh lặp thao tác."
                    )
                    self._reset_equip_substep()
                    return Action.wait(0.5, name="Equip Confirm Timeout: Safe Reset to IDLE")
                logger.info(
                    f"[ChaosFlow] Equip Bước 4: Đang chờ màn hình rời khỏi CHAOS_EQUIPMENT sau khi bấm Confirm "
                    f"(Thử {self._equip_attempts}/{MAX_EQUIP_CONFIRM_WAIT_ATTEMPTS})"
                )
                return Action.wait(0.3, name="Equip: Chờ rời màn hình sau Confirm")

        # 4. CHAOS_SAFE_ZONE: Always select Rest (Heal team), NEVER skip when rest is available! (Item 4)
        if state == State.CHAOS_SAFE_ZONE:
            is_modal = details.get("is_modal_open", False)
            confirm_coord = details.get("confirm_coord") or TAP_COORDS.get("chaos_safe_zone_confirm", (1055, 642))
            rest_coord = details.get("rest_coord") or TAP_COORDS.get("chaos_safe_zone_rest", (455, 690))
            skip_coord = details.get("skip_coord") or TAP_COORDS.get("chaos_safe_zone_skip", (1415, 825))
            has_rest = details.get("has_rest_btn", False)
            score = details.get("score", 0.95)

            # Trường hợp 1: Popup Modal Rest đang mở (Ảnh 2) -> Bấm nút Confirm màu cam
            if is_modal:
                return Action.tap(
                    confirm_coord[0], confirm_coord[1],
                    name="Safe Zone Confirm Rest (Modal Open)",
                    score=score,
                    extra={"allowed_states": {State.CHAOS_SAFE_ZONE}},
                )

            # Trường hợp 2: Đang ở màn hình Camp (Ảnh 1) và còn nút Rest
            if has_rest or not details.get("interactions_exhausted", False):
                return Action.tap(
                    rest_coord[0], rest_coord[1],
                    name="Safe Zone Rest (Always Heal Team)",
                    score=score,
                    extra_actions=[
                        ("tap", confirm_coord),
                    ],
                    extra={"allowed_states": {State.CHAOS_SAFE_ZONE}},
                )

            # Trường hợp 3: Đã hồi phục xong / hết lượt Rest -> Bấm Skip
            return Action.tap(
                skip_coord[0], skip_coord[1],
                name="Safe Zone Skip (No Rest Available)",
                score=score,
                extra={"allowed_states": {State.CHAOS_SAFE_ZONE}},
            )

        # 4b. CHAOS_EVENT: Random Event Encounters (Poacher wager, dialog events, quizzes)
        if state == State.CHAOS_EVENT:
            choices = self.vision.extract_event_choices(screen) if screen is not None else []
            res = self.vision.extract_resources(screen) if screen is not None else ResourceInfo(1.0, False, 0)

            if choices:
                decision = self.ai_brain.decide_event(choices, res)
                target_idx = decision.get("target_index", 0)
                if target_idx < len(choices):
                    tap_coord = choices[target_idx].tap_coord
                    choice_name = choices[target_idx].name or f"Choice {target_idx + 1}"
                    choice_text = choices[target_idx].text
                    matched_ev = choices[target_idx].matched_event_name
                    score = choices[target_idx].priority_score
                else:
                    tap_coord = (795, 765)
                    choice_name = "Default Choice"
                    choice_text = ""
                    matched_ev = ""
                    score = 5
            else:
                tap_coord = (795, 765)
                choice_name = "Default Middle Choice"
                choice_text = ""
                matched_ev = ""
                score = 5

            # Game cơ chế: Muốn chọn event phải nhấn 2 lần vào ô lựa chọn
            # Lần 1: Action tap chính tại tap_coord
            # Lần 2: extra_actions đầu tiên chạm lại chính tap_coord để xác nhận
            extra_actions = [("tap", tap_coord)]

            if screen is not None:
                battle_btn = self.vision.find_action_button(screen, action_type="battle")
                if battle_btn and battle_btn != tap_coord:
                    extra_actions.append(("tap", battle_btn))
                else:
                    confirm_btn = self.vision.find_action_button(screen, action_type="confirm")
                    if confirm_btn and confirm_btn != tap_coord:
                        extra_actions.append(("tap", confirm_btn))

            return Action.tap(
                tap_coord[0], tap_coord[1],
                name=f"Event Choice (Double Tap): {choice_name} ({choice_text[:30]})" if choice_text else f"Event Choice (Double Tap): {choice_name}",
                score=score,
                extra_actions=extra_actions,
                extra={"matched_event": matched_ev, "choice_text": choice_text}
            )

        # 5. CHAOS_CHOOSE_EPIPHANY / CHAOS_CHOOSE_FATE: Auto pick card or event choice immediately (Item 3)
        if state in (State.CHAOS_CHOOSE_EPIPHANY, State.CHAOS_CHOOSE_FATE):
            if not self.auto_pick_epiphany:
                return Action.none(name="Card Selection (Manual Wait)")

            self._epiphany_wait_count = getattr(self, "_epiphany_wait_count", 0) + 1
            if self._epiphany_wait_count < 2:
                return Action.none(name="Wait for card animation to stabilize")

            self._epiphany_wait_count = 0
            epiphany_type = details.get("type") or details.get("epiphany_type", "epiphany")
            res = self.vision.extract_resources(screen) if screen is not None else ResourceInfo(1.0, False, 0)

            # Sub-screen 0: card_reward (1 card on left, assign to 1 of 3 combatants on right)
            if epiphany_type == "card_reward":
                card_info = self.vision.extract_single_card_reward(screen) if screen is not None else {"title": "Card Reward"}
                card_title = card_info.get("title", "Card Reward")
                raw_text = card_info.get("raw_text", "")
                is_memory = card_info.get("is_memory", False)
                combatant_idx = 1
                reason = "Mặc định nhân vật giữa"

                # Match canonical rule ID and clean name FIRST
                matched = None
                if hasattr(self, "rule_manager") and self.rule_manager:
                    matched = self.rule_manager.match_card(card_title) or (self.rule_manager.match_card(raw_text) if raw_text else None)
                if matched:
                    cid = matched.get("id", card_title)
                    cname = matched.get("name", card_title)
                    cvariant = matched.get("variant", "Base")
                    cchar = matched.get("character", "")
                else:
                    cid = re.sub(r"[^\w]+", "_", card_title.lower()).strip("_") or "card_reward"
                    cname = card_title
                    cvariant = "Base"
                    cchar = ""

                # Dynamic combatant selection based on on-screen badge card counts or deck_state
                if hasattr(self, "ai_brain") and getattr(self.ai_brain, "deck_evaluator", None):
                    badge_counts = self.vision.extract_card_reward_combatant_counts(screen) if screen is not None else None
                    combatant_idx, reason = self.ai_brain.deck_evaluator.evaluate_card_reward_combatant(
                        card_title=card_title,
                        is_memory=is_memory,
                        team_characters=self.team_characters,
                        on_screen_counts=badge_counts,
                        card_id=cid,
                        card_character=cchar
                    )

                target_char = self.team_characters[combatant_idx] if combatant_idx < len(self.team_characters) else self.active_character

                def _on_card_reward_success():
                    if hasattr(self, "ai_brain") and getattr(self.ai_brain, "deck_evaluator", None):
                        self.ai_brain.deck_evaluator.deck_state.record_card_picked(
                            target_char, card_id=cid, card_name=cname, variant=cvariant, source="card_reward"
                        )

                combatant_coords = [
                    TAP_COORDS.get("chaos_card_reward_combatant_1", (800, 300)),
                    TAP_COORDS.get("chaos_card_reward_combatant_2", (800, 500)),
                    TAP_COORDS.get("chaos_card_reward_combatant_3", (800, 700)),
                ]
                tap_coord = combatant_coords[combatant_idx] if 0 <= combatant_idx < len(combatant_coords) else (800, 500)
                confirm_coord = TAP_COORDS.get("chaos_card_reward_confirm", (1450, 838))
                return Action.tap(
                    tap_coord[0], tap_coord[1],
                    name=f"Card Reward: Assign '{card_title}' to Combatant {combatant_idx + 1} ({reason})",
                    extra_actions=[
                        ("tap", confirm_coord),
                    ],
                    extra={
                        "card_title": card_title,
                        "card_id": cid,
                        "card_name": cname,
                        "combatant_idx": combatant_idx,
                        "reason": reason,
                        "on_success": _on_card_reward_success,
                    }
                )

            # Sub-screen 1: choose_fate (Lựa chọn định mệnh / Sự kiện)
            if epiphany_type == "choose_fate":
                choices = self.vision.extract_event_choices(screen) if screen is not None else []
                if choices:
                    decision = self.ai_brain.decide_event(choices, res)
                    target_idx = decision.get("target_index", 0)
                    tap_coord = choices[target_idx].tap_coord if target_idx < len(choices) else (800, 480)
                    choice_name = choices[target_idx].name if target_idx < len(choices) else "Option 1"
                else:
                    tap_coord = (800, 480)
                    choice_name = "Default Fate Choice"

                # Kiểm tra nút Confirm xám (vô hiệu) trên màn hình ảnh thật (choose_fate.png)
                # Nút disabled có màu bạc/xám sáng (gray mean > 50) và tỷ lệ cam = 0.0
                is_confirm_disabled = False
                if screen is not None and getattr(screen, "size", 0) > 0 and screen.shape[0] >= 870 and screen.shape[1] >= 1577:
                    confirm_crop = screen[805:870, 1275:1577]
                    gray_c = cv2.cvtColor(confirm_crop, cv2.COLOR_BGR2GRAY)
                    hsv_c = cv2.cvtColor(confirm_crop, cv2.COLOR_BGR2HSV)
                    c_mask = cv2.inRange(hsv_c, (8, 120, 120), (25, 255, 255))
                    c_ratio = float(np.count_nonzero(c_mask)) / max(1, c_mask.size)
                    if gray_c.mean() > 50 and c_ratio < 0.10:
                        is_confirm_disabled = True

                extra_acts = [] if is_confirm_disabled else [("tap", (1425, 835))]

                return Action.tap(
                    tap_coord[0], tap_coord[1],
                    name=f"Choose Fate: {choice_name}",
                    extra_actions=extra_acts,
                    allowed_states={State.CHAOS_CHOOSE_FATE, State.CHAOS_CHOOSE_EPIPHANY},
                )

            # Sub-screen 2: select_attribute (Chọn chỉ số thưởng)
            if epiphany_type == "select_attribute":
                return Action.tap(
                    800, 500,
                    name="Select Attribute (Middle Option)",
                    extra_actions=[("tap", (1425, 835))]
                )

            # Sub-screen 3: remove_card (Thanh lọc thẻ hoặc Skip nếu không có thẻ rác)
            if epiphany_type == "remove_card":
                visible = self.vision.extract_remove_cards(screen) if screen is not None else []
                target_coord = (567, 275)
                card_name = "Basic Card"
                reason = "Xóa thẻ cơ bản mặc định (Slot 0)"
                target_slot = None

                remove_char = self.active_character
                if visible and hasattr(self, "ai_brain") and getattr(self.ai_brain, "deck_evaluator", None):
                    names = [c["title"] for c in visible]
                    remove_char = self._reconcile_remove_screen(visible)
                    decision, target_slot, eval_reason = self.ai_brain.deck_evaluator.evaluate_card_removal(names, remove_char)
                    if decision == "skip":
                        skip_coord = TAP_COORDS.get("chaos_remove_card_skip", (1230, 837))
                        return Action.tap(
                            skip_coord[0], skip_coord[1],
                            name=f"Remove Card: Skip ({eval_reason})",
                            extra={"decision": "skip", "reason": eval_reason}
                        )
                    elif target_slot is not None and target_slot < len(visible):
                        target_coord = visible[target_slot]["tap_coord"]
                        card_name = visible[target_slot]["title"]
                        reason = eval_reason

                # Match canonical rule ID
                matched = None
                if hasattr(self, "rule_manager") and self.rule_manager:
                    matched = self.rule_manager.match_card(card_name)
                if matched:
                    cid = matched.get("id", card_name)
                    cname = matched.get("name", card_name)
                else:
                    cid = re.sub(r"[^\w]+", "_", card_name.lower()).strip("_")
                    cname = card_name

                def _on_remove_card_success():
                    if hasattr(self, "ai_brain") and getattr(self.ai_brain, "deck_evaluator", None):
                        self.ai_brain.deck_evaluator.deck_state.record_card_removed(
                            remove_char, card_id=cid, card_name=cname
                        )

                remove_btn = TAP_COORDS.get("chaos_remove_card_confirm", (1498, 838))
                return Action.tap(
                    target_coord[0], target_coord[1],
                    name=f"Remove Card: {card_name}",
                    extra_actions=[("tap", remove_btn)],
                    extra={
                        "decision": "remove",
                        "card_name": card_name,
                        "card_id": cid,
                        "reason": reason,
                        "on_success": _on_remove_card_success,
                    }
                )

            # Sub-screen 4: etched_memory (Khắc ký ức)
            if epiphany_type == "etched_memory":
                return Action.tap(
                    800, 500,
                    name="Accept Etched Memory",
                    extra_actions=[("tap", (800, 850))]
                )

            # Sub-screen 5: event choices (Sự kiện có danh sách lựa chọn)
            choices = self.vision.extract_event_choices(screen) if screen is not None else []
            if choices and len(choices) >= 2:
                decision = self.ai_brain.decide_event(choices, res)
                target_idx = decision.get("target_index", 0)
                tap_coord = choices[target_idx].tap_coord if target_idx < len(choices) else (800, 360)
                choice_name = choices[target_idx].name if target_idx < len(choices) else "Option 1"
                return Action.tap(
                    tap_coord[0], tap_coord[1],
                    name=f"Event Choice: {choice_name}",
                    extra_actions=[
                        ("tap", (1425, 835)),
                    ]
                )

            # Sub-screen 6: standard 3-card reward / Epiphany
            cards = self.vision.extract_cards(screen, num_cards=3) if screen is not None else []
            decision = self.ai_brain.decide_card(cards, res, active_character=self.active_character)
            target_idx = decision.get("target_index", 1)
            tap_coord = cards[target_idx].tap_coord if target_idx < len(cards) else (800, 450)
            card_title = cards[target_idx].title if target_idx < len(cards) and cards[target_idx].title else f"Card {target_idx + 1}"

            def _on_epiphany_success():
                if 0 <= target_idx < len(cards) and hasattr(self, "ai_brain") and getattr(self.ai_brain, "deck_evaluator", None):
                    chosen_card = cards[target_idx]
                    char = chosen_card.character or self.active_character
                    card_id = chosen_card.matched_card.get("id", "") if chosen_card.matched_card else ""
                    if not card_id and hasattr(self, "rule_manager") and self.rule_manager:
                        m = self.rule_manager.match_card(chosen_card.title or chosen_card.raw_text)
                        if m:
                            card_id = m.get("id", "")
                    if not card_id:
                        card_id = chosen_card.title or chosen_card.name
                    cname = chosen_card.title or chosen_card.name
                    cvariant = chosen_card.variant or "Base"
                    if cvariant and cvariant.lower() != "base":
                        self.ai_brain.deck_evaluator.deck_state.record_card_upgraded(
                            char, card_id=card_id, card_name=cname, new_variant_id=card_id, variant_name=cvariant
                        )
                    else:
                        self.ai_brain.deck_evaluator.deck_state.record_card_picked(
                            char, card_id=card_id, card_name=cname, variant=cvariant, source="epiphany"
                        )

            return Action.tap(
                tap_coord[0], tap_coord[1],
                name=f"Auto Pick Card: {card_title}",
                extra_actions=[
                    ("tap", (1425, 835)),
                ],
                extra={
                    "card_title": card_title,
                    "target_index": target_idx,
                    "on_success": _on_epiphany_success,
                }
            )

        # 6a. CHAOS_SETTLEMENT: Màn hình kết toán phần thưởng (Settlement)
        if state == State.CHAOS_SETTLEMENT:
            is_modal = details.get("is_modal_open", False)
            if is_modal:
                confirm_coord = details.get("confirm_coord") or (1055, 569)
                return Action.tap(
                    *confirm_coord,
                    name="Settlement Modal Confirm",
                    allowed_states={State.CHAOS_SETTLEMENT},
                )
            else:
                continue_coord = details.get("continue_coord") or (1426, 825)
                return Action.tap(
                    *continue_coord,
                    name="Settlement Continue Button",
                    allowed_states={State.CHAOS_SETTLEMENT},
                )

        # 6b. CHAOS_SELECT_DUPLICATE_CARD: Màn hình chọn thẻ sao chép (Duplicate)
        if state == State.CHAOS_SELECT_DUPLICATE_CARD:
            card_coord = details.get("card_coord", (400, 480))
            return Action.tap(
                *card_coord,
                name="Select Duplicate Card (Option 1)",
                allowed_states={State.CHAOS_SELECT_DUPLICATE_CARD},
            )

        # 6c. CHAOS_OBTAIN_REWARD: Tap Obtain button liên tiếp nhận từng phần thưởng
        if state == State.CHAOS_OBTAIN_REWARD:
            from czn_bot.constants import MAX_OBTAIN_SAME_COUNT_TAPS, MAX_OBTAIN_TOTAL_TAPS
            from czn_bot.vision.ocr import get_ocr_service

            count = None
            if screen is not None and getattr(screen, "size", 0) > 0 and screen.shape[0] >= 870 and screen.shape[1] >= 1580:
                crop = screen[780:870, 1260:1580]
                ocr = get_ocr_service()
                txt = ocr.read_text(crop)
                m = re.search(r'\b([0-9])\b', txt)
                if m:
                    count = int(m.group(1))

            if count is not None:
                if self._obtain_last_count is not None and count == self._obtain_last_count:
                    self._obtain_same_count_taps += 1
                else:
                    self._obtain_same_count_taps = 0
                self._obtain_last_count = count

            if self._obtain_same_count_taps >= MAX_OBTAIN_SAME_COUNT_TAPS:
                logger.warning(
                    f"[ChaosFlow] Số đếm Obtain không giảm ({count}) sau {self._obtain_same_count_taps} lần tap liên tiếp. Dừng tap."
                )
                return Action.none(name="Obtain Count Not Decreasing (Stall Guard)")

            if self._obtain_total_taps >= MAX_OBTAIN_TOTAL_TAPS:
                logger.warning(
                    f"[ChaosFlow] Đã đạt giới hạn tối đa {self._obtain_total_taps} lần tap Obtain. Dừng tap."
                )
                return Action.none(name="Obtain Total Taps Cap Reached")

            self._obtain_total_taps += 1
            obtain_coord = details.get("obtain_coord") or (1426, 825)
            return Action.tap(
                *obtain_coord,
                name="Obtain Reward Button",
                allowed_states={State.CHAOS_OBTAIN_REWARD},
            )

        # 7. STORY_DIALOGUE: In Chaos Mode, always fast-forward dialogues
        if state == State.STORY_DIALOGUE:
            skip_coord = details.get("skip_coord") or TAP_COORDS.get("story_dialogue_skip", (1272, 48))
            auto_coord = details.get("auto_coord") or TAP_COORDS.get("story_dialogue_auto", (1395, 48))
            return Action.tap(
                *auto_coord,
                name="Chaos Dialogue Fast-Forward",
                extra_actions=[
                    ("tap", skip_coord),
                    ("tap", skip_coord),
                    ("tap", skip_coord),
                    ("tap", (800, 800)),
                    ("tap", TAP_COORDS.get("story_skip_confirm", (950, 550))),
                ],
                extra={"dialogue_skip": True}
            )

        # 8. Pre-match lobby
        if state in (State.PRE_MATCH_MISSION, State.PRE_MATCH_TEAM):
            coord = details.get("coord")
            if not coord:
                coord = TAP_COORDS["enter_team"] if state == State.PRE_MATCH_TEAM else TAP_COORDS["enter_mission"]
            return Action.tap(*coord, name=f"Enter {state.value}")

        if state in (State.POPUP_EFFECT, State.POPUP_DRAW_PILE, State.POPUP_STAGE_INFO, State.POPUP_PAUSE):
            close_coord = details.get("close_coord") or TAP_COORDS["close_x_default"]
            return Action.tap(*close_coord, name=f"Close {state.value}", extra={"allowed_states": {state}})

        if state == State.POPUP_MONSTER_INFO:
            coord = details.get("close_coord") or TAP_COORDS["close_monster_info"]
            return Action.tap(*coord, name="Dismiss Monster Info", extra={"allowed_states": {State.POPUP_MONSTER_INFO}})

        if state == State.TRANSITIONING:
            return Action.none(name="Transitioning Animation")

        return Action.none(name="Chaos Flow: Idle")

    def _reconcile_remove_screen(self, visible: List[Dict[str, Any]]) -> str:
        """
        Use the cards visible on the Remove Card screen as ground truth for DeckState.
        The owner character is inferred from the matched cards (majority, >= 2 agreeing
        cards, must be in the team); otherwise falls back to self.active_character.
        Returns the character whose deck this screen shows.
        """
        from collections import Counter

        deck_state = self.ai_brain.deck_evaluator.deck_state
        observed: List[Dict[str, str]] = []
        chars: List[str] = []
        for c in visible:
            title = (c.get("title") or "").strip()
            if len(title) < 3:
                continue
            m = self.rule_manager.match_card(title) if getattr(self, "rule_manager", None) else None
            if m:
                observed.append({
                    "card_id": m.get("id", ""), "card_name": m.get("name", title),
                    "variant": m.get("variant", "Base"),
                })
                if m.get("character"):
                    chars.append(m["character"])
            else:
                observed.append({"card_id": re.sub(r"[^\w]+", "_", title.lower()).strip("_"),
                                 "card_name": title, "variant": "Base"})

        owner = self.active_character
        if chars:
            top, n = Counter(chars).most_common(1)[0]
            if n >= 2 and top in self.team_characters:
                owner = top
        try:
            deck_state.reconcile_from_remove_screen(owner, observed)
        except Exception as e:
            logger.warning(f"Lỗi đối soát deck từ màn Remove Card: {e}")
        return owner

    def on_action_executed(self, action: Action, success: bool = True) -> None:
        """Called after an action executes. Invokes on_success callback if execution succeeded."""
        if not success:
            return
        on_success = action.extra.get("on_success") if action.extra else None
        if callable(on_success):
            try:
                on_success()
                action.extra["on_success"] = None
            except Exception as e:
                logger.warning(f"Lỗi khi thực thi post-action callback trong ChaosFlow: {e}")
