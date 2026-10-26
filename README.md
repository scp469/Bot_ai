# Chaos Zero Nightmare - BlueStacks Auto Bot

Bot tự động hóa thông minh cho game **Chaos Zero Nightmare** trên giả lập BlueStacks qua ADB, hỗ trợ cả giao diện đồ họa (GUI) lẫn dòng lệnh (CLI) và chế độ giả lập offline (`--simulate`).

---

## 🚀 Tính năng chính

### 1. Nhận diện trạng thái chính xác (Computer Vision)
- Hoạt động trên độ phân giải chuẩn **1600 × 900** (BGR).
- **IN_MATCH**: Đang trong trận đấu (nhận diện qua nút kết thúc lượt) -> **Tuyệt đối không can thiệp, không tự đánh**.
- **POPUP (Effect, Draw Pile, Stage Info, Monster Info, Pause)**: Tự động tìm tọa độ nút đóng hoặc chữ 'X' và đóng bảng.
- **MATCH_DONE**: Nhận diện màn hình chiến thắng/thất bại, phân biệt nút trái (`Retry` hoặc `Next Mission`) và nút phải (`Confirm`), tự động nhận diện nút Retry bị xám khi hết thể lực.
- **PRE_MATCH**: Tự động bấm `Enter` ở màn Mission Info và Team Formation để vào trận nếu bật cờ tự động.

### 2. 3 Chế độ hoạt động độc lập
- **Đi lại màn (Replay)**: Bấm `Retry` liên tục để cày màn hiện tại. Khi hoàn thành toàn bộ hoặc hết thể lực, bot sẽ tự bấm `Confirm` thoát và dừng an toàn.
- **Cày màn (Progress)**: Bấm `Next Mission` để tiến sang các màn tiếp theo. Nếu thua hoặc gặp `Retry`, tự bấm `Confirm` và dừng.
- **Chế độ Chaos (Chaos Mode)**:
  - Tự động đo % Máu Tổng (Team HP) bằng thuật toán phân tích màu xanh lá cây HSV.
  - Tự động bóc tách Mini-map góc dưới trái thành đồ thị có hướng (DAG) 5 cột dẫn đến Boss.
  - **3 chiến thuật chọn đường**: Safe / Balanced / Aggressive (chọn trên GUI hoặc `--strategy`).
  - Áp dụng luật lọc nhánh theo chiến thuật (ví dụ Luật A khi máu thấp).
  - Tự động tính điểm tối ưu cho từng hòn đảo và chạm vào đảo tốt nhất.
  - Tự động bấm nút `Leave` màu cam sau trận để quay về bản đồ chọn đường.

### 3. Cơ chế an toàn cao (Fail-Safe & High Reliability)
- **Xác nhận đa khung hình (`CONFIRM_FRAMES = 3`)**: Phải khớp liên tiếp 3 khung hình cùng trạng thái mới thực hiện hành động.
- **Phát hiện kẹt thao tác (`MAX_SAME_ACTION`)**: Bấm quá số lần không đổi màn → chuông cảnh báo và dừng.
- **Recovery tự động** (tùy chọn): Khi UNKNOWN, thử đóng popup / tọa độ phụ / phím Android Back trước khi dừng.
- **Kiểm soát UNKNOWN**: Lưu ảnh kiểm chứng, dừng sau 3 lần liên tiếp.
- **Đa luồng an toàn**: Dừng tức thì qua `threading.Event`, ADB không đơ GUI.
- **Nhật ký xoay vòng** + **Stats phiên** (export JSON) + **Notifier** (Telegram / Discord / Toast).

---

## 🛠 Yêu cầu môi trường

1. **BlueStacks 5**:
   - Độ phân giải: **1600 × 900** (Vào BlueStacks Settings -> Display -> 1600x900).
   - Bật ADB: Vào **Settings** -> **Advanced** -> Bật **Android Debug Bridge** (cổng mặc định `5555`).
2. **Python 3.8+**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 💻 Cách sử dụng

### 1. Khởi chạy Giao diện Đồ họa (GUI)
```bash
python main.py
```
hoặc:
```bash
python gui.py
```
- Bấm **"Kết nối"** để kết nối ADB tới BlueStacks (đèn xanh `🟢 Đã kết nối BlueStacks`).
- Chọn chế độ: **"Đi lại màn"**, **"Cày màn"**, hoặc **"Chế độ Chaos"**.
- **Chiến thuật Chaos**: An toàn (Safe) / Cân bằng (Balanced) / Tấn công (Aggressive).
- Tùy chọn **Bật Recovery khi UNKNOWN** (tự thử đóng popup / phím Back trước khi dừng).
- Tùy chỉnh độ trễ vòng lặp và giới hạn lượt retry (nếu cần).
- Bấm **▶ BẮT ĐẦU BOT** / **⏹ DỪNG BOT**.
- Theo dõi thống kê realtime: Retry, Hành động, số đảo đã chọn, Máu TB, Điểm TB.

### 2. Khởi chạy Dòng lệnh (CLI Headless)
```bash
# Chế độ đi lại màn, tối đa 10 lượt:
python main.py --cli --mode replay --max-retries 10

# Chế độ cày màn tiếp theo:
python main.py --cli --mode progress

# Chế độ Chaos tìm đường tự động (mặc định Balanced):
python main.py --cli --mode chaos

# Chaos + chiến thuật An toàn + Recovery:
python main.py --cli --mode chaos --strategy safe --recovery

# Chaos + chiến thuật Tấn công:
python main.py --cli --mode chaos --strategy aggressive
```

| Tham số | Giá trị | Mô tả |
|---------|---------|--------|
| `--strategy` | `safe` / `balanced` / `aggressive` | Chiến thuật chọn đường Chaos (mặc định: balanced) |
| `--recovery` | flag | Bật recovery tự động khi gặp UNKNOWN |

**Ý nghĩa chiến thuật:**
- **safe**: Ưu tiên lửa trại / sự kiện, tránh Elite mạnh khi máu thấp (ngưỡng 70%).
- **balanced**: Công thức mặc định (ngưỡng 60%).
- **aggressive**: Ưu tiên Elite, chấp nhận rủi ro hơn (ngưỡng 40%).

### 3. Chế độ Giả lập Offline (`--simulate`)
Kiểm thử toàn bộ logic nhận diện và bấm nút của bot trong **< 1 giây** bằng các ảnh chụp màn hình tĩnh mà không cần bật BlueStacks:
```bash
# Giả lập với một ảnh chụp màn hình cụ thể:
python main.py --simulate tests/fixtures/chaos_map_3_islands.png --mode chaos

# Giả lập kèm strategy:
python main.py --simulate tests/fixtures/chaos_map_3_islands.png --mode chaos --strategy safe

# Giả lập với một thư mục kịch bản gồm nhiều ảnh liên tiếp:
python main.py --simulate tests/fixtures/ --mode chaos
```
Kết quả các bước chạm kèm vòng tròn đỏ kiểm chứng sẽ được xuất vào thư mục `logs/sim_output/`.

---

## 🧪 Kiểm thử Tự động (Unit Tests)

Dự án sở hữu bộ test suite tự động toàn diện kiểm tra mọi module:
```bash
# Chạy toàn bộ 34 bài kiểm thử:
python -m unittest discover tests

# Chạy riêng từng module:
python -m unittest tests/test_chaos_pathfinder.py
python -m unittest tests/test_chaos_map_reader.py
python -m unittest tests/test_chaos_hp.py
python -m unittest tests/test_chaos_detector.py
python -m unittest tests/test_chaos_integration.py
python -m unittest tests/test_mock_adb.py
```

---

## 📁 Cấu trúc Thư mục

```text
new app/
├── config.py                 # Cấu hình tọa độ, enum, template, Telegram/Discord
├── adb_client.py             # Client ADB (screencap, tap, keyevent)
├── mock_adb.py               # Giả lập ADB offline phục vụ test / simulate
├── detector.py               # Nhận diện trạng thái màn hình (template matching)
├── ocr_service.py            # Windows Media OCR & Tesseract engine
├── bot_engine.py             # State machine, điều phối, fail-safe, tích hợp module
├── chaos_state_machine.py    # State Machine tự động hóa Chaos Mode
├── chaos_ai_brain.py         # AI Quyết định (Gemini Flash & Rule Engine)
├── chaos_vision.py           # Phân tích thị giác OCR thẻ bài / sự kiện
├── chaos_ai_config.py        # Quản lý cấu hình AI, Prompt, Quy tắc JSON
├── chaos_adb.py              # ADB controller cho Chaos (tap, swipe, drag)
├── chaos_hp_reader.py        # Đọc % Máu Tổng (HSV)
├── chaos_map_reader.py       # Parse Mini-map → DAG
├── chaos_pathfinder.py       # Tìm đường + chấm điểm (hỗ trợ Strategy Profile)
├── strategy_profile.py       # Hồ sơ chiến thuật: Safe / Balanced / Aggressive
├── stats_tracker.py          # Thống kê phiên (đảo, HP, điểm, export JSON)
├── notifier.py               # Thông báo Telegram / Discord / Windows Toast
├── recovery.py               # Phục hồi tự động khi UNKNOWN
├── gui.py                    # Giao diện CustomTkinter (Tab Vòng lặp + Tab Chaos AI)
├── main.py                   # Entry: GUI / CLI / Simulate
├── card_rules.json           # Quy tắc ưu tiên thẻ bài
├── event_rules.json          # Quy tắc lựa chọn sự kiện
├── requirements.txt
├── tools/                    # Công cụ build EXE & đóng gói zip
├── templates/                # Ảnh mẫu 1600x900
├── tests/                    # Unit + integration tests
├── docs/                     # Spec & Intent
└── logs/                     # bot.log + bot_activity.log
```

### Thông báo (Notifier)

Cấu hình qua biến môi trường (không hard-code token):

```bash
set TELEGRAM_BOT_TOKEN=123456:ABC...
set TELEGRAM_CHAT_ID=987654321
set DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
set ENABLE_WINDOWS_TOAST=true
```

Bot sẽ gửi thông báo khi: hết thể lực, đạt max retry, dừng do UNKNOWN, lỗi ADB, kết thúc phiên (kèm tóm tắt stats).
