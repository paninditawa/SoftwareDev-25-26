"""Cross-platform text-to-speech helper.

Usage:
    from tts import speak, speak_interrupt
    speak("Hello world")
    speak_interrupt("Stop and say this now")

Speech backend priority:
1. Google TTS (gTTS) — natural human-sounding voice, cached locally.
2. Windows SAPI via win32com.client — offline fallback with interruption.
3. pyttsx3 — cross-platform offline fallback.
4. macOS ``say`` command.
5. Plain print as last resort.

Set TTS_BACKEND=sapi or TTS_BACKEND=pyttsx3 to force an offline engine.
"""

import hashlib
import io
import os
import sys
import subprocess
import tempfile
import threading
from pathlib import Path

_DEBUG = False  # Set to True to enable debug output

# ---------------------------------------------------------------------------
# Cache directory for gTTS audio files
# ---------------------------------------------------------------------------
_CACHE_DIR = Path(tempfile.gettempdir()) / "gamespace_tts_cache"
_CACHE_DIR.mkdir(exist_ok=True)


def _dbg(msg: str) -> None:
    if _DEBUG:
        try:
            print("[tts]", msg)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Pygame mixer — shared across gTTS playback
# ---------------------------------------------------------------------------
_mixer_ready = False
_mixer_lock = threading.Lock()


def _ensure_mixer() -> bool:
    """Initialize pygame.mixer once (safe to call repeatedly)."""
    global _mixer_ready
    if _mixer_ready:
        return True
    with _mixer_lock:
        if _mixer_ready:
            return True
        try:
            import pygame.mixer
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=2048)
            _mixer_ready = True
            _dbg("pygame.mixer initialized for gTTS playback")
            return True
        except Exception as e:
            _dbg(f"pygame.mixer init failed: {e}")
            return False


# ---------------------------------------------------------------------------
# gTTS (Google Text-to-Speech) — natural human voice
# ---------------------------------------------------------------------------

def _gtts_cache_path(text: str) -> Path:
    """Return a deterministic cache file path for *text*."""
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return _CACHE_DIR / f"{key}.mp3"


def _say_gtts(text: str, interrupt: bool = False) -> bool:
    """Generate speech with gTTS → cache MP3 → play via pygame.mixer."""
    if not text.strip():
        return False
    try:
        from gtts import gTTS
    except ImportError:
        _dbg("gTTS not installed")
        return False

    if not _ensure_mixer():
        return False

    import pygame.mixer

    # Stop current playback when interrupting
    if interrupt:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    cache_file = _gtts_cache_path(text)

    # Generate and cache if not already on disk
    if not cache_file.exists():
        try:
            tts_obj = gTTS(text=text, lang="en", slow=False)
            buf = io.BytesIO()
            tts_obj.write_to_fp(buf)
            buf.seek(0)
            cache_file.write_bytes(buf.read())
            _dbg(f"gTTS cached: {cache_file.name}")
        except Exception as e:
            _dbg(f"gTTS generation failed: {e}")
            return False

    # Play the cached file (non-blocking)
    try:
        pygame.mixer.music.load(str(cache_file))
        pygame.mixer.music.play()
        _dbg(f"gTTS started: {text[:40]}")
        return True
    except Exception as e:
        _dbg(f"gTTS playback failed: {e}")
        return False


# ---------------------------------------------------------------------------
# pyttsx3 offline fallback
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Windows SAPI offline fallback
# ---------------------------------------------------------------------------
_sapi_voice = None


def _get_sapi_voice():
    """Return a shared SAPI voice instance (initialized once)."""
    global _sapi_voice
    if _sapi_voice is not None:
        return _sapi_voice

    try:
        import pythoncom
        import win32com.client

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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
_forced_backend = (os.getenv("TTS_BACKEND") or "").strip().lower()


def speak(text: str) -> None:
    """Speak text (non-interrupting)."""
    if _forced_backend == "sapi":
        if _say_sapi(text, interrupt=False):
            return
    elif _forced_backend == "pyttsx3":
        if _say_pyttsx3(text, interrupt=False):
            return
    else:
        # Natural voice first, then offline fallbacks
        if _say_gtts(text, interrupt=False):
            return
        if sys.platform.startswith("win") and _say_sapi(text, interrupt=False):
            return
        if _say_pyttsx3(text, interrupt=False):
            return
        if sys.platform == "darwin" and _say_mac(text):
            return

    print(text)


def speak_interrupt(text: str) -> None:
    """Speak text immediately, stopping any existing speech."""
    # Stop all possible TTS backends to prevent overlapping voices
    
    # Stop gTTS (pygame mixer)
    if _mixer_ready:
        try:
            import pygame.mixer
            pygame.mixer.music.stop()
        except Exception:
            pass
    
    # Stop SAPI
    try:
        voice = _get_sapi_voice()
        if voice is not None:
            voice.Speak("", 3)  # 3 = SVSFPurgeStream
    except Exception:
        pass
    
    # Stop pyttsx3
    try:
        engine = _get_engine()
        if engine is not None:
            engine.stop()
    except Exception:
        pass

    if _forced_backend == "sapi":
        if _say_sapi(text, interrupt=True):
            return
    elif _forced_backend == "pyttsx3":
        if _say_pyttsx3(text, interrupt=True):
            return
    else:
        if _say_gtts(text, interrupt=True):
            return
        if sys.platform.startswith("win") and _say_sapi(text, interrupt=True):
            return
        if _say_pyttsx3(text, interrupt=True):
            return
        if sys.platform == "darwin" and _say_mac(text):
            return

    print(text)


def stop() -> None:
    """Stop any ongoing speech from all backends."""
    # Stop gTTS
    if _mixer_ready:
        try:
            import pygame.mixer
            pygame.mixer.music.stop()
        except Exception:
            pass
    
    # Stop SAPI
    try:
        voice = _get_sapi_voice()
        if voice is not None:
            voice.Speak("", 3)  # 3 = SVSFPurgeStream
    except Exception:
        pass
    
    # Stop pyttsx3
    try:
        engine = _get_engine()
        if engine is not None:
            engine.stop()
    except Exception:
        pass


if __name__ == "__main__":
    speak("Text-to-speech helper installed and working.")
