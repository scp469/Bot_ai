# Spec: Chaos Mode Auto Pathfinding

## 1. Objective
Xây dựng tính năng tự động tìm và chọn đường đi thông minh trong chế độ **Chaos** của game *Chaos Zero Nightmare* trên độ phân giải cố định 1600x900 (BlueStacks):
- Tự động đo % Máu Tổng (Team HP) tại thời điểm chọn đường.
- Phân tích bản đồ nhánh (Mini-map ở góc dưới trái) thành đồ thị có hướng (DAG - Directed Acyclic Graph) từ vị trí hiện tại (📍) đến Boss.
- Áp dụng bộ luật an toàn sinh tồn khi Máu $< 60\%$ (Luật A) và chấm điểm tối ưu lộ trình cho từng hòn đảo khả dụng.
- Tự động chạm vào hòn đảo (Trên / Giữa / Dưới) có điểm số lộ trình cao nhất.
- Sau mỗi trận chiến trong Chaos, tự động phát hiện nút cam **`Leave`** để quay lại bản đồ chọn đường (bỏ qua màn `Obtain` để người chơi tự thao tác).
- Dừng an toàn (UNKNOWN) khi phát hiện bảng câu hỏi sự kiện hoặc khi không có nhánh nào sạch/hợp lệ.

---

## 2. Capability Map & Modules

| Module ID | Trách nhiệm | Phụ thuộc | File dự kiến |
| :--- | :--- | :--- | :--- |
| `chaos-hp` | Đọc Máu Tổng từ thanh máu góc trên trái (kết hợp đo tỷ lệ vạch xanh và OCR/text số `current/max`). Trả về `% HP` và cờ `is_low_hp (< 60%)`. | — | `chaos_hp_reader.py` |
| `chaos-map-parser` | Nhận diện vị trí ghim 📍, tọa độ các cột, so khớp template các icon ô (quái thường, tinh anh, lửa trại, sự kiện, boss...) và dựng đồ thị DAG. | — | `chaos_map_reader.py` |
| `chaos-pathfinder` | Tìm tất cả các đường đi hợp lệ từ 📍 tới Boss, áp dụng Luật A lọc nhánh nguy hiểm khi Máu $< 60\%$, tính điểm theo công thức và xếp hạng các đảo mở đầu (Trên, Giữa, Dưới). | `chaos-map-parser`, `chaos-hp` | `chaos_pathfinder.py` |
| `chaos-engine` | Tích hợp State Machine (`State.CHAOS_MAP`, `State.CHAOS_AFTER_BATTLE`), tọa độ chạm đảo, nhận diện nút `Leave`, ghi log và chụp ảnh kiểm chứng. | `chaos-pathfinder`, `bot_engine`, `detector` | `bot_engine.py`, `detector.py`, `config.py` |

---

## 3. Detailed Technical Design

### 3.1. Phân vùng tọa độ (Resolution: 1600x900)
- **Vùng Máu Tổng (Team HP Bar):**
  - Tọa độ thanh máu: `X: 34 ~ 642, Y: 32 ~ 38` (chiều cao 6px, chiều rộng 608px).
  - Nhận diện: Đo tỷ lệ pixel màu xanh lá cây theo không gian màu HSV (Hue `35 ~ 85`, Saturation `≥ 70`).
  - Trả về `% HP` từ `0.0` đến `1.0` và cờ `is_low_hp = (hp_percent < 0.60)`.
  - Cơ chế an toàn (Fail-Safe): Khi gặp lỗi hoặc không đọc được ảnh, tự động fallback về `(0.0, True)` (Chế độ Sinh tồn) để bảo vệ đội hình.
- **Vùng Mini-map (Góc dưới trái):**
  - Tọa độ: `X: 20 ~ 660, Y: 570 ~ 890` (kích thước 640 × 320 px).
  - Vị trí biểu tượng Ghim 📍 vị trí hiện tại: tìm trong vùng `X: 10 ~ 120, Y: 0 ~ 300` của minimap.
  - Lưới 5 cột phân tích đường nhánh: `GRID_COLS = [155, 250, 345, 440, 535]`.
  - Tọa độ 5 hàng ô nhánh: `GRID_ROWS = [30, 85, 140, 198, 254]`.
  - Icon Boss đích: `(610, 20)` trên minimap crop.
  - Phân loại icon:
    - Quái thường (NORMAL): Kiếm bắt chéo hồng/đỏ tím (`135 ≤ H ≤ 175, S > 70`).
    - Lửa trại (REST): Ngọn lửa cam (`10 ≤ H ≤ 55, S > 70`).
    - Sự kiện (EVENT): Dấu hỏi xanh cyan (`105 ≤ H ≤ 135, S > 70`).
    - Quái tinh anh (ELITE): Mặt quỷ có sừng tím (`120 ≤ H ≤ 150, S > 50, V < 130`).
    - Ô phụ khác (OTHER): Waypoint, Shop (`70 ≤ H ≤ 105, S ≤ 115, V ≥ 90`).
    - Ô lạ không nhận diện được: Gán `UNKNOWN` để kích hoạt dừng an toàn.
  - Dựng đường nối (Edges): Lấy mẫu đa điểm (25%, 50%, 75% chiều dài) để chống nhận diện nhầm khi các đường chéo giao cắt nhau.
- **Vùng các hòn đảo bên phải (Interactive 3D Islands):**
  - Màn hình 3 đảo:
    - Đảo Trên (Top): `(1150, 240)`
    - Đảo Giữa (Middle): `(1280, 520)`
    - Đảo Dưới (Bottom): `(1100, 800)`
  - Màn hình 2 đảo:
    - Đảo Trên (Top): `(1250, 240)`
    - Đảo Dưới (Bottom): `(1330, 420)`
  - Màn hình 1 đảo:
    - Đảo Giữa (Middle): `(1280, 520)`
- **Nút Leave sau trận chiến:**
  - Vùng tìm kiếm: `X: 1250 ~ 1600, Y: 750 ~ 900`.
  - Tọa độ chạm mặc định: `(1426, 828)`.
  - Nhận diện: Template `chaos_leave_button.png` (ngưỡng khớp ≥ `0.80`).

### 3.2. Thuật toán Lọc nhánh & Chấm điểm (Scoring Algorithm)

#### Bước 1: Lọc nhánh khi Máu $< 60\%$ (Luật A)
Cho mỗi đường đi $P = [N_1, N_2, \dots, N_k]$ bắt đầu từ đảo ứng viên tới Boss:
1. Nếu trên $P$ **không có** ô Quái Tinh Anh ➔ **Hợp lệ**.
2. Nếu trên $P$ có Quái Tinh Anh:
   - Tìm vị trí xuất hiện đầu tiên của Tinh Anh ($idx_{elite}$) và vị trí xuất hiện đầu tiên của Lửa Trại ($idx_{rest}$).
   - Nếu không có Lửa Trại HOẶC $idx_{elite} < idx_{rest}$ (Tinh Anh xuất hiện trước Lửa Trại) ➔ **LOẠI BỎ NGAY LẬP TỨC**.
   - Nếu $idx_{rest} < idx_{elite}$ (Có ít nhất một Lửa Trại xuất hiện trước Tinh Anh đầu tiên) ➔ **Hợp lệ**.
   *(Lưu ý: Ô Sự Kiện không thay thế cho Lửa Trại. Quái thường không bị cấm).*

#### Bước 2: Công thức tính điểm cho nhánh hợp lệ
- **Trường hợp Máu $\ge 60\%$ (Tấn công):**
  $$\text{Score}(P) = 3 \times N_{elite} + 1 \times N_{normal} - 2 \times N_{rest} + 0 \times N_{other}$$
- **Trường hợp Máu $< 60\%$ (Sinh tồn):**
  $$\text{Score}(P) = 5 \times N_{rest} + 2 \times N_{event} - 10 \times N_{elite} + 0 \times N_{normal} + 0 \times N_{other}$$

#### Bước 3: Đánh giá điểm của từng Đảo & Phân xử hòa
- Điểm của một Đảo (Trên, Giữa, Dưới) = $\max_{P \in \text{Paths}(\text{Đảo})} \text{Score}(P)$.
- Nếu tất cả các đường xuất phát từ một đảo đều bị loại hoặc chứa ô không nhận diện được ➔ Đảo đó bị loại.
- **Phân xử hòa điểm (Tie-breaker):**
  - Nếu 2 đảo có điểm bằng nhau, ưu tiên đảo có đường đi ngắn hơn tới Boss (ít bước hơn).
  - Nếu độ dài bằng nhau, ưu tiên đảo Trên > Giữa > Dưới (thứ tự cố định).
- **Ràng buộc duy nhất 1 đảo:** Nếu chỉ có 1 đảo khả dụng (đường độc đạo) ➔ Chọn bấm đảo đó.
- **Dừng an toàn (Safety Stop):** Nếu toàn bộ các đảo đều bị loại hoặc Mini-map không phân tích được ➔ Chuyển trạng thái `UNKNOWN`, phát chuông cảnh báo, lưu ảnh và dừng bot.

---

## 4. Commands
```bash
# Chạy GUI:
python main.py

# Chạy CLI chế độ Chaos:
python main.py --cli --mode chaos

# Chạy test suite unit test cho module tìm đường:
python -m unittest tests/test_chaos_pathfinder.py
```

---

## 5. Project Structure
```
d:\new app/
├── config.py                 # Thêm Mode.CHAOS, State.CHAOS_MAP, State.CHAOS_AFTER_BATTLE
├── detector.py               # Thêm detector cho Chaos Map và nút Leave
├── bot_engine.py             # Thêm dispatcher cho State.CHAOS_MAP & CHAOS_AFTER_BATTLE
├── chaos_hp_reader.py        # Module đọc Máu Tổng
├── chaos_map_reader.py       # Module bóc tách đồ thị Mini-map
├── chaos_pathfinder.py       # Module giải thuật DAG và chấm điểm
├── tests/
│   ├── test_chaos_pathfinder.py  # Unit test giải thuật điểm & Luật A
│   └── test_chaos_hp.py          # Unit test đọc máu
├── templates/
│   ├── chaos_leave_button.png    # Template nút Leave
│   ├── chaos_node_sword.png      # Template icon Quái thường
│   ├── chaos_node_fire.png       # Template icon Lửa trại
│   ├── chaos_node_event.png      # Template icon Sự kiện (?)
│   ├── chaos_node_elite.png      # Template icon Tinh anh
│   └── chaos_node_pin.png        # Template icon Ghim vị trí 📍
├── docs/
│   ├── intent/
│   │   └── chaos-pathfinding.md  # Statement of Intent đã xác nhận
│   └── specs/
│       └── SPEC-chaos-pathfinding.md # Tài liệu Spec này
```

---

## 6. Code Style & Architecture
- **Ngôn ngữ:** Python 3.8+ (khớp với môi trường Python 3.14 hiện tại).
- **Kiến trúc:** Functional / Pure logic cho `chaos_pathfinder.py` (dễ dàng viết unit test không cần phụ thuộc ADB/màn hình thực tế).
- **Data Model:** Dùng `dataclass` cho `ChaosNode`, `ChaosEdge`, `PathResult`.
- **An toàn ngoại lệ:** Mọi thao tác xử lý ảnh OpenCV đều có bọc `try/except`, trả về kết quả rỗng thay vì làm sập tiến trình bot.

---

## 7. Testing Strategy
1. **Unit Test Thuật toán (`tests/test_chaos_pathfinder.py`):**
   - Test ca Máu $\ge 60\%$: Kiểm tra công thức $3 \times E + 1 \times N - 2 \times R$.
   - Test ca Máu $< 60\%$ (Luật A):
     - Ca Tinh Anh đứng trước Lửa Trại ➔ Phải bị loại bỏ.
     - Ca Lửa Trại đứng trước Tinh Anh ➔ Phải hợp lệ và bị trừ $-10$ cho Tinh Anh.
     - Ca không có Tinh Anh ➔ Điểm cao nhất khi nhiều Lửa Trại / Sự Kiện.
   - Test phân xử hòa điểm: Ưu tiên đường ngắn tới Boss.
2. **Integration Test với Ảnh Thực Tế (`tests/test_chaos_visual.py`):**
   - Đưa 3 ảnh thực tế mà người dùng vừa cung cấp vào bộ test.
   - Kiểm tra đọc Máu: `1222 / 1222` = 100%.
   - Kiểm tra phát hiện nút `Leave` trên Hình 2.
   - Kiểm tra không nhận diện nhầm nút `Obtain` trên Hình 1.

---

## 8. Boundaries

### Always Do
- Kiểm tra tính hợp lệ của đường đi tới Boss trước khi tính điểm.
- Ghi log chi tiết mỗi lượt chọn đường: % Máu, điểm các nhánh, đảo được bấm.
- Dừng ngay lập tức (phát chuông cảnh báo, không bấm bừa) nếu phát hiện popup câu hỏi sự kiện hoặc map bị che/lỗi.

### Ask First
- Thay đổi hệ số trong công thức tính điểm.
- Thay đổi logic tự động bấm nếu sau này muốn bot tự chọn sự kiện.

### Never Do
- Tuyệt đối không can thiệp hoặc sửa đổi logic Replay / Progress cũ.
- Tuyệt đối không bấm nút `Obtain` sau trận chiến trong Chaos.
- Tuyệt đối không cho bot bấm đại khi không tìm thấy nhánh sạch nào.

---

## 9. Success Criteria (Verification Checklist)
- [ ] Chế độ `Mode.CHAOS` xuất hiện trong cấu hình và giao diện (mặc định TẮT).
- [ ] Máu $\ge 60\%$ và $< 60\%$ kích hoạt đúng 2 công thức tính điểm khác nhau.
- [ ] Luật A chặn 100% các nhánh có Tinh Anh đứng trước Lửa Trại khi yếu máu.
- [ ] Nhận diện chính xác nút `Leave` sau trận và bỏ qua `Obtain`.
- [ ] Tất cả unit tests trong `tests/` đều vượt qua (100% Pass).
- [ ] Không có bất kỳ hồi quy (regression) nào trên các chức năng cũ (Replay / Progress / Hết thể lực).
