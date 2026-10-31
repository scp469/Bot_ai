"""
Multi-dimensional Deck Evaluation Engine for Chaos Zero Nightmare.
Handles:
1. Choose Epiphany: Scores 3 offered cards/variants against preset targets and bloat penalty.
2. Card Reward: Assigns 1 reward card to 1 of 3 combatants.
3. Remove Card: Identifies basic/starter cards to purge, or safely triggers SKIP.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from czn_bot.chaos.decisions import CardInfo
from czn_bot.chaos.deck_preset import CharacterPreset
from czn_bot.chaos.deck_state import DeckState

logger = logging.getLogger("ChaosBot.DeckEvaluator")


@dataclass
class ScoreBreakdown:
    card_index: int
    card_title: str
    card_id: str
    total_score: float
    v_preset: float
    v_marginal: float
    p_bloat: float
    reasons: List[str] = field(default_factory=list)


class DeckEvaluator:
    """Evaluates card choices, card removals, and card assignments in Chaos mode."""

    def __init__(
        self,
        presets: Optional[Dict[str, CharacterPreset]] = None,
        deck_state: Optional[DeckState] = None
    ):
        self.presets: Dict[str, CharacterPreset] = presets or {}
        self.deck_state: DeckState = deck_state or DeckState()

    def evaluate_epiphany_choices(
        self,
        cards: List[CardInfo],
        active_character: Optional[str] = None
    ) -> Tuple[int, List[ScoreBreakdown]]:
        """
        Score offered cards/epiphanies.
        Formula: Score = V_preset + V_marginal - P_bloat.
        Returns: (best_index, list_of_breakdowns)
        """
        if not cards:
            return 0, []

        preset = self.presets.get(active_character) if active_character else None
        target_deck_size = preset.max_deck_size if preset else 10
        current_deck_size = self.deck_state.get_deck_size(active_character) if active_character else 8

        breakdowns: List[ScoreBreakdown] = []
        best_score = -9999.0
        best_idx = 0

        for idx, card in enumerate(cards):
            reasons: List[str] = []
            cid = card.matched_card.get("id", "") if card.matched_card else ""
            card_title = card.title or card.name

            # 1. Base Priority / Preset Value (V_preset)
            v_preset = float(card.priority) if card.priority > 0 else 50.0
            reasons.append(f"Điểm gốc priority={v_preset:.0f}")

            if preset:
                # Check epiphany targets
                for base_name, target_id in preset.epiphany_targets.items():
                    if cid == target_id or (target_id and target_id.lower() in card_title.lower()):
                        v_preset += 50.0
                        reasons.append(f"+50đ Khớp mục tiêu Epiphany preset [{target_id}]")
                        break

                # Check core cards in preset
                for core_rule in preset.core_cards:
                    if cid == core_rule.card_id or core_rule.card_id.lower() in card_title.lower():
                        v_preset += float(core_rule.priority)
                        reasons.append(f"+{core_rule.priority}đ Thẻ cốt lõi preset [{core_rule.card_id}]")
                        break

            # 2. Marginal Value (V_marginal) based on current deck count
            v_marginal = 0.0
            if preset and cid:
                copies = self.deck_state.count_copies(preset.character, cid)
                # Check max copies constraint
                matching_core = next((c for c in preset.core_cards if c.card_id == cid), None)
                if matching_core:
                    if copies >= matching_core.max_copies:
                        v_marginal -= 60.0
                        reasons.append(f"-60đ Đã đạt giới hạn bản sao ({copies}/{matching_core.max_copies})")
                    elif copies < matching_core.min_copies:
                        v_marginal += 20.0
                        reasons.append(f"+20đ Chưa đủ số bản tối thiểu ({copies}/{matching_core.min_copies})")

            # Bonus for AP / Resource keywords and Elasticity
            if "elasticity" in card.variant.lower() or "elasticity" in card.raw_text.lower():
                v_marginal += 50.0
                reasons.append("+50đ Biến thể Elasticity")

            for kw in card.keywords:
                if kw.lower() in ["action point", "ap", "draw"]:
                    v_marginal += 15.0
                    reasons.append(f"+15đ Hồi tài nguyên ({kw})")

            # 3. Deck Bloat Penalty (P_bloat)
            p_bloat = 0.0
            if current_deck_size >= target_deck_size:
                excess = (current_deck_size - target_deck_size) + 1
                p_bloat = float(excess * 12.0)
                reasons.append(f"-{p_bloat:.0f}đ Phạt phình deck ({current_deck_size}/{target_deck_size})")

            total_score = v_preset + v_marginal - p_bloat

            breakdown = ScoreBreakdown(
                card_index=idx,
                card_title=card_title,
                card_id=cid,
                total_score=total_score,
                v_preset=v_preset,
                v_marginal=v_marginal,
                p_bloat=p_bloat,
                reasons=reasons
            )
            breakdowns.append(breakdown)

            if total_score > best_score:
                best_score = total_score
                best_idx = idx

        # Log score breakdown
        logger.info(f"[DeckEvaluator] Đánh giá {len(cards)} lựa chọn (Chọn slot {best_idx}: {breakdowns[best_idx].card_title}):")
        for b in breakdowns:
            marker = "👉" if b.card_index == best_idx else "  "
            logger.info(f"{marker} Slot {b.card_index}: {b.card_title} -> {b.total_score:.1f}đ ({'; '.join(b.reasons)})")

        return best_idx, breakdowns

    def evaluate_card_reward_combatant(
        self,
        card_title: str,
        is_memory: bool,
        team_characters: List[str]
    ) -> Tuple[int, str]:
        """
        Decide which combatant (0, 1, or 2) should receive the Card Reward.
        Default: Combatant 1 (middle / Rossweisse if present).
        """
        if not team_characters:
            return 1, "Mặc định nhân vật giữa (slot 1)"

        # If we know the team, prioritize the character with the smallest deck or carry
        best_idx = 1
        min_size = 999
        for idx, char in enumerate(team_characters[:3]):
            size = self.deck_state.get_deck_size(char)
            # Preference to main carry if deck is not bloated
            if char in self.presets and size < self.presets[char].max_deck_size:
                return idx, f"Gán cho chủ lực {char} (size {size} < {self.presets[char].max_deck_size})"
            if size < min_size:
                min_size = size
                best_idx = idx

        return best_idx, f"Gán cho nhân vật slot {best_idx + 1} (deck mỏng nhất: {min_size} thẻ)"

    def evaluate_card_removal(
        self,
        visible_card_names: List[str],
        character: str
    ) -> Tuple[str, Optional[int], str]:
        """
        Evaluate which card to remove from the 8 visible cards in Remove Card screen.
        Safe Strategy:
        - If an unwanted card (Basic Attack / Basic Skill / removal_priority) is in visible cards:
          returns ("remove", slot_index, reason)
        - If no unwanted card is visible:
          returns ("skip", None, "Không có thẻ rác trong lưới hiển thị -> Bấm Skip để bảo toàn tài nguyên")
        """
        preset = self.presets.get(character)
        removal_list = preset.removal_priority if preset else []

        # Default basic starter cards that are safe to remove
        starter_basic_keywords = ["sword slash", "standing blade", "basic attack", "basic skill", "matter disintegration"]

        for idx, name in enumerate(visible_card_names):
            name_lower = name.lower()
            # 1. Match against preset removal_priority
            for target in removal_list:
                if target.lower() in name_lower:
                    return "remove", idx, f"Xóa thẻ theo preset [{name}] tại slot {idx}"

            # 2. Match against basic starter cards
            for basic_kw in starter_basic_keywords:
                if basic_kw in name_lower:
                    return "remove", idx, f"Xóa thẻ cơ bản khởi đầu [{name}] tại slot {idx}"

        return "skip", None, "Không tìm thấy thẻ rác trong danh sách nhìn thấy -> Bấm Skip an toàn"
