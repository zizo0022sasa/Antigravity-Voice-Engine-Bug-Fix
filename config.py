import json
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

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
    position: str = "bottom_center"  # 'bottom_center', 'bottom_right', 'top_center'
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
    mode: str = "smart"  # 'smart', 'hold', 'toggle'
    audio_format: str = "m4a"  # 'm4a' (AAC compressed, 90% smaller) or 'wav'
    bitrate: str = "64k"
    smart_hold_threshold_sec: float = 0.45
    min_recording_duration_sec: float = 0.6
    max_recording_duration_sec: float = 600.0
    sample_rate: int = 44100
    channels: int = 1
    audio_device_index: Optional[int] = None
    save_directory: str = os.path.join(os.path.expanduser("~"), "Documents", "تسجيلات الصوت")
    auto_paste: bool = True
    paste_delay_ms: int = 150
    auto_send_enter: bool = False
    audio_cues: AudioCuesConfig = field(default_factory=AudioCuesConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "EngineConfig":
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        
        if not os.path.exists(config_path):
            cfg = cls()
            save_dir = os.path.abspath(os.path.expanduser(cfg.save_directory))
            os.makedirs(save_dir, exist_ok=True)
            cfg.save_directory = save_dir
            cfg.save(config_path)
            return cfg
            
        with open(config_path, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
            
        cues_data = data.get("audio_cues", {})
        cues_cfg = AudioCuesConfig(
            enabled=cues_data.get("enabled", True),
            start_freq=cues_data.get("start_freq", 1200),
            start_duration_ms=cues_data.get("start_duration_ms", 90),
            stop_freq=cues_data.get("stop_freq", 1600),
            stop_duration_ms=cues_data.get("stop_duration_ms", 120),
            cancel_freq=cues_data.get("cancel_freq", 450),
            cancel_duration_ms=cues_data.get("cancel_duration_ms", 150)
        )

        overlay_data = data.get("overlay", {})
        overlay_cfg = OverlayConfig(
            enabled=overlay_data.get("enabled", True),
            position=overlay_data.get("position", "bottom_center"),
            offset_y=int(overlay_data.get("offset_y", 50)),
            width=int(overlay_data.get("width", 260)),
            height=int(overlay_data.get("height", 44)),
            show_timer=bool(overlay_data.get("show_timer", True)),
            show_waveform=bool(overlay_data.get("show_waveform", True)),
            waveform_bars=int(overlay_data.get("waveform_bars", 7)),
            theme=overlay_data.get("theme", "dark")
        )
        
        save_dir = data.get("save_directory", os.path.join(os.path.expanduser("~"), "Documents", "تسجيلات الصوت"))
        save_dir = os.path.abspath(os.path.expanduser(save_dir))
        os.makedirs(save_dir, exist_ok=True)
        
        return cls(
            hotkey=data.get("hotkey", "CTRL+CAPSLOCK, F9, F10").upper(),
            mode=data.get("mode", "smart").lower(),
            audio_format=data.get("audio_format", "m4a").lower(),
            bitrate=str(data.get("bitrate", "96k")),
            smart_hold_threshold_sec=float(data.get("smart_hold_threshold_sec", 0.45)),
            min_recording_duration_sec=float(data.get("min_recording_duration_sec", 0.6)),
            max_recording_duration_sec=float(data.get("max_recording_duration_sec", 600.0)),
            sample_rate=int(data.get("sample_rate", 44100)),
            channels=int(data.get("channels", 1)),
            audio_device_index=data.get("audio_device_index"),
            save_directory=save_dir,
            auto_paste=bool(data.get("auto_paste", True)),
            paste_delay_ms=int(data.get("paste_delay_ms", 150)),
            auto_send_enter=bool(data.get("auto_send_enter", False)),
            audio_cues=cues_cfg,
            overlay=overlay_cfg
        )

    def save(self, config_path: str) -> None:
        data = {
            "hotkey": self.hotkey,
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
            "audio_cues": {
                "enabled": self.audio_cues.enabled,
                "start_freq": self.audio_cues.start_freq,
                "start_duration_ms": self.audio_cues.start_duration_ms,
                "stop_freq": self.audio_cues.stop_freq,
                "stop_duration_ms": self.audio_cues.stop_duration_ms,
                "cancel_freq": self.audio_cues.cancel_freq,
                "cancel_duration_ms": self.audio_cues.cancel_duration_ms
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
                "theme": self.overlay.theme
            }
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
