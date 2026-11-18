"""
Audio Recorder Module — Antigravity Smart Voice Engine.

ARCHITECTURAL GOVERNANCE RULE (IMMUTABLE):
Strictly captures local microphone audio and compresses it silently to M4A/WAV
for direct file drop. Zero network calls, zero external STT.
"""

import logging
import os
import shutil
import subprocess
import time
import wave
from datetime import datetime
from typing import Optional, List
import numpy as np
import sounddevice as sd

logger = logging.getLogger("VoiceEngine")


class AudioRecorder:
    """Handles low-latency microphone audio recording with zero-window M4A/AAC compression."""

    def __init__(
        self,
        save_dir: str,
        sample_rate: int = 44100,
        channels: int = 1,
        device_index: Optional[int] = None,
        min_duration_sec: float = 0.6,
        max_duration_sec: float = 600.0,
        audio_format: str = "m4a",
        bitrate: str = "64k",
    ):
        self.save_dir = os.path.abspath(os.path.expanduser(save_dir))
        os.makedirs(self.save_dir, exist_ok=True)
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self.min_duration_sec = min_duration_sec
        self.max_duration_sec = max_duration_sec
        self.audio_format = audio_format.lower()
        self.bitrate = bitrate

        self._stream: Optional[sd.InputStream] = None
        self._frames: List[np.ndarray] = []
        self._captured_samples: int = 0
        self._start_mono: float = 0.0
        self._is_recording: bool = False
        self._current_level: float = 0.0
        self._max_reached: bool = False
        self._overflow_logged: bool = False

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def elapsed_duration(self) -> float:
        if not self._is_recording:
            return 0.0
        return time.monotonic() - self._start_mono

    @property
    def current_level(self) -> float:
        return self._current_level if self._is_recording else 0.0

    @property
    def max_duration_reached(self) -> bool:
        return self._is_recording and (
            self._max_reached or (time.monotonic() - self._start_mono) >= self.max_duration_sec
        )

    def _audio_callback(self, indata, frames, time_info, status):
        """PortAudio streaming callback with overflow logging (AR-02) and strict RAM cap (AR-04)."""
        if status and not self._overflow_logged:
            self._overflow_logged = True
            logger.warning(f"⚠️ Audio input stream status warning: {status}")

        if not self._is_recording:
            return

        max_samples = int(self.max_duration_sec * self.sample_rate)
        remaining = max_samples - self._captured_samples
        if remaining <= 0:
            self._max_reached = True
            self._current_level = 0.0
            raise sd.CallbackStop()

        chunk = indata[:remaining].copy()
        self._frames.append(chunk)
        self._captured_samples += int(chunk.shape[0])

        data = chunk.astype(np.float32)
        rms = float(np.sqrt(np.mean(data ** 2))) if data.size else 0.0
        self._current_level = min(1.0, max(0.0, rms / 3500.0))

        if self._captured_samples >= max_samples:
            self._max_reached = True
            raise sd.CallbackStop()

    def start(self) -> bool:
        if self._is_recording:
            return False

        self._frames = []
        self._captured_samples = 0
        self._max_reached = False
        self._overflow_logged = False
        self._start_mono = time.monotonic()
        self._current_level = 0.0
        self._is_recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=self.device_index,
                dtype="int16",
                callback=self._audio_callback,
            )
            self._stream.start()
            return True
        except Exception as e:
            self._is_recording = False
            self._stream = None
            raise RuntimeError(f"Failed to start audio input stream: {e}") from e

    def _get_ffmpeg_path(self) -> Optional[str]:
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return shutil.which("ffmpeg")

    def _build_unique_base_path(self) -> str:
        stamp = datetime.now().strftime("Voice_%Y-%m-%d_%H-%M-%S")
        candidate = os.path.join(self.save_dir, stamp)
        if not (os.path.exists(f"{candidate}.m4a") or os.path.exists(f"{candidate}.wav")):
            return candidate
        idx = 2
        while os.path.exists(f"{candidate}_{idx}.m4a") or os.path.exists(f"{candidate}_{idx}.wav"):
            idx += 1
        return f"{candidate}_{idx}"

    @staticmethod
    def _remove_silent(path: str) -> None:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            logger.debug(f"Could not remove temporary file '{path}': {e}")

    def stop(self) -> Optional[str]:
        if not self._is_recording:
            return None

        self._is_recording = False
        self._current_level = 0.0
        duration = time.monotonic() - self._start_mono

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug(f"Audio stream close note: {e}")
            self._stream = None

        frames_snapshot = self._frames
        self._frames = []
        self._captured_samples = 0
        self._max_reached = False

        if duration < self.min_duration_sec or not frames_snapshot:
            return None

        audio_data = np.concatenate(frames_snapshot, axis=0)
        del frames_snapshot

        os.makedirs(self.save_dir, exist_ok=True)
        base_path = self._build_unique_base_path()
        wav_path = f"{base_path}.wav"

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())

        if self.audio_format == "m4a":
            ffmpeg_exe = self._get_ffmpeg_path()
            if ffmpeg_exe:
                m4a_path = f"{base_path}.m4a"
                cmd = [
                    ffmpeg_exe, "-y", "-i", wav_path,
                    "-c:a", "aac", "-b:a", self.bitrate,
                    "-ac", str(self.channels),
                    m4a_path,
                ]
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
                startupinfo = None
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0  # SW_HIDE

                try:
                    res = subprocess.run(
                        cmd,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        creationflags=creationflags,
                        startupinfo=startupinfo,
                        timeout=30,
                    )
                    if res.returncode == 0 and os.path.exists(m4a_path) and os.path.getsize(m4a_path) > 0:
                        self._remove_silent(wav_path)
                        return m4a_path

                    err_msg = (res.stderr or b"").decode("utf-8", errors="replace").strip()[-200:]
                    logger.warning(
                        f"⚠️ ffmpeg compression failed (code={res.returncode}): {err_msg}. Falling back to WAV."
                    )
                    self._remove_silent(m4a_path)
                except subprocess.TimeoutExpired:
                    logger.warning("⚠️ ffmpeg timed out after 30s; cleaning up partial M4A and falling back to WAV.")
                    self._remove_silent(m4a_path)
                except Exception as e:
                    logger.warning(f"⚠️ ffmpeg invocation error ({e}); falling back to WAV.")
                    self._remove_silent(m4a_path)

        return wav_path
