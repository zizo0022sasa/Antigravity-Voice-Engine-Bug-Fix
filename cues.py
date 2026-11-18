import threading
import winsound
from typing import Optional
from config import AudioCuesConfig

class AudioCues:
    """Non-blocking audio feedback controller using native Windows Beep."""
    def __init__(self, config: Optional[AudioCuesConfig] = None):
        self.config = config or AudioCuesConfig()

    def _beep_async(self, freq: int, duration_ms: int) -> None:
        if not self.config.enabled:
            return
        def _play():
            try:
                winsound.Beep(max(37, min(32767, freq)), max(1, duration_ms))
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()

    def play_start(self) -> None:
        """Triggered when recording starts."""
        self._beep_async(self.config.start_freq, self.config.start_duration_ms)

    def play_stop(self) -> None:
        """Triggered when recording stops successfully."""
        self._beep_async(self.config.stop_freq, self.config.stop_duration_ms)

    def play_cancel(self) -> None:
        """Triggered when recording is cancelled (e.g. too short)."""
        self._beep_async(self.config.cancel_freq, self.config.cancel_duration_ms)

