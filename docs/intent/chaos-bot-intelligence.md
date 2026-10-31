# Confirmed Statement of Intent: Chaos Bot Intelligence & Autonomous Overhaul

## 1. Thông tin chung (Metadata)
- **Tên dự án:** Chaos Zero Nightmare - BlueStacks Auto Bot
- **Mục tiêu:** Nâng cấp trí thông minh & Tự động hóa hoàn toàn 100% trong Chaos Mode
- **Ngày xác nhận:** 2026-10-28
- **Trạng thái:** Đã thống nhất (Confirmed)

---

## 2. Bản đặc tả ý định (Statement of Intent)

### Outcome (Mục tiêu cốt lõi)
Tự động hóa hoàn toàn 100% chế độ Chaos Mode không gián đoạn:
1. **Xóa bỏ dứt điểm các logic cũ chắp vá:** Gỡ bỏ các chuỗi tap mù tọa độ cứng, logic chặn skip hội thoại trong Chaos, và cờ dừng chờ thủ công.
2. **Tách riêng và xây dựng State `CHAOS_EQUIPMENT`:** Tự động nhận diện và chọn trang bị tối ưu dựa trên dữ liệu từ `templates/equipment_rules.json` và kho ảnh mẫu `templates/swamp_of_judgment_equipment/` (ưu tiên Tier S > A > B, gắn vào nhân vật phù hợp và xác nhận).
3. **Triệt tiêu hoàn toàn sự nhầm lẫn giữa Màn hình Trang bị và Trạm dừng chân (`CHAOS_SAFE_ZONE`):** Phân tách độc lập qua các đặc trưng template/OCR rõ ràng.
4. **Trạm dừng chân (Safe Zone / Campfire):** Luôn luôn ưu tiên chọn **Hồi máu (Rest / Heal)** dù lượng máu đang ở mức 100%, tuyệt đối không bấm bỏ qua (Skip).
5. **Chọn Thẻ bài (Epiphany / Card Reward):** Bật mặc định `auto_pick_epiphany = True`, bot tự động ra quyết định ngay bằng AI/Heuristic mà không phát chuông chờ người dùng bấm tay.
6. **Hội thoại sự kiện (`STORY_DIALOGUE`):** Tự động tua nhanh `[>>]` và Skip `[▷|]` khi chạy Chaos Mode; tự động đưa ra lựa chọn sự kiện ngẫu nhiên theo kho dữ liệu `templates/event_rules.json`.

### User (Đối tượng người dùng)
Người vận hành bot Chaos Zero Nightmare trên giả lập BlueStacks, cần bot tự vận hành trơn tru một mạch từ ải khởi đầu đến Boss cuối mà không cần can thiệp bàn tay người.

### Why now (Lý do thực hiện)
Bot hiện tại liên tục bị khựng/dừng lại ở nhiều màn hình (chọn bài bị dừng chờ, đối thoại bị kẹt không skip, kẹt ở màn hình trang bị do tap trượt tọa độ cứng, và nhận diện nhầm giữa trang bị với trạm dừng chân).

### Success Criteria (Tiêu chí thành công)
1. **Màn hình Trang bị:** Tách thành State `CHAOS_EQUIPMENT`, nhận diện và khớp chính xác 27 trang bị Swamp of Judgment, chọn trang bị điểm cao nhất (Tier S > A > B) và xác nhận thành công.
2. **Trạm dừng chân (`CHAOS_SAFE_ZONE`):** Nhận diện nút Rest (Hồi máu) tại tọa độ chuẩn/OCR và thực hiện hồi máu ngay cả khi HP = 100%, không bấm bỏ qua (Skip).
3. **Chọn thẻ bài:** Mặc định AI/Heuristic tự chọn ngay lập tức, không dừng bot hay phát chuông chờ người dùng.
4. **Sự kiện & Đối thoại:** Tua nhanh hội thoại tự động trong Chaos Mode, giải quyết triệt để logic sự kiện.
5. **Dọn dẹp code cũ:** Loại bỏ hoàn toàn các chuỗi tap tọa độ cứng và logic lỗi thời.
6. **Kiểm thử tự động:** Toàn bộ test suite unit tests tiếp tục đạt Pass 100% (Green).

### Constraints (Ràng buộc kỹ thuật)
- Giữ vững độ phân giải chuẩn 1600×900 (BGR).
- Duy trì cơ chế an toàn đa khung hình (`CONFIRM_FRAMES = 3`).
- Hoạt động 100% Offline: Heuristic Rule Engine sử dụng trực tiếp các file JSON quy tắc (card_rules.json, event_rules.json) và OCR/Template matching cục bộ, không phụ thuộc AI bên ngoài hay API Key.

### Out of Scope (Ngoại vi - Chưa làm đợt này)
- Tự động đánh bài trong trận đấu (Combat AI) thay nút Auto có sẵn của game.
- Thay đổi thuật toán nhận diện và giải đồ thị mini-map DAG 5 cột.

