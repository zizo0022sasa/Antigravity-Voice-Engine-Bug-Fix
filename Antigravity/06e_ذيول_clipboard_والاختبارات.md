# 📎 ملحق 06e: ذيول clipboard_injector.py والاختبارات

## 1. clipboard_injector.py (235–297)
`python
                    user32.CloseClipboard()
            time.sleep(0.03)

        kernel32.GlobalFree(h_drop)
        if h_text:
            kernel32.GlobalFree(h_text)
        logger.error(f"Failed to open clipboard after retries (WinError={ctypes.get_last_error()})")
        return False

    @staticmethod
    def simulate_paste(
        delay_ms: int = 120,
        extra_release_vks: Optional[Iterable[int]] = None,
        phys_down_checker: Optional[Callable[[Iterable[int]], bool]] = None,
    ) -> bool:
        """
        Sends sequenced Ctrl+V via Win32 SendInput ONLY after verifying physical modifiers
        are released. Returns False honestly on timeout or UIPI block (A3, CB-02, CB-11).
        """
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

        released = ClipboardInjector.wait_for_modifiers_release(
            timeout_ms=450,
            extra_vks=extra_release_vks,
            phys_down_checker=phys_down_checker,
        )
        if not released:
            logger.warning("⚠️ Aborting auto-paste: modifier keys still physically held after 450ms.")
            return False

        ctrl_down = _send_key_input(VK_LCONTROL, SCAN_LCTRL, key_up=False)
        if not ctrl_down:
            logger.warning(f"⚠️ SendInput(LCTRL down) blocked (WinError={ctypes.get_last_error()}).")
            return False

        try:
            time.sleep(PASTE_CTRL_SETTLE_SEC)
            v_down = _send_key_input(VK_V, SCAN_V, key_up=False)
            time.sleep(PASTE_V_HOLD_SEC)
            v_up = _send_key_input(VK_V, SCAN_V, key_up=True)
            time.sleep(PASTE_V_RELEASE_SETTLE_SEC)
        finally:
            ctrl_up = _send_key_input(VK_LCONTROL, SCAN_LCTRL, key_up=True)

        if not (v_down and v_up and ctrl_up):
            logger.warning(f"⚠️ SendInput(Ctrl+V) incomplete (WinError={ctypes.get_last_error()}).")
            return False
        return True

    @staticmethod
    def simulate_enter(delay_ms: int = 300) -> bool:
        """Simulates Enter key press via Win32 SendInput with honest bool return (A3)."""
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

        ok1 = _send_key_input(VK_RETURN, SCAN_ENTER, key_up=False)
        if not ok1:
            logger.warning(f"⚠️ SendInput(Enter down) blocked (WinError={ctypes.get_last_error()}).")
            return False
        time.sleep(0.025)
        ok2 = _send_key_input(VK_RETURN, SCAN_ENTER, key_up=True)
        return bool(ok1 and ok2)
`

## 2. 	ests/test_p0_characterization.py (175–269)
`python
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
`

## 3. 	ests/test_voice_engine.py (265–313)
`python
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
`
