"""
Floating Voice Capsule Overlay — Antigravity Smart Voice Engine.

Engineered for 4K / High-DPI (100%–300% scaling) and Multi-Monitor setups:
  • Queries live Win32 MonitorFromWindow + GetMonitorInfoW (rcWork) + GetDpiForMonitor
    on EVERY show/reposition, so HDMI TV reconnects or DPI changes NEVER misplace the pill.
  • Scales pill geometry and waveform bars proportionally to the target monitor's DPI
    while preserving native crisp Tkinter font rendering.
  • Applies WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_TRANSPARENT
    to the true outer Win32 top-level window (GetAncestor(..., GA_ROOT) = TkTopLevel),
    guaranteeing zero focus theft and full mouse click-through.
"""

import math
import random
import logging
import threading
import time
from typing import Optional, Callable, Tuple
import tkinter as tk
import ctypes
from ctypes import wintypes

logger = logging.getLogger("VoiceOverlay")

user32 = ctypes.windll.user32

# Win32 Window Styles & Monitor APIs
GWL_EXSTYLE = -20
GA_ROOT = 2
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SW_SHOWNOACTIVATE = 4
MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND

user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR

user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HMONITOR

user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL


def _query_active_monitor_workarea_and_scale() -> Tuple[int, int, int, int, float]:
    """
    Returns (work_left, work_top, work_right, work_bottom, dpi_scale)
    for the monitor containing the active window (or cursor fallback).
    """
    hmon = None
    fg_hwnd = user32.GetForegroundWindow()
    if fg_hwnd:
        hmon = user32.MonitorFromWindow(fg_hwnd, MONITOR_DEFAULTTONEAREST)
    if not hmon:
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)

    scale = 1.0
    try:
        dpi_x = wintypes.UINT(96)
        dpi_y = wintypes.UINT(96)
        res = ctypes.windll.shcore.GetDpiForMonitor(
            hmon, MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
        )
        if res == 0 and dpi_x.value > 0:
            scale = max(1.0, float(dpi_x.value) / 96.0)
        else:
            sys_dpi = user32.GetDpiForSystem()
            if sys_dpi > 0:
                scale = max(1.0, float(sys_dpi) / 96.0)
    except Exception:
        pass

    if hmon:
        mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return (
                int(mi.rcWork.left),
                int(mi.rcWork.top),
                int(mi.rcWork.right),
                int(mi.rcWork.bottom),
                scale,
            )

    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    return (0, 0, sw, sh, scale)


class VoiceOverlay:
    """
    Ultra-sleek, High-DPI aware floating pill widget (الكبسولة الشاملة الذكية).
    Renders real-time animated microphone waveform, timer, and status without stealing focus.
    """

    def __init__(
        self,
        enabled: bool = True,
        position: str = "bottom_center",
        offset_y: int = 36,
        width: int = 260,
        height: int = 44,
        show_timer: bool = True,
        show_waveform: bool = True,
        waveform_bars: int = 7,
        theme: str = "dark",
        level_source: Optional[Callable[[], float]] = None,
        duration_source: Optional[Callable[[], float]] = None,
    ):
        self.enabled = enabled
        self.position = position
        self.base_offset_y = offset_y
        self.base_width = width
        self.base_height = height
        self.show_timer = show_timer
        self.show_waveform = show_waveform
        self.waveform_bars = max(3, min(15, waveform_bars))
        self.theme = theme

        # Effective physical dimensions (dynamically scaled per monitor DPI)
        self._scale: float = 1.0
        self.width: int = width
        self.height: int = height
        self.offset_y: int = offset_y

        self.level_source = level_source
        self.duration_source = duration_source

        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._hwnd: Optional[int] = None
        self._top_hwnd: Optional[int] = None
        self._state: str = "IDLE"  # "IDLE", "RECORDING", "SUCCESS"
        self._success_text: str = "⚡ تم اللصق!"

        self._anim_timer_id: Optional[str] = None
        self._hide_timer_id: Optional[str] = None

        self._current_bar_heights = [4.0] * self.waveform_bars
        self._bar_multipliers = self._calc_multipliers(self.waveform_bars)

    @property
    def window_hwnds(self) -> Tuple[int, ...]:
        """Returns HWNDs owned by this overlay so focus guards can ignore them."""
        return tuple(h for h in (self._top_hwnd, self._hwnd) if h)

    def _calc_multipliers(self, count: int):
        mid = (count - 1) / 2.0
        multipliers = []
        for i in range(count):
            dist = abs(i - mid) / (mid if mid > 0 else 1.0)
            m = 1.0 - (0.60 * (dist ** 1.5))
            multipliers.append(max(0.35, m))
        return multipliers

    def init_ui(self):
        """Initializes the Tkinter root window and canvas."""
        if not self.enabled or self._root is not None:
            return

        try:
            self._root = tk.Tk()
            self._root.title("Antigravity Voice Capsule")
            self._root.overrideredirect(True)
            self._root.withdraw()

            transparent_color = "#000001"
            self._root.wm_attributes("-transparentcolor", transparent_color)
            self._root.wm_attributes("-topmost", True)
            self._root.configure(bg=transparent_color)

            self._canvas = tk.Canvas(
                self._root,
                width=self.width,
                height=self.height,
                bg=transparent_color,
                highlightthickness=0,
            )
            self._canvas.pack(fill="both", expand=True)

            self._root.update_idletasks()
            self._apply_win32_styles()
            self._reposition()
            self._ui_thread = threading.current_thread()
        except Exception as e:
            logger.warning(f"⚠️ VoiceOverlay GUI initialization warning: {e}")
            self._root = None

    def run_mainloop(self):
        """Runs the mainloop on the calling thread (main thread)."""
        if not self.enabled:
            return
        if self._root is None:
            self.init_ui()
        if self._root:
            try:
                self._root.mainloop()
            except Exception as e:
                logger.debug(f"Mainloop exit note: {e}")

    def _apply_win32_styles(self):
        """
        Applies WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, and WS_EX_TRANSPARENT
        directly onto the true outer Win32 top-level window (GA_ROOT / TkTopLevel).
        """
        if not self._root:
            return
        try:
            child_hwnd = int(self._root.winfo_id())
            top_hwnd = int(user32.GetAncestor(child_hwnd, GA_ROOT)) or child_hwnd
            self._hwnd = child_hwnd
            self._top_hwnd = top_hwnd

            for hwnd in {top_hwnd, child_hwnd}:
                cur_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                new_style = (
                    cur_style
                    | WS_EX_NOACTIVATE
                    | WS_EX_TOOLWINDOW
                    | WS_EX_TOPMOST
                    | WS_EX_TRANSPARENT
                )
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        except Exception as e:
            logger.debug(f"Win32 style application note: {e}")

    def _reposition(self):
        """
        Dynamically queries live monitor work-area and DPI scaling, resizing and centering
        the capsule right above the Windows Taskbar (bottom_center).
        """
        if not self._root or not self._canvas:
            return

        w_left, w_top, w_right, w_bottom, scale = _query_active_monitor_workarea_and_scale()
        self._scale = scale

        # Synchronize Tk font scaling with the monitor's exact DPI (dpi / 72.0 points-per-inch)
        try:
            self._root.tk.call("tk", "scaling", (scale * 96.0) / 72.0)
        except Exception:
            pass

        self.width = max(180, int(round(self.base_width * scale)))
        self.height = max(36, int(round(self.base_height * scale)))
        self.offset_y = int(round(self.base_offset_y * scale))

        self._canvas.configure(width=self.width, height=self.height)

        work_w = max(1, w_right - w_left)
        pos = self.position.lower()
        margin_x = int(round(30 * scale))

        if pos == "bottom_right":
            x = w_right - self.width - margin_x
            y = w_bottom - self.height - self.offset_y
        elif pos == "top_center":
            x = w_left + (work_w - self.width) // 2
            y = w_top + self.offset_y
        else:  # default "bottom_center" (anchored cleanly above Taskbar via rcWork.bottom)
            x = w_left + (work_w - self.width) // 2
            y = w_bottom - self.height - self.offset_y

        self._root.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def _draw_pill_background(self, fill_color="#121317", border_color="#2b2d37"):
        """Draws a smooth rounded pill container scaled to current DPI."""
        if not self._canvas:
            return
        self._canvas.delete("bg_pill")
        pad = max(2, int(round(2 * self._scale)))
        r = max(8, (self.height - pad * 2) // 2)
        x1, y1 = pad, pad
        x2, y2 = self.width - pad, self.height - pad

        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        self._canvas.create_polygon(
            points,
            fill=fill_color,
            outline=border_color,
            width=max(1.5, 1.5 * self._scale),
            smooth=True,
            tags="bg_pill",
        )

    # ------------------ Thread-Safe Public API ------------------

    def show_recording(self):
        if not self.enabled or not self._root:
            return
        self._state = "RECORDING"
        self._root.after(0, self._on_show_recording)

    def show_success(self, text: str = "⚡ تم اللصق!"):
        if not self.enabled or not self._root:
            return
        self._state = "SUCCESS"
        self._success_text = text
        self._root.after(0, self._on_show_success)

    def hide(self):
        if not self.enabled or not self._root:
            return
        self._state = "IDLE"
        self._root.after(0, self._on_hide)

    def stop(self):
        if self._root:
            try:
                if threading.current_thread() == getattr(self, "_ui_thread", None):
                    self._on_stop()
                else:
                    self._root.after(0, self._on_stop)
            except Exception:
                pass

    # ------------------ Internal Handlers ------------------

    def _on_show_recording(self):
        if not self._root or not self._canvas:
            return

        if self._hide_timer_id:
            try:
                self._root.after_cancel(self._hide_timer_id)
            except Exception:
                pass
            self._hide_timer_id = None

        self._state = "RECORDING"
        self._reposition()
        self._apply_win32_styles()
        self._current_bar_heights = [4.0 * self._scale] * self.waveform_bars

        # Show window without stealing keyboard focus
        self._root.deiconify()
        try:
            target = self._top_hwnd or self._hwnd
            if target:
                user32.ShowWindow(target, SW_SHOWNOACTIVATE)
        except Exception:
            pass

        if self._anim_timer_id:
            try:
                self._root.after_cancel(self._anim_timer_id)
            except Exception:
                pass
        self._render_recording_frame()

    def _on_show_success(self):
        if not self._root or not self._canvas:
            return

        if self._anim_timer_id:
            try:
                self._root.after_cancel(self._anim_timer_id)
            except Exception:
                pass
            self._anim_timer_id = None

        self._state = "SUCCESS"
        self._render_success_frame()

        if self._hide_timer_id:
            try:
                self._root.after_cancel(self._hide_timer_id)
            except Exception:
                pass
        self._hide_timer_id = self._root.after(950, self._on_hide)

    def _on_hide(self):
        if not self._root:
            return

        if self._anim_timer_id:
            try:
                self._root.after_cancel(self._anim_timer_id)
            except Exception:
                pass
            self._anim_timer_id = None

        if self._hide_timer_id:
            try:
                self._root.after_cancel(self._hide_timer_id)
            except Exception:
                pass
            self._hide_timer_id = None

        self._state = "IDLE"
        self._root.withdraw()

    def _on_stop(self):
        if not self._root:
            return
        self._on_hide()
        try:
            self._root.quit()
            self._root.destroy()
        except Exception:
            pass
        self._root = None
        self._state = "IDLE"

    # ------------------ Rendering Loops ------------------

    def _render_recording_frame(self):
        if self._state != "RECORDING" or not self._canvas or not self._root:
            return

        s = self._scale
        self._canvas.delete("all")
        self._draw_pill_background(fill_color="#121317", border_color="#2c2e39")

        cy = self.height / 2.0
        now = time.time()

        # 1. Pulsing Red Recording Dot
        pulse = (math.sin(now * 5.0) + 1.0) / 2.0
        dot_r = (4.2 + (pulse * 1.5)) * s
        dot_color = "#ff2247" if pulse > 0.3 else "#a3132c"
        dot_x = 24.0 * s
        self._canvas.create_oval(
            dot_x - dot_r, cy - dot_r, dot_x + dot_r, cy + dot_r,
            fill=dot_color, outline="", tags="dot",
        )

        # 2. Timer Text (font points scale via Tk DPI scaling automatically)
        duration_sec = 0.0
        if self.duration_source:
            try:
                duration_sec = self.duration_source()
            except Exception:
                pass
        m = int(duration_sec // 60)
        sec = int(duration_sec % 60)
        timer_str = f"{m:02d}:{sec:02d}"

        self._canvas.create_text(
            46.0 * s, cy,
            text=timer_str,
            font=("Consolas", 11, "bold"),
            fill="#f0f2f5",
            anchor="w",
            tags="timer",
        )

        # 3. Subtle Divider
        div_x = 108.0 * s
        self._canvas.create_line(
            div_x, cy - 9.0 * s, div_x, cy + 9.0 * s,
            fill="#323542", width=max(1.0, 1.2 * s), tags="divider",
        )

        # 4. Live Equalizer Waveform Bars
        cur_level = 0.0
        if self.level_source:
            try:
                cur_level = self.level_source()
            except Exception:
                pass

        bar_count = self.waveform_bars
        start_x = 124.0 * s
        end_x = self.width - (22.0 * s)
        span = max(20.0, end_x - start_x)
        bar_w = 4.0 * s
        spacing = (span - (bar_count * bar_w)) / max(1, (bar_count - 1))

        is_voice_active = cur_level > 0.06
        min_h = 4.0 * s
        max_h = 24.0 * s

        for i in range(bar_count):
            mult = self._bar_multipliers[i]
            jitter = (random.random() * 0.15 - 0.075) if is_voice_active else 0.0
            eff_level = max(0.0, min(1.0, cur_level * mult + jitter))
            target_h = min_h + (max_h - min_h) * eff_level

            current_h = self._current_bar_heights[i]
            if target_h > current_h:
                new_h = current_h + (target_h - current_h) * 0.55
            else:
                new_h = current_h + (target_h - current_h) * 0.25
            self._current_bar_heights[i] = new_h

            if is_voice_active:
                bar_color = "#ff3355" if eff_level > 0.3 else "#ff667d"
            else:
                bar_color = "#4c5061"

            bx = start_x + i * (bar_w + spacing)
            by1 = cy - (new_h / 2.0)
            by2 = cy + (new_h / 2.0)

            self._canvas.create_line(
                bx + bar_w / 2.0, by1,
                bx + bar_w / 2.0, by2,
                fill=bar_color, width=bar_w, capstyle="round", tags="wave",
            )

        if self._state == "RECORDING" and self._root:
            self._anim_timer_id = self._root.after(35, self._render_recording_frame)

    def _render_success_frame(self):
        if not self._canvas:
            return

        self._canvas.delete("all")
        self._draw_pill_background(fill_color="#0e1f18", border_color="#185c37")

        cy = self.height / 2.0
        cx = self.width / 2.0

        self._canvas.create_text(
            cx, cy,
            text=self._success_text,
            font=("Segoe UI", 11, "bold"),
            fill="#00e676",
            anchor="center",
            tags="success",
        )
