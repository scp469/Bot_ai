"""
Computer Vision & Preprocessing Module for Chaos Zero Nightmare ("Mắt").
Handles:
- Fixed ROI cropping on 1600x900 resolution (Hand cards, Event choices, Resources HP/Credits)
- OpenCV image preprocessing (grayscale, contrast normalization, thresholding)
- Text extraction with OCR & keyword identification (e.g. Elasticity vs Base)
- Template matching fallback for static buttons (Confirm, Continue, Leave, Close X)
- Encoding cropped ROIs for Cloud AI Multi-modal Vision fallback
"""
import base64
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np

from chaos_hp_reader import get_team_hp
from ocr_service import OcrService

logger = logging.getLogger("ChaosBot.Vision")

# ── 1600x900 Standard Resolution Constants ─────────────────────────
STANDARD_WIDTH = 1600
STANDARD_HEIGHT = 900

# Top-bar Resources ROI
HP_BAR_ROI = (34, 32, 608, 6)             # (x, y, w, h)
CREDITS_TOP_ROI = (1180, 15, 260, 52)      # Top-right Credits
CREDITS_FATE_ROI = (100, 830, 150, 50)     # Bottom-left Credits in Choose Fate screen

# 3-Card Layout ROIs (Epiphany, Fate, Card Reward): (x, y, w, h) and tap center (tx, ty)
CARD_3_LAYOUT = [
    {"roi": (140, 160, 430, 580), "tap": (355, 460), "slot": 0, "name": "Thẻ Trái (Card 1)"},
    {"roi": (585, 160, 430, 580), "tap": (800, 460), "slot": 1, "name": "Thẻ Giữa (Card 2)"},
    {"roi": (1030, 160, 430, 580), "tap": (1245, 460), "slot": 2, "name": "Thẻ Phải (Card 3)"},
]

# 4-Card Layout ROIs (In-hand or 4 reward choices)
CARD_4_LAYOUT = [
    {"roi": (90, 200, 330, 520), "tap": (255, 460), "slot": 0, "name": "Thẻ 1"},
    {"roi": (450, 200, 330, 520), "tap": (615, 460), "slot": 1, "name": "Thẻ 2"},
    {"roi": (810, 200, 330, 520), "tap": (975, 460), "slot": 2, "name": "Thẻ 3"},
    {"roi": (1170, 200, 330, 520), "tap": (1335, 460), "slot": 3, "name": "Thẻ 4"},
]

# Horizontal Event Choices ROIs (Dialogue/Event prompts): 3 stacked horizontal bars
EVENT_HORIZONTAL_CHOICES = [
    {"roi": (250, 300, 1100, 120), "tap": (800, 360), "slot": 0, "name": "Lựa chọn 1"},
    {"roi": (250, 440, 1100, 120), "tap": (800, 500), "slot": 1, "name": "Lựa chọn 2"},
    {"roi": (250, 580, 1100, 120), "tap": (800, 640), "slot": 2, "name": "Lựa chọn 3"},
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


class ChaosVision:
    """Computer Vision & Image Preprocessing Pipeline for Chaos Mode."""

    def __init__(self, ocr_service: Optional[OcrService] = None, rule_manager: Optional[Any] = None):
        self.ocr = ocr_service or OcrService()
        self.rule_manager = rule_manager
        if self.rule_manager is None:
            try:
                from chaos_ai_config import ChaosRuleManager
                self.rule_manager = ChaosRuleManager()
            except Exception:
                self.rule_manager = None
        self._button_templates: Dict[str, np.ndarray] = {}
        self._load_templates()

    def _load_templates(self):
        """Pre-cache common action button templates for fast template matching fallback."""
        import os
        from config import TEMPLATES_DIR, TEMPLATES
        keys_to_cache = [
            "confirm_button", "confirm_button_purple",
            "chaos_continue_button", "chaos_leave_button",
            "chaos_obtain_button", "modal_close_button", "close_x",
            "chaos_safe_zone_skip"
        ]
        for key in keys_to_cache:
            filename = TEMPLATES.get(key)
            if filename:
                filepath = os.path.join(TEMPLATES_DIR, filename)
                if os.path.exists(filepath):
                    tpl = cv2.imread(filepath)
                    if tpl is not None:
                        self._button_templates[key] = tpl

    # ── 2.2. Preprocessing với OpenCV ──────────────────────────────

    @staticmethod
    def preprocess_image(img: np.ndarray, method: str = "normalize") -> np.ndarray:
        """
        Tiền xử lý ảnh theo yêu cầu:
        - cv2.cvtColor(img, cv2.COLOR_BGR2GRAY): Chuyển ảnh xám loại bỏ nhiễu màu
        - cv2.normalize() hoặc cv2.threshold(): Tăng tương phản, làm nổi bật chữ trắng/vàng
        """
        if img is None or img.size == 0:
            return img

        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        if method == "threshold":
            # Adaptive threshold for sharp high-contrast text
            return cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 15, 4
            )
        else:
            # Contrast normalization
            return cv2.normalize(gray, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)

    @staticmethod
    def crop_roi(screen: np.ndarray, roi: Tuple[int, int, int, int]) -> np.ndarray:
        """Cắt khung hình chữ nhật an toàn theo (x, y, w, h)."""
        x, y, w, h = roi
        sh, sw = screen.shape[:2]
        x1 = max(0, min(sw - 1, x))
        y1 = max(0, min(sh - 1, y))
        x2 = max(0, min(sw, x + w))
        y2 = max(0, min(sh, y + h))
        return screen[y1:y2, x1:x2]

    # ── 2.1 & 2.3. Nhận diện Thẻ Bài & Biến thể ─────────────────────

    def extract_cards(self, screen: np.ndarray, num_cards: int = 3) -> List[CardInfo]:
        """
        Cắt các khung hình chữ nhật chứa các lá bài (3 hoặc 4 thẻ).
        Đọc text mô tả bằng OCR, phát hiện biến thể (ví dụ: Elasticity vs Base).
        Lưu kèm ảnh cắt để sẵn sàng cho Cloud AI Vision Fallback.
        """
        layout = CARD_3_LAYOUT if num_cards == 3 else CARD_4_LAYOUT
        extracted: List[CardInfo] = []

        known_keywords = [
            "Elasticity", "Base", "Extra Attack", "Action Point", "Morale",
            "Rare", "Heal", "Discard", "Critical", "Focus", "Possession",
            "Passion", "Mute Accent", "Amp Therapy", "Kaleidoscope"
        ]

        for item in layout:
            crop = self.crop_roi(screen, item["roi"])
            norm_crop = self.preprocess_image(crop, method="normalize")
            text = self.ocr.read_text(norm_crop) or self.ocr.read_text(crop)

            # Phân tích tiêu đề và biến thể từ text
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

            # Tách dòng đầu làm tiêu đề nếu có
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
                template_path=tpl_path
            )
            extracted.append(card)

        return extracted

    # ── 2.1 & 2.3. Nhận diện Lựa chọn Sự Kiện ───────────────────────

    def extract_event_choices(self, screen: np.ndarray) -> List[EventChoiceInfo]:
        """
        Đọc các lựa chọn sự kiện:
        Tự động so sánh giữa layout dạng 3 thẻ bài đứng (Vertical cards như Choose Fate)
        và layout dạng 3 thanh lựa chọn ngang (Horizontal bars như hộp thoại sự kiện).
        Chọn layout cho kết quả văn bản đầy đủ và rõ ràng nhất.
        """
        # 1. Thử layout 3 thẻ đứng (Vertical cards)
        v_choices: List[EventChoiceInfo] = []
        v_total_len = 0
        for item in CARD_3_LAYOUT:
            crop = self.crop_roi(screen, item["roi"])
            norm_crop = self.preprocess_image(crop, method="normalize")
            text = self.ocr.read_text(norm_crop) or self.ocr.read_text(crop)
            if len(text.strip()) > 3:
                v_total_len += len(text.strip())
                choice = self._parse_event_choice(item["slot"], item["name"], item["tap"], text, crop)
                v_choices.append(choice)

        # 2. Thử layout 3 thanh ngang (Horizontal choices)
        h_choices: List[EventChoiceInfo] = []
        h_total_len = 0
        for item in EVENT_HORIZONTAL_CHOICES:
            crop = self.crop_roi(screen, item["roi"])
            norm_crop = self.preprocess_image(crop, method="normalize")
            text = self.ocr.read_text(norm_crop) or self.ocr.read_text(crop)
            if len(text.strip()) > 3:
                h_total_len += len(text.strip())
                choice = self._parse_event_choice(item["slot"], item["name"], item["tap"], text, crop)
                h_choices.append(choice)

        # Ưu tiên layout có nhiều lựa chọn hợp lệ hơn và tổng độ dài text tốt hơn
        if len(v_choices) >= 2 and v_total_len >= h_total_len:
            return v_choices
        elif len(h_choices) > 0:
            return h_choices
        elif len(v_choices) > 0:
            return v_choices

        return []

    def _parse_event_choice(self, slot: int, name: str, tap_coord: Tuple[int, int],
                            text: str, crop: np.ndarray) -> EventChoiceInfo:
        """Phân loại lựa chọn sự kiện (đánh boss, quiz, tốn tiền, hồi máu...)."""
        text_lower = text.lower()
        is_combat = any(w in text_lower for w in ["combat", "battle", "fight", "boss", "enemy", "đánh", "quái"])
        is_quiz = any(w in text_lower for w in ["quiz", "riddle", "question", "câu đố", "hỏi"])
        is_heal = any(w in text_lower for w in ["heal", "health", "hp", "recover", "rest", "hồi máu"])
        
        # Nhận diện chi phí credits nếu có
        import re
        cost = 0
        matches = re.findall(r"(\d+)\s*(?:credits|gold|tiền)", text_lower)
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

    # ── 2.1. Đọc Tài Nguyên Máu (HP) & Credits ─────────────────────

    def extract_resources(self, screen: np.ndarray) -> ResourceInfo:
        """
        Đọc chỉ số Máu (HP %) và số lượng Credits hiện có từ thanh trên cùng.
        """
        # 1. Đọc HP từ thanh máu
        hp_percent, is_low = get_team_hp(screen)

        # 2. Đọc Credits từ góc trên bên phải (hoặc góc dưới trái ở màn chọn Fate)
        credits_val = 0
        crop_top = self.crop_roi(screen, CREDITS_TOP_ROI)
        norm_top = self.preprocess_image(crop_top, method="normalize")
        text_credits = self.ocr.read_text(norm_top) or self.ocr.read_text(crop_top)

        # Lọc số
        import re
        nums = re.findall(r"\d+", text_credits)
        if nums:
            try:
                credits_val = int(nums[0])
            except ValueError:
                pass
        else:
            # Thử đọc ở góc dưới trái (Choose Fate)
            crop_fate = self.crop_roi(screen, CREDITS_FATE_ROI)
            text_fate = self.ocr.read_text(crop_fate)
            nums_fate = re.findall(r"\d+", text_fate)
            if nums_fate:
                try:
                    credits_val = int(nums_fate[0])
                except ValueError:
                    pass

        return ResourceInfo(
            hp_percent=hp_percent,
            is_low_hp=is_low,
            credits=credits_val
        )

    # ── 2.3. Template Matching & OCR Button Fallback ───────────────

    def find_button(self, screen: np.ndarray, template_key: str,
                    threshold: float = 0.75) -> Optional[Tuple[int, int]]:
        """
        Template matching dự phòng để quét nhanh vị trí nút bấm cố định
        (Nút Confirm, Continue, Leave, Close X...) bằng cv2.matchTemplate.
        """
        tpl = self._button_templates.get(template_key)
        if tpl is None or screen is None:
            return None

        sh, sw = screen.shape[:2]
        th, tw = tpl.shape[:2]
        if sh < th or sw < tw:
            return None

        # Template matching
        res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            th, tw = tpl.shape[:2]
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            logger.debug(f"Template match '{template_key}' score={max_val:.2f} at ({cx}, {cy})")
            return cx, cy

        return None

    def find_action_button(self, screen: np.ndarray,
                           action_type: str = "confirm") -> Optional[Tuple[int, int]]:
        """
        Thẩm định kép (Template Matching + OCR Search) để tìm nút hành động:
        - action_type: 'confirm', 'continue', 'leave', 'obtain', 'close'
        """
        # 1. Thử Template matching trước
        template_map = {
            "confirm": ["confirm_button", "confirm_button_purple"],
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

        # 2. Thử OCR tìm từ khóa trên màn hình
        keyword_map = {
            "confirm": ["Confirm", "Xác nhận", "OK"],
            "continue": ["Continue", "Tiếp tục"],
            "leave": ["Leave", "Rời đi"],
            "obtain": ["Obtain", "Nhận"],
            "skip": ["Skip", "Bỏ qua"],
            "close": ["Close", "Đóng"]
        }
        for kw in keyword_map.get(action_type, []):
            pt = self.ocr.find_text(screen, kw)
            if pt is not None:
                logger.debug(f"OCR found button '{kw}' at {pt}")
                return pt

        # 3. Fallback tọa độ mặc định chuẩn 1600x900
        fallback_coords = {
            "confirm": (1425, 835),
            "continue": (1415, 825),
            "leave": (1426, 828),
            "obtain": (1380, 830),
            "skip": (1415, 825),
            "close": (1535, 50)
        }
        return fallback_coords.get(action_type)

    # ── Chuyển đổi ảnh cho Multi-modal Vision ───────────────────────

    @staticmethod
    def encode_image_for_ai(img: np.ndarray, format: str = "jpeg") -> str:
        """Mã hóa ảnh OpenCV BGR thành chuỗi Base64 gửi kèm request Cloud AI."""
        if img is None or img.size == 0:
            return ""
        ext = f".{format}"
        success, buffer = cv2.imencode(ext, img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not success:
            return ""
        return base64.b64encode(buffer).decode("ascii")
