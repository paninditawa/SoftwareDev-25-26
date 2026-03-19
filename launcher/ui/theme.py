from __future__ import annotations

import customtkinter as ctk

APP_BG = "#f6f8fb"
APP_PANEL = "#ffffff"
APP_PANEL_ALT = "#edf2f7"
APP_BORDER = "#5c7085"
APP_TEXT = "#0f2942"
APP_MUTED = "#27445f"
APP_ACCENT = "#0b5cab"
APP_ACCENT_STRONG = "#084c8d"
APP_ACCENT_SOFT = APP_ACCENT
APP_FOCUS = "#ffd54a"
APP_BUTTON = APP_ACCENT
APP_BUTTON_HOVER = APP_ACCENT_STRONG
APP_BUTTON_TEXT = "#ffffff"
APP_ENTRY_BG = APP_PANEL
APP_ROW_HIGHLIGHT = "#e7f1fa"

APP_BUTTON_H = 44
APP_FONT_FAMILY = "Segoe UI"


def _font(size: int, bold: bool = False) -> ctk.CTkFont:
    """Return the app's standard font, using bold only for larger headings."""
    weight = "bold" if (bold and size >= 24) else "normal"
    return ctk.CTkFont(family=APP_FONT_FAMILY, size=size, weight=weight)
