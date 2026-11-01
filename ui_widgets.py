import customtkinter as ctk
from theme import T


class CollapsibleSection(ctk.CTkFrame):
    """A titled card whose body can be collapsed. Put content in `.body`."""

    def __init__(self, parent, title: str, icon: str = "", expanded: bool = True, summary: str = ""):
        super().__init__(
            parent,
            corner_radius=T.RADIUS,
            fg_color=T.SURFACE_ALT,
            border_width=1,
            border_color=T.BORDER,
        )
        self._expanded = expanded
        self._summary_text = None

        self.header = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2")
        self.header.pack(fill="x")

        self._arrow = ctk.CTkLabel(
            self.header, text="▾" if expanded else "▸", width=16,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=13, weight="bold"),
            text_color=T.TEXT_MUTED,
        )
        self._arrow.pack(side="left", padx=(12, 2), pady=9)

        self._title = ctk.CTkLabel(
            self.header, text=f"{icon}  {title}" if icon else title,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=13, weight="bold"),
            text_color=T.TEXT,
        )
        self._title.pack(side="left", pady=9)

        self._summary = ctk.CTkLabel(
            self.header, text="",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11),
            text_color=T.TEXT_MUTED,
        )
        self._summary.pack(side="right", padx=12)

        for w in (self.header, self._arrow, self._title, self._summary):
            w.bind("<Button-1>", lambda _e: self.toggle())

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        if expanded:
            self.body.pack(fill="x", padx=T.PAD, pady=(0, T.PAD - 2))
        if summary:
            self.set_summary(summary)

    def toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.body.pack(fill="x", padx=T.PAD, pady=(0, T.PAD - 2))
            self._arrow.configure(text="▾")
        else:
            self.body.pack_forget()
            self._arrow.configure(text="▸")

    def set_summary(self, text: str, color: str = None):
        """Cheap to call often: only redraws when the text changes."""
        key = (text, color)
        if key == self._summary_text:
            return
        self._summary_text = key
        self._summary.configure(text=text, text_color=color or T.TEXT_MUTED)
