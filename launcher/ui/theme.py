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
APP_BG = "#f4f7fb"            # soft cool background with strong readability
APP_PANEL = "#ffffff"         # primary panel surface
APP_PANEL_ALT = "#eaf2ff"     # secondary panel surface
APP_PANEL_RAISED = "#fff4e0"  # raised cards and featured rows

# --- Border and text colors ---
APP_BORDER = "#2d5f99"        # deeper blue outline for better contrast on light surfaces
APP_TEXT = "#1c2d4a"          # dark text for light surfaces
APP_MUTED = "#3b4f6b"         # muted text that still meets readability targets

# --- Accent (interactive element) colors ---
APP_ACCENT = "#b04a2b"          # primary accent tuned for readable button text
APP_ACCENT_STRONG = "#8a351f"   # darker hover / active accent for better contrast
APP_ACCENT_SOFT = "#6eb4e6"     # lighter blue for idle controls
APP_ACCENT_GLOW = "#f1c04a"     # gold used for highlights and badges

# --- Keyboard focus indicator ---
APP_FOCUS = "#2457c5"         # strong blue outline shown on the focused element

# --- Button-specific colors ---
APP_BUTTON = APP_ACCENT             # default button fill
APP_BUTTON_HOVER = APP_ACCENT_STRONG  # button fill when the mouse is over it
APP_BUTTON_TEXT = "#fffdf8"           # warm white text with strong contrast on accent buttons

# --- Entry field color ---
APP_ENTRY_BG = "#ffffff"      # light text-box background for contrast

# --- Table / list row highlight ---
APP_ROW_HIGHLIGHT = "#ffe3a8"  # warm gold used to highlight featured rows

# --- Fixed sizes ---
APP_BUTTON_H = 56             # height in pixels for all standard buttons
APP_FONT_FAMILY = "Trebuchet MS"    # playful, readable font used throughout


def _font(size: int, bold: bool = False) -> ctk.CTkFont:
    # enforce an accessible minimum text size for low-vision readability
    clamped_size = max(14, size)
    # allow bold headings and controls while keeping body copy stable
    weight = "bold" if (bold and clamped_size >= 14) else "normal"
    return ctk.CTkFont(family=APP_FONT_FAMILY, size=clamped_size, weight=weight)
