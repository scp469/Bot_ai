# Chaos Zero Nightmare - BlueStacks Cyber Auto Bot

Bot tự động hóa thông minh thế hệ mới cho game **Chaos Zero Nightmare** trên giả lập BlueStacks qua ADB, hỗ trợ cả giao diện đồ họa Cyberpunk hiện đại (GUI), dòng lệnh (CLI), và chế độ giả lập kiểm thử offline (`--simulate`).

---

## 🚀 Tính năng chính

### 1. Nhận diện trạng thái thị giác chuẩn xác (Computer Vision & OCR)
- Hoạt động tối ưu trên độ phân giải chuẩn **1600 × 900** (BGR).
- **IN_MATCH**: Đang trong trận đấu (nhận diện qua nút kết thúc lượt) -> **Tuyệt đối không can thiệp, không tự đánh**.
- **POPUP (Effect, Draw Pile, Stage Info, Monster Info, Pause)**: Tự động phát hiện nút đóng hoặc icon 'X' và đóng bảng.
- **MATCH_DONE**: Nhận diện màn hình kết thúc ải, phân biệt nút trái (`Retry` hoặc `Next Mission`) và nút phải (`Confirm`), tự động nhận diện nút Retry bị xám khi hết thể lực (Stamina Exhausted).
- **PRE_MATCH**: Tự động bấm `Enter` ở màn Mission Info và Team Formation để vào trận nếu bật cờ tự động.
- **Thẩm định kép Hybrid OCR**: Xác nhận văn bản nút trước khi bấm, ngăn ngừa 100% tình trạng bấm nhầm màn hình chuyển cảnh.

### 2. 4 Chế độ hoạt động độc lập (Flow Architecture)
- **Đi lại màn (Replay Flow)**: Bấm `Retry` liên tục để cày màn hiện tại. Khi hoàn thành toàn bộ hoặc hết thể lực, bot sẽ tự bấm `Confirm` thoát và dừng an toàn.
- **Cày màn (Progress Flow)**: Bấm `Next Mission` để tuần tự mở khóa các màn tiếp theo. Nếu thua hoặc gặp `Retry`, tự bấm `Confirm` và dừng.
- **Cốt truyện (Story Flow)**:
  - Tự động tìm node ải đang mở trên bản đồ chương.
  - Tự động vuốt bản đồ sang phải khi node nằm ngoài tầm nhìn; chuyển chương sau 3 lượt vuốt.
  - Tự động tua nhanh toàn bộ hội thoại và đoạn cắt cảnh (`[>>]`, `[▷|]`, click-away).
  - Tự động phát hiện thất bại trong ải cốt truyện để dừng an toàn.
- **Chế độ Chaos (Chaos Flow)**:
  - Tự động đọc % Máu Tổng (Team HP) bằng thuật toán phân tích màu xanh lá cây HSV.
  - Tự động bóc tách Mini-map góc dưới trái thành đồ thị có hướng (DAG) 5 cột dẫn đến Boss.
  - **3 chiến thuật chọn đường**: Safe / Balanced / Aggressive (chọn trên GUI hoặc `--strategy`).
  - **Tự động chọn trang bị (CHAOS_EQUIPMENT)**: Nhận diện và tự động trang bị 27 vật phẩm Đầm Lầy Phán Xét theo thứ tự ưu tiên Tier S > A > B và bấm Xác nhận `(1360, 806)`.
  - **Khu an toàn Đốm Lửa (CHAOS_SAFE_ZONE)**: LUÔN LUÔN chọn Nghỉ ngơi `(425, 668)` để hồi máu cho đội hình, tuyệt đối không bấm Bỏ qua `(1415, 825)`.
  - **Tự động chọn Thẻ Khai Sáng (CHAOS_CHOOSE_EPIPHANY)**: Tự động đánh giá và chọn thẻ hoặc sự kiện tối ưu theo luật và AI, không bắt người dùng can thiệp thủ công.
  - **Tua nhanh hội thoại Chaos**: Tự động bỏ qua các đoạn hội thoại sự kiện trong chế độ Chaos.
  - Tự động bấm nút `Leave` màu cam sau trận để quay về bản đồ chọn đường.

### 3. Cơ chế an toàn cao (Fail-Safe & High Reliability)
- **Xác nhận đa khung hình (`CONFIRM_FRAMES = 3`)**: Phải khớp liên tiếp 3 khung hình cùng trạng thái mới thực hiện hành động.
- **Phát hiện kẹt thao tác (`MAX_SAME_ACTION`)**: Bấm quá số lần quy định không đổi màn → phát chuông cảnh báo và dừng bot.
- **Watchdog chống kẹt màn hình**: Tự động xuất ảnh chụp và file JSON chẩn đoán khi bị đứng màn quá `STALL_TIMEOUT`.
- **Recovery tự động**: Khi gặp trạng thái UNKNOWN, thử đóng popup / tọa độ phụ / gửi phím Android Back trước khi dừng.
- **Kiểm soát UNKNOWN**: Lưu ảnh kiểm chứng, tự động dọn dẹp ảnh cũ vượt quá giới hạn và dừng sau 3 lần liên tiếp.
- **Kiến trúc luồng thuần túy (Pure Flow Actions)**: Các Flow chỉ trả về đối tượng `Action` mà không tự gọi ADB, cho phép test và mô phỏng 100% không cần BlueStacks.
- **Nhật ký xoay vòng** + **Stats phiên** (export JSON) + **Notifier** (Telegram / Discord / Windows Toast).

---

## 🛠 Yêu cầu môi trường

1. **BlueStacks 5**:
   - Độ phân giải: **1600 × 900** (Vào BlueStacks Settings -> Display -> 1600x900, 240 DPI).
   - Bật ADB: Vào **Settings** -> **Advanced** -> Bật **Android Debug Bridge** (cổng mặc định `5555`).
2. **Python 3.8+**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 📁 Cấu trúc Thư mục Dự án

```text
czn-bot/
├── .env.example              # Mẫu cấu hình môi trường (TELEGRAM, DISCORD, ADB)
├── .gitignore
├── requirements.txt
├── README.md
├── data/
│   ├── templates/            # Kho ảnh mẫu 1600x900 (giữ nguyên thư mục con theo nhân vật)
│   └── rules/                # card_rules.json, event_rules.json, equipment_rules.json
├── src/czn_bot/
│   ├── settings.py           # Đọc .env & ai_config.json sạch sẽ, không mã hóa tự chế
│   ├── constants.py          # 1600x900, ngưỡng match, CONFIRM_FRAMES, MAX_SAME_ACTION
│   ├── coords.py             # TAP_COORDS và các vùng tìm kiếm chuẩn
│   ├── states.py             # Enum Mode, State (CHAOS_EQUIPMENT, CHAOS_SAFE_ZONE, ...)
│   ├── device/
│   │   ├── adb.py            # ADB Client & Chaos ADB controller (tap, swipe, jitter)
│   │   └── mock.py           # Mock ADB Client phục vụ kiểm thử và giả lập offline
│   ├── vision/
│   │   ├── templates.py      # Nạp và so khớp ảnh mẫu
│   │   ├── ocr.py            # Dịch vụ OCR (Windows Media OCR / Tesseract fallback)
│   │   ├── detector.py       # Phân tích ảnh -> State & Details
│   │   ├── hp_reader.py      # Đo thanh máu đội hình bằng HSV
│   │   └── map_reader.py     # Phân tích Minimap DAG & tọa độ đảo 3D
│   ├── chaos/
│   │   ├── pathfinder.py     # Tìm đường trên DAG & Strategy Profile (Safe/Balanced/Aggressive)
│   │   ├── rules.py          # Quản lý quy tắc JSON cho Thẻ bài, Sự kiện, Trang bị
│   │   ├── decisions.py      # Nhận diện thẻ bài, sự kiện, trang bị
│   │   └── ai_brain.py       # Bộ quy tắc chiến thuật Heuristics & OCR cục bộ (100% Offline)
│   ├── flows/
│   │   ├── base.py           # Giao diện Flow & Action (ActionType: TAP, SWIPE, WAIT, STOP...)
│   │   ├── replay.py         # Chế độ đi lại màn
│   │   ├── progress.py       # Chế độ cày màn tiến trình
│   │   ├── story.py          # Chế độ cốt truyện (tua thoại, chọn node)
│   │   └── chaos.py          # Chế độ Chaos thông minh toàn diện
│   ├── runner.py             # Vòng lặp điều phối chính, xác nhận đa khung, watchdog
│   ├── recovery.py           # Phục hồi đa tầng khi gặp UNKNOWN / kẹt màn hình
│   ├── stats.py              # Bộ theo dõi thống kê phiên & xuất telemetry
│   └── notifier.py           # Thông báo Telegram / Discord / Windows Toast
├── apps/
│   ├── cli.py                # Ứng dụng dòng lệnh (CLI) & giả lập offline (--simulate)
│   └── gui.py                # Giao diện CustomTkinter Cyberpunk hiện đại
├── tests/                    # 192 bài kiểm thử tự động (100% Green)
├── tools/                    # Công cụ build EXE & đóng gói phát hành
└── docs/                     # Tài liệu thiết kế & đặc tả hệ thống
```

---

## 💻 Hướng dẫn sử dụng

### 1. Khởi chạy Giao diện Đồ họa (GUI)
```bash
python main.py
```
hoặc:
```bash
python gui.py
```
- Bấm **"Kết nối"** để kết nối ADB tới BlueStacks (đèn xanh `🟢 Đã kết nối BlueStacks`).
- Chọn chế độ mong muốn: **Đi lại màn**, **Cày màn**, **Cốt truyện**, hoặc **Chế độ Chaos**.
- Tùy chỉnh chiến thuật Chaos: An toàn (Safe) / Cân bằng (Balanced) / Tấn công (Aggressive).
- Tùy chọn **Bật Recovery khi UNKNOWN** (tự động thử gỡ kẹt trước khi dừng).
- Bấm **▶ BẮT ĐẦU BOT** / **⏹ DỪNG BOT**.
- Xem preview màn hình trực tiếp và thống kê thời gian thực trên tab Dashboard.

### 2. Khởi chạy Dòng lệnh (CLI Headless)
```bash
# Chế độ đi lại màn, tối đa 10 lượt:
python main.py --cli --mode replay --max-retries 10

# Chế độ cày màn tiếp theo:
python main.py --cli --mode progress

# Chế độ cốt truyện:
python main.py --cli --mode story

# Chế độ Chaos tìm đường tự động (mặc định Balanced):
python main.py --cli --mode chaos

# Chaos + chiến thuật An toàn + Recovery:
python main.py --cli --mode chaos --strategy safe --recovery

# Chaos + chiến thuật Tấn công:
python main.py --cli --mode chaos --strategy aggressive
```

| Tham số | Giá trị | Mô tả |
|---------|---------|--------|
| `--mode` | `replay` / `progress` / `chaos` / `story` | Chế độ bot (mặc định: replay) |
| `--strategy` | `safe` / `balanced` / `aggressive` | Chiến thuật chọn đường Chaos |
| `--max-retries` | số nguyên | Số lượt tối đa trước khi tự dừng |
| `--auto-start` | cờ | Tự động bấm Enter ở màn hình chuẩn bị |
| `--recovery` | cờ | Bật recovery tự động khi gặp UNKNOWN |

### 3. Chế độ Giả lập Offline (`--simulate`)
Kiểm thử toàn bộ logic nhận diện và bấm nút của bot trong **< 1 giây** bằng ảnh chụp tĩnh mà không cần bật BlueStacks:
```bash
# Giả lập với một ảnh chụp màn hình cụ thể:
python main.py --simulate tests/fixtures/chaos_safe_zone.png --mode chaos

# Giả lập với màn hình bản đồ cốt truyện:
python main.py --simulate tests/fixtures/story_map_screen.png --mode story
```
Kết quả các bước chạm kèm ảnh khoanh vùng trực quan sẽ được xuất vào thư mục `logs/sim_output/`.

---

## 🧪 Kiểm thử Tự động (Unit Tests)

Dự án sở hữu bộ test suite tự động toàn diện gồm **192 bài kiểm thử**:
```bash
# Chạy toàn bộ test suite:
python -m unittest discover -s tests -t .

# Chạy riêng từng module kiểm thử:
python -m unittest tests/test_flows.py
python -m unittest tests/test_bot_engine.py
python -m unittest tests/test_chaos_ai.py
python -m unittest tests/test_chaos_pathfinder.py
python -m unittest tests/test_story_mode.py
python -m unittest tests/test_ocr_service.py
```

---

## 🔔 Cấu hình Thông báo (Notifier)

Sao chép `.env.example` thành `.env` (hoặc thiết lập biến môi trường) để kích hoạt thông báo tự động:

```bash
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=987654321
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
ENABLE_WINDOWS_TOAST=true
```

Bot sẽ tự động gửi thông báo khi:
- Hết thể lực (nút Retry xám).
- Đạt số lần lặp tối đa.
- Thua trận trong cốt truyện.
- Gặp sự cố kẹt màn hình hoặc mất kết nối ADB.
- Kết thúc phiên cày kèm báo cáo thống kê đầy đủ.
