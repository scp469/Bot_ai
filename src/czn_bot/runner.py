"""
Main Execution Engine and Runner for Chaos Zero Nightmare Bot.
Manages:
- Decision loop: capture -> multi-frame confirm -> flow.handle -> execute Action -> watchdog
- Anti-stuck action guards, stall watchdog, and UNKNOWN screen recovery
- UI and telemetry callbacks
"""
import os
import time
import threading
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, Tuple, Callable, List
import cv2
import numpy as np

try:
    import winsound
except ImportError:
    winsound = None

from czn_bot.constants import (
    CONFIRM_FRAMES,
    MAX_SAME_ACTION,
    LOGS_DIR,
    DEFAULT_LOOP_DELAY,
    STALL_TIMEOUT,
    STATE_STALL_TIMEOUTS,
    MAX_UNKNOWN_SCREENSHOTS,
    ENABLE_HYBRID_VERIFICATION,
    HYBRID_VERIFICATION_PAD,
    ENABLE_DYNAMIC_ISLAND_DETECTION,
    ENABLE_FRAME_STABILITY,
    FRAME_STABILITY_THRESHOLD,
    FRAME_STABILITY_DELAY,
    ENABLE_TRANSITION_VALIDATION,
    INVALID_TRANSITION_CONFIRM_FRAMES,
)
from czn_bot.states import State, Mode, LeftButton
from czn_bot.device.adb import ADBClient
from czn_bot.vision.detector import ScreenDetector
from czn_bot.vision.state_classifier import DEFAULT_ALLOWED_TRANSITIONS, TemporalFilter
from czn_bot.stats import StatsTracker
from czn_bot.notifier import Notifier
from czn_bot.recovery import RecoveryManager
from czn_bot.chaos.rules import ChaosRuleManager
from czn_bot.chaos.decisions import ChaosVision
from czn_bot.chaos.ai_brain import ChaosAIBrain
from czn_bot.coords import TAP_COORDS
from czn_bot.flows.base import Flow, Action, ActionType
from czn_bot.flows.replay import ReplayFlow
from czn_bot.flows.progress import ProgressFlow
from czn_bot.flows.story import StoryFlow
from czn_bot.flows.chaos import ChaosFlow
from czn_bot.chaos.pathfinder import IslandChoice

logger = logging.getLogger("ChaosBot.Runner")


class BotRunner:
    """Core decision engine coordinating ADB, Vision, Flows, and Safety Watchdogs."""

    def __init__(
        self,
        adb_client: Optional[Any] = None,
        detector: Optional[ScreenDetector] = None,
        stats_tracker: Optional[StatsTracker] = None,
        notifier: Optional[Notifier] = None,
        recovery_manager: Optional[RecoveryManager] = None,
    ) -> None:
        self.adb = adb_client or ADBClient()
        self.detector = detector or ScreenDetector()
        self.stats = stats_tracker or StatsTracker()
        self.notifier = notifier or Notifier()
        self.recovery = recovery_manager or RecoveryManager(adb_client=self.adb, detector=self.detector)

        # Settings
        self.mode: Mode = Mode.REPLAY
        self.loop_delay: float = DEFAULT_LOOP_DELAY
        self.max_retries: Optional[int] = None
        self.auto_start_match: bool = False
        self.enable_recovery: bool = False
        self.enable_hybrid_verification: bool = ENABLE_HYBRID_VERIFICATION
        self.hybrid_pad: int = HYBRID_VERIFICATION_PAD
        self.chaos_strategy: str = "balanced"
        self.enable_dynamic_islands: bool = ENABLE_DYNAMIC_ISLAND_DETECTION
        self.auto_pick_epiphany: bool = True
        self.max_map_retries: int = 5
        self.max_unknown_screenshots: int = MAX_UNKNOWN_SCREENSHOTS

        # AI & Tactical
        self.rule_manager = ChaosRuleManager()
        self.chaos_vision = ChaosVision(rule_manager=self.rule_manager)
        self.chaos_brain = ChaosAIBrain(rule_manager=self.rule_manager)
        self.enable_chaos_ai: bool = True
        self.enable_ai_vision_detection: bool = False
        self.last_ai_decision: Optional[Dict[str, Any]] = None

        # [Mục 1 & 2] Frame stability & Transition validation
        self.enable_frame_stability: bool = ENABLE_FRAME_STABILITY
        self.frame_stability_thresh: float = FRAME_STABILITY_THRESHOLD
        self.frame_stability_delay: float = FRAME_STABILITY_DELAY
        self.stability_use_consecutive_cap: bool = False
        self._last_raw_screen: Optional[np.ndarray] = None
        self._last_decision_log: Optional[str] = None
        self._last_settled_state: Optional[State] = None

        self.enable_transition_validation: bool = ENABLE_TRANSITION_VALIDATION
        self.invalid_transition_confirm_frames: int = INVALID_TRANSITION_CONFIRM_FRAMES
        self.allowed_transitions: Dict[str, Set[str]] = DEFAULT_ALLOWED_TRANSITIONS
        self.temporal_filter: TemporalFilter = TemporalFilter(
            window=self.invalid_transition_confirm_frames,
            need=CONFIRM_FRAMES,
            allowed=self.allowed_transitions
        )

        # State tracking
        self.is_running: bool = False
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.retries_done: int = 0
        self.actions_done: int = 0
        self.current_state: State = State.UNKNOWN

        # Anti-stuck and watchdog guards
        self._last_action: Optional[str] = None
        self._same_action_count: int = 0
        self._last_state: Optional[State] = None
        self._unknown_streak: int = 0
        self.stall_timeout: float = STALL_TIMEOUT
        self._last_progress_time: float = time.time()
        self._stall_recovered_count: int = 0

        # Flows
        self.active_flow: Optional[Flow] = None

        # Callbacks
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_state_change: Optional[Callable[[State, dict], None]] = None
        self.on_frame: Optional[Callable[[Any, State, dict], None]] = None
        self.on_stats_update: Optional[Callable[[dict], None]] = None
        self.on_stopped: Optional[Callable[[str], None]] = None
        self.on_ai_decision: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_stall: Optional[Callable[[State, float, str, str], None]] = None

        self._init_logger()

    def _init_logger(self) -> None:
        log_file = os.path.join(LOGS_DIR, "bot.log")
        self.logger = logging.getLogger("ChaosBot")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = RotatingFileHandler(
                log_file,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8"
            )
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def log(self, message: str) -> None:
        self.logger.info(message)
        if self.on_log:
            try:
                self.on_log(message)
            except Exception:
                pass

    def beep(self, freq: int = 1000, duration_ms: int = 400) -> None:
        if winsound:
            try:
                winsound.Beep(freq, duration_ms)
            except Exception:
                pass

    def _create_flow(self) -> Flow:
        """Instantiate the active Flow based on the configured mode."""
        if self.mode == Mode.REPLAY:
            flow = ReplayFlow(
                max_retries=self.max_retries,
                auto_start_match=self.auto_start_match,
            )
            flow._mode = Mode.REPLAY
            return flow
        elif self.mode == Mode.PROGRESS:
            flow = ProgressFlow(
                max_stages=self.max_retries,
            )
            flow._mode = Mode.PROGRESS
            return flow
        elif self.mode == Mode.STORY:
            flow = StoryFlow(max_stages=self.max_retries)
            flow._mode = Mode.STORY
            return flow
        elif self.mode == Mode.CHAOS:
            flow = ChaosFlow(
                strategy=self.chaos_strategy,
                auto_pick_epiphany=self.auto_pick_epiphany,
                enable_dynamic_islands=self.enable_dynamic_islands,
                rule_manager=self.rule_manager,
                ai_brain=self.chaos_brain,
                vision=self.chaos_vision,
                max_matches=self.max_retries,
            )
            flow._mode = Mode.CHAOS
            return flow
        flow = ReplayFlow()
        flow._mode = Mode.REPLAY
        return flow

    def start(self) -> None:
        """Start the bot execution thread."""
        if self.is_running:
            return
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=2.0)

        self.is_running = True
        self._stop_event.clear()
        self._last_action = None
        self._same_action_count = 0
        self._last_state = None
        self._unknown_streak = 0
        self._last_progress_time = time.time()
        self._stall_recovered_count = 0
        self._last_raw_screen = None
        self._last_decision_log = None
        self._last_settled_state = None
        if hasattr(self, "temporal_filter") and self.temporal_filter:
            self.temporal_filter.reset()
        self.retries_done = 0
        self.actions_done = 0

        self.active_flow = self._create_flow()
        self.stats.start_session()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.log(f"Bot đã khởi động thành công (Chế độ: {self.mode.value})")

    def _halt(self, reason: str, freq: int = 1000, duration: int = 300) -> None:
        self.beep(freq=freq, duration_ms=duration)
        self.stop(reason=reason)

    @property
    def _story_swipe_count(self) -> int:
        if self.active_flow and hasattr(self.active_flow, "swipe_count"):
            return self.active_flow.swipe_count
        return getattr(self, "_story_swipe_count_val", 0)

    @_story_swipe_count.setter
    def _story_swipe_count(self, val: int) -> None:
        self._story_swipe_count_val = val
        if self.active_flow and hasattr(self.active_flow, "swipe_count"):
            self.active_flow.swipe_count = val

    def stop(self, reason: Optional[str] = None) -> None:
        """Signal bot to stop."""
        self.is_running = False
        self._stop_event.set()
        stop_reason = reason or "Người dùng dừng bot"
        self._unknown_streak = 0
        self.stats.record_stop(stop_reason)
        self.log(f"Bot dừng: {stop_reason}")
        if self.notifier and hasattr(self.notifier, "notify_bot_stopped"):
            try:
                summary = self.stats.format_summary() if hasattr(self.stats, "format_summary") else ""
                self.notifier.notify_bot_stopped(stop_reason, summary)
            except Exception:
                pass
        if self.on_stopped:
            try:
                self.on_stopped(stop_reason)
            except Exception:
                pass

    def _dispatch_state(self, state: State, screen: Any, details: Dict[str, Any]) -> bool:
        if self._last_state and self._last_state != state:
            if not self.is_transition_allowed(self._last_state, state):
                self.logger.warning(
                    f"[TransitionValidation] Dispatching unvalidated transition: "
                    f"{self._last_state.value if hasattr(self._last_state, 'value') else self._last_state} -> "
                    f"{state.value if hasattr(state, 'value') else state}"
                )

        if self.active_flow is None or getattr(self.active_flow, "_mode", None) != self.mode:
            self.active_flow = self._create_flow()

        # Sync runtime properties to active flow
        if self.mode == Mode.CHAOS:
            self.active_flow.auto_pick_epiphany = self.auto_pick_epiphany
            self.active_flow.strategy = self.chaos_strategy
            self.active_flow.enable_dynamic_islands = self.enable_dynamic_islands
            self.active_flow.max_matches = self.max_retries
            self.active_flow.max_map_retries = getattr(self, "max_map_retries", 5)
        elif self.mode == Mode.REPLAY:
            self.active_flow.auto_start_match = self.auto_start_match
            self.active_flow.max_retries = self.max_retries
        elif self.mode == Mode.PROGRESS:
            self.active_flow.max_stages = self.max_retries

        # Ignore states when not in pre-match auto-start
        if not getattr(self, "auto_start_match", False) and state in (State.PRE_MATCH_MISSION, State.PRE_MATCH_TEAM):
            return True

        # Non-Chaos modes ignore Chaos-specific states
        if self.mode != Mode.CHAOS and state in (
            State.CHAOS_MAP, State.CHAOS_AFTER_BATTLE, State.CHAOS_EQUIPMENT,
            State.CHAOS_SAFE_ZONE, State.CHAOS_CHOOSE_EPIPHANY, State.CHAOS_OBTAIN_REWARD, State.CHAOS_EVENT
        ):
            return True

        # Reset counters on in-match, transitioning, or choose epiphany
        if state in (State.IN_MATCH, State.TRANSITIONING):
            self._last_action = None
            self._same_action_count = 0

        if state in (State.TRANSITIONING, State.CHAOS_CHOOSE_EPIPHANY, State.CHAOS_EVENT):
            self._unknown_streak = 0

        # State-specific limit / condition checks
        if state == State.MATCH_DONE:
            left_btn = details.get("left_button")
            if left_btn == LeftButton.RETRY_DISABLED:
                if self.notifier and hasattr(self.notifier, "notify_stamina_depleted"):
                    self.notifier.notify_stamina_depleted()
                self._halt("Dừng do hết thể lực (nút Retry xám)", freq=1500, duration=500)
                return False

            if self.max_retries is not None and self.retries_done >= self.max_retries:
                if self.notifier and hasattr(self.notifier, "notify_max_retries"):
                    self.notifier.notify_max_retries(self.max_retries)
                self._halt(f"Đã đạt giới hạn số lần ({self.max_retries})", freq=1200)
                return False

            if self.mode == Mode.STORY:
                reward_score = details.get("reward_score", 0.0)
                confirm_score = details.get("confirm_score", 0.0)
                has_rewards = reward_score >= 0.70
                has_confirm = confirm_score >= 0.70

                if left_btn == LeftButton.RETRY and not has_rewards and not has_confirm:
                    if self.notifier and hasattr(self.notifier, "notify_match_failed"):
                        self.notifier.notify_match_failed()
                    self._halt("Dừng bot do thất bại trong ải cốt truyện (Thua trận)", freq=800, duration=600)
                    return False

        elif self.mode == Mode.CHAOS and state == State.CHAOS_AFTER_BATTLE:
            if self.max_retries is not None and self.retries_done >= self.max_retries:
                if self.notifier and hasattr(self.notifier, "notify_max_retries"):
                    self.notifier.notify_max_retries(self.max_retries)
                self._halt(f"Đã đạt giới hạn số trận Chaos ({self.max_retries})", freq=1200)
                return False

        action = self.active_flow.handle(state, details, screen)
        return self._execute_action(action, screen)

    def _scan_unknown_screen_elements(self, screen: Any) -> Optional[Tuple[str, int, int]]:
        """
        Quét tìm các phần tử UI offline khi gặp màn hình UNKNOWN:
        - Nút đóng (X) hoặc nút Cancel
        - Chạm để đóng (Tap to close)
        - Nút xác nhận (Confirm, OK, Tiếp tục, Skip)
        - Ô lựa chọn sự kiện (nếu màn hình có các card event)
        Trả về: (tên phần tử, center_x, center_y) hoặc None
        """
        if screen is None or getattr(screen, "size", 0) == 0 or not hasattr(self, "detector") or self.detector is None:
            return None

        def safe_match(key: str, region: Optional[Tuple[int, int, int, int]] = None) -> Tuple[float, Optional[Tuple[int, int]]]:
            try:
                if region is not None:
                    res = self.detector.match(screen, key, region=region)
                else:
                    res = self.detector.match(screen, key)
                if isinstance(res, (tuple, list)) and len(res) >= 2:
                    return float(res[0]), res[1]
                return 0.0, None
            except Exception:
                return 0.0, None

        # 1. Quét nút Đóng (X)
        for close_key in ["close_x", "modal_close_button"]:
            score, pt = safe_match(close_key, region=(1100, 0, 500, 250))
            if score >= 0.70 and pt:
                return (f"Nút Đóng ({close_key})", pt[0], pt[1])
            score, pt = safe_match(close_key)
            if score >= 0.72 and pt:
                return (f"Nút Đóng ({close_key})", pt[0], pt[1])

        # 2. Quét "Tap to close" / Chạm để tiếp tục
        score, pt = safe_match("tap_to_close", region=(300, 600, 1000, 300))
        if score >= 0.65 and pt:
            return ("Dòng chữ 'Chạm để đóng'", pt[0], pt[1])
        score, pt = safe_match("tap_to_close")
        if score >= 0.68 and pt:
            return ("Dòng chữ 'Chạm để đóng'", pt[0], pt[1])

        # 3. Quét các nút xác nhận / tiếp tục / skip bằng template
        confirm_keys = [
            ("chaos_settlement_button", "Nút Settlement", 0.70),
            ("chaos_leave_button", "Nút Leave", 0.70),
            ("chaos_safe_zone_confirm_btn", "Nút Xác nhận Cam", 0.70),
            ("confirm_button", "Nút Xác nhận", 0.70),
            ("confirm_button_purple", "Nút Xác nhận Tím", 0.72),
            ("chaos_continue_button", "Nút Tiếp tục", 0.72),
            ("chaos_obtain_button", "Nút Nhận", 0.72),
            ("chaos_safe_zone_skip", "Nút Skip Trạm dừng", 0.72),
            ("story_dialogue_skip", "Nút Skip Hội thoại", 0.72),
        ]
        for key, name, thresh in confirm_keys:
            score, pt = safe_match(key)
            if score >= thresh and pt:
                return (name, pt[0], pt[1])

        # 4. Quét OCR tìm nút xác nhận / tiếp tục / bỏ qua (vùng nửa dưới màn hình)
        try:
            from czn_bot.vision.ocr import get_ocr_service
            ocr = get_ocr_service()
            if ocr and ocr.is_available:
                elements = ocr.recognize_elements(screen[500:880, :], preprocess=True)
                target_keywords = ["settlement", "leave", "confirm", "xác nhận", "tiếp tục", "continue", "skip", "bỏ qua", "ok", "activate", "chọn", "enter", "close", "đóng"]
                for elem in elements:
                    txt = elem.get("text", "").strip().lower()
                    if not txt:
                        continue
                    for kw in target_keywords:
                        if kw in txt:
                            cx, cy = elem["center"]
                            return (f"Nút OCR '{txt}'", cx, cy + 500)
        except Exception as e_ocr:
            self.logger.debug(f"Offline OCR scan error: {e_ocr}")

        # 5. Quét ô lựa chọn sự kiện nếu có
        try:
            from czn_bot.chaos.decisions import ChaosVision
            vision = getattr(self.active_flow, "vision", None)
            if vision is None:
                vision = ChaosVision(rule_manager=getattr(self, "rule_manager", None))
            choices = vision.extract_event_choices(screen)
            if choices and len(choices) > 0:
                first_choice = choices[0]
                return ("Ô lựa chọn sự kiện", first_choice.tap_coord[0], first_choice.tap_coord[1])
        except Exception:
            pass

        return None

    def _handle_unknown(self, screen: Any, details: Dict[str, Any]) -> bool:
        self._unknown_streak += 1
        self.stats.record_unknown()
        self.logger.warning(f"Màn hình UNKNOWN (streak={self._unknown_streak}/3)")

        # 1. Multi-modal AI Vision analysis if configured
        if getattr(self, "enable_chaos_ai", True) and hasattr(self, "chaos_brain") and self.rule_manager.get_api_key():
            try:
                last_st_name = self._last_state.value if hasattr(self._last_state, "value") else str(self._last_state or "")
                self.logger.info("[Vision] Gặp màn hình UNKNOWN -> Phân tích màn hình...")
                ai_decision = self.chaos_brain.analyze_unknown_screen(screen, last_state_name=last_st_name)
                if ai_decision:
                    self.last_ai_decision = ai_decision
                    if self.on_ai_decision:
                        self.on_ai_decision(ai_decision)

                    action = str(ai_decision.get("action", "")).lower()
                    reason = ai_decision.get("reason", "")
                    screen_type = ai_decision.get("screen_type", "unknown")
                    self.logger.info(f"[AI Vision] Phân tích hoàn tất: Type={screen_type}, Action={action.upper()} - {reason}")

                    if action == "wait":
                        wait_sec = float(ai_decision.get("wait_seconds", 1.5))
                        self.log(f"[AI Vision] Đang chờ hoạt cảnh kết thúc ({wait_sec}s): {reason}")
                        time.sleep(wait_sec)
                        self._unknown_streak = 0
                        return True

                    elif action == "tap":
                        tap_coord = ai_decision.get("tap_coord")
                        if tap_coord and isinstance(tap_coord, (list, tuple)) and len(tap_coord) >= 2:
                            tx = int(tap_coord[0])
                            ty = int(tap_coord[1])
                            tx = max(10, min(1590, tx))
                            ty = max(10, min(890, ty))
                            import random
                            rx = tx + random.randint(-3, 3)
                            ry = ty + random.randint(-3, 3)
                            self.log(f"[AI Vision] Chạm vào màn hình tại ({rx}, {ry}): {reason}")
                            self.adb.tap(rx, ry)
                            time.sleep(0.5)
                            self._unknown_streak = 0
                            return True

                    elif action == "stop":
                        if self.notifier and hasattr(self.notifier, "notify_unknown_halt"):
                            self.notifier.notify_unknown_halt()
                        self.stop(reason=f"AI Vision yêu cầu dừng an toàn: {reason}")
                        return False
            except Exception as e_ai_vision:
                self.logger.warning(f"Lỗi khi AI Vision phân tích màn hình UNKNOWN: {e_ai_vision}")

        # 2. Offline UI Element Scanner (Tự động quét nút đóng/xác nhận khi AI vắng mặt hoặc lỗi)
        ui_element = self._scan_unknown_screen_elements(screen)
        if ui_element:
            elem_name, ex, ey = ui_element
            self.log(f"[UI Scanner] Tìm thấy phần tử tương tác: {elem_name} tại ({ex}, {ey}) -> Tự động chạm để giải phóng màn hình UNKNOWN")
            import random
            rx = ex + random.randint(-3, 3)
            ry = ey + random.randint(-3, 3)
            self.adb.tap(rx, ry)
            time.sleep(0.5)
            self._unknown_streak = 0
            return True

        # 3. Automated recovery via Back / Esc key
        if self.enable_recovery and self._unknown_streak < 3:
            self.log(f"[Recovery] Thử khôi phục màn hình UNKNOWN lần {self._unknown_streak}/3 (nhấn phím Back/ESC)...")
            recovered, new_state = self.recovery.attempt_recovery(self._unknown_streak)
            if recovered:
                self.log(f"[RECOVERY] Phục hồi thành công sang trạng thái: {new_state.value if hasattr(new_state, 'value') else new_state}")
                self._unknown_streak = 0
                return True

        # 4. Halt after 3 consecutive unknowns
        if self._unknown_streak >= 3:
            if self.notifier and hasattr(self.notifier, "notify_unknown_streak"):
                self.notifier.notify_unknown_streak(self._unknown_streak)
            if self.notifier and hasattr(self.notifier, "notify_unknown_halt"):
                self.notifier.notify_unknown_halt()
            self.stop(reason="Gặp màn hình UNKNOWN 3 lần liên tiếp")
            return False
        return True

    def _handle_match_done(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.MATCH_DONE, screen, details)

    def _handle_in_match(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.IN_MATCH, screen, details)

    def _handle_popup(self, screen: Any, details: Dict[str, Any], state: State = State.POPUP_EFFECT) -> bool:
        return self._dispatch_state(state, screen, details)

    def _handle_chaos_map(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.CHAOS_MAP, screen, details)

    def _handle_chaos_after_battle(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.CHAOS_AFTER_BATTLE, screen, details)

    def _handle_chaos_equipment(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.CHAOS_EQUIPMENT, screen, details)

    def _handle_chaos_safe_zone(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.CHAOS_SAFE_ZONE, screen, details)

    def _handle_chaos_choose_epiphany(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.CHAOS_CHOOSE_EPIPHANY, screen, details)

    def _handle_chaos_obtain_reward(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.CHAOS_OBTAIN_REWARD, screen, details)

    def _handle_chaos_event(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.CHAOS_EVENT, screen, details)

    def _handle_pre_match(self, screen: Any, details: Dict[str, Any], state: State = State.PRE_MATCH_MISSION) -> bool:
        return self._dispatch_state(state, screen, details)

    def _handle_story_map(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.STORY_MAP, screen, details)

    def _handle_story_dialogue(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.STORY_DIALOGUE, screen, details)

    def _handle_transitioning(self, screen: Any, details: Dict[str, Any]) -> bool:
        return self._dispatch_state(State.TRANSITIONING, screen, details)

    @staticmethod
    def _resolve_chaos_island_coord(
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
                return TAP_COORDS["chaos_island_2_middle"], "Đảo GIỮA"
            elif IslandChoice.MIDDLE in available and IslandChoice.BOTTOM in available:
                if island == IslandChoice.MIDDLE:
                    return TAP_COORDS["chaos_island_2_middle"], "Đảo GIỮA"
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
        return TAP_COORDS["chaos_island_3_middle"], "Đảo GIỮA"

    @staticmethod
    def _cleanup_unknown_screenshots(logs_dir: str = LOGS_DIR, max_keep: int = 50) -> int:
        import glob
        pattern = os.path.join(logs_dir, "unknown_*.png")
        files = glob.glob(pattern)
        if len(files) <= max_keep:
            return 0
        files.sort(key=lambda p: os.path.getmtime(p))
        num_to_delete = len(files) - max_keep
        deleted_count = 0
        for p in files[:num_to_delete]:
            try:
                os.remove(p)
                deleted_count += 1
            except Exception:
                pass
        return deleted_count

    def _handle_stall(
        self,
        screen: Any,
        confirmed_state: State,
        details: Dict[str, Any],
        elapsed_stall: float
    ) -> bool:
        """Handles stall condition with diagnostic dump and auto-recovery."""
        import json
        from datetime import datetime

        rec = details.get("recognizer", "N/A")
        sc = details.get("score", details.get("confidence", 0.0))
        mg = details.get("margin", 0.0)
        ru = details.get("runner_up")
        if ru is None:
            ranked = details.get("ranked", [])
            if len(ranked) > 1:
                ru = ranked[1]
        ru_str = f"{ru[0]} ({float(ru[1]):.2f})" if ru and isinstance(ru, (tuple, list)) and len(ru) >= 2 else str(ru)

        self.log(
            f"⚠️ Cảnh báo kẹt màn hình ({confirmed_state.value}) quá {elapsed_stall:.1f}s | "
            f"Recognizer={rec} (Score={float(sc):.2f}, Margin={float(mg):.2f}, Runner-up={ru_str})"
        )

        if self.enable_recovery:
            attempt = self._stall_recovered_count + 1
            if attempt < 3 and elapsed_stall < 45.0:
                recovered, new_state = self.recovery.attempt_recovery(attempt)
                if recovered and new_state and new_state != confirmed_state:
                    self._stall_recovered_count = 0
                    self._last_progress_time = time.time()
                    return True
                else:
                    self._stall_recovered_count = attempt
                    return True
            else:
                if hasattr(self, "recovery") and self.recovery:
                    recovered, new_state = self.recovery.attempt_recovery(attempt)
                    if recovered and new_state and new_state != confirmed_state:
                        self._stall_recovered_count = 0
                        self._last_progress_time = time.time()
                        return True
                self._halt(f"Tự động phục hồi thất bại sau {attempt} lần thử", freq=600, duration=800)
                return False

        # If recovery disabled: dump diagnostics and halt
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(LOGS_DIR, exist_ok=True)
        img_path = os.path.join(LOGS_DIR, f"stall_{ts}.png")
        json_path = os.path.join(LOGS_DIR, f"stall_{ts}.json")

        try:
            if screen is not None:
                cv2.imwrite(img_path, screen)
        except Exception as e:
            self.logger.warning(f"Không thể lưu ảnh stall: {e}")

        diag_data = {
            "timestamp": ts,
            "state": confirmed_state.value,
            "elapsed": elapsed_stall,
            "recognizer": rec,
            "confidence": float(sc),
            "margin": float(mg),
            "runner_up": ru_str,
            "details": {k: str(v) for k, v in details.items()}
        }
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(diag_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.warning(f"Không thể lưu JSON stall: {e}")

        if getattr(self, "on_stall", None):
            try:
                self.on_stall(confirmed_state, elapsed_stall, img_path, json_path)
            except Exception:
                pass

        self._halt(f"Kẹt tại {confirmed_state.value} quá {elapsed_stall:.1f}s", freq=800, duration=600)
        return False

    def _execute_tap(
        self,
        action_name: str,
        x: int,
        y: int,
        screen: Any = None,
        expected_words: Any = None,
        score: Optional[float] = None
    ) -> bool:
        """Execute a direct tap with stall detection, template bypass, and 2-strike Hybrid OCR fallback."""
        # 1. Template High Confidence Bypass: Nếu template đã khớp rất cao (>= 0.88), tin tưởng template và bỏ qua OCR
        skip_ocr = False
        if score is not None and score >= 0.88:
            skip_ocr = True
            self.log(f"✅ [Hybrid OCR] Khớp template độ tin cậy cao ({score:.2f} >= 0.88) -> Bỏ qua kiểm tra OCR cho [{action_name}]")

        # 2. Hybrid OCR Verification
        if not skip_ocr and getattr(self, "enable_hybrid_verification", False) and screen is not None and expected_words:
            # Kiểm tra ảnh game thực tế 1600x900
            if getattr(screen, "shape", None) and screen.shape[:2] == (900, 1600):
                verified = False
                if hasattr(self.detector, "verify_button_text"):
                    verified = self.detector.verify_button_text(screen, (x, y), expected_words)
                else:
                    from czn_bot.vision.ocr import verify_button_text
                    verified = verify_button_text(screen, (x, y), expected_words)

                if not verified:
                    self._ocr_reject_count = getattr(self, "_ocr_reject_count", 0) + 1
                    if self._ocr_reject_count >= 2:
                        self.log(
                            f"⚠️ [Hybrid OCR] Thao tác [{action_name}] tại ({x}, {y}) đã bị OCR từ chối "
                            f"{self._ocr_reject_count} lần liên tiếp -> Bỏ qua OCR và ép thực hiện bấm nút (Force Tap) để giải phóng kẹt!"
                        )
                        self._ocr_reject_count = 0
                        # Tiếp tục thực thi tap bên dưới
                    else:
                        self.log(
                            f"⚠️ [Hybrid OCR] Hủy thao tác '{action_name}' tại ({x}, {y}) do text không khớp {expected_words} "
                            f"(Lần {self._ocr_reject_count}/2)"
                        )
                        return True
                else:
                    self._ocr_reject_count = 0
            else:
                # Fallback cho mock/test screens
                verified = False
                if hasattr(self.detector, "verify_button_text"):
                    verified = self.detector.verify_button_text(screen, (x, y), expected_words)
                else:
                    from czn_bot.vision.ocr import verify_button_text
                    verified = verify_button_text(screen, (x, y), expected_words)
                if not verified:
                    self.log(f"⚠️ [Hybrid OCR] Hủy thao tác '{action_name}' tại ({x}, {y}) do text không khớp {expected_words}")
                    return True

        if self._last_action == action_name:
            self._same_action_count += 1
        else:
            self._last_action = action_name
            self._same_action_count = 1

        if self._same_action_count > MAX_SAME_ACTION:
            self._halt(reason=f"Hành động '{action_name}' bấm {MAX_SAME_ACTION} lần không đổi màn!")
            return False

        actual_x, actual_y = x, y
        if getattr(self, "_jitter_next_tap", False):
            import random
            actual_x = max(10, min(1590, x + random.choice([-8, -4, 4, 8])))
            actual_y = max(10, min(890, y + random.choice([-8, -4, 4, 8])))
            self._jitter_next_tap = False
            self.log(f"-> Chạm Jitter [{action_name}] tại ({actual_x}, {actual_y}) (gốc: {x}, {y})")
        else:
            self.log(f"-> Chạm [{action_name}] tại ({actual_x}, {actual_y})")

        self.adb.tap(actual_x, actual_y)
        self.actions_done += 1
        self.stats.record_action()
        if screen is not None and isinstance(screen, np.ndarray) and screen.size > 0:
            self._last_action_screen = screen.copy()

        return True

    def check_frame_stability(
        self,
        screen: Optional[np.ndarray],
        prev_screen: Optional[np.ndarray] = None,
        threshold: Optional[float] = None
    ) -> Tuple[bool, float]:
        """
        [Mục 1] Kiểm tra độ ổn định màn hình bằng cv2.absdiff().
        So sánh giữa khung hình hiện tại và khung hình tham chiếu (prev_screen hoặc _last_raw_screen).

        Trả về:
            (is_stable: bool, diff_value: float)
            - is_stable: True nếu diff_value < threshold (màn hình ổn định, sẵn sàng nhận diện)
            - diff_value: Độ chênh lệch pixel trung bình [0.0 - 255.0]
        """
        if screen is None or getattr(screen, "size", 0) == 0:
            return False, 0.0

        ref = prev_screen if prev_screen is not None else getattr(self, "_last_raw_screen", None)
        if ref is None or getattr(ref, "size", 0) == 0:
            # Chưa có khung hình trước đó để so sánh -> coi là ổn định
            return True, 0.0

        if screen.shape != ref.shape:
            return False, 255.0

        thresh = threshold if threshold is not None else getattr(self, "frame_stability_thresh", FRAME_STABILITY_THRESHOLD)

        h, w = screen.shape[:2]
        rh, rw = 90, 160
        g_cur = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY) if len(screen.shape) == 3 else screen
        g_ref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY) if len(ref.shape) == 3 else ref
        g_cur = cv2.resize(g_cur, (rw, rh))
        g_ref = cv2.resize(g_ref, (rw, rh))

        diff = cv2.absdiff(g_cur, g_ref)
        diff_val = float(np.mean(diff))

        is_stable = diff_val < thresh
        return is_stable, diff_val

    def capture_stable_screen(
        self,
        delay: Optional[float] = None,
        threshold: Optional[float] = None
    ) -> Tuple[Optional[np.ndarray], bool, float]:
        """
        [Mục 1] Chụp 2 khung hình cách nhau ~150-200ms bằng ADB và kiểm tra độ ổn định.
        Trả về: (screen: np.ndarray, is_stable: bool, diff_value: float)
        """
        delay_sec = delay if delay is not None else getattr(self, "frame_stability_delay", FRAME_STABILITY_DELAY)
        try:
            frame1 = self.adb.screencap()
        except Exception as e_cap:
            self.logger.warning(f"capture_stable_screen frame 1 error: {e_cap}")
            return None, False, 0.0

        if frame1 is None or getattr(frame1, "size", 0) == 0:
            return None, False, 0.0

        time.sleep(delay_sec)
        try:
            frame2 = self.adb.screencap()
        except Exception as e_cap2:
            self.logger.warning(f"capture_stable_screen frame 2 error: {e_cap2}")
            return frame1, False, 0.0

        if frame2 is None or getattr(frame2, "size", 0) == 0:
            return frame1, False, 0.0

        is_stable, diff_val = self.check_frame_stability(frame2, frame1, threshold=threshold)
        return frame2, is_stable, diff_val

    def is_transition_allowed(
        self,
        from_state: Optional[Any],
        to_state: Any
    ) -> bool:
        """
        [Mục 2] Kiểm tra bước chuyển trạng thái có hợp lệ theo DEFAULT_ALLOWED_TRANSITIONS không.
        from_state và to_state có thể là State enum hoặc chuỗi str.
        """
        if not getattr(self, "enable_transition_validation", True):
            return True
        if from_state is None:
            return True

        from_key = from_state.value if hasattr(from_state, "value") else str(from_state)
        to_key = to_state.value if hasattr(to_state, "value") else str(to_state)

        if from_key in ("UNKNOWN", ""):
            return True
        if to_key in ("UNKNOWN", "TRANSITIONING"):
            return True
        if from_key == to_key:
            return True

        allowed_map = getattr(self, "allowed_transitions", DEFAULT_ALLOWED_TRANSITIONS)
        if from_key not in allowed_map:
            return True

        return to_key in allowed_map[from_key]

    def _format_decision_log(self, state: State, details: Dict[str, Any]) -> str:
        """[Mục 7] Format log chi tiết cho mỗi quyết định nhận diện state."""
        recognizer = details.get("recognizer", "OpenCV StateClassifier" if details.get("score") else "Unknown")
        score = details.get("score", details.get("confidence", 0.0))
        margin = details.get("margin", 0.0)
        runner_up = details.get("runner_up")
        if runner_up is None:
            ranked = details.get("ranked", [])
            if len(ranked) > 1:
                runner_up = ranked[1]

        if runner_up:
            if isinstance(runner_up, (tuple, list)) and len(runner_up) >= 2:
                runner_up_str = f"{runner_up[0]} ({float(runner_up[1]):.2f})"
            else:
                runner_up_str = str(runner_up)
        else:
            runner_up_str = "None"

        st_val = state.value if hasattr(state, "value") else str(state)
        score_val = float(score) if score is not None else 0.0
        margin_val = float(margin) if margin is not None else 0.0
        return (
            f"[VisionDecision] State={st_val} | "
            f"Recognizer={recognizer} | Confidence={score_val:.2f} | Margin={margin_val:.2f} | "
            f"Runner-up={runner_up_str}"
        )

    def _log_state_decision(self, state: State, details: Dict[str, Any]) -> None:
        msg = self._format_decision_log(state, details)
        self.logger.debug(msg)

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _detect_state(self, screen: np.ndarray) -> Tuple[State, Dict[str, Any]]:
        # 1. OpenCV (Template Matching) LUÔN ĐƯỢC CHẠY ĐẦU TIÊN!
        # Cực nhanh (~10ms), tọa độ pixel tuyệt đối chính xác từ template, không tốn API, không có độ trễ mạng.
        cv_state, cv_details = self.detector.detect(screen)
        if cv_state not in (State.UNKNOWN, State.TRANSITIONING):
            self._log_state_decision(cv_state, cv_details)
            return cv_state, cv_details

        # 2. AI Vision CHỈ ĐƯỢC GỌI khi OpenCV trả về UNKNOWN hoặc TRANSITIONING!
        has_ai = (
            getattr(self, "enable_ai_vision_detection", True)
            and getattr(self, "enable_chaos_ai", True)
            and self.rule_manager.get_api_key()
        )

        if has_ai:
            t0 = time.time()
            gray_before = (cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY) if len(screen.shape) == 3 else screen) if screen is not None and screen.size > 0 else None
            try:
                ai_state, ai_details = self.chaos_brain.detect_state_with_ai(screen, last_state=self._last_state)
                if ai_state != State.UNKNOWN:
                    ai_conf = float(ai_details.get("confidence", 0.90))
                    ai_details.setdefault("recognizer", "AI Vision")
                    ai_details.setdefault("score", ai_conf)
                    ai_details.setdefault("confidence", ai_conf)
                    ai_details.setdefault("margin", 0.0)
                    ai_details.setdefault("runner_up", None)
                    ai_details.setdefault("ranked", [(ai_state.value, ai_conf)])

                    # Chống ảnh cũ (Stale Frame Guard): nếu phản hồi mất > 1.5s, kiểm tra lại màn hình hiện tại
                    elapsed = time.time() - t0
                    if elapsed > 1.5 and gray_before is not None:
                        current_screen = self.adb.screencap()
                        if current_screen is not None and current_screen.shape == screen.shape:
                            gray_now = cv2.cvtColor(current_screen, cv2.COLOR_BGR2GRAY) if len(current_screen.shape) == 3 else current_screen
                            diff = cv2.absdiff(gray_before, gray_now)
                            diff_ratio = np.count_nonzero(diff > 35) / diff.size
                            if diff_ratio > 0.15:
                                self.log(
                                    f"⚠️ [AI Vision] Màn hình đã thay đổi ({diff_ratio*100:.1f}%) trong lúc chờ AI ({elapsed:.1f}s) "
                                    f"-> Hủy kết quả AI cũ và nhận diện lại trên khung hình mới!"
                                )
                                re_state, re_details = self.detector.detect(current_screen)
                                self._log_state_decision(re_state, re_details)
                                return re_state, re_details
                    self._log_state_decision(ai_state, ai_details)
                    return ai_state, ai_details
            except Exception as e:
                self.logger.warning(f"Lỗi AI Vision detect state: {e}")

        self._log_state_decision(cv_state, cv_details)
        return cv_state, cv_details

    def _run_loop(self) -> None:
        frame_history: List[Tuple[State, Dict[str, Any], np.ndarray]] = []
        max_history = max(CONFIRM_FRAMES, getattr(self, "invalid_transition_confirm_frames", INVALID_TRANSITION_CONFIRM_FRAMES))

        while not self._stop_event.is_set():
            try:
                screen = None
                for cap_attempt in range(3):
                    try:
                        screen = self.adb.screencap()
                        if screen is not None:
                            break
                    except Exception as e_cap:
                        if cap_attempt == 2:
                            raise e_cap
                        time.sleep(0.3)
            except Exception as e:
                self.log(f"Lỗi chụp màn hình ADB: {e}")
                self.notifier.notify_adb_error(str(e))
                self.stop(reason="Mất kết nối ADB")
                break

            # 1. [Mục 1] Frame Stability Check: kiểm tra độ ổn định màn hình trước khi nhận diện state
            is_stable = True
            diff_val = 0.0
            if getattr(self, "enable_frame_stability", True):
                if getattr(self, "stability_use_consecutive_cap", False):
                    screen2, is_stable, diff_val = self.capture_stable_screen(
                        delay=getattr(self, "frame_stability_delay", FRAME_STABILITY_DELAY),
                        threshold=self.frame_stability_thresh
                    )
                    if screen2 is not None:
                        screen = screen2
                else:
                    is_stable, diff_val = self.check_frame_stability(screen, self._last_raw_screen)

            if not is_stable:
                state = State.TRANSITIONING
                details = {
                    "transitioning": True,
                    "diff": diff_val,
                    "reason": "frame_unstable",
                    "score": 0.0,
                    "confidence": 0.0,
                    "margin": 0.0,
                    "recognizer": "frame_stability_check",
                    "runner_up": None,
                    "ranked": [("TRANSITIONING", 1.0)],
                }
                self.logger.debug(
                    f"[FrameStability] Màn hình chưa ổn định (diff={diff_val:.1f} >= {self.frame_stability_thresh}) -> Chờ khung hình ổn định (TRANSITIONING)"
                )
            else:
                state, details = self._detect_state(screen)

            self._last_raw_screen = screen.copy() if screen is not None and getattr(screen, "size", 0) > 0 else None

            frame_history.append((state, details, screen))
            if len(frame_history) > max_history:
                frame_history.pop(0)

            # 2. [Mục 2] State Transition Validation: kiểm soát bước nhảy state
            required_confirm = CONFIRM_FRAMES
            # Đối chiếu với state đã ổn định thực sự gần nhất (không bị lừa bởi các khung TRANSITIONING/UNKNOWN ở giữa)
            reference_state = self.current_state if self.current_state not in (State.UNKNOWN, State.TRANSITIONING) else (self._last_settled_state or self._last_state)

            if reference_state and state != reference_state and state not in (State.UNKNOWN, State.TRANSITIONING):
                if not self.is_transition_allowed(reference_state, state):
                    # Bước nhảy bất hợp lệ (ví dụ CHAOS_AFTER_BATTLE -> IN_MATCH, dù có hay không có TRANSITIONING ở giữa)
                    # Yêu cầu xác nhận nhiều khung hình hơn để loại bỏ nhận diện nhầm
                    required_confirm = max(CONFIRM_FRAMES + 2, getattr(self, "invalid_transition_confirm_frames", INVALID_TRANSITION_CONFIRM_FRAMES))
                    self.logger.warning(
                        f"[TransitionValidation] Bước nhảy bất hợp lệ: {reference_state.value if hasattr(reference_state, 'value') else reference_state} "
                        f"-> {state.value if hasattr(state, 'value') else state} "
                        f"-> Yêu cầu {required_confirm} khung hình liên tiếp để xác thực!"
                    )

            if hasattr(self, "temporal_filter") and self.temporal_filter:
                self.temporal_filter.push(state)

            if not (len(frame_history) >= required_confirm and all(f[0] == state for f in frame_history[-required_confirm:])):
                if self._stop_event.wait(min(0.2, max(0.05, self.loop_delay))):
                    break
                continue

            confirmed_state, confirmed_details, _ = frame_history[-1]
            if confirmed_state != self.current_state:
                # [Mục 7] Ghi log chi tiết quyết định nhận diện khi trạng thái được xác nhận chuyển đổi
                log_line = self._format_decision_log(confirmed_state, confirmed_details)
                self.log(f"-> Chuyển trạng thái: {log_line}")

            self.current_state = confirmed_state
            if confirmed_state not in (State.UNKNOWN, State.TRANSITIONING):
                self._last_settled_state = confirmed_state

            if self.on_state_change:
                try:
                    self.on_state_change(confirmed_state, confirmed_details)
                except Exception:
                    pass
            if self.on_frame:
                try:
                    self.on_frame(screen, confirmed_state, confirmed_details)
                except Exception:
                    pass

            if confirmed_state != State.UNKNOWN:
                self._unknown_streak = 0

            # Watchdog: Stall check với thời gian giới hạn riêng cho từng trạng thái (Item 2)
            now = time.time()

            is_frozen_battle = False
            if confirmed_state == State.IN_MATCH:
                if hasattr(self, "_last_in_match_screen") and self._last_in_match_screen is not None:
                    if screen is not None and screen.shape == self._last_in_match_screen.shape:
                        g_scr = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY) if len(screen.shape) == 3 else screen
                        g_last = cv2.cvtColor(self._last_in_match_screen, cv2.COLOR_BGR2GRAY) if len(self._last_in_match_screen.shape) == 3 else self._last_in_match_screen
                        diff = cv2.absdiff(g_scr, g_last)
                        motion_ratio = np.count_nonzero(diff > 25) / diff.size
                        if motion_ratio < 0.005:  # Khung hình tĩnh < 0.5% thay đổi
                            is_frozen_battle = True
                self._last_in_match_screen = screen.copy() if screen is not None else None

            # Xác định stall timeout cụ thể cho trạng thái này
            if confirmed_state == State.IN_MATCH and is_frozen_battle:
                timeout_for_state = self.stall_timeout  # Trận đấu đứng yên: 30s
            else:
                state_key = confirmed_state.value if hasattr(confirmed_state, "value") else str(confirmed_state)
                timeout_for_state = STATE_STALL_TIMEOUTS.get(
                    confirmed_state,
                    STATE_STALL_TIMEOUTS.get(state_key, self.stall_timeout)
                )

            if confirmed_state != self._last_state:
                self._last_progress_time = now
                self._stall_recovered_count = 0
                self._last_action_screen = None
            else:
                elapsed = now - self._last_progress_time
                # Kiểm chứng sau tap: nếu sau 2.0-3.0s màn hình không đổi, kích hoạt jitter cho cú tap kế tiếp
                if elapsed >= 2.5 and getattr(self, "_last_action_screen", None) is not None:
                    from czn_bot.vision.state_classifier import screen_changed
                    if not screen_changed(self._last_action_screen, screen, thresh=4.0):
                        self._jitter_next_tap = True

                if elapsed >= timeout_for_state:
                    if not self._handle_stall(screen, confirmed_state, confirmed_details, elapsed):
                        break
                    continue

            # Handle UNKNOWN streak via AI Vision & Offline Scanner
            if confirmed_state == State.UNKNOWN:
                if not self._handle_unknown(screen, confirmed_details):
                    break
                continue

            # Evaluate Flow
            if self.active_flow is None:
                self.active_flow = self._create_flow()

            action = self.active_flow.handle(confirmed_state, confirmed_details, screen)
            should_continue = self._execute_action(action, screen)
            if not should_continue:
                break

            self._last_state = confirmed_state
            if self.on_stats_update:
                try:
                    self.on_stats_update(self.stats.to_dict())
                except Exception:
                    pass

            if self._stop_event.wait(max(0.05, self.loop_delay)):
                break

        self.is_running = False

    def _execute_action(self, action: Action, screen: Optional[np.ndarray]) -> bool:
        """Executes the Action returned by Flow with safety checks."""
        if action.type == ActionType.STOP:
            if action.extra.get("defeat"):
                if self.notifier and hasattr(self.notifier, "notify_match_failed"):
                    self.notifier.notify_match_failed()
                self._halt(action.reason, freq=800, duration=600)
                return False
            elif action.extra.get("max_stages") or action.extra.get("max_retries"):
                if self.notifier and hasattr(self.notifier, "notify_max_retries"):
                    self.notifier.notify_max_retries(self.max_retries)
                self._halt(action.reason, freq=1200, duration=300)
                return False
            self.stop(reason=action.reason)
            return False

        if action.type == ActionType.NONE:
            return True

        if action.type == ActionType.WAIT:
            time.sleep(action.duration)
            return True

        if action.type == ActionType.BACK:
            self.adb.send_keyevent(4)
            time.sleep(0.5)
            return True

        if action.type == ActionType.SWIPE:
            self.log(f"Vuốt: {action.name}")
            dur_ms = int(action.duration * 1000) if action.duration else 500
            self.adb.swipe(action.x, action.y, action.x2, action.y2, duration_ms=dur_ms)
            self.actions_done += 1
            self.stats.record_action()
            return True

        if action.type == ActionType.TAP:
            act_name = action.name or f"Tap ({action.x}, {action.y})"
            success = self._execute_tap(
                act_name,
                action.x,
                action.y,
                screen=screen,
                expected_words=action.extra.get("expected_words"),
                score=action.extra.get("score")
            )
            if not success:
                return False

            if action.extra.get("halt_after"):
                self._halt(action.extra.get("reason", "Dừng theo yêu cầu của Flow"), freq=1200, duration=300)
                return False

            # Extra follow-up taps (e.g. confirming dialogs)
            extra_actions = action.extra.get("extra_actions", [])
            for extra_act in extra_actions:
                time.sleep(0.4)
                if extra_act[0] == "tap":
                    tx, ty = extra_act[1]
                    self.adb.tap(tx, ty)
                    self.actions_done += 1
                    self.stats.record_action()

            if action.extra.get("dialogue_skip"):
                self._last_action = None
                self._same_action_count = 0

            # Mode statistics tracking
            if "retry_number" in action.extra:
                self.retries_done = action.extra["retry_number"]
                self.stats.record_retry()
            elif "stage_number" in action.extra:
                self.retries_done = action.extra["stage_number"]
                self.stats.record_match_completed()
            elif "island" in action.extra:
                self.stats.record_chaos_choice(
                    action.extra["island"],
                    action.extra.get("score", 0.0),
                    action.extra.get("hp_percent", 1.0)
                )

            return True

        return True


# Backward compatibility alias
BotEngine = BotRunner
