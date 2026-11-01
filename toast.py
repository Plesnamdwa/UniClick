import customtkinter as ctk
from theme import T


class ToastManager:
    """Non-blocking toast notifications that slide up from the bottom-center of the window."""

    def __init__(self, root: ctk.CTk):
        self.root = root
        self._current = None
        self._hide_job = None
        self._anim_job = None

    def show(self, message: str, kind: str = "info", duration_ms: int = 2200):
        bg, accent, icon = T.TOAST.get(kind, T.TOAST["info"])
        self._dismiss_now()

        frame = ctk.CTkFrame(
            self.root,
            fg_color=bg,
            corner_radius=T.RADIUS,
            border_width=1,
            border_color=accent,
        )
        ctk.CTkLabel(
            frame,
            text=icon,
            width=24,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=14, weight="bold"),
            text_color=accent,
        ).pack(side="left", padx=(12, 4), pady=8)
        ctk.CTkLabel(
            frame,
            text=message,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=12, weight="bold"),
            text_color=T.TEXT,
        ).pack(side="left", padx=(0, 14), pady=8)

        self._current = frame
        # Slide up: start slightly below the final position
        self._animate_in(frame, start=1.02, end=0.95, steps=8)
        self._hide_job = self.root.after(duration_ms, self._dismiss_now)

    def _animate_in(self, frame, start: float, end: float, steps: int, step: int = 0):
        if frame is not self._current:
            return
        t = step / steps
        eased = 1 - (1 - t) ** 3  # ease-out cubic
        rely = start + (end - start) * eased
        try:
            frame.place(relx=0.5, rely=rely, anchor="s")
            frame.lift()
        except Exception:
            return
        if step < steps:
            self._anim_job = self.root.after(
                14, lambda: self._animate_in(frame, start, end, steps, step + 1)
            )

    def _dismiss_now(self):
        if self._hide_job is not None:
            try:
                self.root.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None
        if self._anim_job is not None:
            try:
                self.root.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None
        if self._current is not None:
            try:
                self._current.destroy()
            except Exception:
                pass
            self._current = None
