"""
Central Voice Engine Orchestrator — Antigravity Smart Voice Engine.

=============================================================================
🔒 IMMUTABLE ARCHITECTURAL & GOVERNANCE RULE (DO NOT VIOLATE):
  • AntigravityVoiceEngine is strictly a PURE-LOCAL Push-to-Talk Audio Recorder
    & Windows Shell Clipboard (CF_HDROP) File Drop Injector.
  • NEVER integrate external Speech-to-Text (STT), Whisper, external Gemini APIs,
    Telegram relays, or network calls.
=============================================================================
"""

import logging
import threading
import time
from typing import Optional

from config import EngineConfig
from cues import AudioCues
from audio_recorder import AudioRecorder
from clipboard_injector import ClipboardInjector
from hotkey_listener import AdaptiveHotkeyListener
from overlay import VoiceOverlay

logger = logging.getLogger("VoiceEngine")


class VoiceEngine:
    """Central orchestrator for the Antigravity Voice Push-to-Talk & File-Drop Engine."""

    def __init__(
        self,
        config: Optional[EngineConfig] = None,
        shutdown_event_handle: Optional[int] = None,
    ):
        self.config = config or EngineConfig.load()
        self._shutdown_event_handle = shutdown_event_handle
        self.cues = AudioCues(self.config.audio_cues)
        self.recorder = AudioRecorder(
            save_dir=self.config.resolved_save_directory,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            device_index=self.config.audio_device_index,
            min_duration_sec=self.config.min_recording_duration_sec,
            max_duration_sec=self.config.max_recording_duration_sec,
            audio_format=self.config.audio_format,
            bitrate=self.config.bitrate,
        )
        self.injector = ClipboardInjector()
        self.listener: Optional[AdaptiveHotkeyListener] = None
        self.overlay = VoiceOverlay(
            enabled=self.config.overlay.enabled,
            position=self.config.overlay.position,
            offset_y=self.config.overlay.offset_y,
            width=self.config.overlay.width,
            height=self.config.overlay.height,
            show_timer=self.config.overlay.show_timer,
            show_waveform=self.config.overlay.show_waveform,
            waveform_bars=self.config.overlay.waveform_bars,
            theme=self.config.overlay.theme,
            level_source=lambda: self.recorder.current_level,
            duration_source=lambda: self.recorder.elapsed_duration,
        )

        self._lock = threading.Lock()
        self._is_running: bool = False
        self._key_down_time: float = 0.0
        self._is_toggle_latched: bool = False
        self._active_hwnd_at_start: int = 0
        self._guard_thread: Optional[threading.Thread] = None

    def _describe_hwnd_for_log(self, hwnd: int) -> str:
        """Privacy-aware window description: exe name by default, title only if opted-in (SEC-01)."""
        if not hwnd:
            return "<none>"
        exe = self.injector.get_window_exe_name(hwnd) or "unknown.exe"
        if self.config.log_window_titles:
            title = self.injector.get_window_title(hwnd)[:60]
            return f"{exe} ({title})" if title else exe
        return exe

    def _max_duration_and_shutdown_guard_loop(self):
        """Monitors max_recording_duration_sec cap and optional Win32 named shutdown event."""
        from win32_api import kernel32, WAIT_OBJECT_0

        while self._is_running:
            if self._shutdown_event_handle:
                if kernel32.WaitForSingleObject(self._shutdown_event_handle, 0) == WAIT_OBJECT_0:
                    logger.info("🛑 Shutdown signal received via Win32 event. Stopping gracefully...")
                    self.stop()
                    return

            if self.recorder.max_duration_reached:
                with self._lock:
                    if self.recorder.is_recording and self.recorder.max_duration_reached:
                        logger.info(
                            f"⏱️ Max recording duration ({self.config.max_recording_duration_sec}s) reached. Auto-saving..."
                        )
                        self._finish_recording()
            time.sleep(0.20)

    def start(self):
        """Initializes UI overlay FIRST (OV-02), then starts background hotkey listener."""
        logger.info(f"🚀 Initializing Voice Engine [Hotkey: {self.config.hotkey} | Mode: {self.config.mode}]")
        logger.info(f"📂 Audio Archive: {self.config.resolved_save_directory}")

        self._is_running = True
        if self.config.overlay.enabled:
            self.overlay.init_ui()

        self.listener = AdaptiveHotkeyListener(
            key_name=self.config.hotkey,
            on_press=self._handle_key_down,
            on_release=self._handle_key_up,
            strict_modifiers=self.config.strict_modifiers,
        )
        hook_ok = self.listener.start()

        self._guard_thread = threading.Thread(
            target=self._max_duration_and_shutdown_guard_loop,
            name="VoiceEngineGuard",
            daemon=True,
        )
        self._guard_thread.start()

        if hook_ok:
            logger.info("🎙️ Voice Engine is ACTIVE (WH_KEYBOARD_LL suppression enabled).")
        else:
            logger.warning("⚠️ Voice Engine started in fallback polling mode (key suppression unavailable).")

    def run_loop(self):
        if self.config.overlay.enabled and self.overlay._root is not None:
            self.overlay.run_mainloop()
        else:
            try:
                while self._is_running:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass

    def stop(self):
        if not self._is_running and self.listener is None:
            return
        self._is_running = False
        with self._lock:
            if self.recorder.is_recording:
                self._cancel_recording()
        if self.listener:
            self.listener.stop()
            self.listener = None
        self.overlay.stop()
        logger.info("🛑 Voice Engine stopped.")

    def _handle_key_down(self):
        with self._lock:
            now = time.monotonic()
            mode = self.config.mode

            if not self.recorder.is_recording:
                self._key_down_time = now
                self._is_toggle_latched = False
                self._active_hwnd_at_start = self.injector.get_foreground_hwnd()

                try:
                    self.recorder.start()
                    self.cues.play_start()
                    self.overlay.show_recording()
                    logger.info(f"🎙️ [RECORDING STARTED] Target: {self._describe_hwnd_for_log(self._active_hwnd_at_start)}")
                except Exception as e:
                    self.overlay.hide()
                    logger.error(f"❌ Failed to start recording: {e}")
            else:
                if mode == "toggle" or self._is_toggle_latched:
                    self._finish_recording()

    def _handle_key_up(self):
        with self._lock:
            if not self.recorder.is_recording:
                return

            mode = self.config.mode
            press_duration = time.monotonic() - self._key_down_time

            if mode == "hold":
                self._finish_recording()
            elif mode == "toggle":
                pass
            else:  # "smart"
                if press_duration >= self.config.smart_hold_threshold_sec:
                    self._finish_recording()
                else:
                    self._is_toggle_latched = True
                    logger.info(f"🔄 Switched to Toggle Mode (tap {self.config.hotkey} again to finish)")

    def _finish_recording(self):
        """Stops recording, archives M4A/WAV, sets clipboard, and performs honest verified paste."""
        self._is_toggle_latched = False
        badge_shown = False
        try:
            duration = self.recorder.elapsed_duration
            saved_file = self.recorder.stop()

            if not saved_file:
                self.cues.play_cancel()
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
