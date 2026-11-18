"""
Phase P1 & Security/Reliability Unit Tests (100% Hardware-Free, CI-Ready).

Covers:
  - CB-01 / DEC-02 / R5: explorer.exe blocked, Antigravity IDE.exe allowed, '' fail-open.
  - AR-01: Corrupt/partial M4A deleted on non-zero ffmpeg exit or TimeoutExpired; WAV returned.
  - HK-01 / HK-07 / A2: Self-healing hook reinstalls when probe ack times out (> 4.5s).
  - HK-04: Unexpected exception inside _finish_recording still hides overlay cleanly.
  - SEC-03: _low_level_proc never logs non-matching user keystrokes (zero keylogger risk).
"""

import ctypes
import logging
import os
import subprocess
import sys
import time
import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import audio_recorder as ar_mod
import clipboard_injector as cb_mod
import config as cfg_mod
import engine as eng_mod
import hotkey_listener as hk_mod


def test_cb01_r5_process_paste_policy():
    """CB-01 + DEC-02 + R5: Blocks explorer.exe, allows normal apps, fails open on ''."""
    blocked = ["explorer.exe", "SearchHost.exe"]

    assert cb_mod.ClipboardInjector.is_paste_allowed_for_process("explorer.exe", blocked, []) is False
    assert cb_mod.ClipboardInjector.is_paste_allowed_for_process("EXPLORER.EXE", blocked, []) is False
    assert cb_mod.ClipboardInjector.is_paste_allowed_for_process("Antigravity IDE.exe", blocked, []) is True
    assert cb_mod.ClipboardInjector.is_paste_allowed_for_process("chrome.exe", blocked, []) is True
    # R5: Fail-open when OS denies QueryFullProcessImageNameW (returns '')
    assert cb_mod.ClipboardInjector.is_paste_allowed_for_process("", blocked, []) is True

    # Explicit allowlist mode
    allow_only = ["Antigravity IDE.exe"]
    assert cb_mod.ClipboardInjector.is_paste_allowed_for_process("Antigravity IDE.exe", blocked, allow_only) is True
    assert cb_mod.ClipboardInjector.is_paste_allowed_for_process("chrome.exe", blocked, allow_only) is False
    assert cb_mod.ClipboardInjector.is_paste_allowed_for_process("", blocked, allow_only) is False


def test_cb01_engine_skips_paste_into_explorer(tmp_path, monkeypatch):
    dummy_audio = tmp_path / "Voice_2026-11-18_10-00-00.m4a"
    dummy_audio.write_bytes(b"M4ADATA")

    cfg = cfg_mod.EngineConfig(
        hotkey="F9",
        save_directory=str(tmp_path),
        auto_paste=True,
        audio_cues=cfg_mod.AudioCuesConfig(enabled=False),
        overlay=cfg_mod.OverlayConfig(enabled=False),
    )
    engine = eng_mod.VoiceEngine(cfg)
    monkeypatch.setattr(engine.recorder, "stop", lambda: str(dummy_audio))
    monkeypatch.setattr(engine.injector, "set_clipboard_file", lambda p: True)
    monkeypatch.setattr(engine.injector, "ensure_target_focus", lambda **kw: 999)
    monkeypatch.setattr(engine.injector, "get_window_exe_name", lambda h: "explorer.exe")

    paste_called = []
    monkeypatch.setattr(engine.injector, "simulate_paste", lambda *a, **kw: paste_called.append(1) or True)
    badges = []
    monkeypatch.setattr(engine.overlay, "show_success", lambda t="": badges.append(t))

    engine._finish_recording()
    assert paste_called == []
    assert len(badges) == 1
    assert "الحافظة" in badges[0]


def test_ar01_partial_m4a_cleaned_up_on_ffmpeg_failure_and_timeout(tmp_path, monkeypatch):
    """AR-01: Orphan partial .m4a is deleted on non-zero returncode or TimeoutExpired, returning valid .wav."""

    class _MockStream:
        def __init__(self, samplerate, channels, device, dtype, callback):
            self.cb = callback
            self.sr = samplerate
            self.ch = channels

        def start(self):
            self.cb(np.ones((int(self.sr * 0.2), self.ch), dtype=np.int16), int(self.sr * 0.2), None, None)

        def stop(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(ar_mod.sd, "InputStream", _MockStream)
    monkeypatch.setattr(ar_mod.AudioRecorder, "_get_ffmpeg_path", lambda self: "fake_ffmpeg.exe")

    # Case 1: ffmpeg writes corrupt partial m4a then exits with code 1
    def _failing_run(cmd, **kwargs):
        m4a_out = cmd[-1]
        with open(m4a_out, "wb") as f:
            f.write(b"PARTIAL_CORRUPT_M4A")
        return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"Simulated codec failure")

    monkeypatch.setattr(ar_mod.subprocess, "run", _failing_run)
    rec = ar_mod.AudioRecorder(save_dir=str(tmp_path), min_duration_sec=0.05, audio_format="m4a")
    rec.start()
    time.sleep(0.08)
    out1 = rec.stop()
    assert out1 is not None and out1.endswith(".wav")
    assert os.path.exists(out1)
    assert list(tmp_path.glob("*.m4a")) == []  # Corrupt partial M4A was deleted!

    # Case 2: ffmpeg times out after writing partial m4a
    def _timeout_run(cmd, **kwargs):
        m4a_out = cmd[-1]
        with open(m4a_out, "wb") as f:
            f.write(b"PARTIAL_TIMEOUT_M4A")
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

    monkeypatch.setattr(ar_mod.subprocess, "run", _timeout_run)
    rec.start()
    time.sleep(0.08)
    out2 = rec.stop()
    assert out2 is not None and out2.endswith(".wav")
    assert list(tmp_path.glob("*.m4a")) == []


def test_hk01_a2_self_healing_reinstalls_hook_when_probe_stalls(monkeypatch):
    """HK-01 + HK-07 + A2: _watchdog_tick triggers _reinstall_hook when probe ack expires (> 4.5s)."""
    listener = hk_mod.AdaptiveHotkeyListener("F9", on_press=lambda: None, on_release=lambda: None)
    monkeypatch.setattr(hk_mod.user32, "GetAsyncKeyState", lambda vk: 0)

    reinstall_calls = []
    monkeypatch.setattr(listener, "_reinstall_hook", lambda: reinstall_calls.append(1) or True)

    listener._running = True
    t0 = 1000.0
    listener._last_probe_ack = t0
    listener._last_probe_sent = t0

    # Advance 5.0s (> HOOK_PROBE_TIMEOUT_SEC = 4.5s) while idle -> triggers self-heal!
    listener._watchdog_tick(now_mono=t0 + 5.0)
    listener._running = False
    assert len(reinstall_calls) == 1


def test_hk04_finish_recording_exception_always_hides_overlay(tmp_path, monkeypatch):
    """HK-04: Even if recorder.stop() throws an unexpected error, overlay.hide() runs in finally."""
    cfg = cfg_mod.EngineConfig(
        hotkey="F9",
        save_directory=str(tmp_path),
        audio_cues=cfg_mod.AudioCuesConfig(enabled=False),
        overlay=cfg_mod.OverlayConfig(enabled=False),
    )
    engine = eng_mod.VoiceEngine(cfg)

    def _boom():
        raise OSError("Simulated disk I/O crash")

    monkeypatch.setattr(engine.recorder, "stop", _boom)
    hide_calls = []
    monkeypatch.setattr(engine.overlay, "hide", lambda: hide_calls.append(1))

    engine._finish_recording()
    assert len(hide_calls) == 1


def test_sec03_hook_callback_never_logs_ordinary_keystrokes(monkeypatch, caplog):
    """SEC-03: Typing ordinary letters/digits/passwords NEVER invokes logging inside _low_level_proc."""
    listener = hk_mod.AdaptiveHotkeyListener("F9", on_press=lambda: None, on_release=lambda: None)
    monkeypatch.setattr(hk_mod.user32, "CallNextHookEx", lambda h, n, w, l: 0)
    monkeypatch.setattr(hk_mod.user32, "GetAsyncKeyState", lambda vk: 0)

    with caplog.at_level(logging.DEBUG):
        for vk in (0x41, 0x42, 0x31, 0x0D, 0x20):  # A, B, 1, Enter, Space
            kb = hk_mod.KBDLLHOOKSTRUCT(vkCode=vk, scanCode=0, flags=0, time=100, dwExtraInfo=0)
            listener._low_level_proc(0, hk_mod.WM_KEYDOWN, ctypes.addressof(kb))
            listener._low_level_proc(0, hk_mod.WM_KEYUP, ctypes.addressof(kb))

    assert caplog.records == []


def test_v21_01_desktop_lock_reaps_orphaned_hook_rules(monkeypatch):
    """V21-01: When input desktop is locked (Win+L / Secure Desktop / UAC), orphaned active rules are reaped."""
    listener = hk_mod.AdaptiveHotkeyListener("F9", on_press=lambda: None, on_release=lambda: None)
    monkeypatch.setattr(hk_mod, "is_input_desktop_accessible", lambda: False)

    rule = listener.rules[0]
    rule.is_active = True
    rule.activated_by_hook = True
    listener._phys_down.add(0x78)
    listener._suppressed_down.add(0x78)

    listener._watchdog_tick(now_mono=100.0)

    assert rule.is_active is False
    assert rule.activated_by_hook is False
    assert listener._phys_down == set()
    assert listener._suppressed_down == set()
    assert not listener._event_queue.empty()
    assert listener._event_queue.get_nowait() == "release"


def test_v21_01_orphan_timeout_reaps_stalled_hook_rule(monkeypatch):
    """V21-01: Rule held longer than orphan_timeout_sec without KeyUp is reaped."""
    listener = hk_mod.AdaptiveHotkeyListener("F9", on_press=lambda: None, on_release=lambda: None, orphan_timeout_sec=10.0)
    monkeypatch.setattr(hk_mod, "is_input_desktop_accessible", lambda: True)

    rule = listener.rules[0]
    rule.is_active = True
    rule.activated_by_hook = True
    rule.activated_time = 100.0
    listener._phys_down.add(0x78)

    # Within timeout -> still active
    listener._watchdog_tick(now_mono=105.0)
    assert rule.is_active is True

    # Exceeded timeout -> reaped
    listener._watchdog_tick(now_mono=111.0)
    assert rule.is_active is False
    assert rule.activated_by_hook is False
    assert listener._phys_down == set()
    assert listener._event_queue.get_nowait() == "release"


def test_v21_02_probe_input_blocked_by_uipi_refreshes_ack_preventing_reinstall(monkeypatch):
    """V21-02: SendInput returning 0 (UIPI block in elevated window) refreshes probe ack, avoiding spurious reinstalls."""
    listener = hk_mod.AdaptiveHotkeyListener("F9", on_press=lambda: None, on_release=lambda: None)
    monkeypatch.setattr(hk_mod.AdaptiveHotkeyListener, "hook_alive", property(lambda s: True))
    monkeypatch.setattr(hk_mod, "is_input_desktop_accessible", lambda: True)
    monkeypatch.setattr(hk_mod.user32, "GetAsyncKeyState", lambda vk: 0)
    monkeypatch.setattr(hk_mod.user32, "SendInput", lambda n, p, s: 0)  # Simulated UIPI block

    reinstall_called = []
    monkeypatch.setattr(listener, "_reinstall_hook", lambda: reinstall_called.append(1) or True)

    listener._running = True
    listener._last_probe_sent = 100.0
    listener._last_probe_ack = 100.0

    # Tick at 102.5s (interval 2.0s reached)
    listener._watchdog_tick(now_mono=102.5)

    assert listener._last_probe_ack == 102.5
    assert reinstall_called == []
    listener._running = False


def test_v21_05_reinstall_hook_backoff_throttling(monkeypatch):
    """V21-05: Failed hook reinstalls obey HOOK_REINSTALL_BACKOFF_SEC before retrying."""
    listener = hk_mod.AdaptiveHotkeyListener("F9", on_press=lambda: None, on_release=lambda: None)
    monkeypatch.setattr(hk_mod, "is_input_desktop_accessible", lambda: True)
    monkeypatch.setattr(hk_mod.user32, "GetAsyncKeyState", lambda vk: 0)

    reinstall_count = []

    def _fake_reinstall():
        listener._last_reinstall_attempt = time.monotonic()
        reinstall_count.append(1)
        return False

    monkeypatch.setattr(listener, "_reinstall_hook", _fake_reinstall)

    listener._running = True
    listener._last_probe_sent = 100.0
    listener._last_probe_ack = 90.0  # Expired (> 4.5s)
    listener._last_reinstall_attempt = 100.0

    # Tick at 102.0s -> backoff (5.0s) not elapsed yet -> no reinstall
    listener._watchdog_tick(now_mono=102.0)
    assert reinstall_count == []

    # Tick at 106.0s -> backoff elapsed -> triggers reinstall
    listener._watchdog_tick(now_mono=106.0)
    assert len(reinstall_count) == 1
    listener._running = False


