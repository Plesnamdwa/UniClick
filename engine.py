import time
import random
import threading
import ctypes
from typing import List, Dict, Any, Callable, Optional
from hotkeys import get_current_mouse_pos

# Windows mouse constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

class AutoClickerEngine:
    """Core clicking engine supporting multi-target click sequences, humanizer jitter, burst clicks, and timers."""

    def __init__(self):
        self.points: List[Dict[str, Any]] = []
        self.default_delay: float = 1.0       # seconds (float)
        self.random_jitter: float = 0.05      # humanized time jitter seconds (+/-)
        self.pixel_jitter: int = 4            # humanized spatial coordinate jitter (+/- px)
        self.restore_cursor: bool = False     # Ghost Click: restore mouse pos after clicking
        self.use_duration: bool = False
        self.duration_seconds: float = 60.0   # auto-stop active timer seconds
        self.use_max_cycles: bool = False
        self.max_cycles: int = 10

        # State management
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()

        self.status = "IDLE" # IDLE, RUNNING, PAUSED, COMPLETED, STOPPED
        self.current_cycle: int = 0
        self.current_step_index: int = 0
        self.total_clicks: int = 0
        self.elapsed_time: float = 0.0
        self.remaining_time: float = 0.0

        # Callbacks
        self.on_status_change: Optional[Callable[[str], None]] = None
        self.on_step: Optional[Callable[[int, int, Dict[str, Any]], None]] = None
        self.on_cycle: Optional[Callable[[int], None]] = None
        self.on_tick: Optional[Callable[[float, float], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None

        self._user32 = ctypes.windll.user32

    def _set_status(self, new_status: str):
        self.status = new_status
        if self.on_status_change:
            try:
                self.on_status_change(new_status)
            except Exception:
                pass

    def _log(self, message: str):
        if self.on_log:
            try:
                self.on_log(message)
            except Exception:
                pass

    def perform_click(
        self,
        x: int,
        y: int,
        click_type: str = "left",
        apply_jitter: bool = False,
        restore_pos: bool = False
    ) -> tuple[int, int]:
        """Simulates mouse move and click at specified coordinates across any monitor.
        Returns actual (clicked_x, clicked_y)."""
        orig_x, orig_y = (0, 0)
        if restore_pos:
            orig_x, orig_y = get_current_mouse_pos()

        target_x, target_y = int(x), int(y)
        if apply_jitter and self.pixel_jitter > 0:
            target_x += random.randint(-self.pixel_jitter, self.pixel_jitter)
            target_y += random.randint(-self.pixel_jitter, self.pixel_jitter)

        # Win32 SetCursorPos handles multi-monitor coordinates (including negative values)
        self._user32.SetCursorPos(target_x, target_y)
        time.sleep(0.015)

        if click_type == "double":
            self._user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.025)
            self._user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.045)
            self._user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.025)
            self._user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.total_clicks += 2
        elif click_type == "right":
            self._user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            time.sleep(0.025)
            self._user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            self.total_clicks += 1
        else:  # Default left click
            self._user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.025)
            self._user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.total_clicks += 1

        if restore_pos:
            time.sleep(0.01)
            self._user32.SetCursorPos(orig_x, orig_y)

        return target_x, target_y

    def _responsive_sleep(self, seconds: float, start_timestamp: float) -> bool:
        """Sleeps in small chunks while checking for stop/pause and updating countdown timer."""
        end_time = time.time() + max(0.0, seconds)
        while time.time() < end_time:
            if self._stop_event.is_set():
                return False

            while not self._pause_event.is_set():
                if self._stop_event.is_set():
                    return False
                time.sleep(0.04)

            now = time.time()
            self.elapsed_time = now - start_timestamp
            if self.use_duration:
                self.remaining_time = max(0.0, self.duration_seconds - self.elapsed_time)
                if self.elapsed_time >= self.duration_seconds:
                    return False
            else:
                self.remaining_time = 0.0

            if self.on_tick:
                try:
                    self.on_tick(self.remaining_time, self.elapsed_time)
                except Exception:
                    pass

            sleep_chunk = min(0.04, end_time - time.time())
            if sleep_chunk > 0:
                time.sleep(sleep_chunk)

        return True

    def _worker(self):
        """Worker loop that traverses points sequentially in queue (1 > 2 > 3 ...)."""
        self._set_status("RUNNING")
        self.current_cycle = 0
        self.total_clicks = 0
        start_time = time.time()

        active_count = sum(1 for pt in self.points if pt.get("enabled", True))
        self._log(f"Auto Clicker STARTED ({active_count}/{len(self.points)} active targets).")

        try:
            while not self._stop_event.is_set():
                # Ensure at least one enabled point exists
                if not any(pt.get("enabled", True) for pt in self.points):
                    self._log("Warning: All targets are disabled! Stopping.")
                    self._set_status("STOPPED")
                    return

                self.current_cycle += 1
                if self.on_cycle:
                    try:
                        self.on_cycle(self.current_cycle)
                    except Exception:
                        pass

                self._log(f"--- Cycle #{self.current_cycle} started ---")

                total_steps = len(self.points)
                for idx, pt in enumerate(self.points):
                    if self._stop_event.is_set():
                        break

                    if not pt.get("enabled", True):
                        continue

                    while not self._pause_event.is_set():
                        if self._stop_event.is_set():
                            break
                        time.sleep(0.04)

                    now = time.time()
                    self.elapsed_time = now - start_time
                    if self.use_duration and self.elapsed_time >= self.duration_seconds:
                        self._log(f"Active timer finished ({self.duration_seconds}s). Completed automatically.")
                        self._set_status("COMPLETED")
                        return

                    self.current_step_index = idx + 1
                    if self.on_step:
                        try:
                            self.on_step(self.current_step_index, total_steps, pt)
                        except Exception:
                            pass

                    # Perform click (supports burst repeat count)
                    label = pt.get("label", f"Target {self.current_step_index}")
                    x = pt.get("x", 0)
                    y = pt.get("y", 0)
                    click_type = pt.get("click_type", "left")
                    repeat_count = max(1, int(pt.get("repeat", 1)))

                    last_cx, last_cy = x, y
                    for r_idx in range(repeat_count):
                        if self._stop_event.is_set():
                            break
                        res = self.perform_click(
                            x, y, click_type,
                            apply_jitter=True,
                            restore_pos=self.restore_cursor
                        )
                        if isinstance(res, tuple):
                            last_cx, last_cy = res
                        if r_idx < repeat_count - 1:
                            if not self._responsive_sleep(0.06, start_time):
                                break

                    rep_tag = f" x{repeat_count}" if repeat_count > 1 else ""
                    self._log(
                        f"Clicked [{self.current_step_index}/{total_steps}] '{label}' "
                        f"at ({last_cx}, {last_cy}) [{click_type}{rep_tag}]"
                    )

                    # Calculate step delay
                    delay = pt.get("delay")
                    if delay is None or delay <= 0:
                        delay = self.default_delay

                    if self.random_jitter > 0:
                        jitter = random.uniform(-self.random_jitter, self.random_jitter)
                        delay = max(0.01, delay + jitter)

                    # Wait delay
                    if not self._responsive_sleep(delay, start_time):
                        if self.use_duration and (time.time() - start_time) >= self.duration_seconds:
                            self._log(f"Active timer expired ({self.duration_seconds}s). Completed.")
                            self._set_status("COMPLETED")
                            return
                        self._log("Auto Clicker stopped.")
                        self._set_status("STOPPED")
                        return

                if self.use_max_cycles and self.current_cycle >= self.max_cycles:
                    self._log(f"Target cycle limit ({self.max_cycles}) reached. Completed.")
                    self._set_status("COMPLETED")
                    return

            self._log("Auto Clicker stopped by user.")
            self._set_status("STOPPED")

        except Exception as e:
            self._log(f"Engine worker error: {e}")
            self._set_status("STOPPED")

    def start(self) -> bool:
        if self.is_running():
            return False

        if not self.points or not any(pt.get("enabled", True) for pt in self.points):
            self._log("Warning: No active targets in sequence! Add or enable at least 1 target.")
            return False

        self._stop_event.clear()
        self._pause_event.set()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        return True

    def pause(self):
        if self.is_running() and self.status == "RUNNING":
            self._pause_event.clear()
            self._set_status("PAUSED")
            self._log("Auto Clicker PAUSED. Press F6 to resume.")

    def resume(self):
        if self.is_running() and self.status == "PAUSED":
            self._pause_event.set()
            self._set_status("RUNNING")
            self._log("Auto Clicker RESUMED.")

    def toggle_pause(self):
        if not self.is_running():
            self.start()
        elif self.status == "PAUSED":
            self.resume()
        elif self.status == "RUNNING":
            self.pause()

    def stop(self):
        if self.is_running():
            self._stop_event.set()
            self._pause_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1.0)
            self._set_status("STOPPED")
            self._log("Auto Clicker STOPPED.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
