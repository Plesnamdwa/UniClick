import sys
import os
import ctypes

# Enable Per-Monitor DPI Awareness V2 for true multi-monitor coordinate alignment
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)) # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Add local directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from win_timer import enable_high_precision_timer, disable_high_precision_timer
from app_ui import UniClickApp

def main():
    enable_high_precision_timer()
    try:
        app = UniClickApp()
        app.mainloop()
    finally:
        disable_high_precision_timer()

if __name__ == "__main__":
    main()
