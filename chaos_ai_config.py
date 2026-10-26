"""
Configuration and Rule Manager for AI-Driven Chaos Mode.
Handles:
- Loading & saving card_rules.json (card variant priorities & keyword weights)
- Loading & saving event_rules.json (event strategies: boss, quiz, credits, healing)
- Loading & saving ai_config.json (encrypted/obfuscated local storage for Gemini API key)
"""
import os
import re
import json
import base64
import logging
from typing import Dict, Any, List

logger = logging.getLogger("ChaosBot.AIConfig")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARD_RULES_PATH = os.path.join(BASE_DIR, "card_rules.json")
EVENT_RULES_PATH = os.path.join(BASE_DIR, "event_rules.json")
CARD_RULES_TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "card_rules.json")
EVENT_RULES_TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "event_rules.json")
AI_CONFIG_PATH = os.path.join(BASE_DIR, "ai_config.json")

# Salt key for local obfuscation
_OBFUSCATION_SALT = b"ChaosZeroNightmareAI2026"


def _encrypt_key(plain_key: str) -> str:
    """Obfuscate API Key before saving locally."""
    if not plain_key:
        return ""
    data = plain_key.encode("utf-8")
    xor_bytes = bytes([b ^ _OBFUSCATION_SALT[i % len(_OBFUSCATION_SALT)] for i, b in enumerate(data)])
    return base64.b64encode(xor_bytes).decode("ascii")


def _decrypt_key(cipher_text: str) -> str:
    """De-obfuscate API Key loaded from disk."""
    if not cipher_text:
        return ""
    try:
        raw_bytes = base64.b64decode(cipher_text.encode("ascii"))
        plain_bytes = bytes([b ^ _OBFUSCATION_SALT[i % len(_OBFUSCATION_SALT)] for i, b in enumerate(raw_bytes)])
        return plain_bytes.decode("utf-8", errors="ignore")
    except Exception:
        # Fallback if key was stored in plain text
        return cipher_text


DEFAULT_CARD_RULES: Dict[str, Any] = {
    "version": "1.0",
    "description": "Bảng quy tắc ưu tiên lựa chọn thẻ bài Chaos",
    "priority_list": [
        {
            "card_name": "Amp Therapy",
            "preferred_variant": "Elasticity",
            "priority": 1,
            "notes": "Ưu tiên tuyệt đối biến thể Elasticity thay vì Base"
        },
        {
            "card_name": "Focus",
            "preferred_variant": "",
            "priority": 2,
            "notes": "Hồi 1 Action Point khi máu dưới 50%"
        },
        {
            "card_name": "Passion",
            "preferred_variant": "",
            "priority": 3,
            "notes": "Tăng Hit count cho các thẻ cơ bản"
        },
        {
            "card_name": "Possession",
            "preferred_variant": "",
            "priority": 4,
            "notes": "Giảm Cost ngẫu nhiên cho thẻ trên tay"
        },
        {
            "card_name": "Mute Accent",
            "preferred_variant": "Skill",
            "priority": 5,
            "notes": "Gây 250% Extra Attack và kích hoạt Morale"
        }
    ],
    "keyword_weights": {
        "Elasticity": 60,
        "Extra Attack": 35,
        "Action Point": 40,
        "Morale": 25,
        "Rare": 30,
        "Heal": 45,
        "Discard": 15,
        "Base": 5
    },
    "default_pick_index": 1
}

DEFAULT_EVENT_RULES: Dict[str, Any] = {
    "version": "1.0",
    "description": "Bảng quy tắc ưu tiên xử lý sự kiện ngẫu nhiên trong Chaos",
    "priorities": {
        "fight_boss_for_gear": True,
        "take_quiz": True,
        "avoid_credit_cost": True,
        "heal_if_low_hp": True
    },
    "min_credit_reserve": 100,
    "hp_critical_threshold": 0.50,
    "strategy_notes": "1. Khi HP < 50%: Ưu tiên hồi máu, né đánh boss nguy hiểm.\n2. Khi HP >= 50%: Ưu tiên giao tranh Boss để nhận trang bị hiếm (Rare).\n3. Tham gia Quiz/Câu đố nhận thưởng miễn phí.\n4. Tránh các lựa chọn tiêu tốn Credits nếu Credits hiện có < 100."
}

DEFAULT_AI_CONFIG: Dict[str, Any] = {
    "provider": "gemini",
    "api_key_encrypted": "",
    "model_name": "gemini-2.5-flash",
    "enable_multimodal_fallback": True,
    "temperature": 0.1,
    "max_tokens": 512
}


class ChaosRuleManager:
    """
    Manages loading, updating, indexing, and querying rule files.
    Seamlessly integrates:
    - Master card database (403 cards) in templates/card_rules.json
    - Master event database (141 events) in templates/event_rules.json
    - User customization overrides in root card_rules.json & event_rules.json
    """

    def __init__(self):
        self.cards: List[Dict[str, Any]] = []
        self.cards_by_name: Dict[str, List[Dict[str, Any]]] = {}
        self.cards_by_id: Dict[str, Dict[str, Any]] = {}
        self.cards_by_template: Dict[str, Dict[str, Any]] = {}
        self.events_database: List[Dict[str, Any]] = []
        self.events_by_name: Dict[str, Dict[str, Any]] = {}
        self.event_choices_index: List[tuple] = []

        self.card_rules = self.load_card_rules()
        self.event_rules = self.load_event_rules()
        self.ai_config = self.load_ai_config()

    def _build_card_indexes(self, rules: Dict[str, Any]):
        """Build fast in-memory lookup indexes for cards."""
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

    def _build_event_indexes(self, rules: Dict[str, Any]):
        """Build fast in-memory lookup indexes for events and choices."""
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

    def load_card_rules(self) -> Dict[str, Any]:
        """
        Load card rules prioritizing templates/card_rules.json (403 cards)
        and merging user customized priority list / keyword weights from root card_rules.json.
        """
        rules: Dict[str, Any] = {}

        # 1. Load comprehensive card database from templates/card_rules.json if present
        if os.path.exists(CARD_RULES_TEMPLATE_PATH):
            try:
                with open(CARD_RULES_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                    logger.info(f"Đã nạp {len(rules.get('cards', []))} thẻ bài từ {CARD_RULES_TEMPLATE_PATH}")
            except Exception as e:
                logger.warning(f"Không thể đọc {CARD_RULES_TEMPLATE_PATH}: {e}")

        # 2. Load user customized overrides from root card_rules.json if present
        user_overrides = {}
        if os.path.exists(CARD_RULES_PATH):
            try:
                with open(CARD_RULES_PATH, "r", encoding="utf-8") as f:
                    user_overrides = json.load(f)
            except Exception as e:
                logger.warning(f"Không thể đọc {CARD_RULES_PATH}: {e}")

        if not rules and not user_overrides:
            rules = DEFAULT_CARD_RULES.copy()
        elif not rules and user_overrides:
            rules = user_overrides
        else:
            # Merge user_overrides into template database
            if "priority_list" in user_overrides:
                rules["priority_list"] = user_overrides["priority_list"]
            if "keyword_weights" in user_overrides:
                rules["keyword_weights"] = user_overrides["keyword_weights"]

        # Ensure priority_list and keyword_weights always exist
        if "priority_list" not in rules:
            rules["priority_list"] = DEFAULT_CARD_RULES["priority_list"].copy()
        if "keyword_weights" not in rules:
            rules["keyword_weights"] = DEFAULT_CARD_RULES["keyword_weights"].copy()

        self._build_card_indexes(rules)
        return rules

    def save_card_rules(self, rules: Dict[str, Any]) -> bool:
        """Export card_rules.json to disk (root) while preserving in-memory indexes."""
        try:
            # Keep templates cards if not included in the payload
            if "cards" not in rules and self.cards:
                self.card_rules["priority_list"] = rules.get("priority_list", self.card_rules.get("priority_list", []))
                self.card_rules["keyword_weights"] = rules.get("keyword_weights", self.card_rules.get("keyword_weights", {}))
            else:
                self.card_rules = rules

            self._build_card_indexes(self.card_rules)
            with open(CARD_RULES_PATH, "w", encoding="utf-8") as f:
                json.dump(rules, f, ensure_ascii=False, indent=2)
            logger.info(f"Đã lưu thành công {CARD_RULES_PATH}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi lưu {CARD_RULES_PATH}: {e}")
            return False

    def load_event_rules(self) -> Dict[str, Any]:
        """
        Load event rules prioritizing templates/event_rules.json (141 events)
        and merging user priorities & credit thresholds from root event_rules.json.
        """
        rules: Dict[str, Any] = {}

        # 1. Load comprehensive event database from templates/event_rules.json
        if os.path.exists(EVENT_RULES_TEMPLATE_PATH):
            try:
                with open(EVENT_RULES_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                    logger.info(f"Đã nạp {len(rules.get('events_database', []))} sự kiện từ {EVENT_RULES_TEMPLATE_PATH}")
            except Exception as e:
                logger.warning(f"Không thể đọc {EVENT_RULES_TEMPLATE_PATH}: {e}")

        # 2. Load user customized overrides from root event_rules.json
        user_overrides = {}
        if os.path.exists(EVENT_RULES_PATH):
            try:
                with open(EVENT_RULES_PATH, "r", encoding="utf-8") as f:
                    user_overrides = json.load(f)
            except Exception as e:
                logger.warning(f"Không thể đọc {EVENT_RULES_PATH}: {e}")

        if not rules and not user_overrides:
            rules = DEFAULT_EVENT_RULES.copy()
        elif not rules and user_overrides:
            rules = user_overrides
        else:
            # Merge user_overrides into template database
            for k, v in user_overrides.items():
                if k != "events_database":
                    rules[k] = v

        # Ensure required keys exist
        if "priorities" not in rules:
            rules["priorities"] = DEFAULT_EVENT_RULES["priorities"].copy()
        if "min_credit_reserve" not in rules:
            rules["min_credit_reserve"] = DEFAULT_EVENT_RULES["min_credit_reserve"]
        if "hp_critical_threshold" not in rules:
            rules["hp_critical_threshold"] = DEFAULT_EVENT_RULES["hp_critical_threshold"]
        if "strategy_notes" not in rules:
            rules["strategy_notes"] = DEFAULT_EVENT_RULES["strategy_notes"]

        self._build_event_indexes(rules)
        return rules

    def save_event_rules(self, rules: Dict[str, Any]) -> bool:
        """Export event_rules.json to disk (root) while preserving in-memory indexes."""
        try:
            if "events_database" not in rules and self.events_database:
                for k in ["priorities", "min_credit_reserve", "hp_critical_threshold", "strategy_notes"]:
                    if k in rules:
                        self.event_rules[k] = rules[k]
            else:
                self.event_rules = rules

            self._build_event_indexes(self.event_rules)
            with open(EVENT_RULES_PATH, "w", encoding="utf-8") as f:
                json.dump(rules, f, ensure_ascii=False, indent=2)
            logger.info(f"Đã lưu thành công {EVENT_RULES_PATH}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi lưu {EVENT_RULES_PATH}: {e}")
            return False

    def load_ai_config(self) -> Dict[str, Any]:
        """Load ai_config.json."""
        if os.path.exists(AI_CONFIG_PATH):
            try:
                with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    return cfg
            except Exception as e:
                logger.warning(f"Không thể đọc {AI_CONFIG_PATH}: {e}. Dùng mặc định.")
        return DEFAULT_AI_CONFIG.copy()

    def save_ai_config(self, api_key: str, model_name: str = "gemini-2.5-flash",
                       enable_multimodal: bool = True) -> bool:
        """Save AI settings with encrypted API Key."""
        try:
            cfg = {
                "provider": "gemini",
                "api_key_encrypted": _encrypt_key(api_key),
                "model_name": model_name,
                "enable_multimodal_fallback": enable_multimodal,
                "temperature": 0.1,
                "max_tokens": 512
            }
            self.ai_config = cfg
            with open(AI_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            logger.info(f"Đã lưu cấu hình AI vào {AI_CONFIG_PATH}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi lưu {AI_CONFIG_PATH}: {e}")
            return False

    def get_api_key(self) -> str:
        """Retrieve plain text API key."""
        cipher = self.ai_config.get("api_key_encrypted", "")
        if not cipher:
            # Check environment variable as fallback
            return os.getenv("GEMINI_API_KEY", "")
        return _decrypt_key(cipher)

    def save_all_rules(self, card_rules: Dict[str, Any], event_rules: Dict[str, Any],
                       api_key: str, model_name: str = "gemini-2.5-flash") -> bool:
        """Save both rule JSONs and AI config simultaneously."""
        ok1 = self.save_card_rules(card_rules)
        ok2 = self.save_event_rules(event_rules)
        ok3 = self.save_ai_config(api_key, model_name)
        return ok1 and ok2 and ok3

    # ── Database Matching & Query Helpers ─────────────────────────

    def match_card(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Match OCR text or title against all 403 cards in the database.
        Returns the best matching card dictionary or None.
        """
        if not text:
            return None
        text_lower = text.lower().strip()
        text_norm = " ".join(re.sub(r"[^\w\s%]", " ", text_lower).split())
        text_words = set(text_norm.split())

        # 1. Match by card name
        for name_lower, variants in self.cards_by_name.items():
            if name_lower in text_lower or name_lower in text_norm:
                if len(variants) == 1:
                    return variants[0]

                # Score each variant based on variant name and description tokens
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

                    for kw in v.get("keywords", []):
                        kw_norm = " ".join(re.sub(r"[^\w\s%]", " ", kw.lower()).split())
                        if kw_norm in text_words or kw_norm in text_norm:
                            score += 5.0

                    # Tiny tie-breaker by priority
                    score += v.get("priority", 0) * 0.01
                    return score

                best_variant = max(variants, key=_score_variant)
                return best_variant

        # 2. Match by card ID or filename
        for card in self.cards:
            cid = card.get("id", "").lower()
            fname = card.get("filename", "").lower().replace(".png", "")
            if (cid and cid in text_lower) or (fname and fname in text_lower):
                return card

        return None

    def match_event_choice(self, text: str) -> Optional[tuple]:
        """
        Match OCR text from an event choice button against events_database (141 events).
        Returns (choice_dict, event_dict) or None.
        """
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

