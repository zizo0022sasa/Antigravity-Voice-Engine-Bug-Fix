"""
Audio Recorder Module — Antigravity Smart Voice Engine.

ARCHITECTURAL GOVERNANCE RULE (IMMUTABLE):
This module strictly captures local microphone audio and compresses it to M4A/WAV
for direct file drop into Antigravity IDE. NEVER add external Speech-to-Text (STT),
Whisper, Gemini APIs, or cloud transcription relays here.
"""

import os
import time
import wave
import subprocess
from datetime import datetime
from typing import Optional, List
import numpy as np
import sounddevice as sd


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
        self.save_dir = os.path.abspath(save_dir)
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
        self._start_time: float = 0.0
        self._is_recording: bool = False
        self._current_level: float = 0.0
        self._max_reached: bool = False

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def elapsed_duration(self) -> float:
        if not self._is_recording:
            return 0.0
        return time.time() - self._start_time

    @property
    def current_level(self) -> float:
        """Returns normalized microphone audio level (0.0 to 1.0)."""
        return self._current_level if self._is_recording else 0.0

    @property
    def max_duration_reached(self) -> bool:
        """True when recording has hit max_duration_sec cap."""
        return self._is_recording and (
            self._max_reached or (time.time() - self._start_time) >= self.max_duration_sec
        )

    def _audio_callback(self, indata, frames, time_info, status):
        """Sounddevice streaming callback with strict max_duration_sec RAM cap."""
        if self._is_recording:
            max_samples = int(self.max_duration_sec * self.sample_rate)
            remaining = max_samples - self._captured_samples
            if remaining <= 0:
                self._max_reached = True
                self._current_level = 0.0
                return
            chunk = indata[:remaining].copy()
            self._frames.append(chunk)
            self._captured_samples += int(chunk.shape[0])
            if self._captured_samples >= max_samples:
                self._max_reached = True
            try:
                # Fast vectorized RMS calculation for real-time waveform visualization
                data = chunk.astype(np.float32)
                rms = np.sqrt(np.mean(data ** 2))
                norm = float(rms) / 3500.0
                self._current_level = min(1.0, max(0.0, norm))
            except Exception:
                pass

    def start(self) -> bool:
        """Starts recording audio stream."""
        if self._is_recording:
            return False

        self._frames = []
        self._captured_samples = 0
        self._max_reached = False
        self._start_time = time.time()
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
            raise RuntimeError(f"Failed to start audio input stream: {e}")

    def _get_ffmpeg_path(self) -> Optional[str]:
        """Resolves ffmpeg path via imageio_ffmpeg or system PATH."""
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
        import shutil
        return shutil.which("ffmpeg")

    def _build_unique_base_path(self) -> str:
        """
        Generates chronologically sortable filename WITHOUT weekday name:
        Example: Voice_2026-11-18_07-55-03
        Appends _2, _3 only if two clips finish within the exact same second.
        """
        stamp = datetime.now().strftime("Voice_%Y-%m-%d_%H-%M-%S")
        candidate = os.path.join(self.save_dir, stamp)
        if not (os.path.exists(f"{candidate}.m4a") or os.path.exists(f"{candidate}.wav")):
            return candidate
        idx = 2
        while os.path.exists(f"{candidate}_{idx}.m4a") or os.path.exists(f"{candidate}_{idx}.wav"):
            idx += 1
        return f"{candidate}_{idx}"

    def stop(self) -> Optional[str]:
        """
        Stops recording and saves audio file (M4A or WAV) without spawning any console window.
        Returns file path if valid recording, or None if too short/cancelled.
        """
        if not self._is_recording:
            return None

        self._is_recording = False
        self._current_level = 0.0
        duration = time.time() - self._start_time

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        # Snapshot & immediately release PCM frame buffer so daemon idle RAM stays ~0MB
        frames_snapshot = self._frames
        self._frames = []
        self._captured_samples = 0
        self._max_reached = False

        # Reject accidental micro-clicks
        if duration < self.min_duration_sec or not frames_snapshot:
            return None

        audio_data = np.concatenate(frames_snapshot, axis=0)
        del frames_snapshot
        base_path = self._build_unique_base_path()
        wav_path = f"{base_path}.wav"

        # Write standard PCM WAV first
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())

        # Compress to M4A silently (CREATE_NO_WINDOW + SW_HIDE prevents focus theft under pythonw.exe)
        if self.audio_format == "m4a":
            ffmpeg_exe = self._get_ffmpeg_path()
            if ffmpeg_exe:
                m4a_path = f"{base_path}.m4a"
                try:
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

                    res = subprocess.run(
                        cmd,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=creationflags,
                        startupinfo=startupinfo,
                        timeout=30,
                    )
                    if res.returncode == 0 and os.path.exists(m4a_path) and os.path.getsize(m4a_path) > 0:
                        try:
                            os.remove(wav_path)
                        except Exception:
                            pass
                        return m4a_path
                except Exception:
                    pass

        return wav_path
