"""
Strategy profiles for Chaos Mode pathfinding in Chaos Zero Nightmare Bot.
Allows customizing weights and risk tolerance:
- BALANCED: Standard balanced formula (Elite for reward, Rest when HP < 60%).
- SAFE: Survival prioritized (High value for Rest/Event, strictly avoids Elite, HP threshold 70%).
- AGGRESSIVE: High risk / reward (Aggressively hunts Elites even down to 40% HP).
"""
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any

from chaos_pathfinder import ChaosNodeType, ChaosNode, filter_rule_a


class StrategyMode(Enum):
    SAFE = "Safe"
    BALANCED = "Balanced"
    AGGRESSIVE = "Aggressive"


@dataclass
class StrategyProfile:
    name: str
    mode: StrategyMode
    hp_threshold: float
    weights_high_hp: Dict[ChaosNodeType, float]
    weights_low_hp: Dict[ChaosNodeType, float]

    def is_low_hp(self, hp_percent: float) -> bool:
        """Check if HP is below this profile's low-HP threshold."""
        return hp_percent < self.hp_threshold

    def calculate_path_score(self, nodes: List[ChaosNode], hp_percent: float) -> float:
        """Calculate weighted path score according to this strategy's formula."""
        low_hp = self.is_low_hp(hp_percent)
        weights = self.weights_low_hp if low_hp else self.weights_high_hp

        score = 0.0
        for n in nodes:
            score += weights.get(n.node_type, 0.0)
        return score

    def filter_path(self, nodes: List[ChaosNode], hp_percent: float) -> Tuple[bool, Optional[str]]:
        """
        Validate path safety according to this strategy profile.
        Returns: (is_valid: bool, rejection_reason: Optional[str])
        """
        low_hp = self.is_low_hp(hp_percent)

        if self.mode == StrategyMode.SAFE:
            # Safe mode: Strictly avoid Elite if HP is low, or require Rest before Elite
            if low_hp:
                has_elite = any(n.node_type == ChaosNodeType.ELITE for n in nodes)
                if has_elite:
                    return False, "[Chiến thuật An Toàn] Máu thấp: Tuyệt đối tránh quái Tinh Anh"
            return filter_rule_a(nodes)

        elif self.mode == StrategyMode.AGGRESSIVE:
            # Aggressive mode: Tolerates Elite encounters, only enforces Rule A when HP < 40%
            if low_hp:
                return filter_rule_a(nodes)
            return True, None

        else:
            # Balanced mode: Standard Rule A when HP < 60%
            if low_hp:
                return filter_rule_a(nodes)
            return True, None


# ── Predefined Strategy Profiles ──────────────────────────────────────

PROFILE_BALANCED = StrategyProfile(
    name="Cân Bằng (Balanced)",
    mode=StrategyMode.BALANCED,
    hp_threshold=0.60,
    weights_high_hp={
        ChaosNodeType.ELITE: 3.0,
        ChaosNodeType.NORMAL: 1.0,
        ChaosNodeType.REST: -2.0,
        ChaosNodeType.EVENT: 0.0,
        ChaosNodeType.OTHER: 0.0,
        ChaosNodeType.BOSS: 0.0,
        ChaosNodeType.UNKNOWN: -100.0,
    },
    weights_low_hp={
        ChaosNodeType.REST: 5.0,
        ChaosNodeType.EVENT: 2.0,
        ChaosNodeType.ELITE: -10.0,
        ChaosNodeType.NORMAL: 0.0,
        ChaosNodeType.OTHER: 0.0,
        ChaosNodeType.BOSS: 0.0,
        ChaosNodeType.UNKNOWN: -100.0,
    },
)

PROFILE_SAFE = StrategyProfile(
    name="An Toàn (Safe)",
    mode=StrategyMode.SAFE,
    hp_threshold=0.70,
    weights_high_hp={
        ChaosNodeType.REST: 3.0,
        ChaosNodeType.EVENT: 2.0,
        ChaosNodeType.NORMAL: 1.0,
        ChaosNodeType.ELITE: 0.5,
        ChaosNodeType.OTHER: 0.0,
        ChaosNodeType.BOSS: 0.0,
        ChaosNodeType.UNKNOWN: -100.0,
    },
    weights_low_hp={
        ChaosNodeType.REST: 8.0,
        ChaosNodeType.EVENT: 4.0,
        ChaosNodeType.ELITE: -25.0,
        ChaosNodeType.NORMAL: -1.0,
        ChaosNodeType.OTHER: 0.0,
        ChaosNodeType.BOSS: 0.0,
        ChaosNodeType.UNKNOWN: -100.0,
    },
)

PROFILE_AGGRESSIVE = StrategyProfile(
    name="Tấn Công (Aggressive)",
    mode=StrategyMode.AGGRESSIVE,
    hp_threshold=0.40,
    weights_high_hp={
        ChaosNodeType.ELITE: 5.0,
        ChaosNodeType.NORMAL: 1.0,
        ChaosNodeType.REST: -3.0,
        ChaosNodeType.EVENT: 0.5,
        ChaosNodeType.OTHER: 0.0,
        ChaosNodeType.BOSS: 0.0,
        ChaosNodeType.UNKNOWN: -100.0,
    },
    weights_low_hp={
        ChaosNodeType.REST: 4.0,
        ChaosNodeType.ELITE: 2.0,
        ChaosNodeType.EVENT: 1.0,
        ChaosNodeType.NORMAL: 0.0,
        ChaosNodeType.OTHER: 0.0,
        ChaosNodeType.BOSS: 0.0,
        ChaosNodeType.UNKNOWN: -100.0,
    },
)

PROFILES: Dict[str, StrategyProfile] = {
    "balanced": PROFILE_BALANCED,
    "safe": PROFILE_SAFE,
    "aggressive": PROFILE_AGGRESSIVE,
}


def get_strategy_profile(strategy: Any) -> StrategyProfile:
    """Resolve a strategy profile by name, enum, or instance."""
    if isinstance(strategy, StrategyProfile):
        return strategy
    if isinstance(strategy, StrategyMode):
        strategy = strategy.value.lower()
    if isinstance(strategy, str):
        key = strategy.strip().lower()
        if "safe" in key or "an toàn" in key:
            return PROFILE_SAFE
        elif "aggr" in key or "tấn công" in key:
            return PROFILE_AGGRESSIVE
        return PROFILE_BALANCED
    return PROFILE_BALANCED
