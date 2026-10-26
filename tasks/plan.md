# Implementation Plan: Chaos Mode Auto Pathfinding

## 1. Architecture & Component Dependencies

```
[Screen Capture (1600x900)]
         │
         ├───► chaos_hp_reader.py ─────────────┐
         │     (Reads Team HP %, is_low_hp)     │
         │                                      ▼
         └───► chaos_map_reader.py ────► chaos_pathfinder.py
               (Parses Mini-map DAG,    (Applies Rule A,
                identifies branches)     scores paths, selects best island)
                                                │
                                                ▼
                                         bot_engine.py
                                         (State Dispatcher, taps island / Leave,
                                          safety stops, logging)
```

## 2. Implementation Order & Slices

### Phase 1: Pure Logic Engine (`chaos_pathfinder.py`)
- **Mục tiêu:** Xây dựng logic tìm đường, lọc theo Luật A, công thức điểm, độc lập hoàn toàn với OpenCV/ADB.
- **Thành phần:** `ChaosNode`, `ChaosEdge`, `PathResult`, hàm `evaluate_paths()`, hàm `select_best_island()`.
- **Checkpoint kiểm chứng:** Toàn bộ test case trong `tests/test_chaos_pathfinder.py` chạy qua 100%.

### Phase 2: Đo Máu Tổng (`chaos_hp_reader.py`)
- **Mục tiêu:** Đo chính xác % Máu Tổng từ thanh máu góc trên trái.
- **Thành phần:** Hàm `get_team_hp(screen)` kết hợp phân tích thanh xanh và text số `current/max`.
- **Checkpoint kiểm chứng:** `test_chaos_hp.py` xác nhận đúng 100% trên ảnh thật người dùng gửi (`1222/1222` = 1.0).

### Phase 3: Bóc tách Mini-map & Cắt Template (`chaos_map_reader.py`)
- **Mục tiêu:** Trích xuất các template chuẩn từ ảnh chụp thực tế và viết bộ giải mã đồ thị Mini-map.
- **Thành phần:**
  - Các template: `chaos_node_sword.png`, `chaos_node_fire.png`, `chaos_node_event.png`, `chaos_node_elite.png`, `chaos_node_boss.png`, `chaos_node_pin.png`, `chaos_leave_button.png`.
  - Bộ đọc vị trí ghim 📍 và dựng danh sách các nhánh/cột.
- **Checkpoint kiểm chứng:** Đọc được cấu trúc các nhánh từ 3 ảnh thực tế mà người dùng cung cấp.

### Phase 4: Tích hợp Engine & State Machine (`bot_engine.py`, `detector.py`, `config.py`, `gui.py`)
- **Mục tiêu:** Đấu nối vào hệ thống bot hiện tại mà không ảnh hưởng bất kỳ luồng cũ nào.
- **Thành phần:**
  - `config.py`: Enum `Mode.CHAOS`, `State.CHAOS_MAP`, `State.CHAOS_AFTER_BATTLE`, tọa độ chạm đảo và nút Leave.
  - `detector.py`: Nhận diện `CHAOS_MAP` và `CHAOS_AFTER_BATTLE`.
  - `bot_engine.py`: Xử lý hành động bấm đảo, bấm Leave, dừng an toàn, ghi log.
  - `gui.py`: Thêm nút chọn chế độ Chaos.
- **Checkpoint kiểm chứng:** Chạy thử bot trong chế độ Chaos trên giả lập hoặc với ảnh mô phỏng.

---

## 3. Rủi ro & Giải pháp phòng ngừa (Risks & Mitigations)

| Rủi ro | Mức độ | Giải pháp phòng ngừa |
| :--- | :---: | :--- |
| **Ảnh hưởng tới luồng cũ (Replay/Progress)** | Cao | Tách biệt tuyệt đối bằng kiểm tra `self.mode == Mode.CHAOS`. Nếu không phải mode Chaos, 100% code mới không bao giờ được gọi. |
| **Mini-map bị che hoặc icon không rõ** | Trung bình | Luật an toàn: Nhánh nào có ô không nhận diện được ➔ Hủy nhánh đó. Nếu không còn nhánh sạch ➔ Coi là `UNKNOWN`, dừng bot và báo động. |
| **Hiện bảng câu hỏi sự kiện / lửa trại** | Trung bình | Khi rơi vào bảng sự kiện, detector sẽ không thấy map hay đảo ➔ Nhận diện `UNKNOWN` ➔ Giữ nguyên màn hình, dừng bot để người chơi chọn. |
| **Game cập nhật tọa độ hoặc số máu đổi** | Thấp | Kết hợp cả 2 phương pháp đo máu (thanh xanh và text số); tính tỷ lệ % tương đối thay vì giá trị cố định. |
