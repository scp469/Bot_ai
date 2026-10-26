"""
State detector for Chaos Zero Nightmare.
Uses OpenCV template matching on fixed/dynamic regions,
pixel-based heuristics, and per-template confidence thresholds.
"""
import os
import logging
import cv2
import numpy as np
from config import State, LeftButton, TEMPLATES_DIR, TEMPLATES, MATCH_THRESHOLD, TEMPLATE_THRESHOLDS, TAP_COORDS

logger = logging.getLogger("ChaosBot.Detector")


class ScreenDetector:
    def __init__(self, threshold=MATCH_THRESHOLD):
        self.threshold = threshold
        self.templates = {}
        self._load_templates()

    def _load_templates(self):
        """Pre-load all template images."""
        for key, fname in TEMPLATES.items():
            path = os.path.join(TEMPLATES_DIR, fname)
            if os.path.isfile(path):
                img = cv2.imread(path)
                if img is not None:
                    self.templates[key] = img

    def match(self, screen, templ_key, region=None):
        """
        Match a template against screen or sub-region.
        Returns (score, (center_x, center_y)) or (0.0, None).
        """
        templ = self.templates.get(templ_key)
        if templ is None or screen is None:
            return 0.0, None

        if region is not None:
            rx, ry, rw, rh = region
            h, w = screen.shape[:2]
            # Clip bounds
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
            return max_val, (cx, cy)
        else:
            th, tw = templ.shape[:2]
            if screen.shape[0] < th or screen.shape[1] < tw:
                return 0.0, None
            res = cv2.matchTemplate(screen, templ, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            return max_val, (cx, cy)

    def find_close_x(self, screen):
        """
        Search top-right area for the close 'X' button.
        Returns (center_x, center_y) or default tap coordinate.
        """
        # Search region: top-right corner x: 1350..1590, y: 0..120
        region = (1350, 0, 240, 120)
        score, pt = self.match(screen, "close_x", region=region)
        if score >= 0.70 and pt:
            return pt
        return TAP_COORDS["close_x_default"]

    # ── Hybrid Verification (Thẩm định kép OCR) ────
    def verify_button(self, screen, box_or_point, expected_words, expand_pad=25) -> bool:
        """
        Thẩm định kép (Hybrid Verification) vị trí nút bấm bằng OCR.
        Đảm bảo tại vị trí nút thực sự chứa đúng chữ cần bấm trước khi click.
        """
        try:
            from ocr_service import verify_button_text
            return verify_button_text(screen, box_or_point, expected_words, expand_pad=expand_pad)
        except Exception as e:
            logger.debug(f"verify_button OCR error: {e}")
            return False

    def find_text(self, screen, text_query, region=None):
        """
        Tìm tọa độ tâm của cụm từ trên màn hình bằng OCR không phụ thuộc template ảnh.
        """
        try:
            from ocr_service import find_text
            return find_text(screen, text_query, region=region)
        except Exception as e:
            logger.debug(f"find_text OCR error: {e}")
            return None

    # ── Per-template threshold ────────────────────
    def _get_threshold(self, templ_key):
        """Get match threshold for a specific template, with per-template overrides."""
        return TEMPLATE_THRESHOLDS.get(templ_key, self.threshold)

    # ── Pixel heuristics ──────────────────────────
    def _check_in_match_heuristic(self, screen):
        """
        Pixel heuristic for IN_MATCH when End Turn template fails.
        Detects green HP bar at top + battle background.
        Covers card-selection phase or animation where End Turn button is hidden or dim.
        """
        h, w = screen.shape[:2]
        if h < 200 or w < 600:
            return False

        # Check 1: Green HP bar at top of screen (y=5..45, x=50..600)
        hp_bar_crop = screen[5:45, 50:600]
        hsv_hp = cv2.cvtColor(hp_bar_crop, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv_hp, (35, 70, 70), (95, 255, 255))
        green_ratio = cv2.countNonZero(green_mask) / green_mask.size

        if green_ratio < 0.08:
            return False

        # Check 2: Battle background in center area
        center_crop = screen[300:600, 400:1200]
        gray_center = cv2.cvtColor(center_crop, cv2.COLOR_BGR2GRAY)
        if gray_center.mean() > 165:
            return False

        return True

    def _check_pre_match_heuristic(self, screen):
        """
        Pixel heuristic for pre-match screens (Basin of Hyperspace / Save Data Formation).
        Detects: dark back button at top-left + light background + dark action button
        at bottom-right.
        Returns State or None.
        """
        h, w = screen.shape[:2]
        if h < 700 or w < 1400:
            return None

        # Check 1: Dark back arrow button at top-left corner
        back_btn_area = screen[20:55, 35:85]
        back_gray = cv2.cvtColor(back_btn_area, cv2.COLOR_BGR2GRAY)
        back_dark_ratio = np.sum(back_gray < 60) / back_gray.size
        if back_dark_ratio < 0.30:
            return None

        # Check 2: Light/white background in upper-center area
        bg_area = screen[100:300, 300:700]
        bg_gray = cv2.cvtColor(bg_area, cv2.COLOR_BGR2GRAY)
        if bg_gray.mean() < 160:
            return None

        # Check 3: Dark action button at bottom-right (y: 780..880, x: 1100..1550)
        btn_area = screen[780:880, 1100:1550]
        btn_gray = cv2.cvtColor(btn_area, cv2.COLOR_BGR2GRAY)
        btn_dark_ratio = np.sum(btn_gray < 100) / btn_gray.size
        if btn_dark_ratio < 0.30:
            return None

        # All checks passed → pre-match screen
        # Distinguish: Save Data Formation has "Preset" button at bottom-left (y: 780..880, x: 50..300)
        preset_area = screen[780:880, 50:300]
        preset_gray = cv2.cvtColor(preset_area, cv2.COLOR_BGR2GRAY)
        has_preset = np.sum(preset_gray < 100) / preset_gray.size > 0.25

        if has_preset:
            return State.PRE_MATCH_TEAM
        else:
            return State.PRE_MATCH_MISSION

    def _check_story_map_heuristic(self, screen):
        """
        Pixel heuristic for Story Chapter Map when story_title template is borderline.
        Checks: Top-left back button, light top bar, and light map background.
        """
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

    def find_story_active_node(self, screen):
        """
        Find coordinates of the next active stage node on the Chapter Map.
        Looks for orange play triangle (story_node_play) or orange badge 'N'.
        Returns (cx, cy) or None.
        """
        if screen is None or screen.size == 0:
            return None
        # 1. Template match across full map width (x: 0..1600, y: 100..850)
        score, pt = self.match(screen, "story_node_play", region=(0, 100, 1600, 750))
        if score >= self._get_threshold("story_node_play") and pt:
            return pt

        # 2. Heuristic: Orange play button contour across map area
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

    def _log_unknown_scores(self, scores):
        """Log all template match scores when detection falls to UNKNOWN for debugging."""
        if not scores:
            return
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = sorted_scores[:8]
        score_str = ", ".join(f"{k}={v:.2f}" for k, v in top)
        logger.debug(f"[UNKNOWN] Top match scores: {score_str}")

    # ── Main detection ────────────────────────────
    def detect(self, screen):
        """
        Classifies screen into (State, details_dict).
        Screen must be a 1600x900 BGR numpy array.
        Uses template matching with per-template thresholds,
        pixel heuristics for expanded detection, and TRANSITIONING state
        for animation/cutscene frames.
        """
        if screen is None or screen.size == 0:
            return State.UNKNOWN, {}

        scores = {}  # Track template match scores for debug logging

        # 1. Check In-Match (turn end button) - most frequent state during play, fast ROI
        score_in_match, _ = self.match(screen, "in_match_check", region=(1320, 680, 200, 200))
        scores["in_match_check"] = score_in_match
        if score_in_match >= self._get_threshold("in_match_check"):
            return State.IN_MATCH, {"score": score_in_match}

        # 2. Check Chaos After Battle (Leave button)
        score_leave, pt_leave = self.match(screen, "chaos_leave_button", region=(1250, 750, 350, 150))
        scores["chaos_leave_button"] = score_leave
        if score_leave >= self._get_threshold("chaos_leave_button"):
            return State.CHAOS_AFTER_BATTLE, {
                "score": score_leave,
                "leave_coord": pt_leave or TAP_COORDS["chaos_leave_button"],
            }

        score_cont, pt_cont = self.match(screen, "chaos_continue_button", region=(1200, 750, 380, 140))
        scores["chaos_continue_button"] = score_cont
        if score_cont >= self._get_threshold("chaos_continue_button"):
            return State.CHAOS_AFTER_BATTLE, {
                "score": score_cont,
                "leave_coord": pt_cont or TAP_COORDS["chaos_continue_button"],
            }

        score_settle, pt_settle = self.match(screen, "chaos_settlement_button", region=(1250, 750, 350, 150))
        scores["chaos_settlement_button"] = score_settle
        if score_settle >= self._get_threshold("chaos_settlement_button"):
            return State.CHAOS_AFTER_BATTLE, {
                "score": score_settle,
                "leave_coord": pt_settle or TAP_COORDS["chaos_settlement_button"],
            }

        # 2a. Check Chaos Equipment Screen (Equipment title at top -> Confirm at bottom right)
        score_equip, _ = self.match(screen, "equipment_title", region=(650, 70, 350, 110))
        scores["equipment_title"] = score_equip
        if score_equip >= self._get_threshold("equipment_title"):
            return State.CHAOS_AFTER_BATTLE, {
                "score": score_equip,
                "is_equipment": True,
                "leave_coord": TAP_COORDS["equipment_confirm"],
            }

        # 2b. Check Chaos Choose Epiphany (Choose Epiphany Effect / Card Epiphany / In-battle Epiphany - Wait for user choice)
        score_vo, _ = self.match(screen, "view_original", region=(1200, 20, 380, 120))
        scores["view_original"] = score_vo
        score_vo_w, _ = self.match(screen, "view_original_white", region=(1200, 20, 380, 120))
        scores["view_original_white"] = score_vo_w
        score_epi, _ = self.match(screen, "epiphany_title", region=(500, 50, 600, 130))
        scores["epiphany_title"] = score_epi
        score_epi_w, _ = self.match(screen, "epiphany_text_white", region=(600, 750, 350, 130))
        scores["epiphany_text_white"] = score_epi_w
        score_ce, _ = self.match(screen, "card_epiphany_title", region=(500, 50, 600, 130))
        scores["card_epiphany_title"] = score_ce
        score_cr, _ = self.match(screen, "card_reward_title", region=(500, 50, 600, 130))
        scores["card_reward_title"] = score_cr
        score_sa, _ = self.match(screen, "select_attribute_title", region=(600, 80, 400, 80))
        scores["select_attribute_title"] = score_sa
        score_em, _ = self.match(screen, "etched_memory_title", region=(550, 70, 500, 100))
        scores["etched_memory_title"] = score_em
        score_cf, _ = self.match(screen, "choose_fate_title", region=(600, 800, 400, 100))
        scores["choose_fate_title"] = score_cf
        score_rc, _ = self.match(screen, "remove_card_title", region=(80, 10, 470, 80))
        scores["remove_card_title"] = score_rc

        if (score_vo >= self._get_threshold("view_original") or
            score_vo_w >= self._get_threshold("view_original_white") or
            score_epi >= self._get_threshold("epiphany_title") or
            score_epi_w >= self._get_threshold("epiphany_text_white") or
            score_ce >= self._get_threshold("card_epiphany_title") or
            score_cr >= self._get_threshold("card_reward_title") or
            score_sa >= self._get_threshold("select_attribute_title") or
            score_em >= self._get_threshold("etched_memory_title") or
            score_cf >= self._get_threshold("choose_fate_title") or
            score_rc >= self._get_threshold("remove_card_title")):
            return State.CHAOS_CHOOSE_EPIPHANY, {
                "score_view_original": max(score_vo, score_vo_w),
                "score_epiphany": max(score_epi, score_epi_w),
                "score_card_epiphany": score_ce,
                "score_card_reward": score_cr,
                "score_etched_memory": score_em,
                "score_choose_fate": score_cf,
                "score_remove_card": score_rc,
            }

        # 2c. Check Chaos Obtain Reward (Orange Obtain button in bottom-right)
        score_obtain, pt_obtain = self.match(screen, "chaos_obtain_button", region=(1100, 750, 490, 140))
        scores["chaos_obtain_button"] = score_obtain
        if score_obtain >= self._get_threshold("chaos_obtain_button"):
            return State.CHAOS_OBTAIN_REWARD, {
                "score": score_obtain,
                "obtain_coord": pt_obtain or TAP_COORDS["chaos_obtain_button"],
            }

        # 2d. Check Chaos Safe Zone (Skip button in bottom-right)
        score_sz, pt_sz = self.match(screen, "chaos_safe_zone_skip", region=(1200, 750, 380, 140))
        scores["chaos_safe_zone_skip"] = score_sz
        if score_sz >= self._get_threshold("chaos_safe_zone_skip"):
            return State.CHAOS_SAFE_ZONE, {
                "score": score_sz,
                "skip_coord": pt_sz or TAP_COORDS["chaos_safe_zone_skip"],
            }

        # 3. Check Chaos Map Screen (Minimap + Boss + Pin)
        from chaos_map_reader import is_chaos_map_screen
        if is_chaos_map_screen(screen):
            return State.CHAOS_MAP, {}

        # 4. Check Popups
        score_effect, _ = self.match(screen, "effect_title", region=(80, 10, 250, 80))
        scores["effect_title"] = score_effect
        if score_effect >= self._get_threshold("effect_title"):
            close_pt = self.find_close_x(screen)
            return State.POPUP_EFFECT, {"close_coord": close_pt, "score": score_effect}

        score_dp, _ = self.match(screen, "draw_pile_title", region=(80, 10, 250, 80))
        scores["draw_pile_title"] = score_dp
        if score_dp >= self._get_threshold("draw_pile_title"):
            close_pt = self.find_close_x(screen)
            return State.POPUP_DRAW_PILE, {"close_coord": close_pt, "score": score_dp}

        score_si, _ = self.match(screen, "stage_info_title", region=(80, 10, 260, 80))
        scores["stage_info_title"] = score_si
        if score_si >= self._get_threshold("stage_info_title"):
            close_pt = self.find_close_x(screen)
            return State.POPUP_STAGE_INFO, {"close_coord": close_pt, "score": score_si}

        score_mi, _ = self.match(screen, "monster_info_title", region=(30, 15, 260, 80))
        scores["monster_info_title"] = score_mi
        if score_mi >= self._get_threshold("monster_info_title"):
            return State.POPUP_MONSTER_INFO, {
                "close_coord": TAP_COORDS["close_monster_info"],
                "score": score_mi,
            }

        score_pause, _ = self.match(screen, "pause_title", region=(80, 10, 300, 100))
        scores["pause_title"] = score_pause
        if score_pause >= self._get_threshold("pause_title"):
            close_pt = self.find_close_x(screen)
            return State.POPUP_PAUSE, {"close_coord": close_pt, "score": score_pause}

        # 5. Check Pre-match screens (Enter buttons)
        score_pre_team, pt_pre_team = self.match(screen, "pre_enter_team", region=(1050, 750, 520, 140))
        scores["pre_enter_team"] = score_pre_team
        if score_pre_team >= self._get_threshold("pre_enter_team"):
            enter_x = (pt_pre_team[0] + 150) if pt_pre_team else TAP_COORDS["enter_team"][0]
            enter_y = pt_pre_team[1] if pt_pre_team else TAP_COORDS["enter_team"][1]
            return State.PRE_MATCH_TEAM, {
                "score": score_pre_team,
                "coord": (enter_x, enter_y),
            }

        score_pre_mission, pt_pre_mission = self.match(screen, "pre_enter_mission", region=(1000, 750, 570, 140))
        scores["pre_enter_mission"] = score_pre_mission
        if score_pre_mission >= self._get_threshold("pre_enter_mission"):
            return State.PRE_MATCH_MISSION, {
                "score": score_pre_mission,
                "coord": pt_pre_mission or TAP_COORDS["enter_mission"],
            }

        score_chaos_lobby, pt_lobby = self.match(screen, "chaos_enter_lobby", region=(1200, 800, 390, 100))
        scores["chaos_enter_lobby"] = score_chaos_lobby
        if score_chaos_lobby >= 0.85:
            return State.PRE_MATCH_MISSION, {"score": score_chaos_lobby, "coord": pt_lobby or (1415, 865)}

        # 5b. Pre-match pixel heuristic (back button + light bg + action button)
        pre_match_state = self._check_pre_match_heuristic(screen)
        if pre_match_state is not None:
            return pre_match_state, {"heuristic": True}

        # 5c. Check Story Dialogue (Skip button or Auto button in top-right)
        score_skip, pt_skip = self.match(screen, "story_dialogue_skip", region=(1200, 15, 140, 80))
        scores["story_dialogue_skip"] = score_skip
        score_auto, pt_auto = self.match(screen, "story_dialogue_auto", region=(1330, 15, 140, 80))
        scores["story_dialogue_auto"] = score_auto

        if score_skip >= self._get_threshold("story_dialogue_skip") or score_auto >= self._get_threshold("story_dialogue_auto"):
            return State.STORY_DIALOGUE, {
                "skip_coord": pt_skip or TAP_COORDS["story_dialogue_skip"],
                "auto_coord": pt_auto or TAP_COORDS["story_dialogue_auto"],
                "score": max(score_skip, score_auto),
            }

        # 5d. Check Story Map (Story title top-left or Chapter header)
        score_st, _ = self.match(screen, "story_title", region=(60, 10, 130, 70))
        scores["story_title"] = score_st
        if score_st >= self._get_threshold("story_title") or self._check_story_map_heuristic(screen):
            active_node = self.find_story_active_node(screen)
            return State.STORY_MAP, {
                "score": score_st,
                "active_node": active_node,
            }

        # 5e. Generic popup modal with close 'X' button in top-right (e.g. Chaos Info, notices)
        score_x, pt_x = self.match(screen, "close_x", region=(1350, 0, 240, 120))
        scores["close_x"] = score_x
        if score_x >= 0.85:
            close_pt = pt_x or TAP_COORDS["close_x_default"]
            return State.POPUP_EFFECT, {"close_coord": close_pt, "score": score_x}

        # 5f. Full screen modal / Reward Obtained popup (Tap to close window)
        score_obt, _ = self.match(screen, "memory_obtained_title", region=(700, 70, 300, 100))
        scores["memory_obtained_title"] = score_obt
        score_ttc, pt_ttc = self.match(screen, "tap_to_close", region=(500, 800, 600, 100))
        scores["tap_to_close"] = score_ttc
        if score_obt >= self._get_threshold("memory_obtained_title") or score_ttc >= self._get_threshold("tap_to_close"):
            return State.POPUP_EFFECT, {"close_coord": (800, 850), "score": max(score_obt, score_ttc)}

        # 5g. Info detail modal with orange Close button (View Details / Card details)
        score_mcb, pt_mcb = self.match(screen, "modal_close_button", region=(700, 780, 200, 100))
        scores["modal_close_button"] = score_mcb
        if score_mcb >= self._get_threshold("modal_close_button"):
            return State.POPUP_EFFECT, {"close_coord": pt_mcb or TAP_COORDS["modal_close_button"], "score": score_mcb}


        # 6. Check MATCH_DONE screen (Reward text + Confirm button)
        score_reward = 0.0
        reward_keys = ["reward_text", "story_reward_text"]
        for rk in reward_keys:
            if rk not in self.templates:
                continue
            for rx, ry, rw, rh in [
                (800, 450, 350, 150),
                (780, 430, 390, 170),
                (900, 500, 300, 200),
                (500, 550, 600, 200),
            ]:
                s, _ = self.match(screen, rk, region=(rx, ry, rw, rh))
                if s > score_reward:
                    score_reward = s
        scores["reward_text"] = score_reward

        score_confirm = 0.0
        confirm_coord = None
        confirm_keys = ["confirm_button", "confirm_button_purple"]
        for ck in confirm_keys:
            if ck not in self.templates:
                continue
            for rx, ry, rw, rh in [
                (1200, 750, 380, 150),
                (1150, 700, 440, 190),
                (750, 650, 600, 250),
            ]:
                s, pt = self.match(screen, ck, region=(rx, ry, rw, rh))
                if s > score_confirm:
                    score_confirm = s
                    confirm_coord = pt
        scores["confirm_button"] = score_confirm

        thresh_reward = min(self._get_threshold("reward_text"), self._get_threshold("story_reward_text"))
        thresh_confirm = min(self._get_threshold("confirm_button"), self._get_threshold("confirm_button_purple"))

        if score_reward >= thresh_reward or score_confirm >= thresh_confirm:
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

            # Only check for RETRY_DISABLED if retry button was confidently recognized
            if left_btn == LeftButton.RETRY and score_retry >= 0.60:
                btn_crop = screen[795:860, 920:1220]
                if btn_crop.size > 0:
                    hsv = cv2.cvtColor(btn_crop, cv2.COLOR_BGR2HSV)
                    orange_mask = cv2.inRange(hsv, (8, 100, 100), (25, 255, 255))
                    orange_ratio = cv2.countNonZero(orange_mask) / (btn_crop.shape[0] * btn_crop.shape[1])
                    mean_sat = hsv[:, :, 1].mean()
                    if orange_ratio < 0.15 and mean_sat < 35:
                        left_btn = LeftButton.RETRY_DISABLED

            return State.MATCH_DONE, {
                "left_button": left_btn,
                "reward_score": score_reward,
                "confirm_score": score_confirm,
                "retry_score": score_retry,
                "next_score": score_next,
                "confirm_coord": confirm_coord,
            }

        # 6c. In-Match pixel heuristic (HP bar + battle background) when all other screens ruled out
        if self._check_in_match_heuristic(screen):
            return State.IN_MATCH, {"score": 0.0, "heuristic": True}

        # 7. Check TRANSITIONING (animation/cutscene - no UI elements detected)
        max_score = max(scores.values()) if scores else 0.0
        if max_score < 0.50:
            return State.TRANSITIONING, {"max_score": max_score}

        # 7b. Check dark cutscene / animation (heavy dark screen during skill cutscene)
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        dark_ratio = np.sum(gray < 60) / gray.size
        if dark_ratio > 0.65 and max_score < 0.70:
            return State.TRANSITIONING, {"dark_cutscene": True, "dark_ratio": dark_ratio}

        # 8. UNKNOWN - log debug scores for diagnosis
        self._log_unknown_scores(scores)
        return State.UNKNOWN, {}
