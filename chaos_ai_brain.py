"""
Cloud AI Brain & Hybrid Logic Engine for Chaos Zero Nightmare ("Não").
Handles:
- Dynamic Prompt Packaging: Injects card_rules.json and event_rules.json into System Prompt
- Real-time Context Packaging: Current HP %, Credits, and OCR extracted card/event choices
- Gemini API communication with strict JSON structured outputs
- Multi-modal Vision Fallback: If OCR is noisy or empty, sends cropped images directly to Gemini Flash Vision
- Offline Heuristic Fallback: Evaluates rules locally if API Key is unset or network drops
"""
import json
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from PIL import Image
import numpy as np
import cv2

from chaos_ai_config import ChaosRuleManager
from chaos_vision import CardInfo, EventChoiceInfo, ResourceInfo

logger = logging.getLogger("ChaosBot.AIBrain")


def _normalize_model_name(model_name: Optional[str]) -> str:
    """Normalize and validate Gemini model name, defaulting to high-speed gemini-3.5-flash."""
    if not model_name:
        return "gemini-3.5-flash"
    m = model_name.strip().lower()
    if "lite" in m:
        return "gemini-3.5-flash-lite"
    if "3.6" in m:
        return "gemini-3.6-flash"
    if "3.5" in m or "latest" in m:
        return "gemini-3.5-flash"
    if "1.5" in m or "2.5" in m or "2.0" in m:
        return "gemini-3.5-flash"
    return model_name.strip()


class ChaosAIBrain:
    """Cloud AI Tactical Decision Engine powered by Google Gemini with Hybrid Fallback."""

    def __init__(self, rule_manager: Optional[ChaosRuleManager] = None):
        self.rule_manager = rule_manager or ChaosRuleManager()
        self._genai_client = None
        self._current_api_key = None

    def _get_client(self, override_key: Optional[str] = None):
        """Instantiate Google GenAI client lazily with sanitized key."""
        raw_key = override_key or self.rule_manager.get_api_key()
        if not raw_key:
            return None
        api_key = raw_key.strip().strip('"\'')
        if not api_key:
            return None

        if self._genai_client is None or self._current_api_key != api_key:
            try:
                from google import genai
                self._genai_client = genai.Client(api_key=api_key)
                self._current_api_key = api_key
                logger.info("Google GenAI client initialized successfully.")
            except Exception as e:
                logger.error(f"Lỗi khởi tạo Google GenAI Client: {e}")
                self._genai_client = None

        return self._genai_client

    def test_connection(self, api_key: Optional[str] = None, model_name: Optional[str] = None) -> Tuple[bool, str]:
        """Kiểm tra kết nối và tính hợp lệ của API Key với model cụ thể."""
        raw_key = api_key or self.rule_manager.get_api_key()
        if not raw_key:
            return False, "Chưa nhập API Key. Vui lòng dán Gemini API Key vào ô nhập."

        clean_key = raw_key.strip().strip('"\'')
        if not clean_key:
            return False, "API Key không hợp lệ (chuỗi trống)."

        configured_model = model_name or self.rule_manager.ai_config.get("model_name", "gemini-3.5-flash")
        target_model = _normalize_model_name(configured_model)

        try:
            client = self._get_client(override_key=clean_key)
            if client is None:
                return False, "Không thể khởi tạo GenAI Client. Vui lòng kiểm tra thư viện google-genai."

            response = client.models.generate_content(
                model=target_model,
                contents="Hello, reply with JSON: {\"status\": \"ok\", \"message\": \"connected\"}"
            )
            if response and response.text:
                logger.info(f"Test connection response ({target_model}): {response.text}")
                return True, f"Kết nối Gemini API thành công! (Model: {target_model})"
            return False, "Không nhận được phản hồi từ Gemini API."
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Lỗi test kết nối Gemini API ({target_model}): {err_msg}")
            if "404" in err_msg or "not found" in err_msg.lower():
                return False, f"Model '{target_model}' không tồn tại hoặc chưa được hỗ trợ. Đề xuất dùng 'gemini-1.5-flash'. (Chi tiết: {err_msg})"
            if "API_KEY_INVALID" in err_msg or "400" in err_msg or "key not valid" in err_msg.lower():
                return False, f"API Key không hợp lệ hoặc đã bị vô hiệu hóa. Vui lòng kiểm tra lại trên Google AI Studio. (Chi tiết: {err_msg})"
            return False, f"Lỗi kết nối Gemini API: {err_msg}"

    # ── 3.1. Đóng gói Prompt Động (Dynamic Prompting) ───────────────

    def _build_system_prompt(self) -> str:
        """Nhúng card_rules.json và event_rules.json vào System Prompt."""
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
  "target_index": <int 0, 1, 2...>,
  "confidence": <float 0.0 - 1.0>,
  "reason": "<giải thích ngắn gọn và súc tích trong 1 câu bằng tiếng Việt>"
}}
"""
        return prompt

    # ── 3.2. Quyết định Thẻ Bài (Card Selection) ────────────────────

    def decide_card(self, cards: List[CardInfo], resources: ResourceInfo) -> Dict[str, Any]:
        """
        Quyết định chọn lá bài tối ưu từ danh sách CardInfo.
        Hỗ trợ Cloud AI và Multi-modal Vision Fallback khi OCR trống.
        """
        if not cards:
            return {"action": "choose_card", "target_index": 1, "confidence": 0.5, "reason": "Không có dữ liệu thẻ, chọn mặc định thẻ giữa"}

        # Kiểm tra xem có cần kích hoạt Multi-modal Fallback không (OCR quá ngắn hoặc rỗng)
        total_text_len = sum(len(c.raw_text.strip()) for c in cards)
        use_vision = total_text_len < 15 and any(c.image is not None for c in cards)

        client = self._get_client()
        if client:
            try:
                system_prompt = self._build_system_prompt()
                user_prompt = f"""=== TRẠNG THÁI HIỆN TẠI ===
- Máu đội (Team HP): {int(resources.hp_percent * 100)}% {'(Nguy cấp!)' if resources.is_low_hp else '(An toàn)'}
- Credits hiện có: {resources.credits}

=== CÁC LỰA CHỌN THẺ BÀI ===
"""
                for c in cards:
                    user_prompt += f"- Vị trí {c.slot} ({c.name}):\n"
                    user_prompt += f"  + Tiêu đề: {c.title or 'Chưa rõ'}\n"
                    user_prompt += f"  + Biến thể nhận diện: {c.variant}\n"
                    if c.character:
                        user_prompt += f"  + Nhân vật sở hữu: {c.character}\n"
                    if c.priority > 0:
                        user_prompt += f"  + Điểm ưu tiên chuẩn (templates): {c.priority}/100\n"
                    if c.description_vi:
                        user_prompt += f"  + Mô tả chi tiết (VI): {c.description_vi}\n"
                    user_prompt += f"  + Từ khóa: {', '.join(c.keywords) if c.keywords else 'Không'}\n"
                    user_prompt += f"  + Nội dung mô tả OCR: {c.raw_text}\n"

                user_prompt += "\nHãy chọn lá bài tốt nhất phù hợp với bộ quy tắc và trạng thái hiện tại."

                contents: List[Any] = [system_prompt, user_prompt]

                # Nếu kích hoạt Multi-modal Fallback: đính kèm trực tiếp ảnh các lá bài
                if use_vision:
                    logger.info("[AIBrain] Kích hoạt Multi-modal Vision Fallback cho Thẻ Bài do OCR bị thiếu.")
                    for c in cards:
                        if c.image is not None:
                            pil_img = Image.fromarray(cv2.cvtColor(c.image, cv2.COLOR_BGR2RGB))
                            contents.append(f"Hình ảnh thực tế của {c.name}:")
                            contents.append(pil_img)

                model_name = _normalize_model_name(self.rule_manager.ai_config.get("model_name", "gemini-3.5-flash"))
                from google.genai import types
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )

                decision = self._parse_json_response(response.text)
                if decision:
                    logger.info(f"[AIBrain] Quyết định chọn thẻ: {decision}")
                    return decision
            except Exception as e:
                logger.warning(f"[AIBrain] Lỗi gọi Gemini API: {e}. Chuyển sang Heuristic Fallback.")

        # Fallback Heuristic cục bộ nếu không gọi được API
        return self._heuristic_card_decision(cards, resources)

    # ── 3.2. Quyết định Lựa chọn Sự Kiện (Event Decision) ────────────

    def decide_event(self, choices: List[EventChoiceInfo], resources: ResourceInfo) -> Dict[str, Any]:
        """
        Quyết định chọn phương án sự kiện tối ưu từ danh sách EventChoiceInfo.
        Hỗ trợ Multi-modal Vision Fallback khi OCR trống/lộn xộn.
        """
        if not choices:
            return {"action": "choose_event_option", "target_index": 0, "confidence": 0.5, "reason": "Không có lựa chọn sự kiện, chọn phương án 1"}

        total_text_len = sum(len(c.text.strip()) for c in choices)
        use_vision = total_text_len < 15 and any(c.image is not None for c in choices)

        client = self._get_client()
        if client:
            try:
                system_prompt = self._build_system_prompt()
                user_prompt = f"""=== TRẠNG THÁI HIỆN TẠI ===
- Máu đội (Team HP): {int(resources.hp_percent * 100)}% {'(Nguy cấp!)' if resources.is_low_hp else '(An toàn)'}
- Credits hiện có: {resources.credits}

=== CÁC LỰA CHỌN SỰ KIỆN ===
"""
                for c in choices:
                    user_prompt += f"- Lựa chọn {c.slot} ({c.name}):\n"
                    user_prompt += f"  + Nội dung: {c.text}\n"
                    if c.matched_event_name:
                        user_prompt += f"  + Sự kiện khớp (templates): {c.matched_event_name}\n"
                    if c.priority_score > 0:
                        user_prompt += f"  + Điểm khuyến nghị (templates): {c.priority_score}/10\n"
                    if c.outcome_summary:
                        user_prompt += f"  + Kết quả dự kiến (templates): {c.outcome_summary}\n"
                    if c.recommendation:
                        user_prompt += f"  + Lời khuyên chiến thuật (templates): {c.recommendation}\n"
                    user_prompt += f"  + Đặc điểm: {', '.join(c.keywords) if c.keywords else 'Bình thường'}\n"
                    if c.cost_credits > 0:
                        user_prompt += f"  + Chi phí Credits: {c.cost_credits}\n"

                user_prompt += "\nHãy chọn phương án sự kiện tối ưu nhất theo quy tắc sự kiện."

                contents: List[Any] = [system_prompt, user_prompt]

                if use_vision:
                    logger.info("[AIBrain] Kích hoạt Multi-modal Vision Fallback cho Sự Kiện do OCR bị thiếu.")
                    for c in choices:
                        if c.image is not None:
                            pil_img = Image.fromarray(cv2.cvtColor(c.image, cv2.COLOR_BGR2RGB))
                            contents.append(f"Hình ảnh của {c.name}:")
                            contents.append(pil_img)

                model_name = _normalize_model_name(self.rule_manager.ai_config.get("model_name", "gemini-3.5-flash"))
                from google.genai import types
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )

                decision = self._parse_json_response(response.text)
                if decision:
                    logger.info(f"[AIBrain] Quyết định sự kiện: {decision}")
                    return decision
            except Exception as e:
                logger.warning(f"[AIBrain] Lỗi gọi Gemini API cho sự kiện: {e}. Chuyển sang Heuristic Fallback.")

        # Fallback Heuristic cục bộ
        return self._heuristic_event_decision(choices, resources)

    # ── 3.3. Quyết định Chọn Hòn Đảo / Lộ Trình (Map Island Decision) ───

    def decide_island(
        self,
        evaluations: Dict[Any, Any],
        resources: ResourceInfo,
        fallback_island: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Quyết định chọn hòn đảo tối ưu (Top, Middle, Bottom) từ kết quả đánh giá nhánh đường.
        Hỗ trợ phân tích chiến thuật bằng Gemini Cloud AI và Heuristic Pathfinder.
        """
        if not evaluations:
            choice_str = fallback_island.value if hasattr(fallback_island, "value") else (str(fallback_island) if fallback_island else "middle")
            return {
                "action": "choose_island",
                "target_island": choice_str,
                "confidence": 0.5,
                "reason": "Không có thông tin nhánh đường, chọn đảo mặc định."
            }

        client = self._get_client()
        if client:
            try:
                system_prompt = self._build_system_prompt()
                user_prompt = f"""=== TRẠNG THÁI HIỆN TẠI ===
- Máu đội (Team HP): {int(resources.hp_percent * 100)}% {'(Nguy cấp!)' if resources.is_low_hp else '(An toàn)'}
- Credits hiện có: {resources.credits}

=== CÁC HÒN ĐẢO / NHÁNH ĐƯỜNG KHẢ DỤNG ===
"""
                for isl, ev in evaluations.items():
                    isl_name = isl.value.upper() if hasattr(isl, "value") else str(isl)
                    if ev.is_available and ev.best_path:
                        path_nodes = " -> ".join([getattr(n.node_type, "value", str(n.node_type)) for n in ev.best_path.nodes]) if hasattr(ev.best_path, "nodes") else ""
                        user_prompt += f"- Đảo {isl_name}:\n"
                        user_prompt += f"  + Điểm đánh giá thuật toán: {ev.best_score:.1f}\n"
                        user_prompt += f"  + Độ dài đường đi: {ev.best_path.length} bước\n"
                        if path_nodes:
                            user_prompt += f"  + Chuỗi các node: {path_nodes}\n"
                    else:
                        user_prompt += f"- Đảo {isl_name}: Bị loại ({ev.rejection_reason or 'Không có đường tới Boss'})\n"

                user_prompt += "\nHãy chọn hòn đảo tối ưu nhất (top, middle, hoặc bottom). Trả về JSON: {\"action\": \"choose_island\", \"target_island\": \"top\"|\"middle\"|\"bottom\", \"confidence\": 0.9, \"reason\": \"<1 câu tiếng Việt ngắn gọn giải thích lý do>\"}"

                model_name = _normalize_model_name(self.rule_manager.ai_config.get("model_name", "gemini-3.5-flash"))
                from google.genai import types
                response = client.models.generate_content(
                    model=model_name,
                    contents=[system_prompt, user_prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )

                decision = self._parse_json_response(response.text)
                if decision and "target_island" in decision:
                    logger.info(f"[AIBrain] AI quyết định chọn đảo: {decision}")
                    return decision
            except Exception as e:
                logger.warning(f"[AIBrain] Lỗi gọi Gemini API cho bản đồ: {e}. Dùng thuật toán Heuristic Pathfinder.")

        # Heuristic fallback dựa trên điểm cao nhất từ pathfinder
        valid = [ev for ev in evaluations.values() if ev.is_available and ev.best_path]
        if valid:
            island_priority = {"top": 3, "middle": 2, "bottom": 1}
            best_ev = max(
                valid,
                key=lambda ev: (
                    ev.best_score,
                    -ev.best_path.length,
                    island_priority.get(ev.island.value if hasattr(ev.island, "value") else str(ev.island), 0)
                )
            )
            isl_str = best_ev.island.value if hasattr(best_ev.island, "value") else str(best_ev.island)
            reason = f"Đường đi tối ưu tới Boss (Điểm: {best_ev.best_score:.1f}, {best_ev.best_path.length} bước)"
            if resources.is_low_hp:
                reason += " - Ưu tiên an toàn/hồi máu khi HP thấp"
            else:
                reason += " - Ưu tiên săn quái/tinh anh tích lũy tài nguyên"
            return {
                "action": "choose_island",
                "target_island": isl_str,
                "confidence": 0.90,
                "reason": f"[Pathfinder] {reason}"
            }

        fallback_str = fallback_island.value if hasattr(fallback_island, "value") else (str(fallback_island) if fallback_island else "middle")
        return {
            "action": "choose_island",
            "target_island": fallback_str,
            "confidence": 0.50,
            "reason": "Chọn đảo dự phòng khả dụng"
        }

    # ── Heuristic Fallback Engines (Cục bộ khi mất mạng/hết quota) ─

    def _heuristic_card_decision(self, cards: List[CardInfo], resources: ResourceInfo) -> Dict[str, Any]:
        """Đánh giá điểm số cục bộ theo cơ sở dữ liệu templates/card_rules.json và trọng số từ khóa."""
        logger.info("[AIBrain] Sử dụng Heuristic Rule Engine cục bộ cho Thẻ Bài.")
        card_rules = self.rule_manager.card_rules
        priority_list = card_rules.get("priority_list", [])
        weights = card_rules.get("keyword_weights", {})

        best_score = -999.0
        best_idx = 0
        best_reason = "Chọn theo quy tắc mặc định"

        for idx, card in enumerate(cards):
            score = 0.0
            reasons = []

            # 0. Điểm chuẩn từ cơ sở dữ liệu templates/card_rules.json (0-100)
            if card.priority > 0:
                score += float(card.priority)
                desc_label = f" ({card.description_vi})" if card.description_vi else ""
                reasons.append(f"Điểm chuẩn {card.priority}đ [{card.title or card.name}]{desc_label}")

            # 1. So khớp với priority_list người dùng cấu hình
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

            # 2. Cộng điểm từ khóa
            for kw, weight in weights.items():
                if kw.lower() in card.raw_text.lower():
                    score += float(weight)
                    reasons.append(f"+{weight}đ ({kw})")

            # 3. Ưu tiên biến thể Elasticity
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
        """Đánh giá lựa chọn sự kiện cục bộ theo cơ sở dữ liệu templates/event_rules.json và quy tắc sự kiện."""
        logger.info("[AIBrain] Sử dụng Heuristic Rule Engine cục bộ cho Sự Kiện.")
        event_rules = self.rule_manager.event_rules
        priorities = event_rules.get("priorities", {})
        min_credit = event_rules.get("min_credit_reserve", 100)

        best_idx = 0
        best_score = -999.0
        best_reason = "Chọn sự kiện an toàn nhất"

        for idx, c in enumerate(choices):
            score = 10.0
            reasons = []

            # 0. Điểm khuyến nghị chuẩn từ cơ sở dữ liệu templates/event_rules.json (1-10)
            if c.matched_choice:
                score += float(c.priority_score) * 12.0
                if c.recommendation:
                    reasons.append(f"[{c.priority_score}/10đ] {c.recommendation}")
                elif c.outcome_summary:
                    reasons.append(f"[{c.priority_score}/10đ] {c.outcome_summary}")

            # Nếu máu thấp, ưu tiên hồi máu
            if resources.is_low_hp and c.is_heal:
                score += 100.0
                reasons.append("Ưu tiên hồi máu khi HP < 50%")
            elif resources.is_low_hp and c.is_combat:
                score -= 80.0
                reasons.append("Né giao tranh khi HP thấp")

            # Nếu máu khỏe, ưu tiên đánh Boss nhận đồ
            if not resources.is_low_hp and c.is_combat and priorities.get("fight_boss_for_gear", True):
                score += 60.0
                reasons.append("Máu khỏe: Đánh boss nhận trang bị Rare")

            # Tham gia Quiz an toàn
            if c.is_quiz and priorities.get("take_quiz", True):
                score += 45.0
                reasons.append("Tham gia Quiz nhận thưởng an toàn")

            # Né tốn credits
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
        """Làm sạch và parse chuỗi JSON từ phản hồi của mô hình LLM."""
        if not raw_text:
            return None
        clean = raw_text.strip()
        # Loại bỏ code block markdown ```json ... ```
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE)

        try:
            return json.loads(clean)
        except Exception:
            # Tìm block JSON {...} đầu tiên
            match = re.search(r"\{.*?\}", clean, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return None
