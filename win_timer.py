import ctypes

_winmm = None
_timer_active = False

try:
    _winmm = ctypes.windll.winmm
except Exception:
    _winmm = None

def enable_high_precision_timer():
    """Sets Windows system timer resolution to 1ms for sub-millisecond precision sleep."""
    global _timer_active
    if _winmm and not _timer_active:
        try:
            _winmm.timeBeginPeriod(1)
            _timer_active = True
        except Exception:
            pass

def disable_high_precision_timer():
    """Restores Windows system timer resolution to default."""
    global _timer_active
    if _winmm and _timer_active:
        try:
            _winmm.timeEndPeriod(1)
            _timer_active = False
        except Exception:
            pass
