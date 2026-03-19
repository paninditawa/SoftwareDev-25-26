"""Speech and focus announcements for the launcher UI.

This module uses the project's required `tts` helper for spoken output and
tracks screen/focus context so announcements are useful to keyboard users.
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

# import text-to-speech functions from the required project helper
from tts import speak as _tts_speak
from tts import speak_interrupt as _tts_speak_interrupt


# SpeechManager manages spoken announcements for app
class SpeechManager:

    # create speech manager; on_announce is optional callback
    def __init__(self, on_announce: Callable[[str], None] | None = None) -> None:
        # callback function (if one was provided)
        self.on_announce = on_announce
        # start w voice output on
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

    # repeat last spoken message, if any exists
    def repeat_last(self) -> None:
        # only repeat if there's a prev message
        if self.last_message:
            self.announce(self.last_message, interrupt=True, force=True)

    # say where user is: screen, summary, + focused control
    def where_am_i(self) -> None:
        # collect context pieces into list
        parts = []
        # add screen title if known
        if self.current_screen:
            parts.append(self.current_screen)
        # add screen summary if known
        if self.current_summary:
            parts.append(self.current_summary)
        # add focused control info if known
        if self.current_focus:
            parts.append(f"Focused on {self.current_focus}")
        # join parts into one sentence, or use default message
        message = ". ".join(parts) if parts else "No current context available."
        # speak location / context message immediately
        self.announce(message, interrupt=True, force=True)

    # attach focus behavior to UI widget so focus is announced
    def bind_focus(self, widget, label: str, hint: str = "") -> None:
        # run whenever widget gains keyboard focus
        def _on_focus(_event=None) -> None:
            # announce label + hint for focused widget
            self.set_focus(label, hint)

        # register focus handler a+ keep any existing handlers too
        widget.bind("<FocusIn>", _on_focus, add="+")
