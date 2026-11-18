"""
Clipboard Injector & Win32 Atomic Paste Simulator — Antigravity Smart Voice Engine.

Implements battle-tested Windows automation patterns (inspired by Microsoft PowerToys
Advanced Paste & ShareX):
  1. Explicit 64-bit Win32 GlobalAlloc / CF_HDROP handle safety.
  2. Physical modifier-release guard (waits until user lifts fingers from Ctrl/CapsLock/F9/F10)
     so physical KeyUp events NEVER cancel synthetic Ctrl+V and produce bare 'v' or 'ر'.
  3. True 64-bit Win32 SendInput (40-byte INPUT struct) with deterministic settle intervals.
  4. Foreground HWND verification so paste never lands on a background/helper window.
"""

import ctypes
from ctypes import wintypes
import os
import time
import logging
from typing import Optional, Iterable

logger = logging.getLogger("VoiceEngine")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

ULONG_PTR = wintypes.WPARAM

# -------------------------------------------------------------
# 64-bit Windows Prototype Specifications
# -------------------------------------------------------------
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL

kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID

kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL

kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL

user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL

user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE

user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT

CF_UNICODETEXT = 13
CF_HDROP = 15
GHND = 0x0042
GMEM_MOVEABLE = 0x0002

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

VK_CONTROL = 0x11
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_MENU = 0x12
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_CAPITAL = 0x14
VK_V = 0x56
VK_RETURN = 0x0D
VK_F9 = 0x78
VK_F10 = 0x79

SCAN_LCTRL = 0x1D
SCAN_V = 0x2F
SCAN_ENTER = 0x1C

# Keys that must be physically released by the user before firing synthetic Ctrl+V
GUARDED_RELEASE_VKS = (
    VK_CONTROL, VK_LCONTROL, VK_RCONTROL,
    VK_MENU, VK_LMENU, VK_RMENU,
    VK_SHIFT, VK_LSHIFT, VK_RSHIFT,
    VK_CAPITAL, VK_F9, VK_F10,
)


class DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("fNC", wintypes.BOOL),
        ("fWide", wintypes.BOOL),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTunion),
    ]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def _send_key_input(vk: int, scan: int, key_up: bool = False) -> bool:
    """Dispatches a single keyboard event via Win32 SendInput with full 64-bit struct alignment."""
    flags = KEYEVENTF_KEYUP if key_up else 0
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(
        wVk=vk,
        wScan=scan,
        dwFlags=flags,
        time=0,
        dwExtraInfo=0,
    )
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    return sent == 1


class ClipboardInjector:
    """Handles native 64-bit Windows clipboard operations and race-free input simulation."""

    @staticmethod
    def get_foreground_hwnd() -> int:
        """Returns the HWND of the currently focused window (0 if none)."""
        hwnd = user32.GetForegroundWindow()
        return int(hwnd) if hwnd else 0

    @staticmethod
    def get_window_title(hwnd: int) -> str:
        """Returns window title for a specific HWND."""
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    @staticmethod
    def get_foreground_window_title() -> str:
        """Returns the title of the currently focused window."""
        return ClipboardInjector.get_window_title(ClipboardInjector.get_foreground_hwnd())

    @staticmethod
    def ensure_target_focus(
        fallback_hwnd: int,
        ignored_hwnds: Optional[Iterable[int]] = None,
    ) -> int:
        """
        Ensures a valid target window owns focus before pasting.
        Only restores fallback_hwnd if current foreground is 0 or an internal overlay window,
        preserving focus if the user intentionally switched chat windows while speaking.
        """
        ignored = set(int(h) for h in (ignored_hwnds or ()) if h)
        cur_hwnd = ClipboardInjector.get_foreground_hwnd()
        if cur_hwnd and cur_hwnd not in ignored:
            return cur_hwnd

        if fallback_hwnd and fallback_hwnd not in ignored and user32.IsWindow(fallback_hwnd):
            user32.SetForegroundWindow(fallback_hwnd)
            time.sleep(0.04)
            return ClipboardInjector.get_foreground_hwnd() or fallback_hwnd
        return cur_hwnd

    @staticmethod
    def wait_for_modifiers_release(timeout_ms: int = 450, extra_vks: Optional[Iterable[int]] = None) -> None:
        """
        Waits until the user physically releases hotkey modifiers (Ctrl, CapsLock, F9, F10, etc.).
        Prevents physical KeyUp from racing with synthetic Ctrl+V and producing bare 'v' or 'ر'.
        """
        vks = list(GUARDED_RELEASE_VKS)
        if extra_vks:
            for vk in extra_vks:
                if vk not in vks:
                    vks.append(vk)

        deadline = time.monotonic() + (max(0, timeout_ms) / 1000.0)
        while time.monotonic() < deadline:
            any_down = any(bool(user32.GetAsyncKeyState(vk) & 0x8000) for vk in vks)
            if not any_down:
                # Extra 15ms debounce settle after finger lift
                time.sleep(0.015)
                return
            time.sleep(0.010)

    @staticmethod
    def set_clipboard_file(file_path: str) -> bool:
        """
        Places file in Windows Clipboard as CF_HDROP (file drop) and CF_UNICODETEXT.
        Uses explicit 64-bit types to prevent handle truncation.
        """
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            logger.error(f"Cannot set clipboard: file does not exist '{abs_path}'")
            return False

        # Prepare CF_HDROP double-null-terminated wide string
        drop_bytes = (abs_path + "\0\0").encode("utf-16le")
        df = DROPFILES(pFiles=ctypes.sizeof(DROPFILES), fWide=True)

        total_drop_size = ctypes.sizeof(DROPFILES) + len(drop_bytes)
        h_drop = kernel32.GlobalAlloc(GHND, total_drop_size)
        if not h_drop:
            logger.error("GlobalAlloc failed for CF_HDROP")
            return False

        p_drop = kernel32.GlobalLock(h_drop)
        if not p_drop:
            kernel32.GlobalFree(h_drop)
            logger.error("GlobalLock failed for CF_HDROP")
            return False

        ctypes.memmove(p_drop, ctypes.byref(df), ctypes.sizeof(DROPFILES))
        ctypes.memmove(p_drop + ctypes.sizeof(DROPFILES), drop_bytes, len(drop_bytes))
        kernel32.GlobalUnlock(h_drop)

        # Prepare CF_UNICODETEXT fallback
        text_bytes = (abs_path + "\0").encode("utf-16le")
        h_text = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
        if h_text:
            p_text = kernel32.GlobalLock(h_text)
            if p_text:
                ctypes.memmove(p_text, text_bytes, len(text_bytes))
                kernel32.GlobalUnlock(h_text)

        # Open and set clipboard with retries and strict HGLOBAL ownership safety
        for _attempt in range(10):
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    res_drop = user32.SetClipboardData(CF_HDROP, h_drop)
                    if not res_drop:
                        logger.error(f"SetClipboardData CF_HDROP failed: err={kernel32.GetLastError()}")
                        kernel32.GlobalFree(h_drop)
                    if h_text:
                        res_text = user32.SetClipboardData(CF_UNICODETEXT, h_text)
                        if not res_text:
                            kernel32.GlobalFree(h_text)
                    return bool(res_drop)
                finally:
                    user32.CloseClipboard()
            time.sleep(0.03)

        kernel32.GlobalFree(h_drop)
        if h_text:
            kernel32.GlobalFree(h_text)
        logger.error(f"Failed to open clipboard after retries: err={kernel32.GetLastError()}")
        return False

    @staticmethod
    def simulate_paste(delay_ms: int = 120, extra_release_vks: Optional[Iterable[int]] = None) -> bool:
        """
        Simulates Ctrl+V reliably across Arabic & English keyboard layouts and Electron/Chromium apps:
          1. Waits for clipboard OS lock flush (delay_ms).
          2. Waits until user physically lifts fingers from hotkey modifiers.
          3. Sends LCTRL down -> 35ms settle -> V down -> 25ms hold -> V up -> 20ms -> LCTRL up via Win32 SendInput.
        """
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

        # Critical: wait until physical Ctrl / CapsLock / F9 / F10 are released by user's hand
        ClipboardInjector.wait_for_modifiers_release(timeout_ms=450, extra_vks=extra_release_vks)

        try:
            ok1 = _send_key_input(VK_LCONTROL, SCAN_LCTRL, key_up=False)
            time.sleep(0.035)  # Allow Electron/Chromium input queue to latch ctrlKey=True
            ok2 = _send_key_input(VK_V, SCAN_V, key_up=False)
            time.sleep(0.025)
            ok3 = _send_key_input(VK_V, SCAN_V, key_up=True)
            time.sleep(0.020)
            ok4 = _send_key_input(VK_LCONTROL, SCAN_LCTRL, key_up=True)
            if ok1 and ok2 and ok3 and ok4:
                return True
        except Exception as e:
            logger.warning(f"SendInput Ctrl+V warning, trying keybd_event fallback: {e}")

        # Fallback: Win32 keybd_event with identical safe settle intervals
        try:
            user32.keybd_event(VK_LCONTROL, SCAN_LCTRL, 0, 0)
            time.sleep(0.035)
            user32.keybd_event(VK_V, SCAN_V, 0, 0)
            time.sleep(0.025)
            user32.keybd_event(VK_V, SCAN_V, KEYEVENTF_KEYUP, 0)
            time.sleep(0.020)
            user32.keybd_event(VK_LCONTROL, SCAN_LCTRL, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            logger.error(f"Failed to simulate paste: {e}")
            return False

    @staticmethod
    def simulate_enter(delay_ms: int = 100) -> bool:
        """Simulates Enter key press via Win32 SendInput."""
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

        try:
            ok1 = _send_key_input(VK_RETURN, SCAN_ENTER, key_up=False)
            time.sleep(0.025)
            ok2 = _send_key_input(VK_RETURN, SCAN_ENTER, key_up=True)
            if ok1 and ok2:
                return True
        except Exception:
            pass

        try:
            user32.keybd_event(VK_RETURN, SCAN_ENTER, 0, 0)
            time.sleep(0.025)
            user32.keybd_event(VK_RETURN, SCAN_ENTER, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            logger.error(f"Failed to simulate enter: {e}")
            return False
