# 📎 ملحق 06d: ذيلا engine.py و config.py

## 1. engine.py (205–281)
`python
                logger.info(f"⚠️ Recording discarded (< {self.config.min_recording_duration_sec}s or empty).")
                return

            self.cues.play_stop()
            logger.info(f"✅ [RECORDED] Duration: {duration:.2f}s | Saved: {saved_file}")

            clip_ok = self.injector.set_clipboard_file(saved_file)
            if not clip_ok:
                self.overlay.show_success("💾 حُفظ على القرص")
                badge_shown = True
                logger.error("❌ Failed to place audio file onto clipboard.")
                return

            if not self.config.auto_paste:
                self.overlay.show_success("✅ تم الحفظ!")
                badge_shown = True
                return

            target_hwnd = self.injector.ensure_target_focus(
                fallback_hwnd=self._active_hwnd_at_start,
                ignored_hwnds=self.overlay.window_hwnds,
            )
            if not target_hwnd:
                # HK-03 / DEC-03: Secure Desktop (UAC / Win+L) or no foreground window
                self.overlay.show_success("💾 حُفظ (انسخ بـ Ctrl+V)")
                badge_shown = True
                logger.warning("⚠️ No active target window (UAC/Lock); skipped auto-paste. File ready in clipboard.")
                return

            target_exe = self.injector.get_window_exe_name(target_hwnd)
            if not self.injector.is_paste_allowed_for_process(
                exe_name=target_exe,
                blocked_processes=self.config.blocked_paste_processes,
                allowed_processes=self.config.allowed_paste_processes,
            ):
                # CB-01 / DEC-02: Blocked target (e.g. explorer.exe)
                self.overlay.show_success("💾 حُفظ في الحافظة!")
                badge_shown = True
                logger.info(f"🛡️ Skipped auto-paste into '{target_exe}' (blocked target). File ready in clipboard.")
                return

            logger.info(f"📋 Injecting into target: {self._describe_hwnd_for_log(target_hwnd)}")
            extra_vks = self.listener.all_vk_codes if self.listener else None
            phys_checker = self.listener.is_any_phys_down if self.listener else None

            pasted = self.injector.simulate_paste(
                delay_ms=self.config.paste_delay_ms,
                extra_release_vks=extra_vks,
                phys_down_checker=phys_checker,
            )
            if pasted:
                self.overlay.show_success("⚡ تم اللصق!")
                badge_shown = True
                logger.info("⚡ Auto-paste (Ctrl+V) delivered and verified.")
                if self.config.auto_send_enter:
                    if self.injector.simulate_enter(self.config.auto_send_enter_delay_ms):
                        logger.info("🚀 Auto-send (Enter) executed!")
            else:
                # EN-01: Honest failure reporting when UIPI or held modifiers block SendInput
                self.overlay.show_success("💾 حُفظ (الصق بـ Ctrl+V)")
                badge_shown = True
                logger.warning("⚠️ Auto-paste could not be delivered; audio is saved and ready in clipboard.")
        except Exception:
            logger.exception("❌ Unexpected error in _finish_recording")
        finally:
            if not badge_shown:
                self.overlay.hide()

    def _cancel_recording(self):
        try:
            self.recorder.stop()
        except Exception:
            logger.exception("Error stopping recorder on cancel")
        self._is_toggle_latched = False
        self.cues.play_cancel()
        self.overlay.hide()
        logger.info("❌ Recording cancelled.")
`

## 2. config.py (185–247)
`python
            smart_hold_threshold_sec=max(0.05, float(data.get("smart_hold_threshold_sec", defaults.smart_hold_threshold_sec))),
            min_recording_duration_sec=max(0.05, float(data.get("min_recording_duration_sec", defaults.min_recording_duration_sec))),
            max_recording_duration_sec=max(1.0, float(data.get("max_recording_duration_sec", defaults.max_recording_duration_sec))),
            sample_rate=sample_rate,
            channels=channels,
            audio_device_index=data.get("audio_device_index", defaults.audio_device_index),
            save_directory=str(data.get("save_directory", defaults.save_directory)),
            auto_paste=bool(data.get("auto_paste", defaults.auto_paste)),
            paste_delay_ms=max(0, int(data.get("paste_delay_ms", defaults.paste_delay_ms))),
            auto_send_enter=bool(data.get("auto_send_enter", defaults.auto_send_enter)),
            auto_send_enter_delay_ms=max(0, int(data.get("auto_send_enter_delay_ms", defaults.auto_send_enter_delay_ms))),
            blocked_paste_processes=[str(p) for p in blocked],
            allowed_paste_processes=[str(p) for p in allowed],
            log_window_titles=bool(data.get("log_window_titles", defaults.log_window_titles)),
            audio_cues=cues_cfg,
            overlay=overlay_cfg,
        )

    def save(self, config_path: str) -> None:
        data = {
            "hotkey": self.hotkey,
            "strict_modifiers": self.strict_modifiers,
            "mode": self.mode,
            "audio_format": self.audio_format,
            "bitrate": self.bitrate,
            "smart_hold_threshold_sec": self.smart_hold_threshold_sec,
            "min_recording_duration_sec": self.min_recording_duration_sec,
            "max_recording_duration_sec": self.max_recording_duration_sec,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "audio_device_index": self.audio_device_index,
            "save_directory": self.save_directory,
            "auto_paste": self.auto_paste,
            "paste_delay_ms": self.paste_delay_ms,
            "auto_send_enter": self.auto_send_enter,
            "auto_send_enter_delay_ms": self.auto_send_enter_delay_ms,
            "blocked_paste_processes": self.blocked_paste_processes,
            "allowed_paste_processes": self.allowed_paste_processes,
            "log_window_titles": self.log_window_titles,
            "audio_cues": {
                "enabled": self.audio_cues.enabled,
                "start_freq": self.audio_cues.start_freq,
                "start_duration_ms": self.audio_cues.start_duration_ms,
                "stop_freq": self.audio_cues.stop_freq,
                "stop_duration_ms": self.audio_cues.stop_duration_ms,
                "cancel_freq": self.audio_cues.cancel_freq,
                "cancel_duration_ms": self.audio_cues.cancel_duration_ms,
            },
            "overlay": {
                "enabled": self.overlay.enabled,
                "position": self.overlay.position,
                "offset_y": self.overlay.offset_y,
                "width": self.overlay.width,
                "height": self.overlay.height,
                "show_timer": self.overlay.show_timer,
                "show_waveform": self.overlay.show_waveform,
                "waveform_bars": self.overlay.waveform_bars,
                "theme": self.overlay.theme,
            },
        }
        os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
`
