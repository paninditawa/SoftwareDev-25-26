"""
NavigationMixin for the HelloWorld GameSpace launcher.

This mixin handles all keyboard-driven navigation for the main menu
screen and the login screen.  Key concepts:

  nav_mode — when True, arrow keys move between left-column page buttons;
              when False, arrow keys move between right-column action buttons.
  action_index / action_buttons — track the currently highlighted button
              in the right-column action panel.
  show_menu() — builds the two-column (nav + details) layout and wires
              up every page button.
  select_page() — switches the active page, refreshes the action panel,
              and announces the page title (announcement happens once per navigation).
"""
from __future__ import annotations

# Low-level tkinter for widget type checking
import tkinter as tk

# Styled UI components
import customtkinter as ctk

# Color constants for drawing nav-button highlight borders
from launcher.ui.theme import (
    APP_ACCENT,
    APP_ACCENT_SOFT,
    APP_ACCENT_STRONG,
    APP_BORDER,
    APP_FOCUS,
    APP_MUTED,
    APP_PANEL,
    APP_PANEL_ALT,
    APP_TEXT,
    _font,
)


# All navigation helpers live inside this one mixin class.
class NavigationMixin:
    def _handle_pane_cycle(self, _delta: int):
        # Tab/Shift-Tab with no modifier: cycle between the left nav pane and the right action pane.
        if self.current_screen != "menu":
            return None

        focus = self.focus_get()
        in_nav_pane = focus in self.nav_buttons.values()

        if in_nav_pane:
            # Currently in the nav pane; try moving to the first interactive item on the right.
            if self._focus_first_action_target():
                return "break"
            self.speech.announce("No interactive controls are available in the details pane.", interrupt=True, force=True)
            return "break"

        # Currently on the right side; jump back to the nav pane.
        self.nav_mode = True
        self._sync_keyboard_focus()
        return "break"

    def _handle_left(self, _event=None):
        # Left arrow: on the login screen, decrease the speed slider if it is focused.
        if self.current_screen == "login":
            try:
                if self.login_focus_order[self.login_focus_index] is self._speed_slider:
                    return self._adjust_speed_slider(-1)
            except (AttributeError, IndexError):
                pass
            return None
        # Left arrow: switch to nav_mode (left column).
        if self.current_screen != "menu":
            return None
        if self._is_text_entry(self.focus_get()):
            if self.current_page_key == "apples":
                self.nav_mode = True
                self._sync_keyboard_focus()
                return "break"
            return None
        self.nav_mode = True
        self._sync_keyboard_focus()
        return "break"

    def _handle_right(self, _event=None):
        # Right arrow: on the login screen, increase the speed slider if it is focused.
        if self.current_screen == "login":
            try:
                if self.login_focus_order[self.login_focus_index] is self._speed_slider:
                    return self._adjust_speed_slider(1)
            except (AttributeError, IndexError):
                pass
            return None
        # Right arrow: move focus to the action panel (right column) if any interactive targets exist.
        if self.current_screen != "menu":
            return None
        if self._is_text_entry(self.focus_get()):
            return None
        if self._focus_first_action_target():
            return "break"
        self.speech.announce("No action buttons on this page.", interrupt=True, force=True)
        return "break"

    def _handle_activate(self, _event=None):
        # Space or Enter: activate the currently focused button on either screen.
        if self.current_screen == "menu":
            if self.nav_mode:
                # In the nav pane: pressing Enter/Space jumps to the action buttons.
                if self.action_buttons:
                    self.nav_mode = False
                    self.action_index = 0
                    self._sync_keyboard_focus()
                else:
                    self.speech.announce("No action buttons on this page.", interrupt=True, force=True)
                return "break"
            if self._is_text_entry(self.focus_get()):
                return None
            if self.action_buttons:
                # In the action pane: invoke the highlighted action button.
                self.action_buttons[self.action_index].invoke()
                return "break"
            return "break"

        if self.current_screen == "login":
            # On the login screen: invoke the focused button or fall back to the tracked index.
            widget = self.focus_get()
            if hasattr(widget, "invoke") and not self._is_text_entry(widget):
                widget.invoke()
                return "break"
            if self.login_action_buttons:
                self.login_action_buttons[self.login_action_index].invoke()
                return "break"
            return "break"

        # Any other screen: invoke the focused widget if it has an invoke method.
        widget = self.focus_get()
        if hasattr(widget, "invoke") and not self._is_text_entry(widget):
            widget.invoke()
            return "break"
        return None

    def _handle_vertical(self, delta: int):
        # Up/Down arrows: navigate the current screen's focusable items.
        if self.current_screen == "login":
            self._move_login_focus_by(delta)
            return "break"
        if self.current_screen != "menu":
            return None
        if self._is_text_entry(self.focus_get()):
            if self.current_page_key in {"apples", "battleship"}:
                return self._move_action_selection(delta)
            return None
        if self.nav_mode:
            return self._move_menu_selection(delta)
        return self._move_action_selection(delta)

    def _is_text_entry(self, widget) -> bool:
        # Return True if the widget is a text input (standard Entry or customtkinter variant).
        if widget is None:
            return False
        try:
            return (
                isinstance(widget, tk.Entry)
                or isinstance(widget, ctk.CTkEntry)
                or widget.winfo_class() in {"Entry", "TEntry", "CTkEntry"}
            )
        except Exception:
            return False

    def _move_menu_selection(self, delta: int):
        # Move the highlight in the left-column page list and load the new page.
        if self.current_screen != "menu":
            return None
        if self._is_text_entry(self.focus_get()):
            return None
        current_index = self.menu_order.index(self.current_page_key)
        new_index = (current_index + delta) % len(self.menu_order)
        new_key = self.menu_order[new_index]
        self.nav_index = new_index
        # Pass announce=False: _sync_keyboard_focus below makes the single announcement.
        self.select_page(new_key, announce=False)
        self.nav_mode = True
        self._sync_keyboard_focus()
        return "break"

    def _move_action_selection(self, delta: int):
        # Move the highlight among the right-column action controls.
        targets = [
            widget
            for widget in self.action_widgets
            if widget is not None and (self._is_text_entry(widget) or hasattr(widget, "invoke"))
        ]
        if not targets:
            self.speech.announce("No action controls on this page.", interrupt=True, force=True)
            return "break"
        if len(targets) <= 1:
            # Only one interactive item — fall back to the nav pane instead of cycling endlessly.
            self.nav_mode = True
            return self._move_menu_selection(delta)

        focus = self.focus_get()
        if focus in targets:
            current_index = targets.index(focus)
        elif self._is_text_entry(focus):
            current_index = next((i for i, widget in enumerate(targets) if self._is_text_entry(widget)), 0)
        elif self.action_buttons and self.action_buttons[self.action_index] in targets:
            current_index = targets.index(self.action_buttons[self.action_index])
        else:
            current_index = 0

        next_index = (current_index + delta) % len(targets)
        target = targets[next_index]

        if self._is_text_entry(target):
            try:
                target.focus_force()
            except Exception:
                target.focus_set()
            return "break"

        if target in self.action_buttons:
            self.action_index = self.action_buttons.index(target)
        self.nav_mode = False
        self._sync_keyboard_focus()
        return "break"

    def _focus_first_action_target(self) -> bool:
        # Find the first enabled interactive widget in the action area and focus it.
        for widget in self.action_widgets:
            if widget is None:
                continue
            try:
                if not widget.winfo_exists():
                    continue
            except Exception:
                continue

            if self._is_text_entry(widget):
                self.nav_mode = False
                self.action_index = 0
                try:
                    widget.focus_force()
                except Exception:
                    widget.focus_set()
                return True

            if hasattr(widget, "invoke"):
                try:
                    if str(widget.cget("state")) == "disabled":
                        continue  # skip disabled buttons
                except Exception:
                    pass
                if widget in self.action_buttons:
                    self.nav_mode = False
                    self.action_index = self.action_buttons.index(widget)
                    self._sync_keyboard_focus()
                else:
                    self.nav_mode = False
                    widget.focus_set()
                return True

        return False

    def _style_nav_button(self, key: str, button: ctk.CTkButton) -> None:
        # Draw a stronger highlight on the nav button that is both selected AND has keyboard cursor.
        selected = key == self.current_page_key
        keyboard_cursor = self.nav_mode and selected
        if keyboard_cursor:
            button.configure(fg_color=APP_ACCENT_STRONG, border_width=3, border_color=APP_FOCUS)
        elif selected:
            button.configure(fg_color=APP_ACCENT, border_width=2, border_color=APP_BORDER)
        else:
            button.configure(fg_color=(APP_ACCENT_SOFT, APP_ACCENT), border_width=1, border_color=APP_BORDER)

    def _style_action_buttons(self) -> None:
        # Draw a highlight border on the currently focused action button.
        for index, button in enumerate(self.action_buttons):
            keyboard_cursor = (not self.nav_mode) and index == self.action_index
            if keyboard_cursor:
                button.configure(border_width=3, border_color=APP_FOCUS)
            else:
                button.configure(border_width=1, border_color=APP_BORDER)

    def _sync_keyboard_focus(self) -> None:
        # Restyle all buttons and move OS focus to whichever item is currently active.
        if self.current_screen != "menu":
            return
        for key, button in self.nav_buttons.items():
            self._style_nav_button(key, button)
        self._style_action_buttons()
        if self.nav_mode:
            # Focus belongs in the nav pane; announce the current page title.
            button = self.nav_buttons.get(self.current_page_key)
            if button is not None:
                button.focus_set()
                self.speech.set_focus(self.page_meta[self.current_page_key]["title"], self.page_meta[self.current_page_key]["hint"])
            return
        if self.action_buttons:
            # Focus belongs in the action pane; announce the highlighted button.
            button = self.action_buttons[self.action_index]
            button.focus_set()
            text = button.cget("text")
            self.speech.set_focus(text, "Press Enter to activate.")

    def show_menu(self) -> None:
        # Build the two-column main menu layout after a successful login.
        self.current_screen = "menu"
        self._clear_content()
        if self.auth_session is None:
            # Should not happen normally, but fall back to login if session was lost.
            self.show_login()
            return

        # Default to the home page if the last remembered page no longer exists.
        if self.current_page_key not in self.menu_order:
            self.current_page_key = "home"

        # Root frame: two columns — left nav pane (fixed width) + right details pane (expands).
        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.pack(fill="both", expand=True)
        root.grid_columnconfigure(0, weight=0)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)

        # Left navigation panel.
        nav = ctk.CTkFrame(root, width=320, **self._surface_style_kwargs())
        nav.grid(row=0, column=0, sticky="nsw", padx=(18, 10), pady=18)
        nav.grid_propagate(False)

        # Right details panel.
        details = ctk.CTkFrame(root, fg_color=APP_PANEL, corner_radius=22, border_width=2, border_color=APP_BORDER)
        details.grid(row=0, column=1, sticky="nsew", padx=(10, 18), pady=18)
        details.grid_columnconfigure(0, weight=1)
        details.grid_rowconfigure(2, weight=1)

        # Welcome message at the top of the nav panel.
        mode_prefix = "Signed in as"
        display_name = self.auth_session.username or self.auth_session.email
        welcome = ctk.CTkLabel(nav, text=f"{mode_prefix} {display_name}", wraplength=250, justify="left", text_color=APP_TEXT, font=_font(18, bold=True))
        welcome.pack(anchor="w", padx=16, pady=(16, 10))

        # Short navigation hint beneath the welcome label.
        nav_text = "Use Up/Down arrows to change pages. Press Left/Right arrows to move between the page list and the details pane."
        self._nav_help_label = ctk.CTkLabel(nav, text=nav_text, justify="left", wraplength=250, text_color=APP_MUTED, font=_font(15, bold=True))
        self._nav_help_label.pack(anchor="w", padx=16, pady=(0, 12))

        ctk.CTkLabel(
            nav,
            text="GAME SELECT",
            text_color=APP_FOCUS,
            font=_font(14, bold=True),
        ).pack(anchor="w", padx=16, pady=(4, 8))

        # Create one nav button per page and register it in the nav_buttons dictionary.
        for key in self.menu_order:
            title = self.page_meta[key]["title"]
            button = ctk.CTkButton(nav, text=title, anchor="w", command=lambda page=key: self.select_page(page, announce=True), **self._button_style_kwargs())
            button.pack(fill="x", padx=16, pady=4)
            self.speech.bind_focus(button, title, self.page_meta[key]["hint"])
            self._bind_tab_aliases(button)
            self.nav_buttons[key] = button

        # Page title and description labels inside the details pane.
        self.detail_title = ctk.CTkLabel(details, text="", text_color=APP_TEXT, font=_font(28, bold=True))
        self.detail_title.grid(row=0, column=0, sticky="w", padx=24, pady=(24, 8))

        self.detail_body = ctk.CTkLabel(details, text="", wraplength=self._content_wraplength, justify="left", anchor="w", text_color=APP_MUTED, font=_font(16, bold=True))
        self.detail_body.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))

        # Scrollable frame where game-specific action buttons and inputs are shown.
        self.action_frame = ctk.CTkScrollableFrame(details, fg_color=APP_PANEL_ALT, corner_radius=18, border_width=1, border_color=APP_BORDER)
        self.action_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self.action_frame.grid_columnconfigure(0, weight=1)

        # Load the last page (or home) and then sync focus after a short delay.
        self.select_page(self.current_page_key, announce=False)
        self.after(150, self._sync_keyboard_focus)
        self.speech.set_screen(
            "Main menu",
            "Use Up and Down arrows to choose a page. Press Right Arrow or Enter to activate. Press Left Arrow to go back.",
        )
        self._update_wraplengths()

    def select_page(self, page_key: str, announce: bool = True) -> None:
        # Switch the active page: update the nav-button styles, detail labels, and action panel.
        if page_key not in self.page_meta:
            return
        self.current_page_key = page_key
        for key, button in self.nav_buttons.items():
            self._style_nav_button(key, button)
        meta = self.page_meta[page_key]
        self.detail_title.configure(text=meta["title"])
        self.detail_body.configure(text=meta["description"])
        # Rebuild the right-hand action panel for the new page.
        self._render_actions(page_key)
        self._sync_keyboard_focus()
        if announce:
            self.speech.set_focus(meta["title"], meta["hint"])
