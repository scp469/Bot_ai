"""
Tactical Decision & Heuristic Rule Engine for Chaos Zero Nightmare (100% Offline).
Handles:
- Offline Heuristic Card Decisions: Priority list, variant matching, keyword weights
- Offline Event Decisions: Priorities, quiz rules, credit reserve & HP threshold guards
- Offline Island Path Decisions: Best DAG path selection
"""
import re
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from PIL import Image
import numpy as np
import cv2

from czn_bot.states import State
from czn_bot.chaos.rules import ChaosRuleManager
from czn_bot.chaos.decisions import CardInfo, EventChoiceInfo, ResourceInfo, ChaosVision
from czn_bot.chaos.pathfinder import IslandChoice, IslandEvaluation
from czn_bot.chaos.deck_evaluator import DeckEvaluator
from czn_bot.chaos.deck_preset import load_preset

logger = logging.getLogger("ChaosBot.AIBrain")


def _normalize_model_name(model_name: Optional[str]) -> str:
    """Normalize and validate Gemini model name, defaulting to gemini-2.5-flash."""
    if not model_name:
        return "gemini-2.5-flash"
    m = model_name.strip().lower()
    if "3.5" in m or "2.5" in m or "lite" in m:
        return "gemini-2.5-flash"
    if "2.0" in m:
        return "gemini-2.0-flash"
    if "1.5" in m:
        return "gemini-1.5-flash"
    return model_name.strip()


class ChaosAIBrain:
    """Tactical Decision Engine powered by local rules and heuristics (100% Offline)."""

    def __init__(self, rule_manager: Optional[ChaosRuleManager] = None):
        self.rule_manager = rule_manager or ChaosRuleManager()
        self._genai_client = None
        self._current_api_key = None
        self.deck_evaluator = DeckEvaluator()
        try:
            for char in ["rossweisse", "tiphera"]:
                try:
                    p = load_preset(char, card_rules=self.rule_manager.card_rules)
                    self.deck_evaluator.presets[p.character] = p
                except Exception:
                    pass
        except Exception:
            pass

    def _get_client(self, override_key: Optional[str] = None):
        """
        Return the active client only if explicitly injected (e.g. mock in tests).
        In normal offline operation, remote Gemini client is disabled.
        """
        return self._genai_client

    def test_connection(self, api_key: Optional[str] = None, model_name: Optional[str] = None) -> Tuple[bool, str]:
        return False, "Chế độ AI đám mây đã được gỡ bỏ. Bot hoạt động 100% offline bằng quy tắc cục bộ."

    def _build_system_prompt(self) -> str:
        card_rules = self.rule_manager.card_rules
        event_rules = self.rule_manager.event_rules

        priority_cards_str = json.dumps(card_rules.get("priority_list", []), ensure_ascii=False, indent=2)
        keyword_weights_str = json.dumps(card_rules.get("keyword_weights", {}), ensure_ascii=False, indent=2)
        event_priorities_str = json.dumps(event_rules.get("priorities", {}), ensure_ascii=False, indent=2)
        event_strategy_notes = event_rules.get("strategy_notes", "")

        prompt = f"""Bạn là một chuyên gia chiến thuật AI cho game Chaos Zero Nightmare.
Nhiệm vụ của bạn là phân tích các lựa chọn (thẻ bài hoặc sự kiện ngẫu nhiên) và đưa ra quyết định tối ưu nhất dựa trên bộ quy tắc người dùng đã cấu hình.

=== BỘ QUY TẮC THẺ BÀI (CARD RULES) ===
1. Danh sách thẻ ưu tiên theo thứ tự:
{priority_cards_str}

2. Trọng số từ khóa biến thể (Keyword Weights):
{keyword_weights_str}
(Lưu ý: Luôn ưu tiên biến thể thẻ được chỉ định, ví dụ Amp Therapy [Elasticity] > Amp Therapy [Base]).

=== BỘ QUY TẮC SỰ KIỆN (EVENT RULES) ===
1. Tiêu chí ưu tiên sự kiện:
{event_priorities_str}
- min_credit_reserve: {event_rules.get("min_credit_reserve", 100)} (Bảo toàn số Credits tối thiểu)
- hp_critical_threshold: {event_rules.get("hp_critical_threshold", 0.50)} (Ngưỡng máu nguy cấp)

2. Hướng dẫn chiến thuật sự kiện:
{event_strategy_notes}

=== YÊU CẦU ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC JSON SẠCH) ===
Bạn CHỈ ĐƯỢC PHÉP trả về một chuỗi JSON hợp lệ, KHÔNG kèm theo markdown format thừa thãi, theo cấu trúc:
{{
  "action": "choose_card" | "choose_event_option" | "choose_island",
  "target_index": 0 | 1 | 2,
  "confidence": 0.95,
  "reason": "Lý do ngắn gọn bằng tiếng Việt"
}}
"""
        return prompt

    def decide_card(self, cards: List[CardInfo], resources: ResourceInfo) -> Dict[str, Any]:
        """Quyết định chọn thẻ bài 100% offline dựa trên bảng quy tắc ưu tiên và OCR/templates."""
        if not cards:
            return {"action": "choose_card", "target_index": 1, "confidence": 0.5, "reason": "Không có dữ liệu thẻ, chọn mặc định thẻ giữa"}

        return self._heuristic_card_decision(cards, resources)

    def decide_event(self, choices: List[EventChoiceInfo], resources: ResourceInfo) -> Dict[str, Any]:
        """Quyết định lựa chọn sự kiện 100% offline dựa trên bảng quy tắc sự kiện và templates."""
        if not choices:
            return {"action": "choose_event_option", "target_index": 0, "confidence": 0.5, "reason": "Không có lựa chọn sự kiện, chọn phương án 1"}

        return self._heuristic_event_decision(choices, resources)

    def decide_island(
        self,
        evaluations: Dict[IslandChoice, IslandEvaluation],
        resources: ResourceInfo,
        strategy_mode: str = "balanced",
        fallback_island: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Quyết định chọn đảo Chaos 100% offline dựa trên thuật toán tìm đường DAG điểm cao nhất."""
        valid_islands = {k: v for k, v in evaluations.items() if v.is_available and v.best_path}
        if not valid_islands:
            fallback_val = getattr(fallback_island, "value", str(fallback_island)) if fallback_island else "middle"
            return {"action": "choose_island", "target_island": fallback_val, "confidence": 0.4, "reason": "Không có nhánh nào hợp lệ theo thuật toán"}

        best_isl = max(valid_islands.keys(), key=lambda k: valid_islands[k].best_score)
        return {
            "action": "choose_island",
            "target_island": best_isl.value,
            "confidence": 0.90,
            "reason": f"Chọn đảo {best_isl.value} điểm cao nhất ({valid_islands[best_isl].best_score:.1f}đ)"
        }

    def analyze_unknown_screen(
        self,
        screen: np.ndarray,
        last_state_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Phân tích màn hình không rõ (UNKNOWN) bằng Multi-modal Gemini Flash Vision.
        """
        if screen is None or getattr(screen, "size", 0) == 0:
            return None

        client = self._get_client()
        if not client:
            return None

        try:
            pil_img = Image.fromarray(cv2.cvtColor(screen, cv2.COLOR_BGR2RGB))
            configured_model = self.rule_manager.ai_config.get("model_name", "gemini-2.5-flash")
            model_name = _normalize_model_name(configured_model)

            prompt = f"""Bạn là hệ thống thị giác AI (Vision AI) giám sát bot game Chaos Zero Nightmare trên giả lập Android (độ phân giải 1600x900).
Trạng thái gần nhất trước đó của bot: '{last_state_name or "CHƯA XÁC ĐỊNH"}'.
Hiện tại màn hình đang bị nhận diện là UNKNOWN (không khớp mẫu quen thuộc).
Hãy nhìn kỹ bức ảnh chụp màn hình thực tế này và phân loại chính xác:

1. "battle_animation": Đang trong trận đấu (hiệu ứng chiêu thức, ánh sáng kỹ năng, nộ, chuyển động nhân vật, không có UI nút bấm tĩnh).
   -> action: "wait"
   -> wait_seconds: 1.5 - 2.5
   -> tap_coord: null
   -> reason: "Hiệu ứng kỹ năng đang chạy, đợi hoạt cảnh kết thúc"

2. "popup": Bảng thông báo, popup quà, bảng xác nhận, nút đóng (X ở góc trên phải), nút Xác nhận / Confirm / OK màu cam, hoặc "Tap to close".
   -> action: "tap"
   -> tap_coord: [x, y] (tọa độ pixel trên khung 1600x900 để đóng hoặc xác nhận)
   -> reason: mô tả nút cần bấm

3. "dialogue": Hội thoại cốt truyện, nhân vật nói chuyện, có nút Skip/Auto góc trên hoặc chạm vào màn hình để qua câu thoại.
   -> action: "tap"
   -> tap_coord: [x, y] (ví dụ [1500, 45] để Skip, hoặc [800, 800] để qua thoại)
   -> reason: mô tả hành động tua thoại

4. "game_menu": Màn hình có nút bấm rõ ràng để đi tiếp (nút Tiếp tục, Chọn, Bắt đầu, Vào màn).
   -> action: "tap"
   -> tap_coord: [x, y]
   -> reason: mô tả nút bấm tiếp theo

5. "critical_error": Mất kết nối mạng, bảo trì máy chủ, bắt buộc nhập captcha, hoặc văng màn hình chính Android.
   -> action: "stop"
   -> tap_coord: null
   -> reason: giải thích sự cố cần người chơi can thiệp

Yêu cầu định dạng đầu ra (BẮT BUỘC CHUỖI JSON HỢP LỆ, KHÔNG THÊM BẤT KỲ VĂN BẢN NGOÀI JSON):
{{
  "screen_type": "battle_animation" | "popup" | "dialogue" | "game_menu" | "critical_error",
  "action": "wait" | "tap" | "stop",
  "tap_coord": [x, y],
  "wait_seconds": 1.5,
  "confidence": 0.0 - 1.0,
  "description": "<mô tả ngắn những gì bạn thấy trên màn hình trong 1 câu>",
  "reason": "<lý do thực hiện hành động này trong 1 câu>"
}}"""

            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, pil_img]
            )

            decision = self._parse_json_response(response.text)
            if decision and "action" in decision:
                logger.info(f"[AIBrain] AI Vision phân tích UNKNOWN thành công: {decision}")
                return decision
        except Exception as e:
            logger.warning(f"[AIBrain] Lỗi khi gọi Gemini Vision phân tích màn hình UNKNOWN: {e}")

        return None

    def detect_state_with_ai(
        self,
        screen: np.ndarray,
        last_state: Optional[State] = None
    ) -> Tuple[State, Dict[str, Any]]:
        client = self._get_client()
        if not client or screen is None or getattr(screen, "size", 0) == 0:
            return State.UNKNOWN, {}

        try:
            h, w = screen.shape[:2]
            if (h, w) != (900, 1600):
                screen = cv2.resize(screen, (1600, 900), interpolation=cv2.INTER_AREA)

            thumb = cv2.resize(screen, (800, 450), interpolation=cv2.INTER_AREA)
            pil_img = Image.fromarray(cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB))

            prompt = """Bạn là AI Vision phân loại màn hình game 'Chaos Zero Nightmare'.
Phân loại màn hình hiện tại thành đúng 1 State duy nhất trong danh sách sau:
- IN_MATCH: Đang trong trận đấu (có vòng tròn lượt đấu / thanh kỹ năng)
- MATCH_DONE: Màn hình kết quả sau trận thường (Victory/Defeat với nút Retry hoặc Next Mission)
- CHAOS_MAP: Bản đồ chọn đảo Chaos (có minimap góc dưới trái và các hòn đảo 3D)
- CHAOS_AFTER_BATTLE: Màn hình kết thúc trận Chaos CÓ NÚT CAM "LEAVE" / "RỜI KHỎI" ở góc dưới phải. KHÔNG ĐƯỢC NHẦM VỚI MÀN HÌNH TRANG BỊ.
- CHAOS_EQUIPMENT: Màn hình nhận hoặc trang bị vật phẩm (Equipment / Gears / Bảng trang bị cho nhân vật, có các ô trang bị, nút "Trang bị" hoặc "Xác nhận"). TUYỆT ĐỐI KHÔNG GỌI LÀ CHAOS_AFTER_BATTLE.
- CHAOS_OBTAIN_REWARD: Màn hình nhận thưởng có nút cam "Obtain" / "Nhận" ở góc dưới phải
- CHAOS_CHOOSE_EPIPHANY: Màn hình chọn Thẻ Khai Sáng (Epiphany) hoặc 3 thẻ bài kỹ năng hoặc lựa chọn sự kiện
- CHAOS_SAFE_ZONE: Khu an toàn / Đốm lửa (lựa chọn Nghỉ ngơi / Hồi máu cho đội hình, có icon lửa trại)
- CHAOS_EVENT: Màn hình sự kiện ngẫu nhiên trong Chaos (Random Event encounter), có khung mô tả sự kiện trên và các thẻ lựa chọn (Event choices) ở dưới.
- PRE_MATCH_MISSION: Màn hình chuẩn bị vào màn (Mission Info có nút Enter)
- PRE_MATCH_TEAM: Màn hình sắp xếp đội hình trước trận (Team Formation)
- STORY_MAP: Bản đồ chương cốt truyện
- STORY_DIALOGUE: Đoạn cắt cảnh hội thoại nhân vật (có nút Skip/Auto)
- POPUP_EFFECT: Bảng popup thông báo, chi tiết, hoặc icon đóng 'X'
- TRANSITIONING: Hoạt cảnh chuyển cảnh, màn hình đen hoặc mờ
- UNKNOWN: Màn hình lạ không khớp các loại trên

Trả về duy nhất JSON:
{
  "state": "TÊN_STATE",
  "confidence": 0.95,
  "description": "Mô tả ngắn",
  "details": {}
}
"""
            model_name = _normalize_model_name(self.rule_manager.ai_config.get("model_name", "gemini-2.5-flash"))
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, pil_img]
            )

            res = self._parse_json_response(response.text)
            if res and "state" in res:
                s_str = str(res["state"]).strip().upper()
                matched_state = State.UNKNOWN
                for s in State:
                    if s.name == s_str or s.value == s_str:
                        matched_state = s
                        break
                if matched_state == State.UNKNOWN:
                    state_map = {
                        "BATTLE": State.IN_MATCH,
                        "FIGHT": State.IN_MATCH,
                        "MAP": State.CHAOS_MAP,
                        "EPIPHANY": State.CHAOS_CHOOSE_EPIPHANY,
                        "CARD_REWARD": State.CHAOS_CHOOSE_EPIPHANY,
                        "LEAVE": State.CHAOS_AFTER_BATTLE,
                        "OBTAIN": State.CHAOS_OBTAIN_REWARD,
                        "EQUIPMENT": State.CHAOS_EQUIPMENT,
                        "GEAR": State.CHAOS_EQUIPMENT,
                        "SAFE_ZONE": State.CHAOS_SAFE_ZONE,
                        "REST": State.CHAOS_SAFE_ZONE,
                        "EVENT": State.CHAOS_EVENT,
                        "CHOICE": State.CHAOS_EVENT,
                        "CHAOS_EVENT": State.CHAOS_EVENT,
                        "VICTORY": State.MATCH_DONE,
                        "RESULT": State.MATCH_DONE,
                        "POPUP": State.POPUP_EFFECT,
                        "DIALOGUE": State.STORY_DIALOGUE,
                        "ANIMATION": State.TRANSITIONING,
                    }
                    matched_state = state_map.get(s_str, State.UNKNOWN)

                details = res.get("details", {})
                if not isinstance(details, dict):
                    details = {}
                details["ai_detected"] = True
                details["confidence"] = float(res.get("confidence", 0.9))
                details["description"] = res.get("description", "")
                return matched_state, details
        except Exception as e:
            logger.warning(f"Lỗi AI Vision detect state: {e}")

        return State.UNKNOWN, {}

    def _heuristic_card_decision(self, cards: List[CardInfo], resources: ResourceInfo) -> Dict[str, Any]:
        if getattr(self, "deck_evaluator", None):
            best_idx, breakdowns = self.deck_evaluator.evaluate_epiphany_choices(cards)
            if breakdowns and 0 <= best_idx < len(breakdowns):
                chosen = breakdowns[best_idx]
                conf = cards[best_idx].confidence if hasattr(cards[best_idx], "confidence") and cards[best_idx].confidence > 0 else 0.85
                return {
                    "action": "choose_card",
                    "target_index": best_idx,
                    "confidence": conf,
                    "score": chosen.total_score,
                    "reason": f"[DeckEvaluator] {chosen.card_title} ({chosen.total_score:.1f}đ): {'; '.join(chosen.reasons)}"
                }
        card_rules = self.rule_manager.card_rules
        priority_list = card_rules.get("priority_list", [])
        weights = card_rules.get("keyword_weights", {})

        best_score = -999.0
        best_idx = 0
        best_reason = "Chọn theo quy tắc mặc định"

        for idx, card in enumerate(cards):
            score = 0.0
            reasons = []

            if card.priority > 0:
                score += float(card.priority)
                desc_label = f" ({card.description_vi})" if card.description_vi else ""
                reasons.append(f"Điểm chuẩn {card.priority}đ [{card.title or card.name}]{desc_label}")

            for p_item in priority_list:
                p_name = p_item.get("card_name", "").lower()
                if p_name and p_name in card.raw_text.lower():
                    pref_var = p_item.get("preferred_variant", "").lower()
                    if pref_var and pref_var in card.raw_text.lower():
                        score += 150.0 - (p_item.get("priority", 1) * 10)
                        reasons.append(f"Khớp thẻ ưu tiên {p_item['card_name']} [{pref_var}]")
                    else:
                        score += 100.0 - (p_item.get("priority", 1) * 10)
                        reasons.append(f"Khớp thẻ ưu tiên {p_item['card_name']}")

            for kw, weight in weights.items():
                if kw.lower() in card.raw_text.lower():
                    score += float(weight)
                    reasons.append(f"+{weight}đ ({kw})")

            if "elasticity" in card.variant.lower():
                score += 50.0
                reasons.append("+50đ biến thể Elasticity")

            if score > best_score:
                best_score = score
                best_idx = idx
                best_reason = "; ".join(reasons) if reasons else f"Thẻ {card.name} điểm cao nhất"

        return {
            "action": "choose_card",
            "target_index": best_idx,
            "confidence": 0.85,
            "reason": f"[Heuristic Engine] {best_reason}"
        }

    def _heuristic_event_decision(self, choices: List[EventChoiceInfo], resources: ResourceInfo) -> Dict[str, Any]:
        event_rules = self.rule_manager.event_rules
        priorities = event_rules.get("priorities", {})
        min_credit = event_rules.get("min_credit_reserve", 100)

        best_idx = 0
        best_score = -999.0
        best_reason = "Chọn sự kiện an toàn nhất"

        for idx, c in enumerate(choices):
            score = 10.0
            reasons = []

            if c.matched_choice:
                score += float(c.priority_score) * 12.0
                if c.recommendation:
                    reasons.append(f"[{c.priority_score}/10đ] {c.recommendation}")
                elif c.outcome_summary:
                    reasons.append(f"[{c.priority_score}/10đ] {c.outcome_summary}")

            if resources.is_low_hp and c.is_heal:
                score += 100.0
                reasons.append("Ưu tiên hồi máu khi HP < 50%")
            elif resources.is_low_hp and c.is_combat:
                score -= 80.0
                reasons.append("Né giao tranh khi HP thấp")

            if not resources.is_low_hp and c.is_combat and priorities.get("fight_boss_for_gear", True):
                score += 60.0
                reasons.append("Máu khỏe: Đánh boss nhận trang bị Rare")

            if c.is_quiz and priorities.get("take_quiz", True):
                score += 45.0
                reasons.append("Tham gia Quiz nhận thưởng an toàn")

            if c.cost_credits > 0:
                if resources.credits < min_credit or priorities.get("avoid_credit_cost", True):
                    score -= 50.0
                    reasons.append(f"Né tốn {c.cost_credits} Credits")

            if score > best_score:
                best_score = score
                best_idx = idx
                best_reason = "; ".join(reasons) if reasons else f"Chọn {c.name}"

        return {
            "action": "choose_event_option",
            "target_index": best_idx,
            "confidence": 0.85,
            "reason": f"[Heuristic Engine] {best_reason}"
        }

    @staticmethod
    def _parse_json_response(raw_text: str) -> Optional[Dict[str, Any]]:
        if not raw_text:
            return None
        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return None
