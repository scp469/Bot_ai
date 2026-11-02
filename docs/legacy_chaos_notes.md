# Legacy Chaos Architecture & Domain Knowledge Reference (Audited vs backup-full-archive)

> **Mục đích tài liệu:** Lưu trữ toàn bộ tri thức nghiệp vụ, luật chơi, cấu trúc dữ liệu JSON thực tế (`data/rules/`, `data/presets/`), công thức đánh giá Deck và thuật toán tìm đường (Pathfinder) đối chiếu trực tiếp từ nhánh `backup-full-archive` trước khi tái thiết lập trong `chaos2`.

---

## 1. Cấu trúc và Schema Thực tế các file Quy tắc (Rules & Presets)

### 1.1. `data/rules/card_rules.json` (Thực tế trong repo)
- **Top-level keys:** `version`, `game`, `updated_at`, `total_cards` (403), `characters`, `priority_tiers`, `cards`.
- **Cấu trúc mỗi card:**
  ```json
  {
    "id": "nia_stroke_base",
    "filename": "stroke_base.png",
    "character": "Nia",
    "template_path": "Nia/stroke_base.png",
    "name": "Stroke",
    "variant": "Base",
    "cost": 1,
    "cost_type": "AP",
    "type": "Basic Attack",
    "target": "single_enemy",
    "priority": 15,
    "keywords": ["Basic Attack"],
    "description": "100% Damage",
    "description_vi": "Gây 100% sát thương đơn mục tiêu",
    "condition": "filler_damage",
    "discard_priority": 1
  }
  ```
- *Lưu ý:* `keyword_weights` và `priority_list` trong code cũ là hằng số fallback nội bộ của class `ChaosRuleManager`, không nằm trong file JSON gốc.

### 1.2. `data/rules/event_rules.json` (Thực tế trong repo)
- **Top-level keys:** `events_database` (64 sự kiện), `total_events`, `updated_at`.
- **Cấu trúc mỗi event:**
  ```json
  {
    "event_name": "A Child Locked in a Room",
    "event_type": "Common / Laboratory",
    "choices": [
      {
        "choice_id": 1,
        "choice_text": "Receive the memory of longing",
        "outcome_summary": "Decrease all Combatants' Stress by 9, Apply Memory Encroachment 2",
        "priority_score": 8,
        "recommendation": "Chọn khi cần xả stress gấp cho toàn đội (-9 Stress)..."
      }
    ]
  }
  ```
- *Lưu ý:* `priorities`, `min_credit_reserve`, `hp_critical_threshold` là các giá trị mặc định được định nghĩa trong code cũ, không lưu cứng trong JSON.

### 1.3. `data/rules/equipment_rules.json` (Thực tế trong repo)
- **Top-level keys:** `version`, `game`, `updated_at`, `world`, `total_equipments` (27 trang bị Swamp of Judgment), `priority_tiers`, `equipments`.
- **Cấu trúc mỗi equipment:**
  ```json
  {
    "id": "eq_sec_010",
    "slug": "branch-of-eternity",
    "name": "Branch of Eternity",
    "filename": "branch-of-eternity.webp",
    "template_path": "swamp_of_judgment_equipment/images/branch-of-eternity.webp",
    "rarity": "Unique",
    "type": "Weapon (Vũ khí)",
    "chaos_world": "Swamp of Judgment",
    "tier": "tier_s_must_pick",
    "priority": 95,
    "condition": "has_healer",
    "trigger": "on_heal_or_recover",
    "synergy_tags": ["Heal", "Fixed Damage", "AoE", "Healer DPS"],
    "best_characters": ["Nia", "Mika", "Healers"],
    "recommendation_vi": "Cực kỳ bá đạo cho đội hình có Healer (như Nia)...",
    "discard_if": "no_healing_cards",
    "stats_5star": {"atk": 82, "def": 31, "hp": 83},
    "description_en": "On Heal or Recover through an ability, inflict Fixed Damage equal to 50% of Recover Amount to all enemies",
    "reward_tags": ["encounter"]
  }
  ```

### 1.4. `data/presets/*.json` (Character Presets)
- **Cấu trúc thực tế (ví dụ `rossweisse.json`):**
  ```json
  {
    "character": "Rossweisse",
    "archetype": "Flow_Burst",
    "version": "1.0.0",
    "core_cards": [
      {
        "card_id": "rossweisse_flicker_blade_blink",
        "min_copies": 1,
        "max_copies": 2,
        "priority": 95
      }
    ],
    "epiphany_targets": {
      "rossweisse_flicker_blade": "rossweisse_flicker_blade_blink",
      "rossweisse_sword_resonance": "rossweisse_sword_resonance_activate_all"
    },
    "removal_priority": [
      "rossweisse_sword_slash_base",
      "rossweisse_standing_blade_base"
    ],
    "max_deck_size": 8
  }
  ```

---

## 2. Công thức Đánh giá Thẻ & Deck (Deck Evaluation Engine)

### 2.1. Đánh giá lựa chọn Thức tỉnh / Epiphany
- **Công thức:**
  $$\text{Total Score} = V_{\text{preset}} + V_{\text{marginal}} - P_{\text{bloat}}$$
- **Thành phần:**
  1. $V_{\text{preset}}$:
     - Điểm gốc: `card.priority` (nếu > 0) hoặc `50.0`.
     - Khớp `epiphany_targets`: $+50.0$.
     - Khớp `core_cards`: $+\text{core\_rule.priority}$.
  2. $V_{\text{marginal}}$:
     - Số lượng bản sao $C \ge \text{max\_copies}$: $-60.0$.
     - $C < \text{min\_copies}$: $+20.0$.
     - Biến thể chứa `"Elasticity"`: $+50.0$.
     - Từ khóa hồi tài nguyên (`"Action Point"`, `"AP"`, `"Draw"`): $+15.0$.
  3. $P_{\text{bloat}}$:
     - Khi $\text{current\_deck\_size} \ge \text{target\_deck\_size}$:
       $$P_{\text{bloat}} = (\text{current\_deck\_size} - \text{target\_deck\_size} + 1) \times 12.0$$

### 2.2. Gán Thẻ Thưởng (Card Reward) cho Nhân vật
1. Thẻ đặc quyền nhân vật (Non-memory, có `character` cụ thể): Gán cho nhân vật đó nếu chưa vượt `max_copies`.
2. Khớp Core Card của nhân vật trong đội hình.
3. Thẻ Ký Ức (Memory): Ưu tiên cho carry chủ lực nếu $\text{size} < \text{max\_deck\_size}$, ngược lại gán cho nhân vật có số thẻ ít nhất.
4. Mặc định: Gán cho nhân vật có deck mỏng nhất (ít thẻ nhất) để chống phình deck.

### 2.3. Lọc & Xóa thẻ (Remove Card)
1. Quét lưới 8 thẻ hiển thị, đối chiếu với danh sách `preset.removal_priority`.
2. Nếu không có thẻ trong danh sách ưu tiên xóa, quét các thẻ khởi đầu cơ bản: `"Sword Slash"`, `"Standing Blade"`, `"Basic Attack"`, `"Basic Skill"`, `"Matter Disintegration"`, `"Barrier Deployment"`.
3. Nếu không tìm thấy bất kỳ thẻ nào cần xóa: **Bấm SKIP** an toàn để bảo toàn tài nguyên (Credits).

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
- Ưu tiên hòa điểm: `TOP (3) > MIDDLE (2) > BOTTOM (1)`.

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

## 4. Danh sách Lỗi Cũ & Anti-Patterns ĐÃ BIẾT (DO NOT MIGRATE TO CHAOS2)

1. **Gán cứng `active_character = "Rossweisse"`:** Bản cũ mặc định `active_character` là Rossweisse ở mọi nơi, làm hỏng việc tính deck và target epiphany khi người dùng chọn nhân vật khác (như Nia, Tiphera).
2. **Lỗi đối chiếu key `epiphany_targets`:** Trong preset JSON, key là `rossweisse_flicker_blade` nhưng code cũ kiểm tra `cid == target_id or target_id in card_title.lower()`, bỏ qua hoàn toàn base card key mapping!
3. **Chuỗi Tap Mù (Blind Tap Chains):** Code cũ gọi `tap()` liên tiếp (chọn slot rồi Confirm ngay lập tức) mà không xác nhận frame tiếp theo đã phản hồi chưa.
4. **Hạ tầng K-frame phân mảnh:** Trộn lẫn `_settled_frames`, `frames_since_change`, `STATE_SETTLING_FRAMES`, `min_frames=2` ở nhiều file khác nhau gây trễ hoặc xung đột.
5. **Tap bừa vào ROI Đảo 3D:** Code cũ có fallback tap vào vùng đảo ngay cả khi không có đường đi an toàn.
6. **Không phân biệt được 3 thẻ cùng tên trong Epiphany:** Trong game thực tế, 3 thẻ Epiphany có thể có **cùng tên** (ví dụ "Dual Creation"), chỉ khác ở Tag (ví dụ `[Unique]` vs `[Unique / Initiation]`) và nội dung hiệu ứng. Code cũ chỉ so khớp theo tên nên nhận diện sai.
7. **Bỏ qua xác nhận trạng thái nút Remove:** Xóa thẻ tốn điểm và không hoàn tác được. Code cũ tap trực tiếp mà không kiểm tra nút Remove đã chuyển từ xám sang cam (kích hoạt) hay chưa.
