# 📎 ملحق 06a: hotkey_listener.py (الأسطر 250–385)

`python
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
        self._hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc_ref, hmod, 0)
        if self._hook_handle:
            self._last_probe_ack = time.monotonic()
        else:
            err = ctypes.get_last_error()
            logger.error(f"❌ SetWindowsHookExW(WH_KEYBOARD_LL) failed (WinError={err}). Key suppression unavailable.")
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

    @staticmethod
    def _send_probe_input() -> None:
        """Sends neutral VK_NONAME (0xFC) KEYUP tagged with HOOK_PROBE_MAGIC."""
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.union.ki = KEYBDINPUT(
            wVk=VK_PROBE_NONAME,
            wScan=0,
            dwFlags=KEYEVENTF_KEYUP,
            time=0,
            dwExtraInfo=HOOK_PROBE_MAGIC,
        )
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _reinstall_hook(self) -> bool:
        """Cleanly tears down a dead/timed-out hook thread and installs a fresh WH_KEYBOARD_LL."""
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
`
