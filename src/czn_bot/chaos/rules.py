"""
Rule Manager for AI and Heuristic Chaos Mode.
Loads and indexes card_rules.json, event_rules.json, and equipment_rules.json.
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

from czn_bot.constants import (
    DATA_RULES_DIR,
    DATA_TEMPLATES_DIR,
    LEGACY_TEMPLATES_DIR,
    PROJECT_ROOT,
)
from czn_bot.settings import get_gemini_api_key, load_ai_config, save_ai_config

logger = logging.getLogger("ChaosBot.ChaosRules")

DEFAULT_CARD_RULES: Dict[str, Any] = {
    "version": "1.0",
    "description": "Bảng quy tắc ưu tiên lựa chọn thẻ bài Chaos",
    "priority_list": [
        {"card_name": "Amp Therapy", "preferred_variant": "Elasticity", "priority": 1},
        {"card_name": "Focus", "preferred_variant": "", "priority": 2},
        {"card_name": "Passion", "preferred_variant": "", "priority": 3},
        {"card_name": "Possession", "preferred_variant": "", "priority": 4},
        {"card_name": "Mute Accent", "preferred_variant": "Skill", "priority": 5},
    ],
    "keyword_weights": {
        "Elasticity": 60,
        "Extra Attack": 35,
        "Action Point": 40,
        "Morale": 25,
        "Rare": 30,
        "Heal": 45,
        "Discard": 15,
        "Base": 5,
    },
    "default_pick_index": 1,
}

DEFAULT_EVENT_RULES: Dict[str, Any] = {
    "version": "1.0",
    "description": "Bảng quy tắc ưu tiên xử lý sự kiện ngẫu nhiên trong Chaos",
    "priorities": {
        "fight_boss_for_gear": True,
        "take_quiz": True,
        "avoid_credit_cost": True,
        "heal_if_low_hp": True,
    },
    "min_credit_reserve": 100,
    "hp_critical_threshold": 0.50,
}




def _find_rule_file(filename: str) -> Optional[str]:
    """Find rule file searching data/rules, data/templates, templates, and project root."""
    search_paths = [
        os.path.join(DATA_RULES_DIR, filename),
        os.path.join(DATA_TEMPLATES_DIR, filename),
        os.path.join(LEGACY_TEMPLATES_DIR, filename),
        os.path.join(PROJECT_ROOT, filename),
    ]
    for p in search_paths:
        if os.path.isfile(p):
            return p
    return None


class ChaosRuleManager:
    """Manages loading, indexing, and querying game rules and AI configurations."""

    def __init__(self):
        self.cards: List[Dict[str, Any]] = []
        self.cards_by_name: Dict[str, List[Dict[str, Any]]] = {}
        self.cards_by_id: Dict[str, Dict[str, Any]] = {}
        self.cards_by_template: Dict[str, Dict[str, Any]] = {}

        self.events_database: List[Dict[str, Any]] = []
        self.events_by_name: Dict[str, Dict[str, Any]] = {}
        self.event_choices_index: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []

        self.equipments: List[Dict[str, Any]] = []
        self.equipments_by_name: Dict[str, Dict[str, Any]] = {}
        self.equipments_by_filename: Dict[str, Dict[str, Any]] = {}

        self.card_rules = self.load_card_rules()
        self.event_rules = self.load_event_rules()
        self.equipment_rules = self.load_equipment_rules()
        self.ai_config = self.load_ai_config()

    def load_ai_config(self) -> Dict[str, Any]:
        return load_ai_config()

    def get_api_key(self) -> str:
        return get_gemini_api_key()

    def save_ai_api_key(self, plain_key: str) -> bool:
        """Save API key in ai_config.json without homemade encryption."""
        cfg = self.load_ai_config()
        cfg["api_key"] = plain_key.strip()
        self.ai_config = cfg
        return save_ai_config(cfg)

    def save_ai_config(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        enable_multimodal: bool = True,
        **kwargs
    ) -> bool:
        """Save AI settings in ai_config.json cleanly."""
        cfg = self.load_ai_config()
        if api_key is not None:
            clean_key = api_key.strip().strip('"\'')
            cfg["api_key"] = clean_key
            os.environ["GEMINI_API_KEY"] = clean_key
        if model_name is not None:
            clean_model = model_name.strip()
            if not clean_model:
                clean_model = "gemini-2.5-flash"
            cfg["model_name"] = clean_model
            os.environ["GEMINI_MODEL"] = clean_model
        cfg["enable_multimodal_fallback"] = enable_multimodal
        for k, v in kwargs.items():
            cfg[k] = v
        self.ai_config = cfg
        return save_ai_config(cfg)

    def save_card_rules(self, rules: Dict[str, Any]) -> bool:
        """Export card rules to data/rules/card_rules.json."""
        try:
            if "cards" not in rules and self.cards:
                self.card_rules["priority_list"] = rules.get("priority_list", self.card_rules.get("priority_list", []))
                self.card_rules["keyword_weights"] = rules.get("keyword_weights", self.card_rules.get("keyword_weights", {}))
            else:
                self.card_rules = rules
            self._build_card_indexes(self.card_rules)
            target_path = os.path.join(DATA_RULES_DIR, "card_rules.json")
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(self.card_rules, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save card rules: {e}")
            return False

    def save_event_rules(self, rules: Dict[str, Any]) -> bool:
        """Export event rules to data/rules/event_rules.json."""
        try:
            if "events_database" not in rules and self.events_database:
                for k in ["priorities", "min_credit_reserve", "hp_critical_threshold", "strategy_notes"]:
                    if k in rules:
                        self.event_rules[k] = rules[k]
            else:
                self.event_rules = rules
            self._build_event_indexes(self.event_rules)
            target_path = os.path.join(DATA_RULES_DIR, "event_rules.json")
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(self.event_rules, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save event rules: {e}")
            return False

    def save_all_rules(
        self,
        card_rules: Dict[str, Any],
        event_rules: Dict[str, Any],
        api_key: str = "",
        model_name: str = "offline"
    ) -> bool:
        """Save rules cleanly."""
        ok1 = self.save_card_rules(card_rules)
        ok2 = self.save_event_rules(event_rules)
        if api_key:
            self.save_ai_config(api_key=api_key, model_name=model_name)
        return ok1 and ok2

    def _build_card_indexes(self, rules: Dict[str, Any]) -> None:
        self.cards = rules.get("cards", [])
        self.cards_by_name.clear()
        self.cards_by_id.clear()
        self.cards_by_template.clear()

        for card in self.cards:
            cid = card.get("id", "")
            if cid:
                self.cards_by_id[cid] = card

            name = card.get("name", "").strip()
            if name:
                name_lower = name.lower()
                if name_lower not in self.cards_by_name:
                    self.cards_by_name[name_lower] = []
                self.cards_by_name[name_lower].append(card)

            tpl = card.get("template_path", "")
            if tpl:
                self.cards_by_template[tpl] = card
                fname = os.path.basename(tpl)
                self.cards_by_template[fname] = card

    def _build_event_indexes(self, rules: Dict[str, Any]) -> None:
        self.events_database = rules.get("events_database", [])
        self.events_by_name.clear()
        self.event_choices_index.clear()

        for ev in self.events_database:
            ename = ev.get("event_name", "").strip()
            if ename:
                self.events_by_name[ename.lower()] = ev

            for ch in ev.get("choices", []):
                ctext = ch.get("choice_text", "").strip()
                if ctext:
                    self.event_choices_index.append((ctext.lower(), ch, ev))

    def _build_equipment_indexes(self, rules: Dict[str, Any]) -> None:
        self.equipments = rules.get("equipments", [])
        self.equipments_by_name.clear()
        self.equipments_by_filename.clear()

        for eq in self.equipments:
            name = eq.get("name", "").strip()
            if name:
                self.equipments_by_name[name.lower()] = eq
            fname = eq.get("filename", "").strip()
            if fname:
                self.equipments_by_filename[fname.lower()] = eq
            tpl = eq.get("template_path", "").strip()
            if tpl:
                base_name = os.path.basename(tpl).lower()
                self.equipments_by_filename[base_name] = eq

    def load_equipment_rules(self) -> Dict[str, Any]:
        p = _find_rule_file("equipment_rules.json")
        rules: Dict[str, Any] = {}
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                    logger.info(f"Đã nạp {len(rules.get('equipments', []))} trang bị từ {p}")
            except Exception as e:
                logger.warning(f"Lỗi nạp equipment_rules: {e}")

        self._build_equipment_indexes(rules)
        return rules

    def load_card_rules(self) -> Dict[str, Any]:
        p = _find_rule_file("card_rules.json")
        rules: Dict[str, Any] = {}
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                    logger.info(f"Đã nạp {len(rules.get('cards', []))} thẻ bài từ {p}")
            except Exception as e:
                logger.warning(f"Lỗi nạp card_rules: {e}")

        for k, v in DEFAULT_CARD_RULES.items():
            if k not in rules:
                rules[k] = v

        self._build_card_indexes(rules)
        return rules

    def load_event_rules(self) -> Dict[str, Any]:
        p = _find_rule_file("event_rules.json")
        rules: Dict[str, Any] = {}
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                    logger.info(f"Đã nạp {len(rules.get('events_database', []))} sự kiện từ {p}")
            except Exception as e:
                logger.warning(f"Lỗi nạp event_rules: {e}")

        for k, v in DEFAULT_EVENT_RULES.items():
            if k not in rules:
                rules[k] = v

        self._build_event_indexes(rules)
        return rules

    def match_card(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Match OCR text or title against all 403 cards in the database.
        Returns the best matching card dictionary or None.
        """
        import re
        if not text:
            return None
        text_lower = text.lower().strip()
        text_norm = " ".join(re.sub(r"[^\w\s%]", " ", text_lower).split())
        text_words = set(text_norm.split())

        for name_lower, variants in self.cards_by_name.items():
            if name_lower in text_lower or name_lower in text_norm:
                if len(variants) == 1:
                    return variants[0]

                def _score_variant(v: Dict[str, Any]) -> float:
                    score = 0.0
                    v_name = v.get("variant", "").lower()
                    v_name_norm = " ".join(re.sub(r"[^\w\s%]", " ", v_name).split())
                    if v_name_norm and (v_name_norm in text_norm or v_name in text_lower):
                        score += 50.0

                    desc = v.get("description", "").lower()
                    desc_words = re.sub(r"[^\w\s%]", " ", desc).split()
                    for token in desc_words:
                        if len(token) >= 2 and token in text_words:
                            score += 10.0
                    return score

                return max(variants, key=_score_variant)

        return None

    def match_event_choice(self, text: str) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Match OCR text from an event choice button against events_database."""
        if not text:
            return None
        text_lower = text.lower().strip()

        best_match = None
        best_score = 0
        for ctext_lower, ch, ev in self.event_choices_index:
            if ctext_lower in text_lower or text_lower in ctext_lower:
                match_len = min(len(ctext_lower), len(text_lower))
                if match_len > best_score and match_len >= 4:
                    best_score = match_len
                    best_match = (ch, ev)

        return best_match

    def match_event_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Match event name from title."""
        if not title:
            return None
        t_lower = title.lower().strip()
        for ename_lower, ev in self.events_by_name.items():
            if ename_lower in t_lower or t_lower in ename_lower:
                return ev
        return None

    def match_equipment(self, query: str) -> Optional[Dict[str, Any]]:
        """Match OCR text, slug, or filename against equipment database."""
        if not query:
            return None
        q_lower = query.lower().strip()

        for name_lower, eq in self.equipments_by_name.items():
            if name_lower in q_lower or q_lower in name_lower:
                return eq

        for fname_lower, eq in self.equipments_by_filename.items():
            base = fname_lower.replace(".webp", "").replace(".png", "")
            if base in q_lower or q_lower in base:
                return eq

        return None

    def query_equipment(self, query: str) -> Optional[Dict[str, Any]]:
        q = query.strip().lower()
        if q in self.equipments_by_name:
            return self.equipments_by_name[q]
        if q in self.equipments_by_filename:
            return self.equipments_by_filename[q]
        for name, eq in self.equipments_by_name.items():
            if q in name or name in q:
                return eq
        return None

    def query_card(self, name_or_keyword: str) -> List[Dict[str, Any]]:
        k = name_or_keyword.strip().lower()
        if k in self.cards_by_name:
            return self.cards_by_name[k]
        results = []
        for name, cards in self.cards_by_name.items():
            if k in name:
                results.extend(cards)
        return results

    def query_event(self, text: str) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
        t = text.strip().lower()
        if t in self.events_by_name:
            ev = self.events_by_name[t]
            choices = ev.get("choices", [])
            first_ch = choices[0] if choices else {}
            return first_ch, ev

        for ctext_lower, ch, ev in self.event_choices_index:
            if ctext_lower in t or t in ctext_lower:
                return ch, ev
        return None
