"""Break Timer — Modern break reminder with web-based UI."""
import json
import os
import struct
import sys
import threading
import time

try:
    import webview
except ImportError:
    print("Break Timer requires pywebview. Install it with: pip install pywebview")
    print("(Windows 11 already includes the WebView2 runtime.)")
    input("\nPress Enter to exit...")
    sys.exit(1)


def _app_dir():
    """Directory for user data (settings.json lives alongside the executable)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _res(rel):
    """Path to a resource bundled by PyInstaller (index.html, timer.png)."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)


_DEFAULTS = {"work_m": 45, "work_s": 0, "break_m": 10, "break_s": 0}


def _load_settings():
    p = os.path.join(_app_dir(), "settings.json")
    try:
        with open(p) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def _save_settings(work_m, work_s, break_m, break_s):
    p = os.path.join(_app_dir(), "settings.json")
    try:
        with open(p, "w") as f:
            json.dump({"work_m": work_m, "work_s": work_s,
                       "break_m": break_m, "break_s": break_s}, f)
    except OSError:
        pass


def _set_window_icon_async(title):
    """Daemon thread: wrap timer.png as ICO and set it as the window icon."""
    png_path = _res("timer.png")
    ico_dir = _app_dir()
    ico_path = os.path.join(ico_dir, "timer.ico")

    if not os.path.exists(png_path):
        return

    # Build ICO from PNG — ICO is just a header + raw PNG data
    if not os.path.exists(ico_path):
        try:
            with open(png_path, "rb") as f:
                png_data = f.read()
            buf = struct.pack("<HHH", 0, 1, 1)
            buf += struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png_data), 22)
            buf += png_data
            with open(ico_path, "wb") as f:
                f.write(buf)
        except OSError:
            ico_path = png_path  # fall back to PNG

    def _apply():
        time.sleep(0.3)
        try:
            import ctypes
            hwnd = ctypes.windll.user32.FindWindowW(None, title)
            if not hwnd:
                return
            hicon = ctypes.windll.user32.LoadImageW(
                None, ico_path, 1, 0, 0, 0x00000010
            )
            if hicon:
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon)
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon)
        except Exception:
            pass

    threading.Thread(target=_apply, daemon=True).start()


class TimerAPI:
    """Bridge between the HTML/JS UI and Python timer logic."""

    def __init__(self):
        self._window = None
        self._lock = threading.Lock()

        self._running = False
        self._is_work = True
        self._current_sec = 0
        self._target_sec = 0

        self._thread = None
        self._stop_ev = threading.Event()

    def set_window(self, window):
        self._window = window

    # ── Called from JS ────────────────────────────────────────

    def get_state(self):
        return {
            "current_sec": self._current_sec,
            "target_sec": self._target_sec,
            "is_work": int(self._is_work),
            "running": int(self._running),
        }

    def get_settings(self):
        return _load_settings()

    def close_window(self):
        if self._window:
            self._window.destroy()

    def start_work(self, work_m, work_s, break_m, break_s):
        _save_settings(work_m, work_s, break_m, break_s)
        with self._lock:
            self._teardown_thread()
            self._is_work = True
            self._current_sec = 0
            self._target_sec = work_m * 60 + work_s
            self._running = True
            self._spawn()
            self._push_state()

    def start_break(self, work_m, work_s, break_m, break_s):
        _save_settings(work_m, work_s, break_m, break_s)
        with self._lock:
            self._teardown_thread()
            self._is_work = False
            target = break_m * 60 + break_s
            self._target_sec = target
            self._current_sec = target
            self._running = True
            self._spawn()
            self._push_state()

    def toggle(self, work_m=0, work_s=0, break_m=0, break_s=0):
        if work_m or work_s or break_m or break_s:
            _save_settings(work_m, work_s, break_m, break_s)
        with self._lock:
            if self._running:
                self._running = False
            else:
                if self._target_sec == 0:
                    if self._is_work:
                        self._target_sec = work_m * 60 + work_s
                    else:
                        self._target_sec = break_m * 60 + break_s
                    self._current_sec = (
                        0 if self._is_work else self._target_sec
                    )
                self._running = True
                self._stop_ev.clear()
                self._spawn()
            self._push_state()

    def reset(self, work_m, work_s, break_m, break_s):
        _save_settings(work_m, work_s, break_m, break_s)
        with self._lock:
            self._running = False
            if self._is_work:
                self._current_sec = 0
                self._target_sec = work_m * 60 + work_s
            else:
                self._target_sec = break_m * 60 + break_s
                self._current_sec = self._target_sec
            self._push_state()

    def switch_mode(self, work_m, work_s, break_m, break_s):
        _save_settings(work_m, work_s, break_m, break_s)
        with self._lock:
            self._teardown_thread()
            self._is_work = not self._is_work
            if self._is_work:
                self._current_sec = 0
                self._target_sec = work_m * 60 + work_s
            else:
                self._target_sec = break_m * 60 + break_s
                self._current_sec = self._target_sec
            self._running = True
            self._spawn()
            self._push_state()

    def extend(self, minutes):
        with self._lock:
            added = minutes * 60
            if self._is_work:
                self._target_sec += added
            else:
                self._current_sec += added
            if not self._running:
                self._running = True
                self._stop_ev.clear()
                self._spawn()
            self._push_state()

    # ── Internal ──────────────────────────────────────────────

    def _teardown_thread(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._stop_ev.set()
            self._thread.join(timeout=2)
            self._stop_ev.clear()

    def _spawn(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        finished = False
        while self._running:
            if self._stop_ev.wait(1):
                break
            with self._lock:
                if not self._running:
                    break
                if self._is_work:
                    self._current_sec += 1
                else:
                    self._current_sec -= 1

                done = (
                    self._is_work and self._current_sec >= self._target_sec
                ) or (
                    not self._is_work and self._current_sec <= 0
                )
                if done:
                    self._running = False
                    finished = True

            self._push_state()
            if finished:
                self._push_finished()
                break

    def _push_state(self):
        if self._window:
            self._window.evaluate_js(
                f"window.__update({self._current_sec},{self._target_sec},"
                f"{int(self._is_work)},{int(self._running)})"
            )

    def _push_finished(self):
        if self._window:
            self._window.evaluate_js(f"window.__done({int(self._is_work)})")


if __name__ == "__main__":
    api = TimerAPI()
    window = webview.create_window(
        "Break Timer",
        url=_res("index.html"), js_api=api,
        width=400, height=620, resizable=False,
    )
    api.set_window(window)

    _set_window_icon_async("Break Timer")
    webview.start()
