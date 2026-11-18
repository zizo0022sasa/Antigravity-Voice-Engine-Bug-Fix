import ctypes
import os
import re
import sys
import time
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import EngineConfig, AudioCuesConfig, OverlayConfig
from cues import AudioCues
from clipboard_injector import ClipboardInjector, INPUT
from audio_recorder import AudioRecorder
from hotkey_listener import AdaptiveHotkeyListener
from overlay import VoiceOverlay, WS_EX_NOACTIVATE, WS_EX_TRANSPARENT, GWL_EXSTYLE
from engine import VoiceEngine


def test_config_load_and_defaults(tmp_path):
    config_file = str(tmp_path / "test_config.json")
    cfg = EngineConfig.load(config_file)
    assert "CTRL+CAPSLOCK" in cfg.hotkey
    assert "F9" in cfg.hotkey
    assert "F10" in cfg.hotkey
    assert cfg.mode == "smart"
    assert cfg.sample_rate == 44100
    assert cfg.channels == 1
    assert os.path.exists(cfg.save_directory)

    cfg.hotkey = "F8"
    cfg.auto_send_enter = True
    cfg.save(config_file)

    reloaded = EngineConfig.load(config_file)
    assert reloaded.hotkey == "F8"
    assert reloaded.auto_send_enter is True


def test_sendinput_struct_size_64bit():
    """Ensures Win32 INPUT structure matches 64-bit Windows ABI (40 bytes)."""
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(INPUT) == expected


def test_audio_cues_execution():
    cues = AudioCues(AudioCuesConfig(enabled=True, start_freq=1000, start_duration_ms=10))
    cues.play_start()
    cues.play_stop()
    cues.play_cancel()


def test_clipboard_set_file(tmp_path):
    test_file = tmp_path / "sample.wav"
    test_file.write_bytes(b"RIFFdummydataWAVEfmt ")
    success = ClipboardInjector.set_clipboard_file(str(test_file))
    assert success is True


def test_foreground_window_query_and_focus_guard():
    hwnd = ClipboardInjector.get_foreground_hwnd()
    assert isinstance(hwnd, int)
    title = ClipboardInjector.get_foreground_window_title()
    assert isinstance(title, str)
    resolved = ClipboardInjector.ensure_target_focus(fallback_hwnd=hwnd, ignored_hwnds=(999999999,))
    assert isinstance(resolved, int)


def test_recorder_rejects_sub_threshold(tmp_path):
    rec = AudioRecorder(
        save_dir=str(tmp_path),
        min_duration_sec=1.0,
    )
    rec.start()
    time.sleep(0.1)
    saved = rec.stop()
    assert saved is None


def test_recorder_chronological_filename_without_weekday_and_no_focus_steal(tmp_path):
    """
    Verifies:
      1. Filename strictly follows Voice_YYYY-MM-DD_HH-MM-SS.(m4a|wav) with NO weekday name.
      2. M4A ffmpeg compression executes with CREATE_NO_WINDOW without changing foreground HWND.
    """
    fg_before = ClipboardInjector.get_foreground_hwnd()
    rec = AudioRecorder(
        save_dir=str(tmp_path),
        sample_rate=44100,
        channels=1,
        min_duration_sec=0.2,
        audio_format="m4a",
    )
    rec.start()
    time.sleep(0.35)
    saved_path = rec.stop()
    fg_after = ClipboardInjector.get_foreground_hwnd()

    assert saved_path is not None
    assert os.path.exists(saved_path)
    assert os.path.getsize(saved_path) > 0

    basename = os.path.basename(saved_path)
    # Must match Voice_2026-11-18_08-10-03.m4a (or .wav) — ZERO weekday words!
    assert re.match(r"^Voice_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:_\d+)?\.(m4a|wav)$", basename), (
        f"Unexpected filename format: {basename}"
    )
    for weekday in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
        assert weekday not in basename

    # Foreground window must NOT have been hijacked by ffmpeg console
    if fg_before != 0:
        assert fg_after == fg_before
    # PCM buffer in RAM must be released immediately after stop()
    assert rec._frames == []


def test_recorder_enforces_max_duration_cap(tmp_path):
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


def test_hotkey_listener_lifecycle():
    pressed = []
    released = []
    listener = AdaptiveHotkeyListener(
        key_name="CTRL+CAPSLOCK, F9, F10",
        on_press=lambda: pressed.append(1),
        on_release=lambda: released.append(1),
    )
    assert 0x78 in listener.all_vk_codes  # F9
    assert 0x79 in listener.all_vk_codes  # F10
    assert 0x14 in listener.all_vk_codes  # CAPSLOCK
    listener.start()
    time.sleep(0.08)
    listener.stop()


def test_engine_workflow_mock(tmp_path):
    cfg = EngineConfig(
        hotkey="F9",
        mode="smart",
        save_directory=str(tmp_path),
        min_recording_duration_sec=0.2,
        auto_paste=False,
        audio_cues=AudioCuesConfig(enabled=False),
    )
    engine = VoiceEngine(cfg)
    engine._handle_key_down()
    assert engine.recorder.is_recording is True
    time.sleep(0.5)
    engine._handle_key_up()
    assert engine.recorder.is_recording is False


def test_engine_toggle_mode_workflow(tmp_path):
    cfg = EngineConfig(
        hotkey="F9",
        mode="toggle",
        save_directory=str(tmp_path),
        min_recording_duration_sec=0.2,
        auto_paste=False,
        audio_cues=AudioCuesConfig(enabled=False),
    )
    engine = VoiceEngine(cfg)
    engine._handle_key_down()
    assert engine.recorder.is_recording is True
    engine._handle_key_up()
    assert engine.recorder.is_recording is True
    time.sleep(0.25)
    engine._handle_key_down()
    assert engine.recorder.is_recording is False


def test_engine_smart_mode_tap_latches_toggle(tmp_path):
    cfg = EngineConfig(
        hotkey="F9",
        mode="smart",
        smart_hold_threshold_sec=0.4,
        save_directory=str(tmp_path),
        min_recording_duration_sec=0.2,
        auto_paste=False,
        audio_cues=AudioCuesConfig(enabled=False),
    )
    engine = VoiceEngine(cfg)
    engine._handle_key_down()
    time.sleep(0.05)
    engine._handle_key_up()
    assert engine.recorder.is_recording is True
    assert engine._is_toggle_latched is True
    time.sleep(0.25)
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


def test_voice_overlay_lifecycle_and_toplevel_styles():
    overlay = VoiceOverlay(
        enabled=True,
        position="bottom_center",
        offset_y=50,
        waveform_bars=7,
        level_source=lambda: 0.75,
        duration_source=lambda: 3.5,
    )
    overlay.init_ui()
    assert overlay._root is not None
    assert overlay._top_hwnd is not None and overlay._top_hwnd != 0

    ex_style = ctypes.windll.user32.GetWindowLongW(overlay._top_hwnd, GWL_EXSTYLE)
    assert bool(ex_style & WS_EX_NOACTIVATE)
    assert bool(ex_style & WS_EX_TRANSPARENT)

    overlay.show_recording()
    overlay._root.update()
    assert overlay._state == "RECORDING"

    overlay.show_success("⚡ تم اللصق!")
    overlay._root.update()
    assert overlay._state == "SUCCESS"

    overlay.hide()
    overlay._root.update()
    assert overlay._state == "IDLE"

    overlay.stop()
    assert overlay._root is None
