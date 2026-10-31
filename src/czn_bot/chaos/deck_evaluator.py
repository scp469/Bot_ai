"""
Multi-dimensional Deck Evaluation Engine for Chaos Zero Nightmare.
Handles:
1. Choose Epiphany: Scores 3 offered cards/variants against preset targets and bloat penalty.
2. Card Reward: Assigns 1 reward card to 1 of 3 combatants.
3. Remove Card: Identifies basic/starter cards to purge, or safely triggers SKIP.
"""
import re
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

        preset = (self.presets.get(active_character) or self.presets.get(active_character.lower())) if active_character else None
        target_deck_size = preset.max_deck_size if preset else 10
        current_deck_size = self.deck_state.get_deck_size(active_character) if active_character else 8
        if current_deck_size == 0 and active_character:
            # Fallback if deck not explicitly initialized: assume starter deck has 7 cards
            current_deck_size = 7

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
                cid_norm = cid.lower().replace("_", " ")
                title_norm = card_title.lower().replace("_", " ")
                matching_core = None
                for core_rule in preset.core_cards:
                    core_norm = core_rule.card_id.lower().replace("_", " ")
                    if (
                        cid.lower() == core_rule.card_id.lower()
                        or (cid_norm and (cid_norm in core_norm or core_norm in cid_norm))
                        or (title_norm and (title_norm in core_norm or core_norm in title_norm))
                    ):
                        v_preset += float(core_rule.priority)
                        reasons.append(f"+{core_rule.priority}đ Thẻ cốt lõi preset [{core_rule.card_id}]")
                        matching_core = core_rule
                        break

            # 2. Marginal Value (V_marginal) based on current deck count
            v_marginal = 0.0
            if preset and matching_core:
                copies = self.deck_state.count_copies(preset.character, matching_core.card_id, include_variants=True)
                # Check max copies constraint
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
        team_characters: List[str],
        on_screen_counts: Optional[List[int]] = None,
        card_id: Optional[str] = None,
        card_character: Optional[str] = None
    ) -> Tuple[int, str]:
        """
        Decide which combatant (0, 1, or 2) should receive the Card Reward.
        Evaluates on-screen card counts (or in-memory DeckState), checking character affinity,
        core card priorities with max_copies constraint, and deck bloat.
        """
        if not team_characters:
            return 1, "Mặc định nhân vật giữa (slot 1)"

        num_slots = min(3, len(team_characters))
        counts: List[int] = []
        for i in range(num_slots):
            char = team_characters[i]
            if (
                on_screen_counts
                and i < len(on_screen_counts)
                and on_screen_counts[i] is not None
                and 0 < int(on_screen_counts[i]) <= 40
            ):
                c = int(on_screen_counts[i])
                self.deck_state.sync_deck_size(char, c)
            else:
                c = self.deck_state.get_deck_size(char)
                if c == 0:
                    c = 8
            counts.append(c)

        # 1. Non-memory character-specific card: assign to the specific character if in team
        if not is_memory and card_character:
            for idx in range(num_slots):
                if team_characters[idx].lower() == card_character.lower():
                    char = team_characters[idx]
                    preset = self.presets.get(char) or self.presets.get(char.lower())
                    if preset and card_id:
                        core = next((c for c in preset.core_cards if c.card_id == card_id or card_id in c.card_id), None)
                        if core:
                            copies = self.deck_state.count_copies(char, core.card_id, include_variants=True)
                            if copies >= core.max_copies:
                                logger.info(f"[DeckEvaluator] {char} đã đủ max_copies [{core.card_id}] ({copies}/{core.max_copies})")
                    return idx, f"Gán thẻ độc quyền cho {char} (Slot {idx + 1})"

        # 2. Check presets for matching core cards with max_copies constraint
        title_norm = card_title.lower().replace("_", " ")
        cid_norm = (card_id or "").lower().replace("_", " ")
        for idx in range(num_slots):
            char = team_characters[idx]
            preset = self.presets.get(char) or self.presets.get(char.lower())
            if preset:
                for core in preset.core_cards:
                    core_norm = core.card_id.lower().replace("_", " ")
                    matches = (
                        (card_id and (core.card_id.lower() == card_id.lower() or card_id.lower() in core.card_id.lower() or core.card_id.lower() in card_id.lower()))
                        or (title_norm and (title_norm in core_norm or core_norm in title_norm))
                        or (cid_norm and (cid_norm in core_norm or core_norm in cid_norm))
                    )
                    if matches:
                        copies = self.deck_state.count_copies(char, core.card_id, include_variants=True)
                        if copies < core.max_copies:
                            return idx, f"Gán thẻ phù hợp cốt lõi cho {char} [{core.card_id}] ({copies}/{core.max_copies} bản)"
                        else:
                            logger.info(f"[DeckEvaluator] Bỏ qua gán cho {char}: đã đạt max_copies [{core.card_id}] ({copies}/{core.max_copies})")

        # 3. If Memory Card: prioritize main carry if not bloated, else lowest deck
        if is_memory:
            for idx in range(num_slots):
                char = team_characters[idx]
                preset = self.presets.get(char) or self.presets.get(char.lower())
                if preset and counts[idx] < preset.max_deck_size:
                    return idx, f"Gán Thẻ Ký Ức (Memory) cho chủ lực {char} (size {counts[idx]} < {preset.max_deck_size})"

            min_idx = min(range(len(counts)), key=counts.__getitem__)
            return min_idx, f"Gán Thẻ Ký Ức cho {team_characters[min_idx]} (deck mỏng nhất: {counts[min_idx]} thẻ)"

        # 4. Default: assign to character with the smallest deck (avoid bloat)
        min_idx = min(range(len(counts)), key=counts.__getitem__)
        return min_idx, f"Gán cho nhân vật slot {min_idx + 1} ({team_characters[min_idx]}) có deck mỏng nhất: {counts[min_idx]} thẻ"

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
        preset = self.presets.get(character) or (self.presets.get(character.lower()) if character else None)
        removal_list = preset.removal_priority if preset else []

        # 1. Match against preset removal_priority in priority order
        for target in removal_list:
            cleaned = re.sub(r"^[a-z]+_", "", target.lower()).replace("_base", "").replace("_", " ")
            cleaned_stem = cleaned[:-2] if len(cleaned) > 6 else cleaned
            for idx, name in enumerate(visible_card_names):
                name_lower = name.lower()
                if (
                    cleaned in name_lower
                    or cleaned_stem in name_lower
                    or target.lower() in name_lower
                ):
                    return "remove", idx, f"Xóa thẻ theo preset [{name}] tại slot {idx}"

        # 2. Match against basic starter cards
        starter_basic_keywords = [
            "sword slash", "sword slas", "standing blade", "standing blad",
            "basic attack", "basic_atta", "basic skill",
            "matter disintegration", "barrier deployment"
        ]
        for basic_kw in starter_basic_keywords:
            for idx, name in enumerate(visible_card_names):
                if basic_kw in name.lower():
                    return "remove", idx, f"Xóa thẻ cơ bản khởi đầu [{name}] tại slot {idx}"

        return "skip", None, "Không tìm thấy thẻ rác trong danh sách nhìn thấy -> Bấm Skip an toàn"
