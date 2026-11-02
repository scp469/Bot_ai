---
name: add-chaos2-screen
description: Quy trình thêm một màn hình mới vào Chaos2. Thêm một màn = một mục trong SCREEN_REGISTRY + Facts dataclass + Reader + Vùng hợp lệ/cấm + Test fixture ảnh thật. Thay thế cho add-chaos-state cũ.
disable-model-invocation: false
---

# Quy Trình Thêm Màn Hình Mới Vào Chaos2

Trong kiến trúc Chaos2, mỗi màn hình được định nghĩa tập trung và độc lập: **Perception tách rời Hành động, một Registry duy nhất, không sửa nhiều file.**

## 5 Bước Thêm Màn Hình Mới

### Bước 1: Chuẩn bị Fixture Ảnh Thật (1600x900)
1. Chụp ảnh màn hình thật từ giả lập (1600x900 BGR). Tuyệt đối không dùng ảnh giả hoặc ảnh sai tỷ lệ.
2. Lưu file vào `tests/fixtures/states/<ten_man_hinh>.png`.

### Bước 2: Đo Đạc Tọa Độ & Neo (Anchors) Trực Tiếp Trên Ảnh
1. Mở ảnh và đo trực tiếp tọa độ (x, y, w, h) của:
   - Neo dương: Tiêu đề, icon đặc trưng, nút bấm riêng biệt của màn.
   - Neo âm: Các nút bấm hoặc tiêu đề của màn hình khác có thể gây nhầm lẫn.
   - Vùng CẤM (`forbidden_tap_zones`): Các nút nguy hiểm (Extract hủy trang bị, Skip bỏ qua phần thưởng, nút thoát trận...).
   - Vùng HỢP LỆ (`valid_tap_zones`): Các vị trí dự kiến sẽ tap (thẻ lựa chọn, nút Confirm...).
2. Nếu có template ảnh mới: cắt ảnh con (nhỏ, sát biên) lưu vào `data/templates/<ten_template>.png` và đăng ký vào `TEMPLATES` trong `src/czn_bot/constants.py`.
3. Đặt tên hằng số cho toàn bộ tọa độ/ngưỡng trong `src/czn_bot/chaos2/config.py`.

### Bước 3: Định Nghĩa Facts Dataclass & Reader (Perception)
1. Trong `src/czn_bot/chaos2/perception/facts.py`:
   - Tạo dataclass `<Screen>Facts` chứa dữ kiện thuần cần thiết cho quyết định.
2. Trong `src/czn_bot/chaos2/perception/readers.py`:
   - Viết hàm thuần `read_<screen>_facts(screen: np.ndarray, ...) -> <Screen>Facts`.
3. Export trong `src/czn_bot/chaos2/perception/__init__.py`.

### Bước 4: Khai Báo Trong `SCREEN_REGISTRY`
Trong `src/czn_bot/chaos2/registry.py`, thêm một mục `ScreenDef`:
```python
"<ID_MAN_HINH>": ScreenDef(
    id="<ID_MAN_HINH>",
    name="Tên mô tả màn hình",
    positive_layouts=(
        # Các biến thể layout nếu màn hình có nhiều dạng hiển thị
        (AnchorDef("<template_key>", (x, y, w, h), threshold=0.75, weight=1.0),),
    ),
    negative_anchors=(
        AnchorDef("<template_khac>", (x, y, w, h), threshold=0.65, negative=True),
    ),
    k_frames=2, # Số frame đồng nhất cần thiết trước khi cho phép tap
    handler=None, # Gán hàm handler khi đã sẵn sàng
    valid_tap_zones=(
        Zone(x1, y1, x2, y2, "Tên nút hợp lệ"),
    ),
    forbidden_tap_zones=(
        Zone(x1, y1, x2, y2, "Nút CẤM NGUY HIỂM"),
    ),
    allowed_next_states={"<STATE_TIEP_THEO_1>", "<STATE_TIEP_THEO_2>"},
),
```

### Bước 5: Khóa Kiểm Thử Với Test Fixture
1. Mở `tests/test_chaos2_harness.py`:
   - Thêm `<ten_man_hinh>.png: "<ID_MAN_HINH>"` vào từ điển `expected_states`.
2. Chạy test harness:
   ```bash
   python -m pytest tests/test_chaos2_harness.py -v -s
   ```
3. Đảm bảo:
   - State mới nhận diện đúng 100% với confidence >= 0.75 và margin rõ ràng.
   - Không gây false positive (nhận nhầm) sang bất kỳ fixture nào khác trong 21 fixtures hiện tại.

