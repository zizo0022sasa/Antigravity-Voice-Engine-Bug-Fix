"""
Adaptive Hotkey Listener — Antigravity Smart Voice Engine.

Combines two battle-tested Win32 mechanisms (inspired by AutoHotkey v2 & Microsoft PowerToys):
  1. Win32 Low-Level Keyboard Hook (WH_KEYBOARD_LL) on a dedicated message-pump thread:
     - Sub-millisecond non-blocking callback dispatching to an async worker queue.
     - Suppresses trigger keys (e.g., F10 so it NEVER activates the Windows Menu Bar,
       F9 so it NEVER triggers breakpoints, and CapsLock in CTRL+CAPSLOCK so LED NEVER toggles).
     - Ignores synthetic/injected events (LLKHF_INJECTED) to prevent feedback loops.
  2. Lightweight GetAsyncKeyState Watchdog & Mouse Fallback:
     - Supports mouse side buttons (MOUSE_X1, MOUSE_X2, MOUSE_MIDDLE).
     - Provides seamless fallback in elevated (Run-as-Admin) windows where UIPI blocks hooks.
     - Guarantees zero stuck-key states across window switches or Win+L lock screen.
"""

import ctypes
from ctypes import wintypes
import queue
import threading
import time
from typing import Callable, Optional, List, Set

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_ssize_t
ULONG_PTR = wintypes.WPARAM

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x00000010


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT

user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = wintypes.SHORT

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

# Comprehensive Virtual Key Codes mapping
VK_MAP = {
    # Function Keys
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "F13": 0x7C, "F14": 0x7D, "F15": 0x7E, "F16": 0x7F,
    "F17": 0x80, "F18": 0x81, "F19": 0x82, "F20": 0x83,
    "F21": 0x84, "F22": 0x85, "F23": 0x86, "F24": 0x87,

    # Modifiers & Locks
    "CTRL": 0x11, "CONTROL": 0x11, "LCTRL": 0xA2, "RCTRL": 0xA3,
    "ALT": 0x12, "LALT": 0xA4, "RALT": 0xA5,
    "SHIFT": 0x10, "LSHIFT": 0xA0, "RSHIFT": 0xA1,
    "WIN": 0x5B, "WINDOWS": 0x5B,
    "CAPSLOCK": 0x14, "CAPS": 0x14, "CAPS_LOCK": 0x14, "CAPITAL": 0x14,

    # System & Media
    "PRINTSCREEN": 0x2C, "PRTSC": 0x2C, "PRINT_SCREEN": 0x2C, "SNAPSHOT": 0x2C,
    "INSERT": 0x2D, "PAUSE": 0x13, "SCROLL_LOCK": 0x91, "SCROLLLOCK": 0x91,
    "PAGE_UP": 0x21, "PAGE_DOWN": 0x22, "HOME": 0x24, "END": 0x23,
    "SPACE": 0x20, "TAB": 0x09, "ESC": 0x1B, "ESCAPE": 0x1B,

    # Mouse Buttons
    "MOUSE_X1": 0x05, "MOUSE_SIDE1": 0x05, "MOUSE_BACK": 0x05,
    "MOUSE_X2": 0x06, "MOUSE_SIDE2": 0x06, "MOUSE_FORWARD": 0x06,
    "MOUSE_MIDDLE": 0x04,
}

MODIFIER_FAMILIES = {
    0x11: (0x11, 0xA2, 0xA3),  # CTRL
    0xA2: (0xA2,),
    0xA3: (0xA3,),
    0x12: (0x12, 0xA4, 0xA5),  # ALT
    0xA4: (0xA4,),
    0xA5: (0xA5,),
    0x10: (0x10, 0xA0, 0xA1),  # SHIFT
    0xA0: (0xA0,),
    0xA1: (0xA1,),
    0x5B: (0x5B, 0x5C),        # WIN
}

MOUSE_VKS = {0x04, 0x05, 0x06}


def _is_vk_down(vk: int) -> bool:
    """Checks physical key state via GetAsyncKeyState, expanding generic modifiers."""
    family = MODIFIER_FAMILIES.get(vk, (vk,))
    return any(bool(user32.GetAsyncKeyState(code) & 0x8000) for code in family)


class _HotkeyRule:
    """Represents one parsed hotkey or chord (e.g., 'CTRL+CAPSLOCK' or 'F10')."""

    def __init__(self, raw_spec: str):
        self.raw_spec = raw_spec.upper().strip()
        parts = [p.strip().replace(" ", "") for p in self.raw_spec.split("+") if p.strip()]
        vks = [VK_MAP[p] for p in parts if p in VK_MAP]
        if not vks:
            vks = [0x78]  # Default fallback: F9

        self.vk_codes: List[int] = vks
        self.modifier_vks: List[int] = vks[:-1]
        self.trigger_vk: int = vks[-1]
        self.is_mouse: bool = any(vk in MOUSE_VKS for vk in vks)
        self.is_active: bool = False
        self.activated_by_hook: bool = False
        self.caps_initial_state: int = 0
        self.has_caps: bool = (0x14 in vks)

    def matches_modifier_release(self, vk: int) -> bool:
        for mod in self.modifier_vks:
            if vk in MODIFIER_FAMILIES.get(mod, (mod,)):
                return True
        return False

    def all_modifiers_down(self) -> bool:
        return all(_is_vk_down(mod) for mod in self.modifier_vks)

    def all_keys_down(self) -> bool:
        return all(_is_vk_down(vk) for vk in self.vk_codes)


class BaseHotkeyListener:
    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError


class AdaptiveHotkeyListener(BaseHotkeyListener):
    """
    High-level multi-hotkey listener supporting single keys, combinations,
    and comma-separated hotkeys (e.g. 'CTRL+CAPSLOCK, F9, F10') with OS key suppression.
    """

    def __init__(self, key_name: str, on_press: Callable[[], None], on_release: Callable[[], None]):
        raw_specs = [k.strip() for k in key_name.split(",") if k.strip()]
        if not raw_specs:
            raw_specs = ["F9"]

        self.rules: List[_HotkeyRule] = [_HotkeyRule(spec) for spec in raw_specs]
        self.on_press = on_press
        self.on_release = on_release

        self._running = False
        self._state_lock = threading.Lock()
        self._event_queue: "queue.SimpleQueue[Optional[str]]" = queue.SimpleQueue()

        self._hook_handle: Optional[wintypes.HHOOK] = None
        self._hook_thread_id: int = 0
        self._hook_proc_ref: Optional[HOOKPROC] = None

        self._hook_thread: Optional[threading.Thread] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._hook_ready = threading.Event()

    @property
    def all_vk_codes(self) -> Set[int]:
        """Returns all virtual key codes monitored across all configured rules."""
        out: Set[int] = set()
        for rule in self.rules:
            for vk in rule.vk_codes:
                out.update(MODIFIER_FAMILIES.get(vk, (vk,)))
        return out

    def _any_other_rule_active(self, exclude_rule: _HotkeyRule) -> bool:
        return any(r.is_active for r in self.rules if r is not exclude_rule)

    def _worker_loop(self):
        """Executes on_press / on_release outside the Win32 hook thread so input never lags."""
        while self._running:
            action = self._event_queue.get()
            if action is None:
                break
            try:
                if action == "press":
                    self.on_press()
                elif action == "release":
                    self.on_release()
            except Exception:
                pass

    def _low_level_proc(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0 and lParam:
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            # Ignore synthetic events (e.g. our own SendInput Ctrl+V or AutoHotkey remaps)
            if not (kb.flags & LLKHF_INJECTED):
                vk = int(kb.vkCode)
                is_down_msg = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                is_up_msg = wParam in (WM_KEYUP, WM_SYSKEYUP)

                suppress = False
                with self._state_lock:
                    for rule in self.rules:
                        if rule.is_mouse:
                            continue

                        if is_down_msg and vk == rule.trigger_vk:
                            if rule.is_active:
                                # Auto-repeat while holding trigger key -> keep suppressed!
                                suppress = True
                            elif rule.all_modifiers_down():
                                was_any_active = self._any_other_rule_active(rule)
                                rule.is_active = True
                                rule.activated_by_hook = True
                                suppress = True
                                if not was_any_active:
                                    self._event_queue.put_nowait("press")

                        elif is_up_msg and rule.is_active:
                            if vk == rule.trigger_vk:
                                rule.is_active = False
                                rule.activated_by_hook = False
                                suppress = True
                                if not self._any_other_rule_active(rule):
                                    self._event_queue.put_nowait("release")
                            elif rule.matches_modifier_release(vk):
                                # Modifier lifted first: end hotkey, pass modifier KeyUp to OS
                                rule.is_active = False
                                rule.activated_by_hook = False
                                if not self._any_other_rule_active(rule):
                                    self._event_queue.put_nowait("release")

                if suppress:
                    return 1

        return user32.CallNextHookEx(self._hook_handle, nCode, wParam, lParam)

    def _hook_thread_main(self):
        """Dedicated Win32 message loop hosting WH_KEYBOARD_LL."""
        self._hook_thread_id = int(kernel32.GetCurrentThreadId())
        self._hook_proc_ref = HOOKPROC(self._low_level_proc)
        hmod = kernel32.GetModuleHandleW(None)
        self._hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc_ref, hmod, 0)
        self._hook_ready.set()

        if not self._hook_handle:
            return

        msg = wintypes.MSG()
        while self._running:
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res <= 0:
                break

        if self._hook_handle:
            user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None

    def _watchdog_loop(self):
        """
        Companion 35ms polling loop:
          1. Handles mouse triggers (MOUSE_X1/X2/MIDDLE).
          2. Catches keyboard triggers inside Elevated (Admin) windows where UIPI hides hook events.
          3. Releases any active rule immediately if physical keys are no longer held.
        """
        while self._running:
            with self._state_lock:
                for rule in self.rules:
                    physically_down = rule.all_keys_down()

                    if physically_down and not rule.is_active:
                        # Triggered via mouse button OR inside an elevated window bypassed by UIPI
                        was_any_active = self._any_other_rule_active(rule)
                        if rule.has_caps:
                            rule.caps_initial_state = user32.GetKeyState(0x14) & 1
                        rule.is_active = True
                        rule.activated_by_hook = False
                        if not was_any_active:
                            self._event_queue.put_nowait("press")

                    elif not physically_down and rule.is_active:
                        was_hook = rule.activated_by_hook
                        rule.is_active = False
                        rule.activated_by_hook = False
                        # Restore CapsLock only if it wasn't suppressed by the hook
                        if not was_hook and rule.has_caps:
                            cur_caps = user32.GetKeyState(0x14) & 1
                            if cur_caps != rule.caps_initial_state:
                                user32.keybd_event(0x14, 0, 0, 0)
                                user32.keybd_event(0x14, 0, 2, 0)
                        if not self._any_other_rule_active(rule):
                            self._event_queue.put_nowait("release")

            time.sleep(0.035)

    def start(self):
        if self._running:
            return
        self._running = True
        self._hook_ready.clear()

        self._worker_thread = threading.Thread(target=self._worker_loop, name="VoiceHotkeyWorker", daemon=True)
        self._worker_thread.start()

        self._hook_thread = threading.Thread(target=self._hook_thread_main, name="VoiceHotkeyLLHook", daemon=True)
        self._hook_thread.start()
        self._hook_ready.wait(timeout=0.5)

        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, name="VoiceHotkeyWatchdog", daemon=True)
        self._watchdog_thread.start()

    def stop(self):
        if not self._running:
            return
        self._running = False

        if self._hook_thread_id:
            try:
                user32.PostThreadMessageW(self._hook_thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass

        self._event_queue.put_nowait(None)

        if self._hook_thread:
            self._hook_thread.join(timeout=0.3)
            self._hook_thread = None
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=0.3)
            self._watchdog_thread = None
        if self._worker_thread:
            self._worker_thread.join(timeout=0.3)
            self._worker_thread = None
