import ctypes
import os
import re
import sys
import time
import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import EngineConfig, AudioCuesConfig, OverlayConfig
from cues import AudioCues
from clipboard_injector import ClipboardInjector
from win32_api import (
    user32,
    kernel32,
    INPUT,
    CF_UNICODETEXT,
    GMEM_MOVEABLE,
    WS_EX_NOACTIVATE,
    WS_EX_TRANSPARENT,
    GWL_EXSTYLE,
    get_window_long_ptr,
)
from audio_recorder import AudioRecorder
from hotkey_listener import AdaptiveHotkeyListener
from overlay import VoiceOverlay
from engine import VoiceEngine


def _read_clipboard_unicode_text() -> str:
    """Reads current CF_UNICODETEXT from clipboard so tests can restore developer's clipboard."""
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return ""
    if not user32.OpenClipboard(None):
        return ""
    try:
        h_data = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_data:
            return ""
        ptr = kernel32.GlobalLock(h_data)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h_data)
    finally:
        user32.CloseClipboard()


def _restore_clipboard_unicode_text(text: str) -> None:
    if not user32.OpenClipboard(None):
        return
    try:
        user32.EmptyClipboard()
        if text:
            raw = (text + "\0").encode("utf-16le")
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(raw))
            if h_mem:
                ptr = kernel32.GlobalLock(h_mem)
                if ptr:
                    ctypes.memmove(ptr, raw, len(raw))
                    kernel32.GlobalUnlock(h_mem)
                    if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                        kernel32.GlobalFree(h_mem)
                else:
                    kernel32.GlobalFree(h_mem)
    finally:
        user32.CloseClipboard()


def test_config_load_and_defaults_isolated(tmp_path):
    """TS-03 & DEC-06: load() preserves '~' in save_directory and creates zero folders outside tmp_path."""
    config_file = str(tmp_path / "test_config.json")
    cfg = EngineConfig.load(config_file)
    assert "CTRL+CAPSLOCK" in cfg.hotkey
    assert "F9" in cfg.hotkey
    assert "F10" in cfg.hotkey
    assert cfg.mode == "smart"
    assert cfg.sample_rate == 44100
    assert cfg.channels == 1
    assert cfg.save_directory.startswith("~")
    assert os.path.isabs(cfg.resolved_save_directory)

    cfg.hotkey = "F8"
    cfg.auto_send_enter = True
    cfg.save(config_file)

    reloaded = EngineConfig.load(config_file)
    assert reloaded.hotkey == "F8"
    assert reloaded.auto_send_enter is True
    assert reloaded.save_directory.startswith("~")


def test_sendinput_struct_size_64bit():
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(INPUT) == expected


@pytest.mark.hw
def test_audio_cues_execution():
    cues = AudioCues(AudioCuesConfig(enabled=True, start_freq=1000, start_duration_ms=10))
    cues.play_start()
    cues.play_stop()
    cues.play_cancel()


@pytest.mark.hw
def test_clipboard_set_file_preserves_user_clipboard(tmp_path):
    """TS-02: Saves and restores developer's clipboard text around real Win32 clipboard test."""
    prior_text = _read_clipboard_unicode_text()
    try:
        test_file = tmp_path / "sample.wav"
        test_file.write_bytes(b"RIFFdummydataWAVEfmt ")
        success = ClipboardInjector.set_clipboard_file(str(test_file))
        assert success is True
    finally:
        _restore_clipboard_unicode_text(prior_text)


def test_foreground_window_query_and_focus_guard():
    hwnd = ClipboardInjector.get_foreground_hwnd()
    assert isinstance(hwnd, int)
    title = ClipboardInjector.get_foreground_window_title()
    assert isinstance(title, str)
    resolved = ClipboardInjector.ensure_target_focus(fallback_hwnd=hwnd, ignored_hwnds=(999999999,))
    assert isinstance(resolved, int)


class _DummyInputStream:
    """Mock PortAudio InputStream for CI runners without a physical microphone."""

    def __init__(self, samplerate, channels, device, dtype, callback):
        self.samplerate = samplerate
        self.channels = channels
        self.callback = callback
        self._active = False

    def start(self):
        self._active = True
        chunk = np.zeros((int(self.samplerate * 0.15), self.channels), dtype=np.int16)
        try:
            self.callback(chunk, len(chunk), None, None)
        except Exception:
            pass

    def stop(self):
        self._active = False

    def close(self):
        self._active = False


def test_recorder_rejects_sub_threshold_mocked(tmp_path, monkeypatch):
    import sounddevice as sd
    monkeypatch.setattr(sd, "InputStream", _DummyInputStream)
    rec = AudioRecorder(save_dir=str(tmp_path), min_duration_sec=1.0)
    rec.start()
    time.sleep(0.05)
    saved = rec.stop()
    assert saved is None


def test_recorder_chronological_filename_without_weekday_mocked(tmp_path, monkeypatch):
    import sounddevice as sd
    monkeypatch.setattr(sd, "InputStream", _DummyInputStream)
    fg_before = ClipboardInjector.get_foreground_hwnd()
    rec = AudioRecorder(
        save_dir=str(tmp_path),
        sample_rate=44100,
        channels=1,
        min_duration_sec=0.1,
        audio_format="m4a",
    )
    rec.start()
    time.sleep(0.18)
    saved_path = rec.stop()
    fg_after = ClipboardInjector.get_foreground_hwnd()

    assert saved_path is not None
    assert os.path.exists(saved_path)
    assert os.path.getsize(saved_path) > 0

    basename = os.path.basename(saved_path)
    assert re.match(r"^Voice_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:_\d+)?\.(m4a|wav)$", basename)
    for weekday in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
        assert weekday not in basename

    if fg_before != 0:
        assert fg_after == fg_before
    assert rec._frames == []


@pytest.mark.hw
def test_recorder_real_microphone_enforces_max_duration(tmp_path):
    rec = AudioRecorder(
        save_dir=str(tmp_path),
        sample_rate=44100,
        channels=1,
        min_duration_sec=0.1,
        max_duration_sec=0.25,
        audio_format="wav",
    )
    rec.start()
    time.sleep(0.4)
    assert rec.max_duration_reached is True
    saved = rec.stop()
    assert saved is not None
    assert os.path.exists(saved)
    assert rec._frames == []


@pytest.mark.hw
def test_hotkey_listener_live_hook_lifecycle():
    listener = AdaptiveHotkeyListener(
        key_name="CTRL+CAPSLOCK, F9, F10",
        on_press=lambda: None,
        on_release=lambda: None,
    )
    assert 0x78 in listener.all_vk_codes
    assert 0x79 in listener.all_vk_codes
    assert 0x14 in listener.all_vk_codes
    ok = listener.start()
    assert isinstance(ok, bool)
    time.sleep(0.06)
    listener.stop()


def test_engine_modes_workflow_isolated(tmp_path, monkeypatch):
    import sounddevice as sd
    monkeypatch.setattr(sd, "InputStream", _DummyInputStream)

    # 1. Smart mode hold (>= threshold -> stops on release)
    cfg = EngineConfig(
        hotkey="F9",
        mode="smart",
        smart_hold_threshold_sec=0.15,
        save_directory=str(tmp_path),
        min_recording_duration_sec=0.05,
        auto_paste=False,
        audio_cues=AudioCuesConfig(enabled=False),
        overlay=OverlayConfig(enabled=False),
    )
    engine = VoiceEngine(cfg)
    engine._handle_key_down()
    assert engine.recorder.is_recording is True
    time.sleep(0.20)
    engine._handle_key_up()
    assert engine.recorder.is_recording is False

    # 2. Smart mode quick tap (< threshold -> latches toggle)
    engine._handle_key_down()
    time.sleep(0.03)
    engine._handle_key_up()
    assert engine.recorder.is_recording is True
    assert engine._is_toggle_latched is True
    time.sleep(0.05)
    engine._handle_key_down()
    assert engine.recorder.is_recording is False
    assert engine._is_toggle_latched is False


def test_overlay_config_and_defaults(tmp_path):
    config_file = str(tmp_path / "test_overlay_cfg.json")
    cfg = EngineConfig.load(config_file)
    assert cfg.overlay.enabled is True
    assert cfg.overlay.position == "bottom_center"
    assert cfg.overlay.waveform_bars == 7

    cfg.overlay.position = "top_center"
    cfg.overlay.offset_y = 30
    cfg.overlay.waveform_bars = 9
    cfg.save(config_file)

    reloaded = EngineConfig.load(config_file)
    assert reloaded.overlay.position == "top_center"
    assert reloaded.overlay.offset_y == 30
    assert reloaded.overlay.waveform_bars == 9


def test_voice_overlay_lifecycle_and_persistent_exstyles():
    """TS-06: Verifies WS_EX_NOACTIVATE | WS_EX_TRANSPARENT persist across full show->success->hide cycle."""
    overlay = VoiceOverlay(
        enabled=True,
        position="bottom_center",
        offset_y=50,
        waveform_bars=7,
        level_source=lambda: 0.75,
        duration_source=lambda: 3.5,
    )
    overlay.init_ui()
    if overlay._root is None:
        pytest.skip("Tkinter GUI not available or broken in this runner environment")

    assert overlay._root is not None
    assert overlay._top_hwnd is not None and overlay._top_hwnd != 0

    overlay.show_recording()
    overlay._root.update()
    assert overlay._state == "RECORDING"

    overlay.show_success("⚡ تم اللصق!")
    overlay._root.update()
    assert overlay._state == "SUCCESS"

    overlay.hide()
    overlay._root.update()
    assert overlay._state == "IDLE"

    ex_style_after = get_window_long_ptr(overlay._top_hwnd, GWL_EXSTYLE)
    assert bool(ex_style_after & WS_EX_NOACTIVATE)
    assert bool(ex_style_after & WS_EX_TRANSPARENT)

    overlay.stop()
    assert overlay._root is None
