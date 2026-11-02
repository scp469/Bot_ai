"""
Mini-map Parser, DAG Builder, and 3D Island detector for Chaos Mode.
Parses the bottom-left mini-map (X: 20..660, Y: 570..890) into a Directed Acyclic Graph (DAG)
compatible with `czn_bot.chaos.pathfinder`.
"""
import os
import logging
from typing import Dict, List, Optional, Set, Tuple
import cv2
import numpy as np

from dataclasses import dataclass
from enum import Enum
from czn_bot.constants import TEMPLATES_DIR, DATA_TEMPLATES_DIR, LEGACY_TEMPLATES_DIR

logger = logging.getLogger("ChaosBot.MapReader")


class ChaosNodeType(Enum):
    NORMAL = "normal"
    ELITE = "elite"
    REST = "rest"
    EVENT = "event"
    BOSS = "boss"
    OTHER = "other"
    UNKNOWN = "unknown"


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

# Bounding box of Mini-map on 1600x900 resolution
MINIMAP_X1 = 20
MINIMAP_Y1 = 570
MINIMAP_X2 = 660
MINIMAP_Y2 = 890

# Grid column X coordinates (relative to minimap crop)
GRID_COLS = [155, 250, 345, 440, 535]

# Grid row Y coordinates (relative to minimap crop)
GRID_ROWS = [30, 85, 140, 198, 254]

# Boss coordinate (relative to minimap crop)
BOSS_X = 610
BOSS_Y = 20


def extract_minimap(screen: np.ndarray) -> Optional[np.ndarray]:
    """Cắt vùng Mini-map từ ảnh chụp màn hình (hỗ trợ cả ảnh gốc 1600x900 và ảnh đã crop sẵn)."""
    if screen is None or screen.size == 0:
        return None
    h, w = screen.shape[:2]
    if h == 900 and w == 1600:
        return screen[MINIMAP_Y1:MINIMAP_Y2, MINIMAP_X1:MINIMAP_X2]
    if h == 320 and w == 640:
        return screen
    if abs(w / h - 16.0 / 9.0) < 0.05:
        scale_x = w / 1600.0
        scale_y = h / 900.0
        x1 = int(MINIMAP_X1 * scale_x)
        y1 = int(MINIMAP_Y1 * scale_y)
        x2 = int(MINIMAP_X2 * scale_x)
        y2 = int(MINIMAP_Y2 * scale_y)
        crop = screen[y1:y2, x1:x2]
        if crop.shape[0] != 320 or crop.shape[1] != 640:
            crop = cv2.resize(crop, (640, 320), interpolation=cv2.INTER_AREA)
        return crop
    return None


_PIN_TEMPLATE = None
_BOSS_TEMPLATE = None
_EQUIP_TITLE_TEMPLATE = None


def _get_templates():
    global _PIN_TEMPLATE, _BOSS_TEMPLATE
    if _PIN_TEMPLATE is None or _BOSS_TEMPLATE is None:
        search_dirs = [DATA_TEMPLATES_DIR, TEMPLATES_DIR, LEGACY_TEMPLATES_DIR]
        for d in search_dirs:
            pin_p = os.path.join(d, "chaos_node_pin.png")
            boss_p = os.path.join(d, "chaos_node_boss.png")
            if os.path.exists(pin_p) and _PIN_TEMPLATE is None:
                _PIN_TEMPLATE = cv2.imread(pin_p)
            if os.path.exists(boss_p) and _BOSS_TEMPLATE is None:
                _BOSS_TEMPLATE = cv2.imread(boss_p)
            if _PIN_TEMPLATE is not None and _BOSS_TEMPLATE is not None:
                break
    return _PIN_TEMPLATE, _BOSS_TEMPLATE


def _get_settlement_template() -> Optional[np.ndarray]:
    from czn_bot.constants import DATA_TEMPLATES_DIR, TEMPLATES_DIR, LEGACY_TEMPLATES_DIR
    search_dirs = [DATA_TEMPLATES_DIR, TEMPLATES_DIR, LEGACY_TEMPLATES_DIR]
    for d in search_dirs:
        if not d or not os.path.exists(d):
            continue
        p = os.path.join(d, "settlement_title.png")
        if os.path.isfile(p):
            img = cv2.imread(p)
            if img is not None:
                return img
    return None

def _get_equipment_template():
    global _EQUIP_TITLE_TEMPLATE
    if _EQUIP_TITLE_TEMPLATE is None:
        search_dirs = [DATA_TEMPLATES_DIR, TEMPLATES_DIR, LEGACY_TEMPLATES_DIR]
        for d in search_dirs:
            eq_p = os.path.join(d, "equipment_title.png")
            if os.path.exists(eq_p):
                _EQUIP_TITLE_TEMPLATE = cv2.imread(eq_p)
                break
    return _EQUIP_TITLE_TEMPLATE


def is_chaos_map_screen(screen: np.ndarray) -> bool:
    """
    Kiểm tra xem màn hình hiện tại có phải là màn hình chọn đảo Chaos Map không:
    - Có biểu tượng Boss ở góc trên phải Mini-map (match score >= 0.80).
    - Có biểu tượng Ghim 📍 vị trí hiện tại trên Mini-map (match score >= 0.80).
    """
    try:
        minimap = extract_minimap(screen)
        if minimap is None or minimap.shape[:2] != (320, 640):
            return False

        pin_tpl, boss_tpl = _get_templates()
        if pin_tpl is None or boss_tpl is None:
            boss_cell = minimap[5:35, 595:625]
            return boss_cell.std() > 40

        boss_roi = minimap[0:60, 570:640]
        res_boss = cv2.matchTemplate(boss_roi, boss_tpl, cv2.TM_CCOEFF_NORMED)
        _, max_boss, _, _ = cv2.minMaxLoc(res_boss)
        dest_cell = minimap[5:35, 595:625]
        has_destination = (max_boss >= 0.70) or (dest_cell.std() > 30)
        if not has_destination:
            return False

        pin_search = minimap.copy()
        pin_search[0:60, 560:640] = 0
        res_pin = cv2.matchTemplate(pin_search, pin_tpl, cv2.TM_CCOEFF_NORMED)
        _, max_pin, _, _ = cv2.minMaxLoc(res_pin)
        if max_pin < 0.70:
            return False

        return True
    except Exception as e:
        logger.warning(f"Error checking chaos map screen: {e}")
        return False


def classify_node_type(cell: np.ndarray) -> Tuple[Optional[ChaosNodeType], float]:
    """Phân loại loại ô từ vùng ảnh 24x24 pixel của ô trên Mini-map."""
    if cell.std() < 30:
        return None, 0.0

    hsv = cv2.cvtColor(cell, cv2.COLOR_BGR2HSV)
    ch = float(hsv[6:18, 6:18, 0].mean())
    cs = float(hsv[6:18, 6:18, 1].mean())
    cv_val = float(hsv[6:18, 6:18, 2].mean())

    if (135 <= ch <= 175) and cs > 70:
        return ChaosNodeType.NORMAL, cs
    if (10 <= ch <= 55) and cs > 70:
        return ChaosNodeType.REST, cs
    if (105 <= ch <= 135) and cs > 70:
        return ChaosNodeType.EVENT, cs
    if (120 <= ch <= 150) and cs > 50 and cv_val < 130:
        return ChaosNodeType.ELITE, cs
    if (70 <= ch <= 105) and cs <= 115 and cv_val >= 90:
        return ChaosNodeType.OTHER, cv_val

    return None, 0.0


def _row_to_island_choice(r_idx: int, r: int) -> IslandChoice:
    """Ánh xạ vị trí hàng (r_idx) hoặc tọa độ Y trên mini-map tới IslandChoice."""
    if r_idx <= 1 or r < 140:
        return IslandChoice.TOP
    elif r_idx in (2, 3) or (140 <= r < 230):
        return IslandChoice.MIDDLE
    else:
        return IslandChoice.BOTTOM


def parse_chaos_minimap(
    screen: np.ndarray,
) -> Tuple[
    Dict[IslandChoice, str],
    Dict[str, List[str]],
    Dict[str, ChaosNode],
    Set[str],
]:
    """Phân tích toàn bộ Mini-map thành cấu trúc DAG."""
    minimap = extract_minimap(screen)
    if minimap is None:
        logger.error("Không thể cắt vùng Mini-map từ ảnh màn hình")
        return {}, {}, {}, set()

    gray = cv2.cvtColor(minimap, cv2.COLOR_BGR2GRAY)
    nodes_map: Dict[str, ChaosNode] = {}
    present_by_col: Dict[int, List[Tuple[int, int, str]]] = {}

    for c_idx, c in enumerate(GRID_COLS):
        present_by_col[c_idx] = []
        for r_idx, r in enumerate(GRID_ROWS):
            cell = minimap[r - 12 : r + 12, c - 12 : c + 12]
            ntype, _ = classify_node_type(cell)
            if ntype is not None:
                node_id = f"c{c_idx + 1}_r{r_idx}"
                nodes_map[node_id] = ChaosNode(
                    node_id=node_id,
                    node_type=ntype,
                    col_idx=c_idx + 1,
                    row_idx=r_idx,
                    x=c,
                    y=r,
                )
                present_by_col[c_idx].append((r_idx, r, node_id))

    boss_node_id = "boss"
    nodes_map[boss_node_id] = ChaosNode(
        node_id=boss_node_id,
        node_type=ChaosNodeType.BOSS,
        col_idx=6,
        row_idx=0,
        x=BOSS_X,
        y=BOSS_Y,
    )

    adj_list: Dict[str, List[str]] = {nid: [] for nid in nodes_map}

    for c_idx in range(len(GRID_COLS) - 1):
        c1 = GRID_COLS[c_idx]
        c2 = GRID_COLS[c_idx + 1]

        for r1_idx, r1, n1_id in present_by_col[c_idx]:
            for r2_idx, r2, n2_id in present_by_col[c_idx + 1]:
                x1, y1 = c1 + 26, r1 + 12
                x2, y2 = c2 - 26, r2 + 12

                matches = 0
                for t in [0.25, 0.45, 0.65, 0.85]:
                    px = int(x1 + t * (x2 - x1))
                    py = int(y1 + t * (y2 - y1))
                    window = gray[max(0, py - 5): min(gray.shape[0], py + 6), px]
                    if len(window) > 0 and np.max(window) > 70:
                        matches += 1

                if matches >= 2:
                    adj_list[n1_id].append(n2_id)

    last_col_idx = max((c for c, nodes in present_by_col.items() if nodes), default=None)
    if last_col_idx is not None:
        for _, _, n_id in present_by_col[last_col_idx]:
            if boss_node_id not in adj_list[n_id]:
                adj_list[n_id].append(boss_node_id)

    for n_id, edges in adj_list.items():
        if n_id != boss_node_id and not edges:
            node = nodes_map.get(n_id)
            if node and node.col_idx >= 3:
                edges.append(boss_node_id)

    pin_tpl, _ = _get_templates()
    current_col_idx = -1
    pin_tip_x, pin_tip_y = -1, -1
    if pin_tpl is not None:
        pin_search = minimap.copy()
        pin_search[0:60, 560:640] = 0
        res_pin = cv2.matchTemplate(pin_search, pin_tpl, cv2.TM_CCOEFF_NORMED)
        _, max_pin, _, loc_pin = cv2.minMaxLoc(res_pin)
        if max_pin >= 0.70:
            pin_tip_x = loc_pin[0] + pin_tpl.shape[1] // 2
            pin_tip_y = loc_pin[1] + pin_tpl.shape[0]
            for c_idx, c in enumerate(GRID_COLS):
                if abs(pin_tip_x - c) < 45:
                    current_col_idx = c_idx
                    break

    next_nodes: List[Tuple[int, int, str]] = []
    if current_col_idx == -1 or (current_col_idx == 0 and pin_tip_x < GRID_COLS[0] - 25):
        next_nodes = list(present_by_col.get(0, []))
    else:
        col_nodes = present_by_col.get(current_col_idx, [])
        if col_nodes:
            curr_node = min(col_nodes, key=lambda it: abs(it[1] - pin_tip_y))
            curr_id = curr_node[2]
            targets = adj_list.get(curr_id, [])
            for t_id in targets:
                if t_id == boss_node_id:
                    next_nodes.append((0, BOSS_Y, boss_node_id))
                elif t_id in nodes_map:
                    n = nodes_map[t_id]
                    next_nodes.append((n.row_idx, n.y, t_id))
        if not next_nodes and current_col_idx + 1 < len(GRID_COLS):
            next_nodes = list(present_by_col.get(current_col_idx + 1, []))
        elif not next_nodes and current_col_idx + 1 >= len(GRID_COLS):
            next_nodes = [(0, BOSS_Y, boss_node_id)]

    next_nodes.sort(key=lambda it: it[1])
    island_roots: Dict[IslandChoice, str] = {}

    if len(next_nodes) == 1:
        choice = _row_to_island_choice(next_nodes[0][0], next_nodes[0][1])
        island_roots[choice] = next_nodes[0][2]
    elif len(next_nodes) == 2:
        c0 = _row_to_island_choice(next_nodes[0][0], next_nodes[0][1])
        c1 = _row_to_island_choice(next_nodes[1][0], next_nodes[1][1])
        if c0 == c1:
            c0, c1 = IslandChoice.TOP, IslandChoice.BOTTOM
        island_roots[c0] = next_nodes[0][2]
        island_roots[c1] = next_nodes[1][2]
    elif len(next_nodes) >= 3:
        island_roots[IslandChoice.TOP] = next_nodes[0][2]
        island_roots[IslandChoice.MIDDLE] = next_nodes[1][2]
        island_roots[IslandChoice.BOTTOM] = next_nodes[2][2]

    return island_roots, adj_list, nodes_map, {boss_node_id}


def detect_3d_island_coords(
    screen: np.ndarray,
    expected_choices: Optional[List[IslandChoice]] = None,
    pin_score: Optional[float] = None,
    has_equipment_title: Optional[bool] = None,
    state: Optional[Any] = None,
) -> Dict[IslandChoice, Tuple[int, int]]:
    """
    Tìm tọa độ thực tế của các hòn đảo 3D dựa trên:
    - Mũi tên định hướng cyan (▶) tại 3 làn: TOP (795, 211), MID (1021, 477), BOT (793, 742)
    - Sự hiện diện của cờ / thân đảo tại các ROI tương ứng
    - Trả về tọa độ điểm tap an toàn sâu trong thân đảo (>=40px cách mép đảo)
    """
    from czn_bot.constants import CHAOS_MAP_MIN_PIN_SCORE

    if screen is None or screen.size == 0:
        return {}

    # Guard 1: State validation nếu được truyền
    if state is not None:
        state_str = getattr(state, "name", str(state))
        if state_str != "CHAOS_MAP":
            logger.warning(f"[MapReader] Guard chặn detect_3d_island_coords: state={state_str} != CHAOS_MAP")
            return {}

    # Guard 2: Minimap pin score check (ngưỡng 0.75 phân định rõ màn Map thật và màn khác)
    if pin_score is not None and pin_score < CHAOS_MAP_MIN_PIN_SCORE:
        logger.warning(
            f"[MapReader] Guard chặn detect_3d_island_coords: Điểm ghim pin_score={pin_score:.2f} < {CHAOS_MAP_MIN_PIN_SCORE}"
        )
        return {}

    # Guard 3: Neo âm equipment_title
    if has_equipment_title is True:
        logger.warning("[MapReader] Guard chặn detect_3d_island_coords: Phát hiện equipment_title trên màn hình")
        return {}

    if has_equipment_title is None:
        try:
            eq_tpl = _get_equipment_template()
            if eq_tpl is not None and screen.shape[0] >= 180 and screen.shape[1] >= 1000:
                eq_crop = screen[70:180, 650:1000]
                if eq_crop.shape[0] >= eq_tpl.shape[0] and eq_crop.shape[1] >= eq_tpl.shape[1]:
                    res = cv2.matchTemplate(eq_crop, eq_tpl, cv2.TM_CCOEFF_NORMED)
                    _, max_eq, _, _ = cv2.minMaxLoc(res)
                    if max_eq >= 0.65:
                        logger.warning(
                            f"[MapReader] Guard chặn detect_3d_island_coords: Tự phát hiện equipment_title (score={max_eq:.2f} >= 0.65)"
                        )
                        return {}
        except Exception as e_eq:
            logger.debug(f"Lỗi kiểm tra equipment_title trong detect_3d_island_coords: {e_eq}")

    # Guard 4: Neo âm settlement_title
    try:
        st_tpl = _get_settlement_template()
        if st_tpl is not None and screen.shape[0] >= 120 and screen.shape[1] >= 1100:
            st_crop = screen[30:120, 780:1100]
            if st_crop.shape[0] >= st_tpl.shape[0] and st_crop.shape[1] >= st_tpl.shape[1]:
                res_st = cv2.matchTemplate(st_crop, st_tpl, cv2.TM_CCOEFF_NORMED)
                _, max_st, _, _ = cv2.minMaxLoc(res_st)
                if max_st >= 0.65:
                    logger.warning(
                        f"[MapReader] Guard chặn detect_3d_island_coords: Tự phát hiện settlement_title (score={max_st:.2f} >= 0.65)"
                    )
                    return {}
    except Exception as e_st:
        logger.debug(f"Lỗi kiểm tra settlement_title trong detect_3d_island_coords: {e_st}")

    h, w = screen.shape[:2]
    if (h, w) != (900, 1600):
        screen = cv2.resize(screen, (1600, 900), interpolation=cv2.INTER_AREA)

    # 1. Phát hiện mũi tên cyan ▶ tại 3 làn (TOP: 795, 211; MID: 1021, 477; BOT: 793, 742)
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    cyan_mask = cv2.inRange(hsv, (75, 30, 80), (110, 255, 255))

    top_arrow = np.sum(cyan_mask[185:235, 770:820] > 0)
    mid_arrow = np.sum(cyan_mask[450:500, 995:1045] > 0)
    bot_arrow = np.sum(cyan_mask[715:765, 770:820] > 0)

    # 2. Kiểm tra cờ / thân đảo tại ROI 3 làn
    # TOP: x: 1150-1260, y: 65-200
    # MID: x: 1390-1490, y: 316-460
    # BOT: x: 1150-1260, y: 585-735
    top_flag = screen[65:200, 1150:1260].mean()
    mid_flag = screen[316:460, 1390:1490].mean()
    bot_flag = screen[585:735, 1150:1260].mean()

    has_top = (top_arrow > 100) and (top_flag > 55.0)
    has_mid = (mid_arrow > 100) and (mid_flag > 55.0)
    has_bot = (bot_arrow > 100) and (bot_flag > 55.0)

    # Tọa độ điểm tap an toàn nằm trong thân đảo (>= 40px từ viền đảo)
    BODY_POINTS = {
        IslandChoice.TOP: (1070, 200),
        IslandChoice.MIDDLE: (1290, 475),
        IslandChoice.BOTTOM: (1090, 730),
    }

    active_lanes: List[IslandChoice] = []
    if has_top:
        active_lanes.append(IslandChoice.TOP)
    if has_mid:
        active_lanes.append(IslandChoice.MIDDLE)
    if has_bot:
        active_lanes.append(IslandChoice.BOTTOM)

    # Fallback dự phòng nếu mũi tên nhấp nháy đúng frame chụp
    if not active_lanes:
        if mid_flag > 55.0:
            active_lanes.append(IslandChoice.MIDDLE)
        if top_flag > 55.0:
            active_lanes.append(IslandChoice.TOP)
        if bot_flag > 55.0:
            active_lanes.append(IslandChoice.BOTTOM)

    result: Dict[IslandChoice, Tuple[int, int]] = {}
    for lane in active_lanes:
        result[lane] = BODY_POINTS[lane]

    if expected_choices:
        filtered: Dict[IslandChoice, Tuple[int, int]] = {}
        for c in expected_choices:
            if c in result:
                filtered[c] = result[c]
        if filtered:
            return filtered

    return result
