"""
accessibility.py is a module that provides a SpeechManager class, which handles text-to-speech announcements for the app, 
including screen changes & focus updates. It uses the tts helper for speech but falls back to print statements if TTS is unavailable. 
SpeechManager can also track the current screen and focused control for context-aware announcements.
"""

# annotations keep type hints as text until Python needs them
from __future__ import annotations

# sys reads + edits Python's import search path
import sys
# Path works w file + folder paths safely
from pathlib import Path
# Callable describes a val as a function that's callable
from typing import Callable

# find project root folder from this file's location
_repo_root = Path(__file__).resolve().parents[1]

# if project root isn't already in Python's search path...
if str(_repo_root) not in sys.path:
    # add it so imports like tts can be found
    sys.path.insert(0, str(_repo_root))

# import text-to-speech functions from project helper
try:
    # normal speech function
    from tts import speak as _tts_speak

    # interrupting speech function (cuts off current speech)
    from tts import speak_interrupt as _tts_speak_interrupt

# if TTS import fails, use print fallbacks
except Exception:
    # fallback function: show text on screen instead of speaking
    def _tts_speak(text: str) -> None:
        print(text)

    # fallback interrupt function: also prints text
    def _tts_speak_interrupt(text: str) -> None:
        print(text)


# SpeechManager manages spoken announcements for app
class SpeechManager:

    # create speech manager; on_announce is optional callback
    def __init__(self, on_announce: Callable[[str], None] | None = None) -> None:
        # callback function (if one was provided)
        self.on_announce = on_announce
        # start w voice output on.
        self.voice_enabled = True
        # remember last message to repeat or avoid dups
        self.last_message = ""
        # track current screen title for context
        self.current_screen = ""
        # track short screen summary for context
        self.current_summary = ""
        # track which control is currently focused
        self.current_focus = ""

    # speak / report message, w options to interrupt + force repeats
    def announce(self, text: str, interrupt: bool = True, force: bool = False) -> None:
        # if no text, do nothing
        if not text:
            return
        # if same as last time + not forced, skip it
        if not force and text == self.last_message:
            return

        # save message as newest message
        self.last_message = text
        # if callback exists, send message to it too
        if self.on_announce:
            self.on_announce(text)

        # if voice is turned off, stop after callback / recording
        if not self.voice_enabled:
            return

        # use interrupting speech when requested
        if interrupt:
            _tts_speak_interrupt(text)
        # else, speak normally
        else:
            _tts_speak(text)

    # set current screen info + announce immediately
    def set_screen(self, title: str, summary: str = "") -> None:
        # save active screen title
        self.current_screen = title
        # save active screen summary
        self.current_summary = summary
        # build one message from title + summary
        message = title if not summary else f"{title}. {summary}"
        # announce even if repeats, because screen changed
        self.announce(message, interrupt=True, force=True)

    # set current focused control info + announce
    def set_focus(self, label: str, hint: str = "") -> None:
        # save currently focused control label
        self.current_focus = label
        # build one message from label + optional hint
        message = label if not hint else f"{label}. {hint}"
        # announce focus immediately + force it to be read
        self.announce(message, interrupt=True, force=True)

    # Repeat the last spoken message, if any exists.
    def repeat_last(self) -> None:
        # Only repeat when we actually have a previous message.
        if self.last_message:
            self.announce(self.last_message, interrupt=True, force=True)

    # Say where the user is: screen, summary, and focused control.
    def where_am_i(self) -> None:
        # Collect context pieces into a list.
        parts = []
        # Add screen title if known.
        if self.current_screen:
            parts.append(self.current_screen)
        # Add screen summary if known.
        if self.current_summary:
            parts.append(self.current_summary)
        # Add focused control info if known.
        if self.current_focus:
            parts.append(f"Focused on {self.current_focus}")
        # Join parts into one sentence, or use a default message.
        message = ". ".join(parts) if parts else "No current context available."
        # Speak the location/context message immediately.
        self.announce(message, interrupt=True, force=True)

    # Attach focus behavior to a UI widget so focus is announced.
    def bind_focus(self, widget, label: str, hint: str = "") -> None:
        # This runs whenever the widget gains keyboard focus.
        def _on_focus(_event=None) -> None:
            # Announce the label and hint for the focused widget.
            self.set_focus(label, hint)

        # Register the focus handler and keep any existing handlers too.
        widget.bind("<FocusIn>", _on_focus, add="+")
