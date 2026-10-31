"""
Cyberpunk-Themed Modern GUI for Chaos Zero Nightmare Bot.
Built with CustomTkinter (v6.0.0) & Pillow.

Features:
- High-contrast Cyberpunk Orange & Black styling.
- 4 Top Navigation Tabs:
    1. 🎮 Điều khiển chính (Main Dashboard & Quick Controls)
    2. 🗺️ Chaos & Cốt truyện (Chaos Strategy, 3D Islands & Story)
    3. 📺 Xem trước & Nhật ký (Live Screen Preview & Formatted Logs)
    4. ⚙️ Cài đặt nâng cao (Hybrid OCR, Watchdog, Webhooks & Storage)
"""

import os
import sys
import threading
import subprocess
from datetime import datetime
from typing import Optional, Any, Dict, List
import cv2
import numpy as np
from PIL import Image

import customtkinter as ctk

import sys
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from czn_bot.states import Mode, State
from czn_bot.constants import (
    LOGS_DIR,
    ENABLE_HYBRID_VERIFICATION,
    HYBRID_VERIFICATION_PAD,
    MAX_UNKNOWN_SCREENSHOTS,
)
from czn_bot.settings import (
    ADB_HOST,
    ADB_PORT,
    ENABLE_WINDOWS_TOAST,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DISCORD_WEBHOOK_URL,
)
from czn_bot.device.adb import ADBClient
from czn_bot.vision.detector import ScreenDetector
from czn_bot.runner import BotRunner as BotEngine


# Set global appearance mode and color theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Cyberpunk Palette Constants ─────────────────────────────────────
COLOR_BG_BASE = "#0f0f13"
COLOR_BG_CARD = "#171720"
COLOR_BG_SUBCARD = "#20202c"
COLOR_BG_INPUT = "#13131a"
COLOR_ACCENT = "#ff6b00"
COLOR_ACCENT_HOVER = "#ff8533"
COLOR_ACCENT_DIM = "#8a3c00"
COLOR_GREEN = "#00c853"
COLOR_GREEN_HOVER = "#00e676"
COLOR_RED = "#d50000"
COLOR_RED_HOVER = "#ff1744"
COLOR_TEXT_MAIN = "#ffffff"
COLOR_TEXT_MUTED = "#9e9eb0"
COLOR_TEXT_ORANGE = "#ff9100"
COLOR_BORDER = "#2e2e3e"


class BotGUI:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("⚡ Chaos Zero Nightmare — BlueStacks Cyber Bot")
        self.root.geometry("940x720")
        self.root.minsize(860, 640)
        self.root.configure(fg_color=COLOR_BG_BASE)

        # Backend components
        self.adb = ADBClient(host=ADB_HOST, port=ADB_PORT)
        self.detector = ScreenDetector()
        self.engine = BotEngine(adb_client=self.adb, detector=self.detector)

        # Wire engine callbacks
        self.engine.on_log = self._handle_log
        self.engine.on_state_change = self._handle_state_change
        self.engine.on_frame = self._handle_live_frame
        self.engine.on_stats_update = self._handle_stats_update
        self.engine.on_stopped = self._handle_stopped
        self.engine.on_stall = self._handle_stall_alert

        # UI state variables
        self.mode_var = ctk.StringVar(value=Mode.REPLAY.value)
        self.strategy_var = ctk.StringVar(value="balanced")
        self.auto_start_var = ctk.BooleanVar(value=True)
        self.recovery_var = ctk.BooleanVar(value=False)
        self.dynamic_islands_var = ctk.BooleanVar(value=True)
        self.auto_pick_epiphany_var = ctk.BooleanVar(value=True)
        self.hybrid_ocr_var = ctk.BooleanVar(value=ENABLE_HYBRID_VERIFICATION)
        self.live_preview_enabled = ctk.BooleanVar(value=True)
        self.limit_retry_var = ctk.BooleanVar(value=False)
        self.max_retries_var = ctk.StringVar(value="10")
        self.delay_var = ctk.StringVar(value="1.5")
        self.hybrid_pad_var = ctk.StringVar(value=str(HYBRID_VERIFICATION_PAD))
        self.toast_var = ctk.BooleanVar(value=ENABLE_WINDOWS_TOAST)
        self.max_unknown_var = ctk.StringVar(value=str(MAX_UNKNOWN_SCREENSHOTS))

        # Rule Manager state variables (100% Offline)
        self.engine.on_ai_decision = self._handle_ai_decision

        ev_prio = self.engine.rule_manager.event_rules.get("priorities", {})
        self.rule_fight_boss_var = ctk.BooleanVar(value=ev_prio.get("fight_boss_for_gear", True))
        self.rule_take_quiz_var = ctk.BooleanVar(value=ev_prio.get("take_quiz", True))
        self.rule_avoid_cost_var = ctk.BooleanVar(value=ev_prio.get("avoid_credit_cost", True))
        self.rule_heal_hp_var = ctk.BooleanVar(value=ev_prio.get("heal_if_low_hp", True))
        self.rule_min_credits_var = ctk.StringVar(value=str(self.engine.rule_manager.event_rules.get("min_credit_reserve", 100)))

        self.amp_therapy_variant_var = ctk.StringVar(value="Elasticity")
        self.card_focus_var = ctk.BooleanVar(value=True)
        self.card_passion_var = ctk.BooleanVar(value=True)
        self.card_possession_var = ctk.BooleanVar(value=True)
        self.card_mute_accent_var = ctk.BooleanVar(value=True)

        # Cached last screenshot for preview
        self._last_screen: Optional[np.ndarray] = None
        self._preview_ctk_image: Optional[ctk.CTkImage] = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_closing)
        self._check_initial_connection()

    def _build_ui(self):
        # ── 1. Top Header Bar ──────────────────────────────────────────
        header_frame = ctk.CTkFrame(self.root, fg_color=COLOR_BG_CARD, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        header_frame.pack(fill="x", padx=14, pady=(12, 6))

        # Title with neon icon
        lbl_title = ctk.CTkLabel(
            header_frame,
            text="⚡ CHAOS ZERO NIGHTMARE",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=COLOR_ACCENT
        )
        lbl_title.pack(side="left", padx=16, pady=10)

        lbl_subtitle = ctk.CTkLabel(
            header_frame,
            text="|  BlueStacks Precision Bot",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_MUTED
        )
        lbl_subtitle.pack(side="left", padx=(0, 16), pady=10)

        # Connection status pill
        self.lbl_status = ctk.CTkLabel(
            header_frame,
            text="⚪ Đang kiểm tra ADB...",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#f57c00"
        )
        self.lbl_status.pack(side="right", padx=16, pady=10)

        btn_reconnect = ctk.CTkButton(
            header_frame,
            text="⟳ Kết nối",
            width=80,
            height=28,
            fg_color=COLOR_BG_SUBCARD,
            hover_color=COLOR_ACCENT_DIM,
            text_color=COLOR_TEXT_MAIN,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_connect_clicked
        )
        btn_reconnect.pack(side="right", padx=6, pady=10)

        # ── 2. Top Tabs View ────────────────────────────────────────────
        self.tabview = ctk.CTkTabview(
            self.root,
            fg_color=COLOR_BG_CARD,
            segmented_button_fg_color=COLOR_BG_SUBCARD,
            segmented_button_selected_color=COLOR_ACCENT,
            segmented_button_selected_hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_MAIN,
            corner_radius=10,
            border_width=1,
            border_color=COLOR_BORDER
        )
        self.tabview.pack(fill="both", expand=True, padx=14, pady=6)

        tab1 = self.tabview.add("🎮 Điều khiển chính")
        tab2 = self.tabview.add("⚔️ Quy tắc & Chiến thuật Chaos")
        tab3 = self.tabview.add("📺 Xem trước & Nhật ký")
        tab4 = self.tabview.add("⚙️ Cài đặt nâng cao")

        self._build_tab_dashboard(tab1)
        self._build_tab_chaos_story(tab2)
        self._build_tab_preview_logs(tab3)
        self._build_tab_settings(tab4)

        # ── 3. Bottom Global Telemetry Bar ──────────────────────────────
        footer_frame = ctk.CTkFrame(self.root, fg_color=COLOR_BG_CARD, corner_radius=8, height=36, border_width=1, border_color=COLOR_BORDER)
        footer_frame.pack(fill="x", padx=14, pady=(4, 10))

        self.lbl_telemetry_state = ctk.CTkLabel(
            footer_frame,
            text="Trạng thái: CHƯA CHẠY",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_ACCENT
        )
        self.lbl_telemetry_state.pack(side="left", padx=14, pady=4)

        self.lbl_telemetry_stats = ctk.CTkLabel(
            footer_frame,
            text="Trận: 0 | Click: 0 | Đảo: 0 | Máu TB: —",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_telemetry_stats.pack(side="right", padx=14, pady=4)

    # ── Tab 1: Điều khiển chính ─────────────────────────────────────────
    def _build_tab_dashboard(self, parent):
        # Section 1: Mode Selection
        mode_card = ctk.CTkFrame(parent, fg_color=COLOR_BG_SUBCARD, corner_radius=8)
        mode_card.pack(fill="x", padx=12, pady=10)

        lbl_mode_head = ctk.CTkLabel(
            mode_card,
            text="CHẾ ĐỘ HOẠT ĐỘNG",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_ACCENT
        )
        lbl_mode_head.pack(anchor="w", padx=14, pady=(10, 4))

        modes = [
            (Mode.REPLAY.value, "Đi lại màn", "Lặp lại liên tục đúng màn vừa xong (Bấm Retry)"),
            (Mode.PROGRESS.value, "Cày màn", "Tự động đi tiếp khi màn hiện Next Stage"),
            (Mode.CHAOS.value, "Chế độ Chaos", "Thuật toán tìm đường DAG thông minh, né tránh Elite khi ít máu"),
            (Mode.STORY.value, "Cốt truyện", "Tự động chọn ải, chuyển chương và tua nhanh hội thoại"),
        ]

        row_mode = ctk.CTkFrame(mode_card, fg_color="transparent")
        row_mode.pack(fill="x", padx=12, pady=(0, 10))

        for val, title, desc in modes:
            rb_frame = ctk.CTkFrame(row_mode, fg_color=COLOR_BG_INPUT, corner_radius=6, border_width=1, border_color=COLOR_BORDER)
            rb_frame.pack(side="left", fill="both", expand=True, padx=4, pady=4)

            rb = ctk.CTkRadioButton(
                rb_frame,
                text=title,
                value=val,
                variable=self.mode_var,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLOR_TEXT_MAIN,
                fg_color=COLOR_ACCENT,
                hover_color=COLOR_ACCENT_HOVER
            )
            rb.pack(anchor="w", padx=10, pady=(8, 2))

            lbl_desc = ctk.CTkLabel(
                rb_frame,
                text=desc,
                font=ctk.CTkFont(size=10),
                text_color=COLOR_TEXT_MUTED,
                wraplength=170,
                justify="left"
            )
            lbl_desc.pack(anchor="w", padx=10, pady=(0, 8))

        # Section 2: Quick Parameters
        param_card = ctk.CTkFrame(parent, fg_color=COLOR_BG_SUBCARD, corner_radius=8)
        param_card.pack(fill="x", padx=12, pady=6)

        param_row = ctk.CTkFrame(param_card, fg_color="transparent")
        param_row.pack(fill="x", padx=14, pady=10)

        # Loop delay
        ctk.CTkLabel(param_row, text="Thời gian chờ mỗi vòng:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self.entry_delay = ctk.CTkEntry(param_row, width=65, textvariable=self.delay_var, justify="center")
        self.entry_delay.pack(side="left", padx=(0, 4))
        ctk.CTkLabel(param_row, text="giây", text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 24))

        # Retry limit
        chk_limit = ctk.CTkCheckBox(
            param_row,
            text="Giới hạn số lượt/trận:",
            variable=self.limit_retry_var,
            command=self._on_limit_toggled,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER
        )
        chk_limit.pack(side="left", padx=(0, 6))

        self.entry_limit = ctk.CTkEntry(param_row, width=65, textvariable=self.max_retries_var, justify="center", state="disabled")
        self.entry_limit.pack(side="left", padx=(0, 24))

        # Auto Enter pre-match
        chk_auto = ctk.CTkSwitch(
            param_row,
            text="Tự bấm Enter vào trận",
            variable=self.auto_start_var,
            progress_color=COLOR_ACCENT
        )
        chk_auto.pack(side="left")

        # Section 3: Large Big Action Buttons
        btn_card = ctk.CTkFrame(parent, fg_color="transparent")
        btn_card.pack(fill="x", padx=12, pady=(16, 10))

        self.btn_start = ctk.CTkButton(
            btn_card,
            text="▶  BẮT ĐẦU BOT",
            height=54,
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            fg_color=COLOR_GREEN,
            hover_color=COLOR_GREEN_HOVER,
            text_color="#ffffff",
            corner_radius=10,
            command=self._on_start_clicked
        )
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_stop = ctk.CTkButton(
            btn_card,
            text="⏹  DỪNG BOT",
            height=54,
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            fg_color=COLOR_RED,
            hover_color=COLOR_RED_HOVER,
            text_color="#ffffff",
            corner_radius=10,
            state="disabled",
            command=self._on_stop_clicked
        )
        self.btn_stop.pack(side="right", fill="x", expand=True, padx=(8, 0))

    # ── Tab 2: Chaos AI & Chiến thuật ──────────────────────────────────
    def _build_tab_chaos_story(self, parent):
        scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # ── 1. Thông tin Hệ thống Chiến thuật Ngoại tuyến (100% Offline) ──
        offline_card = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_SUBCARD, corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        offline_card.pack(fill="x", padx=10, pady=(6, 8))

        ctk.CTkLabel(
            offline_card,
            text="⚡ HỆ THỐNG QUY TẮC CHIẾN THUẬT CỤC BỘ (100% OFFLINE)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=14, pady=(10, 4))

        ctk.CTkLabel(
            offline_card,
            text="Bot hoạt động 100% ngoại tuyến, không kết nối AI bên ngoài và không yêu cầu API Key.\nNhận diện màn hình bằng OpenCV + OCR cục bộ. Tự động chọn thẻ, sự kiện và tìm đường dựa theo cấu hình bên dưới.",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_MUTED,
            justify="left"
        ).pack(anchor="w", padx=14, pady=(0, 10))

        # ── 2. Quản lý Quy tắc Thẻ bài (Card Rules) ────────────────────
        card_box = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_SUBCARD, corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        card_box.pack(fill="x", padx=10, pady=6)

        # Database Info Banner
        num_cards = len(getattr(self.engine.rule_manager, "cards", []))
        num_events = len(getattr(self.engine.rule_manager, "events_database", []))
        if num_cards > 0 or num_events > 0:
            db_banner = ctk.CTkFrame(card_box, fg_color=COLOR_BG_INPUT, corner_radius=6, border_width=1, border_color="#00e676")
            db_banner.pack(fill="x", padx=14, pady=(8, 4))
            ctk.CTkLabel(
                db_banner,
                text=f"📚 Đã nạp từ templates/: {num_cards} Thẻ bài (12 Nhân vật) | {num_events} Sự kiện game hoàn chỉnh",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#00e676"
            ).pack(side="left", padx=10, pady=6)

        head_card = ctk.CTkFrame(card_box, fg_color="transparent")
        head_card.pack(fill="x", padx=14, pady=(6, 4))

        ctk.CTkLabel(
            head_card,
            text="🃏 QUẢN LÝ BIẾN THỂ & MỨC ƯU TIÊN THẺ BÀI (CARD RULES)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(side="left")

        chk_pick = ctk.CTkSwitch(
            head_card,
            text="Tự động chọn thẻ",
            variable=self.auto_pick_epiphany_var,
            progress_color=COLOR_ACCENT,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        chk_pick.pack(side="right")

        # Table of cards & variant rules
        table_cards = ctk.CTkFrame(card_box, fg_color=COLOR_BG_INPUT, corner_radius=6, border_width=1, border_color=COLOR_BORDER)
        table_cards.pack(fill="x", padx=14, pady=(4, 10))

        # Amp Therapy row (variant selection)
        r1 = ctk.CTkFrame(table_cards, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(r1, text="1. Amp Therapy:", font=ctk.CTkFont(size=12, weight="bold"), width=150, anchor="w").pack(side="left")
        ctk.CTkLabel(r1, text="Biến thể ưu tiên:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 6))
        opt_amp = ctk.CTkOptionMenu(
            r1,
            values=["Elasticity (Khuyến nghị)", "Base"],
            variable=self.amp_therapy_variant_var,
            fg_color=COLOR_BG_SUBCARD,
            button_color=COLOR_ACCENT_DIM,
            button_hover_color=COLOR_ACCENT,
            width=200
        )
        opt_amp.pack(side="left")
        ctk.CTkLabel(r1, text="Ưu tiên tuyệt đối biến thể Elasticity so với Base", font=ctk.CTkFont(size=10), text_color="#00e676").pack(side="left", padx=12)

        # Other cards rows
        card_items = [
            ("2. Focus:", self.card_focus_var, "Hồi 1 Action Point khi máu dưới 50%"),
            ("3. Passion:", self.card_passion_var, "Tăng Hit count cho các thẻ cơ bản"),
            ("4. Possession:", self.card_possession_var, "Giảm Cost ngẫu nhiên cho thẻ trên tay"),
            ("5. Mute Accent:", self.card_mute_accent_var, "Gây 250% Extra Attack và kích hoạt Morale"),
        ]
        for name, var, desc in card_items:
            rf = ctk.CTkFrame(table_cards, fg_color="transparent")
            rf.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(rf, text=name, font=ctk.CTkFont(size=12, weight="bold"), width=150, anchor="w").pack(side="left")
            ctk.CTkSwitch(rf, text="Ưu tiên", variable=var, progress_color=COLOR_ACCENT, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 20))
            ctk.CTkLabel(rf, text=desc, font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")

        # ── 3. Cấu hình Quy tắc Sự kiện (Event Rules) ──────────────────
        event_box = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_SUBCARD, corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        event_box.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(
            event_box,
            text="📜 CẤU HÌNH QUY TẮC SỰ KIỆN (EVENT RULES)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=14, pady=(10, 6))

        grid_ev = ctk.CTkFrame(event_box, fg_color="transparent")
        grid_ev.pack(fill="x", padx=14, pady=(0, 6))

        sw1 = ctk.CTkSwitch(grid_ev, text="⚔️ Đánh boss nhận trang bị Rare (fight_boss_for_gear)", variable=self.rule_fight_boss_var, progress_color=COLOR_ACCENT)
        sw1.grid(row=0, column=0, sticky="w", padx=6, pady=4)

        sw2 = ctk.CTkSwitch(grid_ev, text="🧩 Tham gia Quiz / Câu đố an toàn (take_quiz)", variable=self.rule_take_quiz_var, progress_color=COLOR_ACCENT)
        sw2.grid(row=0, column=1, sticky="w", padx=16, pady=4)

        sw3 = ctk.CTkSwitch(grid_ev, text="💰 Né sự kiện tốn Credits (avoid_credit_cost)", variable=self.rule_avoid_cost_var, progress_color=COLOR_ACCENT)
        sw3.grid(row=1, column=0, sticky="w", padx=6, pady=4)

        sw4 = ctk.CTkSwitch(grid_ev, text="💚 Ưu tiên hồi máu khi HP < 50% (heal_if_low_hp)", variable=self.rule_heal_hp_var, progress_color=COLOR_ACCENT)
        sw4.grid(row=1, column=1, sticky="w", padx=16, pady=4)

        # Min Credits Reserve
        row_credit = ctk.CTkFrame(event_box, fg_color="transparent")
        row_credit.pack(fill="x", padx=14, pady=(4, 10))

        ctk.CTkLabel(row_credit, text="Số Credits tối thiểu cần giữ lại (không tiêu tốn):", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkEntry(row_credit, textvariable=self.rule_min_credits_var, width=80, fg_color=COLOR_BG_INPUT, border_color=COLOR_BORDER).pack(side="left", padx=8)
        ctk.CTkLabel(row_credit, text="Credits (Né các lựa chọn tốn tiền nếu quỹ < mốc này)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")

        # ── 4. Nút Lưu Quy Tắc & Xuất File JSON ────────────────────────
        save_box = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        save_box.pack(fill="x", padx=10, pady=8)

        self.btn_save_rules = ctk.CTkButton(
            save_box,
            text="💾  LƯU QUY TẮC (Xuất ra card_rules.json & event_rules.json)",
            height=46,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLOR_GREEN,
            hover_color=COLOR_GREEN_HOVER,
            command=self._on_save_rules_clicked
        )
        self.btn_save_rules.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.lbl_save_status = ctk.CTkLabel(
            save_box,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00e676"
        )
        self.lbl_save_status.pack(side="left")

        # ── 5. Badge Quyết Định AI Thời Gian Thực ─────────────────────
        ai_dec_box = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_SUBCARD, corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        ai_dec_box.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(
            ai_dec_box,
            text="🧠 QUYẾT ĐỊNH CHIẾN THUẬT AI GẦN NHẤT",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=14, pady=(8, 2))

        self.lbl_ai_reason = ctk.CTkLabel(
            ai_dec_box,
            text="Chưa có quyết định nào từ AI (Sẵn sàng khi gặp bảng chọn thẻ hoặc sự kiện)",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=COLOR_TEXT_ORANGE,
            wraplength=800,
            justify="left"
        )
        self.lbl_ai_reason.pack(anchor="w", padx=14, pady=(0, 10))

        # ── 6. Chiến thuật chọn đường Chaos & Thống kê phiên ──────────
        strat_card = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_SUBCARD, corner_radius=8)
        strat_card.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(
            strat_card,
            text="CHIẾN THUẬT CHỌN ĐƯỜNG TRONG BẢN ĐỒ CHAOS",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=14, pady=(8, 4))

        strategies = [
            ("safe", "🛡️ An toàn (Safe)", "Ưu tiên tối đa Lửa trại & Sự kiện để bảo toàn máu; né tránh Tinh anh khi máu yếu."),
            ("balanced", "⚖️ Cân bằng (Balanced)", "Cân bằng tối ưu giữa điểm thưởng và khả năng sinh tồn (Khuyến nghị)."),
            ("aggressive", "⚔️ Tấn công (Aggressive)", "Ưu tiên chọn ô Tinh anh và giao tranh để cày điểm kinh nghiệm và di vật."),
        ]

        row_strat = ctk.CTkFrame(strat_card, fg_color="transparent")
        row_strat.pack(fill="x", padx=10, pady=(0, 8))

        for code, label, tip in strategies:
            sf = ctk.CTkFrame(row_strat, fg_color=COLOR_BG_INPUT, corner_radius=6, border_width=1, border_color=COLOR_BORDER)
            sf.pack(side="left", fill="both", expand=True, padx=3, pady=2)

            rb = ctk.CTkRadioButton(
                sf,
                text=label,
                value=code,
                variable=self.strategy_var,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=COLOR_ACCENT,
                hover_color=COLOR_ACCENT_HOVER
            )
            rb.pack(anchor="w", padx=8, pady=(6, 2))

            ctk.CTkLabel(
                sf,
                text=tip,
                font=ctk.CTkFont(size=9),
                text_color=COLOR_TEXT_MUTED,
                wraplength=210,
                justify="left"
            ).pack(anchor="w", padx=8, pady=(0, 6))

        # Chaos Telemetry Dashboard
        telemetry_card = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_SUBCARD, corner_radius=8)
        telemetry_card.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(
            telemetry_card,
            text="THỐNG KÊ CHI TIẾT PHIÊN CHAOS",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=14, pady=(8, 4))

        row_stats = ctk.CTkFrame(telemetry_card, fg_color="transparent")
        row_stats.pack(fill="x", padx=14, pady=(0, 10))

        self.lbl_chaos_hp = ctk.CTkLabel(
            row_stats,
            text="💚 Máu đội TB: —",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#00e676"
        )
        self.lbl_chaos_hp.pack(side="left", padx=(0, 24))

        self.lbl_chaos_score = ctk.CTkLabel(
            row_stats,
            text="⭐ Điểm lộ trình TB: —",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffd600"
        )
        self.lbl_chaos_score.pack(side="left", padx=(0, 24))

        self.lbl_chaos_picks = ctk.CTkLabel(
            row_stats,
            text="🏝️ Đảo đã chọn: Trên (0) | Giữa (0) | Dưới (0)",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_MAIN
        )
        self.lbl_chaos_picks.pack(side="left")

    # ── Tab 3: Xem trước & Nhật ký ─────────────────────────────────────
    def _build_tab_preview_logs(self, parent):
        # Two-column layout in Tab 3: Left = Live Screen Preview, Right = Action Controls
        preview_container = ctk.CTkFrame(parent, fg_color="transparent")
        preview_container.pack(fill="x", padx=8, pady=4)

        # Left Preview Box
        preview_box = ctk.CTkFrame(preview_container, fg_color=COLOR_BG_SUBCARD, corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        preview_box.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=4)

        prev_head = ctk.CTkFrame(preview_box, fg_color="transparent")
        prev_head.pack(fill="x", padx=10, pady=(6, 2))

        ctk.CTkLabel(
            prev_head,
            text="📺 XEM TRƯỚC MÀN HÌNH GIẢ LẬP",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(side="left")

        chk_live = ctk.CTkSwitch(
            prev_head,
            text="Bật Live Preview",
            variable=self.live_preview_enabled,
            progress_color=COLOR_ACCENT,
            font=ctk.CTkFont(size=11)
        )
        chk_live.pack(side="right")

        # Screen image display label (default 480x270 ratio 16:9)
        self.lbl_preview = ctk.CTkLabel(
            preview_box,
            text="[ Chưa có hình ảnh từ giả lập ]",
            width=480,
            height=270,
            fg_color="#08080a",
            corner_radius=6,
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_preview.pack(padx=10, pady=8)

        # Right Action & Shortcuts
        ctrl_box = ctk.CTkFrame(preview_container, fg_color=COLOR_BG_SUBCARD, corner_radius=8, width=220, border_width=1, border_color=COLOR_BORDER)
        ctrl_box.pack(side="right", fill="y", padx=(6, 0), pady=4)

        ctk.CTkLabel(
            ctrl_box,
            text="THAO TÁC NHANH",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=12, pady=(10, 8))

        btn_snap = ctk.CTkButton(
            ctrl_box,
            text="📸 Chụp màn hình ngay",
            fg_color=COLOR_BG_INPUT,
            hover_color=COLOR_ACCENT_DIM,
            command=self._on_snapshot_clicked
        )
        btn_snap.pack(fill="x", padx=12, pady=4)

        btn_open_img = ctk.CTkButton(
            ctrl_box,
            text="📂 Thư mục ảnh Logs",
            fg_color=COLOR_BG_INPUT,
            hover_color=COLOR_ACCENT_DIM,
            command=self._open_logs_dir
        )
        btn_open_img.pack(fill="x", padx=12, pady=4)

        btn_clear_log = ctk.CTkButton(
            ctrl_box,
            text="🗑️ Xóa sạch nhật ký",
            fg_color=COLOR_BG_INPUT,
            hover_color=COLOR_RED,
            command=self._clear_log
        )
        btn_clear_log.pack(fill="x", padx=12, pady=4)

        # Log Console Box below
        log_box = ctk.CTkFrame(parent, fg_color=COLOR_BG_SUBCARD, corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        log_box.pack(fill="both", expand=True, padx=8, pady=(4, 6))

        self.txt_log = ctk.CTkTextbox(
            log_box,
            fg_color="#0a0a0e",
            text_color="#e0e0e0",
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=6
        )
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=8)

    # ── Tab 4: Cài đặt nâng cao ────────────────────────────────────────
    def _build_tab_settings(self, parent):
        scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # Section 1: Hybrid OCR Verification
        ocr_card = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_SUBCARD, corner_radius=8)
        ocr_card.pack(fill="x", padx=8, pady=6)

        ctk.CTkLabel(
            ocr_card,
            text="THẨM ĐỊNH KÉP OCR (HYBRID VERIFICATION)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=14, pady=(10, 4))

        ocr_row = ctk.CTkFrame(ocr_card, fg_color="transparent")
        ocr_row.pack(fill="x", padx=14, pady=(0, 10))

        chk_ocr = ctk.CTkSwitch(
            ocr_row,
            text="Bật thẩm định chữ trước khi bấm (Ngăn chặn bấm nhầm thẻ)",
            variable=self.hybrid_ocr_var,
            progress_color=COLOR_ACCENT
        )
        chk_ocr.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(ocr_row, text="Nới rộng vùng quét (Pad):").pack(side="left", padx=(0, 4))
        entry_pad = ctk.CTkEntry(ocr_row, width=50, textvariable=self.hybrid_pad_var, justify="center")
        entry_pad.pack(side="left", padx=(0, 4))
        ctk.CTkLabel(ocr_row, text="px", text_color=COLOR_TEXT_MUTED).pack(side="left")

        # Section 2: Watchdog & Recovery
        watch_card = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_SUBCARD, corner_radius=8)
        watch_card.pack(fill="x", padx=8, pady=6)

        ctk.CTkLabel(
            watch_card,
            text="BẢO VỆ CHỐNG TREO MÁY (STALL WATCHDOG & RECOVERY)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=14, pady=(10, 4))

        watch_row = ctk.CTkFrame(watch_card, fg_color="transparent")
        watch_row.pack(fill="x", padx=14, pady=(0, 10))

        chk_rec = ctk.CTkSwitch(
            watch_row,
            text="Tự động bấm thoát/phục hồi khi bot đứng hình quá 30s",
            variable=self.recovery_var,
            progress_color=COLOR_ACCENT
        )
        chk_rec.pack(side="left", padx=(0, 20))

        # Section 3: Webhook & Notifications
        notif_card = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_SUBCARD, corner_radius=8)
        notif_card.pack(fill="x", padx=8, pady=6)

        ctk.CTkLabel(
            notif_card,
            text="CẤU HÌNH THÔNG BÁO TỪ XA (TELEGRAM & DISCORD)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=14, pady=(10, 6))

        # Discord
        d_row = ctk.CTkFrame(notif_card, fg_color="transparent")
        d_row.pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(d_row, text="Discord Webhook URL:", width=150, anchor="w").pack(side="left")
        self.entry_discord = ctk.CTkEntry(d_row, placeholder_text="https://discord.com/api/webhooks/...")
        self.entry_discord.pack(side="left", fill="x", expand=True, padx=6)
        if DISCORD_WEBHOOK_URL:
            self.entry_discord.insert(0, DISCORD_WEBHOOK_URL)
        ctk.CTkButton(d_row, text="Test Discord", width=95, fg_color=COLOR_BG_INPUT, hover_color=COLOR_ACCENT_DIM, command=self._test_discord).pack(side="right")

        # Telegram
        t_row = ctk.CTkFrame(notif_card, fg_color="transparent")
        t_row.pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(t_row, text="Telegram Bot Token:", width=150, anchor="w").pack(side="left")
        self.entry_tg_token = ctk.CTkEntry(t_row, placeholder_text="123456:ABC-DEF...")
        self.entry_tg_token.pack(side="left", fill="x", expand=True, padx=6)
        if TELEGRAM_BOT_TOKEN:
            self.entry_tg_token.insert(0, TELEGRAM_BOT_TOKEN)

        t_row2 = ctk.CTkFrame(notif_card, fg_color="transparent")
        t_row2.pack(fill="x", padx=14, pady=(3, 10))
        ctk.CTkLabel(t_row2, text="Telegram Chat ID:", width=150, anchor="w").pack(side="left")
        self.entry_tg_chat = ctk.CTkEntry(t_row2, placeholder_text="-100123456789")
        self.entry_tg_chat.pack(side="left", fill="x", expand=True, padx=6)
        if TELEGRAM_CHAT_ID:
            self.entry_tg_chat.insert(0, TELEGRAM_CHAT_ID)
        ctk.CTkButton(t_row2, text="Test Telegram", width=95, fg_color=COLOR_BG_INPUT, hover_color=COLOR_ACCENT_DIM, command=self._test_telegram).pack(side="right")

        # Section 4: Storage Manager
        store_card = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_SUBCARD, corner_radius=8)
        store_card.pack(fill="x", padx=8, pady=(6, 12))

        ctk.CTkLabel(
            store_card,
            text="QUẢN LÝ DUNG LƯỢNG ẢNH LỖI (STORAGE CLEANUP)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=14, pady=(10, 4))

        store_row = ctk.CTkFrame(store_card, fg_color="transparent")
        store_row.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(store_row, text="Giữ tối đa số ảnh UNKNOWN gần nhất:").pack(side="left", padx=(0, 6))
        ctk.CTkEntry(store_row, width=60, textvariable=self.max_unknown_var, justify="center").pack(side="left", padx=(0, 20))

        btn_clean = ctk.CTkButton(
            store_row,
            text="🧹 Dọn dẹp ảnh cũ ngay",
            width=150,
            fg_color=COLOR_BG_INPUT,
            hover_color=COLOR_ACCENT_DIM,
            command=self._clean_storage_now
        )
        btn_clean.pack(side="left")

    # ── Event Handlers & Control ───────────────────────────────────────
    def _on_limit_toggled(self):
        if self.limit_retry_var.get():
            self.entry_limit.configure(state="normal")
            self._on_retries_changed()
        else:
            self.entry_limit.configure(state="disabled")
            self.engine.max_retries = None

    def _on_retries_changed(self, *args):
        if self.limit_retry_var.get():
            raw = self.max_retries_var.get().strip()
            try:
                val = int(raw)
                if val > 0:
                    self.engine.max_retries = val
            except ValueError:
                pass
        else:
            self.engine.max_retries = None

    def _check_initial_connection(self):
        self.root.after(300, self._on_connect_clicked)

    def _on_connect_clicked(self, on_done=None):
        host = ADB_HOST
        port = ADB_PORT
        self.lbl_status.configure(text="⏳ Đang kết nối ADB...", text_color="#f57c00")

        def _worker():
            self.adb = ADBClient(host=host, port=port)
            self.engine.adb = self.adb
            ok = self.adb.connect() or self.adb.is_connected()

            def _update_ui():
                if ok:
                    ok_res, size, res_msg = self.adb.check_resolution()
                    if not ok_res and size is not None:
                        self.lbl_status.configure(
                            text=f"⚠️ {size[0]}x{size[1]} (Cần 1600x900)",
                            text_color="#e65100"
                        )
                        self._handle_log(f"⚠️ Đã kết nối nhưng độ phân giải {size[0]}x{size[1]} khác chuẩn 1600x900!")
                    else:
                        self.lbl_status.configure(text=f"🟢 Đã kết nối: {host}:{port} (1600x900)", text_color="#00e676")
                        self._handle_log(f"🟢 Đã kết nối thành công tới BlueStacks tại {host}:{port}")
                else:
                    self.lbl_status.configure(text=f"🔴 Chưa kết nối: {host}:{port}", text_color="#ff1744")
                    self._handle_log(f"🔴 Không thể kết nối ADB tại {host}:{port}. Vui lòng kiểm tra BlueStacks Settings.")

                if on_done:
                    on_done(ok)

            self.root.after(0, _update_ui)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_start_clicked(self):
        if not self.adb.is_connected():
            self._handle_log("❌ Chưa kết nối được BlueStacks qua ADB! Bấm 'Kết nối' trước khi chạy.")
            return

        # Configure engine options
        val = self.mode_var.get()
        if val == Mode.REPLAY.value:
            selected_mode = Mode.REPLAY
        elif val == Mode.PROGRESS.value:
            selected_mode = Mode.PROGRESS
        elif val == Mode.STORY.value:
            selected_mode = Mode.STORY
        else:
            selected_mode = Mode.CHAOS

        self.engine.mode = selected_mode
        self.engine.auto_start_match = self.auto_start_var.get()
        self.engine.chaos_strategy = self.strategy_var.get()
        self.engine.enable_recovery = self.recovery_var.get()
        self.engine.enable_dynamic_islands = self.dynamic_islands_var.get()
        self.engine.auto_pick_epiphany = self.auto_pick_epiphany_var.get()
        self.engine.enable_hybrid_verification = self.hybrid_ocr_var.get()
        self.engine.enable_ai_vision_detection = False

        try:
            raw_delay = self.delay_var.get().replace(",", ".").strip()
            self.engine.loop_delay = max(0.1, float(raw_delay))
        except ValueError:
            self.engine.loop_delay = 1.5

        if self.limit_retry_var.get():
            try:
                self.engine.max_retries = int(self.max_retries_var.get().strip())
            except ValueError:
                self.engine.max_retries = None
        else:
            self.engine.max_retries = None

        try:
            self.engine.hybrid_pad = int(self.hybrid_pad_var.get().strip())
        except ValueError:
            self.engine.hybrid_pad = HYBRID_VERIFICATION_PAD
        # Status Logging for Chaos
        if selected_mode == Mode.CHAOS:
            self._handle_log("⚔️ [Chaos Mode] Đã kích hoạt Bộ quy tắc Heuristics & OCR cục bộ (100% Offline).")

        # Update buttons state
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_telemetry_state.configure(text=f"Trạng thái: ĐANG CHẠY ({selected_mode.value})")

        self.engine.start()

    def _on_stop_clicked(self):
        self.engine.stop(reason="Người dùng yêu cầu dừng")
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _on_snapshot_clicked(self):
        """Take an instant screenshot and display in Live Preview."""
        def _snap():
            if not self.adb.is_connected():
                self._handle_log("❌ ADB chưa kết nối, không thể chụp ảnh.")
                return
            screen = self.adb.screencap()
            if screen is not None:
                self._update_preview_image(screen, tag="SNAPSHOT (Thủ công)")
                self._handle_log("📸 Đã chụp và cập nhật khung xem trước.")

        threading.Thread(target=_snap, daemon=True).start()

    # ── Live Screen Preview Render ─────────────────────────────────────
    def _handle_live_frame(self, screen: Any, state: State, details: dict):
        """Callback from BotEngine on every confirmed screencap."""
        if not self.live_preview_enabled.get():
            return
        if screen is None or getattr(screen, "size", 0) == 0:
            return
        self._last_screen = screen
        self._update_preview_image(screen, tag=f"{state.value}")

    def _update_preview_image(self, screen_bgr: np.ndarray, tag: str = ""):
        """Render a 480x270 preview image with state overlay."""
        def _render():
            try:
                # Resize from 1600x900 to 480x270 (16:9)
                resized = cv2.resize(screen_bgr, (480, 270), interpolation=cv2.INTER_AREA)

                # Draw state tag pill in top-left
                if tag:
                    cv2.rectangle(resized, (8, 8), (220, 32), (20, 20, 26), -1)
                    cv2.rectangle(resized, (8, 8), (220, 32), (0, 107, 255), 1)
                    cv2.putText(
                        resized, tag[:24], (14, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA
                    )

                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
                ctk_img = ctk.CTkImage(dark_image=pil_img, size=(480, 270))
                self._preview_ctk_image = ctk_img
                self.lbl_preview.configure(image=ctk_img, text="")
            except Exception as e:
                pass

        self.root.after(0, _render)

    # ── Callbacks from BotEngine ───────────────────────────────────────
    def _handle_log(self, message: str):
        def _append():
            timestamp = datetime.now().strftime("%H:%M:%S")
            line = f"[{timestamp}] {message}"
            self.txt_log.insert("end", line + "\n")
            self.txt_log.see("end")
        self.root.after(0, _append)

    def _handle_state_change(self, state: State, details: dict):
        def _update():
            self.lbl_telemetry_state.configure(text=f"Trạng thái: {state.value}")
        self.root.after(0, _update)

    def _handle_stats_update(self, stats: dict):
        def _update():
            summary = stats.get("summary", {})
            retries = stats.get("retries_done", 0)
            actions = stats.get("actions_done", 0)
            chaos_picks = summary.get("chaos_choices_total", 0)
            avg_hp = summary.get("chaos_avg_hp_percent")

            hp_str = f"{avg_hp:.0%}" if avg_hp is not None else "—"
            self.lbl_telemetry_stats.configure(
                text=f"Trận: {retries} | Click: {actions} | Đảo: {chaos_picks} | Máu TB: {hp_str}"
            )

            # Tab 2 detailed telemetry
            if avg_hp is not None:
                self.lbl_chaos_hp.configure(text=f"💚 Máu đội TB: {avg_hp:.1%}")
            avg_score = summary.get("chaos_avg_score")
            if avg_score is not None:
                self.lbl_chaos_score.configure(text=f"⭐ Điểm đường đi TB: {avg_score:.1f}")

            choices = summary.get("chaos_choices", {})
            self.lbl_chaos_picks.configure(
                text=f"🏝️ Đảo đã chọn: Trên ({choices.get('top', 0)}) | Giữa ({choices.get('middle', 0)}) | Dưới ({choices.get('bottom', 0)})"
            )

        self.root.after(0, _update)

    def _handle_stopped(self, reason: str):
        def _update():
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.lbl_telemetry_state.configure(text=f"Đã dừng: {reason}")
            self._handle_log(f"⏹ Bot đã dừng lại: {reason}")
        self.root.after(0, _update)

    def _handle_stall_alert(self, state: State, elapsed: float, img_path: str, json_path: str):
        self._handle_log(f"⚠️ [WATCHDOG] CẢNH BÁO: Bot dừng tại '{state.value}' quá {elapsed:.1f}s!")

    def _clear_log(self):
        self.txt_log.delete("0.0", "end")

    def _open_logs_dir(self):
        if sys.platform == "win32":
            os.startfile(LOGS_DIR)
        else:
            subprocess.run(["xdg-open", LOGS_DIR])

    def _clean_storage_now(self):
        try:
            limit = int(self.max_unknown_var.get().strip())
        except ValueError:
            limit = MAX_UNKNOWN_SCREENSHOTS
        deleted = BotEngine._cleanup_unknown_screenshots(max_keep=limit)
        self._handle_log(f"🧹 Đã dọn dẹp kho ảnh: Xóa {deleted} ảnh UNKNOWN vượt quá mốc {limit} tấm.")

    def _test_discord(self):
        url = self.entry_discord.get().strip()
        if not url:
            self._handle_log("❌ Vui lòng nhập Discord Webhook URL.")
            return

        def _send():
            import urllib.request, json
            try:
                data = json.dumps({"content": "⚡ [Chaos Zero Nightmare Bot] Kiểm tra kết nối Webhook thành công!"}).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "ChaosBot"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status in (200, 204):
                        self._handle_log("✅ Gửi tin nhắn test Discord thành công!")
                    else:
                        self._handle_log(f"⚠️ Discord phản hồi mã: {resp.status}")
            except Exception as e:
                self._handle_log(f"❌ Lỗi gửi test Discord: {e}")

        threading.Thread(target=_send, daemon=True).start()

    def _test_telegram(self):
        token = self.entry_tg_token.get().strip()
        chat_id = self.entry_tg_chat.get().strip()
        if not token or not chat_id:
            self._handle_log("❌ Vui lòng nhập đầy đủ Telegram Bot Token và Chat ID.")
            return

        def _send():
            import urllib.request, json
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                data = json.dumps({"chat_id": chat_id, "text": "⚡ [Chaos Zero Nightmare Bot] Kiểm tra kết nối Telegram thành công!"}).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        self._handle_log("✅ Gửi tin nhắn test Telegram thành công!")
                    else:
                        self._handle_log(f"⚠️ Telegram phản hồi mã: {resp.status}")
            except Exception as e:
                self._handle_log(f"❌ Lỗi gửi test Telegram: {e}")

        threading.Thread(target=_send, daemon=True).start()

    def _toggle_api_key_visibility(self):
        pass

    def _on_test_ai_clicked(self):
        self._handle_log("ℹ️ Chế độ AI đám mây đã tắt. Bot hoạt động 100% offline.")

    def _on_save_rules_clicked(self):
        """Lưu toàn bộ quy tắc ra card_rules.json và event_rules.json."""
        # Build card rules
        amp_variant = "Elasticity" if "elasticity" in self.amp_therapy_variant_var.get().lower() else "Base"
        card_rules = {
            "version": "1.0",
            "description": "Bảng quy tắc ưu tiên lựa chọn thẻ bài Chaos",
            "priority_list": [
                {
                    "card_name": "Amp Therapy",
                    "preferred_variant": amp_variant,
                    "priority": 1,
                    "notes": f"Ưu tiên biến thể {amp_variant}"
                },
                {
                    "card_name": "Focus",
                    "preferred_variant": "",
                    "priority": 2,
                    "active": self.card_focus_var.get(),
                    "notes": "Hồi 1 Action Point khi máu dưới 50%"
                },
                {
                    "card_name": "Passion",
                    "preferred_variant": "",
                    "priority": 3,
                    "active": self.card_passion_var.get(),
                    "notes": "Tăng Hit count cho các thẻ cơ bản"
                },
                {
                    "card_name": "Possession",
                    "preferred_variant": "",
                    "priority": 4,
                    "active": self.card_possession_var.get(),
                    "notes": "Giảm Cost ngẫu nhiên cho thẻ trên tay"
                },
                {
                    "card_name": "Mute Accent",
                    "preferred_variant": "Skill",
                    "priority": 5,
                    "active": self.card_mute_accent_var.get(),
                    "notes": "Gây 250% Extra Attack và kích hoạt Morale"
                }
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

        # Build event rules
        try:
            min_credits = int(self.rule_min_credits_var.get().strip())
        except ValueError:
            min_credits = 100

        event_rules = {
            "version": "1.0",
            "description": "Bảng quy tắc ưu tiên xử lý sự kiện ngẫu nhiên trong Chaos",
            "priorities": {
                "fight_boss_for_gear": self.rule_fight_boss_var.get(),
                "take_quiz": self.rule_take_quiz_var.get(),
                "avoid_credit_cost": self.rule_avoid_cost_var.get(),
                "heal_if_low_hp": self.rule_heal_hp_var.get()
            },
            "min_credit_reserve": min_credits,
            "hp_critical_threshold": 0.50,
            "strategy_notes": "1. Khi HP < 50%: Ưu tiên hồi máu, né đánh boss nguy hiểm.\n2. Khi HP >= 50%: Ưu tiên giao tranh Boss nhận đồ Rare.\n3. Tham gia Quiz nhận thưởng an toàn.\n4. Né sự kiện tốn tiền nếu Credits < min_credit_reserve."
        }

        ok = self.engine.rule_manager.save_all_rules(card_rules, event_rules)
        if ok:
            self.lbl_save_status.configure(text="✅ Đã lưu thành công card_rules.json & event_rules.json!", text_color="#00e676")
            self._handle_log("💾 [Cấu hình Quy tắc] Đã lưu thành công card_rules.json và event_rules.json.")
            self.root.after(4000, lambda: self.lbl_save_status.configure(text=""))
        else:
            self.lbl_save_status.configure(text="❌ Lỗi khi lưu file quy tắc!", text_color="#ff1744")

    def _handle_ai_decision(self, decision: Dict[str, Any]):
        """Cập nhật huy hiệu hiển thị quyết định AI trên giao diện thời gian thực."""
        if not decision:
            return
        action = decision.get("action", "")
        reason = decision.get("reason", "")
        idx = decision.get("target_index", 0)
        conf = decision.get("confidence", 0.0)

        action_names = {
            "choose_card": "Chọn Thẻ Bài",
            "choose_event_option": "Chọn Lựa Chọn Sự Kiện",
            "choose_island": "Chọn Đảo Bản Đồ",
            "wait": "Quét Giao Diện: Chờ Hoạt Cảnh",
            "tap": "Quét Giao Diện: Chạm Phục Hồi",
            "stop": "Quét Giao Diện: Dừng An Toàn"
        }
        name = action_names.get(action, action.upper() if action else "Chiến Thuật Cục Bộ")
        desc = decision.get("description", "")
        if action in ("wait", "tap", "stop"):
            text = f"👁️ [{name}] {desc} (Độ tin cậy: {int(conf * 100)}%)\n💬 Chỉ dẫn: {reason}"
        else:
            text = f"🎯 [{name}] Mục tiêu: Số {idx + 1} (Độ tin cậy: {int(conf * 100)}%)\n💬 Lý do: {reason}"

        def _update():
            if hasattr(self, "lbl_ai_reason"):
                self.lbl_ai_reason.configure(text=text)
        self.root.after(0, _update)

    def _on_window_closing(self):
        if self.engine.is_running:
            self.engine.stop(reason="Đóng cửa sổ GUI")
        self.root.destroy()


def main(args=None):
    root = ctk.CTk()
    app = BotGUI(root)
    if args:
        if getattr(args, "mode", None):
            mode_map = {
                "chaos": Mode.CHAOS.value,
                "progress": Mode.PROGRESS.value,
                "story": Mode.STORY.value,
                "replay": Mode.REPLAY.value,
            }
            if args.mode in mode_map:
                app.mode_var.set(mode_map[args.mode])
        if getattr(args, "strategy", None):
            app.strategy_var.set(args.strategy)
        if getattr(args, "auto_start", False):
            app.auto_start_var.set(True)
        if getattr(args, "recovery", False):
            app.recovery_var.set(True)
        if getattr(args, "start", False):
            def _auto_start(ok):
                if ok:
                    root.after(600, app._on_start_clicked)
            root.after(400, lambda: app._on_connect_clicked(on_done=_auto_start))
    root.mainloop()


if __name__ == "__main__":
    main()
