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
APP_BG = "#f6f7ff"            # soft lavender-white backdrop for the full launcher
APP_PANEL = "#fffdf8"         # warm bright panel surface
APP_PANEL_ALT = "#e5f3ff"     # playful sky panel used for sidebars and callouts
APP_PANEL_RAISED = "#fff1d6"  # raised cards and featured rows

# --- Border and text colors ---
APP_BORDER = "#4f8fd8"        # vivid blue outline used for frames and focus areas
APP_TEXT = "#1c2d4a"          # dark text for light surfaces
APP_MUTED = "#50637f"         # softer body text

# --- Accent (interactive element) colors ---
APP_ACCENT = "#ff7a59"          # arcade coral primary accent
APP_ACCENT_STRONG = "#ff9f43"   # sunny orange hover / active accent
APP_ACCENT_SOFT = "#7cc7ff"     # lighter blue for idle controls
APP_ACCENT_GLOW = "#ffd76a"     # gold used for highlights and badges

# --- Keyboard focus indicator ---
APP_FOCUS = "#2457c5"         # strong blue outline shown on the focused element

# --- Button-specific colors ---
APP_BUTTON = APP_ACCENT             # default button fill
APP_BUTTON_HOVER = APP_ACCENT_STRONG  # button fill when the mouse is over it
APP_BUTTON_TEXT = "#fffdf8"           # warm white text on all buttons

# --- Entry field color ---
APP_ENTRY_BG = "#ffffff"      # light text-box background for contrast

# --- Table / list row highlight ---
APP_ROW_HIGHLIGHT = "#ffe3a8"  # warm gold used to highlight featured rows

# --- Fixed sizes ---
APP_BUTTON_H = 50             # height in pixels for all standard buttons
APP_FONT_FAMILY = "Trebuchet MS"    # playful, readable font used throughout


def _font(size: int, bold: bool = False) -> ctk.CTkFont:
    # only use bold when size is large (headings); body text stays normal weight
    weight = "bold" if (bold and size >= 24) else "normal"
    return ctk.CTkFont(family=APP_FONT_FAMILY, size=size, weight=weight)
