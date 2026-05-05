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
APP_BG = "#eaf4ff"          # light sky backdrop for the full launcher
APP_PANEL = "#ffffff"       # main panel surface
APP_PANEL_ALT = "#dcecff"   # brighter panel used for sidebars and callouts
APP_PANEL_RAISED = "#c8dcfb"  # raised cards and list rows

# --- Border and text colors ---
APP_BORDER = "#55b7e8"      # bright blue outline used for frames and focus areas
APP_TEXT = "#17324f"        # dark text for light surfaces
APP_MUTED = "#47627f"       # softer body text

# --- Accent (interactive element) colors ---
APP_ACCENT = "#ff5d8f"          # candy-pink primary accent
APP_ACCENT_STRONG = "#ff7a45"   # orange hover / active accent
APP_ACCENT_SOFT = "#9bc3ef"     # quieter accent for idle controls
APP_ACCENT_GLOW = "#ffd166"     # gold used for fun highlights and badges

# --- Keyboard focus indicator ---
APP_FOCUS = "#ffe66d"       # bright yellow outline shown on the focused element

# --- Button-specific colors ---
APP_BUTTON = APP_ACCENT             # default button fill
APP_BUTTON_HOVER = APP_ACCENT_STRONG  # button fill when the mouse is over it
APP_BUTTON_TEXT = "#fff8f1"         # warm white text on all buttons

# --- Entry field color ---
APP_ENTRY_BG = "#f8fbff"    # light text-box background for contrast

# --- Table / list row highlight ---
APP_ROW_HIGHLIGHT = "#b9d7ff"  # cool blue used to highlight featured rows

# --- Fixed sizes ---
APP_BUTTON_H = 46           # height in pixels for all standard buttons
APP_FONT_FAMILY = "Trebuchet MS"    # playful, readable font used throughout


def _font(size: int, bold: bool = False) -> ctk.CTkFont:
    # only use bold when size is large (headings); body text stays normal weight
    weight = "bold" if (bold and size >= 24) else "normal"
    return ctk.CTkFont(family=APP_FONT_FAMILY, size=size, weight=weight)
