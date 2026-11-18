"""
Entrypoint — Antigravity Smart Voice Engine.

=============================================================================
🔒 IMMUTABLE ARCHITECTURAL & GOVERNANCE RULE (DO NOT MODIFY):
  • Pure-Local Push-to-Talk Audio Recorder & Clipboard (CF_HDROP) File Drop ONLY.
  • ZERO external Speech-to-Text (STT), Whisper, Gemini APIs, or cloud relays.
  • Antigravity IDE natively processes attached audio files directly.
=============================================================================
"""

import ctypes
import os
import sys


def _enable_per_monitor_dpi_awareness() -> None:
    """
    Enables Per-Monitor v2 DPI awareness BEFORE Tkinter or audio drivers initialize.
    Prevents 4K / 225% scaling coordinate drift and blurry/tiny overlay rendering.
    """
    if os.name != "nt":
        return
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4 (Windows 10 1703+ / Windows 11)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_ssize_t(-4))
        return
    except Exception:
        pass
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# Must execute at process entry BEFORE importing tkinter/sounddevice
_enable_per_monitor_dpi_awareness()

# Ensure current script directory is in sys.path and is current working directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
try:
    os.chdir(SCRIPT_DIR)
except Exception:
    pass

import signal
import logging
from config import EngineConfig
from engine import VoiceEngine

# Ensure safe stdout/stderr handling for pythonw.exe and Windows consoles
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

# Setup file + console logging (prevent duplicate handlers on re-import)
log_path = os.path.join(SCRIPT_DIR, "voice_engine.log")
root_logger = logging.getLogger()
if not root_logger.handlers:
    handlers = [logging.FileHandler(log_path, encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
logger = logging.getLogger("VoiceEngine")


def print_banner(cfg: EngineConfig):
    if sys.stdout is None:
        return
    try:
        print("=" * 65)
        print(" 🎙️  ANTIGRAVITY SMART VOICE ENGINE (Push-to-Talk & File Drop)")
        print("=" * 65)
        print(f" • Hotkeys:           [{cfg.hotkey}]")
        print(f" • Mode:              {cfg.mode.upper()} (Smart Hold / Toggle)")
        print(f" • Audio Archive:     {cfg.save_directory}")
        print(f" • Auto Paste:        {'ENABLED (Ctrl+V)' if cfg.auto_paste else 'DISABLED'}")
        print(f" • Auto Send (Enter): {'ENABLED' if cfg.auto_send_enter else 'DISABLED'}")
        print("-" * 65)
        print(" 💡 Instructions:")
        print("   1. Go to any Antigravity IDE chat window.")
        print(f"   2. Press & HOLD or TAP [{cfg.hotkey}] to talk.")
        print("   3. Finish talking -> Audio attaches automatically into chat!")
        print("   Press Ctrl+C anytime to exit.")
        print("=" * 65 + "\n")
    except Exception:
        pass


_SINGLETON_MUTEX = None


def check_single_instance():
    """Prevents duplicate instances using 64-bit safe Win32 named mutex."""
    global _SINGLETON_MUTEX
    if os.name != "nt":
        return True
    try:
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        k32.CreateMutexW.restype = wintypes.HANDLE

        mutex_name = "Local\\AntigravityVoiceEngine_SingleInstance"
        mutex = k32.CreateMutexW(None, False, mutex_name)
        if not mutex:
            return True
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            logger.info("ℹ️ Voice Engine is already running in the background. Exiting duplicate.")
            k32.CloseHandle(mutex)
            return None
        _SINGLETON_MUTEX = mutex
        return mutex
    except Exception:
        return True


def main():
    _mutex = check_single_instance()
    if not _mutex:
        sys.exit(0)

    cfg = EngineConfig.load()
    print_banner(cfg)

    engine = VoiceEngine(cfg)
    engine.start()

    def signal_handler(sig, frame):
        logger.info("Shutting down Voice Engine gracefully...")
        engine.stop()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except Exception:
        pass

    try:
        engine.run_loop()
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
