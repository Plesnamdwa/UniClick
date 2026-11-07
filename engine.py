import time
import random
import threading
import ctypes
from ctypes import wintypes
from typing import List, Dict, Any, Callable, Optional
from hotkeys import get_current_mouse_pos
from win_timer import enable_high_precision_timer, disable_high_precision_timer

# Windows input constants and structures
ULONG_PTR = ctypes.c_size_t

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


class AutoClickerEngine:
    """High-precision clicking engine supporting multi-target click sequences, burst clicks, and timers."""

    def __init__(self):
        self.points: List[Dict[str, Any]] = []
        self.default_delay: float = 1.0       # seconds (float)
        self.random_jitter: float = 0.0       # humanized time jitter seconds (+/-)
        self.pixel_jitter: int = 0            # humanized spatial coordinate jitter (+/- px)
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

        self.status = "IDLE"  # IDLE, RUNNING, PAUSED, COMPLETED, STOPPED
        self.current_cycle: int = 0
        self.current_step_index: int = 0
        self.total_clicks: int = 0
        self.elapsed_time: float = 0.0
        self.remaining_time: float = 0.0
        self._paused_duration: float = 0.0

        # Callbacks
        self.on_status_change: Optional[Callable[[str], None]] = None
        self.on_step: Optional[Callable[[int, int, Dict[str, Any]], None]] = None
        self.on_cycle: Optional[Callable[[int], None]] = None
        self.on_tick: Optional[Callable[[float, float], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None

        self._user32 = ctypes.windll.user32
        self._setup_win32_prototypes()

    def _setup_win32_prototypes(self):
        """Pre-bind ctypes argtypes and restypes to eliminate dynamic marshalling overhead."""
        try:
            self._user32.SetCursorPos.argtypes = [ctypes.c_long, ctypes.c_long]
            self._user32.SetCursorPos.restype = wintypes.BOOL
        except Exception:
            pass

        try:
            self._user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
            self._user32.SendInput.restype = wintypes.UINT
        except Exception:
            pass

        try:
            self._user32.mouse_event.argtypes = [
                wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ULONG_PTR
            ]
            self._user32.mouse_event.restype = None
        except Exception:
            pass

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

    def _emit_click_batch(self, flags_list: list[int]):
        """Dispatches mouse event flags atomically using SendInput with fallback to mouse_event."""
        n = len(flags_list)
        if n == 0:
            return

        arr = (INPUT * n)()
        for i, flag in enumerate(flags_list):
            arr[i].type = INPUT_MOUSE
            arr[i].u.mi.dx = 0
            arr[i].u.mi.dy = 0
            arr[i].u.mi.mouseData = 0
            arr[i].u.mi.dwFlags = flag
            arr[i].u.mi.time = 0
            arr[i].u.mi.dwExtraInfo = 0

        sent = self._user32.SendInput(n, arr, ctypes.sizeof(INPUT))
        if sent != n:
            # Fallback to legacy mouse_event if SendInput is blocked by OS session/integrity
            for flag in flags_list:
                self._user32.mouse_event(flag, 0, 0, 0, 0)

    def perform_click(
        self,
        x: int,
        y: int,
        click_type: str = "left",
        apply_jitter: bool = False,
        restore_pos: bool = False
    ) -> tuple[int, int]:
        """Simulates rapid, reliable mouse click at specified coordinates across any monitor.
        Returns actual (clicked_x, clicked_y)."""
        orig_x, orig_y = (0, 0)
        if restore_pos:
            orig_x, orig_y = get_current_mouse_pos()

        target_x, target_y = int(x), int(y)
        if apply_jitter and self.pixel_jitter > 0:
            target_x += random.randint(-self.pixel_jitter, self.pixel_jitter)
            target_y += random.randint(-self.pixel_jitter, self.pixel_jitter)

        # Win32 SetCursorPos handles multi-monitor coordinates seamlessly
        self._user32.SetCursorPos(target_x, target_y)

        if click_type == "double":
            self._emit_click_batch([MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP])
            time.sleep(0.012)
            self._emit_click_batch([MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP])
            self.total_clicks += 2
        elif click_type == "right":
            self._emit_click_batch([MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP])
            self.total_clicks += 1
        elif click_type == "middle":
            self._emit_click_batch([MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP])
            self.total_clicks += 1
        else:  # Default left click
            self._emit_click_batch([MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP])
            self.total_clicks += 1

        if restore_pos:
            self._user32.SetCursorPos(orig_x, orig_y)

        return target_x, target_y

    def _responsive_sleep(self, seconds: float, start_mono: float) -> bool:
        """High-precision responsive sleep that tracks pause/stop and timers accurately with 1ms resolution."""
        if seconds <= 0:
            return not self._stop_event.is_set()

        end_time = time.perf_counter() + seconds
        last_tick_time = 0.0

        while True:
            if self._stop_event.is_set():
                return False

            if not self._pause_event.is_set():
                pause_start = time.perf_counter()
                while not self._pause_event.is_set():
                    if self._stop_event.is_set():
                        return False
                    time.sleep(0.015)
                pause_spent = time.perf_counter() - pause_start
                self._paused_duration += pause_spent
                end_time += pause_spent  # extend sleep target cleanly by paused duration

            now_mono = time.perf_counter()
            rem = end_time - now_mono
            if rem <= 0:
                break

            self.elapsed_time = max(0.0, (now_mono - start_mono) - self._paused_duration)
            if self.use_duration:
                self.remaining_time = max(0.0, self.duration_seconds - self.elapsed_time)
                if self.elapsed_time >= self.duration_seconds:
                    return False
            else:
                self.remaining_time = 0.0

            # Throttle on_tick callbacks to at most once every ~80ms (12 FPS) to prevent UI flooding
            if self.on_tick and (now_mono - last_tick_time >= 0.08):
                last_tick_time = now_mono
                try:
                    self.on_tick(self.remaining_time, self.elapsed_time)
                except Exception:
                    pass

            if rem > 0.012:
                # Sleep in chunks up to 0.05s using Event.wait so stop() wakes it immediately
                sleep_chunk = min(0.05, rem - 0.003)
                if self._stop_event.wait(sleep_chunk):
                    return False
            else:
                # Sub-millisecond spin for the final boundary
                pass

        return True

    def _worker(self):
        """Worker loop that traverses points sequentially in queue (1 > 2 > 3 ...)."""
        self._set_status("RUNNING")
        self.current_cycle = 0
        self.total_clicks = 0
        self._paused_duration = 0.0
        start_mono = time.perf_counter()

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

                # Snapshot points list to prevent race conditions during point addition/removal
                pts_snapshot = list(self.points)
                total_steps = len(pts_snapshot)

                for idx, pt in enumerate(pts_snapshot):
                    if self._stop_event.is_set():
                        break

                    if not pt.get("enabled", True):
                        continue

                    if not self._pause_event.is_set():
                        pause_start = time.perf_counter()
                        while not self._pause_event.is_set():
                            if self._stop_event.is_set():
                                break
                            time.sleep(0.015)
                        pause_spent = time.perf_counter() - pause_start
                        self._paused_duration += pause_spent

                    now_mono = time.perf_counter()
                    self.elapsed_time = max(0.0, (now_mono - start_mono) - self._paused_duration)
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

                    # Step timing mark for drift-compensated precision sleep
                    step_start = time.perf_counter()

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
                            apply_jitter=bool(self.pixel_jitter > 0),
                            restore_pos=self.restore_cursor
                        )
                        if isinstance(res, tuple):
                            last_cx, last_cy = res
                        if r_idx < repeat_count - 1:
                            if not self._responsive_sleep(0.015, start_mono):
                                break

                    # Calculate step delay
                    delay = pt.get("delay")
                    if delay is None or delay <= 0:
                        delay = self.default_delay

                    if self.random_jitter > 0:
                        jitter = random.uniform(-self.random_jitter, self.random_jitter)
                        delay = max(0.005, delay + jitter)

                    # Only log individual clicks if delay is comfortable (>= 0.25s) or total steps > 1
                    # to prevent UI message queue flood on high-speed auto clicking (e.g. 10+ CPS)
                    if delay >= 0.25 or total_steps > 1:
                        rep_tag = f" x{repeat_count}" if repeat_count > 1 else ""
                        self._log(
                            f"Clicked [{self.current_step_index}/{total_steps}] '{label}' "
                            f"at ({last_cx}, {last_cy}) [{click_type}{rep_tag}]"
                        )

                    # Compensate execution time so total step interval is exactly equal to 'delay'
                    elapsed_in_click = time.perf_counter() - step_start
                    sleep_needed = max(0.001, delay - elapsed_in_click)

                    # Wait delay
                    if not self._responsive_sleep(sleep_needed, start_mono):
                        now_mono = time.perf_counter()
                        self.elapsed_time = max(0.0, (now_mono - start_mono) - self._paused_duration)
                        if self.use_duration and self.elapsed_time >= self.duration_seconds:
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
        finally:
            disable_high_precision_timer()

    def start(self) -> bool:
        if self.is_running():
            return False

        if not self.points or not any(pt.get("enabled", True) for pt in self.points):
            self._log("Warning: No active targets in sequence! Add or enable at least 1 target.")
            return False

        enable_high_precision_timer()
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
                self._thread.join(timeout=0.15)
            self._set_status("STOPPED")
            self._log("Auto Clicker STOPPED.")
            disable_high_precision_timer()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
