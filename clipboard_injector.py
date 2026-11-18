"""
Clipboard Injector & Honest Win32 SendInput Simulator — Antigravity Smart Voice Engine.

Implements Gate-1 verified clipboard & input rules:
  1. Centralized 64-bit Win32 prototypes with use_last_error=True (CB-04).
  2. Strict HGLOBAL ownership transfer & cleanup on failure (CB-10).
  3. Boolean modifier-release guard checking BOTH GetAsyncKeyState and hook _phys_down
     (CB-02, R10): aborts paste (returns False) if modifiers remain held past timeout,
     eliminating any residual window for bare 'v' / 'ر'.
  4. Honest SendInput-only execution (CB-11, A3): lying void keybd_event fallback removed.
"""

import ctypes
import logging
import os
import time
from typing import Optional, Iterable, Callable

from win32_api import (
    user32,
    kernel32,
    DROPFILES,
    INPUT,
    KEYBDINPUT,
    CF_UNICODETEXT,
    CF_HDROP,
    GHND,
    GMEM_MOVEABLE,
    INPUT_KEYBOARD,
    KEYEVENTF_KEYUP,
    get_process_exe_name,
)

logger = logging.getLogger("VoiceEngine")

# Named Engineering Constants (R6)
PASTE_CTRL_SETTLE_SEC = 0.035
PASTE_V_HOLD_SEC = 0.025
PASTE_V_RELEASE_SETTLE_SEC = 0.020
MODIFIER_RELEASE_DEBOUNCE_SEC = 0.015

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

GUARDED_RELEASE_VKS = (
    VK_CONTROL, VK_LCONTROL, VK_RCONTROL,
    VK_MENU, VK_LMENU, VK_RMENU,
    VK_SHIFT, VK_LSHIFT, VK_RSHIFT,
    VK_CAPITAL, VK_F9, VK_F10,
)


def _send_key_input(vk: int, scan: int, key_up: bool = False) -> bool:
    """Dispatches a single keyboard event via Win32 SendInput (40-byte Win64 ABI)."""
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
    """Handles native 64-bit Windows clipboard operations and honest SendInput paste."""

    @staticmethod
    def get_foreground_hwnd() -> int:
        hwnd = user32.GetForegroundWindow()
        return int(hwnd) if hwnd else 0

    @staticmethod
    def get_window_title(hwnd: int) -> str:
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    @staticmethod
    def get_window_exe_name(hwnd: int) -> str:
        return get_process_exe_name(hwnd)

    @staticmethod
    def get_foreground_window_title() -> str:
        return ClipboardInjector.get_window_title(ClipboardInjector.get_foreground_hwnd())

    @staticmethod
    def ensure_target_focus(
        fallback_hwnd: int,
        ignored_hwnds: Optional[Iterable[int]] = None,
    ) -> int:
        """
        Returns the active foreground HWND, restoring fallback_hwnd only if focus shifted
        to an internal overlay window. If foreground is 0 (e.g. UAC / Win+L Secure Desktop),
        returns 0 so caller skips blind paste (HK-03 / DEC-03).
        """
        ignored = set(int(h) for h in (ignored_hwnds or ()) if h)
        cur_hwnd = ClipboardInjector.get_foreground_hwnd()
        if cur_hwnd == 0:
            return 0
        if cur_hwnd not in ignored:
            return cur_hwnd

        if fallback_hwnd and fallback_hwnd not in ignored and user32.IsWindow(fallback_hwnd):
            user32.SetForegroundWindow(fallback_hwnd)
            time.sleep(0.04)
            new_fg = ClipboardInjector.get_foreground_hwnd()
            if new_fg and new_fg not in ignored:
                return new_fg
        return 0

    @staticmethod
    def is_paste_allowed_for_process(
        exe_name: str,
        blocked_processes: Optional[Iterable[str]] = None,
        allowed_processes: Optional[Iterable[str]] = None,
    ) -> bool:
        """
        Evaluates target process against blocked/allowed lists (DEC-02, R5):
          • Fail-open when exe_name == '' unless an explicit allowlist is configured.
          • Blocks explorer.exe etc. to prevent copying audio files into folders.
        """
        norm_exe = (exe_name or "").strip().lower()
        allowed_set = {p.strip().lower() for p in (allowed_processes or ()) if p and p.strip()}
        blocked_set = {p.strip().lower() for p in (blocked_processes or ()) if p and p.strip()}

        if allowed_set:
            return bool(norm_exe) and (norm_exe in allowed_set)
        if not norm_exe:
            return True  # R5: Fail-open when process image query is denied by OS
        return norm_exe not in blocked_set

    @staticmethod
    def wait_for_modifiers_release(
        timeout_ms: int = 450,
        extra_vks: Optional[Iterable[int]] = None,
        phys_down_checker: Optional[Callable[[Iterable[int]], bool]] = None,
    ) -> bool:
        """
        Waits until user physically lifts fingers from guarded modifiers & trigger keys.
        Returns True when all keys are released, or False if still held at timeout (CB-02, R10).
        """
        vks = list(GUARDED_RELEASE_VKS)
        if extra_vks:
            for vk in extra_vks:
                if vk not in vks:
                    vks.append(vk)

        deadline = time.monotonic() + (max(0, timeout_ms) / 1000.0)
        while True:
            os_down = any(bool(user32.GetAsyncKeyState(vk) & 0x8000) for vk in vks)
            hook_down = bool(phys_down_checker(vks)) if phys_down_checker else False
            if not os_down and not hook_down:
                time.sleep(MODIFIER_RELEASE_DEBOUNCE_SEC)
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.010)

    @staticmethod
    def set_clipboard_file(file_path: str) -> bool:
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            logger.error(f"Cannot set clipboard: file does not exist '{abs_path}'")
            return False

        drop_bytes = (abs_path + "\0\0").encode("utf-16le")
        df = DROPFILES(pFiles=ctypes.sizeof(DROPFILES), fWide=True)

        total_drop_size = ctypes.sizeof(DROPFILES) + len(drop_bytes)
        h_drop = kernel32.GlobalAlloc(GHND, total_drop_size)
        if not h_drop:
            logger.error(f"GlobalAlloc failed for CF_HDROP (WinError={ctypes.get_last_error()})")
            return False

        p_drop = kernel32.GlobalLock(h_drop)
        if not p_drop:
            kernel32.GlobalFree(h_drop)
            logger.error(f"GlobalLock failed for CF_HDROP (WinError={ctypes.get_last_error()})")
            return False

        ctypes.memmove(p_drop, ctypes.byref(df), ctypes.sizeof(DROPFILES))
        ctypes.memmove(p_drop + ctypes.sizeof(DROPFILES), drop_bytes, len(drop_bytes))
        kernel32.GlobalUnlock(h_drop)

        text_bytes = (abs_path + "\0").encode("utf-16le")
        h_text = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
        if h_text:
            p_text = kernel32.GlobalLock(h_text)
            if p_text:
                ctypes.memmove(p_text, text_bytes, len(text_bytes))
                kernel32.GlobalUnlock(h_text)
            else:
                kernel32.GlobalFree(h_text)
                h_text = None

        for _attempt in range(10):
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    res_drop = user32.SetClipboardData(CF_HDROP, h_drop)
                    if not res_drop:
                        logger.error(f"SetClipboardData CF_HDROP failed (WinError={ctypes.get_last_error()})")
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
        logger.error(f"Failed to open clipboard after retries (WinError={ctypes.get_last_error()})")
        return False

    @staticmethod
    def simulate_paste(
        delay_ms: int = 120,
        extra_release_vks: Optional[Iterable[int]] = None,
        phys_down_checker: Optional[Callable[[Iterable[int]], bool]] = None,
    ) -> bool:
        """
        Sends sequenced Ctrl+V via Win32 SendInput ONLY after verifying physical modifiers
        are released. Returns False honestly on timeout or UIPI block (A3, CB-02, CB-11).
        """
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

        released = ClipboardInjector.wait_for_modifiers_release(
            timeout_ms=450,
            extra_vks=extra_release_vks,
            phys_down_checker=phys_down_checker,
        )
        if not released:
            logger.warning("⚠️ Aborting auto-paste: modifier keys still physically held after 450ms.")
            return False

        ctrl_down = _send_key_input(VK_LCONTROL, SCAN_LCTRL, key_up=False)
        if not ctrl_down:
            logger.warning(f"⚠️ SendInput(LCTRL down) blocked (WinError={ctypes.get_last_error()}).")
            return False

        try:
            time.sleep(PASTE_CTRL_SETTLE_SEC)
            v_down = _send_key_input(VK_V, SCAN_V, key_up=False)
            time.sleep(PASTE_V_HOLD_SEC)
            v_up = _send_key_input(VK_V, SCAN_V, key_up=True)
            time.sleep(PASTE_V_RELEASE_SETTLE_SEC)
        finally:
            ctrl_up = _send_key_input(VK_LCONTROL, SCAN_LCTRL, key_up=True)

        if not (v_down and v_up and ctrl_up):
            logger.warning(f"⚠️ SendInput(Ctrl+V) incomplete (WinError={ctypes.get_last_error()}).")
            return False
        return True

    @staticmethod
    def simulate_enter(delay_ms: int = 300) -> bool:
        """Simulates Enter key press via Win32 SendInput with honest bool return (A3)."""
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

        ok1 = _send_key_input(VK_RETURN, SCAN_ENTER, key_up=False)
        if not ok1:
            logger.warning(f"⚠️ SendInput(Enter down) blocked (WinError={ctypes.get_last_error()}).")
            return False
        time.sleep(0.025)
        ok2 = _send_key_input(VK_RETURN, SCAN_ENTER, key_up=True)
        return bool(ok1 and ok2)
