"""
Mini-map Parser and DAG Builder for Chaos Mode.
Parses the bottom-left mini-map (X: 20..660, Y: 570..890) into a Directed Acyclic Graph (DAG)
compatible with `chaos_pathfinder.py`.
"""
import logging
from typing import Dict, List, Optional, Set, Tuple
import cv2
import numpy as np

from chaos_pathfinder import ChaosNode, ChaosNodeType, IslandChoice

logger = logging.getLogger("ChaosBot")

# Bounding box of Mini-map on 1600x900 resolution
MINIMAP_X1 = 20
MINIMAP_Y1 = 570
MINIMAP_X2 = 660
MINIMAP_Y2 = 890

# Grid column X coordinates (relative to minimap crop)
GRID_COLS = [155, 250, 345, 440, 535]

# Grid row Y coordinates (relative to minimap crop)
# Row 0: 30, Row 1: 85 (Top), Row 2: 140, Row 3: 198 (Mid), Row 4: 254 (Bot)
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
    # Nếu tỷ lệ tương đương 1600x900
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
        import os
        base = os.path.dirname(os.path.abspath(__file__))
        pin_p = os.path.join(base, "templates", "chaos_node_pin.png")
        boss_p = os.path.join(base, "templates", "chaos_node_boss.png")
        if os.path.exists(pin_p):
            _PIN_TEMPLATE = cv2.imread(pin_p)
        if os.path.exists(boss_p):
            _BOSS_TEMPLATE = cv2.imread(boss_p)
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
            # Fallback nếu thiếu file template
            boss_cell = minimap[5:35, 595:625]
            return boss_cell.std() > 40

        # 1. Kiểm tra điểm đến ở góc trên phải Mini-map (Boss skull hoặc Shop/Waypoint)
        boss_roi = minimap[0:60, 570:640]
        res_boss = cv2.matchTemplate(boss_roi, boss_tpl, cv2.TM_CCOEFF_NORMED)
        _, max_boss, _, _ = cv2.minMaxLoc(res_boss)
        dest_cell = minimap[5:35, 595:625]
        has_destination = (max_boss >= 0.70) or (dest_cell.std() > 30)
        if not has_destination:
            return False

        # 2. So khớp biểu tượng Ghim 📍 (tìm theo toàn bộ minimap, trừ góc Boss trên phải)
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
    """
    Phân loại loại ô từ vùng ảnh 24x24 pixel của ô trên Mini-map:
    - NORMAL (Quái thường): Biểu tượng kiếm hồng/đỏ.
    - REST (Lửa trại): Biểu tượng ngọn lửa cam.
    - EVENT (Sự kiện): Biểu tượng dấu hỏi xanh.
    - ELITE (Tinh anh): Biểu tượng mặt quỷ tím có sừng.
    - OTHER (Waypoint, Shop): Biểu tượng cổng trắng/xám, 0 điểm.
    - UNKNOWN: Ô lạ không nhận diện được.
    """
    if cell.std() < 30:
        return None, 0.0

    hsv = cv2.cvtColor(cell, cv2.COLOR_BGR2HSV)
    # Lấy vùng trung tâm 12x12
    ch = float(hsv[6:18, 6:18, 0].mean())
    cs = float(hsv[6:18, 6:18, 1].mean())
    cv_val = float(hsv[6:18, 6:18, 2].mean())

    # 1. Quái thường (Kiếm bắt chéo - màu hồng/đỏ tím: Hue 135..175, Saturation cao)
    if (135 <= ch <= 175) and cs > 70:
        return ChaosNodeType.NORMAL, cs

    # 2. Lửa trại / Trạm nghỉ (Ngọn lửa cam: Hue 10..55, Saturation cao)
    if (10 <= ch <= 55) and cs > 70:
        return ChaosNodeType.REST, cs

    # 3. Sự kiện (Dấu hỏi ? màu xanh/cyan: Hue 105..135, Saturation cao)
    if (105 <= ch <= 135) and cs > 70:
        return ChaosNodeType.EVENT, cs

    # 4. Quái tinh anh (Mặt quỷ có sừng tím)
    if (120 <= ch <= 150) and cs > 50 and cv_val < 130:
        return ChaosNodeType.ELITE, cs

    # 5. Waypoint / Shop / Cổng dịch chuyển (Màu trắng xám nhạt: Saturation thấp, Value cao)
    # 5. Waypoint / Shop / Cổng dịch chuyển (Màu xám/xanh nhạt: Saturation <= 115, Value >= 90)
    if (70 <= ch <= 105) and cs <= 115 and cv_val >= 90:
        return ChaosNodeType.OTHER, cv_val

    # Nếu không khớp bất kỳ mẫu node hợp lệ nào ở trên -> Ô trống hoặc nền bản đồ
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
    """
    Phân tích toàn bộ Mini-map thành cấu trúc DAG:
    Trả về:
    - island_roots: Dict[IslandChoice, node_id] (Ánh xạ các đảo Trên/Giữa/Dưới tới node khởi đầu)
    - adj_list: Dict[node_id, List[target_node_id]] (Danh sách kề của đồ thị DAG)
    - nodes_map: Dict[node_id, ChaosNode] (Bản đồ chi tiết các node)
    - boss_node_ids: Set[str] (Tập hợp các node đích - Boss)
    """
    minimap = extract_minimap(screen)
    if minimap is None:
        logger.error("Không thể cắt vùng Mini-map từ ảnh màn hình")
        return {}, {}, {}, set()

    gray = cv2.cvtColor(minimap, cv2.COLOR_BGR2GRAY)
    nodes_map: Dict[str, ChaosNode] = {}
    present_by_col: Dict[int, List[Tuple[int, int, str]]] = {}

    # Bước 1: Phát hiện và phân loại các node trên lưới 5 cột
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

    # Thêm Boss node (Cột 6)
    boss_node_id = "boss"
    nodes_map[boss_node_id] = ChaosNode(
        node_id=boss_node_id,
        node_type=ChaosNodeType.BOSS,
        col_idx=6,
        row_idx=0,
        x=BOSS_X,
        y=BOSS_Y,
    )

    # Bước 2: Dựng các cạnh nối giữa các cột liền kề
    adj_list: Dict[str, List[str]] = {nid: [] for nid in nodes_map}

    for c_idx in range(len(GRID_COLS) - 1):
        c1 = GRID_COLS[c_idx]
        c2 = GRID_COLS[c_idx + 1]

        for r1_idx, r1, n1_id in present_by_col[c_idx]:
            for r2_idx, r2, n2_id in present_by_col[c_idx + 1]:
                # Đoạn thẳng kết nối nằm ở khoảng trống giữa 2 ô (từ đỉnh phải ô 1 đến đỉnh trái ô 2)
                # Bán kính chiều ngang mỗi ô hình thoi là ~26px, tâm dọc thực tế là r + 12px
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

    # Bước 3: Nối toàn bộ các node ở cột cuối cùng vào Boss (hỗ trợ cả map 4 cột và 5 cột)
    last_col_idx = max((c for c, nodes in present_by_col.items() if nodes), default=None)
    if last_col_idx is not None:
        for _, _, n_id in present_by_col[last_col_idx]:
            if boss_node_id not in adj_list[n_id]:
                adj_list[n_id].append(boss_node_id)

    # Đảm bảo các node ở các cột sâu (col_idx >= 3) không có nhánh con đều nối trực tiếp vào Boss
    for n_id, edges in adj_list.items():
        if n_id != boss_node_id and not edges:
            node = nodes_map.get(n_id)
            if node and node.col_idx >= 3:
                edges.append(boss_node_id)

    # Bước 4: Xác định các đảo lựa chọn tiếp theo dựa trên vị trí Ghim (Pin 📍) hiện tại
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
        # Đang ở điểm xuất phát trước Cột 1: các lựa chọn nằm ở Cột 1
        next_nodes = list(present_by_col.get(0, []))
    else:
        # Nhân vật đang ở Cột current_col_idx: tìm node gần ghim nhất
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
            # Dự phòng: lấy toàn bộ node ở cột kế tiếp
            next_nodes = list(present_by_col.get(current_col_idx + 1, []))
        elif not next_nodes and current_col_idx + 1 >= len(GRID_COLS):
            next_nodes = [(0, BOSS_Y, boss_node_id)]

    # Sắp xếp các ô tiếp theo theo chiều dọc (Y tăng dần: Trên -> Giữa -> Dưới)
    next_nodes.sort(key=lambda it: it[1])
    island_roots: Dict[IslandChoice, str] = {}

    if len(next_nodes) == 1:
        # Trường hợp 1 đảo (đường độc đạo): phân loại theo hàng (thường là MIDDLE)
        choice = _row_to_island_choice(next_nodes[0][0], next_nodes[0][1])
        island_roots[choice] = next_nodes[0][2]
    elif len(next_nodes) == 2:
        # 2 đảo: phân loại dựa trên hàng thực tế (Top: row 1, Mid: row 3, Bot: row 4)
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
    """
    Tìm tọa độ thực tế của các bong bóng biểu tượng trên các hòn đảo 3D (vùng bên phải màn hình).
    Sử dụng không gian màu HSV để lọc màu icon (Kiếm, Lửa, Sự kiện, Tinh anh)
    kết hợp với tính toán tâm hình học (Centroid Moments) để trả về tọa độ click chính xác.

    :param screen: Ảnh chụp toàn màn hình 1600x900 BGR.
    :param expected_choices: Danh sách IslandChoice kỳ vọng từ minimap (ví dụ [TOP, MIDDLE]).
    :return: Dict[IslandChoice, (click_x, click_y)]
    """
    if screen is None or screen.size == 0:
        return {}

    # Đảm bảo ảnh ở độ phân giải chuẩn 1600x900
    h, w = screen.shape[:2]
    if (h, w) != (900, 1600):
        screen = cv2.resize(screen, (1600, 900), interpolation=cv2.INTER_AREA)

    # Vùng chứa các hòn đảo bay trên màn hình 1600x900 (nửa bên phải)
    roi_x1, roi_y1, roi_x2, roi_y2 = 680, 80, 1480, 780
    roi = screen[roi_y1:roi_y2, roi_x1:roi_x2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # Tìm các cụm màu rực của icon nằm trong bong bóng đảo (Kiếm đỏ, Lửa cam, Dấu hỏi xanh, Tím...)
    # Độ bão hòa S > 110 và Độ sáng V > 120 trên nền bong bóng tối
    icon_mask = ((hsv[:, :, 1] > 110) & (hsv[:, :, 2] > 120)).astype(np.uint8) * 255

    # Gom cụm các nét vẽ của cùng 1 icon lại với nhau
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    closed = cv2.morphologyEx(icon_mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 250 < area < 20000:  # Kích thước hợp lý của 1 icon/banner trên đảo
            M = cv2.moments(cnt)
            if M["m00"] > 0:
                cx = roi_x1 + int(M["m10"] / M["m00"])
                cy = roi_y1 + int(M["m01"] / M["m00"])
                # Nhắm trực tiếp vào tâm icon/banner trên đảo
                candidates.append((cx, cy + 10, area))

    # Sắp xếp theo chiều dọc Y tăng dần (Từ Trên -> Dưới)
    candidates.sort(key=lambda pt: pt[1])

    # Khử các điểm quá gần nhau theo trục Y (< 90px)
    filtered: List[Tuple[int, int]] = []
    for pt in candidates:
        if not filtered or abs(pt[1] - filtered[-1][1]) >= 90:
            filtered.append((pt[0], pt[1]))

    result: Dict[IslandChoice, Tuple[int, int]] = {}
    if not filtered:
        return result

    # Nếu có danh sách expected_choices từ minimap
    if expected_choices:
        order = [IslandChoice.TOP, IslandChoice.MIDDLE, IslandChoice.BOTTOM]
        sorted_choices = [c for c in order if c in expected_choices]

        # Trường hợp chỉ có 1 đảo duy nhất: gán tọa độ đảo phù hợp nhất cho lựa chọn đó
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
            # Khớp theo phân vùng Y nếu phát hiện thừa điểm nhiễu
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

    # Fallback tự suy luận theo số lượng điểm phát hiện được
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

