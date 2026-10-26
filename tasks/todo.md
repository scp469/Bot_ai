# Task List: Chaos Mode Auto Pathfinding

- [x] Task 1: Xây dựng Core Data Structures & Pathfinding Algorithm (`chaos_pathfinder.py`)
  - Acceptance: Cài đặt `ChaosNode`, `ChaosEdge`, `PathResult`. Lọc theo Luật A khi Máu $< 60\%$ (loại bỏ Tinh Anh đứng trước Lửa Trại). Tính điểm theo công thức cho Máu $\ge 60\%$ và Máu $< 60\%$. Phân xử hòa điểm chọn đường ngắn hơn. Chọn đảo (Trên / Giữa / Dưới) có điểm cao nhất.
  - Verify: Chạy `python -m unittest tests/test_chaos_pathfinder.py` vượt qua 100% test case.
  - Files: `chaos_pathfinder.py`, `tests/test_chaos_pathfinder.py`

- [x] Task 2: Xây dựng Module Đọc Máu Tổng (`chaos_hp_reader.py`)
  - Acceptance: Đọc vùng Máu Tổng (`X: 60~450, Y: 20~65`), tính tỷ lệ chiều dài thanh xanh lá cây (và trích xuất text số `current/max`). Trả về `% HP` (0.0 ~ 1.0) và cờ `is_low_hp = % HP < 0.60`.
  - Verify: Chạy `python -m unittest tests/test_chaos_hp.py` với ảnh thực tế 1600x900 trả về chính xác 1.0 (100%).
  - Files: `chaos_hp_reader.py`, `tests/test_chaos_hp.py`

- [x] Task 3: Trích xuất Templates & Xây dựng Bộ Giải Mã Mini-map (`chaos_map_reader.py`)
  - Acceptance: Cắt và lưu các template icon từ ảnh thực tế vào `templates/` (`chaos_node_sword.png`, `chaos_node_fire.png`, `chaos_node_event.png`, `chaos_node_elite.png`, `chaos_node_boss.png`, `chaos_node_pin.png`, `chaos_leave_button.png`). Xây dựng module nhận diện ghim 📍, nhận diện các ô trên Mini-map và xuất ra đồ thị DAG cho `chaos_pathfinder`.
  - Verify: Chạy script kiểm thử bóc tách đồ thị trên cả 2 ảnh map thực tế (ảnh 3 đảo và ảnh 1 đảo).
  - Files: `chaos_map_reader.py`, thư mục `templates/`

- [x] Task 4: Cập nhật Config & Detector cho các trạng thái Chaos (`config.py`, `detector.py`)
  - Acceptance: Thêm `Mode.CHAOS`, `State.CHAOS_MAP`, `State.CHAOS_AFTER_BATTLE`, tọa độ đảo và nút Leave vào `config.py`. Thêm nhận diện `CHAOS_MAP` và `CHAOS_AFTER_BATTLE` vào `detector.py`.
  - Verify: Test `detector.detect()` trên ảnh map và ảnh nút Leave trả về đúng State tương ứng.
  - Files: `config.py`, `detector.py`

- [x] Task 5: Tích hợp Bot Engine & GUI (`bot_engine.py`, `gui.py`, `main.py`)
  - Acceptance: Trong `bot_engine.py`, khi `self.mode == Mode.CHAOS`:
    - `State.CHAOS_MAP`: gọi đọc máu, đọc map, chọn đảo tốt nhất, lưu log + ảnh, chạm đảo.
    - `State.CHAOS_AFTER_BATTLE`: chạm nút `Leave` về map.
    - An toàn: nếu không có nhánh sạch hoặc gặp popup câu hỏi sự kiện -> dừng bot báo `UNKNOWN`.
    - Các luồng cũ Replay/Progress hoàn toàn không bị ảnh hưởng.
    - Thêm radio button "Chế độ Chaos" trên giao diện `gui.py`.
  - Verify: Chạy thử `main.py` và kiểm thử luồng hoạt động (31/31 unit & integration tests pass).
  - Files: `bot_engine.py`, `gui.py`, `main.py`

- [x] Task 6: Module OCR Dùng Chung & Thẩm Định Kép - Hybrid Verification (`ocr_service.py`, `detector.py`, `bot_engine.py`, `gui.py`)
  - Acceptance:
    - Xây dựng `ocr_service.py` với Windows Native OCR (`Windows.Media.Ocr.OcrEngine` qua WinRT) siêu tốc (~1.5ms - 15ms) và cơ chế fallback RapidOCR an toàn.
    - Cung cấp API dùng chung: `read_text`, `find_text`, `verify_button_text` với cơ chế mở rộng 2 tầng (Stage 1 crop chuẩn, Stage 2 mở rộng +25px pad).
    - Tích hợp Thẩm định kép (Hybrid Verification) vào `detector.py` và `bot_engine.py` trước khi click các nút trọng yếu (`Confirm`, `Retry`, `Next Mission`, `Enter`, `Leave`, `Skip`). Loại bỏ hoàn toàn tình trạng click nhầm thẻ hay bấm sai nút do dương tính giả.
    - Tích hợp Checkbox cấu hình "Thẩm định kép OCR" trên giao diện `gui.py`.
  - Verify: Viết bộ unit tests `tests/test_ocr_service.py` và bổ sung test cases trong `tests/test_bot_engine.py`. Toàn bộ 144/144 tests trong hệ thống chạy qua 100%.
  - [x] Task 7: Nâng cấp Giao diện Đỉnh cao với CustomTkinter (`gui.py`, `main.py`)
  - Acceptance:
    - Chuyển đổi toàn diện từ Tkinter cơ bản sang `customtkinter.CTk` với ngôn ngữ thiết kế Cyberpunk Cam & Đen (High Contrast `#ff6b00`, nền Obsidian `#0f0f13`, thẻ thẻ Card `#171720`).
    - Bố cục 4 Top Tabs trực quan (`CTkTabview`):
      1. **Bảng điều khiển (Dashboard)**: Trạng thái kết nối ADB, chọn chế độ (Replay, Progress, Chaos), chỉ số thống kê Real-time (Thời gian chạy, Số trận, Thắng/Thua, Winrate), nút START/STOP/PAUSE nổi bật.
      2. **Chế độ Chaos & Vượt Ải**: Cấu hình chiến thuật Chaos (An toàn vs Cân bằng vs Tham lam), bộ đếm Máu tổng và Đảo đã chọn, cấu hình giới hạn số trận hoặc cấp độ đích.
      3. **Màn hình Trực tiếp & Nhật ký**: Live Screen Preview 16:9 thu nhỏ theo chu kỳ vòng lặp bot (0% overhead ADB), công tắc bật/tắt Preview tiết kiệm CPU, bảng Log thời gian thực phân màu rực rỡ với nút Copy & Clear.
      4. **Cài đặt Nâng cao**: Cấu hình ADB Serial, Cấu hình Thẩm định kép OCR, Webhook Discord/Telegram với nút kiểm tra gửi thử trực tiếp (chạy thread nền non-blocking), Dọn dẹp bộ nhớ ảnh rác.
    - Duy trì khả năng tương thích 100% với `main.py` và bảo toàn toàn bộ 144 unit tests của hệ thống.
  - Verify: Chạy thử nghiệm GUI headless lifecycle test không lỗi DPI, khởi động bot mượt mà, 144/144 unit tests pass.
  - Files: `gui.py`, `main.py`
