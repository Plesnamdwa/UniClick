"""Design tokens for the UniClick UI.

Use these everywhere instead of hardcoded hex values so the look stays consistent.
"""


class T:
    # Surfaces (soft, slightly warm dark - easy on the eyes during long sessions)
    BG = "#0F1218"
    SURFACE = "#171B24"
    SURFACE_ALT = "#1E2430"
    SURFACE_HOVER = "#262E3D"
    BORDER = "#2C3545"

    # Text
    TEXT = "#E8EDF5"
    TEXT_MUTED = "#8E9BB0"
    TEXT_DIM = "#5F6B7E"
    TEXT_ON_PRIMARY = "#0B1220"
    TEXT_ON_SUCCESS = "#06251B"
    TEXT_ON_WARNING = "#2A1E02"
    TEXT_ON_DANGER = "#2B0C0C"
    TEXT_ON_TEAL = "#04201C"

    # Accents
    PRIMARY = "#4F9CF9"
    PRIMARY_HOVER = "#3B86E3"
    SUCCESS = "#34D399"
    SUCCESS_HOVER = "#22B883"
    PULSE_DIM = "#1C6B52"
    WARNING = "#FBBF24"
    WARNING_HOVER = "#E0A612"
    DANGER = "#F87171"
    DANGER_HOVER = "#E25555"
    DANGER_SUBTLE = "#3A1D21"
    DANGER_SUBTLE_HOVER = "#5A2328"
    TEAL = "#2DD4BF"
    TEAL_HOVER = "#1DB8A5"
    NEUTRAL = "#334055"
    NEUTRAL_HOVER = "#41506A"

    # Tactical Pin palettes: (outer_ring, inner_ring, disc_fill)
    TRANSPARENT_KEY = "#010101"
    PIN_CORE = "#0F172A"
    PIN_TEXT = "#FFFFFF"
    PIN_TEXT_DISABLED = "#94A3B8"
    PIN_FIRST = ("#10B981", "#34D399", "#064E3B")      # Step #1: Emerald
    PIN_LAST = ("#F59E0B", "#FBBF24", "#451A03")       # Final step: Amber Gold
    PIN_MIDDLE = ("#0284C7", "#38BDF8", "#0F172A")     # Intermediate: Cyber Blue
    PIN_HIGHLIGHT = ("#F43F5E", "#FDA4AF", "#2A1019")  # Hovered / Dragged: Rose
    PIN_FLASH = ("#2DD4BF", "#E8EDF5", "#11423B")      # Fired / Pulsed: Bright Teal
    PIN_DISABLED = ("#475569", "#64748B", "#1E293B")   # Disabled: Slate

    # Status badge colors: (background, dot/text color, label)
    STATUS = {
        "IDLE": ("#222A38", "#8E9BB0", "Ready"),
        "RUNNING": ("#10382C", "#34D399", "Running"),
        "PAUSED": ("#3D3014", "#FBBF24", "Paused"),
        "COMPLETED": ("#152E52", "#60A5FA", "Completed"),
        "STOPPED": ("#3A2024", "#F87171", "Stopped"),
    }

    # Toast colors by kind: (background, accent, icon)
    TOAST = {
        "info": ("#1E2A3D", "#4F9CF9", "ℹ"),
        "success": ("#12332A", "#34D399", "✓"),
        "warning": ("#3A2F12", "#FBBF24", "!"),
        "error": ("#3A1D21", "#F87171", "✕"),
    }

    # Shape / spacing
    RADIUS = 12
    RADIUS_SM = 8
    PAD = 14
    PAD_SM = 8

    # Fonts (family, size, weight)
    FONT_FAMILY = "Segoe UI"
    MONO_FAMILY = "Consolas"
