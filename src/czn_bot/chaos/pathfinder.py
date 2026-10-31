"""
Core Pathfinding, Scoring Engine, and Strategy Profiles for Chaos Mode.
Pure logic, zero GUI/ADB dependencies. Fully unit-testable.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any


class ChaosNodeType(Enum):
    NORMAL = "normal"      # Quái thường (kiếm ⚔)
    ELITE = "elite"        # Quái tinh anh (mặt quỷ tím)
    REST = "rest"          # Lửa trại / Trạm nghỉ (ngọn lửa 🔥)
    EVENT = "event"        # Sự kiện (?)
    BOSS = "boss"          # Trùm / Đích cột cuối
    OTHER = "other"        # Shop, Waypoint, etc. (0 điểm, hợp lệ)
    UNKNOWN = "unknown"    # Ô lạ / không nhận diện được (làm hỏng nhánh)


class IslandChoice(Enum):
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


@dataclass
class ChaosNode:
    node_id: str
    node_type: ChaosNodeType
    col_idx: int = 0
    row_idx: int = 0
    x: int = 0
    y: int = 0


@dataclass
class PathResult:
    island: IslandChoice
    nodes: List[ChaosNode]
    score: float = 0.0
    is_valid: bool = True
    invalid_reason: Optional[str] = None

    @property
    def length(self) -> int:
        return len(self.nodes)


def filter_rule_a(nodes: List[ChaosNode]) -> Tuple[bool, Optional[str]]:
    """
    Áp dụng Luật A cho trường hợp Máu < 60%:
    1. Nếu không có Tinh Anh: Hợp lệ.
    2. Nếu Tinh Anh xuất hiện trước mọi Lửa Trại (hoặc không có Lửa Trại nào): Loại ngay.
    3. Nếu có ít nhất một Lửa Trại xuất hiện trước Tinh Anh đầu tiên: Hợp lệ.
    """
    first_elite_idx = None
    first_rest_idx = None

    for idx, node in enumerate(nodes):
        if node.node_type == ChaosNodeType.ELITE and first_elite_idx is None:
            first_elite_idx = idx
        elif node.node_type == ChaosNodeType.REST and first_rest_idx is None:
            first_rest_idx = idx

    if first_elite_idx is None:
        return True, None

    if first_rest_idx is None:
        return False, f"Tinh anh tại bước {first_elite_idx + 1} nhưng không có lửa trại nào trên nhánh"

    if first_elite_idx < first_rest_idx:
        return False, f"Tinh anh (bước {first_elite_idx + 1}) xuất hiện trước lửa trại (bước {first_rest_idx + 1})"

    return True, None


def calculate_path_score(nodes: List[ChaosNode], is_low_hp: bool) -> float:
    """Legacy scoring function."""
    counts = {t: 0 for t in ChaosNodeType}
    for n in nodes:
        counts[n.node_type] += 1

    if not is_low_hp:
        score = (
            3.0 * counts[ChaosNodeType.ELITE]
            + 1.0 * counts[ChaosNodeType.NORMAL]
            - 2.0 * counts[ChaosNodeType.REST]
        )
    else:
        score = (
            5.0 * counts[ChaosNodeType.REST]
            + 2.0 * counts[ChaosNodeType.EVENT]
            - 10.0 * counts[ChaosNodeType.ELITE]
        )
    return score


# ── Strategy Profiles ─────────────────────────────────────────

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
        """Validate path safety according to this strategy profile."""
        low_hp = self.is_low_hp(hp_percent)

        if self.mode == StrategyMode.SAFE:
            if low_hp:
                has_elite = any(n.node_type == ChaosNodeType.ELITE for n in nodes)
                if has_elite:
                    return False, "[Chiến thuật An Toàn] Máu thấp: Tuyệt đối tránh quái Tinh Anh"
            return filter_rule_a(nodes)

        elif self.mode == StrategyMode.AGGRESSIVE:
            if low_hp:
                return filter_rule_a(nodes)
            return True, None

        else:
            if low_hp:
                return filter_rule_a(nodes)
            return True, None


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


# ── Search & Decision Algorithms ──────────────────────────────

def find_all_paths(
    start_node_id: str,
    adj_list: Dict[str, List[str]],
    nodes_map: Dict[str, ChaosNode],
    boss_node_ids: Set[str],
    visited: Optional[Set[str]] = None
) -> List[List[ChaosNode]]:
    """Find all paths from start_node_id to any boss node."""
    if visited is None:
        visited = set()

    if start_node_id not in nodes_map:
        return []

    current_node = nodes_map[start_node_id]

    if start_node_id in boss_node_ids or current_node.node_type == ChaosNodeType.BOSS:
        return [[current_node]]

    visited.add(start_node_id)
    all_paths = []

    for neighbor_id in adj_list.get(start_node_id, []):
        if neighbor_id not in visited and neighbor_id in nodes_map:
            sub_paths = find_all_paths(
                neighbor_id, adj_list, nodes_map, boss_node_ids, visited.copy()
            )
            for sp in sub_paths:
                all_paths.append([current_node] + sp)

    return all_paths


@dataclass
class IslandEvaluation:
    island: IslandChoice
    best_path: Optional[PathResult] = None
    all_paths: List[PathResult] = field(default_factory=list)
    is_available: bool = True
    rejection_reason: Optional[str] = None

    @property
    def best_score(self) -> float:
        return self.best_path.score if self.best_path and self.best_path.is_valid else float("-inf")


def evaluate_island_branches(
    island_roots: Dict[IslandChoice, str],
    adj_list: Dict[str, List[str]],
    nodes_map: Dict[str, ChaosNode],
    boss_node_ids: Set[str],
    hp_percent: float,
    strategy: Optional[Any] = None,
) -> Dict[IslandChoice, IslandEvaluation]:
    """Evaluate all available islands using the chosen strategy profile."""
    profile = get_strategy_profile(strategy)
    evaluations: Dict[IslandChoice, IslandEvaluation] = {}

    for island, root_id in island_roots.items():
        if not root_id or root_id not in nodes_map:
            evaluations[island] = IslandEvaluation(
                island=island, is_available=False, rejection_reason="Đảo không tồn tại hoặc không bấm được"
            )
            continue

        raw_paths = find_all_paths(root_id, adj_list, nodes_map, boss_node_ids)
        if not raw_paths:
            evaluations[island] = IslandEvaluation(
                island=island, is_available=False, rejection_reason="Không có đường đi nào tới Boss"
            )
            continue

        path_results: List[PathResult] = []
        for p_nodes in raw_paths:
            has_unknown = any(n.node_type == ChaosNodeType.UNKNOWN for n in p_nodes)
            if has_unknown:
                path_results.append(
                    PathResult(island=island, nodes=p_nodes, is_valid=False, invalid_reason="Chứa ô không nhận diện được")
                )
                continue

            reaches_boss = (
                p_nodes[-1].node_id in boss_node_ids
                or p_nodes[-1].node_type == ChaosNodeType.BOSS
            )
            if not reaches_boss:
                path_results.append(
                    PathResult(island=island, nodes=p_nodes, is_valid=False, invalid_reason="Đường không tới được Boss")
                )
                continue

            is_valid, reject_reason = profile.filter_path(p_nodes, hp_percent)
            if not is_valid:
                path_results.append(
                    PathResult(island=island, nodes=p_nodes, is_valid=False, invalid_reason=reject_reason)
                )
                continue

            score = profile.calculate_path_score(p_nodes, hp_percent)
            path_results.append(
                PathResult(island=island, nodes=p_nodes, score=score, is_valid=True)
            )

        valid_paths = [p for p in path_results if p.is_valid]
        if not valid_paths:
            evaluations[island] = IslandEvaluation(
                island=island,
                all_paths=path_results,
                is_available=False,
                rejection_reason="Tất cả các nhánh sau đảo này đều bị loại (Luật A hoặc ô lỗi)",
            )
            continue

        best_p = max(valid_paths, key=lambda p: (p.score, -p.length))
        evaluations[island] = IslandEvaluation(
            island=island,
            best_path=best_p,
            all_paths=path_results,
            is_available=True
        )

    return evaluations


def select_best_island(
    island_roots: Dict[IslandChoice, str],
    adj_list: Dict[str, List[str]],
    nodes_map: Dict[str, ChaosNode],
    boss_node_ids: Set[str],
    hp_percent: float,
    strategy: Optional[Any] = None,
) -> Tuple[Optional[IslandChoice], Dict[IslandChoice, IslandEvaluation]]:
    """Select the optimal island choice."""
    evaluations = evaluate_island_branches(
        island_roots, adj_list, nodes_map, boss_node_ids, hp_percent, strategy=strategy
    )

    valid_islands = [
        ev for ev in evaluations.values() if ev.is_available and ev.best_path is not None
    ]

    if not valid_islands:
        return None, evaluations

    if len(valid_islands) == 1:
        return valid_islands[0].island, evaluations

    island_priority = {
        IslandChoice.TOP: 3,
        IslandChoice.MIDDLE: 2,
        IslandChoice.BOTTOM: 1,
    }

    best_ev = max(
        valid_islands,
        key=lambda ev: (
            ev.best_score,
            -ev.best_path.length,
            island_priority.get(ev.island, 0)
        )
    )

    return best_ev.island, evaluations

