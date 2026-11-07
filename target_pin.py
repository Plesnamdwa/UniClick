import tkinter as tk
from typing import Callable, Optional, List
import ctypes
from hotkeys import get_current_mouse_pos, VK_LBUTTON, VK_RBUTTON, VK_ESCAPE, play_sound
from theme import T

# Win32 extended window styles for click-through ripple overlay
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


class TargetPin:
    """Draggable circular tactical reticle marking a target click coordinate across any monitor."""

    PIN_SIZE = 60
    HALF_SIZE = 30

    def __init__(
        self,
        parent: tk.Misc,
        index: int,
        total_count: int,
        x: int,
        y: int,
        label: str = "",
        delay: float = 1.0,
        click_type: str = "left",
        enabled: bool = True,
        on_moved: Optional[Callable[[int, int, int], None]] = None,
        on_wheel_delay: Optional[Callable[[int, float], None]] = None,
        on_delete: Optional[Callable[[int], None]] = None,
        animate_spawn: bool = True,
    ):
        self.parent = parent
        self.index = index
        self.total_count = total_count
        self.center_x = int(x)
        self.center_y = int(y)
        self.label = label
        self.delay = delay
        self.click_type = click_type
        self.enabled = enabled

        self.on_moved = on_moved
        self.on_wheel_delay = on_wheel_delay
        self.on_delete = on_delete

        self.top_left_x = self.center_x - self.HALF_SIZE
        self.top_left_y = self.center_y - self.HALF_SIZE
        self._highlighted = False
        self._is_dragging = False
        self._flashing = False
        self._scale = 1.0
        self._anim_job: Optional[str] = None

        # Borderless topmost circular window using color-key transparency for outer corners
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        self.win.config(bg=T.TRANSPARENT_KEY, cursor="fleur")
        try:
            self.win.wm_attributes("-transparentcolor", T.TRANSPARENT_KEY)
        except Exception:
            pass

        self.canvas = tk.Canvas(
            self.win,
            width=self.PIN_SIZE,
            height=self.PIN_SIZE,
            bg=T.TRANSPARENT_KEY,
            highlightthickness=0,
            cursor="fleur",
        )
        self.canvas.pack(fill="both", expand=True)

        # Floating HUD Tooltip window (shown while hovering or dragging)
        self.hud_win: Optional[tk.Toplevel] = None
        self.hud_lbl: Optional[tk.Label] = None

        self._start_mouse_x = 0
        self._start_mouse_y = 0
        self._start_pin_x = 0
        self._start_pin_y = 0

        # Bind mouse interactions
        for widget in (self.canvas, self.win):
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)
            widget.bind("<ButtonRelease-1>", self._on_drag_end)
            widget.bind("<Enter>", self._on_hover_enter)
            widget.bind("<Leave>", self._on_hover_leave)
            widget.bind("<MouseWheel>", self._on_mouse_wheel)
            widget.bind("<ButtonRelease-3>", self._on_right_click)

        self.update_position(self.center_x, self.center_y)
        if animate_spawn:
            self.animate_pop()
        else:
            self._draw_reticle()

    def _get_accent_colors(self) -> tuple[str, str, str]:
        """Returns (outer_ring_color, inner_ring_color, badge_bg) based on pin state & position."""
        if self._flashing:
            return T.PIN_FLASH
        if not self.enabled:
            return T.PIN_DISABLED
        if self._highlighted or self._is_dragging:
            return T.PIN_HIGHLIGHT
        if self.index == 0:
            return T.PIN_FIRST
        if self.total_count > 1 and self.index == self.total_count - 1:
            return T.PIN_LAST
        return T.PIN_MIDDLE

    def animate_pop(self):
        """Elastic pop-in animation when a pin spawns."""
        frames = [0.42, 0.78, 1.10, 1.0]
        self._run_scale_frames(frames, flash=False)

    def pulse(self):
        """Brief visual pulse + flash when triggered or adjusted."""
        frames = [1.14, 1.06, 1.0]
        self._run_scale_frames(frames, flash=True)

    def _run_scale_frames(self, frames: list[float], flash: bool = False):
        if self._anim_job is not None:
            try:
                self.win.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None

        self._flashing = flash

        def _step(idx: int):
            if not self.win.winfo_exists():
                return
            self._scale = frames[idx]
            if idx == len(frames) - 1:
                self._flashing = False
            self._draw_reticle()
            if idx + 1 < len(frames):
                self._anim_job = self.win.after(28, lambda: _step(idx + 1))
            else:
                self._anim_job = None

        _step(0)

    def _draw_reticle(self):
        if not self.canvas.winfo_exists():
            return
        self.canvas.delete("all")
        cx, cy = self.HALF_SIZE, self.HALF_SIZE
        s = self._scale
        outer_col, inner_col, disc_bg = self._get_accent_colors()

        r_outer = max(6, round(24 * s))
        r_inner = max(4, round(17 * s))
        tick_in = max(4, round(17 * s))
        tick_out = max(6, round(28 * s))

        # Solid circular base so clicking ANYWHERE inside the circle grabs the pin
        self.canvas.create_oval(
            cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer,
            fill=disc_bg, outline=outer_col, width=3
        )

        # Tactical crosshair ticks
        self.canvas.create_line(cx - tick_out, cy, cx - tick_in, cy, fill=inner_col, width=2)
        self.canvas.create_line(cx + tick_in, cy, cx + tick_out, cy, fill=inner_col, width=2)
        self.canvas.create_line(cx, cy - tick_out, cx, cy - tick_in, fill=inner_col, width=2)
        self.canvas.create_line(cx, cy + tick_in, cx, cy + tick_out, fill=inner_col, width=2)

        # Inner precision ring
        self.canvas.create_oval(
            cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner,
            fill=T.PIN_CORE, outline=inner_col, width=2
        )

        if s >= 0.7:
            # Sequence Number (#1, #2, ...)
            num_str = f"#{self.index + 1}"
            self.canvas.create_text(
                cx, cy - 3,
                text=num_str,
                fill=T.PIN_TEXT if self.enabled else T.PIN_TEXT_DISABLED,
                font=(T.FONT_FAMILY, 10, "bold"),
            )

            # Small delay sub-label inside circle bottom
            delay_txt = f"{self.delay:.1f}s"
            self.canvas.create_text(
                cx, cy + 9,
                text=delay_txt,
                fill=inner_col,
                font=(T.FONT_FAMILY, 7, "bold"),
            )

    def _show_hud(self):
        if self.hud_win is None or not self.hud_win.winfo_exists():
            self.hud_win = tk.Toplevel(self.win)
            self.hud_win.overrideredirect(True)
            self.hud_win.wm_attributes("-topmost", True)
            self.hud_win.config(bg=T.BORDER)
            self.hud_lbl = tk.Label(
                self.hud_win,
                text="",
                bg=T.SURFACE,
                fg=T.TEXT,
                font=(T.FONT_FAMILY, 9, "bold"),
                padx=10,
                pady=4,
                relief="flat",
                bd=0,
            )
            self.hud_lbl.pack(padx=1, pady=1)

        self._update_hud_text_and_pos()
        try:
            self.hud_win.deiconify()
        except Exception:
            pass

    def _update_hud_text_and_pos(self):
        if self.hud_win and self.hud_lbl and self.hud_win.winfo_exists():
            state_str = "" if self.enabled else " [DISABLED]"
            txt = (
                f"#{self.index + 1} {self.label}{state_str}   ·   "
                f"X {self.center_x}, Y {self.center_y}   ·   "
                f"⏱ {self.delay:.2f}s  (Scroll ±0.1s · Right-click delete)"
            )
            if getattr(self, "_last_hud_text", None) != txt:
                self._last_hud_text = txt
                outer_col, _, _ = self._get_accent_colors()
                self.hud_win.config(bg=outer_col)
                self.hud_lbl.config(text=txt)
            hud_x = self.center_x - 125
            hud_y = self.top_left_y - 34
            self.hud_win.geometry(f"+{hud_x}+{hud_y}")

    def _hide_hud(self):
        if self.hud_win and self.hud_win.winfo_exists():
            try:
                self.hud_win.withdraw()
            except Exception:
                pass

    def set_highlight(self, highlighted: bool):
        if self._highlighted != highlighted:
            self._highlighted = highlighted
            self._draw_reticle()
            if highlighted:
                self._show_hud()
            elif not self._is_dragging:
                self._hide_hud()

    def update_position(self, x: int, y: int):
        """Moves pin center to target coordinates across any monitor."""
        self.center_x = int(x)
        self.center_y = int(y)
        self.top_left_x = self.center_x - self.HALF_SIZE
        self.top_left_y = self.center_y - self.HALF_SIZE

        geom = f"{self.PIN_SIZE}x{self.PIN_SIZE}+{self.top_left_x}+{self.top_left_y}"
        self.win.geometry(geom)
        if self._is_dragging or self._highlighted:
            self._update_hud_text_and_pos()

    def sync_metadata(self, index: int, total_count: int, pt: dict):
        self.index = index
        self.total_count = total_count
        self.label = pt.get("label", f"Target #{index + 1}")
        self.delay = float(pt.get("delay", 1.0))
        self.click_type = pt.get("click_type", "left")
        self.enabled = bool(pt.get("enabled", True))
        self._draw_reticle()
        if not self._is_dragging:
            self.update_position(pt.get("x", 500), pt.get("y", 300))

    def show(self):
        try:
            self.win.deiconify()
            geom = f"{self.PIN_SIZE}x{self.PIN_SIZE}+{self.top_left_x}+{self.top_left_y}"
            self.win.geometry(geom)
        except Exception:
            pass

    def hide(self):
        self._hide_hud()
        try:
            self.win.withdraw()
        except Exception:
            pass

    def destroy(self):
        if self._anim_job is not None:
            try:
                self.win.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None
        self._hide_hud()
        if self.hud_win:
            try:
                self.hud_win.destroy()
            except Exception:
                pass
        try:
            self.win.destroy()
        except Exception:
            pass

    def _on_hover_enter(self, event):
        self._highlighted = True
        self._draw_reticle()
        self._show_hud()

    def _on_hover_leave(self, event):
        if not self._is_dragging:
            self._highlighted = False
            self._draw_reticle()
            self._hide_hud()

    def _on_drag_start(self, event):
        self._is_dragging = True
        self._start_mouse_x = event.x_root
        self._start_mouse_y = event.y_root
        self._start_pin_x = self.top_left_x
        self._start_pin_y = self.top_left_y
        self._draw_reticle()
        self._show_hud()

    def _on_drag_motion(self, event):
        if not self._is_dragging:
            return
        dx = event.x_root - self._start_mouse_x
        dy = event.y_root - self._start_mouse_y

        self.top_left_x = self._start_pin_x + dx
        self.top_left_y = self._start_pin_y + dy
        self.center_x = self.top_left_x + self.HALF_SIZE
        self.center_y = self.top_left_y + self.HALF_SIZE

        geom = f"{self.PIN_SIZE}x{self.PIN_SIZE}+{self.top_left_x}+{self.top_left_y}"
        self.win.geometry(geom)
        self._update_hud_text_and_pos()

        if self.on_moved:
            self.on_moved(self.index, self.center_x, self.center_y)

    def _on_drag_end(self, event):
        self._is_dragging = False
        self._draw_reticle()
        if self.on_moved:
            self.on_moved(self.index, self.center_x, self.center_y)

    def _on_mouse_wheel(self, event):
        """Scroll wheel directly on pin adjusts its delay by ±0.1s with a tactile pulse."""
        delta = 0.1 if event.delta > 0 else -0.1
        self.delay = round(max(0.05, self.delay + delta), 2)
        self.pulse()
        self._update_hud_text_and_pos()
        if self.on_wheel_delay:
            self.on_wheel_delay(self.index, self.delay)

    def _on_right_click(self, event):
        """Right-clicking a pin deletes it quickly."""
        if self.on_delete:
            self.on_delete(self.index)


class SnipeCursorOverlay:
    """Floating non-blocking HUD tracker that follows the cursor across all monitors until Left-Click places a pin."""

    def __init__(
        self,
        parent: tk.Misc,
        on_picked: Callable[[int, int], None],
        on_cancelled: Optional[Callable[[], None]] = None,
    ):
        self.parent = parent
        self.on_picked = on_picked
        self.on_cancelled = on_cancelled
        self._user32 = ctypes.windll.user32
        self._active = True

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        self.win.config(bg=T.TEAL)

        self.lbl = tk.Label(
            self.win,
            text="🎯 SNIPE MODE: Left-Click anywhere to place pin | Right-Click/ESC to cancel",
            bg=T.SURFACE,
            fg=T.TEAL,
            font=(T.FONT_FAMILY, 9, "bold"),
            padx=12,
            pady=6,
            relief="flat",
            bd=0,
        )
        self.lbl.pack(padx=1, pady=1)

        # Wait until initial mouse button release before arming trigger
        self._armed = False
        self.parent.after(150, self._poll)

    def _poll(self):
        if not self._active:
            return

        x, y = get_current_mouse_pos()
        if getattr(self, "_last_snipe_pos", None) != (x, y):
            self._last_snipe_pos = (x, y)
            # Position floating badge slightly offset from cursor so cursor never clicks the badge itself
            self.win.geometry(f"+{x + 22}+{y + 22}")
            self.lbl.config(
                text=f"🎯 SNIPE TARGET   (X {x} · Y {y})\nLeft-click: Place Pin   ·   Right-click / Esc: Cancel"
            )

        l_down = bool(self._user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        r_down = bool(self._user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000)
        esc_down = bool(self._user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)

        if not self._armed:
            if not l_down:
                self._armed = True
        else:
            if l_down:
                self.stop()
                play_sound("snipe")
                self.on_picked(x, y)
                return
            if r_down or esc_down:
                self.stop()
                play_sound("cancel")
                if self.on_cancelled:
                    self.on_cancelled()
                return

        self.parent.after(16, self._poll)

    def stop(self):
        self._active = False
        try:
            self.win.destroy()
        except Exception:
            pass


class TargetPinManager:
    """Manages all on-screen circular target pins and click-flash ripples for the sequence."""

    def __init__(
        self,
        parent: tk.Misc,
        on_pin_moved: Optional[Callable[[int, int, int], None]] = None,
        on_pin_wheel_delay: Optional[Callable[[int, float], None]] = None,
        on_pin_delete: Optional[Callable[[int], None]] = None,
    ):
        self.parent = parent
        self.on_pin_moved = on_pin_moved
        self.on_pin_wheel_delay = on_pin_wheel_delay
        self.on_pin_delete = on_pin_delete
        self.pins: List[TargetPin] = []
        self.visible = True

    def sync_points(self, points: List[dict]):
        """Synchronizes on-screen pins with current points data."""
        total = len(points)
        while len(self.pins) > total:
            p = self.pins.pop()
            p.destroy()

        while len(self.pins) < total:
            idx = len(self.pins)
            pt = points[idx]
            pin = TargetPin(
                parent=self.parent,
                index=idx,
                total_count=total,
                x=pt.get("x", 500),
                y=pt.get("y", 300),
                label=pt.get("label", f"Target #{idx + 1}"),
                delay=float(pt.get("delay", 1.0)),
                click_type=pt.get("click_type", "left"),
                enabled=bool(pt.get("enabled", True)),
                on_moved=self.on_pin_moved,
                on_wheel_delay=self.on_pin_wheel_delay,
                on_delete=self.on_pin_delete,
                animate_spawn=self.visible,
            )
            if not self.visible:
                pin.hide()
            self.pins.append(pin)

        for idx, (pin, pt) in enumerate(zip(self.pins, points)):
            pin.sync_metadata(idx, total, pt)

    def flash_click(self, x: int, y: int, index: Optional[int] = None):
        """Shows a brief, 100% click-through expanding ripple ring at (x, y) when a step fires."""
        if index is not None and 0 <= index < len(self.pins) and self.visible:
            self.pins[index].pulse()

        size = 56
        half = size // 2
        try:
            win = tk.Toplevel(self.parent)
            win.overrideredirect(True)
            win.wm_attributes("-topmost", True)
            win.config(bg=T.TRANSPARENT_KEY)
            win.wm_attributes("-transparentcolor", T.TRANSPARENT_KEY)
            win.geometry(f"{size}x{size}+{int(x) - half}+{int(y) - half}")

            # Make window click-through & non-activating via Win32 extended styles
            try:
                hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(
                    hwnd,
                    GWL_EXSTYLE,
                    ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
                )
            except Exception:
                pass

            cv = tk.Canvas(win, width=size, height=size, bg=T.TRANSPARENT_KEY, highlightthickness=0)
            cv.pack(fill="both", expand=True)

            radii = [10, 17, 24]
            widths = [3, 2, 1]
            colors = [T.SUCCESS, T.TEAL, T.PRIMARY]

            def _animate(step_i: int):
                if not win.winfo_exists():
                    return
                if step_i >= len(radii):
                    try:
                        win.destroy()
                    except Exception:
                        pass
                    return
                cv.delete("all")
                r = radii[step_i]
                cv.create_oval(
                    half - r, half - r, half + r, half + r,
                    outline=colors[step_i], width=widths[step_i],
                )
                win.after(45, lambda: _animate(step_i + 1))

            _animate(0)
        except Exception:
            pass

    def highlight_pin(self, index: Optional[int]):
        for idx, pin in enumerate(self.pins):
            pin.set_highlight(index is not None and idx == index)

    def show_all(self):
        self.visible = True
        for p in self.pins:
            p.show()

    def hide_all(self):
        self.visible = False
        for p in self.pins:
            p.hide()

    def clear(self):
        for p in self.pins:
            p.destroy()
        self.pins.clear()
