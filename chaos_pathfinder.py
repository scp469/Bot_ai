"""
Core Pathfinding and Scoring Engine for Chaos Mode.
Pure logic, zero GUI/ADB dependencies. Fully unit-testable.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


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

    # Không có tinh anh -> Luôn hợp lệ
    if first_elite_idx is None:
        return True, None

    # Có tinh anh nhưng không có lửa trại nào
    if first_rest_idx is None:
        return False, f"Tinh anh tại bước {first_elite_idx + 1} nhưng không có lửa trại nào trên nhánh"

    # Tinh anh xuất hiện trước lửa trại
    if first_elite_idx < first_rest_idx:
        return False, f"Tinh anh (bước {first_elite_idx + 1}) xuất hiện trước lửa trại (bước {first_rest_idx + 1})"

    # Có lửa trại trước tinh anh đầu tiên -> Hợp lệ
    return True, None


def calculate_path_score(nodes: List[ChaosNode], is_low_hp: bool) -> float:
    """
    Tính điểm cho một lộ trình hợp lệ:
    - Khi Máu >= 60% (is_low_hp == False):
      Score = 3 * Elite + 1 * Normal - 2 * Rest + 0 * Other
    - Khi Máu < 60% (is_low_hp == True):
      Score = 5 * Rest + 2 * Event - 10 * Elite + 0 * Normal + 0 * Other
    """
    counts = {t: 0 for t in ChaosNodeType}
    for n in nodes:
        counts[n.node_type] += 1

    if not is_low_hp:
        # Máu >= 60%: Tấn công
        score = (
            3.0 * counts[ChaosNodeType.ELITE]
            + 1.0 * counts[ChaosNodeType.NORMAL]
            - 2.0 * counts[ChaosNodeType.REST]
        )
    else:
        # Máu < 60%: Sinh tồn
        score = (
            5.0 * counts[ChaosNodeType.REST]
            + 2.0 * counts[ChaosNodeType.EVENT]
            - 10.0 * counts[ChaosNodeType.ELITE]
        )
    return score


def find_all_paths(
    start_node_id: str,
    adj_list: Dict[str, List[str]],
    nodes_map: Dict[str, ChaosNode],
    boss_node_ids: Set[str],
    visited: Optional[Set[str]] = None
) -> List[List[ChaosNode]]:
    """Tìm tất cả các đường đi từ start_node_id tới bất kỳ node nào trong boss_node_ids."""
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
    """
    Đánh giá tất cả các đảo khả dụng.
    Mỗi đảo được gán điểm bằng điểm của đường đi hợp lệ tốt nhất xuất phát từ đảo đó.
    """
    from strategy_profile import get_strategy_profile
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
            # 1. Kiểm tra ô lạ / UNKNOWN
            has_unknown = any(n.node_type == ChaosNodeType.UNKNOWN for n in p_nodes)
            if has_unknown:
                path_results.append(
                    PathResult(island=island, nodes=p_nodes, is_valid=False, invalid_reason="Chứa ô không nhận diện được")
                )
                continue

            # 2. Kiểm tra đích có phải Boss không
            reaches_boss = (
                p_nodes[-1].node_id in boss_node_ids
                or p_nodes[-1].node_type == ChaosNodeType.BOSS
            )
            if not reaches_boss:
                path_results.append(
                    PathResult(island=island, nodes=p_nodes, is_valid=False, invalid_reason="Đường không tới được Boss")
                )
                continue

            # 3. Lọc an toàn theo Chiến thuật
            is_valid, reject_reason = profile.filter_path(p_nodes, hp_percent)
            if not is_valid:
                path_results.append(
                    PathResult(island=island, nodes=p_nodes, is_valid=False, invalid_reason=reject_reason)
                )
                continue

            # 4. Tính điểm theo Chiến thuật
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

        # Chọn đường tốt nhất: Điểm cao nhất -> ngắn hơn
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
    """
    Lựa chọn đảo tối ưu nhất theo hồ sơ chiến thuật:
    1. Đánh giá tất cả các đảo.
    2. Lọc các đảo có nhánh sạch hợp lệ.
    3. Xếp hạng: Điểm cao nhất -> Độ dài đường ngắn hơn -> Thứ tự ưu tiên Top > Middle > Bottom.
    4. Trả về (best_island, evaluations). Nếu không có đảo nào hợp lệ, trả về (None, evaluations).
    """
    evaluations = evaluate_island_branches(
        island_roots, adj_list, nodes_map, boss_node_ids, hp_percent, strategy=strategy
    )

    valid_islands = [
        ev for ev in evaluations.values() if ev.is_available and ev.best_path is not None
    ]

    if not valid_islands:
        return None, evaluations

    # Nếu chỉ có duy nhất 1 đảo khả dụng (đường độc đạo)
    if len(valid_islands) == 1:
        return valid_islands[0].island, evaluations

    # Thứ tự ưu tiên đảo khi hòa điểm và hòa độ dài
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
