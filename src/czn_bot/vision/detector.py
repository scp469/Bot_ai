"""
State detector for Chaos Zero Nightmare.
Uses OpenCV template matching on fixed/dynamic regions,
pixel-based heuristics, and per-template confidence thresholds.
"""
import os
import logging
from typing import Dict, Optional, Tuple, Any
import cv2
import numpy as np

from czn_bot.states import State, LeftButton
from czn_bot.constants import (
    TEMPLATES_DIR,
    DATA_TEMPLATES_DIR,
    LEGACY_TEMPLATES_DIR,
    TEMPLATES,
    MATCH_THRESHOLD,
    TEMPLATE_THRESHOLDS,
)
from czn_bot.coords import TAP_COORDS
from czn_bot.vision.map_reader import is_chaos_map_screen
from czn_bot.vision.ocr import get_ocr_service

logger = logging.getLogger("ChaosBot.Detector")


class ScreenDetector:
    def __init__(self, threshold: float = MATCH_THRESHOLD):
        self.threshold = threshold
        self.templates: Dict[str, np.ndarray] = {}
        self._load_templates()
        from czn_bot.vision.state_classifier import StateClassifier, DEFAULT_STATE_SPECS
        self.classifier = StateClassifier(DEFAULT_STATE_SPECS, matcher=self.match)

    def _load_templates(self) -> None:
        """Pre-load all template images."""
        search_dirs = [DATA_TEMPLATES_DIR, TEMPLATES_DIR, LEGACY_TEMPLATES_DIR]
        for key, fname in TEMPLATES.items():
            for d in search_dirs:
                if not d or not os.path.exists(d):
                    continue
                path = os.path.join(d, fname)
                if os.path.isfile(path):
                    img = cv2.imread(path)
                    if img is not None:
                        self.templates[key] = img
                        break

    def match(
        self,
        screen: np.ndarray,
        templ_key: str,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> Tuple[float, Optional[Tuple[int, int]]]:
        """
        Match a template against screen or sub-region.
        Returns (score, (center_x, center_y)) or (0.0, None).
        """
        templ = self.templates.get(templ_key)
        if templ is None or screen is None or screen.size == 0:
            return 0.0, None

        if region is not None:
            rx, ry, rw, rh = region
            h, w = screen.shape[:2]
            rx = max(0, min(rx, w - 1))
            ry = max(0, min(ry, h - 1))
            rw = max(1, min(rw, w - rx))
            rh = max(1, min(rh, h - ry))
            crop = screen[ry:ry + rh, rx:rx + rw]
            th, tw = templ.shape[:2]
            if crop.shape[0] < th or crop.shape[1] < tw:
                return 0.0, None
            res = cv2.matchTemplate(crop, templ, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            cx = rx + max_loc[0] + tw // 2
            cy = ry + max_loc[1] + th // 2
            return float(max_val), (cx, cy)
        else:
            th, tw = templ.shape[:2]
            if screen.shape[0] < th or screen.shape[1] < tw:
                return 0.0, None
            res = cv2.matchTemplate(screen, templ, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            return float(max_val), (cx, cy)

    def find_close_x(self, screen: np.ndarray) -> Tuple[int, int]:
        """Search top-right area for the close 'X' button."""
        region = (1350, 0, 240, 120)
        score, pt = self.match(screen, "close_x", region=region)
        if score >= 0.70 and pt:
            return pt
        return TAP_COORDS["close_x_default"]

    def verify_button(
        self,
        screen: np.ndarray,
        box_or_point: Any,
        expected_words: Any,
        expand_pad: int = 25
    ) -> bool:
        """Thẩm định kép (Hybrid Verification) vị trí nút bấm bằng OCR."""
        try:
            ocr = get_ocr_service()
            return ocr.verify_button_text(screen, box_or_point, expected_words, expand_pad=expand_pad)
        except Exception as e:
            logger.debug(f"verify_button OCR error: {e}")
            return False

    def find_text(self, screen: np.ndarray, text_query: str, region: Optional[Any] = None) -> Optional[Tuple[int, int]]:
        """Tìm tọa độ tâm của cụm từ trên màn hình bằng OCR."""
        try:
            ocr = get_ocr_service()
            return ocr.find_text(screen, text_query, region=region)
        except Exception as e:
            logger.debug(f"find_text OCR error: {e}")
            return None

    def _get_threshold(self, templ_key: str) -> float:
        return TEMPLATE_THRESHOLDS.get(templ_key, self.threshold)

    def _check_in_match_heuristic(self, screen: np.ndarray) -> bool:
        h, w = screen.shape[:2]
        if h < 200 or w < 600:
            return False

        hp_bar_crop = screen[5:45, 50:600]
        hsv_hp = cv2.cvtColor(hp_bar_crop, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv_hp, (35, 70, 70), (95, 255, 255))
        green_ratio = cv2.countNonZero(green_mask) / green_mask.size

        if green_ratio < 0.08:
            return False

        # Siết chặt heuristic: Thanh máu trong trận đấu thật phải có dạng thanh dài liên tục
        contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        max_bar_w = 0
        max_aspect = 0.0
        for c in contours:
            bx, by, bw, bh = cv2.boundingRect(c)
            if bw > max_bar_w:
                max_bar_w = bw
                max_aspect = bw / float(max(1, bh))

        # Nếu không có thanh ngang đủ dài (>=100px) hoặc không có tỷ lệ ngang >= 3.0 -> Loại bỏ (nhiễu loading screen)
        if max_bar_w < 100 or max_aspect < 3.0:
            return False

        # Siết chặt: Không để nhận nhầm màn hình Chaos Map (Minimap góc dưới trái)
        if h >= 900 and w >= 1600:
            minimap_area = screen[680:890, 10:270]
            hsv_mini = cv2.cvtColor(minimap_area, cv2.COLOR_BGR2HSV)
            mini_mask = cv2.inRange(hsv_mini, (10, 40, 40), (140, 255, 255))
            if (cv2.countNonZero(mini_mask) / mini_mask.size) > 0.15:
                return False

        center_crop = screen[300:600, 400:1200]
        gray_center = cv2.cvtColor(center_crop, cv2.COLOR_BGR2GRAY)
        if gray_center.mean() > 165:
            return False

        return True

    def _check_pre_match_heuristic(self, screen: np.ndarray) -> Optional[State]:
        h, w = screen.shape[:2]
        if h < 700 or w < 1400:
            return None

        back_btn_area = screen[20:55, 35:85]
        back_gray = cv2.cvtColor(back_btn_area, cv2.COLOR_BGR2GRAY)
        back_dark_ratio = np.sum(back_gray < 60) / back_gray.size
        if back_dark_ratio < 0.30:
            return None

        bg_area = screen[100:300, 300:700]
        bg_gray = cv2.cvtColor(bg_area, cv2.COLOR_BGR2GRAY)
        if bg_gray.mean() < 160:
            return None

        btn_area = screen[780:880, 1100:1550]
        btn_gray = cv2.cvtColor(btn_area, cv2.COLOR_BGR2GRAY)
        btn_dark_ratio = np.sum(btn_gray < 100) / btn_gray.size
        if btn_dark_ratio < 0.30:
            return None

        preset_area = screen[780:880, 50:300]
        preset_gray = cv2.cvtColor(preset_area, cv2.COLOR_BGR2GRAY)
        has_preset = np.sum(preset_gray < 100) / preset_gray.size > 0.25

        if has_preset:
            return State.PRE_MATCH_TEAM
        else:
            return State.PRE_MATCH_MISSION

    def _check_story_map_heuristic(self, screen: np.ndarray) -> bool:
        h, w = screen.shape[:2]
        if h < 700 or w < 1400:
            return False
        back_crop = screen[15:65, 20:70]
        back_gray = cv2.cvtColor(back_crop, cv2.COLOR_BGR2GRAY)
        if np.sum(back_gray < 80) / back_gray.size < 0.20:
            return False
        bar_crop = screen[20:60, 400:800]
        if cv2.cvtColor(bar_crop, cv2.COLOR_BGR2GRAY).mean() < 160:
            return False
        mid_crop = screen[200:500, 300:1300]
        if cv2.cvtColor(mid_crop, cv2.COLOR_BGR2GRAY).mean() < 150:
            return False
        return True

    def find_story_active_node(self, screen: np.ndarray) -> Optional[Tuple[int, int]]:
        if screen is None or screen.size == 0:
            return None
        score, pt = self.match(screen, "story_node_play", region=(0, 100, 1600, 750))
        if score >= self._get_threshold("story_node_play") and pt:
            return pt

        hsv = cv2.cvtColor(screen[100:850, 0:1600], cv2.COLOR_BGR2HSV)
        orange_mask = cv2.inRange(hsv, (8, 140, 140), (25, 255, 255))
        contours, _ = cv2.findContours(orange_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            if 150 < area < 2500:
                x, y, w, h = cv2.boundingRect(c)
                if 0.7 <= w / float(h) <= 1.4:
                    cx = x + w // 2
                    cy = 100 + y + h // 2
                    return (cx, cy)
        return None

    def _check_chaos_event_heuristic(self, screen: np.ndarray) -> bool:
        """Heuristic check for Chaos Event Encounter screen with choice cards."""
        h, w = screen.shape[:2]
        if h < 700 or w < 1400:
            return False

        if is_chaos_map_screen(screen):
            return False

        # 1. Top banner: dark horizontal banner at y in [130, 270]
        banner_roi = screen[130:270, 200:1400]
        gray_banner = cv2.cvtColor(banner_roi, cv2.COLOR_BGR2GRAY)
        b_mean = gray_banner.mean()
        if b_mean < 20 or b_mean > 130:
            return False

        # 2. Bottom choices area: dark rounded rectangles at y in [660, 860]
        bottom_roi = screen[660:860, 150:1450]
        gray_bottom = cv2.cvtColor(bottom_roi, cv2.COLOR_BGR2GRAY)
        card_mean = gray_bottom.mean()
        if card_mean < 15 or card_mean > 120:
            return False

        # 3. Text edge activity in bottom choice area
        edges = cv2.Canny(gray_bottom, 50, 150)
        edge_ratio = np.count_nonzero(edges) / edges.size
        if edge_ratio < 0.02:
            return False

        return True

    def _log_unknown_scores(self, scores: Dict[str, float]) -> None:
        if not scores:
            return
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = sorted_scores[:8]
        score_str = ", ".join(f"{k}={v:.2f}" for k, v in top)
        logger.debug(f"[UNKNOWN] Top match scores: {score_str}")

    def _resolve_match_done_details(self, screen: np.ndarray, clf_res: Any) -> Dict[str, Any]:
        """Resolves retry vs next mission and button state for MATCH_DONE."""
        score_reward = clf_res.evidence.get("reward_text", 0.0)
        confirm_coord = clf_res.best_coords.get("confirm_button") or clf_res.best_coords.get("confirm_button_purple")
        score_confirm = max(clf_res.evidence.get("confirm_button", 0.0), clf_res.evidence.get("confirm_button_purple", 0.0))

        btn_regions = [
            (850, 700, 400, 180),
            (830, 680, 440, 200),
            (750, 650, 600, 250),
        ]
        score_retry = 0.0
        retry_keys = [
            "retry_button", "retry_button_new", "retry_button_text",
            "retry_button_refresh", "retry_button_alt", "retry_button_grey"
        ]
        for key in retry_keys:
            if key not in self.templates:
                continue
            for rx, ry, rw, rh in btn_regions:
                s, _ = self.match(screen, key, region=(rx, ry, rw, rh))
                if s > score_retry:
                    score_retry = s

        score_next = 0.0
        for rx, ry, rw, rh in btn_regions:
            s, _ = self.match(screen, "next_mission_button", region=(rx, ry, rw, rh))
            if s > score_next:
                score_next = s

        retry_confident = score_retry >= self._get_threshold("retry_button")
        next_confident = score_next >= self._get_threshold("next_mission_button")

        if retry_confident and not next_confident:
            left_btn = LeftButton.RETRY
        elif next_confident and not retry_confident:
            left_btn = LeftButton.NEXT_MISSION
        elif retry_confident and next_confident:
            left_btn = LeftButton.RETRY if score_retry >= score_next else LeftButton.NEXT_MISSION
        else:
            left_btn = LeftButton.NONE

        if left_btn == LeftButton.RETRY and score_retry >= 0.60:
            btn_crop = screen[795:860, 920:1220]
            if btn_crop.size > 0:
                hsv = cv2.cvtColor(btn_crop, cv2.COLOR_BGR2HSV)
                orange_mask = cv2.inRange(hsv, (8, 100, 100), (25, 255, 255))
                orange_ratio = cv2.countNonZero(orange_mask) / (btn_crop.shape[0] * btn_crop.shape[1])
                mean_sat = hsv[:, :, 1].mean()
                if orange_ratio < 0.15 and mean_sat < 35:
                    left_btn = LeftButton.RETRY_DISABLED

        runner_up = clf_res.ranked[1] if len(clf_res.ranked) > 1 else None
        return {
            "left_button": left_btn,
            "reward_score": score_reward,
            "confirm_score": score_confirm,
            "retry_score": score_retry,
            "next_score": score_next,
            "confirm_coord": confirm_coord,
            "score": clf_res.confidence,
            "confidence": clf_res.confidence,
            "margin": clf_res.margin,
            "ranked": clf_res.ranked,
            "runner_up": runner_up,
            "recognizer": "OpenCV StateClassifier",
        }

    def _log_decision(self, state: State, details: Dict[str, Any]) -> None:
        rec = details.get("recognizer", "Unknown")
        sc = details.get("score", details.get("confidence", 0.0))
        mg = details.get("margin", 0.0)
        ru = details.get("runner_up")
        if ru and isinstance(ru, (tuple, list)) and len(ru) >= 2:
            ru_str = f"{ru[0]} ({float(ru[1]):.2f})"
        else:
            ru_str = str(ru)
        logger.debug(
            f"[ScreenDetector] State: {state.value} | Recognizer: {rec} | "
            f"Score: {sc:.2f} | Margin: {mg:.2f} | Runner-up: {ru_str}"
        )

    def detect(self, screen: np.ndarray) -> Tuple[State, Dict[str, Any]]:
        """
        Classifies screen into (State, details_dict) using evidence fusion (StateClassifier).
        Fallback to pixel heuristics when classifier returns UNKNOWN.
        """
        if screen is None or screen.size == 0:
            det = {
                "recognizer": "none",
                "score": 0.0,
                "confidence": 0.0,
                "margin": 0.0,
                "runner_up": None,
                "ranked": [],
            }
            return State.UNKNOWN, det

        # 1. StateClassifier: Bằng chứng chéo, neo âm và tính điểm đa neo
        self.classifier.set_matcher(self.match)
        clf_res = self.classifier.classify(screen)

        if clf_res.state == "AMBIGUOUS":
            logger.debug(f"[AMBIGUOUS] States sát nhau: {clf_res.ranked[:3]}, margin={clf_res.margin:.2f}")
            det = {
                "ambiguous": True,
                "recognizer": "OpenCV StateClassifier (Ambiguous)",
                "score": clf_res.confidence,
                "confidence": clf_res.confidence,
                "margin": clf_res.margin,
                "ranked": clf_res.ranked,
                "runner_up": clf_res.ranked[1] if len(clf_res.ranked) > 1 else None,
                "evidence": clf_res.evidence,
            }
            self._log_decision(State.UNKNOWN, det)
            return State.UNKNOWN, det

        if clf_res.state != "UNKNOWN":
            try:
                state_enum = State[clf_res.state]
            except KeyError:
                state_enum = State.UNKNOWN

            runner_up = clf_res.ranked[1] if len(clf_res.ranked) > 1 else None
            details: Dict[str, Any] = {}

            # Chi tiết hóa dữ liệu điều khiển theo từng State
            if state_enum == State.CHAOS_AFTER_BATTLE:
                leave_coord = (
                    clf_res.best_coords.get("chaos_leave_button")
                    or clf_res.best_coords.get("chaos_continue_button")
                    or clf_res.best_coords.get("chaos_settlement_button")
                    or TAP_COORDS["chaos_leave_button"]
                )
                details = {
                    "leave_coord": leave_coord,
                }

            elif state_enum == State.CHAOS_EQUIPMENT:
                details = {
                    "confirm_coord": TAP_COORDS.get("equipment_confirm", (1360, 806)),
                }

            elif state_enum == State.CHAOS_SAFE_ZONE:
                # 1. Phát hiện Modal Rest (Popup xác nhận nghỉ ngơi)
                sc_conf, pt_conf = self.match(
                    screen, "chaos_safe_zone_confirm_btn", region=(800, 590, 510, 100)
                )
                is_modal_open = sc_conf >= 0.70
                confirm_coord = pt_conf if is_modal_open else TAP_COORDS.get("chaos_safe_zone_confirm", (1055, 642))

                # 2. Phát hiện nút Rest trên màn hình Trạm nghỉ (Camp)
                sc_rest, pt_rest = self.match(
                    screen, "chaos_safe_zone_rest_icon", region=(250, 620, 350, 130)
                )
                has_rest_btn = sc_rest >= 0.70
                if has_rest_btn and pt_rest:
                    rest_coord = (pt_rest[0] + 35, pt_rest[1])
                else:
                    rest_coord = TAP_COORDS.get("chaos_safe_zone_rest", (455, 690))

                skip_coord = clf_res.best_coords.get("chaos_safe_zone_skip", TAP_COORDS["chaos_safe_zone_skip"])

                details = {
                    "is_modal_open": is_modal_open,
                    "has_rest_btn": has_rest_btn,
                    "rest_coord": rest_coord,
                    "confirm_coord": confirm_coord,
                    "cancel_coord": TAP_COORDS.get("chaos_safe_zone_cancel", (544, 642)),
                    "skip_coord": skip_coord,
                }

            elif state_enum == State.CHAOS_EVENT:
                ev_coord = (
                    clf_res.best_coords.get("chaos_event_icon")
                    or clf_res.best_coords.get("chaos_event_badge")
                    or clf_res.best_coords.get("chaos_event_battle_btn")
                )
                details = {
                    "type": "event_encounter",
                    "coord": ev_coord,
                }

            elif state_enum == State.CHAOS_OBTAIN_REWARD:
                details = {
                    "obtain_coord": clf_res.best_coords.get("chaos_obtain_button", TAP_COORDS["chaos_obtain_button"]),
                }

            elif state_enum == State.CHAOS_CHOOSE_EPIPHANY:
                if clf_res.evidence.get("choose_fate_title", 0.0) >= self._get_threshold("choose_fate_title"):
                    sub_type = "choose_fate"
                elif clf_res.evidence.get("select_attribute_title", 0.0) >= self._get_threshold("select_attribute_title"):
                    sub_type = "select_attribute"
                elif clf_res.evidence.get("remove_card_title", 0.0) >= self._get_threshold("remove_card_title"):
                    sub_type = "remove_card"
                elif clf_res.evidence.get("etched_memory_title", 0.0) >= self._get_threshold("etched_memory_title"):
                    sub_type = "etched_memory"
                elif (clf_res.evidence.get("card_epiphany_title", 0.0) >= self._get_threshold("card_epiphany_title") or
                      clf_res.evidence.get("epiphany_title", 0.0) >= self._get_threshold("epiphany_title") or
                      clf_res.evidence.get("epiphany_text_white", 0.0) >= self._get_threshold("epiphany_text_white")):
                    sub_type = "epiphany"
                else:
                    sub_type = "card_reward"

                details = {
                    "type": sub_type,
                    "epiphany_type": sub_type,
                    "score_view_original": max(clf_res.evidence.get("view_original", 0.0), clf_res.evidence.get("view_original_white", 0.0)),
                    "score_epiphany": max(clf_res.evidence.get("epiphany_title", 0.0), clf_res.evidence.get("epiphany_text_white", 0.0)),
                    "score_card_epiphany": clf_res.evidence.get("card_epiphany_title", 0.0),
                    "score_card_reward": clf_res.evidence.get("card_reward_title", 0.0),
                    "score_etched_memory": clf_res.evidence.get("etched_memory_title", 0.0),
                    "score_choose_fate": clf_res.evidence.get("choose_fate_title", 0.0),
                    "score_remove_card": clf_res.evidence.get("remove_card_title", 0.0),
                }

            elif state_enum == State.POPUP_EFFECT:
                close_pt = self.find_close_x(screen)
                if clf_res.evidence.get("memory_obtained_title", 0.0) >= 0.70 or clf_res.evidence.get("tap_to_close", 0.0) >= 0.70:
                    close_pt = (800, 850)
                details = {
                    "close_coord": close_pt,
                }

            elif state_enum in (State.POPUP_DRAW_PILE, State.POPUP_STAGE_INFO, State.POPUP_MONSTER_INFO, State.POPUP_PAUSE):
                close_pt = self.find_close_x(screen)
                if state_enum == State.POPUP_MONSTER_INFO:
                    close_pt = TAP_COORDS["close_monster_info"]
                details = {
                    "close_coord": close_pt,
                }

            elif state_enum == State.PRE_MATCH_TEAM:
                pt_pre_team = clf_res.best_coords.get("pre_enter_team")
                enter_x = (pt_pre_team[0] + 150) if pt_pre_team else TAP_COORDS["enter_team"][0]
                enter_y = pt_pre_team[1] if pt_pre_team else TAP_COORDS["enter_team"][1]
                raw_score = max(clf_res.evidence.get("pre_enter_team", 0.0), clf_res.confidence)
                details = {
                    "score": raw_score,
                    "confidence": raw_score,
                    "coord": (enter_x, enter_y),
                }

            elif state_enum == State.PRE_MATCH_MISSION:
                pt_pre_mission = clf_res.best_coords.get("pre_enter_mission") or clf_res.best_coords.get("chaos_enter_lobby")
                raw_score = max(clf_res.evidence.get("pre_enter_mission", 0.0), clf_res.evidence.get("chaos_enter_lobby", 0.0), clf_res.confidence)
                details = {
                    "score": raw_score,
                    "confidence": raw_score,
                    "coord": pt_pre_mission or TAP_COORDS["enter_mission"],
                }

            elif state_enum == State.STORY_DIALOGUE:
                details = {
                    "skip_coord": clf_res.best_coords.get("story_dialogue_skip", TAP_COORDS["story_dialogue_skip"]),
                    "auto_coord": clf_res.best_coords.get("story_dialogue_auto", TAP_COORDS["story_dialogue_auto"]),
                }

            elif state_enum == State.STORY_MAP:
                details = {
                    "active_node": self.find_story_active_node(screen),
                }

            elif state_enum == State.MATCH_DONE:
                details = self._resolve_match_done_details(screen, clf_res)

            # Metadata nhận diện chuẩn hóa cho tất cả các nhánh StateClassifier
            details.setdefault("score", clf_res.confidence)
            details.setdefault("confidence", clf_res.confidence)
            details.setdefault("margin", clf_res.margin)
            details.setdefault("ranked", clf_res.ranked)
            details.setdefault("runner_up", runner_up)
            details.setdefault("recognizer", "OpenCV StateClassifier")

            self._log_decision(state_enum, details)
            return state_enum, details

        # 2. Pixel Heuristics Fallback (khi classifier trả về UNKNOWN)
        if is_chaos_map_screen(screen):
            details = {
                "recognizer": "heuristic_chaos_map",
                "score": 1.0,
                "confidence": 1.0,
                "margin": 1.0,
                "runner_up": None,
                "ranked": [("CHAOS_MAP", 1.0)],
            }
            self._log_decision(State.CHAOS_MAP, details)
            return State.CHAOS_MAP, details

        if self._check_in_match_heuristic(screen):
            details = {
                "score": 0.80,
                "confidence": 0.80,
                "heuristic": True,
                "recognizer": "heuristic_in_match",
                "margin": 0.0,
                "runner_up": None,
                "ranked": [("IN_MATCH", 0.80)],
            }
            self._log_decision(State.IN_MATCH, details)
            return State.IN_MATCH, details

        if self._check_chaos_event_heuristic(screen):
            details = {
                "heuristic": True,
                "type": "event_encounter",
                "recognizer": "heuristic_chaos_event",
                "score": 0.80,
                "confidence": 0.80,
                "margin": 0.0,
                "runner_up": None,
                "ranked": [("CHAOS_EVENT", 0.80)],
            }
            self._log_decision(State.CHAOS_EVENT, details)
            return State.CHAOS_EVENT, details

        pre_match_state = self._check_pre_match_heuristic(screen)
        if pre_match_state is not None:
            details = {
                "heuristic": True,
                "recognizer": "heuristic_pre_match",
                "score": 0.80,
                "confidence": 0.80,
                "margin": 0.0,
                "runner_up": None,
                "ranked": [(pre_match_state.value, 0.80)],
            }
            self._log_decision(pre_match_state, details)
            return pre_match_state, details

        if self._check_story_map_heuristic(screen):
            active_node = self.find_story_active_node(screen)
            sc = clf_res.evidence.get("story_title", 0.80)
            details = {
                "score": sc,
                "confidence": sc,
                "active_node": active_node,
                "recognizer": "heuristic_story_map",
                "margin": 0.0,
                "runner_up": None,
                "ranked": [("STORY_MAP", sc)],
            }
            self._log_decision(State.STORY_MAP, details)
            return State.STORY_MAP, details

        # Close X generic modal
        score_x, pt_x = self.match(screen, "close_x", region=(1350, 0, 240, 120))
        if score_x >= 0.85:
            close_pt = pt_x or TAP_COORDS["close_x_default"]
            details = {
                "close_coord": close_pt,
                "score": score_x,
                "confidence": score_x,
                "recognizer": "heuristic_close_x",
                "margin": 0.0,
                "runner_up": None,
                "ranked": [("POPUP_EFFECT", score_x)],
            }
            self._log_decision(State.POPUP_EFFECT, details)
            return State.POPUP_EFFECT, details

        score_obt, _ = self.match(screen, "memory_obtained_title", region=(700, 70, 300, 100))
        score_ttc, pt_ttc = self.match(screen, "tap_to_close", region=(500, 800, 600, 100))
        if score_obt >= self._get_threshold("memory_obtained_title") or score_ttc >= self._get_threshold("tap_to_close"):
            sc = max(score_obt, score_ttc)
            details = {
                "close_coord": (800, 850),
                "score": sc,
                "confidence": sc,
                "recognizer": "heuristic_tap_to_close",
                "margin": 0.0,
                "runner_up": None,
                "ranked": [("POPUP_EFFECT", sc)],
            }
            self._log_decision(State.POPUP_EFFECT, details)
            return State.POPUP_EFFECT, details

        score_mcb, pt_mcb = self.match(screen, "modal_close_button", region=(700, 780, 200, 100))
        if score_mcb >= self._get_threshold("modal_close_button"):
            details = {
                "close_coord": pt_mcb or TAP_COORDS["modal_close_button"],
                "score": score_mcb,
                "confidence": score_mcb,
                "recognizer": "heuristic_modal_close",
                "margin": 0.0,
                "runner_up": None,
                "ranked": [("POPUP_EFFECT", score_mcb)],
            }
            self._log_decision(State.POPUP_EFFECT, details)
            return State.POPUP_EFFECT, details

        # 3. Transitioning / Dark cutscene / Blank frame
        max_score = max(clf_res.evidence.values()) if clf_res.evidence else 0.0
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        dark_ratio = np.sum(gray < 60) / gray.size
        if dark_ratio > 0.65 and max_score < 0.70:
            details = {
                "dark_cutscene": True,
                "dark_ratio": dark_ratio,
                "recognizer": "heuristic_dark_cutscene",
                "score": 1.0,
                "confidence": 1.0,
                "margin": 0.0,
                "runner_up": None,
                "ranked": [("TRANSITIONING", 1.0)],
            }
            self._log_decision(State.TRANSITIONING, details)
            return State.TRANSITIONING, details

        self._log_unknown_scores(clf_res.evidence)
        ru = clf_res.ranked[1] if len(clf_res.ranked) > 1 else None
        top_cand = clf_res.ranked[0] if clf_res.ranked else None
        details = {
            "recognizer": "none",
            "score": 0.0,
            "confidence": 0.0,
            "margin": clf_res.margin,
            "ranked": clf_res.ranked,
            "top_candidate": top_cand,
            "runner_up": ru,
            "evidence": clf_res.evidence,
        }
        self._log_decision(State.UNKNOWN, details)
        return State.UNKNOWN, details

