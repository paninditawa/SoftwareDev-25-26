"""Shared visual theme for all pygame games.

Keeps game colors and typography aligned with the launcher so the
experience feels consistent across Hangman, Escape Room, Mad Libs,
Maze, and Connect 4.
"""

from __future__ import annotations


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


# Matches launcher/ui/theme.py palette.
GAME_BG = _hex_to_rgb("#f4f7fb")
GAME_PANEL = _hex_to_rgb("#ffffff")
GAME_PANEL_ALT = _hex_to_rgb("#eaf2ff")
GAME_BORDER = _hex_to_rgb("#2d5f99")
GAME_TEXT = _hex_to_rgb("#1c2d4a")
GAME_MUTED = _hex_to_rgb("#3b4f6b")
GAME_ACCENT = _hex_to_rgb("#b04a2b")
GAME_ACCENT_STRONG = _hex_to_rgb("#8a351f")
GAME_FOCUS = _hex_to_rgb("#2457c5")
GAME_GLOW = _hex_to_rgb("#f1c04a")

# Default font family used by launcher theme.
GAME_FONT_FAMILY = "trebuchetms"
