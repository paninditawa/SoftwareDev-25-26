"""Cross-platform text-to-speech helper.

Usage:
    from tts import speak
    speak("Hello world")

This attempts, in order:
- Windows SAPI via `win32com.client`
- macOS `say` command
- `pyttsx3` fallback
- prints text if no TTS available
"""
import sys
import subprocess


def _sapi_speak(text: str) -> bool:
    try:
        import win32com.client

        win32com.client.Dispatch("SAPI.SpVoice").Speak(text)
        return True
    except Exception:
        return False


def _say_mac(text: str) -> bool:
    try:
        subprocess.run(["say", text], check=False)
        return True
    except Exception:
        return False


def _pyttsx3_speak(text: str) -> bool:
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception:
        return False


def speak(text: str) -> None:
    """Speak text using a platform-appropriate backend.

    This function never raises; if TTS is unavailable it will print the text.
    """
    if sys.platform.startswith("win"):
        if _sapi_speak(text):
            return
    if sys.platform == "darwin":
        if _say_mac(text):
            return
    if _pyttsx3_speak(text):
        return
    # final fallback
    print(text)


if __name__ == "__main__":
    speak("Text-to-speech helper installed and working.")
