"""Cross-platform text-to-speech helper.

Usage:
    from tts import speak, speak_interrupt
    speak("Hello world")
    speak_interrupt("Stop and say this now")

This attempts, in order:
- Windows SAPI via `win32com.client` (best interruption support)
- pyttsx3 fallback
- macOS `say` command
- prints text if no TTS available
"""

import os
import sys
import subprocess

_DEBUG = False  # Set to True to enable debug output


def _dbg(msg: str) -> None:
    if _DEBUG:
        try:
            print("[tts]", msg)
        except Exception:
            pass


_engine = None


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine
    try:
        import pyttsx3

        _engine = pyttsx3.init()
        _dbg("Initialized pyttsx3 engine")
    except Exception as e:
        _dbg(f"pyttsx3 init failed: {e}")
        _engine = None
    return _engine


_sapi_voice = None


def _get_sapi_voice():
    """Return a shared SAPI voice instance (initialized once)."""
    global _sapi_voice
    if _sapi_voice is not None:
        return _sapi_voice

    try:
        import pythoncom
        import win32com.client

        # Ensure COM is initialized for this thread.
        pythoncom.CoInitialize()
        _sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
        _dbg("Initialized SAPI.SpVoice")
    except Exception as e:
        _dbg(f"SAPI init failed: {e}")
        _sapi_voice = None
    return _sapi_voice


def _say_sapi(text: str, interrupt: bool = False) -> bool:
    try:
        voice = _get_sapi_voice()
        if voice is None:
            return False

        # SVSFPurgeBeforeSpeak = 2 (stop current speech); SVSFlagsAsync = 1 (non-blocking)
        flags = 1 | (2 if interrupt else 0)
        _dbg(f"SAPI speak ({'interrupt' if interrupt else 'normal'}): {text}")
        voice.Speak(text, flags)
        return True
    except Exception as e:
        _dbg(f"SAPI failed: {e}")
        return False


def _say_pyttsx3(text: str, interrupt: bool = False) -> bool:
    engine = _get_engine()
    if engine is None:
        return False

    try:
        if interrupt:
            try:
                _dbg("pyttsx3 interrupt")
                engine.stop()
            except Exception as e:
                _dbg(f"pyttsx3 stop failed: {e}")
        _dbg(f"pyttsx3 speak ({'interrupt' if interrupt else 'normal'}): {text}")
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception as e:
        _dbg(f"pyttsx3 failed: {e}")
        return False


def _say_mac(text: str) -> bool:
    try:
        _dbg(f"macOS say: {text}")
        subprocess.run(["say", text], check=False)
        return True
    except Exception as e:
        _dbg(f"mac say failed: {e}")
        return False


def speak(text: str) -> None:
    """Speak text (non‑interrupting)."""
    # Try SAPI first (works on Windows even without pyttsx3 installed).
    if sys.platform.startswith("win") and _say_sapi(text, interrupt=False):
        return

    # fallback to pyttsx3
    if _say_pyttsx3(text, interrupt=False):
        return

    # macOS fallback
    if sys.platform == "darwin" and _say_mac(text):
        return

    # final fallback
    print(text)


def speak_interrupt(text: str) -> None:
    """Speak text immediately, stopping any existing speech."""
    if sys.platform.startswith("win") and _say_sapi(text, interrupt=True):
        return

    if _say_pyttsx3(text, interrupt=True):
        return

    if sys.platform == "darwin" and _say_mac(text):
        return

    print(text)


def stop() -> None:
    """Stop any ongoing speech."""
    # Use a short speak call with interruption to purge.
    if sys.platform.startswith("win"):
        _say_sapi("", interrupt=True)
    else:
        # Fallback: just issue an empty statement.
        _say_pyttsx3("", interrupt=True)


if __name__ == "__main__":
    speak("Text-to-speech helper installed and working.")
