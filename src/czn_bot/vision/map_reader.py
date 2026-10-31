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

from czn_bot.constants import TEMPLATES_DIR, DATA_TEMPLATES_DIR, LEGACY_TEMPLATES_DIR
from czn_bot.chaos.pathfinder import ChaosNode, ChaosNodeType, IslandChoice

logger = logging.getLogger("ChaosBot.MapReader")

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


def _get_templates():
    global _PIN_TEMPLATE, _BOSS_TEMPLATE
    if _PIN_TEMPLATE is None:
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
) -> Dict[IslandChoice, Tuple[int, int]]:
    """Tìm tọa độ thực tế của các bong bóng biểu tượng trên các hòn đảo 3D."""
    if screen is None or screen.size == 0:
        return {}

    h, w = screen.shape[:2]
    if (h, w) != (900, 1600):
        screen = cv2.resize(screen, (1600, 900), interpolation=cv2.INTER_AREA)

    roi_x1, roi_y1, roi_x2, roi_y2 = 680, 80, 1480, 780
    roi = screen[roi_y1:roi_y2, roi_x1:roi_x2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    icon_mask = ((hsv[:, :, 1] > 110) & (hsv[:, :, 2] > 120)).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    closed = cv2.morphologyEx(icon_mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 250 < area < 20000:
            M = cv2.moments(cnt)
            if M["m00"] > 0:
                cx = roi_x1 + int(M["m10"] / M["m00"])
                cy = roi_y1 + int(M["m01"] / M["m00"])
                candidates.append((cx, cy + 10, area))

    candidates.sort(key=lambda pt: pt[1])

    filtered: List[Tuple[int, int]] = []
    for pt in candidates:
        if not filtered or abs(pt[1] - filtered[-1][1]) >= 90:
            filtered.append((pt[0], pt[1]))

    result: Dict[IslandChoice, Tuple[int, int]] = {}
    if not filtered:
        return result

    if expected_choices:
        order = [IslandChoice.TOP, IslandChoice.MIDDLE, IslandChoice.BOTTOM]
        sorted_choices = [c for c in order if c in expected_choices]

        if len(sorted_choices) == 1 and filtered:
            target_choice = sorted_choices[0]
            if len(filtered) == 1:
                result[target_choice] = filtered[0]
            elif target_choice == IslandChoice.BOTTOM:
                result[target_choice] = filtered[-1]
            elif target_choice == IslandChoice.TOP:
                result[target_choice] = filtered[0]
            else:
                result[target_choice] = filtered[len(filtered) // 2]
            return result

        if len(filtered) == len(sorted_choices):
            for choice, pt in zip(sorted_choices, filtered):
                result[choice] = pt
            return result
        elif len(filtered) > len(sorted_choices):
            for choice in sorted_choices:
                if choice == IslandChoice.TOP:
                    pts = [p for p in filtered if p[1] < 350]
                    if pts:
                        result[choice] = pts[0]
                elif choice == IslandChoice.MIDDLE:
                    pts = [p for p in filtered if 350 <= p[1] <= 650]
                    if pts:
                        result[choice] = pts[0]
                elif choice == IslandChoice.BOTTOM:
                    pts = [p for p in filtered if p[1] > 650]
                    if pts:
                        result[choice] = pts[-1]
            if len(result) == len(sorted_choices):
                return result

    if len(filtered) == 1:
        result[IslandChoice.MIDDLE] = filtered[0]
    elif len(filtered) == 2:
        result[IslandChoice.TOP] = filtered[0]
        result[IslandChoice.BOTTOM] = filtered[1]
    elif len(filtered) >= 3:
        result[IslandChoice.TOP] = filtered[0]
        result[IslandChoice.MIDDLE] = filtered[1]
        result[IslandChoice.BOTTOM] = filtered[2]

    return result

