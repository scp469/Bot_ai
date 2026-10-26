"""
State Machine Loop & Crash Recovery for Chaos Zero Nightmare ("Vòng lặp trạng thái").
Handles:
- State Machine Loop with 6 core contexts:
    STATE_LOBBY: At main lobby -> tap Chaos entrance
    STATE_MAP_CHOOSING: At path selection -> calculate route & choose island
    STATE_EVENT: At random event / fate / campfire -> AI tactical choice & confirm
    STATE_CARD_REWARD: At card / epiphany selection -> AI card choice & confirm
    STATE_BATTLE: In battle (IN_MATCH) -> game auto-play, bot waits without interfering
    STATE_RESULT: Post-battle settlement -> tap Obtain / Leave / Continue to proceed
- Human-like Actions: Random coordinate jitter (±3-4 px) and random sleep (0.8s - 1.8s)
- Crash Recovery & Anti-freeze: 15-second watchdog timer, back key / X close recovery
- Logging Module: Writes to logs/bot_activity.log and saves logs/screenshot_error.png on exceptions
"""
import os
import time
import logging
from enum import Enum
from typing import Dict, Any, Optional, Tuple, Callable
import cv2
import numpy as np

from chaos_adb import ChaosADBController, get_adb_controller
from chaos_vision import ChaosVision
from chaos_ai_brain import ChaosAIBrain
from detector import ScreenDetector
from config import State, TAP_COORDS

# Setup dedicated activity logger
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
ACTIVITY_LOG_FILE = os.path.join(LOGS_DIR, "bot_activity.log")
ERROR_SCREENSHOT_FILE = os.path.join(LOGS_DIR, "screenshot_error.png")

activity_logger = logging.getLogger("ChaosBot.Activity")
if not activity_logger.handlers:
    activity_logger.setLevel(logging.INFO)
    fh = logging.FileHandler(ACTIVITY_LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    activity_logger.addHandler(fh)


class ChaosState(Enum):
    STATE_LOBBY = "STATE_LOBBY"
    STATE_MAP_CHOOSING = "STATE_MAP_CHOOSING"
    STATE_EVENT = "STATE_EVENT"
    STATE_CARD_REWARD = "STATE_CARD_REWARD"
    STATE_BATTLE = "STATE_BATTLE"
    STATE_RESULT = "STATE_RESULT"
    STATE_POPUP = "STATE_POPUP"
    STATE_UNKNOWN = "STATE_UNKNOWN"


class ChaosStateMachine:
    """Manages the full lifecycle loop of Chaos mode with AI decision making and recovery."""

    def __init__(
        self,
        adb: Optional[ChaosADBController] = None,
        vision: Optional[ChaosVision] = None,
        brain: Optional[ChaosAIBrain] = None,
        detector: Optional[ScreenDetector] = None
    ):
        self.adb = adb or get_adb_controller()
        self.vision = vision or ChaosVision()
        self.brain = brain or ChaosAIBrain()
        self.detector = detector or ScreenDetector()

        # Callbacks for UI updates
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_state_change: Optional[Callable[[ChaosState, str], None]] = None
        self.on_decision: Optional[Callable[[Dict[str, Any]], None]] = None

        # Internal state tracking
        self.current_state: ChaosState = ChaosState.STATE_UNKNOWN
        self.last_state: ChaosState = ChaosState.STATE_UNKNOWN
        self.state_start_time: float = time.time()
        self.same_screen_freeze_threshold: float = 15.0  # 15s freeze recovery
        self.retry_count: int = 0
        self.is_running: bool = False

    def log(self, message: str, level: str = "info"):
        """Log to activity file and UI callback."""
        if level == "warning":
            activity_logger.warning(message)
        elif level == "error":
            activity_logger.error(message)
        else:
            activity_logger.info(message)

        if self.on_log:
            self.on_log(message)

    def identify_state(self, screen: np.ndarray) -> Tuple[ChaosState, Dict[str, Any]]:
        """
        Xác định ngữ cảnh màn hình hiện tại thuộc State nào trong 6 nhóm chính.
        """
        if screen is None:
            return ChaosState.STATE_UNKNOWN, {}

        # 1. Kiểm tra đang trong trận chiến (IN_MATCH)
        score_in_match, _ = self.detector.match(screen, "in_match_check")
        if score_in_match >= 0.70:
            return ChaosState.STATE_BATTLE, {"score": score_in_match}

        # 2. Kiểm tra màn hình chọn Thẻ Bài / Epiphany (Dựa trên tiêu đề chuẩn xác)
        for key in ["card_reward_title", "card_epiphany_title", "epiphany_title"]:
            score, pt = self.detector.match(screen, key)
            if score >= 0.75:
                return ChaosState.STATE_CARD_REWARD, {"type": key, "coord": pt}

        # 3. Kiểm tra màn hình Nhận Thưởng / Kết Thúc Trận (RESULT)
        score_obtain, pt_obtain = self.detector.match(screen, "chaos_obtain_button")
        score_leave, pt_leave = self.detector.match(screen, "chaos_leave_button")
        score_cont, pt_cont = self.detector.match(screen, "chaos_continue_button")
        score_settle, pt_settle = self.detector.match(screen, "chaos_settlement_button")
        if score_obtain >= 0.80:
            return ChaosState.STATE_RESULT, {"type": "obtain", "coord": pt_obtain}
        if score_leave >= 0.75:
            return ChaosState.STATE_RESULT, {"type": "leave", "coord": pt_leave}
        if score_cont >= 0.75:
            return ChaosState.STATE_RESULT, {"type": "continue", "coord": pt_cont}
        if score_settle >= 0.75:
            return ChaosState.STATE_RESULT, {"type": "settlement", "coord": pt_settle}

        # 4. Kiểm tra màn hình Sự Kiện (Choose Fate, Safe Zone, Dialogue events)
        score_safe, pt_safe = self.detector.match(screen, "chaos_safe_zone_skip")
        score_fate, pt_fate = self.detector.match(screen, "choose_fate_title")
        score_attr, _ = self.detector.match(screen, "select_attribute_title")
        if score_safe >= 0.75:
            return ChaosState.STATE_EVENT, {"type": "safe_zone", "coord": pt_safe}
        if score_fate >= 0.75:
            return ChaosState.STATE_EVENT, {"type": "choose_fate", "coord": pt_fate}
        if score_attr >= 0.75:
            return ChaosState.STATE_EVENT, {"type": "select_attribute"}

        # 5. Kiểm tra các mẫu phụ của Thẻ Bài (view_original)
        score_vo, pt_vo = self.detector.match(screen, "view_original")
        if score_vo >= 0.75:
            return ChaosState.STATE_CARD_REWARD, {"type": "view_original", "coord": pt_vo}
        score_vow, pt_vow = self.detector.match(screen, "view_original_white")
        if score_vow >= 0.90:
            return ChaosState.STATE_CARD_REWARD, {"type": "view_original_white", "coord": pt_vow}

        # 5. Kiểm tra màn hình Bản Đồ Chọn Đường (MAP_CHOOSING)
        score_pin, _ = self.detector.match(screen, "chaos_node_pin")
        score_boss, _ = self.detector.match(screen, "chaos_node_boss")
        if score_pin >= 0.75 or score_boss >= 0.75:
            return ChaosState.STATE_MAP_CHOOSING, {"score_pin": score_pin}

        # 6. Kiểm tra màn hình Sảnh Chính (LOBBY)
        score_lobby, pt_lobby = self.detector.match(screen, "chaos_enter_lobby")
        if score_lobby >= 0.75:
            return ChaosState.STATE_LOBBY, {"coord": pt_lobby}

        # 7. Kiểm tra Popup phụ (X hoặc Close hoặc Tap to close)
        score_modal, pt_modal = self.detector.match(screen, "modal_close_button")
        score_close_x, pt_x = self.detector.match(screen, "close_x")
        score_tap_close, _ = self.detector.match(screen, "tap_to_close")
        if score_modal >= 0.75:
            return ChaosState.STATE_POPUP, {"type": "modal", "coord": pt_modal}
        if score_close_x >= 0.80:
            return ChaosState.STATE_POPUP, {"type": "close_x", "coord": pt_x}
        if score_tap_close >= 0.75:
            return ChaosState.STATE_POPUP, {"type": "tap_to_close"}

        return ChaosState.STATE_UNKNOWN, {}

    # ── Xử lý từng State ──────────────────────────────────────────

    def handle_lobby(self, screen: np.ndarray, details: Dict[str, Any]) -> bool:
        """STATE_LOBBY: Đang ở sảnh chính -> Bấm nút vào ải Chaos."""
        self.log("Trạng thái: STATE_LOBBY -> Bấm nút vào ải Chaos...")
        tap_pt = details.get("coord", (1400, 780))
        self.adb.tap_location(*tap_pt, random_offset=True)
        self.adb.human_sleep(1.2, 1.8)
        return True

    def handle_map_choosing(self, screen: np.ndarray, details: Dict[str, Any]) -> bool:
        """
        STATE_MAP_CHOOSING: Đang ở bản đồ chọn đường.
        Đo máu, phân tích đồ thị đường đi, tính điểm và chạm hòn đảo tối ưu.
        """
        self.log("Trạng thái: STATE_MAP_CHOOSING -> Phân tích bản đồ và chọn ngã rẽ...")
        try:
            from chaos_hp_reader import get_team_hp
            from chaos_map_reader import parse_chaos_minimap, detect_3d_island_coords
            from chaos_pathfinder import select_best_island

            hp_percent, is_low = get_team_hp(screen)
            roots, adj, nodes, boss_ids = parse_chaos_minimap(screen)

            if not roots:
                # Fallback: Tự động bấm đảo giữa mặc định nếu không thấy minimap
                self.log("⚠️ Không phân tích được minimap -> Chạm đảo Giữa mặc định.")
                self.adb.tap_location(1330, 420, random_offset=True)
                self.adb.human_sleep(1.0, 1.5)
                return True

            best_island, evaluations = select_best_island(
                roots, adj, nodes, boss_ids, hp_percent, strategy="balanced"
            )

            # Gọi AI Brain đưa ra quyết định chọn đường đi
            resources = self.vision.extract_resources(screen)
            ai_decision = self.brain.decide_island(evaluations, resources, fallback_island=best_island)
            if self.on_decision:
                self.on_decision(ai_decision)

            target_island_str = ai_decision.get("target_island", "middle").lower()
            reason = ai_decision.get("reason", "Tối ưu hóa lộ trình tới Boss")
            self.log(f"[AI Chọn Đường] Đã chọn Đảo {target_island_str.upper()} | Lý do: {reason}")

            # Tìm tọa độ đảo (ưu tiên nhận diện 3D thực tế)
            dynamic_islands = detect_3d_island_coords(screen)
            chosen_coord = None
            if dynamic_islands and target_island_str in dynamic_islands:
                chosen_coord = dynamic_islands[target_island_str]

            if chosen_coord is None:
                # Tọa độ tĩnh fallback
                static_coords = {
                    "top": (1210, 140),
                    "middle": (1330, 420),
                    "bottom": (1350, 680)
                }
                chosen_coord = static_coords.get(target_island_str, (1330, 420))

            self.adb.tap_location(*chosen_coord, random_offset=True)
            self.adb.human_sleep(1.0, 1.6)
            return True

        except Exception as e:
            self.log(f"Lỗi khi xử lý Map Choosing: {e}", level="error")
            self._save_error_screenshot(screen)
            return False

    def handle_event(self, screen: np.ndarray, details: Dict[str, Any]) -> bool:
        """
        STATE_EVENT: Đang gặp sự kiện ngẫu nhiên hoặc chọn Fate / Trạm nghỉ.
        Đọc các lựa chọn -> Gọi AI Brain ra quyết định -> Chạm lựa chọn & Confirm.
        """
        self.log("Trạng thái: STATE_EVENT -> Đọc lựa chọn sự kiện và gọi AI quyết định...")
        try:
            # 1. Trạm nghỉ (Safe Zone / Campfire)
            if details.get("type") == "safe_zone":
                self.log("Sự kiện: Trạm nghỉ an toàn (Campfire) -> Bấm Skip và Confirm...")
                skip_pt = details.get("coord", (1415, 825))
                self.adb.tap_location(*skip_pt, random_offset=True)
                self.adb.human_sleep(0.8, 1.2)
                # Confirm popup bỏ qua
                confirm_pt = TAP_COORDS.get("chaos_safe_zone_confirm", (956, 568))
                self.adb.tap_location(*confirm_pt, random_offset=True)
                self.adb.human_sleep(1.0, 1.5)
                return True

            # 2. Sự kiện câu hỏi / Choose Fate / Đánh boss
            choices = self.vision.extract_event_choices(screen)
            resources = self.vision.extract_resources(screen)

            decision = self.brain.decide_event(choices, resources)
            if self.on_decision:
                self.on_decision(decision)

            target_idx = decision.get("target_index", 0)
            reason = decision.get("reason", "Quyết định bởi AI")
            self.log(f"[AI Sự Kiện] Chọn lựa chọn {target_idx + 1} | Lý do: {reason}")

            # Chạm vào lựa chọn được AI chọn
            if target_idx < len(choices):
                tap_coord = choices[target_idx].tap_coord
            else:
                tap_coord = (800, 460)

            self.adb.tap_location(*tap_coord, random_offset=True)
            self.adb.human_sleep(0.8, 1.3)

            # Chạm Confirm nếu có
            confirm_btn = self.vision.find_action_button(screen, action_type="confirm")
            if confirm_btn:
                self.adb.tap_location(*confirm_btn, random_offset=True)
                self.adb.human_sleep(1.0, 1.6)

            return True

        except Exception as e:
            self.log(f"Lỗi khi xử lý Event: {e}", level="error")
            self._save_error_screenshot(screen)
            return False

    def handle_card_reward(self, screen: np.ndarray, details: Dict[str, Any]) -> bool:
        """
        STATE_CARD_REWARD: Đang ở màn chọn thẻ bài / Epiphany.
        Cắt các lá bài -> Gọi AI Brain -> Chạm thẻ được chọn -> Bấm Confirm.
        """
        self.log("Trạng thái: STATE_CARD_REWARD -> Phân tích các lá bài và gọi AI...")
        try:
            cards = self.vision.extract_cards(screen, num_cards=3)
            resources = self.vision.extract_resources(screen)

            decision = self.brain.decide_card(cards, resources)
            if self.on_decision:
                self.on_decision(decision)

            target_idx = decision.get("target_index", 1)
            reason = decision.get("reason", "Quyết định bởi AI")
            self.log(f"[AI Thẻ Bài] Chọn lá {target_idx + 1} ({cards[target_idx].name if target_idx < len(cards) else ''}) | Lý do: {reason}")

            # Chạm vào lá bài
            if target_idx < len(cards):
                tap_coord = cards[target_idx].tap_coord
            else:
                tap_coord = (800, 460)

            self.adb.tap_location(*tap_coord, random_offset=True)
            self.adb.human_sleep(0.8, 1.2)

            # Bấm Confirm xác nhận
            confirm_btn = self.vision.find_action_button(screen, action_type="confirm")
            if confirm_btn:
                self.adb.tap_location(*confirm_btn, random_offset=True)
                self.adb.human_sleep(1.0, 1.5)

            return True

        except Exception as e:
            self.log(f"Lỗi khi xử lý Card Reward: {e}", level="error")
            self._save_error_screenshot(screen)
            return False

    def handle_battle(self, screen: np.ndarray, details: Dict[str, Any]) -> bool:
        """
        STATE_BATTLE: Đang trong trận đấu (IN_MATCH).
        Nhường toàn bộ quyền điều khiển cho tính năng Auto có sẵn của game. Bot chỉ chờ đợi.
        """
        self.log("Trạng thái: STATE_BATTLE (Đang trong trận đấu) -> Game đang tự đánh, bot chờ...")
        self.adb.human_sleep(2.0, 3.0)
        return True

    def handle_result(self, screen: np.ndarray, details: Dict[str, Any]) -> bool:
        """
        STATE_RESULT: Màn hình nhận thưởng sau trận (Obtain / Leave / Continue).
        Chạm nút tương ứng để qua màn.
        """
        res_type = details.get("type", "obtain")
        self.log(f"Trạng thái: STATE_RESULT -> Bấm nút {res_type.upper()} để tiếp tục...")
        tap_pt = details.get("coord")
        if not tap_pt:
            tap_pt = self.vision.find_action_button(screen, action_type=res_type)
        if tap_pt:
            self.adb.tap_location(*tap_pt, random_offset=True)
            self.adb.human_sleep(1.0, 1.6)
        return True

    def handle_popup(self, screen: np.ndarray, details: Dict[str, Any]) -> bool:
        """STATE_POPUP: Đóng popup thông báo / Close / Tap to close."""
        self.log("Trạng thái: STATE_POPUP -> Đóng popup...")
        pop_type = details.get("type", "close_x")
        if pop_type == "tap_to_close":
            self.adb.tap_location(800, 850, random_offset=True)
        else:
            tap_pt = details.get("coord", (1535, 50))
            self.adb.tap_location(*tap_pt, random_offset=True)
        self.adb.human_sleep(0.8, 1.2)
        return True

    # ── 4.3. Watchdog & Crash Recovery ────────────────────────────

    def check_watchdog_recovery(self, screen: np.ndarray) -> bool:
        """
        Kiểm tra nếu bot bị kẹt ở cùng một trạng thái quá 15 giây (ngoại trừ STATE_BATTLE):
        Tự động bấm Back hoặc tìm nút X để đóng popup bất ngờ.
        """
        if self.current_state == ChaosState.STATE_BATTLE:
            # Trong trận đánh có thể kéo dài vài phút, không kích hoạt timeout
            return False

        elapsed = time.time() - self.state_start_time
        if elapsed > self.same_screen_freeze_threshold:
            self.log(f"⚠️ CẢNH BÁO: Bị kẹt ở {self.current_state.value} quá {int(elapsed)}s (>15s)!", level="warning")
            self.log("Kích hoạt cơ chế Khôi phục lỗi (Crash Recovery): Thử tìm 'X' hoặc gửi phím BACK...")
            self._save_error_screenshot(screen)

            # Thử tìm nút X
            close_btn = self.vision.find_action_button(screen, action_type="close")
            if close_btn:
                self.adb.tap_location(*close_btn, random_offset=True)
                self.adb.human_sleep(1.0, 1.5)
            else:
                # Gửi phím Android Back
                self.adb.send_back()
                self.adb.human_sleep(1.2, 1.8)

            # Reset timer
            self.state_start_time = time.time()
            return True

        return False

    def _save_error_screenshot(self, screen: np.ndarray):
        """Lưu lại ảnh chụp màn hình khi gặp ngoại lệ để kiểm tra lỗi sau này."""
        if screen is not None and screen.size > 0:
            try:
                cv2.imwrite(ERROR_SCREENSHOT_FILE, screen)
                self.log(f"Đã lưu ảnh lỗi tại: {ERROR_SCREENSHOT_FILE}")
            except Exception as e:
                activity_logger.error(f"Không thể lưu screenshot_error.png: {e}")

    # ── Vòng Lặp Chính (Main Execution Step) ──────────────────────

    def step(self) -> bool:
        """Thực hiện một chu kỳ nhận diện và xử lý trạng thái."""
        screen = self.adb.capture_screen()
        if screen is None:
            self.log("Không chụp được màn hình giả lập. Đang thử lại...", level="warning")
            time.sleep(1.0)
            return False

        state, details = self.identify_state(screen)

        # Cập nhật thời gian trạng thái
        if state != self.current_state:
            self.last_state = self.current_state
            self.current_state = state
            self.state_start_time = time.time()
            self.retry_count = 0
            if self.on_state_change:
                self.on_state_change(state, f"Chuyển sang {state.value}")

        # Kiểm tra Watchdog (quá 15s)
        if self.check_watchdog_recovery(screen):
            return True

        # Điều hướng xử lý theo State
        if state == ChaosState.STATE_LOBBY:
            return self.handle_lobby(screen, details)
        elif state == ChaosState.STATE_MAP_CHOOSING:
            return self.handle_map_choosing(screen, details)
        elif state == ChaosState.STATE_EVENT:
            return self.handle_event(screen, details)
        elif state == ChaosState.STATE_CARD_REWARD:
            return self.handle_card_reward(screen, details)
        elif state == ChaosState.STATE_BATTLE:
            return self.handle_battle(screen, details)
        elif state == ChaosState.STATE_RESULT:
            return self.handle_result(screen, details)
        elif state == ChaosState.STATE_POPUP:
            return self.handle_popup(screen, details)
        else:
            self.retry_count += 1
            if self.retry_count % 3 == 0:
                self.log(f"Trạng thái không xác định ({self.retry_count} lần) -> Đang quan sát...", level="warning")
            time.sleep(1.0)
            return True
