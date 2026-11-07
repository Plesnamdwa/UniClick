import ctypes
from ctypes import wintypes
import threading
import time
import queue
import winsound
from typing import Callable, Optional
from win_timer import ensure_dpi_awareness_v2

ensure_dpi_awareness_v2()

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]

_user32 = ctypes.windll.user32
try:
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    _user32.GetCursorPos.restype = wintypes.BOOL
except Exception:
    pass

try:
    _user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    _user32.MonitorFromPoint.restype = wintypes.HMONITOR
except Exception:
    pass

try:
    _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    _user32.GetMonitorInfoW.restype = wintypes.BOOL
except Exception:
    pass

def get_current_mouse_pos() -> tuple[int, int]:
    """Gets current physical screen cursor coordinates (X, Y) across all monitors."""
    pt = POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)

def get_monitor_bounds_at(x: int, y: int) -> tuple[int, int, int, int]:
    """Returns (left, top, right, bottom) of the monitor nearest to (x, y)."""
    try:
        pt = wintypes.POINT(int(x), int(y))
        hmon = _user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST = 2
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcWork
            return int(r.left), int(r.top), int(r.right), int(r.bottom)
    except Exception:
        pass
    return 0, 0, 1920, 1080

# Sound cue sequences: list of (frequency_hz, duration_ms)
SOUND_CUES: dict[str, list[tuple[int, int]]] = {
    "add": [(784, 35), (1175, 45)],
    "snipe": [(988, 30), (1319, 50)],
    "start": [(659, 40), (880, 60)],
    "pause": [(659, 40), (523, 55)],
    "stop": [(523, 45), (392, 65)],
    "complete": [(784, 50), (988, 50), (1319, 95)],
    "delete": [(440, 40)],
    "gather": [(659, 35), (784, 45)],
    "cancel": [(494, 40), (392, 50)],
}

_audio_queue: queue.Queue = queue.Queue(maxsize=16)

def _audio_worker():
    """Single persistent daemon worker thread to prevent thread churn and Beep collisions."""
    while True:
        try:
            notes = _audio_queue.get()
            if notes is None:
                break
            for freq, dur in notes:
                try:
                    winsound.Beep(freq, dur)
                except Exception:
                    try:
                        winsound.MessageBeep(winsound.MB_OK)
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            _audio_queue.task_done()

_audio_thread = threading.Thread(target=_audio_worker, daemon=True)
_audio_thread.start()

def play_tone(freq: int = 880, duration_ms: int = 60):
    """Plays a non-blocking crisp audio tone via persistent audio worker queue."""
    try:
        _audio_queue.put_nowait([(freq, duration_ms)])
    except queue.Full:
        pass

def play_sound(cue: str = "add"):
    """Plays a pleasant, non-blocking multi-note sound cue by name."""
    notes = SOUND_CUES.get(cue, [(880, 50)])
    try:
        _audio_queue.put_nowait(notes)
    except queue.Full:
        pass

# Win32 Virtual Key Codes
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_ESCAPE = 0x1B
VK_F6 = 0x75
VK_F7 = 0x76
VK_F8 = 0x77

class GlobalHotkeyManager:
    """High-reliability Global Hotkey Manager using Win32 GetAsyncKeyState with edge detection."""

    def __init__(
        self,
        on_toggle_start: Optional[Callable[[], None]] = None,
        on_capture_point: Optional[Callable[[int, int], None]] = None,
        on_emergency_stop: Optional[Callable[[], None]] = None,
    ):
        self.on_toggle_start = on_toggle_start
        self.on_capture_point = on_capture_point
        self.on_emergency_stop = on_emergency_stop

        self._user32 = ctypes.windll.user32
        try:
            self._user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
            self._user32.GetAsyncKeyState.restype = ctypes.c_short
        except Exception:
            pass
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None

    def start(self):
        """Starts the background Win32 hotkey polling thread."""
        if self._running:
            return

        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        """Polls key state every ~15ms with drift compensation and rising-edge trigger."""
        prev_f6 = False
        prev_f7 = False
        prev_f8 = False
        prev_esc = False

        next_t = time.perf_counter() + 0.015

        while self._running:
            try:
                down_f6 = bool(self._user32.GetAsyncKeyState(VK_F6) & 0x8000)
                down_f7 = bool(self._user32.GetAsyncKeyState(VK_F7) & 0x8000)
                down_f8 = bool(self._user32.GetAsyncKeyState(VK_F8) & 0x8000)
                down_esc = bool(self._user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)

                if down_f6 and not prev_f6:
                    if self.on_toggle_start:
                        self.on_toggle_start()

                if down_f7 and not prev_f7:
                    x, y = get_current_mouse_pos()
                    if self.on_capture_point:
                        self.on_capture_point(x, y)

                if (down_f8 and not prev_f8) or (down_esc and not prev_esc):
                    if self.on_emergency_stop:
                        self.on_emergency_stop()

                prev_f6 = down_f6
                prev_f7 = down_f7
                prev_f8 = down_f8
                prev_esc = down_esc

            except Exception:
                pass

            wait_time = next_t - time.perf_counter()
            if wait_time > 0:
                time.sleep(wait_time)
            next_t = max(next_t + 0.015, time.perf_counter())

    def stop(self):
        """Stops the hotkey thread."""
        self._running = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=0.5)
