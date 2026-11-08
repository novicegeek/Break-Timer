"""Break Timer — Modern break reminder with web-based UI."""
import ctypes
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


_dpi_ready = False


def _enable_dpi_awareness():
    """Make Win32 coordinates match the physical pixels that pywebview's
    WinForms window placement uses (it is built DpiAware), so the pop-up
    lands on-screen on high-DPI laptops instead of off the right edge."""
    global _dpi_ready
    if _dpi_ready:
        return
    _dpi_ready = True
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
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


# ── Pop-up alert window ──────────────────────────────────────

_POPUP_W, _POPUP_H = 360, 300


_ALERT_TEXT = {
    True: {"kind": "work", "title": "Work Complete - Break Timer",
           "heading": "Work Complete!", "msg": "Time for a break",
           "primary": "Start Break", "ghost": "+5 Minutes", "emoji": "☕"},
    False: {"kind": "break", "title": "Break Over - Break Timer",
            "heading": "Break Over!", "msg": "Time to focus",
            "primary": "Start Working", "ghost": "+5 Minutes", "emoji": "💪"},
}


def _raise_window(title):
    """Show the alert on top of the other windows, once, without keeping it
    pinned above everything afterwards."""
    try:
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, title)
        if not hwnd:
            return
        u.ShowWindow(hwnd, 9)  # SW_RESTORE
        # Briefly flag it topmost so it comes up above the current window,
        # then drop the flag: it behaves like a normal window from then on.
        u.SetWindowPos(hwnd, -1, 0, 0, 0, 0,      # HWND_TOPMOST
                       0x0001 | 0x0002 | 0x0004 | 0x0040)
        # NOSIZE | NOMOVE | NOACTIVATE | SHOWWINDOW
        tid = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
        cur = ctypes.windll.kernel32.GetCurrentThreadId()
        if tid and tid != cur:
            u.AttachThreadInput(cur, tid, True)
        u.SetForegroundWindow(hwnd)
        u.BringWindowToTop(hwnd)
        if tid and tid != cur:
            u.AttachThreadInput(cur, tid, False)
        u.SetWindowPos(hwnd, -2, 0, 0, 0, 0,      # HWND_NOTOPMOST
                       0x0001 | 0x0002 | 0x0004)
    except Exception:
        pass


def _nudge_window_foreground(title):
    """Let the freshly created window finish laying out, then raise it."""
    def _run():
        time.sleep(0.6)
        _raise_window(title)

    threading.Thread(target=_run, daemon=True).start()


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

        self._alert_lock = threading.Lock()
        self._alert_win = None
        self._alert_data = {}

    def set_window(self, window):
        self._window = window
        window.events.closed += self._on_main_closed

    def _on_main_closed(self):
        # Closing the timer also closes any alert window that is still open
        self._close_popup()

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
        # Pop up a separate alert window so the reminder is visible even when
        # the timer window is behind other windows or minimized.
        self._open_popup(self._is_work)

    # ── Alert pop-up ──────────────────────────────────────────

    def _open_popup(self, is_work):
        info = dict(_ALERT_TEXT[bool(is_work)])
        info["is_work"] = bool(is_work)
        with self._alert_lock:
            if self._alert_win is not None:
                # An alert is already on screen: refresh it instead of stacking
                self._close_popup_locked()
            self._alert_data = info

        # Build the alert page with this alert's texts baked in. Pass it as
        # HTML rather than a temp file: pywebview's local server needs the
        # page to live next to index.html.
        html = None
        try:
            with open(_res("alert.html"), encoding="utf-8") as f:
                html = f.read()
            js = ("<script>window.__ALERT__="
                  + json.dumps(info, ensure_ascii=True)
                  + ";</script>")
            html = html.replace("</head>", js + "\n</head>")
        except OSError:
            html = None

        # Appear where the timer window is, so it is always on-screen
        x = y = None
        try:
            x, y = self._window.x + 16, self._window.y + 16
        except Exception:
            pass

        common = dict(
            js_api=self, width=_POPUP_W, height=_POPUP_H,
            x=x, y=y, resizable=False, on_top=False, easy_drag=False,
        )
        try:
            if html is not None:
                win = webview.create_window(
                    info["title"], html=html, **common)
            else:
                win = webview.create_window(
                    info["title"], url=_res("alert.html"), **common)
        except Exception:
            try:
                win = webview.create_window(
                    info["title"], url=_res("alert.html"), **common)
            except Exception:
                return

        with self._alert_lock:
            self._alert_win = win
        win.events.closed += self._on_popup_closed
        # Show it above whatever the user is doing right now
        _nudge_window_foreground(info["title"])

    def _on_popup_closed(self):
        with self._alert_lock:
            self._alert_win = None
        try:
            self._push_state()
        except Exception:
            pass

    def _close_popup_locked(self):
        win, self._alert_win = self._alert_win, None
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass

    def _close_popup(self):
        with self._alert_lock:
            self._close_popup_locked()

    # Buttons on the alert window call these

    def alert_primary(self):
        info = dict(self._alert_data)
        self._close_popup()
        cfg = _load_settings()
        args = (
            cfg.get("work_m", _DEFAULTS["work_m"]),
            cfg.get("work_s", _DEFAULTS["work_s"]),
            cfg.get("break_m", _DEFAULTS["break_m"]),
            cfg.get("break_s", _DEFAULTS["break_s"]),
        )
        if info.get("is_work"):
            self.start_break(*args)
        else:
            self.start_work(*args)

    def alert_extend(self):
        self._close_popup()
        self.extend(5)

    def alert_dismiss(self):
        self._close_popup()


if __name__ == "__main__":
    _enable_dpi_awareness()
    api = TimerAPI()
    window = webview.create_window(
        "Break Timer",
        url=_res("index.html"), js_api=api,
        width=400, height=620, resizable=False,
    )
    api.set_window(window)

    _set_window_icon_async("Break Timer")
    webview.start()
