"""
Visual theme constants for the HelloWorld GameSpace launcher.
All colors, sizes, and font settings live here so they can be
changed in one place and applied across the whole UI automatically.
"""

# annotations keeps type hints as strings until they are needed
from __future__ import annotations

# CTkFont is the customtkinter font class used to style text
import customtkinter as ctk

# --- Background and panel colors ---
APP_BG = "#f6f8fb"          # light grey used as the window background
APP_PANEL = "#ffffff"        # white card/panel surface
APP_PANEL_ALT = "#edf2f7"   # slightly tinted panel for alternate sections

# --- Border and text colors ---
APP_BORDER = "#5c7085"      # muted blue-grey used for outlines
APP_TEXT = "#0f2942"        # dark navy used for main body text
APP_MUTED = "#27445f"       # slightly lighter navy for secondary text

# --- Accent (interactive element) colors ---
APP_ACCENT = "#0b5cab"          # primary blue used on buttons and nav items
APP_ACCENT_STRONG = "#084c8d"   # darker blue shown on hover / selected state
APP_ACCENT_SOFT = APP_ACCENT    # alias kept so callers can request a softer accent

# --- Keyboard focus indicator ---
APP_FOCUS = "#ffd54a"       # bright yellow outline shown on the focused element

# --- Button-specific colors ---
APP_BUTTON = APP_ACCENT             # default button fill
APP_BUTTON_HOVER = APP_ACCENT_STRONG  # button fill when the mouse is over it
APP_BUTTON_TEXT = "#ffffff"         # white text on all buttons

# --- Entry field color ---
APP_ENTRY_BG = APP_PANEL    # text-box background matches the card it sits on

# --- Table / list row highlight ---
APP_ROW_HIGHLIGHT = "#e7f1fa"  # pale blue used to highlight matching rows

# --- Fixed sizes ---
APP_BUTTON_H = 44           # height in pixels for all standard buttons
APP_FONT_FAMILY = "Segoe UI"    # font used throughout the whole app


def _font(size: int, bold: bool = False) -> ctk.CTkFont:
    # only use bold when size is large (headings); body text stays normal weight
    weight = "bold" if (bold and size >= 24) else "normal"
    return ctk.CTkFont(family=APP_FONT_FAMILY, size=size, weight=weight)
