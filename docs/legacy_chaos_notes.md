# Legacy Chaos Architecture & Domain Knowledge Reference

> **Mục đích tài liệu:** Lưu trữ toàn bộ tri thức nghiệp vụ, luật chơi, cấu trúc dữ liệu JSON (Card/Event/Equipment/Presets), công thức đánh giá Deck và thuật toán tìm đường (Pathfinder) từ mã nguồn Chaos cũ (`src/czn_bot/chaos/` và `src/czn_bot/flows/chaos.py`) trước khi dọn dẹp mã nguồn cũ để tái thiết lập trong `chaos2`.

---

## 1. Cấu trúc và Schema các file Quy tắc (Rules & Presets)

Tất cả các file cấu hình nằm trong `data/rules/` và `data/presets/`.

### 1.1. `data/rules/card_rules.json`
- **Mục đích:** Danh mục toàn bộ thẻ bài (403+ thẻ) cùng trọng số từ khóa và danh sách ưu tiên chung.
- **Schema:**
  ```json
  {
    "version": "1.0",
    "description": "Bảng quy tắc ưu tiên lựa chọn thẻ bài Chaos",
    "cards": [
      {
        "id": "rossweisse_amp_therapy_elasticity",
        "name": "Amp Therapy",
        "character": "Rossweisse",
        "variant": "Elasticity",
        "description": "...",
        "priority": 90,
        "template_path": "templates/cards/amp_therapy_elasticity.png"
      }
    ],
    "priority_list": [
      {"card_name": "Amp Therapy", "preferred_variant": "Elasticity", "priority": 1},
      {"card_name": "Focus", "preferred_variant": "", "priority": 2},
      {"card_name": "Passion", "preferred_variant": "", "priority": 3},
      {"card_name": "Possession", "preferred_variant": "", "priority": 4},
      {"card_name": "Mute Accent", "preferred_variant": "Skill", "priority": 5}
    ],
    "keyword_weights": {
      "Elasticity": 60,
      "Extra Attack": 35,
      "Action Point": 40,
      "Morale": 25,
      "Rare": 30,
      "Heal": 45,
      "Discard": 15,
      "Base": 5
    },
    "default_pick_index": 1
  }
  ```

### 1.2. `data/rules/event_rules.json`
- **Mục đích:** Cơ sở dữ liệu sự kiện ngẫu nhiên trong Chaos (Events) và các lựa chọn (Choices).
- **Schema:**
  ```json
  {
    "version": "1.0",
    "description": "Bảng quy tắc ưu tiên xử lý sự kiện ngẫu nhiên trong Chaos",
    "priorities": {
      "fight_boss_for_gear": true,
      "take_quiz": true,
      "avoid_credit_cost": true,
      "heal_if_low_hp": true
    },
    "min_credit_reserve": 100,
    "hp_critical_threshold": 0.50,
    "events_database": [
      {
        "event_name": "Tên sự kiện",
        "choices": [
          {
            "choice_text": "Chuỗi text nhận diện OCR trên nút lựa chọn",
            "cost_credits": 0,
            "is_combat": false,
            "is_quiz": false,
            "is_heal": false,
            "outcome_summary": "Tóm tắt kết quả lựa chọn"
          }
        ]
      }
    ]
  }
  ```

### 1.3. `data/rules/equipment_rules.json`
- **Mục đích:** Danh sách trang bị (27 trang bị đầm lầy Swamp of Judgment) và xếp hạng Tier (S > A > B).
- **Schema:**
  ```json
  {
    "version": "1.0",
    "equipments": [
      {
        "name": "Tên trang bị",
        "filename": "ten_file.webp",
        "tier": "S",
        "character": "All",
        "template_path": "templates/equipment/ten_file.png",
        "description": "Hiệu ứng trang bị"
      }
    ]
  }
  ```

### 1.4. `data/presets/*.json` (Character Presets)
- **Mục đích:** Cấu hình build deck riêng cho từng nhân vật (ví dụ: `rossweisse.json`, `tiphera.json`, `nia.json`).
- **Schema:**
  ```json
  {
    "character": "Rossweisse",
    "archetype": "Elasticity DPS",
    "version": "1.0.0",
    "max_deck_size": 10,
    "core_cards": [
      {
        "card_id": "rossweisse_amp_therapy_elasticity",
        "min_copies": 1,
        "max_copies": 2,
        "priority": 90
      }
    ],
    "epiphany_targets": {
      "Amp Therapy": "rossweisse_amp_therapy_elasticity"
    },
    "removal_priority": [
      "rossweisse_standing_blade_base",
      "rossweisse_sword_slash_base"
    ]
  }
  ```

---

## 2. Công thức Đánh giá Thẻ & Deck (Deck Evaluation Engine)

### 2.1. Đánh giá lựa chọn Thức tỉnh / Epiphany
- **Công thức:**
  $$\text{Total Score} = V_{\text{preset}} + V_{\text{marginal}} - P_{\text{bloat}}$$

- **Chi tiết từng thành phần:**
  1. $V_{\text{preset}}$ (Điểm giá trị cơ bản & Preset):
     - Gốc: `priority` của thẻ (nếu > 0) hoặc mặc định `50.0`.
     - $+50.0$ nếu `card_id` hoặc tên thẻ khớp mục tiêu trong `preset.epiphany_targets`.
     - $+\text{core\_rule.priority}$ nếu thẻ nằm trong `preset.core_cards`.
  2. $V_{\text{marginal}}$ (Điểm biên tế & Ràng buộc bản sao):
     - Số lượng bản sao hiện tại $C$:
       - Nếu $C \ge \text{max\_copies}$: $-60.0$ (phạt vượt quá số lượng cần thiết).
       - Nếu $C < \text{min\_copies}$: $+20.0$ (thưởng hoàn thiện bộ bài tối thiểu).
     - Biến thể thẻ:
       - Chứa từ khóa `"Elasticity"`: $+50.0$.
       - Chứa từ khóa `"Action Point"`, `"AP"`, hoặc `"Draw"`: $+15.0$.
  3. $P_{\text{bloat}}$ (Phạt phình Deck):
     - Nếu $\text{current\_deck\_size} \ge \text{target\_deck\_size}$:
       $$P_{\text{bloat}} = (\text{current\_deck\_size} - \text{target\_deck\_size} + 1) \times 12.0$$

### 2.2. Gán Thẻ Thưởng (Card Reward) cho Nhân vật
1. **Thẻ đặc quyền nhân vật (Non-memory, có character cụ thể):** Gán trực tiếp cho nhân vật tương ứng trong đội hình nếu chưa chạm `max_copies`.
2. **Khớp Core Card trong Preset:** Kiểm tra thẻ có nằm trong `core_cards` của nhân vật nào chưa đạt `max_copies` không.
3. **Thẻ Ký Ức (Memory Card):** Ưu tiên gán cho chủ lực (main carry) nếu deck của chủ lực chưa chạm `max_deck_size`; nếu đã đầy, gán cho nhân vật có số thẻ ít nhất.
4. **Mặc định:** Gán cho nhân vật có số thẻ ít nhất để tránh phình deck.

### 2.3. Lọc & Xóa thẻ (Remove Card)
1. Quét lưới 8 thẻ hiển thị, đối chiếu với danh sách `preset.removal_priority`.
2. Nếu không có thẻ trong danh sách ưu tiên xóa, quét các thẻ khởi đầu cơ bản: `"Sword Slash"`, `"Standing Blade"`, `"Basic Attack"`, `"Basic Skill"`, `"Matter Disintegration"`, `"Barrier Deployment"`.
3. Nếu không tìm thấy bất kỳ thẻ nào cần xóa trong 8 thẻ nhìn thấy: **Bấm SKIP** an toàn để bảo toàn tài nguyên (Credits), không xóa bừa.

---

## 3. Thuật toán Tìm đường Mini-map (Pathfinder DAG)

### 3.1. Các loại Node (ChaosNodeType)
- `NORMAL` (Kiếm ⚔): Quái thường.
- `ELITE` (Mặt quỷ tím 👿): Quái tinh anh.
- `REST` (Ngọn lửa 🔥): Lửa trại / Trạm hồi máu.
- `EVENT` (?): Sự kiện ngẫu nhiên.
- `BOSS`: Điểm cuối cùng trên bản đồ.
- `OTHER`: Shop, Waypoint (0 điểm, hợp lệ).
- `UNKNOWN`: Node không nhận diện được (loại bỏ toàn bộ nhánh chứa node này).

### 3.2. Ba lựa chọn Đảo (IslandChoice)
- `IslandChoice.TOP`: Nhánh trên.
- `IslandChoice.MIDDLE`: Nhánh giữa.
- `IslandChoice.BOTTOM`: Nhánh dưới.
- Ưu tiên khi điểm bằng nhau: `TOP (3) > MIDDLE (2) > BOTTOM (1)`.

### 3.3. Quy tắc An toàn (Luật A khi HP < 60%)
- Nếu nhánh không có Tinh Anh (`ELITE`): Hợp lệ.
- Nếu `ELITE` xuất hiện trước mọi Lửa Trại (`REST`) hoặc không có `REST` nào: **Loại bỏ nhánh ngay lập tức**.
- Nếu có ít nhất một `REST` xuất hiện trước `ELITE` đầu tiên: Hợp lệ.

### 3.4. Trọng số Chiến thuật (Strategy Profiles)
| Node Type | Balanced (High HP) | Balanced (Low HP < 60%) | Safe (High HP) | Safe (Low HP < 70%) | Aggressive (High HP) | Aggressive (Low HP < 40%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **ELITE** | +3.0 | -10.0 | +0.5 | -25.0 (Cấm tuyệt đối) | +5.0 | +2.0 |
| **NORMAL** | +1.0 | 0.0 | +1.0 | -1.0 | +1.0 | 0.0 |
| **REST** | -2.0 | +5.0 | +3.0 | +8.0 | -3.0 | +4.0 |
| **EVENT** | 0.0 | +2.0 | +2.0 | +4.0 | +0.5 | +1.0 |
| **UNKNOWN** | -100.0 | -100.0 | -100.0 | -100.0 | -100.0 | -100.0 |

---

## 4. Cơ chế Truy vấn Rules (ChaosRuleManager)

1. **Khớp Thẻ bài (`match_card`):**
   - Bước 1: Khớp chính xác ID trong `cards_by_id`.
   - Bước 2: Chuẩn hóa text (bỏ dấu, hạ thường, thay `_` bằng khoảng trắng) -> Khớp tên chính xác.
   - Bước 3: Khớp chuỗi con (substring) có kiểm tra độ dài tối thiểu (>= 6 ký tự và chiếm >= 60% tên thẻ).
   - Bước 4: Khớp mờ (fuzzy match) bằng `difflib.SequenceMatcher`: Yêu cầu `ratio >= 0.85`, độ dài >= 5 ký tự và cách biệt so với thẻ đứng thứ hai >= 0.05. Nếu mơ hồ thì từ chối đoán (`return None`).
2. **Khớp Sự kiện (`match_event_choice`, `match_event_by_title`):**
   - Khớp chuỗi OCR trên nút lựa chọn với danh mục `event_choices_index`.
3. **Khớp Trang bị (`match_equipment`):**
   - Khớp theo tên chuẩn hóa, tên file (`.webp`), hoặc tên template (`.png`).

---

## 5. Danh sách Anti-Patterns & Lỗi cũ CẦN TRÁNH trong Chaos2 (DO NOT MIGRATE)

1. **Hardcoded `active_character="Rossweisse"`:** Trong flow cũ, `active_character` luôn bị gán cứng mặc định là `"Rossweisse"` dẫn tới việc tính toán deck và lựa chọn thẻ sai lệch khi người dùng chạy đội hình khác. Trong Chaos2, thông tin nhân vật phải được lấy động từ cấu hình đội hình thực tế.
2. **Chuỗi Tap Mù (Blind Tap Chains):** Flow cũ thường gửi chuỗi tap liên tiếp (ví dụ tap chọn slot rồi lập tức tap nút Confirm mà không qua vòng lặp kiểm tra trạng thái màn hình thực tế). Trong Chaos2: **Perception tách rời Action; mỗi action chỉ phát 1 tap duy nhất và buộc phải chờ verify ở frame tiếp theo**.
3. **Phân mảnh Bộ lọc Temporal / K-frame:** Bản cũ tồn tại đồng thời `_settled_frames`, `frames_since_change`, `STATE_SETTLING_FRAMES` và `min_frames=2` ở nhiều nơi gây xung đột và trễ phản hồi. Trong Chaos2: **Chỉ duy nhất `SCREEN_REGISTRY` giữ K-frame settling per-state**.
4. **Tap bừa vào vùng Đảo 3D:** Bản cũ cho phép tap fallback vào vùng đảo 3D khi tọa độ không chắc chắn. Trong Chaos2: **TapGuard từ chối mặc định nếu tọa độ không nằm trong vùng hợp lệ**.
5. **Cộng dồn điểm biến thể Epiphany bị lặp:** Bản cũ khi chấm điểm Epiphany cộng dồn nhiều lần điểm Elasticity và Priority gây thổi phồng điểm số sai thực tế.

