import ctypes
from ctypes import wintypes
import math
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Win32 GDI & User32 bindings for sub-microsecond pixel sampling
_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32

try:
    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.GetDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.ReleaseDC.restype = ctypes.c_int

    _gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    _gdi32.GetPixel.restype = wintypes.COLORREF
except AttributeError as e:
    logger.error("pixel_scanner: Win32 GDI binding setup error: %s", e)

# Base preset palette
BASE_PALETTE = {
    "Red": "#FF3B30",
    "Yellow": "#FFCC00",
    "Green": "#34C759",
    "Blue": "#007AFF",
    "Orange": "#FF9500",
    "Purple": "#AF52DE",
    "White": "#FFFFFF",
    "Black": "#000000",
}

def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Converts hex string (e.g. '#FF3B30' or 'FF3B30') to (r, g, b) tuple."""
    s = hex_str.strip().lstrip("#")
    if len(s) == 3:
        s = "".join([c * 2 for c in s])
    if len(s) != 6:
        return (255, 0, 0)
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    except Exception:
        return (255, 0, 0)

def rgb_to_hex(r, g=None, b=None) -> str:
    """Converts (r, g, b) tuple or r, g, b integers to hex string '#RRGGBB'."""
    if isinstance(r, (tuple, list)):
        r, g, b = r[0], r[1], r[2]
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    return f"#{r:02X}{g:02X}{b:02X}"

def get_pixel_color(x: int, y: int) -> Tuple[int, int, int]:
    """Retrieves physical screen RGB color at (x, y) across any display with ~1.5us latency."""
    hdc = 0
    try:
        hdc = _user32.GetDC(0)
        if not hdc:
            logger.warning("pixel_scanner: GetDC(0) returned NULL.")
            return (0, 0, 0)
        color = _gdi32.GetPixel(hdc, int(x), int(y))
        # CLR_INVALID is 0xFFFFFFFF (-1)
        if color == 0xFFFFFFFF:
            return (0, 0, 0)
        # COLORREF in Windows is 0x00BBGGRR
        r = color & 0xFF
        g = (color >> 8) & 0xFF
        b = (color >> 16) & 0xFF
        return (r, g, b)
    except Exception as e:
        logger.debug("pixel_scanner: get_pixel_color error at (%s, %s): %s", x, y, e)
        return (0, 0, 0)
    finally:
        if hdc:
            _user32.ReleaseDC(0, hdc)

def color_distance_pct(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    """Calculates 3D Euclidean RGB color distance normalized to 0.0% - 100.0%.
    Maximum distance in 3D RGB space is sqrt(255^2 * 3) ≈ 441.673."""
    dr = c1[0] - c2[0]
    dg = c1[1] - c2[1]
    db = c1[2] - c2[2]
    dist = math.sqrt(dr * dr + dg * dg + db * db)
    return (dist / 441.67295593) * 100.0

def color_matches(
    actual_rgb: Tuple[int, int, int],
    target_rgb_or_hex,
    tolerance_pct: float = 30.0
) -> bool:
    """Evaluates whether actual RGB matches target within the specified tolerance percentage."""
    if isinstance(target_rgb_or_hex, str):
        target_rgb = hex_to_rgb(target_rgb_or_hex)
    else:
        target_rgb = target_rgb_or_hex

    diff_pct = color_distance_pct(actual_rgb, target_rgb)
    return diff_pct <= max(0.0, float(tolerance_pct))
