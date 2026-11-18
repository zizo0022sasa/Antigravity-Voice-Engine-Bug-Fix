"""
Central Voice Engine Orchestrator — Antigravity Smart Voice Engine.

=============================================================================
🔒 IMMUTABLE ARCHITECTURAL & GOVERNANCE RULE (DO NOT VIOLATE):
  • AntigravityVoiceEngine is strictly a PURE-LOCAL Push-to-Talk Audio Recorder
    & Windows Shell Clipboard (CF_HDROP) File Drop Injector for Antigravity IDE.
  • NEVER integrate external Speech-to-Text (STT), Whisper, external Gemini APIs,
    Telegram relays, or third-party transcription services.
  • Antigravity IDE natively receives and processes the audio file directly.
=============================================================================
"""

import time
import logging
import threading
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

    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig.load()
        self.cues = AudioCues(self.config.audio_cues)
        self.recorder = AudioRecorder(
            save_dir=self.config.save_directory,
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
        self._active_window_at_start: str = ""
        self._guard_thread: Optional[threading.Thread] = None

    def _max_duration_guard_loop(self):
        """Auto-finishes recording if max_recording_duration_sec is reached in Toggle/Hold mode."""
        while self._is_running:
            if self.recorder.max_duration_reached:
                with self._lock:
                    if self.recorder.is_recording and self.recorder.max_duration_reached:
                        logger.info(
                            f"⏱️ Max recording duration ({self.config.max_recording_duration_sec}s) reached. Auto-saving..."
                        )
                        self._finish_recording()
            time.sleep(0.25)

    def start(self):
        """Initializes and starts the background hotkey listener and overlay."""
        logger.info(f"🚀 Initializing Voice Engine [Hotkey: {self.config.hotkey} | Mode: {self.config.mode}]")
        logger.info(f"📂 Audio Archive: {self.config.save_directory}")

        self._is_running = True
        self.listener = AdaptiveHotkeyListener(
            key_name=self.config.hotkey,
            on_press=self._handle_key_down,
            on_release=self._handle_key_up,
        )
        self.listener.start()
        self._guard_thread = threading.Thread(
            target=self._max_duration_guard_loop,
            name="VoiceMaxDurationGuard",
            daemon=True,
        )
        self._guard_thread.start()
        if self.config.overlay.enabled:
            self.overlay.init_ui()
        logger.info("🎙️ Voice Engine is ACTIVE and listening in the background!")

    def run_loop(self):
        """Runs the main event loop on the main thread."""
        if self.config.overlay.enabled and self.overlay._root is not None:
            self.overlay.run_mainloop()
        else:
            try:
                while self._is_running:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    def stop(self):
        """Stops the engine and background listeners."""
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
        """Called when hotkey is pressed down."""
        with self._lock:
            now = time.time()
            mode = self.config.mode

            if not self.recorder.is_recording:
                self._key_down_time = now
                self._is_toggle_latched = False
                self._active_hwnd_at_start = self.injector.get_foreground_hwnd()
                self._active_window_at_start = self.injector.get_window_title(self._active_hwnd_at_start)

                try:
                    self.recorder.start()
                    self.cues.play_start()
                    self.overlay.show_recording()
                    logger.info(f"🎙️ [RECORDING STARTED] Focus: '{self._active_window_at_start}'")
                except Exception as e:
                    logger.error(f"❌ Failed to start recording: {e}")
            else:
                if mode == "toggle" or self._is_toggle_latched:
                    self._finish_recording()

    def _handle_key_up(self):
        """Called when hotkey is released."""
        with self._lock:
            if not self.recorder.is_recording:
                return

            mode = self.config.mode
            press_duration = time.time() - self._key_down_time

            if mode == "hold":
                self._finish_recording()
            elif mode == "toggle":
                pass
            elif mode == "smart":
                if press_duration >= self.config.smart_hold_threshold_sec:
                    self._finish_recording()
                else:
                    self._is_toggle_latched = True
                    logger.info(f"🔄 Switched to Toggle Mode (tap {self.config.hotkey} again to finish)")

    def _finish_recording(self):
        """Stops recording, archives M4A/WAV, copies to clipboard, and simulates race-free paste."""
        duration = self.recorder.elapsed_duration
        saved_file = self.recorder.stop()
        self._is_toggle_latched = False

        if not saved_file:
            self.cues.play_cancel()
            self.overlay.hide()
            logger.info(f"⚠️ Recording discarded (< {self.config.min_recording_duration_sec}s or empty).")
            return

        self.cues.play_stop()
        logger.info(f"✅ [RECORDED] Duration: {duration:.2f}s | Saved: {saved_file}")

        if self.config.auto_paste:
            target_hwnd = self.injector.ensure_target_focus(
                fallback_hwnd=self._active_hwnd_at_start,
                ignored_hwnds=self.overlay.window_hwnds,
            )
            target_window = self.injector.get_window_title(target_hwnd)
            logger.info(f"📋 Injecting into active window: '{target_window}'")

            success = self.injector.set_clipboard_file(saved_file)
            if success:
                extra_vks = self.listener.all_vk_codes if self.listener else None
                self.injector.simulate_paste(
                    delay_ms=self.config.paste_delay_ms,
                    extra_release_vks=extra_vks,
                )
                self.overlay.show_success("⚡ تم اللصق!")
                logger.info("⚡ Auto-paste (Ctrl+V) executed successfully!")

                if self.config.auto_send_enter:
                    self.injector.simulate_enter(150)
                    logger.info("🚀 Auto-send (Enter) executed!")
            else:
                self.overlay.hide()
                logger.error("❌ Failed to set clipboard data.")
        else:
            self.overlay.show_success("✅ تم الحفظ!")

    def _cancel_recording(self):
        """Aborts recording without pasting."""
        self.recorder.stop()
        self._is_toggle_latched = False
        self.cues.play_cancel()
        self.overlay.hide()
        logger.info("❌ Recording cancelled.")
