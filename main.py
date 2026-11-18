"""
Entrypoint — Antigravity Smart Voice Engine.

=============================================================================
🔒 IMMUTABLE ARCHITECTURAL & GOVERNANCE RULE (DO NOT MODIFY):
  • Pure-Local Push-to-Talk Audio Recorder & Clipboard (CF_HDROP) File Drop ONLY.
  • ZERO external Speech-to-Text (STT), Whisper, Gemini APIs, or network calls.
=============================================================================
"""

import ctypes
import os
import sys


def _enable_per_monitor_dpi_awareness() -> None:
    """Enables Per-Monitor v2 DPI awareness BEFORE Tkinter or audio drivers initialize."""
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_ssize_t(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_per_monitor_dpi_awareness()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
try:
    os.chdir(SCRIPT_DIR)
except OSError:
    pass

import logging
from logging.handlers import RotatingFileHandler
import signal

from config import EngineConfig
from engine import VoiceEngine
from win32_api import kernel32

SINGLETON_MUTEX_NAME = "Local\\AntigravityVoiceEngine_SingleInstance"
SHUTDOWN_EVENT_NAME = "Local\\AntigravityVoiceEngine_Shutdown"

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Setup bounded rotating file logging with read-only directory fallback (SEC-01, REL-01)
log_path = os.path.join(SCRIPT_DIR, "voice_engine.log")
root_logger = logging.getLogger()
if not root_logger.handlers:
    handlers = []
    try:
        handlers.append(
            RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        )
    except OSError:
        handlers.append(logging.NullHandler())
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
logger = logging.getLogger("VoiceEngine")

_SINGLETON_MUTEX = None
_SHUTDOWN_EVENT = None


def check_single_instance():
    """Prevents duplicate instances using 64-bit safe Win32 named mutex."""
    global _SINGLETON_MUTEX
    if os.name != "nt":
        return True
    mutex = kernel32.CreateMutexW(None, False, SINGLETON_MUTEX_NAME)
    if not mutex:
        return True
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        logger.info("ℹ️ Voice Engine is already running in the background. Exiting duplicate.")
        kernel32.CloseHandle(mutex)
        return None
    _SINGLETON_MUTEX = mutex
    return mutex


def create_shutdown_event() -> int:
    """Creates named Win32 event allowing graceful stop from stop_voice.bat / uninstall (R8)."""
    global _SHUTDOWN_EVENT
    if os.name != "nt":
        return 0
    evt = kernel32.CreateEventW(None, False, False, SHUTDOWN_EVENT_NAME)
    _SHUTDOWN_EVENT = evt
    return int(evt) if evt else 0


def print_banner(cfg: EngineConfig):
    if sys.stdout is None:
        return
    try:
        print("=" * 65)
        print(" 🎙️  ANTIGRAVITY SMART VOICE ENGINE (Push-to-Talk & File Drop)")
        print("=" * 65)
        print(f" • Hotkeys:           [{cfg.hotkey}]")
        print(f" • Mode:              {cfg.mode.upper()} (Smart Hold / Toggle)")
        print(f" • Audio Archive:     {cfg.resolved_save_directory}")
        print(f" • Auto Paste:        {'ENABLED (Ctrl+V)' if cfg.auto_paste else 'DISABLED'}")
        print(f" • Auto Send (Enter): {'ENABLED' if cfg.auto_send_enter else 'DISABLED'}")
        print("=" * 65 + "\n")
    except Exception:
        pass


def main():
    _mutex = check_single_instance()
    if not _mutex:
        sys.exit(0)

    shutdown_evt = create_shutdown_event()
    cfg = EngineConfig.load()
    print_banner(cfg)

    engine = VoiceEngine(cfg, shutdown_event_handle=shutdown_evt)
    engine.start()

    def signal_handler(sig, frame):
        logger.info("Shutting down Voice Engine gracefully...")
        engine.stop()
        sys.exit(0)

    for sig_name in ("SIGINT", "SIGTERM"):
        sig_val = getattr(signal, sig_name, None)
        if sig_val is not None:
            try:
                signal.signal(sig_val, signal_handler)
            except Exception:
                pass

    try:
        engine.run_loop()
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
