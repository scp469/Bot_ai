"""
czn_bot.chaos2.config - Toàn bộ hằng số, ngưỡng, tọa độ đo trên ảnh thật 1600x900.
Không hardcode số ma thuật trong logic.
"""

from typing import Dict, List, Tuple

# ── 1. Kích thước màn hình & hạ tầng ──────────────────────────────────────────
SCREEN_WIDTH: int = 1600
SCREEN_HEIGHT: int = 900
DEBUG_CAPTURES_DIR: str = "debug_captures"

# ── 2. Độ ổn định khung hình (Single Source of Truth) ─────────────────────────
# K khung hình đồng nhất liên tiếp trước khi dispatch Action
K_FRAMES_DEFAULT: int = 2
K_FRAMES_MAP: int = 3       # Mũi tên và cờ đảo nhấp nháy cần 3 frame
K_FRAMES_DIALOG: int = 2
K_FRAMES_OBTAIN: int = 2
K_FRAMES_EQUIPMENT: int = 2
K_FRAMES_SETTLEMENT: int = 2
K_FRAMES_REMOVE: int = 2
K_FRAMES_EPIPHANY: int = 2

# ── 3. Giới hạn số lần thử & Timeout an toàn (Safe Stop) ───────────────────────
MAX_ACTION_RETRIES: int = 3         # Quá 3 lần không đạt expected_next -> Safe Stop
MAX_UNKNOWN_FRAMES: int = 5         # Quá 5 frame UNKNOWN liên tiếp -> Safe Stop
DEFAULT_ACTION_TIMEOUT: float = 5.0 # Thời gian chờ verify sau tap (giây)
DEFAULT_DRY_RUN: bool = False       # Chế độ chạy thử không gửi tap

# ── 3.1 Cấu hình bảo vệ hành động không hoàn tác & kết thúc lượt ──────────────
ALLOW_LEAVE: bool = False           # Mặc định False: kết thúc cả lượt chạy, chỉ log "sẵn sàng Leave"
IRREVERSIBLE_MODE: str = "log_only" # "log_only" | "auto" (Mặc định log_only: không phát tap cho hành động irreversible)
IRREVERSIBLE_ALLOW: List[str] = []  # Danh sách tên hành động được phép tap thật ngay cả khi log_only
IRREVERSIBLE_MAX_CAPTURES_PER_MIN: int = 5 # Giới hạn lưu ảnh tối đa 5 ảnh / phút để tránh spam disk

# Danh mục từ khóa OCR tiếng Anh (English UI)
OCR_KEYWORDS: Dict[str, List[str]] = {
    "obtain": ["Obtain", "BATTLE END"],
    "settlement": ["Settlement", "Continue", "Temporary Return", "Leave"],
    "safe_zone": ["Available Safe Zone Interactions", "Rest", "Skip"],
    "fate": ["Choose Fate", "Confirm"],
    "duplicate": ["Select a card to Duplicate.", "Skip"],
    "epiphany": ["Choose Epiphany Effect.", "View original"],
    "remove_card": ["Select 1 card(s) to Remove.", "Remove", "Cancel"],
    "copy_complete": ["Copy Card Complete", "Tap to close the window"],
}

# ── 4. Tọa độ & Vùng cấm theo màn hình (ĐO TRỰC TIẾP TRÊN FIXTURE 1600x900) ───

# 4.1 EQUIPMENT
ROW_Y_RANGES: List[Tuple[int, int]] = [(170, 370), (370, 570), (570, 770)]
ROW_ORANGE_BORDER_X: Tuple[int, int] = (972, 1015)
ROW_ORANGE_CONNECTOR_X: Tuple[int, int] = (885, 972)
# Nút Confirm cam: bbox (1275, 803, 1578, 872), tâm (1426, 837)
COORD_EQUIP_CONFIRM: Tuple[int, int] = (1426, 837)
ZONE_EQUIP_CONFIRM: Tuple[int, int, int, int] = (1275, 803, 1578, 872)
# NÚT NGUY HIỂM: Extract đỏ - bbox (912, 804, 1261, 871) -> CẤM TUYỆT ĐỐI TAP
ZONE_EQUIP_EXTRACT: Tuple[int, int, int, int] = (912, 804, 1261, 871)
# Vùng chữ "Select combatant." (1365, 105, 210, 33)
ROI_EQUIP_SELECT_COMBATANT: Tuple[int, int, int, int] = (1365, 105, 210, 35)

# 4.2 OBTAIN REWARD (Sau trận)
# Nút Obtain cam: bbox (1275, 791, 1578, 859), tâm (1426, 825)
COORD_OBTAIN_BUTTON: Tuple[int, int] = (1426, 825)
ZONE_OBTAIN_BUTTON: Tuple[int, int, int, int] = (1275, 791, 1578, 859)
# Nút Skip trắng: bbox (945, 791, 1247, 858) -> CẤM TAP (bỏ qua trang bị/duplicate)
ZONE_OBTAIN_SKIP: Tuple[int, int, int, int] = (945, 791, 1247, 858)
# Vùng đọc số đếm trên nút Obtain (3/2/1) bằng OCR: (1495, 795, 90, 65)
CROP_OBTAIN_COUNT: Tuple[int, int, int, int] = (1495, 795, 90, 65)

# 4.3 SETTLEMENT
# Nút Continue cam: bbox (1263, 785, 1581, 866), tâm (1426, 825)
COORD_SETTLEMENT_CONTINUE: Tuple[int, int] = (1426, 825)
ZONE_SETTLEMENT_CONTINUE: Tuple[int, int, int, int] = (1263, 785, 1581, 866)
# NÚT NGUY HIỂM: Temporary Return (824, 792, 1126, 858) -> CẤM TAP
ZONE_SETTLEMENT_TEMP_RETURN: Tuple[int, int, int, int] = (824, 792, 1126, 858)
# NÚT NGUY HIỂM: Obtain Voucher (1272, 318, 1572, 378) -> CẤM TAP
ZONE_SETTLEMENT_VOUCHER: Tuple[int, int, int, int] = (1272, 318, 1572, 378)
# Tiêu đề Settlement: (800, 30, 280, 80)
ROI_SETTLEMENT_TITLE: Tuple[int, int, int, int] = (800, 30, 280, 80)
# Nút Leave bbox (824, 790, 1126, 860)
ZONE_SETTLEMENT_LEAVE: Tuple[int, int, int, int] = (824, 790, 1126, 860)

# 4.4 MODAL DIALOG 2 NÚT (Rest, Loot Certification)
AUTO_CONFIRM_LOOT_DIALOG: bool = True
DIALOG_SEARCH_ROI: Tuple[int, int, int, int] = (800, 500, 500, 200) # (x, y, w, h)
DIALOG_HSV_ORANGE_LOWER: Tuple[int, int, int] = (5, 120, 120)
DIALOG_HSV_ORANGE_UPPER: Tuple[int, int, int] = (25, 255, 255)
# Checkbox "Do not show until next login" -> KHÔNG TICK
ZONE_DIALOG_CHECKBOX: Tuple[int, int, int, int] = (300, 450, 750, 550)

# 4.5 SELECT DUPLICATE CARD
# Tiêu đề: (600, 85, 450, 70)
ROI_DUPLICATE_TITLE: Tuple[int, int, int, int] = (600, 85, 450, 70)
# Nút Skip bên phải: bbox (1267, 805, 1568, 870) -> CẤM TAP
ZONE_DUPLICATE_SKIP: Tuple[int, int, int, int] = (1267, 805, 1568, 870)

# 4.6 CHOOSE FATE
# 3 thẻ buff: tâm x ≈ [407, 800, 1192], y ≈ 400
FATE_CARD_CENTERS: List[Tuple[int, int]] = [(407, 400), (800, 400), (1192, 400)]
# Nút Confirm cam: (1275, 803, 1578, 872), tâm (1426, 837)
COORD_FATE_CONFIRM: Tuple[int, int] = (1426, 837)
ZONE_FATE_CONFIRM: Tuple[int, int, int, int] = (1275, 803, 1578, 872)
# Nút tròn ▶ cạnh Confirm: (1185, 803, 1255, 872) -> CẤM TAP
ZONE_FATE_ROUND_PLAY: Tuple[int, int, int, int] = (1185, 803, 1255, 872)

# 4.7 EVENT
# Lựa chọn ở dưới màn hình: tâm x ≈ [375, 765, 1215], y ≈ 765
EVENT_3CHOICES_CENTERS: List[Tuple[int, int]] = [(375, 765), (795, 765), (1215, 765)]
EVENT_WAYPOINT_CENTER: Tuple[int, int] = (795, 765)
# Nút tròn kiếm góc dưới phải (1460, 725, 1570, 835), tâm (1515, 780): CẤM TAP MẶC ĐỊNH
ZONE_EVENT_ROUND_SWORD: Tuple[int, int, int, int] = (1460, 725, 1570, 835)

# 4.8 SAFE ZONE
COORD_SAFE_ZONE_REST: Tuple[int, int] = (380, 680)
COORD_SAFE_ZONE_SKIP: Tuple[int, int] = (1426, 825)
ZONE_SAFE_ZONE_SHOP: Tuple[int, int, int, int] = (600, 200, 1000, 550)       # CẤM TAP SHOP
ZONE_SAFE_ZONE_TRAINING: Tuple[int, int, int, int] = (1050, 100, 1450, 450)   # CẤM TAP TRAINING

# 4.9 MAP
# Tọa độ tap an toàn vào thân đảo (3 làn)
MAP_LANE_SAFE_TAPS: Dict[int, Tuple[int, int]] = {
    0: (1070, 200),  # Làn trên (Top)
    1: (1290, 475),  # Làn giữa (Mid)
    2: (1090, 730),  # Làn dưới (Bot)
}
# Vùng kiểm tra mũi tên cyan (▶)
MAP_ARROW_ROIS: Dict[int, Tuple[int, int, int, int]] = {
    0: (770, 185, 60, 60),
    1: (995, 450, 60, 60),
    2: (770, 715, 60, 60),
}
# Vùng cờ từng làn (trên: 1150-1260, 65-200; giữa: 1390-1490, 316-460; dưới: 1150-1260, 585-735)
MAP_FLAG_ROIS: Dict[int, Tuple[int, int, int, int]] = {
    0: (1150, 65, 110, 135),
    1: (1390, 316, 100, 144),
    2: (1150, 585, 110, 150),
}
# Bounding box đảo 3D tổng quát (680, 80, 1480, 780): CẤM TAP NGOÀI CHAOS_MAP
ZONE_MAP_3D_ISLANDS: Tuple[int, int, int, int] = (680, 80, 1480, 780)

# 4.10 EPIPHANY & REMOVE CARD
ZONE_EPIPHANY_VIEW_ORIGINAL: Tuple[int, int, int, int] = (1340, 92, 1570, 146) # CẤM TAP
ZONE_REMOVE_CANCEL: Tuple[int, int, int, int] = (50, 790, 360, 870)
ZONE_REMOVE_EXECUTE: Tuple[int, int, int, int] = (1240, 790, 1560, 870)
