"""
Bot execution engine.
Implements the main decision cycle:
capture -> confirm state (3 frames) -> single action -> wait -> repeat
"""
import os
import time
import threading
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, Callable
import cv2

try:
    import winsound
except ImportError:
    winsound = None

from config import (
    State, Mode, LeftButton, TAP_COORDS,
    CONFIRM_FRAMES, MAX_SAME_ACTION, LOGS_DIR,
    ENABLE_DYNAMIC_ISLAND_DETECTION, MAX_UNKNOWN_SCREENSHOTS,
    ENABLE_HYBRID_VERIFICATION, HYBRID_VERIFICATION_PAD
)
from adb_client import ADBClient
from detector import ScreenDetector
from stats_tracker import StatsTracker
from notifier import Notifier
from recovery import RecoveryManager
from chaos_ai_config import ChaosRuleManager
from chaos_vision import ChaosVision
from chaos_ai_brain import ChaosAIBrain


class BotEngine:
    def __init__(
        self,
        adb_client: Optional[ADBClient] = None,
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

        # Configurable settings
        self.mode: Mode = Mode.REPLAY
        self.loop_delay: float = 1.5
        self.max_retries: Optional[int] = None      # None = unlimited, or int
        self.auto_start_match: bool = False         # Auto enter if in pre-match screen
        self.enable_recovery: bool = False          # Automated recovery on UNKNOWN state
        self.enable_hybrid_verification: bool = ENABLE_HYBRID_VERIFICATION  # Thẩm định kép OCR trước khi click
        self.hybrid_pad: int = HYBRID_VERIFICATION_PAD
        self.chaos_strategy: str = "balanced"       # StrategyProfile: balanced, safe, aggressive
        self.enable_dynamic_islands: bool = ENABLE_DYNAMIC_ISLAND_DETECTION
        self.auto_pick_epiphany: bool = False       # Không tự chọn thẻ trong Chaos (để người chơi tự chọn)
        self.max_unknown_screenshots: int = MAX_UNKNOWN_SCREENSHOTS

        # AI-driven Chaos tactical modules
        self.rule_manager = ChaosRuleManager()
        self.chaos_vision = ChaosVision()
        self.chaos_brain = ChaosAIBrain(rule_manager=self.rule_manager)
        self.enable_chaos_ai: bool = True
        self.last_ai_decision: Optional[Dict[str, Any]] = None
        self.on_ai_decision: Optional[Callable[[Dict[str, Any]], None]] = None

        # State tracking
        self.is_running: bool = False
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Statistics
        self.retries_done: int = 0
        self.actions_done: int = 0
        self.current_state: State = State.UNKNOWN

        # Guard against stuck clicks
        self._last_action: Optional[str] = None
        self._same_action_count: int = 0
        self._last_state: Optional[State] = None
        self._unknown_streak: int = 0
        self._story_swipe_count: int = 0

        # Stall Watchdog (Giám sát bot dừng quá 30s)
        self.stall_timeout: float = 30.0
        self._last_progress_time: float = time.time()
        self._stall_recovered_count: int = 0
        self.on_stall: Optional[Callable[[State, float, str, str], None]] = None

        # Callbacks to UI
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_state_change: Optional[Callable[[State, dict], None]] = None
        self.on_frame: Optional[Callable[[Any, State, dict], None]] = None
        self.on_stats_update: Optional[Callable[[dict], None]] = None
        self.on_stopped: Optional[Callable[[str], None]] = None

        # File logger
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

    # ── Public API ──────────────────────────────
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
        self.retries_done = 0
        self.actions_done = 0
        self._cleanup_unknown_screenshots(getattr(self, "max_unknown_screenshots", MAX_UNKNOWN_SCREENSHOTS))
        self.stats.start_session()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        strat_label = self.chaos_strategy
        try:
            from strategy_profile import get_strategy_profile
            strat_label = get_strategy_profile(self.chaos_strategy).name
        except Exception:
            pass
        recovery_str = "BẬT" if self.enable_recovery else "TẮT"
        self.log(
            f"Bot bắt đầu. Chế độ: {self.mode.value}, "
            f"Chiến thuật: {strat_label}, "
            f"Delay: {self.loop_delay}s, "
            f"Max retry: {self.max_retries or 'Vô hạn'}, "
            f"Recovery: {recovery_str}"
        )

    def stop(self, reason: str = "Người dùng dừng") -> None:
        """Stop the bot execution, export performance stats, and notify listeners."""
        if not self.is_running:
            return
        self.is_running = False
        self._stop_event.set()
        self._unknown_streak = 0
        self.stats.record_stop(reason)
        self.log(f"Bot dừng: {reason}")

        # Export session summary report
        summary = ""
        try:
            summary = self.stats.format_summary()
            self.logger.info("\n" + summary)
            self.stats.export_json()
        except Exception as e:
            self.logger.error(f"Lỗi xuất báo cáo thống kê: {e}")

        # Send notification
        try:
            self.notifier.notify_bot_stopped(reason, summary)
        except Exception:
            pass

        self._safe_callback(self.on_stopped, reason)

    # ── Core Loop ───────────────────────────────
    def _run_loop(self) -> None:
        """Core decision loop: capture -> 3-frame confirmation -> handle state -> repeat."""
        frame_history: list[Tuple[State, dict, Any]] = []

        # Mapping state → handler
        handlers = {
            State.IN_MATCH: self._handle_in_match,
            State.POPUP_EFFECT: lambda s, d: self._handle_popup(s, d, State.POPUP_EFFECT),
            State.POPUP_DRAW_PILE: lambda s, d: self._handle_popup(s, d, State.POPUP_DRAW_PILE),
            State.POPUP_STAGE_INFO: lambda s, d: self._handle_popup(s, d, State.POPUP_STAGE_INFO),
            State.POPUP_MONSTER_INFO: lambda s, d: self._handle_popup(s, d, State.POPUP_MONSTER_INFO),
            State.POPUP_PAUSE: lambda s, d: self._handle_popup(s, d, State.POPUP_PAUSE),
            State.MATCH_DONE: self._handle_match_done,
            State.CHAOS_MAP: self._handle_chaos_map,
            State.CHAOS_AFTER_BATTLE: self._handle_chaos_after_battle,
            State.CHAOS_OBTAIN_REWARD: self._handle_chaos_obtain_reward,
            State.CHAOS_CHOOSE_EPIPHANY: self._handle_chaos_choose_epiphany,
            State.CHAOS_SAFE_ZONE: self._handle_chaos_safe_zone,
            State.PRE_MATCH_MISSION: lambda s, d: self._handle_pre_match(s, d, State.PRE_MATCH_MISSION),
            State.PRE_MATCH_TEAM: lambda s, d: self._handle_pre_match(s, d, State.PRE_MATCH_TEAM),
            State.STORY_MAP: self._handle_story_map,
            State.STORY_DIALOGUE: self._handle_story_dialogue,
            State.TRANSITIONING: self._handle_transitioning,
            State.UNKNOWN: self._handle_unknown,
        }

        while not self._stop_event.is_set():
            try:
                # 1. Capture screen with retry to tolerate momentary WinError/ADB spikes
                screen = None
                for cap_attempt in range(3):
                    try:
                        screen = self.adb.screencap()
                        if screen is not None:
                            break
                    except Exception as e_cap:
                        if cap_attempt == 2:
                            raise e_cap
                        time.sleep(0.4)
            except Exception as e:
                self.log(f"Lỗi chụp màn hình ADB: {e}")
                self.notifier.notify_adb_error(str(e))
                self._halt("Mất kết nối ADB", freq=500)
                break

            # 2. Detect single frame
            state, details = self.detector.detect(screen)
            frame_history.append((state, details, screen))
            if len(frame_history) > CONFIRM_FRAMES:
                frame_history.pop(0)

            # 3. Check confirmation: need CONFIRM_FRAMES consecutive matches
            if not (len(frame_history) == CONFIRM_FRAMES and all(f[0] == state for f in frame_history)):
                confirm_wait = min(0.25, max(0.05, self.loop_delay))
                if self._stop_event.wait(confirm_wait):
                    break
                continue

            confirmed_state, confirmed_details, _ = frame_history[-1]
            self.current_state = confirmed_state
            self._safe_callback(self.on_state_change, confirmed_state, confirmed_details)
            self._safe_callback(self.on_frame, screen, confirmed_state, confirmed_details)

            if confirmed_state != State.UNKNOWN:
                self._unknown_streak = 0

            # 3.1. Stall Watchdog: Giám sát nếu bot dừng ở một chỗ quá stall_timeout (30s)
            # Miễn trừ: IN_MATCH (đang đánh quái), CHAOS_CHOOSE_EPIPHANY (người chơi tự chọn thẻ),
            # và STORY_DIALOGUE (hội thoại / cắt cảnh cốt truyện có thể kéo dài nhiều phút)
            STALL_EXEMPT_STATES = {
                State.IN_MATCH,
                State.CHAOS_CHOOSE_EPIPHANY,
                State.STORY_DIALOGUE,
            }

            now = time.time()
            if confirmed_state != self._last_state:
                self._last_progress_time = now
                self._stall_recovered_count = 0
            elif confirmed_state in STALL_EXEMPT_STATES:
                self._last_progress_time = now
                self._stall_recovered_count = 0
            else:
                elapsed_stall = now - self._last_progress_time
                if elapsed_stall >= self.stall_timeout:
                    should_continue = self._handle_stall(
                        screen, confirmed_state, confirmed_details, elapsed_stall
                    )
                    if not should_continue:
                        break

            # 4. Dispatch via handlers dictionary
            prev_actions = self.actions_done
            handler = handlers.get(confirmed_state)
            if handler:
                try:
                    should_continue = handler(screen, confirmed_details)
                    if not should_continue:
                        break
                except Exception as e:
                    self.log(f"❌ Lỗi xử lý {confirmed_state.value}: {e}")
                    logger.exception("Error in state handler")
            else:
                self.log(f"State chưa được xử lý: {confirmed_state}")

            self._last_state = confirmed_state

            # Reset frame history only after a tap action was performed
            if self.actions_done > prev_actions:
                frame_history.clear()

            self._emit_stats()

            # Wait loop delay before next screencap
            if self._stop_event.wait(max(0.05, self.loop_delay)):
                break

        self.is_running = False

    # ── State Handlers (mỗi state 1 method) ─────
    def _handle_in_match(self, screen: Any, details: Dict[str, Any]) -> bool:
        """Handle IN_MATCH state: passively wait during combat, reset click guard."""
        if self._last_state != State.IN_MATCH:
            self.log("Trạng thái: IN_MATCH (Đang trong trận - Không bấm)")
        self._last_action = None
        self._same_action_count = 0
        return True

    def _handle_popup(self, screen: Any, details: Dict[str, Any], state: State) -> bool:
        """Handle popup overlays by closing them via detected or default coordinates."""
        if state == State.POPUP_MONSTER_INFO:
            close_pt = details.get("close_coord", TAP_COORDS["close_monster_info"])
            action_name = "Đóng Monster Info"
        elif state == State.POPUP_PAUSE:
            close_pt = details.get("close_coord", TAP_COORDS["close_x_default"])
            action_name = "Đóng Pause"
        else:
            close_pt = details.get("close_coord", TAP_COORDS["close_x_default"])
            action_name = f"Đóng {state.value}"

        return self._execute_tap(action_name, *close_pt)

    def _handle_match_done(self, screen: Any, details: Dict[str, Any]) -> bool:
        """Handle end-of-match screen, stamina verification, and Replay / Progress logic."""
        left_btn = details.get("left_button")
        self.log(f"Trạng thái: MATCH_DONE (Nút trái: {left_btn.value if left_btn else 'None'})")

        if left_btn == LeftButton.RETRY_DISABLED:
            self.log("⚠️ ĐÃ HẾT THỂ LỰC!")
            self.stats.record_stamina_exhausted()
            self.notifier.notify_stamina_depleted()
            self._halt("Hết thể lực (Nút Retry bị xám)", freq=1500, duration=800)
            return False

        if self.mode == Mode.REPLAY:
            if left_btn == LeftButton.RETRY:
                if self.max_retries is not None and self.retries_done >= self.max_retries:
                    self.notifier.notify_max_retries(self.max_retries)
                    self._halt(f"Đã đạt giới hạn Retry ({self.max_retries})", freq=1200)
                    return False

                self.retries_done += 1
                self.stats.record_retry()
                self.log(f"Thực hiện Retry lần thứ {self.retries_done}")
                return self._execute_tap(
                    "Bấm Retry",
                    *TAP_COORDS["left_button"],
                    screen=screen,
                    expected_words=["retry", "thử lại"]
                )
            else:
                self.stats.record_match_completed()
                self._execute_tap(
                    "Bấm Confirm (Thoát)",
                    *TAP_COORDS["right_button"],
                    screen=screen,
                    expected_words=["confirm", "xác nhận", "ok"]
                )
                self._halt("Hoàn thành màn chơi (Next Mission)", freq=1200, duration=400)
                return False

        elif self.mode == Mode.PROGRESS:
            if left_btn == LeftButton.NEXT_MISSION:
                if self.max_retries is not None and self.retries_done >= self.max_retries:
                    self.notifier.notify_max_retries(self.max_retries)
                    self._halt(f"Đã đạt giới hạn số màn chơi ({self.max_retries})", freq=1200)
                    return False

                self.retries_done += 1
                self.stats.record_match_completed()
                limit_str = f"/{self.max_retries}" if self.max_retries else ""
                self.log(f"Thực hiện Next Mission lần thứ {self.retries_done}{limit_str}")
                return self._execute_tap(
                    "Bấm Next Mission",
                    *TAP_COORDS["left_button"],
                    screen=screen,
                    expected_words=["next", "mission", "tiếp"]
                )
            else:
                self.stats.record_match_completed()
                self._execute_tap(
                    "Bấm Confirm",
                    *TAP_COORDS["right_button"],
                    screen=screen,
                    expected_words=["confirm", "xác nhận", "ok"]
                )
                self._halt("Dừng do màn kết thúc với Retry")
                return False

        elif self.mode == Mode.STORY:
            # Story mode: victory -> Confirm to claim rewards and return to map
            # A true defeat has NO rewards, and has a confident retry button.
            # If rewards or confirm button are present, it is VICTORY.
            reward_score = details.get("reward_score", 0.0)
            confirm_score = details.get("confirm_score", 0.0)
            has_rewards = reward_score >= 0.70
            has_confirm = confirm_score >= 0.70

            # Only consider defeat if Retry button is present and there are NO rewards / confirm
            if left_btn == LeftButton.RETRY and not has_rewards and not has_confirm:
                self.log("⚠️ Thua trận cốt truyện!")
                self.notifier.notify_match_failed()
                self._halt("Dừng bot do thất bại trong ải cốt truyện (Thua trận)", freq=800, duration=600)
                return False

            if self.max_retries is not None and self.retries_done >= self.max_retries:
                self.notifier.notify_max_retries(self.max_retries)
                self._halt(f"Đã đạt giới hạn số ải cốt truyện ({self.max_retries})", freq=1200)
                return False

            self.retries_done += 1
            self.stats.record_match_completed()
            limit_str = f"/{self.max_retries}" if self.max_retries else ""
            self.log(f"-> Hoàn thành ải cốt truyện (Ải {self.retries_done}{limit_str}). Bấm Confirm nhận thưởng.")
            confirm_pt = details.get("confirm_coord") or TAP_COORDS["right_button"]
            return self._execute_tap(
                "Bấm Confirm (Cốt truyện)",
                *confirm_pt,
                screen=screen,
                expected_words=["confirm", "xác nhận", "ok"]
            )

        return True  # CHAOS mode ở MATCH_DONE thì bỏ qua

    @staticmethod
    def _resolve_chaos_island_coord(
        best_island: Any,
        total_islands: int,
        available_islands: Optional[Any] = None,
    ) -> Tuple[Tuple[int, int], str]:
        """Resolve screen tap coordinates and label based on island choice and count."""
        from chaos_pathfinder import IslandChoice
        if total_islands == 1:
            coord = TAP_COORDS.get("chaos_island_1_middle", (1280, 520))
            name = "Đảo duy nhất"
        elif total_islands == 2:
            if best_island == IslandChoice.TOP:
                coord = TAP_COORDS.get("chaos_island_2_top", (1250, 240))
                name = "Đảo TRÊN (2 đảo)"
            elif best_island == IslandChoice.MIDDLE:
                coord = TAP_COORDS.get("chaos_island_2_middle", TAP_COORDS.get("chaos_island_2_bottom", (1330, 420)))
                name = "Đảo GIỮA (2 đảo)"
            else:  # IslandChoice.BOTTOM
                if available_islands and IslandChoice.TOP in available_islands and IslandChoice.MIDDLE not in available_islands:
                    coord = TAP_COORDS.get("chaos_island_3_bottom", (1100, 800))
                else:
                    coord = TAP_COORDS.get("chaos_island_2_bottom", (1330, 420))
                name = "Đảo DƯỚI (2 đảo)"
        else:
            key = f"chaos_island_3_{best_island.value}"
            coord = TAP_COORDS.get(key, TAP_COORDS.get(f"chaos_island_{best_island.value}", (1280, 520)))
            isl_name = "TRÊN" if best_island == IslandChoice.TOP else ("GIỮA" if best_island == IslandChoice.MIDDLE else "DƯỚI")
            name = f"Đảo {isl_name}"

        return coord, name

    def _handle_chaos_map(self, screen: Any, details: Dict[str, Any]) -> bool:
        """Xử lý màn hình chọn đảo Chaos. Trả về False nếu cần dừng bot."""
        self.log("Trạng thái: CHAOS_MAP (Bản đồ chọn đảo Chaos)")

        if self.mode != Mode.CHAOS:
            self.log(f"⚠️ Phát hiện bản đồ Chaos nhưng đang ở chế độ {self.mode.value} → Bỏ qua.")
            return True

        try:
            from chaos_hp_reader import get_team_hp
            from chaos_map_reader import parse_chaos_minimap, detect_3d_island_coords
            from chaos_pathfinder import select_best_island, IslandChoice

            hp_percent, is_low_hp = get_team_hp(screen)
            mode_str = "SINH TỒN (< 60%)" if is_low_hp else "TẤN CÔNG (>= 60%)"
            self.log(f"Máu đội: {hp_percent:.1%} → {mode_str}")

            roots, adj, nodes, boss_ids = parse_chaos_minimap(screen)
            if not roots:
                self._save_unknown(screen)
                self._halt("Mini-map không hợp lệ hoặc bị che", freq=750)
                return False

            best_island, evaluations = select_best_island(
                roots, adj, nodes, boss_ids, hp_percent, strategy=self.chaos_strategy
            )

            for isl, ev in evaluations.items():
                status = (
                    f"Điểm: {ev.best_score:.1f}"
                    if ev.is_available and ev.best_path
                    else f"LOẠI ({ev.rejection_reason})"
                )
                self.log(f"  * Đảo {isl.value.upper()}: {status}")

            if best_island is None:
                # Nếu chỉ có 1 đảo khả dụng (đường độc đạo), tự động đi tiếp theo đảo duy nhất
                if roots and len(roots) == 1:
                    fallback_island = list(roots.keys())[0]
                    self.log(f"⚠️ Không tìm thấy đường tới Boss hoàn hảo, nhưng chỉ có 1 đảo duy nhất → Tiếp tục chọn đảo {fallback_island.value.upper()}")
                    best_island = fallback_island
                elif roots:
                    # Nếu có các đảo nhưng đồ thị nhận diện bị nhiễu: tự động chọn đảo khả dụng theo độ ưu tiên
                    for pref in [IslandChoice.MIDDLE, IslandChoice.TOP, IslandChoice.BOTTOM]:
                        if pref in roots:
                            fallback_island = pref
                            break
                    else:
                        fallback_island = list(roots.keys())[0]
                    self.log(f"⚠️ Đồ thị đường đi phức tạp, tự động chọn đảo khả dụng {fallback_island.value.upper()} để tiếp tục hành trình...")
                    best_island = fallback_island
                else:
                    self._save_unknown(screen)
                    self._halt("Không có đường đi an toàn tới Boss")
                    return False

            # Cho phép Cloud AI (Gemini) phân tích chiến thuật chọn đảo nếu có cấu hình API Key
            if getattr(self, "enable_chaos_ai", True) and hasattr(self, "chaos_brain") and self.rule_manager.get_api_key():
                try:
                    from chaos_vision import ResourceInfo
                    res_info = ResourceInfo(hp_percent=hp_percent, is_low_hp=is_low_hp, credits=0)
                    ai_decision = self.chaos_brain.decide_island(evaluations, res_info, fallback_island=best_island)
                    if ai_decision and "target_island" in ai_decision:
                        target_str = str(ai_decision["target_island"]).lower()
                        for cand in roots.keys():
                            if cand.value.lower() == target_str:
                                best_island = cand
                                reason = ai_decision.get("reason", "Chiến thuật tối ưu")
                                self.log(f"🤖 [AI Map] Cloud AI chọn Đảo {cand.value.upper()} | Lý do: {reason}")
                                break
                        self.last_ai_decision = ai_decision
                        if self.on_ai_decision:
                            self.on_ai_decision(ai_decision)
                except Exception as e_ai_map:
                    self.logger.warning(f"Lỗi AI đánh giá đảo: {e_ai_map}")

            # Ghi nhận chỉ số thống kê Chaos
            best_eval = evaluations.get(best_island)
            score = best_eval.best_score if (best_eval and best_eval.best_score != float("-inf")) else 0.0
            self.stats.record_chaos_choice(best_island.value, score, hp_percent)

            # Chọn tọa độ tĩnh chuẩn cấu hình
            static_coord, name = self._resolve_chaos_island_coord(
                best_island, len(roots), available_islands=set(roots.keys())
            )
            target_coord = static_coord

            # Nếu bật nhận diện động 3D, quét vị trí thực tế trên màn hình
            if getattr(self, "enable_dynamic_islands", True):
                try:
                    dyn_coords = detect_3d_island_coords(screen, expected_choices=list(roots.keys()))
                    if best_island in dyn_coords:
                        target_coord = dyn_coords[best_island]
                        self.log(f"→ Nhận diện động 3D: {name} tại {target_coord} (Tọa độ gốc: {static_coord})")
                    else:
                        self.log(f"→ Dùng tọa độ cấu hình: {name} tại {static_coord}")
                except Exception as e_dyn:
                    self.logger.warning(f"Lỗi nhận diện động 3D đảo Chaos: {e_dyn}")
                    self.log(f"→ Dùng tọa độ cấu hình: {name} tại {static_coord}")
            else:
                self.log(f"→ Dùng tọa độ cấu hình: {name} tại {static_coord}")

            # Nếu đang thử lại (lần 2+), đổi tọa độ offset hoặc thử đảo thay thế để không bao giờ bị kẹt
            if self._last_action == name and self._same_action_count >= 1:
                alt_islands = [k for k in roots.keys() if k != best_island]
                if self._same_action_count >= 2 and alt_islands:
                    alt_isl = alt_islands[0]
                    alt_coord, alt_name = self._resolve_chaos_island_coord(
                        alt_isl, len(roots), available_islands=set(roots.keys())
                    )
                    self.log(f"⚠️ Thử đảo thay thế {alt_name} tại {alt_coord} sau {self._same_action_count} lần bấm...")
                    name = alt_name
                    target_coord = alt_coord
                else:
                    target_coord = (target_coord[0], max(100, target_coord[1] - 40))
                    self.log(f"⚠️ Thử lại với tọa độ offset: {target_coord}")

            self.log(f"→ CHỌN {name} tại {target_coord} (Điểm: {score:.1f})")
            return self._execute_tap(name, *target_coord)

        except Exception as e:
            self.log(f"Lỗi xử lý Chaos Map: {e}")
            self._save_unknown(screen)
            self._halt(f"Lỗi xử lý Chaos: {e}")
            return False


    def _handle_chaos_after_battle(self, screen: Any, details: Dict[str, Any]) -> bool:
        """Handle Chaos post-battle screen: tap Leave button to return to map."""
        self.log("Trạng thái: CHAOS_AFTER_BATTLE (Màn hình nút Leave)")
        if self.mode != Mode.CHAOS:
            self.log(f"⚠️ Phát hiện nút Leave nhưng bot đang ở chế độ {self.mode.value} -> Bỏ qua.")
            return True

        if self.max_retries is not None and self.retries_done >= self.max_retries:
            self.notifier.notify_max_retries(self.max_retries)
            self._halt(f"Đã đạt giới hạn số trận Chaos ({self.max_retries})", freq=1200)
            return False

        if details.get("is_equipment"):
            self.log("[CHAOS] Màn hình chọn trang bị: Tự động chọn và Confirm...")
            self.adb.tap(500, 350)
            time.sleep(0.3)
            self.adb.tap(1150, 520)
            time.sleep(0.3)
            self.adb.tap(1360, 806)
            self._last_action = None
            self._same_action_count = 0
            return True

        self.retries_done += 1
        self.stats.record_match_completed()
        leave_coord = details.get("leave_coord", TAP_COORDS["chaos_leave_button"])
        limit_str = f"/{self.max_retries}" if self.max_retries else ""
        self.log(f"-> Bấm nút Leave để quay lại bản đồ chọn đường (Trận {self.retries_done}{limit_str}).")
        return self._execute_tap(
            "Bấm Leave",
            *leave_coord,
            screen=screen,
            expected_words=["leave", "rời", "thoát", "confirm", "continue", "tiếp"]
        )

    def _handle_chaos_obtain_reward(self, screen: Any, details: Dict[str, Any]) -> bool:
        """Handle Chaos post-battle Obtain screen: tap Obtain button to claim loot and return to map."""
        self.log("Trạng thái: CHAOS_OBTAIN_REWARD (Màn hình nhận thưởng trận đánh) -> Bấm Obtain nhận thưởng...")
        obtain_coord = details.get("obtain_coord", TAP_COORDS.get("chaos_obtain_button", (1380, 830)))
        return self._execute_tap(
            "Bấm Obtain",
            *obtain_coord,
            screen=screen,
            expected_words=["obtain", "skip", "nhận", "thu thập"]
        )

    def _handle_chaos_choose_epiphany(self, screen: Any, details: Dict[str, Any]) -> bool:
        """Xử lý màn hình chọn hiệu ứng Epiphany / Thẻ bài / Số phận bằng Cloud AI."""
        if self._last_state != State.CHAOS_CHOOSE_EPIPHANY:
            self.log("Trạng thái: CHAOS_CHOOSE_EPIPHANY (Chọn hiệu ứng Epiphany / Thẻ Chaos)...")
            self.beep(freq=1200, duration_ms=200)
            self._epiphany_wait_count = 0

        self._epiphany_wait_count = getattr(self, "_epiphany_wait_count", 0) + 1
        self._last_action = None
        self._same_action_count = 0
        self._unknown_streak = 0

        # Nếu cờ auto_pick_epiphany được bật: Đợi 1 nhịp ổn định hoạt ảnh (wait_count >= 2) rồi gọi AI ra quyết định
        if getattr(self, "auto_pick_epiphany", False) and self._epiphany_wait_count >= 2:
            is_choose_fate = details.get("score_choose_fate", 0) >= 0.70
            is_remove_card = details.get("score_remove_card", 0) >= 0.70

            if is_remove_card:
                self.log("[CHAOS AI] Màn hình sao chép/xóa thẻ: Bấm Skip và Confirm...")
                self.adb.tap(1147, 837)
                time.sleep(0.5)
                self.adb.tap(1055, 569)
                self._epiphany_wait_count = 0
                return True

            resources = self.chaos_vision.extract_resources(screen)

            if is_choose_fate:
                self.log("[CHAOS AI] Đang phân tích các lựa chọn Số phận (Choose Fate)...")
                choices = self.chaos_vision.extract_event_choices(screen)
                decision = self.chaos_brain.decide_event(choices, resources)
                self.last_ai_decision = decision
                if self.on_ai_decision:
                    self.on_ai_decision(decision)

                target_idx = decision.get("target_index", 0)
                reason = decision.get("reason", "AI chọn phương án tối ưu")
                self.log(f"🤖 [AI Fate] Chọn lựa chọn {target_idx + 1} | Lý do: {reason}")

                tap_coord = choices[target_idx].tap_coord if target_idx < len(choices) else (500, 450)
                import random
                rx = tap_coord[0] + random.randint(-3, 3)
                ry = tap_coord[1] + random.randint(-3, 3)
                self.adb.tap(rx, ry)
                time.sleep(0.6)

                confirm_btn = self.chaos_vision.find_action_button(screen, "confirm") or (1425, 837)
                self.adb.tap(confirm_btn[0] + random.randint(-3, 3), confirm_btn[1] + random.randint(-3, 3))

            else:
                self.log("[CHAOS AI] Đang phân tích các thẻ bài và kiểm tra biến thể...")
                cards = self.chaos_vision.extract_cards(screen, num_cards=3)
                decision = self.chaos_brain.decide_card(cards, resources)
                self.last_ai_decision = decision
                if self.on_ai_decision:
                    self.on_ai_decision(decision)

                target_idx = decision.get("target_index", 1)
                reason = decision.get("reason", "AI chọn thẻ tối ưu")
                chosen_card_name = cards[target_idx].title if target_idx < len(cards) and cards[target_idx].title else f"Thẻ {target_idx + 1}"
                self.log(f"🤖 [AI Thẻ Bài] Chọn {chosen_card_name} [{cards[target_idx].variant if target_idx < len(cards) else ''}] | Lý do: {reason}")

                tap_coord = cards[target_idx].tap_coord if target_idx < len(cards) else (800, 460)
                import random
                rx = tap_coord[0] + random.randint(-3, 3)
                ry = tap_coord[1] + random.randint(-3, 3)
                self.adb.tap(rx, ry)
                time.sleep(0.6)

                confirm_btn = self.chaos_vision.find_action_button(screen, "confirm") or (1426, 837)
                self.adb.tap(confirm_btn[0] + random.randint(-3, 3), confirm_btn[1] + random.randint(-3, 3))

            self._epiphany_wait_count = 0
            time.sleep(0.8)
            return True

        time.sleep(1.0)
        return True

    def _handle_chaos_safe_zone(self, screen: Any, details: Dict[str, Any]) -> bool:
        """Xử lý trạm nghỉ (Safe Zone / Campfire) trong chế độ Chaos: Bấm Skip và xác nhận bỏ qua để đi tiếp."""
        self.log("Trạng thái: CHAOS_SAFE_ZONE (Trạm nghỉ an toàn) -> Bấm Skip và Xác nhận bỏ qua...")
        skip_coord = details.get("skip_coord", TAP_COORDS["chaos_safe_zone_skip"])
        res = self._execute_tap(
            "Skip Safe Zone",
            *skip_coord,
            screen=screen,
            expected_words=["skip", "bỏ qua"]
        )
        if not res:
            return False
        time.sleep(0.8)
        confirm_coord = TAP_COORDS.get("chaos_safe_zone_confirm", (956, 568))
        self.adb.tap(*confirm_coord)
        self._last_action = None
        self._same_action_count = 0
        self._unknown_streak = 0
        return True

    def _handle_pre_match(self, screen: Any, details: Dict[str, Any], state: State) -> bool:
        """Handle pre-match screens (mission / team selection) if auto_start_match is enabled."""
        if not self.auto_start_match:
            return True

        if state == State.PRE_MATCH_MISSION:
            self.log("Trạng thái: PRE_MATCH_MISSION -> Bấm Enter vào đội hình")
            tap_pt = details.get("coord", TAP_COORDS["enter_mission"])
            return self._execute_tap(
                "Enter Mission",
                *tap_pt,
                screen=screen,
                expected_words=["enter", "vào"]
            )
        elif state == State.PRE_MATCH_TEAM:
            self.log("Trạng thái: PRE_MATCH_TEAM -> Bấm Enter bắt đầu trận")
            tap_pt = details.get("coord", TAP_COORDS["enter_team"])
            return self._execute_tap(
                "Enter Team",
                *tap_pt,
                screen=screen,
                expected_words=["enter", "bắt đầu", "vào trận"]
            )
        return True

    def _handle_unknown(self, screen: Any, details: Dict[str, Any]) -> bool:
        """Handle UNKNOWN state: beep alert, save screenshot, halt after 3 consecutive frames."""
        self._unknown_streak += 1
        self.stats.record_unknown()
        self.log(f"Trạng thái: UNKNOWN (Lần {self._unknown_streak}/3) -> Phát cảnh báo.")
        if self._unknown_streak == 1:
            self._save_unknown(screen)
        self.beep(freq=750, duration_ms=300)

        # Attempt automated state recovery on first and second unknown encounters if enabled
        if self.enable_recovery and self._unknown_streak < 3:
            recovered, new_state = self.recovery.attempt_recovery(self._unknown_streak)
            if recovered and new_state:
                self.log(f"[RECOVERY] Tự động phục hồi thành công sang trạng thái: {new_state.value}")
                self._unknown_streak = 0
                return True

        if self._unknown_streak >= 3:
            self.notifier.notify_unknown_halt()
            self.stop(reason="Phát hiện trạng thái UNKNOWN liên tiếp 3 lần - Dừng an toàn để người chơi xử lý")
            return False
        return True

    def _handle_transitioning(self, screen: Any, details: Dict[str, Any]) -> bool:
        """Handle TRANSITIONING state: animation/cutscene in progress, wait without action."""
        if self._last_state != State.TRANSITIONING:
            self.log("Trạng thái: TRANSITIONING (Animation/Chuyển cảnh - Đợi)")
        # Reset click guard — no action needed during transitions
        self._last_action = None
        self._same_action_count = 0
        return True

    def _handle_story_map(self, screen: Any, details: Dict[str, Any]) -> bool:
        """Handle STORY_MAP state: locate and tap next active node, swipe if needed, or switch chapter."""
        if self.mode != Mode.STORY:
            self.log(f"⚠️ Phát hiện bản đồ Cốt truyện nhưng đang ở chế độ {self.mode.value} -> Bỏ qua.")
            if self.mode == Mode.CHAOS and details.get("active_node") is None:
                self.log("[CHAOS] Đã về màn hình tổng kết/Battle Report sau khi hoàn thành Chaos -> Bấm Quay lại...")
                self.adb.tap(42, 45)
                time.sleep(1.0)
            return True

        self.log("Trạng thái: STORY_MAP (Bản đồ chọn ải cốt truyện)")
        active_node = details.get("active_node")
        if active_node:
            self._story_swipe_count = 0
            # Ensure tap target is safely within clickable stage card boundaries
            tap_x = max(100, min(active_node[0], 1520))
            tap_y = active_node[1]
            self.log(f"-> Phát hiện ải cốt truyện tiếp theo tại {active_node} -> Bấm vào ải ({tap_x}, {tap_y}).")
            return self._execute_tap("Vào ải cốt truyện", tap_x, tap_y)

        # If active node not visible on screen, try swiping left to find subsequent stages
        if self._story_swipe_count < 3:
            self._story_swipe_count += 1
            self.log(f"-> Không thấy ải mới trên màn hình. Vuốt bản đồ sang trái (Lần {self._story_swipe_count}/3)...")
            self.adb.swipe(1200, 500, 400, 500, duration_ms=500)
            time.sleep(1.2)
            self._last_action = None
            self._same_action_count = 0
            return True

        # If swiped 3 times and still no active node, attempt to advance to next chapter
        self._story_swipe_count = 0
        self.log("-> Đã kiểm tra hết bản đồ chương hiện tại. Bấm [>] để sang Chapter tiếp theo...")
        res = self._execute_tap("Chuyển Chapter tiếp theo", *TAP_COORDS["story_chapter_next"])
        time.sleep(1.5)
        self._last_action = None
        self._same_action_count = 0
        return res

    def _handle_story_dialogue(self, screen: Any, details: Dict[str, Any]) -> bool:
        """
        Handle STORY_DIALOGUE state: rapidly fast-forward through dialogues.
        Taps auto button, skip button, and screen text to pass dialogues in Story mode.
        In Chaos mode, does not skip story dialogues so players can read/follow the story.
        """
        if self.mode == Mode.CHAOS:
            if self._last_state != State.STORY_DIALOGUE:
                self.log(f"⚠️ Trạng thái: STORY_DIALOGUE (trong {self.mode.value}) -> Bỏ qua, không tự động skip cốt truyện.")
            # Reset action stall guard during dialogues
            self._last_action = None
            self._same_action_count = 0
            return True

        skip_coord = details.get("skip_coord", TAP_COORDS["story_dialogue_skip"])
        auto_coord = details.get("auto_coord", TAP_COORDS["story_dialogue_auto"])
        self.log(f"Trạng thái: STORY_DIALOGUE (trong {self.mode.value}) -> Tua nhanh lời thoại...")

        # Tap auto button at top-right
        self.adb.tap(*auto_coord)
        # Tap skip button at top-right
        for _ in range(3):
            self.adb.tap(*skip_coord)
            time.sleep(0.1)
        # Tap screen text area to rapidly advance dialogues
        self.adb.tap(800, 800)
        # Tap Confirm if "Skip story?" confirmation popup appears
        confirm_skip_coord = TAP_COORDS.get("story_skip_confirm", (950, 550))
        self.adb.tap(*confirm_skip_coord)

        # Reset action stall guard during dialogues
        self._last_action = None
        self._same_action_count = 0
        return True

    # ── Helpers ─────────────────────────────────
    def _handle_stall(
        self,
        screen: Any,
        confirmed_state: State,
        details: Dict[str, Any],
        elapsed_stall: float,
    ) -> bool:
        """
        Xử lý khi bot dừng lại ở một chỗ (trạng thái không đổi) quá stall_timeout (30s).
        Lưu ảnh bằng chứng, dump JSON chẩn đoán, ghi log cảnh báo và thực hiện phục hồi hoặc dừng an toàn.
        """
        import json
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        state_tag = confirmed_state.name.lower()
        img_name = f"stall_{timestamp}_{state_tag}.png"
        json_name = f"stall_{timestamp}_{state_tag}.json"
        img_path = os.path.join(LOGS_DIR, img_name)
        json_path = os.path.join(LOGS_DIR, json_name)

        if screen is not None:
            try:
                cv2.imwrite(img_path, screen)
            except Exception as e_img:
                self.logger.error(f"Lỗi lưu ảnh stall: {e_img}")

        diagnostic_info = {
            "timestamp": datetime.now().isoformat(),
            "state": confirmed_state.value,
            "elapsed_seconds": round(elapsed_stall, 2),
            "stall_timeout": self.stall_timeout,
            "actions_done": self.actions_done,
            "mode": self.mode.value,
            "details": {str(k): str(v) for k, v in details.items()},
            "last_action": self._last_action,
            "same_action_count": self._same_action_count,
            "unknown_streak": self._unknown_streak,
            "stall_recovered_count": self._stall_recovered_count,
        }
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(diagnostic_info, f, ensure_ascii=False, indent=2)
        except Exception as e_json:
            self.logger.error(f"Lỗi xuất JSON stall: {e_json}")

        self.log(
            f"⚠️ [WATCHDOG] CẢNH BÁO: Bot dừng lại ở trạng thái '{confirmed_state.value}' "
            f"quá {elapsed_stall:.1f}s không đổi màn!"
        )
        self.log(f"  → Đã lưu ảnh bằng chứng: {img_path}")
        self.log(f"  → Đã lưu chẩn đoán JSON: {json_path}")
        self.beep(freq=750, duration_ms=400)
        self._safe_callback(self.on_stall, confirmed_state, elapsed_stall, img_path, json_path)

        if self.enable_recovery:
            self._stall_recovered_count += 1
            self.log(
                f"[WATCHDOG RECOVERY] Thử tự động giải thoát (Lần {self._stall_recovered_count}/3)..."
            )
            recovered, new_state = self.recovery.attempt_recovery(self._stall_recovered_count)
            if recovered and new_state and new_state != confirmed_state:
                self.log(
                    f"✅ [WATCHDOG RECOVERY THÀNH CÔNG] Đã giải phóng bot sang trạng thái: {new_state.value}"
                )
                self._last_progress_time = time.time()
                self._stall_recovered_count = 0
                return True

            if self._stall_recovered_count >= 3 or elapsed_stall >= 45.0:
                self._halt(
                    f"Bot dừng lại ở {confirmed_state.value} quá {elapsed_stall:.0f}s - Phục hồi thất bại!",
                    freq=600,
                    duration=600,
                )
                return False
            else:
                self._last_progress_time = time.time() - 20.0
                return True
        else:
            self._halt(
                f"Bot dừng lại ở {confirmed_state.value} quá {elapsed_stall:.0f}s!",
                freq=600,
                duration=600,
            )
            return False

    def _execute_tap(
        self,
        action_name: str,
        x: int,
        y: int,
        screen: Any = None,
        expected_words: Optional[Union[str, List[str]]] = None
    ) -> bool:
        """
        Execute a tap with stall detection guard and optional Hybrid OCR Verification.
        """
        # Thẩm định kép OCR: Kiểm tra thực tế trên màn hình trước khi click
        if (
            self.enable_hybrid_verification
            and expected_words is not None
            and screen is not None
        ):
            # Chỉ áp dụng trên ảnh game thực tế 1600x900 (tránh ảnh giả lập/mock trong test)
            if getattr(screen, "shape", None) and screen.shape[:2] == (900, 1600):
                pad = getattr(self, "hybrid_pad", HYBRID_VERIFICATION_PAD)
                is_valid = self.detector.verify_button(screen, (x, y), expected_words, expand_pad=pad)
                if not is_valid:
                    self.log(
                        f"⚠️ [HYBRID OCR] Hủy click [{action_name}] tại ({x}, {y}): "
                        f"Không thấy chữ {expected_words} (Dương tính giả) -> Bỏ qua chờ frame tiếp theo."
                    )
                    self._last_action = None
                    self._same_action_count = 0
                    return True
                else:
                    self.log(f"✅ [HYBRID OCR] Xác thực thành công [{action_name}] với {expected_words}")

        if self._last_action == action_name:
            self._same_action_count += 1
        else:
            self._last_action = action_name
            self._same_action_count = 1

        if self._same_action_count > MAX_SAME_ACTION:
            self._halt(
                f"Hành động '{action_name}' bấm {MAX_SAME_ACTION} lần không đổi màn!",
                freq=600
            )
            return False

        # Human-like random offset (anti-cheat) - skip on mock ADB clients in tests
        target_x = x
        target_y = y
        is_mock = hasattr(self.adb, "_mock_name") or type(self.adb).__name__ in ("MagicMock", "MockADBClient")
        if getattr(self, "enable_click_jitter", True) and not is_mock:
            import random
            target_x = max(0, min(1599, target_x + random.randint(-3, 3)))
            target_y = max(0, min(899, target_y + random.randint(-3, 3)))

        self.log(f"-> Chạm [{action_name}] tại ({target_x}, {target_y}) (Lần {self._same_action_count})")
        self.adb.tap(target_x, target_y)
        self.actions_done += 1
        self.stats.record_action()
        self._emit_stats()

        # Human-like random delay
        if getattr(self, "enable_click_jitter", True) and not is_mock and self.mode == Mode.CHAOS:
            import random
            time.sleep(random.uniform(0.6, 1.2))

        return True

    def _halt(self, reason: str, freq: int = 600, duration: int = 500) -> None:
        """Dừng bot + phát chuông + gọi callback."""
        self.beep(freq=freq, duration_ms=duration)
        self.stop(reason=reason)

    def _safe_callback(self, callback: Optional[Callable], *args) -> None:
        """Call a callback safely without raising exceptions."""
        if callback:
            try:
                callback(*args)
            except Exception:
                pass

    @staticmethod
    def _cleanup_unknown_screenshots(max_keep: int = MAX_UNKNOWN_SCREENSHOTS) -> int:
        """
        Giữ lại tối đa max_keep ảnh unknown mới nhất trong LOGS_DIR.
        Xóa tất cả các ảnh sau tấm thứ max_keep (các ảnh cũ hơn vượt quá giới hạn).
        Trả về số lượng ảnh đã xóa.
        """
        try:
            import glob
            pattern = os.path.join(LOGS_DIR, "unknown_*.png")
            files = glob.glob(pattern)
            if len(files) <= max_keep:
                return 0
            # Sắp xếp theo mtime giảm dần (mới nhất đứng trước)
            files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
            to_delete = files[max_keep:]
            deleted_count = 0
            for f in to_delete:
                try:
                    os.remove(f)
                    deleted_count += 1
                except OSError:
                    pass
            return deleted_count
        except Exception:
            return 0

    def _save_unknown(self, screen: Any) -> None:
        """Save unrecognized screen snapshot to logs directory and prune excess images."""
        if screen is None:
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(LOGS_DIR, f"unknown_{timestamp}.png")
        try:
            cv2.imwrite(filepath, screen)
            self.log(f"[UNKNOWN] Đã lưu ảnh vào: {filepath}")
            # Sau 50 tấm unknown thì xóa tất cả ảnh cũ sau tấm đó
            max_limit = getattr(self, "max_unknown_screenshots", MAX_UNKNOWN_SCREENSHOTS)
            deleted = self._cleanup_unknown_screenshots(max_limit)
            if deleted > 0:
                self.log(f"[DỌN DẸP] Đã xóa {deleted} ảnh UNKNOWN cũ (duy trì tối đa {max_limit} tấm mới nhất)")
        except Exception as e:
            self.log(f"Lỗi lưu ảnh UNKNOWN: {e}")

    def _emit_stats(self) -> None:
        """Emit current statistics to UI callback."""
        self._safe_callback(self.on_stats_update, {
            "retries_done": self.retries_done,
            "actions_done": self.actions_done,
            "state": self.current_state.value if self.current_state else "NONE",
            "summary": self.stats.to_dict(),
        })

    def log(self, message: str) -> None:
        """Log message to rotating log file and UI callback."""
        self.logger.info(message)
        self._safe_callback(self.on_log, message)

    def beep(self, freq: int = 1000, duration_ms: int = 400) -> None:
        """Audible alert on warning or halt."""
        if winsound:
            try:
                winsound.Beep(freq, duration_ms)
            except Exception:
                try:
                    winsound.MessageBeep()
                except Exception:
                    pass
