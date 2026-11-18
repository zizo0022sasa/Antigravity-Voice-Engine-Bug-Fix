"""
Adaptive Hotkey Listener — Antigravity Smart Voice Engine.

Implements Gate-1 verified Win32 input architecture:
  1. Exclusive Hook Ownership (HK-11 / A1): Rules activated by WH_KEYBOARD_LL are owned
     exclusively by the hook and NEVER prematurely released by GetAsyncKeyState polling
     (since win32k does not update gafAsyncKeyState for keys suppressed via return 1).
  2. Physical Key Shadow Set (_phys_down) & Symmetrical KeyUp Suppression (_suppressed_down)
     (HK-12 / A5 / R10 / N2): Any key suppressed on KeyDown is guaranteed to be suppressed on KeyUp.
  3. Self-Healing Heartbeat Probe (HK-01 / HK-07 / A2 / N1): Sends neutral VK_NONAME (0xFC)
     KEYUP tagged with HOOK_PROBE_MAGIC every 2.0s while idle; auto-reinstalls hook if dropped.
  4. Strict Modifier Exclusivity (HK-02 / DEC-01) & Token Validation (CF-01).
"""

import ctypes
from ctypes import wintypes
import logging
import queue
import threading
import time
from typing import Callable, Optional, List, Set, Iterable

from win32_api import (
    user32,
    kernel32,
    KBDLLHOOKSTRUCT,
    HOOKPROC,
    INPUT,
    KEYBDINPUT,
    INPUT_KEYBOARD,
    KEYEVENTF_KEYUP,
    WH_KEYBOARD_LL,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_SYSKEYDOWN,
    WM_SYSKEYUP,
    WM_QUIT,
    LLKHF_INJECTED,
    is_input_desktop_accessible,
)

logger = logging.getLogger("VoiceEngine")

# Named Engineering Constants (R6 — internal physics, NOT user config)
WATCHDOG_POLL_SEC = 0.035
HOOK_PROBE_INTERVAL_SEC = 2.0
HOOK_PROBE_TIMEOUT_SEC = 4.5
HOOK_REINSTALL_BACKOFF_SEC = 5.0
DEFAULT_ORPHAN_TIMEOUT_SEC = 305.0
VK_PROBE_NONAME = 0xFC
HOOK_PROBE_MAGIC = 0x41475956  # "AGYV"

# Comprehensive Virtual Key Codes mapping (including A-Z and 0-9 per CF-01)
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
    "WIN": 0x5B, "WINDOWS": 0x5B, "LWIN": 0x5B, "RWIN": 0x5C,
    "CAPSLOCK": 0x14, "CAPS": 0x14, "CAPS_LOCK": 0x14, "CAPITAL": 0x14,

    # System & Navigation
    "PRINTSCREEN": 0x2C, "PRTSC": 0x2C, "PRINT_SCREEN": 0x2C, "SNAPSHOT": 0x2C,
    "INSERT": 0x2D, "DELETE": 0x2E, "DEL": 0x2E, "PAUSE": 0x13,
    "SCROLL_LOCK": 0x91, "SCROLLLOCK": 0x91,
    "PAGE_UP": 0x21, "PAGE_DOWN": 0x22, "HOME": 0x24, "END": 0x23,
    "SPACE": 0x20, "TAB": 0x09, "ESC": 0x1B, "ESCAPE": 0x1B,
    "TILDE": 0xC0, "BACKTICK": 0xC0, "GRAVE": 0xC0,

    # Mouse Buttons
    "MOUSE_X1": 0x05, "MOUSE_SIDE1": 0x05, "MOUSE_BACK": 0x05,
    "MOUSE_X2": 0x06, "MOUSE_SIDE2": 0x06, "MOUSE_FORWARD": 0x06,
    "MOUSE_MIDDLE": 0x04,
}
for _ch_code in range(ord("A"), ord("Z") + 1):
    VK_MAP[chr(_ch_code)] = _ch_code
for _dig_code in range(ord("0"), ord("9") + 1):
    VK_MAP[chr(_dig_code)] = _dig_code

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
    0x5C: (0x5C,),
}

CANONICAL_MODIFIER_FAMILIES = (
    (0x11, 0xA2, 0xA3),  # CTRL family
    (0x12, 0xA4, 0xA5),  # ALT family
    (0x10, 0xA0, 0xA1),  # SHIFT family
    (0x5B, 0x5C),        # WIN family
)

MOUSE_VKS = {0x04, 0x05, 0x06}


def _is_vk_down_os(vk: int, phys_down: Optional[Set[int]] = None) -> bool:
    """Checks key state via hook shadow set (_phys_down) + GetAsyncKeyState."""
    family = MODIFIER_FAMILIES.get(vk, (vk,))
    if phys_down and any(code in phys_down for code in family):
        return True
    return any(bool(user32.GetAsyncKeyState(code) & 0x8000) for code in family)


class _HotkeyRule:
    """Represents a validated hotkey or chord (e.g., 'CTRL+CAPSLOCK' or 'F10')."""

    def __init__(self, raw_spec: str):
        self.raw_spec = raw_spec.upper().strip()
        parts = [p.strip().replace(" ", "") for p in self.raw_spec.split("+") if p.strip()]
        if not parts:
            raise ValueError("Empty hotkey specification")

        unknown = [p for p in parts if p not in VK_MAP]
        if unknown:
            raise ValueError(f"Unknown key token(s) in '{raw_spec}': {unknown}")

        self.vk_codes: List[int] = [VK_MAP[p] for p in parts]
        self.modifier_vks: List[int] = self.vk_codes[:-1]
        self.trigger_vk: int = self.vk_codes[-1]
        self.is_mouse: bool = any(vk in MOUSE_VKS for vk in self.vk_codes)
        self.is_active: bool = False
        self.activated_by_hook: bool = False
        self.activated_time: float = 0.0
        self.caps_initial_state: int = 0
        self.has_caps: bool = (0x14 in self.vk_codes)

        # Precompute allowed modifier codes so strict_modifiers check is O(1)
        allowed: Set[int] = set()
        for mod in self.modifier_vks:
            allowed.update(MODIFIER_FAMILIES.get(mod, (mod,)))
        allowed.update(MODIFIER_FAMILIES.get(self.trigger_vk, (self.trigger_vk,)))
        self._allowed_mod_codes: Set[int] = allowed

    def matches_trigger(self, vk: int) -> bool:
        return vk in MODIFIER_FAMILIES.get(self.trigger_vk, (self.trigger_vk,))

    def matches_modifier_release(self, vk: int) -> bool:
        for mod in self.modifier_vks:
            if vk in MODIFIER_FAMILIES.get(mod, (mod,)):
                return True
        return False

    def modifiers_satisfied(self, strict: bool, phys_down: Optional[Set[int]] = None) -> bool:
        if not all(_is_vk_down_os(mod, phys_down) for mod in self.modifier_vks):
            return False
        if strict:
            for fam in CANONICAL_MODIFIER_FAMILIES:
                if any(code in self._allowed_mod_codes for code in fam):
                    continue
                if any(_is_vk_down_os(code, phys_down) for code in fam):
                    return False
        return True

    def all_keys_down_os(self) -> bool:
        return all(_is_vk_down_os(vk, None) for vk in self.vk_codes)


class AdaptiveHotkeyListener:
    """
    Multi-hotkey listener with WH_KEYBOARD_LL suppression, exclusive hook ownership,
    symmetrical KeyUp tracking, and magic-probe self-healing.
    """

    def __init__(
        self,
        key_name: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        strict_modifiers: bool = True,
        orphan_timeout_sec: float = DEFAULT_ORPHAN_TIMEOUT_SEC,
    ):
        self.strict_modifiers = strict_modifiers
        self.orphan_timeout_sec = orphan_timeout_sec
        self.on_press = on_press
        self.on_release = on_release

        raw_specs = [k.strip() for k in key_name.split(",") if k.strip()]
        valid_rules: List[_HotkeyRule] = []
        for spec in raw_specs:
            try:
                valid_rules.append(_HotkeyRule(spec))
            except ValueError as e:
                logger.warning(f"⚠️ Ignoring invalid hotkey '{spec}': {e}")

        if not valid_rules:
            logger.warning("⚠️ No valid hotkeys found; falling back to safe default 'F9'.")
            valid_rules = [_HotkeyRule("F9")]

        self.rules: List[_HotkeyRule] = valid_rules

        self._running = False
        self._state_lock = threading.Lock()
        self._event_queue: "queue.SimpleQueue[Optional[str]]" = queue.SimpleQueue()

        self._phys_down: Set[int] = set()
        self._suppressed_down: Set[int] = set()

        self._hook_handle: Optional[wintypes.HHOOK] = None
        self._hook_thread_id: int = 0
        self._hook_proc_ref: Optional[HOOKPROC] = None

        now = time.monotonic()
        self._last_probe_sent: float = now
        self._last_probe_ack: float = now
        self._last_reinstall_attempt: float = 0.0

        self._hook_thread: Optional[threading.Thread] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._hook_ready = threading.Event()

    @property
    def hook_alive(self) -> bool:
        return bool(self._hook_handle) and (
            self._hook_thread is not None and self._hook_thread.is_alive()
        )

    @property
    def all_vk_codes(self) -> Set[int]:
        out: Set[int] = set()
        for rule in self.rules:
            for vk in rule.vk_codes:
                out.update(MODIFIER_FAMILIES.get(vk, (vk,)))
        return out

    def is_any_phys_down(self, vks: Iterable[int]) -> bool:
        """Thread-safe query against _phys_down shadow set (R10)."""
        with self._state_lock:
            return any(vk in self._phys_down for vk in vks)

    def _any_other_rule_active(self, exclude_rule: _HotkeyRule) -> bool:
        return any(r.is_active for r in self.rules if r is not exclude_rule)

    def _worker_loop(self):
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
                logger.exception("❌ Unhandled exception in hotkey worker callback")

    def _low_level_proc(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0 and lParam:
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = int(kb.vkCode)

            # N1: Heartbeat probe MUST be intercepted FIRST before LLKHF_INJECTED filter!
            # Known side-effect if OS silently drops hook: neutral VK_NONAME (0xFC) KEYUP
            # reaches foreground app every 2.0s for <= 4.5s until _reinstall_hook() runs.
            if vk == VK_PROBE_NONAME and int(kb.dwExtraInfo) == HOOK_PROBE_MAGIC:
                self._last_probe_ack = time.monotonic()
                return 1

            if not (kb.flags & LLKHF_INJECTED):
                is_down_msg = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                is_up_msg = wParam in (WM_KEYUP, WM_SYSKEYUP)

                suppress = False
                with self._state_lock:
                    if is_down_msg:
                        self._phys_down.add(vk)
                    elif is_up_msg:
                        self._phys_down.discard(vk)

                    for rule in self.rules:
                        if rule.is_mouse:
                            continue

                        if is_down_msg and rule.matches_trigger(vk):
                            if rule.is_active:
                                suppress = True
                            elif rule.modifiers_satisfied(self.strict_modifiers, self._phys_down):
                                was_any_active = self._any_other_rule_active(rule)
                                rule.is_active = True
                                rule.activated_by_hook = True
                                rule.activated_time = time.monotonic()
                                suppress = True
                                if not was_any_active:
                                    self._event_queue.put_nowait("press")

                        elif is_up_msg and rule.is_active:
                            if rule.matches_trigger(vk):
                                rule.is_active = False
                                rule.activated_by_hook = False
                                suppress = True
                                if not self._any_other_rule_active(rule):
                                    self._event_queue.put_nowait("release")
                            elif rule.matches_modifier_release(vk):
                                rule.is_active = False
                                rule.activated_by_hook = False
                                if not self._any_other_rule_active(rule):
                                    self._event_queue.put_nowait("release")

                    # N2: Record into _suppressed_down ONLY if KeyDown was actually suppressed!
                    if is_down_msg and suppress:
                        self._suppressed_down.add(vk)
                    # A5 (HK-12): Symmetrical KeyUp suppression even if rule deactivated early
                    elif is_up_msg and vk in self._suppressed_down:
                        self._suppressed_down.discard(vk)
                        suppress = True

                if suppress:
                    return 1

        return user32.CallNextHookEx(self._hook_handle, nCode, wParam, lParam)

    def _hook_thread_main(self):
        self._hook_thread_id = int(kernel32.GetCurrentThreadId())
        self._hook_proc_ref = HOOKPROC(self._low_level_proc)
        hmod = kernel32.GetModuleHandleW(None)
        local_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc_ref, hmod, 0)
        self._hook_handle = local_hook
        if local_hook:
            self._last_probe_ack = time.monotonic()
        else:
            err = ctypes.get_last_error()
            logger.error(f"❌ SetWindowsHookExW(WH_KEYBOARD_LL) failed (WinError={err}). Key suppression unavailable.")
        self._hook_ready.set()

        if not local_hook:
            return

        try:
            msg = wintypes.MSG()
            while self._running:
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res <= 0:
                    break
        finally:
            # V21-03: Thread only unhooks its own local hook handle to prevent racing with _reinstall_hook()
            if local_hook:
                try:
                    user32.UnhookWindowsHookEx(local_hook)
                except Exception:
                    pass
                if self._hook_handle == local_hook:
                    self._hook_handle = None

    @staticmethod
    def _send_probe_input() -> bool:
        """Sends neutral VK_NONAME (0xFC) KEYUP tagged with HOOK_PROBE_MAGIC. Returns True if inserted."""
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.union.ki = KEYBDINPUT(
            wVk=VK_PROBE_NONAME,
            wScan=0,
            dwFlags=KEYEVENTF_KEYUP,
            time=0,
            dwExtraInfo=HOOK_PROBE_MAGIC,
        )
        sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        return bool(sent > 0)

    def _reinstall_hook(self) -> bool:
        """Cleanly tears down a dead/timed-out hook thread and installs a fresh WH_KEYBOARD_LL."""
        self._last_reinstall_attempt = time.monotonic()
        old_tid = self._hook_thread_id
        old_thread = self._hook_thread
        if old_tid:
            try:
                user32.PostThreadMessageW(old_tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        if old_thread and old_thread.is_alive():
            old_thread.join(timeout=0.2)
        if self._hook_handle:
            try:
                user32.UnhookWindowsHookEx(self._hook_handle)
            except Exception:
                pass
            self._hook_handle = None

        with self._state_lock:
            self._phys_down.clear()
            self._suppressed_down.clear()
            had_orphan = False
            for r in self.rules:
                if r.is_active and r.activated_by_hook:
                    r.is_active = False
                    r.activated_by_hook = False
                    had_orphan = True
            if had_orphan and not any(r.is_active for r in self.rules):
                self._event_queue.put_nowait("release")

        if not self._running:
            return False

        self._hook_ready.clear()
        now = time.monotonic()
        self._last_probe_sent = now
        self._last_probe_ack = now
        self._hook_thread = threading.Thread(target=self._hook_thread_main, name="VoiceHotkeyLLHook", daemon=True)
        self._hook_thread.start()
        self._hook_ready.wait(timeout=0.5)
        ok = bool(self._hook_handle)
        if ok:
            logger.warning("♻️ Self-healed: WH_KEYBOARD_LL hook successfully re-installed.")
        return ok

    def _watchdog_tick(self, now_mono: Optional[float] = None) -> None:
        """
        Single deterministic iteration of the companion watchdog (N3):
          • NEVER releases rules owned by WH_KEYBOARD_LL under normal operation (HK-11 / A1).
          • Reaps orphaned rules if desktop is locked (Secure Desktop / Win+L / UAC) or active duration exceeded (V21-01).
          • Handles mouse buttons and UIPI-elevated windows via GetAsyncKeyState.
          • Drives the 2.0s idle magic-probe health check when daemon is running (A2, V21-02, V21-05).
        """
        now = now_mono if now_mono is not None else time.monotonic()
        any_active = False

        # V21-01: Check desktop accessibility (Win+L / Secure Desktop / UAC)
        desktop_accessible = is_input_desktop_accessible()

        with self._state_lock:
            if not desktop_accessible:
                had_active = False
                for r in self.rules:
                    if r.is_active:
                        r.is_active = False
                        r.activated_by_hook = False
                        had_active = True
                self._phys_down.clear()
                self._suppressed_down.clear()
                if had_active:
                    logger.warning("🔒 Secure Desktop active (screen locked / UAC); reaped orphaned hotkey state (V21-01).")
                    self._event_queue.put_nowait("release")
                return

            for rule in self.rules:
                # V21-01: Orphan reaper if rule active longer than timeout (e.g. dropped KeyUp)
                if rule.is_active and rule.activated_by_hook:
                    if (now - rule.activated_time) > self.orphan_timeout_sec:
                        logger.warning(
                            f"⏰ Orphan reaper: rule '{rule.raw_spec}' active for >{self.orphan_timeout_sec:.1f}s without release; forced cleanup (V21-01)."
                        )
                        rule.is_active = False
                        rule.activated_by_hook = False
                        self._phys_down.clear()
                        self._suppressed_down.clear()
                        if not self._any_other_rule_active(rule):
                            self._event_queue.put_nowait("release")
                        continue
                    any_active = True
                    continue

                physically_down = rule.all_keys_down_os()
                if physically_down and not rule.is_active:
                    if not rule.is_mouse and self.strict_modifiers:
                        if not rule.modifiers_satisfied(True, None):
                            continue
                    was_any_active = self._any_other_rule_active(rule)
                    if rule.has_caps:
                        rule.caps_initial_state = user32.GetKeyState(0x14) & 1
                    rule.is_active = True
                    rule.activated_by_hook = False
                    rule.activated_time = now
                    any_active = True
                    if not was_any_active:
                        self._event_queue.put_nowait("press")

                elif not physically_down and rule.is_active and not rule.activated_by_hook:
                    rule.is_active = False
                    if rule.has_caps:
                        cur_caps = user32.GetKeyState(0x14) & 1
                        if cur_caps != rule.caps_initial_state:
                            user32.keybd_event(0x14, 0, 0, 0)
                            user32.keybd_event(0x14, 0, KEYEVENTF_KEYUP, 0)
                    if not self._any_other_rule_active(rule):
                        self._event_queue.put_nowait("release")

                if rule.is_active:
                    any_active = True

        # A2: Periodic idle heartbeat probe (only when listener is started)
        if self._running and not any_active:
            if not self.hook_alive or (now - self._last_probe_ack) > HOOK_PROBE_TIMEOUT_SEC:
                if (now - self._last_reinstall_attempt) >= HOOK_REINSTALL_BACKOFF_SEC:
                    logger.warning("⚠️ WH_KEYBOARD_LL hook unresponsive or dropped; attempting self-heal...")
                    self._reinstall_hook()
            elif (now - self._last_probe_sent) >= HOOK_PROBE_INTERVAL_SEC:
                self._last_probe_sent = now
                probe_sent = self._send_probe_input()
                if not probe_sent:
                    # V21-02: SendInput returned 0 (UIPI block or elevated window).
                    # Treat as ack to avoid false-positive hook reinstall storm.
                    self._last_probe_ack = now
                    logger.debug("⚠️ SendInput probe blocked (likely UIPI / elevated window); probe skipped.")

    def _watchdog_loop(self):
        while self._running:
            self._watchdog_tick()
            time.sleep(WATCHDOG_POLL_SEC)

    def start(self) -> bool:
        if self._running:
            return bool(self._hook_handle)
        self._running = True
        self._hook_ready.clear()
        now = time.monotonic()
        self._last_probe_sent = now
        self._last_probe_ack = now

        self._worker_thread = threading.Thread(target=self._worker_loop, name="VoiceHotkeyWorker", daemon=True)
        self._worker_thread.start()

        self._hook_thread = threading.Thread(target=self._hook_thread_main, name="VoiceHotkeyLLHook", daemon=True)
        self._hook_thread.start()
        self._hook_ready.wait(timeout=0.5)

        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, name="VoiceHotkeyWatchdog", daemon=True)
        self._watchdog_thread.start()
        return bool(self._hook_handle)

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
        with self._state_lock:
            self._phys_down.clear()
            self._suppressed_down.clear()
