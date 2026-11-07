import sys
import os

# Add local directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from win_timer import enable_high_precision_timer, disable_high_precision_timer, ensure_dpi_awareness_v2

# Enable Per-Monitor DPI Awareness V2 before creating any GUI windows
ensure_dpi_awareness_v2()

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
