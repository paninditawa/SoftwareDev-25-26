from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:
    from tts import speak as _tts_speak
    from tts import speak_interrupt as _tts_speak_interrupt
except Exception:
    def _tts_speak(text: str) -> None:
        print(text)

    def _tts_speak_interrupt(text: str) -> None:
        print(text)


class SpeechManager:
    def __init__(self, on_announce: Callable[[str], None] | None = None) -> None:
        self.on_announce = on_announce
        self.voice_enabled = True
        self.last_message = ""
        self.current_screen = ""
        self.current_summary = ""
        self.current_focus = ""

    def announce(self, text: str, interrupt: bool = True, force: bool = False) -> None:
        if not text:
            return
        if not force and text == self.last_message:
            return

        self.last_message = text
        if self.on_announce:
            self.on_announce(text)

        if not self.voice_enabled:
            return

        if interrupt:
            _tts_speak_interrupt(text)
        else:
            _tts_speak(text)

    def set_screen(self, title: str, summary: str = "") -> None:
        self.current_screen = title
        self.current_summary = summary
        message = title if not summary else f"{title}. {summary}"
        self.announce(message, interrupt=True, force=True)

    def set_focus(self, label: str, hint: str = "") -> None:
        self.current_focus = label
        message = label if not hint else f"{label}. {hint}"
        self.announce(message, interrupt=True, force=True)

    def repeat_last(self) -> None:
        if self.last_message:
            self.announce(self.last_message, interrupt=True, force=True)

    def where_am_i(self) -> None:
        parts = []
        if self.current_screen:
            parts.append(self.current_screen)
        if self.current_summary:
            parts.append(self.current_summary)
        if self.current_focus:
            parts.append(f"Focused on {self.current_focus}")
        message = ". ".join(parts) if parts else "No current context available."
        self.announce(message, interrupt=True, force=True)

    def bind_focus(self, widget, label: str, hint: str = "") -> None:
        def _on_focus(_event=None) -> None:
            self.set_focus(label, hint)

        widget.bind("<FocusIn>", _on_focus, add="+")
