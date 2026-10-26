# Statement of Intent: Chaos Mode Auto Pathfinding

## Outcome
Xây dựng chế độ mới `Mode.CHAOS` hoàn toàn độc lập với các luồng cũ (Replay, Progress):
1. **Trên bản đồ Chaos (`State.CHAOS_MAP`):**
   - Đọc thanh Máu Tổng (Team HP) ở góc trên bên trái, chia 2 ngưỡng: $\ge 60\%$ (Tấn công) và $< 60\%$ (Sinh tồn).
   - Quét đồ thị Mini-map (góc dưới trái) từ vị trí ghim 📍 tới Boss.
   - Áp dụng luật loại trừ khi Máu $< 60\%$ (Luật A): Loại ngay mọi nhánh có Quái Tinh Anh xuất hiện trước Lửa Trại.
   - Chấm điểm các nhánh hợp lệ:
     - Máu $\ge 60\%$: $\text{Điểm} = 3 \times \text{tinh\_anh} + 1 \times \text{quái\_thường} - 2 \times \text{lửa\_trại}$
     - Máu $< 60\%$: $\text{Điểm} = 5 \times \text{lửa\_trại} + 2 \times \text{sự\_kiện} - 10 \times \text{tinh\_anh}$
     *(Ô khác = 0 điểm. Đường không tới Boss bị loại. Hòa điểm ưu tiên đường ngắn hơn).*
   - Bấm vào hòn đảo (Trên / Giữa / Dưới) mở đầu cho nhánh sạch có điểm cao nhất (chỉ có 1 đảo thì bấm đảo đó).
   - Nếu hết nhánh sạch hoặc map lỗi: Dừng bot, báo động `UNKNOWN`. Nếu vào ô mở bảng chọn sự kiện: Dừng bot để người chơi tự chọn.
2. **Sau trận chiến (`State.CHAOS_AFTER_BATTLE`):**
   - Để người chơi tự bấm nhận phần thưởng `Obtain`.
   - Bot chỉ nhận diện và bấm duy nhất nút cam **`Leave`** khi xuất hiện để quay trở lại bản đồ.
3. **Kiểm chứng:** Mỗi lần chọn đường đều lưu ảnh chụp màn hình + log chi tiết (% máu, điểm các đảo, đảo được chọn).

## User
Người chơi Chaos Zero Nightmare cần bot tự động điều hướng chế độ Chaos với thuật toán định lượng rõ ràng, tối ưu tài nguyên và an toàn sinh tồn.

## Why Now
Các luồng cơ bản (Replay, Progress, hết thể lực, đóng popup) đã hoàn thiện và kiểm thử ổn định 100%. Chế độ Chaos là tính năng mở rộng độc lập.

## Success Criteria
1. Nhận diện chính xác màn hình chọn đường Chaos và đo đúng % Máu Tổng.
2. Dựng được đồ thị các nhánh từ Mini-map và áp dụng đúng 100% công thức tính điểm & luật loại trừ theo ngưỡng Máu 60%.
3. Bấm chính xác đảo có điểm cao nhất (tọa độ đảo trên, giữa, dưới).
4. Nhận diện nút `Leave` sau trận và bấm để về map. Bỏ qua màn `Obtain`.
5. An toàn: dừng lại ngay khi hết nhánh sạch, khi map không đọc được, hoặc khi gặp bảng chọn câu hỏi sự kiện.

## Constraints
- Giữ nguyên vẹn 100% code của Replay, Progress, hết thể lực, đóng popup.
- Chế độ Chaos là tính năng riêng, mặc định TẮT.
- Không can thiệp đánh bài trong trận (vẫn dùng auto game).

## Out of Scope
- Không tự chọn đáp án trong các bảng sự kiện / hội thoại phức tạp.
- Không can thiệp đánh bài trong trận.
- Không tự nhận phần thưởng ở màn `Obtain`.
