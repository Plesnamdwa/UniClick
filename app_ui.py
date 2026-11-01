import tkinter as tk
from tkinter import messagebox, simpledialog
import customtkinter as ctk
import time
import queue
from typing import Optional

from engine import AutoClickerEngine
from hotkeys import GlobalHotkeyManager, get_current_mouse_pos, get_monitor_bounds_at, play_sound, play_tone
from profile_manager import ProfileManager
from target_pin import TargetPinManager, SnipeCursorOverlay
from theme import T
from toast import ToastManager
from ui_widgets import CollapsibleSection

# Modern visual theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class UniClickApp(ctk.CTk):
    """Desktop GUI for UniClick with Multi-Target Sequence & Tactical Pins."""

    def __init__(self):
        super().__init__()

        self.title("UniClick - Multi-Target Sequence & Timer")
        self.geometry("1040x820")
        self.minsize(920, 700)
        self.configure(fg_color=T.BG)

        self.toast = ToastManager(self)
        self._pulse_on = False
        self._pulse_job = None
        self._closing = False

        # Thread-safe event queue for zero-lag decoupled GUI updates
        self._event_queue = queue.Queue()

        # Core engine & data
        self.engine = AutoClickerEngine()
        self.profile_mgr = ProfileManager()
        self.current_profile_name = "Default Profile"

        # Interactive Target Pin Manager (Draggable circular screen reticles)
        self.pin_mgr = TargetPinManager(
            parent=self,
            on_pin_moved=self._on_pin_dragged,
            on_pin_wheel_delay=self._on_pin_wheel_delay,
            on_pin_delete=self._cmd_delete_point,
        )
        self._snipe_overlay: Optional[SnipeCursorOverlay] = None
        self._is_mini_mode = False
        self._mini_job = None
        self._pre_mini_topmost = False
        self._saved_geometry = "1040x820"

        # Wire engine callbacks into thread-safe queue (zero Tcl lock contention)
        self.engine.on_status_change = lambda st: self._event_queue.put(("status", st))
        self.engine.on_step = lambda step, total, pt: self._event_queue.put(("step", (step, total, pt)))
        self.engine.on_cycle = lambda cyc: self._event_queue.put(("cycle", cyc))
        self.engine.on_tick = lambda rem, el: self._event_queue.put(("tick", (rem, el)))
        self.engine.on_log = lambda msg: self._event_queue.put(("log", msg))

        # Wire global hotkeys into thread-safe queue
        self.hotkeys = GlobalHotkeyManager(
            on_toggle_start=lambda: self._event_queue.put(("hotkey_start", None)),
            on_capture_point=lambda x, y: self._event_queue.put(("hotkey_capture", (x, y))),
            on_emergency_stop=lambda: self._event_queue.put(("hotkey_stop", None)),
        )
        self.hotkeys.start()

        # UI widget references for live updates without full rebuilds
        self.point_widgets = []
        self._coord_labels = {}
        self._delay_vars = {}
        self._label_vars = {}

        # Build UI layout
        self._build_header()
        self._build_hotkey_banner()
        self._build_main_content()
        self._build_mini_bar()

        # Load initial profile
        self._load_initial_profile()
        self._ui_ready = True

        # Start live cursor coordinate tracker loop
        self._update_cursor_tracker()

        # Start thread-safe event queue consumer (dispatches on main UI thread)
        self._drain_event_queue()

        # Clean exit handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -----------------------------
    # UI Building (Header & Hotkey Banner)
    # -----------------------------
    def _build_header(self):
        self.header_frame = ctk.CTkFrame(
            self,
            corner_radius=T.RADIUS,
            fg_color=T.SURFACE,
            border_width=1,
            border_color=T.BORDER,
        )
        self.header_frame.pack(fill="x", padx=T.PAD, pady=(T.PAD, 6))

        top_row = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=T.PAD, pady=(T.PAD - 2, 6))

        # Status pill: [ dot  Label ]
        idle_bg, idle_fg, idle_label = T.STATUS["IDLE"]
        self.status_badge = ctk.CTkFrame(top_row, fg_color=idle_bg, corner_radius=20)
        self.status_badge.pack(side="left", padx=(0, 14))
        self.status_dot = ctk.CTkLabel(
            self.status_badge, text="●", width=16,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=14),
            text_color=idle_fg,
        )
        self.status_dot.pack(side="left", padx=(12, 2), pady=6)
        self.status_text = ctk.CTkLabel(
            self.status_badge, text=idle_label,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=13, weight="bold"),
            text_color=idle_fg,
        )
        self.status_text.pack(side="left", padx=(0, 14), pady=6)

        # Live stats: big timer + small telemetry line
        stats_frame = ctk.CTkFrame(top_row, fg_color="transparent")
        stats_frame.pack(side="left", padx=4)

        self.lbl_countdown = ctk.CTkLabel(
            stats_frame,
            text="⏳ Timer: Ready",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=18, weight="bold"),
            text_color=T.TEXT,
        )
        self.lbl_countdown.pack(anchor="w")

        self.lbl_cycles = ctk.CTkLabel(
            stats_frame,
            text="🔄 Cycle: #0   |   🎯 Step: 0/0   |   ⚡ Clicks: 0",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=12),
            text_color=T.TEXT_MUTED,
        )
        self.lbl_cycles.pack(anchor="w")

        # Control buttons (right side)
        btn_frame = ctk.CTkFrame(top_row, fg_color="transparent")
        btn_frame.pack(side="right")

        self.var_topmost = ctk.BooleanVar(value=False)
        self.Switch_topmost = ctk.CTkSwitch(
            btn_frame,
            text="Always on Top",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11),
            text_color=T.TEXT_MUTED,
            progress_color=T.PRIMARY,
            variable=self.var_topmost,
            width=40,
            command=self._cmd_toggle_topmost,
        )
        self.Switch_topmost.pack(side="left", padx=(0, 10))

        self.btn_mini = self._make_button(
            btn_frame, "🗕 Mini", "neutral", width=76, command=self._cmd_toggle_mini_mode
        )
        self.btn_mini.pack(side="left", padx=4)

        self.btn_start = self._make_button(
            btn_frame, "▶  Start  F6", "success", width=124, command=self._cmd_start, bold=True
        )
        self.btn_start.pack(side="left", padx=4)

        self.btn_pause = self._make_button(
            btn_frame, "⏸  Pause", "warning", width=94, command=self._cmd_pause, bold=True
        )
        self.btn_pause.configure(state="disabled")
        self.btn_pause.pack(side="left", padx=4)

        self.btn_stop = self._make_button(
            btn_frame, "⏹  Stop  Esc", "danger", width=112, command=self._cmd_stop, bold=True
        )
        self.btn_stop.pack(side="left", padx=(4, 0))

        # Progress bar along bottom of header
        self.progress_bar = ctk.CTkProgressBar(
            self.header_frame,
            height=8,
            corner_radius=4,
            fg_color=T.SURFACE_ALT,
            progress_color=T.SUCCESS,
        )
        self.progress_bar.pack(fill="x", padx=T.PAD, pady=(2, T.PAD - 2))
        self.progress_bar.set(0.0)

    def _make_button(self, parent, text, kind="neutral", width=100, command=None, bold=False, height=36):
        """Consistent button factory. kind: primary | success | warning | danger | teal | neutral."""
        palette = {
            "primary": (T.PRIMARY, T.PRIMARY_HOVER, T.TEXT_ON_PRIMARY),
            "success": (T.SUCCESS, T.SUCCESS_HOVER, T.TEXT_ON_SUCCESS),
            "warning": (T.WARNING, T.WARNING_HOVER, T.TEXT_ON_WARNING),
            "danger": (T.DANGER, T.DANGER_HOVER, T.TEXT_ON_DANGER),
            "teal": (T.TEAL, T.TEAL_HOVER, T.TEXT_ON_TEAL),
            "neutral": (T.NEUTRAL, T.NEUTRAL_HOVER, T.TEXT),
            "ghost": ("transparent", T.SURFACE_HOVER, T.TEXT_MUTED),
            "ghost_danger": ("transparent", T.DANGER_SUBTLE, T.DANGER),
        }
        fg, hover, txt = palette.get(kind, palette["neutral"])
        return ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=height,
            corner_radius=T.RADIUS_SM + 2,
            fg_color=fg,
            hover_color=hover,
            text_color=txt,
            text_color_disabled=T.TEXT_DIM,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=13 if bold else 12, weight="bold" if bold else "normal"),
            command=command,
        )

    def _build_hotkey_banner(self):
        self.banner_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.banner_frame.pack(fill="x", padx=T.PAD, pady=(0, 4))

        tips = [
            ("F6", "Start / Pause"),
            ("F7", "Drop pin at cursor"),
            ("Esc", "Emergency stop"),
            ("Scroll on pin", "Delay ±0.1s"),
            ("Right-click pin", "Delete"),
        ]

        for key, desc in tips:
            tip = ctk.CTkFrame(self.banner_frame, fg_color="transparent")
            tip.pack(side="left", padx=(0, 12))
            # Keycap look
            cap = ctk.CTkFrame(
                tip, fg_color=T.SURFACE_ALT, corner_radius=6, border_width=1, border_color=T.BORDER
            )
            cap.pack(side="left")
            ctk.CTkLabel(
                cap, text=key,
                font=ctk.CTkFont(family=T.MONO_FAMILY, size=11, weight="bold"),
                text_color=T.PRIMARY,
            ).pack(padx=7, pady=1)
            ctk.CTkLabel(
                tip, text=desc,
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=11),
                text_color=T.TEXT_MUTED,
            ).pack(side="left", padx=(5, 0))

        # Live multi-monitor cursor readout
        self.lbl_live_cursor = ctk.CTkLabel(
            self.banner_frame,
            text="📍 X: 0, Y: 0",
            font=ctk.CTkFont(family=T.MONO_FAMILY, size=11, weight="bold"),
            text_color=T.SUCCESS,
        )
        self.lbl_live_cursor.pack(side="right", padx=4)

    def _build_main_content(self):
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.pack(fill="both", expand=True, padx=T.PAD, pady=(4, T.PAD))

        # Left: Multi-Target Click Sequence
        left_frame = ctk.CTkFrame(self.main_content, corner_radius=T.RADIUS, fg_color=T.SURFACE, border_width=1, border_color=T.BORDER)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 7))

        q_header = ctk.CTkFrame(left_frame, fg_color="transparent")
        q_header.pack(fill="x", padx=T.PAD, pady=(T.PAD - 2, 2))

        title_col = ctk.CTkFrame(q_header, fg_color="transparent")
        title_col.pack(side="left")

        title_row = ctk.CTkFrame(title_col, fg_color="transparent")
        title_row.pack(anchor="w")
        self.lbl_seq_title = ctk.CTkLabel(
            title_row,
            text="Multi-Target Click Sequence",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=15, weight="bold"),
            text_color=T.TEXT,
        )
        self.lbl_seq_title.pack(side="left")
        self.lbl_seq_count = ctk.CTkLabel(
            title_row,
            text="0 targets",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11, weight="bold"),
            fg_color=T.SURFACE_ALT,
            text_color=T.TEXT_MUTED,
            corner_radius=10,
            padx=8,
            pady=1,
        )
        self.lbl_seq_count.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            title_col,
            text="Clicks run top to bottom, then loop back to #1",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11),
            text_color=T.TEXT_DIM,
        ).pack(anchor="w")

        btn_gather = self._make_button(
            q_header, "📍 Gather pins here", "ghost", width=124, height=28,
            command=self._cmd_gather_pins_to_current_monitor,
        )
        btn_gather.pack(side="right")

        # Scrollable points list
        self.queue_scroll = ctk.CTkScrollableFrame(
            left_frame,
            label_text="",
            fg_color="transparent",
            scrollbar_button_color=T.NEUTRAL,
            scrollbar_button_hover_color=T.NEUTRAL_HOVER,
        )
        self.queue_scroll.pack(fill="both", expand=True, padx=T.PAD_SM, pady=4)

        # Sequence toolbar
        q_toolbar = ctk.CTkFrame(left_frame, fg_color="transparent")
        q_toolbar.pack(fill="x", padx=T.PAD, pady=(4, T.PAD))

        btn_snipe = self._make_button(
            q_toolbar, "🕵️  Snipe on Screen", "teal", width=150, command=self._cmd_start_snipe_mode, bold=True
        )
        btn_snipe.pack(side="left", padx=(0, 6))

        btn_add_pin = self._make_button(
            q_toolbar, "＋  Spawn Pin", "primary", width=116, command=self._cmd_spawn_new_target_pin, bold=True
        )
        btn_add_pin.pack(side="left", padx=6)

        self.btn_toggle_pins = self._make_button(
            q_toolbar, "👁  Hide pins", "ghost", width=96, command=self._cmd_toggle_pins
        )
        self.btn_toggle_pins.pack(side="left", padx=6)

        btn_clear = self._make_button(
            q_toolbar, "🗑  Clear all", "ghost_danger", width=96, command=self._cmd_clear_points
        )
        btn_clear.pack(side="right")

        # Right: Settings, Anti-Detection, Profiles, Logs (collapsible sections)
        right_frame = ctk.CTkFrame(
            self.main_content, width=385, corner_radius=T.RADIUS,
            fg_color=T.SURFACE, border_width=1, border_color=T.BORDER,
        )
        right_frame.pack(side="right", fill="both", padx=(8, 0))
        right_frame.pack_propagate(False)

        right_scroll = ctk.CTkScrollableFrame(
            right_frame, label_text="", fg_color="transparent",
            scrollbar_button_color=T.NEUTRAL, scrollbar_button_hover_color=T.NEUTRAL_HOVER,
        )
        right_scroll.pack(fill="both", expand=True, padx=6, pady=6)

        # 1. Interval & humanizer
        self.sec_interval = CollapsibleSection(right_scroll, "Click Interval", "⏱️", expanded=True)
        self.sec_interval.pack(fill="x", pady=5, padx=2)
        b = self.sec_interval.body

        row = self._setting_row(b)
        ctk.CTkLabel(row, text="Default delay (seconds)", font=ctk.CTkFont(family=T.FONT_FAMILY, size=12),
                     text_color=T.TEXT).pack(side="left")
        self.entry_default_delay = self._entry(row, "1.0")
        self.entry_default_delay.pack(side="right")

        row = self._setting_row(b)
        self.var_use_jitter = ctk.BooleanVar(value=False)
        self.chk_jitter = self._switch(row, "Time jitter (± s)", self.var_use_jitter)
        self.chk_jitter.pack(side="left")
        self.entry_jitter = self._entry(row, "0.05")
        self.entry_jitter.pack(side="right")

        row = self._setting_row(b)
        self.var_use_px_jitter = ctk.BooleanVar(value=False)
        self.chk_px_jitter = self._switch(row, "Click radius (± px)", self.var_use_px_jitter)
        self.chk_px_jitter.pack(side="left")
        self.entry_px_jitter = self._entry(row, "4")
        self.entry_px_jitter.pack(side="right")

        row = self._setting_row(b)
        self.var_restore_cursor = ctk.BooleanVar(value=False)
        self.chk_restore_cursor = self._switch(row, "👻 Ghost click (return cursor)", self.var_restore_cursor)
        self.chk_restore_cursor.pack(side="left")

        # 2. Active timer
        self.sec_timer = CollapsibleSection(right_scroll, "Active Timer", "⏳", expanded=True)
        self.sec_timer.pack(fill="x", pady=5, padx=2)
        b = self.sec_timer.body

        row = self._setting_row(b)
        self.var_use_duration = ctk.BooleanVar(value=False)
        self.chk_duration = self._switch(row, "Auto-stop after", self.var_use_duration)
        self.chk_duration.pack(side="left")
        self.entry_duration = self._entry(row, "60.0")
        self.entry_duration.pack(side="right")
        ctk.CTkLabel(row, text="s", font=ctk.CTkFont(size=11), text_color=T.TEXT_DIM).pack(side="right", padx=(0, 4))

        chips = self._setting_row(b)
        for label_txt, secs in [("30s", 30), ("1m", 60), ("5m", 300), ("15m", 900), ("30m", 1800)]:
            self._chip(chips, label_txt, lambda s=secs: self._set_quick_duration(s)).pack(side="left", padx=(0, 5))

        # 3. Repeat cycles
        self.sec_cycles = CollapsibleSection(right_scroll, "Repeat Cycles", "🔁", expanded=False)
        self.sec_cycles.pack(fill="x", pady=5, padx=2)
        b = self.sec_cycles.body

        row = self._setting_row(b)
        self.var_use_cycles = ctk.BooleanVar(value=False)
        self.chk_cycles = self._switch(row, "Stop after cycles", self.var_use_cycles)
        self.chk_cycles.pack(side="left")
        self.entry_max_cycles = self._entry(row, "10")
        self.entry_max_cycles.pack(side="right")

        chips = self._setting_row(b)
        for label_txt, cyc in [("5x", 5), ("10x", 10), ("25x", 25), ("50x", 50), ("100x", 100)]:
            self._chip(chips, label_txt, lambda c=cyc: self._set_quick_cycles(c)).pack(side="left", padx=(0, 5))

        # 4. Profiles
        self.sec_profiles = CollapsibleSection(right_scroll, "Profiles & Presets", "💾", expanded=True)
        self.sec_profiles.pack(fill="x", pady=5, padx=2)
        b = self.sec_profiles.body

        row = self._setting_row(b)
        self.combo_profiles = ctk.CTkComboBox(
            row,
            values=self._get_profile_list(),
            height=30,
            corner_radius=T.RADIUS_SM,
            fg_color=T.SURFACE,
            border_color=T.BORDER,
            button_color=T.NEUTRAL,
            button_hover_color=T.NEUTRAL_HOVER,
            dropdown_fg_color=T.SURFACE_ALT,
            dropdown_hover_color=T.SURFACE_HOVER,
            text_color=T.TEXT,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=12),
        )
        self.combo_profiles.set(self.current_profile_name)
        self.combo_profiles.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._make_button(row, "Load", "neutral", width=60, height=30,
                          command=self._cmd_load_selected_profile).pack(side="right")

        row = self._setting_row(b)
        self._make_button(row, "💾  Save preset", "primary", width=150, height=32, bold=True,
                          command=self._cmd_save_profile).pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._make_button(row, "Delete", "ghost_danger", width=70, height=32,
                          command=self._cmd_delete_profile).pack(side="right")

        # 5. Activity log
        self.sec_log = CollapsibleSection(right_scroll, "Activity Log", "📜", expanded=True)
        self.sec_log.pack(fill="x", pady=5, padx=2)
        b = self.sec_log.body

        self.txt_log = ctk.CTkTextbox(
            b, height=150, corner_radius=T.RADIUS_SM,
            fg_color=T.BG, border_width=1, border_color=T.BORDER,
            text_color=T.TEXT_MUTED, wrap="word",
            font=ctk.CTkFont(family=T.MONO_FAMILY, size=11),
        )
        self.txt_log.pack(fill="x")
        tb = self.txt_log._textbox
        for tag, color in [
            ("time", T.TEXT_DIM), ("cycle", T.TEXT_DIM), ("click", T.TEXT_MUTED), ("info", T.TEXT),
            ("success", T.SUCCESS), ("warn", T.WARNING), ("done", T.PRIMARY), ("error", T.DANGER),
        ]:
            tb.tag_config(tag, foreground=color)

        self._make_button(
            b, "Clear log", "ghost", width=80, height=24,
            command=lambda: self.txt_log.delete("1.0", "end"),
        ).pack(anchor="e", pady=(6, 0))

    # ---- small widget helpers (settings panel) ----
    def _setting_row(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        return row

    def _entry(self, parent, default: str, width: int = 72):
        e = ctk.CTkEntry(
            parent, width=width, height=28, corner_radius=T.RADIUS_SM,
            fg_color=T.SURFACE, border_color=T.BORDER, justify="center",
            text_color=T.TEXT, font=ctk.CTkFont(family=T.MONO_FAMILY, size=12),
        )
        e.insert(0, default)
        return e

    def _switch(self, parent, text: str, var):
        return ctk.CTkSwitch(
            parent, text=text, variable=var,
            switch_width=34, switch_height=16,
            progress_color=T.PRIMARY, text_color=T.TEXT,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=12),
        )

    def _chip(self, parent, text: str, command):
        return ctk.CTkButton(
            parent, text=text, width=44, height=24, corner_radius=T.RADIUS_SM,
            fg_color=T.SURFACE, hover_color=T.NEUTRAL, text_color=T.TEXT_MUTED,
            border_width=1, border_color=T.BORDER,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11), command=command,
        )

    @staticmethod
    def _format_secs(seconds: float) -> str:
        s = int(round(seconds))
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}h {m:02d}m"
        if m:
            return f"{m}m {sec:02d}s" if sec else f"{m}m"
        return f"{sec}s"

    def _refresh_section_summaries(self):
        """Keep each collapsed header informative. set_summary only redraws on change."""
        try:
            delay = float(self.entry_default_delay.get())
            txt = f"{delay:g}s"
            if self.var_use_jitter.get() or self.var_use_px_jitter.get():
                txt += " · humanized"
            if self.var_restore_cursor.get():
                txt += " · ghost"
            self.sec_interval.set_summary(txt)
        except Exception:
            self.sec_interval.set_summary("")
        try:
            if self.var_use_duration.get():
                self.sec_timer.set_summary(self._format_secs(float(self.entry_duration.get())), T.SUCCESS)
            else:
                self.sec_timer.set_summary("Off")
        except Exception:
            self.sec_timer.set_summary("")
        try:
            if self.var_use_cycles.get():
                self.sec_cycles.set_summary(f"{int(float(self.entry_max_cycles.get()))}×", T.SUCCESS)
            else:
                self.sec_cycles.set_summary("Off")
        except Exception:
            self.sec_cycles.set_summary("")
        self.sec_profiles.set_summary(self.current_profile_name if len(self.current_profile_name) < 22
                                      else self.current_profile_name[:20] + "…")

    # ---- Mini mode bar ----
    def _build_mini_bar(self):
        self.mini_bar = ctk.CTkFrame(
            self, corner_radius=T.RADIUS, fg_color=T.SURFACE, border_width=1, border_color=T.BORDER
        )
        top = ctk.CTkFrame(self.mini_bar, fg_color="transparent")
        top.pack(fill="x", padx=T.PAD_SM + 2, pady=(T.PAD_SM + 2, 4))

        self.mini_dot = ctk.CTkLabel(top, text="●", width=14, font=ctk.CTkFont(size=14), text_color=T.TEXT_MUTED)
        self.mini_dot.pack(side="left")
        self.mini_status = ctk.CTkLabel(
            top, text="Ready", width=70, anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=12, weight="bold"), text_color=T.TEXT_MUTED,
        )
        self.mini_status.pack(side="left", padx=(2, 8))
        self.mini_timer = ctk.CTkLabel(
            top, text="", anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=14, weight="bold"), text_color=T.TEXT,
        )
        self.mini_timer.pack(side="left", fill="x", expand=True)

        self.mini_btn_expand = self._make_button(top, "⤢", "ghost", width=32, height=30, command=self._cmd_toggle_mini_mode)
        self.mini_btn_expand.pack(side="right", padx=(4, 0))
        self.mini_btn_stop = self._make_button(top, "⏹", "danger", width=38, height=30, command=self._cmd_stop, bold=True)
        self.mini_btn_stop.pack(side="right", padx=2)
        self.mini_btn_pause = self._make_button(top, "⏸", "warning", width=38, height=30, command=self._cmd_pause, bold=True)
        self.mini_btn_pause.pack(side="right", padx=2)
        self.mini_btn_start = self._make_button(top, "▶", "success", width=38, height=30, command=self._cmd_start, bold=True)
        self.mini_btn_start.pack(side="right", padx=2)

        self.mini_progress = ctk.CTkProgressBar(
            self.mini_bar, height=6, corner_radius=3, fg_color=T.SURFACE_ALT, progress_color=T.SUCCESS
        )
        self.mini_progress.pack(fill="x", padx=T.PAD_SM + 4, pady=(0, T.PAD_SM + 2))
        self.mini_progress.set(0)

    def _mini_sync(self):
        """While in mini mode, mirror the (hidden) header state into the compact bar."""
        if not self._is_mini_mode:
            self._mini_job = None
            return
        try:
            self.mini_dot.configure(text_color=self.status_dot.cget("text_color"))
            self.mini_status.configure(
                text=self.status_text.cget("text"), text_color=self.status_text.cget("text_color")
            )
            self.mini_timer.configure(text=self.lbl_countdown.cget("text"))
            self.mini_progress.set(self.progress_bar.get())
            self.mini_progress.configure(progress_color=self.progress_bar.cget("progress_color"))
            st = self.engine.status
            active = st in ("RUNNING", "PAUSED")
            self.mini_btn_start.configure(state="disabled" if active else "normal")
            self.mini_btn_pause.configure(
                state="normal" if active else "disabled", text="▶" if st == "PAUSED" else "⏸"
            )
        except Exception:
            pass
        self._mini_job = self.after(140, self._mini_sync)

    # -----------------------------
    # Interactive Target Pins & Sequence List Rendering
    # -----------------------------
    def _render_points_list(self):
        """Re-renders all target items and syncs on-screen circular pins."""
        for w in self.queue_scroll.winfo_children():
            w.destroy()
        self.point_widgets.clear()
        self._coord_labels.clear()
        self._delay_vars.clear()
        self._label_vars.clear()

        total = len(self.engine.points)
        active_cnt = sum(1 for p in self.engine.points if p.get("enabled", True))
        if total == 0:
            self.lbl_seq_count.configure(text="0 targets", text_color=T.TEXT_MUTED, fg_color=T.SURFACE_ALT)
        else:
            self.lbl_seq_count.configure(
                text=f"{active_cnt}/{total} active",
                text_color=T.SUCCESS if active_cnt == total else T.WARNING,
                fg_color=T.SURFACE_ALT,
            )

        # Sync on-screen draggable visual pins
        self.pin_mgr.sync_points(self.engine.points)

        if not self.engine.points:
            self._render_empty_state()
            return

        for idx, pt in enumerate(self.engine.points):
            self._render_single_point_row(idx, total, pt)

    def _render_empty_state(self):
        box = ctk.CTkFrame(self.queue_scroll, fg_color="transparent")
        box.pack(fill="x", pady=(34, 10))

        ctk.CTkLabel(box, text="🎯", font=ctk.CTkFont(size=44)).pack()
        ctk.CTkLabel(
            box, text="No targets yet",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=17, weight="bold"),
            text_color=T.TEXT,
        ).pack(pady=(6, 2))
        ctk.CTkLabel(
            box, text="Add the buttons you want clicked, in order.",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=12),
            text_color=T.TEXT_MUTED,
        ).pack()

        tips = ctk.CTkFrame(box, fg_color=T.SURFACE_ALT, corner_radius=T.RADIUS)
        tips.pack(pady=16, padx=40)
        for key, text in [
            ("Snipe", "click anywhere on screen to drop a pin"),
            ("F7", "drop a pin right under your cursor"),
            ("Spawn", "place a pin, then drag it onto the button"),
        ]:
            line = ctk.CTkFrame(tips, fg_color="transparent")
            line.pack(anchor="w", padx=14, pady=4)
            ctk.CTkLabel(
                line, text=key, width=52,
                font=ctk.CTkFont(family=T.MONO_FAMILY, size=11, weight="bold"),
                fg_color=T.SURFACE, text_color=T.PRIMARY, corner_radius=6,
            ).pack(side="left")
            ctk.CTkLabel(
                line, text=text,
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=12),
                text_color=T.TEXT_MUTED,
            ).pack(side="left", padx=(8, 0))

        cta = ctk.CTkFrame(box, fg_color="transparent")
        cta.pack()
        self._make_button(
            cta, "🕵️  Snipe on Screen", "teal", width=160, command=self._cmd_start_snipe_mode, bold=True
        ).pack(side="left", padx=5)
        self._make_button(
            cta, "＋  Spawn Pin", "primary", width=120, command=self._cmd_spawn_new_target_pin, bold=True
        ).pack(side="left", padx=5)

    def _get_step_badge_color(self, index: int, total: int, enabled: bool) -> str:
        if not enabled:
            return T.NEUTRAL
        if index == 0:
            return T.SUCCESS  # first step
        if total > 1 and index == total - 1:
            return T.WARNING  # last step (loops back)
        return T.PRIMARY

    @staticmethod
    def _fmt_coord(x, y) -> str:
        return f"X {x}  ·  Y {y}"

    def _bind_card_hover(self, row, index: int, enabled: bool):
        """Hover a card -> lift its color and highlight its pin on screen. Flicker-free for child widgets."""
        base = T.SURFACE_ALT if enabled else T.BG
        hover = T.SURFACE_HOVER if enabled else T.SURFACE

        def on_enter(_e=None):
            try:
                row.configure(fg_color=hover)
            except Exception:
                return
            self.pin_mgr.highlight_pin(index)

        def on_leave(_e=None):
            try:
                px, py = row.winfo_pointerxy()
                x0, y0 = row.winfo_rootx(), row.winfo_rooty()
                inside = x0 <= px < x0 + row.winfo_width() and y0 <= py < y0 + row.winfo_height()
            except Exception:
                inside = False
            if not inside:
                try:
                    row.configure(fg_color=base)
                except Exception:
                    return
                self.pin_mgr.highlight_pin(None)

        def bind_tree(w):
            try:
                w.bind("<Enter>", on_enter, add="+")
                w.bind("<Leave>", on_leave, add="+")
            except Exception:
                pass
            for child in w.winfo_children():
                bind_tree(child)

        bind_tree(row)

    def _icon_button(self, parent, text, command, hover=None, color=None, width=28):
        """Flat icon button for secondary card actions."""
        return ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=26,
            corner_radius=T.RADIUS_SM,
            fg_color="transparent",
            hover_color=hover or T.NEUTRAL,
            text_color=color or T.TEXT_MUTED,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=13),
            command=command,
        )

    def _option_menu(self, parent, values, current, width, command):
        menu = ctk.CTkOptionMenu(
            parent,
            values=values,
            width=width,
            height=26,
            corner_radius=T.RADIUS_SM,
            fg_color=T.SURFACE,
            button_color=T.NEUTRAL,
            button_hover_color=T.NEUTRAL_HOVER,
            dropdown_fg_color=T.SURFACE_ALT,
            dropdown_hover_color=T.SURFACE_HOVER,
            text_color=T.TEXT,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=12),
            dropdown_font=ctk.CTkFont(family=T.FONT_FAMILY, size=12),
            command=command,
        )
        menu.set(current)
        return menu

    def _render_single_point_row(self, index: int, total: int, pt: dict):
        step_num = index + 1
        enabled = bool(pt.get("enabled", True))

        row = ctk.CTkFrame(
            self.queue_scroll,
            corner_radius=T.RADIUS,
            fg_color=T.SURFACE_ALT if enabled else T.BG,
            border_width=1,
            border_color=T.BORDER,
        )
        row.pack(fill="x", pady=4, padx=4)
        row.grid_columnconfigure(1, weight=1)

        # Left: step badge + enable toggle
        left_col = ctk.CTkFrame(row, fg_color="transparent")
        left_col.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=10)

        badge = ctk.CTkLabel(
            left_col,
            text=f"{step_num}",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=14, weight="bold"),
            fg_color=self._get_step_badge_color(index, total, enabled),
            text_color=T.TEXT_ON_PRIMARY if enabled else T.TEXT_MUTED,
            corner_radius=16,
            width=32,
            height=32,
        )
        badge.pack()

        en_var = ctk.BooleanVar(value=enabled)
        chk_en = ctk.CTkSwitch(
            left_col,
            text="",
            variable=en_var,
            width=34,
            switch_width=30,
            switch_height=14,
            progress_color=T.SUCCESS,
            command=lambda i=index, v=en_var: self._cmd_toggle_point_enabled(i, v.get()),
        )
        chk_en.pack(pady=(6, 0))

        # Top line: name (editable)
        lbl_var = tk.StringVar(value=pt.get("label", f"Target #{step_num}"))
        self._label_vars[index] = lbl_var
        ent_lbl = ctk.CTkEntry(
            row,
            textvariable=lbl_var,
            height=28,
            corner_radius=T.RADIUS_SM,
            fg_color="transparent",
            border_width=0,
            text_color=T.TEXT if enabled else T.TEXT_MUTED,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=14, weight="bold"),
        )
        ent_lbl.grid(row=0, column=1, padx=(0, 6), pady=(10, 0), sticky="ew")
        ent_lbl.bind("<KeyRelease>", lambda e, i=index, v=lbl_var: self._update_pt_prop(i, "label", v.get()))

        # Bottom line: coords + delay + click type + burst
        meta = ctk.CTkFrame(row, fg_color="transparent")
        meta.grid(row=1, column=1, padx=(0, 6), pady=(0, 10), sticky="w")

        lbl_coord = ctk.CTkLabel(
            meta,
            text=self._fmt_coord(pt.get("x", 0), pt.get("y", 0)),
            font=ctk.CTkFont(family=T.MONO_FAMILY, size=11),
            text_color=T.PRIMARY if enabled else T.TEXT_DIM,
        )
        lbl_coord.pack(side="left", padx=(8, 12))
        self._coord_labels[index] = lbl_coord

        delay_val = pt.get("delay", 1.0)
        delay_var = tk.StringVar(value=f"{delay_val:.2f}" if delay_val is not None else "1.00")
        self._delay_vars[index] = delay_var
        ctk.CTkLabel(meta, text="⏱", font=ctk.CTkFont(size=12), text_color=T.TEXT_DIM).pack(side="left")
        ent_delay = ctk.CTkEntry(
            meta,
            textvariable=delay_var,
            width=54,
            height=26,
            corner_radius=T.RADIUS_SM,
            fg_color=T.SURFACE,
            border_color=T.BORDER,
            justify="center",
            font=ctk.CTkFont(family=T.MONO_FAMILY, size=12),
        )
        ent_delay.pack(side="left", padx=(3, 2))
        ctk.CTkLabel(meta, text="s", font=ctk.CTkFont(size=11), text_color=T.TEXT_DIM).pack(side="left", padx=(0, 10))
        ent_delay.bind("<KeyRelease>", lambda e, i=index, v=delay_var: self._update_pt_delay(i, v.get()))

        click_type = pt.get("click_type", "left")
        click_labels = {"left": "Left", "double": "Double", "right": "Right"}
        self._option_menu(
            meta,
            ["Left", "Double", "Right"],
            click_labels.get(click_type, "Left"),
            76,
            lambda val, i=index: self._update_pt_prop(i, "click_type", val.lower()),
        ).pack(side="left", padx=(0, 6))

        repeat_cnt = max(1, int(pt.get("repeat", 1)))
        self._option_menu(
            meta,
            ["x1", "x2", "x3", "x5", "x10"],
            f"x{repeat_cnt}",
            62,
            lambda val, i=index: self._update_pt_prop(i, "repeat", int(val.replace("x", ""))),
        ).pack(side="left")

        # Right: actions
        f_actions = ctk.CTkFrame(row, fg_color="transparent")
        f_actions.grid(row=0, column=2, rowspan=2, padx=(0, 8), pady=8, sticky="e")

        top_actions = ctk.CTkFrame(f_actions, fg_color="transparent")
        top_actions.pack()
        self._icon_button(top_actions, "🎯", lambda i=index: self._cmd_test_single_point(i),
                          hover=T.TEAL_HOVER, color=T.TEAL).pack(side="left", padx=1)
        self._icon_button(top_actions, "⧉", lambda i=index: self._cmd_duplicate_point(i)).pack(side="left", padx=1)
        self._icon_button(top_actions, "✕", lambda i=index: self._cmd_delete_point(i),
                          hover=T.DANGER_SUBTLE_HOVER, color=T.DANGER).pack(side="left", padx=1)

        move_actions = ctk.CTkFrame(f_actions, fg_color="transparent")
        move_actions.pack(pady=(2, 0))
        self._icon_button(move_actions, "▲", lambda i=index: self._cmd_move_point_up(i), width=40).pack(side="left", padx=1)
        self._icon_button(move_actions, "▼", lambda i=index: self._cmd_move_point_down(i), width=40).pack(side="left", padx=1)

        self._bind_card_hover(row, index, enabled)
        self.point_widgets.append(row)

    def _on_pin_dragged(self, index: int, x: int, y: int):
        """Called live as the user drags a circular pin across any monitor."""
        if 0 <= index < len(self.engine.points):
            self.engine.points[index]["x"] = x
            self.engine.points[index]["y"] = y
            if index in self._coord_labels:
                self._coord_labels[index].configure(text=self._fmt_coord(x, y))

    def _on_pin_wheel_delay(self, index: int, new_delay: float):
        """Called when the user scrolls the mouse wheel directly over a screen pin."""
        if 0 <= index < len(self.engine.points):
            self.engine.points[index]["delay"] = new_delay
            if index in self._delay_vars:
                self._delay_vars[index].set(f"{new_delay:.2f}")

    def _cmd_toggle_point_enabled(self, index: int, enabled: bool):
        if 0 <= index < len(self.engine.points):
            self.engine.points[index]["enabled"] = enabled
            self._render_points_list()

    def _update_pt_prop(self, index: int, prop: str, val: any):
        if 0 <= index < len(self.engine.points):
            self.engine.points[index][prop] = val
            if index < len(self.pin_mgr.pins):
                self.pin_mgr.pins[index].sync_metadata(
                    index, len(self.engine.points), self.engine.points[index]
                )

    def _update_pt_delay(self, index: int, val_str: str):
        try:
            val = round(max(0.01, float(val_str)), 2)
            self._update_pt_prop(index, "delay", val)
        except ValueError:
            pass

    # -----------------------------
    # Smart Target Acquisition (Spawn, Snipe, F7, Countdown, Gather)
    # -----------------------------
    def _add_target_at(self, x: int, y: int, label: Optional[str] = None, play_cue: bool = True):
        step_num = len(self.engine.points) + 1
        new_pt = {
            "label": label or f"Target #{step_num}",
            "x": int(x),
            "y": int(y),
            "delay": self._get_default_delay_val(),
            "click_type": "left",
            "repeat": 1,
            "enabled": True
        }
        self.engine.points.append(new_pt)
        self._render_points_list()
        if play_cue:
            play_sound("add")
        self._append_log(f"Target #{step_num} placed at ({x}, {y})")
        self.toast.show(f"Target #{step_num} added", "success", 1400)

    def _cmd_spawn_new_target_pin(self):
        """Spawns a new draggable circular pin near the center of the active monitor (never on top of the button!)."""
        cur_x, cur_y = get_current_mouse_pos()
        left, top, right, bottom = get_monitor_bounds_at(cur_x, cur_y)
        mon_cx = (left + right) // 2
        mon_cy = (top + bottom) // 2

        # Cascade offset so multiple spawned pins form a clean diagonal row near screen center
        idx = len(self.engine.points)
        offset_x = ((idx % 6) - 2) * 55
        offset_y = ((idx // 6) % 4 - 1) * 55
        spawn_x = mon_cx + offset_x
        spawn_y = mon_cy + offset_y

        self._add_target_at(spawn_x, spawn_y)

    def _cmd_start_snipe_mode(self):
        """Activates cross-monitor Snipe Mode: move mouse anywhere and Left-Click to place a pin."""
        if self._snipe_overlay is not None:
            self._snipe_overlay.stop()

        self._append_log("Snipe Mode active: Left-click anywhere on any monitor to place pin.")
        self.toast.show("Snipe mode: left-click anywhere to drop a pin (right-click / Esc to cancel)", "info", 3000)
        self._snipe_overlay = SnipeCursorOverlay(
            parent=self,
            on_picked=self._on_snipe_picked,
            on_cancelled=self._on_snipe_cancelled
        )

    def _on_snipe_picked(self, x: int, y: int):
        self._snipe_overlay = None
        self._add_target_at(x, y, play_cue=False)

    def _on_snipe_cancelled(self):
        self._snipe_overlay = None
        self._append_log("Snipe Mode cancelled.")
        self.toast.show("Snipe cancelled", "info", 1200)

    def _cmd_gather_pins_to_current_monitor(self):
        """Brings all pins neatly to the center of the current monitor if they were on another display."""
        if not self.engine.points:
            return
        cur_x, cur_y = get_current_mouse_pos()
        left, top, right, bottom = get_monitor_bounds_at(cur_x, cur_y)
        mon_cx = (left + right) // 2
        mon_cy = (top + bottom) // 2

        for idx, pt in enumerate(self.engine.points):
            col = (idx % 5) - 2
            row = (idx // 5) - 1
            pt["x"] = mon_cx + col * 65
            pt["y"] = mon_cy + row * 65

        self._render_points_list()
        for p in self.pin_mgr.pins:
            p.animate_pop()
        play_sound("gather")
        self._append_log("Gathered all target pins to the center of current monitor.")
        self.toast.show("Pins gathered to this monitor", "success", 1500)

    def _cmd_toggle_pins(self):
        if self.pin_mgr.visible:
            self.pin_mgr.hide_all()
            self.btn_toggle_pins.configure(text="👁  Show pins")
        else:
            self.pin_mgr.show_all()
            self.btn_toggle_pins.configure(text="👁  Hide pins")

    def _cmd_test_single_point(self, index: int):
        if 0 <= index < len(self.engine.points):
            pt = self.engine.points[index]
            # Temporarily hide pin during test click so click hits window underneath
            if index < len(self.pin_mgr.pins):
                self.pin_mgr.pins[index].hide()
            self.update_idletasks()
            self.engine.perform_click(
                pt["x"], pt["y"], pt.get("click_type", "left"),
                apply_jitter=False, restore_pos=True
            )
            if self.pin_mgr.visible and index < len(self.pin_mgr.pins):
                def _restore_and_flash(i=index, x=pt["x"], y=pt["y"]):
                    if i < len(self.pin_mgr.pins):
                        self.pin_mgr.pins[i].show()
                    self.pin_mgr.flash_click(x, y, i)
                self.after(80, _restore_and_flash)
            else:
                self.pin_mgr.flash_click(pt["x"], pt["y"], index)
            self._append_log(f"Test clicked target #{index+1} at ({pt['x']}, {pt['y']})")

    def _cmd_duplicate_point(self, index: int):
        if 0 <= index < len(self.engine.points):
            orig = self.engine.points[index]
            dup = dict(orig)
            dup["label"] = f"{orig.get('label', 'Target')} (Copy)"
            dup["x"] = int(orig.get("x", 500)) + 40
            dup["y"] = int(orig.get("y", 300)) + 40
            self.engine.points.insert(index + 1, dup)
            self._render_points_list()
            if index + 1 < len(self.pin_mgr.pins):
                self.pin_mgr.pins[index + 1].animate_pop()
            play_sound("add")
            self._append_log(f"Duplicated target #{index + 1}.")

    def _cmd_move_point_up(self, index: int):
        if index > 0:
            self.engine.points[index - 1], self.engine.points[index] = (
                self.engine.points[index],
                self.engine.points[index - 1],
            )
            self._render_points_list()

    def _cmd_move_point_down(self, index: int):
        if index < len(self.engine.points) - 1:
            self.engine.points[index], self.engine.points[index + 1] = (
                self.engine.points[index + 1],
                self.engine.points[index],
            )
            self._render_points_list()

    def _cmd_delete_point(self, index: int):
        if 0 <= index < len(self.engine.points):
            del self.engine.points[index]
            play_sound("delete")
            self._render_points_list()

    def _cmd_clear_points(self):
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear all targets in sequence?"):
            self.engine.points.clear()
            self.pin_mgr.clear()
            play_sound("delete")
            self._render_points_list()
            self._append_log("All sequence targets cleared.")

    # -----------------------------
    # Window Modes (Topmost & Mini Mode)
    # -----------------------------
    def _cmd_toggle_topmost(self):
        is_top = self.var_topmost.get()
        self.wm_attributes("-topmost", is_top)

    def _cmd_toggle_mini_mode(self):
        if not self._is_mini_mode:
            self._saved_geometry = self.geometry()
            self._pre_mini_topmost = bool(self.var_topmost.get())
            for w in (self.header_frame, self.banner_frame, self.main_content):
                w.pack_forget()
            self.mini_bar.pack(fill="both", expand=True, padx=T.PAD_SM, pady=T.PAD_SM)
            self.minsize(430, 84)
            self.geometry("540x88")
            self.var_topmost.set(True)
            self.wm_attributes("-topmost", True)
            self.btn_mini.configure(text="🗖 Full", fg_color=T.PRIMARY, text_color=T.TEXT_ON_PRIMARY)
            self._is_mini_mode = True
            self._mini_sync()
        else:
            self._is_mini_mode = False
            self.mini_bar.pack_forget()
            self.minsize(920, 700)
            self.geometry(self._saved_geometry)
            self.header_frame.pack(fill="x", padx=T.PAD, pady=(T.PAD, 6))
            self.banner_frame.pack(fill="x", padx=T.PAD, pady=(0, 4))
            self.main_content.pack(fill="both", expand=True, padx=T.PAD, pady=(4, T.PAD))
            self.var_topmost.set(self._pre_mini_topmost)
            self.wm_attributes("-topmost", self._pre_mini_topmost)
            self.btn_mini.configure(text="🗕 Mini", fg_color=T.NEUTRAL, text_color=T.TEXT)

    def _set_quick_duration(self, seconds: int):
        self.var_use_duration.set(True)
        self.entry_duration.delete(0, "end")
        self.entry_duration.insert(0, f"{float(seconds):.1f}")

    def _set_quick_cycles(self, cycles: int):
        self.var_use_cycles.set(True)
        self.entry_max_cycles.delete(0, "end")
        self.entry_max_cycles.insert(0, str(cycles))

    def _update_cursor_tracker(self):
        try:
            x, y = get_current_mouse_pos()
            self.lbl_live_cursor.configure(text=f"📍 X: {x}, Y: {y}")
        except Exception:
            pass
        try:
            self._refresh_section_summaries()
        except Exception:
            pass
        self.after(60, self._update_cursor_tracker)

    # -----------------------------
    # Settings & Profiles
    # -----------------------------
    def _get_default_delay_val(self) -> float:
        try:
            return max(0.01, float(self.entry_default_delay.get().strip()))
        except ValueError:
            return 1.0

    def _apply_ui_settings_to_engine(self):
        """Syncs all GUI fields (including per-row StringVars) into the engine before start/save."""
        # Flush per-row StringVars in case user didn't defocus entry
        for idx, pt in enumerate(self.engine.points):
            if idx in self._label_vars:
                pt["label"] = self._label_vars[idx].get().strip() or f"Target #{idx + 1}"
            if idx in self._delay_vars:
                try:
                    pt["delay"] = max(0.01, float(self._delay_vars[idx].get().strip()))
                except ValueError:
                    pass

        try:
            self.engine.default_delay = max(0.01, float(self.entry_default_delay.get().strip()))
        except ValueError:
            self.engine.default_delay = 1.0

        if self.var_use_jitter.get():
            try:
                self.engine.random_jitter = max(0.0, float(self.entry_jitter.get().strip()))
            except ValueError:
                self.engine.random_jitter = 0.05
        else:
            self.engine.random_jitter = 0.0

        if self.var_use_px_jitter.get():
            try:
                self.engine.pixel_jitter = max(0, int(float(self.entry_px_jitter.get().strip())))
            except ValueError:
                self.engine.pixel_jitter = 4
        else:
            self.engine.pixel_jitter = 0

        self.engine.restore_cursor = self.var_restore_cursor.get()

        self.engine.use_duration = self.var_use_duration.get()
        try:
            self.engine.duration_seconds = max(0.1, float(self.entry_duration.get().strip()))
        except ValueError:
            self.engine.duration_seconds = 60.0

        self.engine.use_max_cycles = self.var_use_cycles.get()
        try:
            self.engine.max_cycles = max(1, int(self.entry_max_cycles.get().strip()))
        except ValueError:
            self.engine.max_cycles = 10

    def _get_profile_list(self):
        names = self.profile_mgr.list_profiles()
        if "Default Profile" not in names:
            names.insert(0, "Default Profile")
        return names

    def _load_initial_profile(self):
        try:
            profiles = self.profile_mgr.list_profiles()
            if "Default Profile" in profiles:
                data = self.profile_mgr.load_profile("Default Profile")
            else:
                data = self.profile_mgr.get_default_profile()
                self.profile_mgr.save_profile("Default Profile", data)
            self._apply_profile_data(data)
        except Exception as e:
            self._append_log(f"Error loading initial profile: {e}")

    def _apply_profile_data(self, data: dict):
        self.current_profile_name = data.get("name", "Default Profile")
        self.combo_profiles.set(self.current_profile_name)

        self.entry_default_delay.delete(0, "end")
        self.entry_default_delay.insert(0, str(data.get("default_delay", 1.0)))

        jitter = data.get("random_jitter", 0.05)
        self.var_use_jitter.set(bool(data.get("use_jitter", False)))
        self.entry_jitter.delete(0, "end")
        self.entry_jitter.insert(0, str(jitter if jitter > 0 else 0.05))

        px_jitter = data.get("pixel_jitter", 4)
        self.var_use_px_jitter.set(bool(data.get("use_pixel_jitter", False)))
        self.entry_px_jitter.delete(0, "end")
        self.entry_px_jitter.insert(0, str(px_jitter))

        self.var_restore_cursor.set(bool(data.get("restore_cursor", False)))

        self.var_use_duration.set(bool(data.get("use_duration", False)))
        self.entry_duration.delete(0, "end")
        self.entry_duration.insert(0, str(data.get("duration_seconds", 60.0)))

        self.var_use_cycles.set(bool(data.get("use_max_cycles", False)))
        self.entry_max_cycles.delete(0, "end")
        self.entry_max_cycles.insert(0, str(data.get("max_cycles", 10)))

        self.engine.points = list(data.get("points", []))
        self._render_points_list()
        self._append_log(f"Profile '{self.current_profile_name}' loaded ({len(self.engine.points)} targets).")
        if hasattr(self, "toast") and getattr(self, "_ui_ready", False):
            self.toast.show(f"Loaded '{self.current_profile_name}'", "info", 1500)

    def _cmd_save_profile(self):
        name = simpledialog.askstring("Save Preset", "Enter preset name:", initialvalue=self.current_profile_name)
        if not name:
            return

        self._apply_ui_settings_to_engine()
        profile_data = {
            "name": name,
            "default_delay": self.engine.default_delay,
            "use_jitter": self.var_use_jitter.get(),
            "random_jitter": self.engine.random_jitter,
            "use_pixel_jitter": self.var_use_px_jitter.get(),
            "pixel_jitter": self.engine.pixel_jitter,
            "restore_cursor": self.engine.restore_cursor,
            "use_duration": self.engine.use_duration,
            "duration_seconds": self.engine.duration_seconds,
            "use_max_cycles": self.engine.use_max_cycles,
            "max_cycles": self.engine.max_cycles,
            "points": self.engine.points
        }

        self.profile_mgr.save_profile(name, profile_data)
        self.combo_profiles.configure(values=self._get_profile_list())
        self.combo_profiles.set(name)
        self.current_profile_name = name
        self.toast.show(f"Preset '{name}' saved", "success")
        self._append_log(f"Profile '{name}' saved.")

    def _cmd_load_selected_profile(self):
        name = self.combo_profiles.get()
        if not name:
            return
        try:
            data = self.profile_mgr.load_profile(name)
            self._apply_profile_data(data)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load profile: {e}")

    def _cmd_delete_profile(self):
        name = self.combo_profiles.get()
        if not name or name == "Default Profile":
            messagebox.showwarning("Warning", "The default profile cannot be deleted!")
            return
        if messagebox.askyesno("Delete Preset", f"Delete profile '{name}'?"):
            self.profile_mgr.delete_profile(name)
            self.combo_profiles.configure(values=self._get_profile_list())
            self.combo_profiles.set("Default Profile")
            self._cmd_load_selected_profile()

    # -----------------------------
    # Engine Control Commands
    # -----------------------------
    def _cmd_start(self):
        self._apply_ui_settings_to_engine()
        active_pts = [p for p in self.engine.points if p.get("enabled", True)]
        if not active_pts:
            messagebox.showwarning(
                "No Active Targets",
                "Add or enable at least 1 target before starting!\n"
                "Click [+ Spawn Target Pin], [Snipe on Screen], or press F7."
            )
            return

        # Hide on-screen pins while clicking so clicks hit the game window underneath unobstructed
        self.pin_mgr.hide_all()

        if self.engine.status == "PAUSED":
            self.engine.resume()
        else:
            self.progress_bar.set(0.0)
            self.engine.start()

    def _cmd_pause(self):
        if self.engine.status == "RUNNING":
            self.engine.pause()
            self.pin_mgr.show_all()
        elif self.engine.status == "PAUSED":
            self.pin_mgr.hide_all()
            self.engine.resume()

    def _cmd_stop(self):
        if self._snipe_overlay is not None:
            self._snipe_overlay.stop()
            self._snipe_overlay = None
        self.engine.stop()
        self._highlight_active_row(None)
        self.pin_mgr.show_all()

    # -----------------------------
    # Thread-Safe Event Queue Consumer (Runs on Tkinter Main Thread)
    # -----------------------------
    def _drain_event_queue(self):
        if getattr(self, "_closing", False):
            return

        try:
            processed = 0
            while not self._event_queue.empty() and processed < 40:
                event_type, payload = self._event_queue.get_nowait()
                processed += 1
                if event_type == "status":
                    self._update_status_ui(payload)
                elif event_type == "step":
                    step_idx, total, pt = payload
                    self._on_step_ui(step_idx, total, pt)
                elif event_type == "cycle":
                    self.lbl_cycles.configure(
                        text=f"🔄 Cycle: #{payload}   |   🎯 Step: 1/{len(self.engine.points)}   |   ⚡ Clicks: {self.engine.total_clicks}"
                    )
                elif event_type == "tick":
                    rem, el = payload
                    self._update_tick_ui(rem, el)
                elif event_type == "log":
                    self._append_log(payload)
                elif event_type == "hotkey_start":
                    if self.engine.status != "RUNNING":
                        self._cmd_start()
                    else:
                        self._cmd_pause()
                elif event_type == "hotkey_capture":
                    x, y = payload
                    self._add_target_at(x, y)
                elif event_type == "hotkey_stop":
                    self._cmd_stop()
        except Exception:
            pass

        self.after(20, self._drain_event_queue)

    def _on_step_ui(self, step_index: int, total_steps: int, pt: dict):
        now = time.time()
        if not hasattr(self, "_last_step_ui_time") or (now - self._last_step_ui_time >= 0.05) or (step_index != getattr(self, "_last_step_idx", -1)):
            self._last_step_ui_time = now
            self._last_step_idx = step_index
            self.lbl_cycles.configure(
                text=f"🔄 Cycle: #{self.engine.current_cycle}   |   "
                     f"🎯 Step: {step_index}/{total_steps} ({pt.get('label', '')})   |   "
                     f"⚡ Clicks: {self.engine.total_clicks}"
            )
        self._highlight_active_row(step_index - 1)
        if not self.engine.use_duration and self.engine.use_max_cycles and self.engine.max_cycles > 0:
            prog = ((self.engine.current_cycle - 1) + (step_index / max(1, total_steps))) / self.engine.max_cycles
            self.progress_bar.set(min(1.0, max(0.0, prog)))

    def _highlight_active_row(self, active_zero_idx: Optional[int]):
        if getattr(self, "_current_highlight_idx", -999) == active_zero_idx:
            return  # No-op: row is already highlighted, avoid redrawing to prevent UI jitter/flicker!
        self._current_highlight_idx = active_zero_idx

        for idx, row in enumerate(self.point_widgets):
            if not row.winfo_exists():
                continue
            if active_zero_idx is not None and idx == active_zero_idx:
                row.configure(border_width=2, border_color=T.SUCCESS)
            else:
                row.configure(border_width=1, border_color=T.BORDER)

    def _update_status_ui(self, status: str):
        bg, fg, label = T.STATUS.get(status, T.STATUS["IDLE"])
        self.status_badge.configure(fg_color=bg)
        self.status_dot.configure(text_color=fg)
        self.status_text.configure(text=label, text_color=fg)

        prev = getattr(self, "_prev_status", "IDLE")
        self._prev_status = status

        # Pulsing dot only while running
        if status == "RUNNING":
            self.progress_bar.configure(progress_color=T.SUCCESS)
            self._start_pulse()
        else:
            self._stop_pulse()
            if status == "PAUSED":
                self.progress_bar.configure(progress_color=T.WARNING)
            elif status == "COMPLETED":
                self.progress_bar.configure(progress_color=T.PRIMARY)

        if status == "RUNNING":
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="normal", text="⏸  Pause")
            play_sound("start")
            self.toast.show("Resumed" if prev == "PAUSED" else "Started - good luck on the pulls!", "success")
        elif status == "PAUSED":
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="normal", text="▶  Resume")
            play_sound("pause")
            self.toast.show("Paused", "warning")
        else:
            self.btn_start.configure(state="normal", text="▶  Start  F6")
            self.btn_pause.configure(state="disabled", text="⏸  Pause")
            self._highlight_active_row(None)
            if status == "COMPLETED":
                self.progress_bar.set(1.0)
                play_sound("complete")
                self.toast.show(f"Finished - {self.engine.total_clicks} clicks done", "success", 3500)
            elif status == "STOPPED" and prev in ("RUNNING", "PAUSED"):
                play_sound("stop")
                self.toast.show("Stopped", "info")
            self.pin_mgr.show_all()

    def _start_pulse(self):
        if self._pulse_job is not None:
            return
        self._pulse_tick()

    def _stop_pulse(self):
        if self._pulse_job is not None:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None

    def _pulse_tick(self):
        self._pulse_on = not self._pulse_on
        color = T.SUCCESS if self._pulse_on else T.PULSE_DIM
        try:
            self.status_dot.configure(text_color=color)
        except Exception:
            return
        self._pulse_job = self.after(520, self._pulse_tick)

    def _update_tick_ui(self, remaining: float, elapsed: float):
        if self.engine.use_duration and self.engine.duration_seconds > 0:
            rem_m, rem_s = divmod(int(remaining), 60)
            self.lbl_countdown.configure(
                text=f"⏳ Remaining: {rem_m:02d}:{rem_s:02d} ({remaining:.1f}s)"
            )
            prog = min(1.0, max(0.0, elapsed / self.engine.duration_seconds))
            self.progress_bar.set(prog)
        else:
            el_m, el_s = divmod(int(elapsed), 60)
            self.lbl_countdown.configure(
                text=f"⏳ Elapsed: {el_m:02d}:{el_s:02d} ({elapsed:.1f}s)"
            )

    @staticmethod
    def _classify_log(message: str) -> str:
        m = message.lower()
        if m.startswith("---"):
            return "cycle"
        if m.startswith("clicked") or m.startswith("test clicked"):
            return "click"
        if "error" in m:
            return "error"
        if any(k in m for k in ("warning", "paused", "cancel")):
            return "warn"
        if any(k in m for k in ("completed", "finished", "limit reached", "timer expired", "timer finished")):
            return "done"
        if any(k in m for k in ("started", "resumed", "placed", "saved", "loaded", "gathered", "duplicated")):
            return "success"
        return "info"

    def _append_log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        kind = self._classify_log(message)
        self.txt_log.insert("end", f"{timestamp}  ", "time")
        self.txt_log.insert("end", f"{message}\n", kind)
        try:
            line_count = int(float(self.txt_log.index("end-1c").split(".")[0]))
            if line_count > 300:
                self.txt_log.delete("1.0", "60.0")
        except Exception:
            pass
        self.txt_log.see("end")

    def _on_close(self):
        self._closing = True
        try:
            if self._snipe_overlay:
                self._snipe_overlay.stop()
            self.engine.stop()
            self.hotkeys.stop()
            self.pin_mgr.clear()
        except Exception:
            pass
        self.destroy()
