"""
T-P0-00: Characterization & Red-Phase Unit Tests (Executed BEFORE Production Refactor).

Covers:
  - HK-11 / N3: Hook-activated rules must NOT be released by Watchdog when GetAsyncKeyState == 0.
  - HK-12 / A5: Symmetrical KeyUp suppression via _suppressed_down even if rule.is_active changed.
  - HK-02 / DEC-01 / N2: strict_modifiers passes Shift+F10 through without polluting _suppressed_down.
  - A2 / N1: Heartbeat probe (VK_NONAME 0xFC + magic 0x41475956) acked & swallowed before LLKHF_INJECTED;
             probe with wrong magic ignored as normal injected event.
  - CB-11 / A3: simulate_paste returns False honestly when SendInput fails (no lying keybd_event fallback).
  - CB-02 / R10: wait_for_modifiers_release returns bool; held modifier after timeout aborts paste (returns False).
  - EN-01: Engine displays honest fallback badge when simulate_paste returns False.
  - CF-01 / CF-02 / R4: _HotkeyRule rejects unknown tokens; EngineConfig validates enums & deep-merges local config.
  - TS-06: Overlay _reposition math at 4K (3840x2160 workarea, scale=2.25).
"""

import ctypes
import json
import os
import sys
import threading
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config as config_mod
import hotkey_listener as hk_mod
import clipboard_injector as cb_mod
import overlay as ov_mod
import engine as eng_mod


def _make_ll_struct(vk: int, flags: int = 0, extra: int = 0, scan: int = 0, tick: int = 1000):
    kb = hk_mod.KBDLLHOOKSTRUCT(
        vkCode=vk,
        scanCode=scan,
        flags=flags,
        time=tick,
        dwExtraInfo=extra,
    )
    return kb, ctypes.addressof(kb)


def test_cf01_unknown_hotkey_token_raises_value_error():
    """CF-01: Unknown token in hotkey spec must raise ValueError instead of silently dropping to CTRL."""
    with pytest.raises(ValueError):
        hk_mod._HotkeyRule("CTRL+NONEXISTENTKEY")


def test_cf01_alphanumeric_tokens_supported():
    """CF-01: Standard A-Z and 0-9 keys are supported in VK_MAP."""
    rule = hk_mod._HotkeyRule("CTRL+Q")
    assert rule.trigger_vk == 0x51
    assert rule.modifier_vks == [0x11]


def test_hk11_n3_watchdog_does_not_release_hook_owned_rule(monkeypatch):
    """
    HK-11 + N3: When WH_KEYBOARD_LL suppresses F10 (return 1), Windows GetAsyncKeyState(F10)
    stays 0. A single _watchdog_tick() MUST NOT release a rule with activated_by_hook == True.
    """
    listener = hk_mod.AdaptiveHotkeyListener("F10", on_press=lambda: None, on_release=lambda: None)
    monkeypatch.setattr(hk_mod.user32, "CallNextHookEx", lambda h, n, w, l: 0)
    monkeypatch.setattr(hk_mod.user32, "GetAsyncKeyState", lambda vk: 0)

    # Trigger physical F10 KeyDown through _low_level_proc
    kb_down, ptr_down = _make_ll_struct(vk=0x79, flags=0)
    res = listener._low_level_proc(0, hk_mod.WM_SYSKEYDOWN, ptr_down)
    assert res == 1
    assert listener.rules[0].is_active is True
    assert listener.rules[0].activated_by_hook is True
    assert listener._event_queue.get_nowait() == "press"

    # Run deterministic single watchdog tick while GetAsyncKeyState returns 0
    if hasattr(listener, "_watchdog_tick"):
        listener._watchdog_tick()
    else:
        listener._running = True
        t = threading.Thread(target=listener._watchdog_loop, daemon=True)
        t.start()
        time.sleep(0.05)
        listener._running = False
        t.join(timeout=0.2)

    # Rule MUST remain active and queue MUST remain empty!
    assert listener.rules[0].is_active is True, "HK-11 BUG REPRODUCED: Watchdog prematurely released hook-owned rule!"
    assert listener._event_queue.empty()
    assert hasattr(listener, "_watchdog_tick"), "Missing deterministic _watchdog_tick() helper (N3)"


def test_hk12_a5_symmetrical_keyup_suppression_when_modifier_released_first(monkeypatch):
    """
    HK-12 + A5: In CTRL+CAPSLOCK, if CTRL is released BEFORE CAPSLOCK, the rule becomes
    inactive on CTRL KeyUp, yet the subsequent physical CAPSLOCK KeyUp MUST still be suppressed!
    """
    listener = hk_mod.AdaptiveHotkeyListener("CTRL+CAPSLOCK", on_press=lambda: None, on_release=lambda: None)
    monkeypatch.setattr(hk_mod.user32, "CallNextHookEx", lambda h, n, w, l: 0)
    # Simulate CTRL physically held
    monkeypatch.setattr(hk_mod.user32, "GetAsyncKeyState", lambda vk: -32768 if vk in (0x11, 0xA2) else 0)

    # 1. CAPSLOCK KeyDown while CTRL is held -> suppressed (1)
    kb_caps_dn, ptr_caps_dn = _make_ll_struct(vk=0x14, flags=0)
    assert listener._low_level_proc(0, hk_mod.WM_KEYDOWN, ptr_caps_dn) == 1
    assert listener.rules[0].is_active is True

    # 2. CTRL KeyUp arrives FIRST -> rule becomes inactive, CTRL KeyUp passes to OS (0)
    monkeypatch.setattr(hk_mod.user32, "GetAsyncKeyState", lambda vk: 0)
    kb_ctrl_up, ptr_ctrl_up = _make_ll_struct(vk=0xA2, flags=0)
    assert listener._low_level_proc(0, hk_mod.WM_KEYUP, ptr_ctrl_up) == 0
    assert listener.rules[0].is_active is False

    # 3. Orphan CAPSLOCK KeyUp arrives -> MUST still be suppressed (1) via _suppressed_down!
    kb_caps_up, ptr_caps_up = _make_ll_struct(vk=0x14, flags=0)
    assert listener._low_level_proc(0, hk_mod.WM_KEYUP, ptr_caps_up) == 1
    assert 0x14 not in listener._suppressed_down


def test_n2_strict_modifiers_passes_shift_f10_without_polluting_suppressed_down(monkeypatch):
    """
    DEC-01 + HK-02 + N2: With strict_modifiers=True, Shift+F10 must NOT trigger F10 rule,
    both KeyDown and KeyUp must pass through (return 0), and _suppressed_down stays empty.
    """
    listener = hk_mod.AdaptiveHotkeyListener("F10", on_press=lambda: None, on_release=lambda: None)
    monkeypatch.setattr(hk_mod.user32, "CallNextHookEx", lambda h, n, w, l: 0)
    # Simulate SHIFT held
    monkeypatch.setattr(hk_mod.user32, "GetAsyncKeyState", lambda vk: -32768 if vk in (0x10, 0xA0) else 0)

    kb_dn, ptr_dn = _make_ll_struct(vk=0x79, flags=0)
    assert listener._low_level_proc(0, hk_mod.WM_SYSKEYDOWN, ptr_dn) == 0
    assert listener.rules[0].is_active is False
    assert len(getattr(listener, "_suppressed_down", set())) == 0

    kb_up, ptr_up = _make_ll_struct(vk=0x79, flags=0)
    assert listener._low_level_proc(0, hk_mod.WM_SYSKEYUP, ptr_up) == 0


def test_n1_magic_probe_acked_before_injected_and_wrong_magic_ignored(monkeypatch):
    """
    A2 + N1: VK_NONAME (0xFC) with magic 0x41475956 updates _last_probe_ack and returns 1
    even with LLKHF_INJECTED set; wrong magic with LLKHF_INJECTED passes to CallNextHookEx (0).
    """
    listener = hk_mod.AdaptiveHotkeyListener("F9", on_press=lambda: None, on_release=lambda: None)
    monkeypatch.setattr(hk_mod.user32, "CallNextHookEx", lambda h, n, w, l: 0)

    old_ack = getattr(listener, "_last_probe_ack", 0.0)
    time.sleep(0.01)

    # Wrong magic -> ignored as normal injected event (returns 0, ack unchanged)
    kb_bad, ptr_bad = _make_ll_struct(vk=0xFC, flags=hk_mod.LLKHF_INJECTED, extra=0xDEADBEEF)
    assert listener._low_level_proc(0, hk_mod.WM_KEYUP, ptr_bad) == 0
    assert getattr(listener, "_last_probe_ack", 0.0) == old_ack

    # Valid magic -> swallowed (returns 1) and updates _last_probe_ack!
    kb_ok, ptr_ok = _make_ll_struct(vk=0xFC, flags=hk_mod.LLKHF_INJECTED, extra=0x41475956)
    assert listener._low_level_proc(0, hk_mod.WM_KEYUP, ptr_ok) == 1
    assert listener._last_probe_ack > old_ack


def test_cb11_a3_simulate_paste_returns_false_when_sendinput_fails(monkeypatch):
    """
    CB-11 + A3: When SendInput fails (returns 0, e.g. UIPI), simulate_paste MUST return False
    and MUST NOT mask failure with a lying void keybd_event fallback.
    """
    monkeypatch.setattr(cb_mod, "_send_key_input", lambda vk, scan, key_up=False: False)
    monkeypatch.setattr(cb_mod.ClipboardInjector, "wait_for_modifiers_release", staticmethod(lambda **kw: True))
    assert cb_mod.ClipboardInjector.simulate_paste(delay_ms=0) is False


def test_cb02_held_modifier_timeout_aborts_paste(monkeypatch):
    """
    CB-02: If user keeps holding CTRL past wait_for_modifiers_release timeout,
    wait_for_modifiers_release returns False and simulate_paste aborts (returns False) without sending bare 'V'.
    """
    sent_keys = []
    monkeypatch.setattr(cb_mod.user32, "GetAsyncKeyState", lambda vk: -32768 if vk == cb_mod.VK_CONTROL else 0)
    monkeypatch.setattr(cb_mod, "_send_key_input", lambda vk, scan, key_up=False: sent_keys.append(vk) or True)

    released = cb_mod.ClipboardInjector.wait_for_modifiers_release(timeout_ms=30)
    assert released is False
    assert cb_mod.ClipboardInjector.simulate_paste(delay_ms=0) is False
    assert sent_keys == []


def test_en01_engine_shows_honest_warning_badge_when_paste_fails(tmp_path, monkeypatch):
    """
    EN-01: _finish_recording must inspect simulate_paste bool return value and show fallback
    badge instead of lying '⚡ تم اللصق!' when paste returns False.
    """
    dummy_audio = tmp_path / "Voice_2026-11-18_09-50-00.m4a"
    dummy_audio.write_bytes(b"M4ADUMMY")

    cfg = config_mod.EngineConfig(
        hotkey="F9",
        save_directory=str(tmp_path),
        auto_paste=True,
        audio_cues=config_mod.AudioCuesConfig(enabled=False),
        overlay=config_mod.OverlayConfig(enabled=False),
    )
    engine = eng_mod.VoiceEngine(cfg)
    monkeypatch.setattr(engine.recorder, "stop", lambda: str(dummy_audio))
    monkeypatch.setattr(engine.injector, "ensure_target_focus", lambda **kw: 12345)
    monkeypatch.setattr(engine.injector, "get_window_title", lambda h: "Admin Window")
    monkeypatch.setattr(engine.injector, "set_clipboard_file", lambda p: True)
    monkeypatch.setattr(engine.injector, "simulate_paste", lambda *a, **kw: False)

    badges = []
    monkeypatch.setattr(engine.overlay, "show_success", lambda text="⚡ تم اللصق!": badges.append(text))

    engine._finish_recording()
    assert len(badges) == 1
    assert "تم اللصق" not in badges[0]
    assert "حُفظ" in badges[0]


def test_cf02_r4_config_validation_and_deep_merge_local(tmp_path):
    """
    CF-02 + R4 + TS-03: Invalid mode/format fallback safely with warning, and config.local.json
    deep-merges nested overlay keys without wiping sibling overlay settings.
    """
    cfg_path = tmp_path / "config.json"
    local_path = tmp_path / "config.local.json"

    cfg_path.write_text(
        json.dumps({
            "mode": "invalid_mode",
            "audio_format": "ogg_invalid",
            "save_directory": "~/Documents/تسجيلات الصوت",
            "overlay": {"position": "bottom_center", "offset_y": 50, "waveform_bars": 9},
        }),
        encoding="utf-8",
    )
    local_path.write_text(
        json.dumps({"overlay": {"offset_y": 88}}),
        encoding="utf-8",
    )

    loaded = config_mod.EngineConfig.load(str(cfg_path))
    assert loaded.mode == "smart"
    assert loaded.audio_format == "m4a"
    assert loaded.overlay.offset_y == 88
    assert loaded.overlay.waveform_bars == 9  # Preserved via deep merge!


def test_ts06_overlay_4k_225_percent_reposition_math(monkeypatch):
    """TS-06: Verifies exact bottom_center coordinates on 3840x2160 workarea at 225% scale (2.25)."""
    monkeypatch.setattr(
        ov_mod,
        "_query_active_monitor_workarea_and_scale",
        lambda: (0, 0, 3840, 2052, 2.25),
    )
    overlay = ov_mod.VoiceOverlay(enabled=True, position="bottom_center", offset_y=50, width=260, height=44)
    overlay.init_ui()
    try:
        assert overlay._root is not None
        overlay._reposition()
        overlay._root.update_idletasks()
        assert overlay.width == round(260 * 2.25)   # 585
        assert overlay.height == round(44 * 2.25)   # 99
        assert overlay.offset_y == round(50 * 2.25) # 112
        geom = overlay._root.geometry()
        # Expected: 585x99+1627+1841
        expected_x = (3840 - 585) // 2
        expected_y = 2052 - 99 - 112
        assert f"+{expected_x}+{expected_y}" in geom
    finally:
        overlay.stop()
