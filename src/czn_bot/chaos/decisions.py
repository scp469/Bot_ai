"""
Decision dataclasses, Vision Extraction, and Tactical Decision Logic for Chaos Mode.
Handles:
- Card Info, Event Choice Info, Resource Info, Equipment Info
- Layout ROIs and vision extraction for cards, events, and equipments
- Hybrid Template Matching & OCR button locating (find_action_button)
- Image preprocessing and normalization
"""
import os
import re
import base64
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np

from czn_bot.constants import SCREEN_WIDTH, SCREEN_HEIGHT, TEMPLATES_DIR, DATA_TEMPLATES_DIR, TEMPLATES
from czn_bot.vision.hp_reader import get_team_hp
from czn_bot.vision.ocr import get_ocr_service, OcrService
from czn_bot.chaos.rules import ChaosRuleManager
from czn_bot.chaos.pathfinder import select_best_island, IslandChoice

logger = logging.getLogger("ChaosBot.Decisions")

# Standard Layout ROIs
HP_BAR_ROI = (34, 32, 608, 6)
CREDITS_TOP_ROI = (1180, 15, 260, 52)
CREDITS_FATE_ROI = (100, 830, 150, 50)

CARD_3_LAYOUT = [
    {"roi": (140, 160, 430, 580), "tap": (390, 450), "slot": 0, "name": "Thẻ Trái (Card 1)"},
    {"roi": (585, 160, 430, 580), "tap": (800, 450), "slot": 1, "name": "Thẻ Giữa (Card 2)"},
    {"roi": (1030, 160, 430, 580), "tap": (1205, 450), "slot": 2, "name": "Thẻ Phải (Card 3)"},
]

CARD_4_LAYOUT = [
    {"roi": (90, 200, 330, 520), "tap": (255, 460), "slot": 0, "name": "Thẻ 1"},
    {"roi": (450, 200, 330, 520), "tap": (615, 460), "slot": 1, "name": "Thẻ 2"},
    {"roi": (810, 200, 330, 520), "tap": (975, 460), "slot": 2, "name": "Thẻ 3"},
    {"roi": (1170, 200, 330, 520), "tap": (1335, 460), "slot": 3, "name": "Thẻ 4"},
]

EVENT_HORIZONTAL_CHOICES = [
    {"roi": (250, 300, 1100, 120), "tap": (800, 360), "slot": 0, "name": "Lựa chọn 1"},
    {"roi": (250, 440, 1100, 120), "tap": (800, 500), "slot": 1, "name": "Lựa chọn 2"},
    {"roi": (250, 580, 1100, 120), "tap": (800, 640), "slot": 2, "name": "Lựa chọn 3"},
]

EVENT_BOTTOM_3_CHOICES = [
    {"roi": (170, 660, 410, 205), "tap": (375, 765), "slot": 0, "name": "Lựa chọn 1 (Trái)"},
    {"roi": (590, 660, 410, 205), "tap": (795, 765), "slot": 1, "name": "Lựa chọn 2 (Giữa)"},
    {"roi": (1010, 660, 410, 205), "tap": (1215, 765), "slot": 2, "name": "Lựa chọn 3 (Phải)"},
]

EVENT_BOTTOM_2_CHOICES = [
    {"roi": (280, 660, 480, 205), "tap": (520, 765), "slot": 0, "name": "Lựa chọn 1 (Trái)"},
    {"roi": (840, 660, 480, 205), "tap": (1080, 765), "slot": 1, "name": "Lựa chọn 2 (Phải)"},
]

EVENT_BOTTOM_1_CHOICE = [
    {"roi": (480, 650, 560, 200), "tap": (750, 750), "slot": 0, "name": "Lựa chọn 1 (Giữa)"},
]

EVENT_BANNER_ROI = (150, 130, 1300, 150)

REMOVE_CARD_GRID = [
    {"slot": 0, "roi": (430, 115, 200, 370), "tap": (530, 300)},
    {"slot": 1, "roi": (640, 115, 200, 370), "tap": (740, 300)},
    {"slot": 2, "roi": (850, 115, 200, 370), "tap": (950, 300)},
    {"slot": 3, "roi": (1060, 115, 200, 370), "tap": (1160, 300)},
    {"slot": 4, "roi": (430, 500, 200, 370), "tap": (530, 685)},
    {"slot": 5, "roi": (640, 500, 200, 370), "tap": (740, 685)},
    {"slot": 6, "roi": (850, 500, 200, 370), "tap": (950, 685)},
    {"slot": 7, "roi": (1060, 500, 200, 370), "tap": (1160, 685)},
]


@dataclass
class CardInfo:
    slot: int
    name: str
    tap_coord: Tuple[int, int]
    raw_text: str = ""
    title: str = ""
    variant: str = ""
    keywords: List[str] = field(default_factory=list)
    image: Optional[np.ndarray] = None
    matched_card: Optional[Dict[str, Any]] = None
    priority: int = 0
    description_vi: str = ""
    character: str = ""
    template_path: str = ""
    confidence: float = 0.0


@dataclass
class EventChoiceInfo:
    slot: int
    name: str
    tap_coord: Tuple[int, int]
    text: str = ""
    keywords: List[str] = field(default_factory=list)
    cost_credits: int = 0
    is_combat: bool = False
    is_quiz: bool = False
    is_heal: bool = False
    image: Optional[np.ndarray] = None
    matched_choice: Optional[Dict[str, Any]] = None
    matched_event_name: str = ""
    priority_score: int = 5
    recommendation: str = ""
    outcome_summary: str = ""


@dataclass
class ResourceInfo:
    hp_percent: float
    is_low_hp: bool
    credits: int


@dataclass
class EquipmentInfo:
    slot: int
    name: str
    tap_coord: Tuple[int, int]
    priority: int = 50
    tier: str = "tier_c_filler"
    best_characters: List[str] = field(default_factory=list)
    raw_text: str = ""
    matched_equipment: Optional[Dict[str, Any]] = None


class ChaosVision:
    """Computer Vision, ROI extraction, and Template/OCR matching for Chaos Mode."""

    def __init__(self, ocr_service: Optional[OcrService] = None, rule_manager: Optional[ChaosRuleManager] = None):
        if isinstance(ocr_service, ChaosRuleManager) and rule_manager is None:
            rule_manager = ocr_service
            ocr_service = None
        self.ocr = ocr_service or get_ocr_service()
        self.rule_manager = rule_manager or ChaosRuleManager()
        self._button_templates: Dict[str, np.ndarray] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        keys_to_cache = [
            "confirm_button", "confirm_button_purple",
            "chaos_continue_button", "chaos_leave_button",
            "chaos_obtain_button", "chaos_safe_zone_skip",
            "modal_close_button", "close_x",
            "chaos_event_battle_btn", "chaos_event_icon", "chaos_event_badge"
        ]
        for key in keys_to_cache:
            fname = TEMPLATES.get(key)
            if fname:
                path = os.path.join(TEMPLATES_DIR, fname)
                if os.path.isfile(path):
                    img = cv2.imread(path)
                    if img is not None:
                        self._button_templates[key] = img

    def _load_card_templates(self) -> None:
        """Pre-load card templates from data/templates/Season and character folders."""
        if getattr(self, "_card_templates_loaded", False):
            return
        self._card_templates: List[Tuple[str, str, np.ndarray]] = []
        season_dir = os.path.join(DATA_TEMPLATES_DIR, "Season")
        if os.path.isdir(season_dir):
            for fname in os.listdir(season_dir):
                if fname.endswith((".png", ".webp")):
                    p = os.path.join(season_dir, fname)
                    tpl = cv2.imread(p)
                    if tpl is not None:
                        rel_path = f"Season/{fname}"
                        self._card_templates.append((rel_path, fname, tpl))
        self._card_templates_loaded = True

    def match_card_by_template(self, crop: np.ndarray, threshold: float = 0.65) -> Optional[Dict[str, Any]]:
        """Match a cropped card image against loaded templates (e.g. data/templates/Season)."""
        if not getattr(self, "_card_templates", None):
            self._load_card_templates()
        if crop is None or crop.size == 0 or not self._card_templates:
            return None

        best_score = 0.0
        best_rel_path = None
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        ch, cw = crop_gray.shape[:2]

        for rel_path, fname, tpl in self._card_templates:
            tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY) if len(tpl.shape) == 3 else tpl
            th, tw = tpl_gray.shape[:2]
            if ch >= th and cw >= tw:
                res = cv2.matchTemplate(crop_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
            else:
                scaled_tpl = cv2.resize(tpl_gray, (cw, ch))
                res = cv2.matchTemplate(crop_gray, scaled_tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)

            if max_val > best_score:
                best_score = max_val
                best_rel_path = rel_path

        if best_score >= threshold and best_rel_path and self.rule_manager:
            return (
                self.rule_manager.cards_by_template.get(best_rel_path)
                or self.rule_manager.cards_by_template.get(os.path.basename(best_rel_path))
            )
        return None

    @staticmethod
    def preprocess_image(img: np.ndarray, method: str = "normalize") -> np.ndarray:
        """
        Preprocessing for OCR / computer vision:
        - Gray conversion
        - Contrast normalization or adaptive threshold
        """
        if img is None or img.size == 0:
            return img

        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        if method == "threshold":
            return cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 15, 4
            )
        else:
            return cv2.normalize(gray, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)

    @staticmethod
    def crop_roi(screen: np.ndarray, roi: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        if screen is None or screen.size == 0:
            return None
        h, w = screen.shape[:2]
        rx, ry, rw, rh = roi
        rx = max(0, min(w - 1, rx))
        ry = max(0, min(h - 1, ry))
        rw = max(1, min(w - rx, rw))
        rh = max(1, min(h - ry, rh))
        return screen[ry : ry + rh, rx : rx + rw]

    def extract_cards(self, screen: np.ndarray, num_cards: int = 3) -> List[CardInfo]:
        layout = CARD_3_LAYOUT if num_cards == 3 else CARD_4_LAYOUT
        extracted = []
        known_keywords = [
            "Elasticity", "Extra Attack", "Action Point", "Morale",
            "Rare", "Heal", "Discard", "Base", "Skill"
        ]

        for item in layout:
            crop = self.crop_roi(screen, item["roi"])
            norm_crop = self.preprocess_image(crop, method="normalize") if crop is not None and crop.size > 0 else None
            text = (self.ocr.read_text(norm_crop) if norm_crop is not None else "") or (self.ocr.read_text(crop) if crop is not None else "")

            title = ""
            variant = "Base"
            found_keywords: List[str] = []

            text_clean = text.replace("\n", " ").strip()
            for kw in known_keywords:
                if kw.lower() in text_clean.lower():
                    found_keywords.append(kw)

            if "elasticity" in text_clean.lower():
                variant = "Elasticity"
            elif "base" in text_clean.lower():
                variant = "Base"
            elif "skill" in text_clean.lower():
                variant = "Skill"

            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            if lines:
                title = lines[0]

            matched_card = None
            priority = 0
            desc_vi = ""
            char_name = ""
            tpl_path = ""
            if self.rule_manager:
                matched_card = self.rule_manager.match_card(text_clean)
                if not matched_card and crop is not None:
                    matched_card = self.match_card_by_template(crop)

                if matched_card:
                    title = matched_card.get("name", title)
                    variant = matched_card.get("variant", variant)
                    priority = matched_card.get("priority", 0)
                    desc_vi = matched_card.get("description_vi", "")
                    char_name = matched_card.get("character", "")
                    tpl_path = matched_card.get("template_path", "")
                    for kw in matched_card.get("keywords", []):
                        if kw not in found_keywords:
                            found_keywords.append(kw)

            card_conf = 0.90 if matched_card else (0.60 if title else 0.30)
            card = CardInfo(
                slot=item["slot"],
                name=item["name"],
                tap_coord=item["tap"],
                raw_text=text_clean,
                title=title,
                variant=variant,
                keywords=found_keywords,
                image=crop,
                matched_card=matched_card,
                priority=priority,
                description_vi=desc_vi,
                character=char_name,
                template_path=tpl_path,
                confidence=card_conf
            )
            extracted.append(card)

        return extracted

    def extract_single_card_reward(self, screen: np.ndarray) -> Dict[str, Any]:
        """
        Extract the single reward card offered on the Card Reward screen (left region).
        Returns title, raw_text, is_memory flag, and card crop.
        """
        if screen is None or getattr(screen, "size", 0) == 0:
            return {"title": "Card Reward", "raw_text": "", "is_memory": False, "crop": None}
        crop = self.crop_roi(screen, (100, 160, 440, 660))
        norm = self.preprocess_image(crop, method="normalize") if crop is not None and crop.size > 0 else None
        raw_text = (self.ocr.read_text(norm) if norm is not None else "") or (self.ocr.read_text(crop) if crop is not None else "")

        title = "Card Reward"
        lines = [ln.strip() for ln in raw_text.split("\n") if ln.strip()]
        if lines:
            cleaned_line = re.sub(r"^[^a-zA-Z0-9]+", "", lines[0]).strip()
            if cleaned_line:
                title = cleaned_line

        is_memory = "memory" in raw_text.lower()
        return {
            "title": title,
            "raw_text": raw_text,
            "is_memory": is_memory,
            "crop": crop
        }

    def extract_remove_cards(self, screen: np.ndarray) -> List[Dict[str, Any]]:
        """Extract up to 8 visible cards on the Remove Card screen."""
        if screen is None or getattr(screen, "size", 0) == 0:
            return []
        results = []
        for item in REMOVE_CARD_GRID:
            crop = self.crop_roi(screen, item["roi"])
            header = crop[:70, :] if crop is not None and crop.shape[0] >= 70 else crop
            title = self.ocr.read_text(header).strip() if header is not None else ""
            if len(title) > 2:
                results.append({
                    "slot": item["slot"],
                    "tap_coord": item["tap"],
                    "title": title,
                })
        return results

    def extract_event_choices(self, screen: np.ndarray) -> List[EventChoiceInfo]:
        """
        Extract event choices supporting:
        1. Bottom 3 horizontal cards (Standard Chaos event encounter, e.g. Poacher wager)
        2. Bottom 2 horizontal cards (Binary choices)
        3. Vertical stacked bars (Dialogue event choices)
        4. Vertical card layout (3 cards like Choose Fate / Epiphany)
        Prefers the layout that yields rules matches or better OCR results.
        """
        if screen is None or screen.size == 0:
            return []

        # Optional: Read banner text if present
        banner_crop = self.crop_roi(screen, EVENT_BANNER_ROI)
        banner_text = ""
        if banner_crop is not None and banner_crop.size > 0:
            norm_b = self.preprocess_image(banner_crop, method="normalize")
            banner_text = (self.ocr.read_text(norm_b) or self.ocr.read_text(banner_crop)).strip()

        # 1. Check Bottom 3 cards (Standard random event layout)
        b3_choices: List[EventChoiceInfo] = []
        b3_matches = 0
        b3_total_len = 0
        for item in EVENT_BOTTOM_3_CHOICES:
            crop = self.crop_roi(screen, item["roi"])
            norm_crop = self.preprocess_image(crop, method="normalize") if crop is not None and crop.size > 0 else None
            text = (self.ocr.read_text(norm_crop) if norm_crop is not None else "") or (self.ocr.read_text(crop) if crop is not None else "")
            if len(text.strip()) > 3:
                b3_total_len += len(text.strip())
                choice = self._parse_event_choice(item["slot"], item["name"], item["tap"], text, crop)
                if choice.matched_choice:
                    b3_matches += 1
                b3_choices.append(choice)

        if len(b3_choices) >= 2 and (b3_matches >= 1 or b3_total_len >= 30):
            return b3_choices

        # 1b. Check Bottom 1 card (Single Center choice, e.g. Waypoint / Shrine interaction)
        crop_center = self.crop_roi(screen, EVENT_BOTTOM_1_CHOICE[0]["roi"])
        crop_left = self.crop_roi(screen, (170, 660, 300, 200))
        crop_right = self.crop_roi(screen, (1050, 660, 300, 200))
        txt_c = (self.ocr.read_text(crop_center) if crop_center is not None else "").strip()
        txt_l = (self.ocr.read_text(crop_left) if crop_left is not None else "").strip()
        txt_r = (self.ocr.read_text(crop_right) if crop_right is not None else "").strip()

        if len(txt_c) >= 8 and len(txt_l) < 5 and len(txt_r) < 5:
            choice = self._parse_event_choice(
                EVENT_BOTTOM_1_CHOICE[0]["slot"],
                EVENT_BOTTOM_1_CHOICE[0]["name"],
                EVENT_BOTTOM_1_CHOICE[0]["tap"],
                txt_c,
                crop_center
            )
            return [choice]

        # 2. Check Bottom 2 cards
        b2_choices: List[EventChoiceInfo] = []
        b2_matches = 0
        b2_total_len = 0
        for item in EVENT_BOTTOM_2_CHOICES:
            crop = self.crop_roi(screen, item["roi"])
            norm_crop = self.preprocess_image(crop, method="normalize") if crop is not None and crop.size > 0 else None
            text = (self.ocr.read_text(norm_crop) if norm_crop is not None else "") or (self.ocr.read_text(crop) if crop is not None else "")
            if len(text.strip()) > 3:
                b2_total_len += len(text.strip())
                choice = self._parse_event_choice(item["slot"], item["name"], item["tap"], text, crop)
                if choice.matched_choice:
                    b2_matches += 1
                b2_choices.append(choice)

        if len(b2_choices) == 2 and (b2_matches >= 1 or b2_total_len >= 20):
            return b2_choices

        # 3. Horizontal stacked choices
        h_choices: List[EventChoiceInfo] = []
        h_total_len = 0
        h_matches = 0
        for item in EVENT_HORIZONTAL_CHOICES:
            crop = self.crop_roi(screen, item["roi"])
            norm_crop = self.preprocess_image(crop, method="normalize") if crop is not None and crop.size > 0 else None
            text = (self.ocr.read_text(norm_crop) if norm_crop is not None else "") or (self.ocr.read_text(crop) if crop is not None else "")
            if len(text.strip()) > 3:
                h_total_len += len(text.strip())
                choice = self._parse_event_choice(item["slot"], item["name"], item["tap"], text, crop)
                if choice.matched_choice:
                    h_matches += 1
                h_choices.append(choice)

        # 4. Vertical cards (Choose Fate)
        v_choices: List[EventChoiceInfo] = []
        v_total_len = 0
        v_matches = 0
        for item in CARD_3_LAYOUT:
            crop = self.crop_roi(screen, item["roi"])
            norm_crop = self.preprocess_image(crop, method="normalize") if crop is not None and crop.size > 0 else None
            text = (self.ocr.read_text(norm_crop) if norm_crop is not None else "") or (self.ocr.read_text(crop) if crop is not None else "")
            if len(text.strip()) > 3:
                v_total_len += len(text.strip())
                choice = self._parse_event_choice(item["slot"], item["name"], item["tap"], text, crop)
                if choice.matched_choice:
                    v_matches += 1
                v_choices.append(choice)

        candidates = [
            (b3_matches, b3_total_len, b3_choices),
            (b2_matches, b2_total_len, b2_choices),
            (h_matches, h_total_len, h_choices),
            (v_matches, v_total_len, v_choices),
        ]
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        best_set = candidates[0][2]
        if best_set:
            return best_set

        return []

    def _parse_event_choice(self, slot: int, name: str, tap_coord: Tuple[int, int],
                            text: str, crop: np.ndarray) -> EventChoiceInfo:
        text_lower = text.lower()
        is_combat = any(w in text_lower for w in ["combat", "battle", "fight", "boss", "enemy", "đánh", "quái"])
        is_quiz = any(w in text_lower for w in ["quiz", "riddle", "question", "câu đố", "hỏi"])
        is_heal = any(w in text_lower for w in ["heal", "health", "hp", "recover", "rest", "hồi máu"])

        cost = 0
        text_clean = re.sub(r"[,.]", "", text_lower)
        matches = re.findall(r"(\d+)\s*(?:credits|gold|tiền)", text_clean)
        if matches:
            cost = int(matches[0])

        matched_choice = None
        matched_event_name = ""
        priority_score = 5
        recommendation = ""
        outcome_summary = ""

        if self.rule_manager:
            res = self.rule_manager.match_event_choice(text)
            if res:
                matched_choice, ev_dict = res
                matched_event_name = ev_dict.get("event_name", "")
                priority_score = matched_choice.get("priority_score", 5)
                recommendation = matched_choice.get("recommendation", "")
                outcome_summary = matched_choice.get("outcome_summary", "")

                out_lower = outcome_summary.lower()
                if any(w in out_lower for w in ["combat", "battle", "fight", "boss", "attack", "engage"]):
                    is_combat = True
                if any(w in out_lower for w in ["heal", "health", "hp", "recover", "stress", "hồi"]):
                    is_heal = True
                if "credits" in out_lower:
                    m = re.findall(r"(?:spend|requires >=?)\s*(\d+)\s*credits", out_lower)
                    if m:
                        cost = int(m[0])

        keywords: List[str] = []
        if is_combat: keywords.append("Combat/Boss")
        if is_quiz: keywords.append("Quiz")
        if is_heal: keywords.append("Heal")
        if cost > 0: keywords.append(f"Cost:{cost}")

        return EventChoiceInfo(
            slot=slot,
            name=name,
            tap_coord=tap_coord,
            text=text.replace("\n", " ").strip(),
            keywords=keywords,
            cost_credits=cost,
            is_combat=is_combat,
            is_quiz=is_quiz,
            is_heal=is_heal,
            image=crop,
            matched_choice=matched_choice,
            matched_event_name=matched_event_name,
            priority_score=priority_score,
            recommendation=recommendation,
            outcome_summary=outcome_summary
        )

    def extract_resources(self, screen: np.ndarray) -> ResourceInfo:
        hp_percent, is_low = get_team_hp(screen)
        credits_val = 0

        crop_top = self.crop_roi(screen, CREDITS_TOP_ROI)
        norm_top = self.preprocess_image(crop_top, method="normalize") if crop_top is not None and crop_top.size > 0 else None
        text_credits = (self.ocr.read_text(norm_top) if norm_top is not None else "") or (self.ocr.read_text(crop_top) if crop_top is not None else "")

        text_credits_clean = re.sub(r"[,.]", "", text_credits)
        nums = re.findall(r"\d+", text_credits_clean)
        if nums:
            try:
                credits_val = int(nums[0])
            except ValueError:
                pass
        else:
            crop_fate = self.crop_roi(screen, CREDITS_FATE_ROI)
            text_fate = self.ocr.read_text(crop_fate) if crop_fate is not None and crop_fate.size > 0 else ""
            text_fate_clean = re.sub(r"[,.]", "", text_fate)
            nums_fate = re.findall(r"\d+", text_fate_clean)
            if nums_fate:
                try:
                    credits_val = int(nums_fate[0])
                except ValueError:
                    pass

        return ResourceInfo(
            hp_percent=hp_percent,
            is_low_hp=is_low,
            credits=credits_val,
        )

    def extract_equipments(self, screen: np.ndarray) -> List[EquipmentInfo]:
        candidates: List[EquipmentInfo] = []
        if screen is None or screen.size == 0:
            return candidates

        equip_slots = [
            {"slot": 0, "roi": (350, 200, 320, 350), "tap": (500, 350)},
            {"slot": 1, "roi": (700, 200, 320, 350), "tap": (850, 350)},
        ]

        for item in equip_slots:
            crop = self.crop_roi(screen, item["roi"])
            raw_text = self.ocr.read_text(crop) if crop is not None and crop.size > 0 else ""
            matched = self.rule_manager.match_equipment(raw_text) if self.rule_manager else None

            priority = 50
            tier = "tier_c_filler"
            best_chars = []
            name = f"Trang bị {item['slot'] + 1}"

            if matched:
                name = matched.get("name", name)
                priority = matched.get("priority", 50)
                tier = matched.get("tier", "tier_c_filler")
                best_chars = matched.get("best_characters", [])

            candidates.append(EquipmentInfo(
                slot=item["slot"],
                name=name,
                tap_coord=item["tap"],
                priority=priority,
                tier=tier,
                best_characters=best_chars,
                raw_text=raw_text,
                matched_equipment=matched
            ))

        candidates.sort(key=lambda x: x.priority, reverse=True)
        return candidates

    def find_button(self, screen: np.ndarray, template_key: str, threshold: float = 0.75) -> Optional[Tuple[int, int]]:
        tpl = self._button_templates.get(template_key)
        if tpl is None or screen is None:
            return None

        sh, sw = screen.shape[:2]
        th, tw = tpl.shape[:2]
        if sh < th or sw < tw:
            return None

        res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            return cx, cy

        return None

    def find_action_button(self, screen: np.ndarray, action_type: str = "confirm") -> Optional[Tuple[int, int]]:
        # 1. Template matching
        template_map = {
            "confirm": ["confirm_button", "confirm_button_purple"],
            "battle": ["chaos_event_battle_btn"],
            "continue": ["chaos_continue_button"],
            "leave": ["chaos_leave_button"],
            "obtain": ["chaos_obtain_button"],
            "skip": ["chaos_safe_zone_skip"],
            "close": ["modal_close_button", "close_x"]
        }
        for tpl_name in template_map.get(action_type, []):
            pt = self.find_button(screen, tpl_name)
            if pt is not None:
                return pt

        # 2. OCR Search
        keyword_map = {
            "confirm": ["Confirm", "Xác nhận", "OK"],
            "battle": ["Battle", "Fight", "Chiến đấu", "Đánh"],
            "continue": ["Continue", "Tiếp tục"],
            "leave": ["Leave", "Rời đi"],
            "obtain": ["Obtain", "Nhận"],
            "skip": ["Skip", "Bỏ qua"],
            "close": ["Close", "Đóng"]
        }
        for kw in keyword_map.get(action_type, []):
            pt = self.ocr.find_text(screen, kw)
            if pt is not None:
                return pt

        # 3. Fallback coordinates (1600x900)
        fallback_coords = {
            "confirm": (1425, 835),
            "battle": (1475, 830),
            "continue": (1415, 825),
            "leave": (1426, 828),
            "obtain": (1380, 830),
            "skip": (1415, 825),
            "close": (1535, 50)
        }
        return fallback_coords.get(action_type)

    @staticmethod
    def encode_image_for_ai(img: np.ndarray, format: str = "jpeg") -> str:
        if img is None or img.size == 0:
            return ""
        ext = f".{format}"
        success, buffer = cv2.imencode(ext, img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not success:
            return ""
        return base64.b64encode(buffer).decode("ascii")
