# 📎 ملحق 06b: hotkey_listener.py (الأسطر 386–506)

`python
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
          • NEVER releases rules owned by WH_KEYBOARD_LL (HK-11 / A1).
          • Handles mouse buttons and UIPI-elevated windows via GetAsyncKeyState.
          • Drives the 2.0s idle magic-probe health check when daemon is running (A2).
        """
        now = now_mono if now_mono is not None else time.monotonic()
        any_active = False

        with self._state_lock:
            for rule in self.rules:
                # A1 (HK-11): Rules activated by WH_KEYBOARD_LL belong strictly to the hook!
                if rule.is_active and rule.activated_by_hook:
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
                if (now - self._last_probe_sent) >= HOOK_PROBE_INTERVAL_SEC:
                    logger.warning("⚠️ WH_KEYBOARD_LL hook unresponsive or dropped; attempting self-heal...")
                    self._reinstall_hook()
            elif (now - self._last_probe_sent) >= HOOK_PROBE_INTERVAL_SEC:
                self._last_probe_sent = now
                self._send_probe_input()

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
`
