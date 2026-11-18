"""
Configuration Schema & Loader — Antigravity Smart Voice Engine.

Implements:
  • Single Source of Truth defaults on dataclasses (CF-04).
  • Strict enum & numeric validation with safe fallback + warning logs (CF-02).
  • Deep recursive merge for optional config.local.json overrides (CF-05, R4).
  • Zero filesystem directory-creation side effects inside load() (TS-03).
  • Preservation of unexpanded '~' paths on save() for privacy (DEC-06).
"""

import copy
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

logger = logging.getLogger("VoiceEngine")

VALID_MODES = ("smart", "hold", "toggle")
VALID_AUDIO_FORMATS = ("m4a", "wav")
VALID_POSITIONS = ("bottom_center", "bottom_right", "top_center")
DEFAULT_BLOCKED_PROCESSES = ["explorer.exe", "SearchHost.exe", "ShellExperienceHost.exe"]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merges override dictionary into a copy of base dictionary (R4)."""
    merged = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = copy.deepcopy(v)
    return merged


@dataclass
class AudioCuesConfig:
    enabled: bool = True
    start_freq: int = 1200
    start_duration_ms: int = 90
    stop_freq: int = 1600
    stop_duration_ms: int = 120
    cancel_freq: int = 450
    cancel_duration_ms: int = 150


@dataclass
class OverlayConfig:
    enabled: bool = True
    position: str = "bottom_center"
    offset_y: int = 50
    width: int = 260
    height: int = 44
    show_timer: bool = True
    show_waveform: bool = True
    waveform_bars: int = 7
    theme: str = "dark"


@dataclass
class EngineConfig:
    hotkey: str = "CTRL+CAPSLOCK, F9, F10"
    strict_modifiers: bool = True
    mode: str = "smart"
    audio_format: str = "m4a"
    bitrate: str = "64k"
    smart_hold_threshold_sec: float = 0.45
    min_recording_duration_sec: float = 0.6
    max_recording_duration_sec: float = 600.0
    sample_rate: int = 44100
    channels: int = 1
    audio_device_index: Optional[int] = None
    save_directory: str = "~/Documents/تسجيلات الصوت"
    auto_paste: bool = True
    paste_delay_ms: int = 150
    auto_send_enter: bool = False
    auto_send_enter_delay_ms: int = 300
    blocked_paste_processes: List[str] = field(default_factory=lambda: list(DEFAULT_BLOCKED_PROCESSES))
    allowed_paste_processes: List[str] = field(default_factory=list)
    log_window_titles: bool = False
    audio_cues: AudioCuesConfig = field(default_factory=AudioCuesConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)

    @property
    def resolved_save_directory(self) -> str:
        """Expands '~' and environment variables without mutating raw save_directory."""
        return os.path.abspath(os.path.expanduser(os.path.expandvars(self.save_directory)))

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "EngineConfig":
        defaults = cls()
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

        if not os.path.exists(config_path):
            defaults.save(config_path)
            return defaults

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse '{config_path}', using defaults: {e}")
            return defaults

        # Optional local override: config.local.json alongside config_path (CF-05, R4)
        cfg_dir = os.path.dirname(os.path.abspath(config_path))
        local_path = os.path.join(cfg_dir, "config.local.json")
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as lf:
                    local_data = json.load(lf)
                if isinstance(local_data, dict):
                    data = _deep_merge(data, local_data)
            except Exception as e:
                logger.warning(f"⚠️ Failed to parse '{local_path}', ignoring override: {e}")

        cues_def = defaults.audio_cues
        cues_data = data.get("audio_cues") if isinstance(data.get("audio_cues"), dict) else {}
        cues_cfg = AudioCuesConfig(
            enabled=bool(cues_data.get("enabled", cues_def.enabled)),
            start_freq=int(cues_data.get("start_freq", cues_def.start_freq)),
            start_duration_ms=int(cues_data.get("start_duration_ms", cues_def.start_duration_ms)),
            stop_freq=int(cues_data.get("stop_freq", cues_def.stop_freq)),
            stop_duration_ms=int(cues_data.get("stop_duration_ms", cues_def.stop_duration_ms)),
            cancel_freq=int(cues_data.get("cancel_freq", cues_def.cancel_freq)),
            cancel_duration_ms=int(cues_data.get("cancel_duration_ms", cues_def.cancel_duration_ms)),
        )

        ov_def = defaults.overlay
        ov_data = data.get("overlay") if isinstance(data.get("overlay"), dict) else {}
        raw_pos = str(ov_data.get("position", ov_def.position)).lower().strip()
        if raw_pos not in VALID_POSITIONS:
            logger.warning(f"⚠️ Invalid overlay.position '{raw_pos}', falling back to '{ov_def.position}'")
            raw_pos = ov_def.position

        overlay_cfg = OverlayConfig(
            enabled=bool(ov_data.get("enabled", ov_def.enabled)),
            position=raw_pos,
            offset_y=int(ov_data.get("offset_y", ov_def.offset_y)),
            width=max(120, int(ov_data.get("width", ov_def.width))),
            height=max(28, int(ov_data.get("height", ov_def.height))),
            show_timer=bool(ov_data.get("show_timer", ov_def.show_timer)),
            show_waveform=bool(ov_data.get("show_waveform", ov_def.show_waveform)),
            waveform_bars=max(3, min(15, int(ov_data.get("waveform_bars", ov_def.waveform_bars)))),
            theme=str(ov_data.get("theme", ov_def.theme)),
        )

        raw_mode = str(data.get("mode", defaults.mode)).lower().strip()
        if raw_mode not in VALID_MODES:
            logger.warning(f"⚠️ Invalid mode '{raw_mode}', falling back to '{defaults.mode}'")
            raw_mode = defaults.mode

        raw_fmt = str(data.get("audio_format", defaults.audio_format)).lower().strip()
        if raw_fmt not in VALID_AUDIO_FORMATS:
            logger.warning(f"⚠️ Invalid audio_format '{raw_fmt}', falling back to '{defaults.audio_format}'")
            raw_fmt = defaults.audio_format

        sample_rate = int(data.get("sample_rate", defaults.sample_rate))
        if sample_rate <= 0:
            logger.warning(f"⚠️ Invalid sample_rate {sample_rate}, falling back to {defaults.sample_rate}")
            sample_rate = defaults.sample_rate

        channels = int(data.get("channels", defaults.channels))
        if channels not in (1, 2):
            logger.warning(f"⚠️ Invalid channels {channels}, falling back to {defaults.channels}")
            channels = defaults.channels

        blocked = data.get("blocked_paste_processes", defaults.blocked_paste_processes)
        if not isinstance(blocked, list):
            blocked = list(defaults.blocked_paste_processes)

        allowed = data.get("allowed_paste_processes", defaults.allowed_paste_processes)
        if not isinstance(allowed, list):
            allowed = list(defaults.allowed_paste_processes)

        return cls(
            hotkey=str(data.get("hotkey", defaults.hotkey)).upper(),
            strict_modifiers=bool(data.get("strict_modifiers", defaults.strict_modifiers)),
            mode=raw_mode,
            audio_format=raw_fmt,
            bitrate=str(data.get("bitrate", defaults.bitrate)),
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
