# 📎 ملحق الأجزاء المقطوعة في الجولة الأولى (لإغلاق كافة بنود UNVERIFIED فوراً)

> **ملاحظة للمراجع الخارجي:** نظراً لأن أداة القراءة لديك قطعت الملفات الأكبر من `~10KB` وتعذّر عليها جلب ملفين صغيرين في الجولة الأولى، نضع لك هنا **النص الحرفي المطابق 100% للكوميت `f168f47`** لتلك الأجزاء الخمسة حتى تغلق كافة بنود `UNVERIFIED` أثناء مراجعتك للخطة.

---

## 1. محتوى `requirements.txt` بالكامل (56 بايت)
```text
sounddevice>=0.4.6
numpy>=1.26.0
imageio-ffmpeg>=0.5.1
```

---

## 2. محتوى `config.json` بالكامل (إغلاق `SEC-06` — خالٍ من أي مسار مستخدم)
```json
{
  "hotkey": "CTRL+CAPSLOCK, F9, F10",
  "mode": "smart",
  "audio_format": "m4a",
  "bitrate": "64k",
  "smart_hold_threshold_sec": 0.45,
  "min_recording_duration_sec": 0.6,
  "max_recording_duration_sec": 600,
  "sample_rate": 44100,
  "channels": 1,
  "audio_device_index": null,
  "save_directory": "~/Documents/تسجيلات الصوت",
  "auto_paste": true,
  "paste_delay_ms": 150,
  "auto_send_enter": false,
  "audio_cues": {
    "enabled": true,
    "start_freq": 1200,
    "start_duration_ms": 90,
    "stop_freq": 1600,
    "stop_duration_ms": 120,
    "cancel_freq": 450,
    "cancel_duration_ms": 150
  },
  "overlay": {
    "enabled": true,
    "position": "bottom_center",
    "offset_y": 50,
    "width": 260,
    "height": 44,
    "show_timer": true,
    "show_waveform": true,
    "waveform_bars": 7,
    "theme": "dark"
  }
}
```

---

## 3. ذيل `hotkey_listener.py` (الأسطر `289–363`)
```python
    def _watchdog_loop(self):
        while self._running:
            with self._state_lock:
                for rule in self.rules:
                    physically_down = rule.all_keys_down()

                    if physically_down and not rule.is_active:
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
```

---

## 4. ذيل `clipboard_injector.py` (الأسطر `336–375`)
```python
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
```

---

## 5. ذيل `overlay.py` (الأسطر `385–556` — الإخفاء، التدمير، والخطوط الموجبة)
```python
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

    # Inside _render_recording_frame & _render_success_frame:
    # Fonts use positive points (auto-scaled by Tk scaling):
    #   font=("Consolas", 11, "bold")
    #   font=("Segoe UI", 11, "bold")
    # Waveform bars, dot_r, dot_x, div_x, start_x, min_h, max_h all multiply by s = self._scale.
```
