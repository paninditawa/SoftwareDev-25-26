"""
LoginMixin for the HelloWorld GameSpace launcher.

This mixin manages the login/sign-up screen that appears before the main
menu.  It handles:
  - Rendering the sign-in card with email, password, and username fields.
  - Keyboard-driven focus order (Up/Down arrows cycle through all fields
    and buttons).
  - Calling the AuthClient to sign in or create an account.
  - Handing control back to NavigationMixin's show_menu() on success.
"""
from __future__ import annotations

# Standard-library tkinter for low-level widget types and error dialogs
import tkinter as tk
from tkinter import TclError, messagebox

# Third-party customtkinter for styled UI components
import customtkinter as ctk

# Authentication error type (raised by AuthClient on failure)
from launcher.services.auth_client import AuthError
# Color constants and font helper
from launcher.ui.theme import (
    APP_BORDER,
    APP_BUTTON,
    APP_BUTTON_H,
    APP_BUTTON_HOVER,
    APP_BUTTON_TEXT,
    APP_ENTRY_BG,
    APP_FOCUS,
    APP_MUTED,
    APP_PANEL,
    APP_TEXT,
    _font,
)


# All login-screen helpers live inside this mixin.
class LoginMixin:
    def _move_login_action_selection(self, delta: int):
        # Shift the highlighted action button by delta (-1 or +1) and sync the border.
        if not self.login_action_buttons:
            return "break"
        self.login_action_index = (self.login_action_index + delta) % len(self.login_action_buttons)
        self._sync_login_focus()
        return "break"

    def _move_login_focus_by(self, delta: int) -> None:
        # Cycle keyboard focus across the full login_focus_order list (fields + buttons).
        if not self.login_focus_order:
            return
        self.login_focus_index = (self.login_focus_index + delta) % len(self.login_focus_order)
        self._apply_login_widget_focus(self.login_focus_order[self.login_focus_index])

    def _move_to_login_focus(self, index: int) -> None:
        # Jump to a specific position in the focus order (used on initial load).
        if not self.login_focus_order:
            return
        self.login_focus_index = index % len(self.login_focus_order)
        self._apply_login_widget_focus(self.login_focus_order[self.login_focus_index])

    def _apply_login_widget_focus(self, widget: tk.Widget) -> None:
        # Give focus to one widget and announce it; behaviour differs for text entries vs buttons.
        self._style_login_buttons()
        if self._is_text_entry(widget):
            # Move the cursor into to text field and announce its label.
            try:
                widget.focus_force()
            except Exception:
                widget.focus_set()
            try:
                widget.icursor("end")
            except Exception:
                pass
            field_labels: dict[str, tuple[str, str]] = {
                "username": ("Username field", "Type a username when creating a new account."),
                "email": ("Email field", "Type your account email address."),
                "password": ("Password field", "Type your password."),
            }
            for name, entry in self.login_entries.items():
                if entry is widget:
                    lbl, hint = field_labels.get(name, (name + " field", ""))
                    self.speech.set_focus(lbl, hint)
                    break
        else:
            # It is a button — update the action-button index and announce the button label.
            try:
                btn_idx = self.login_action_buttons.index(widget)
                self.login_action_index = btn_idx
            except ValueError:
                pass
            widget.focus_set()
            try:
                self.speech.set_focus(widget.cget("text"), "Press Enter to activate.")
            except Exception:
                pass

    def _register_login_button(self, button: ctk.CTkButton, label: str, hint: str) -> None:
        # Register a button with speech feedback and track which action-button it is.
        self.speech.bind_focus(button, label, hint)
        self._bind_tab_aliases(button)
        self.login_action_buttons.append(button)

        # Whenever this button gains focus, keep the tracking index in sync.
        def _on_focus(_event=None):
            try:
                self.login_action_index = self.login_action_buttons.index(button)
            except ValueError:
                return
            try:
                self.login_focus_index = self.login_focus_order.index(button)
            except (ValueError, AttributeError):
                pass
            self._style_login_buttons()

        button.bind("<FocusIn>", _on_focus, add="+")

    def _style_login_buttons(self) -> None:
        # Draw a highlight border on whichever button currently has keyboard focus.
        focused_widget = self.login_focus_order[self.login_focus_index] if self.login_focus_order else None
        for button in self.login_action_buttons:
            if button is focused_widget:
                button.configure(border_width=3, border_color=APP_FOCUS)
            else:
                button.configure(border_width=0)

    def _sync_login_focus(self) -> None:
        # Move OS focus to the correct action button and announce it.
        if self.current_screen != "login" or not self.login_action_buttons:
            return
        button = self.login_action_buttons[self.login_action_index]
        try:
            self.login_focus_index = self.login_focus_order.index(button)
        except (ValueError, AttributeError):
            pass
        self._style_login_buttons()
        button.focus_set()
        self.speech.set_focus(button.cget("text"), "Press Enter to activate.")

    def _focus_login_entry(self, field_name: str, select_all: bool = False) -> None:
        # Move focus to a named entry field (used after validation errors).
        entry = self.login_entries.get(field_name)
        if entry is None:
            return
        try:
            entry.focus_force()
        except Exception:
            entry.focus_set()
        if select_all:
            try:
                entry.select_range(0, "end")
            except Exception:
                pass
        entry.icursor("end")

    def show_login(self) -> None:
        # Build and display the login card; reset all per-screen tracking state first.
        self.current_screen = "login"
        self._clear_content()
        self.login_entries = {}
        self.username_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()

        # Center the card vertically inside the content area.
        wrapper = ctk.CTkFrame(self.content, fg_color="transparent")
        wrapper.pack(expand=True)

        # The card is a rounded rectangle that holds all the form elements.
        card = ctk.CTkFrame(wrapper, width=560, fg_color=APP_PANEL, corner_radius=14, border_width=2, border_color=APP_BORDER)
        card.pack(padx=40, pady=40)

        title = ctk.CTkLabel(card, text="Sign In to HelloWorld GameSpace", text_color=APP_TEXT, font=_font(28, bold=True))
        title.pack(anchor="w", padx=24, pady=(24, 8))

        # Brief navigation hint for blind users.
        summary = ctk.CTkLabel(
            card,
            text="Use Up and Down arrows to move between buttons. Username is required when creating a new account.",
            wraplength=460,
            justify="left",
            anchor="w",
            text_color=APP_MUTED,
            font=_font(16, bold=True),
        )
        summary.pack(anchor="w", padx=24, pady=(0, 16))
        self._login_summary_label = summary

        # Build all three input fields in one loop to avoid repetition.
        for field_name, var, label_text, hint, show in [
            ("username", self.username_var, "Username (for new accounts)", "Type a username when creating a new account.", ""),
            ("email", self.email_var, "Email", "Type your account email address.", ""),
            ("password", self.password_var, "Password", "Type your password.", "*"),
        ]:
            ctk.CTkLabel(card, text=label_text, text_color=APP_TEXT, font=_font(15, bold=True)).pack(anchor="w", padx=24)
            entry = ctk.CTkEntry(
                card,
                textvariable=var,
                width=460,
                height=42,
                show=show,  # "*" masks the password field
                fg_color=APP_ENTRY_BG,
                border_color=APP_BORDER,
                text_color=APP_TEXT,
            )
            entry.pack(padx=24, pady=(4, 16))
            self.speech.bind_focus(entry, f"{label_text} field", hint)
            self.login_entries[field_name] = entry

        # Sign In and Create Account sit side by side.
        button_row = ctk.CTkFrame(card, fg_color="transparent")
        button_row.pack(fill="x", padx=24, pady=(0, 12))
        button_row.grid_columnconfigure((0, 1), weight=1)

        sign_in_button = ctk.CTkButton(button_row, text="Sign In", command=self._sign_in, **self._button_style_kwargs())
        sign_in_button.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self._register_login_button(sign_in_button, "Sign In button", "Activate to sign in.")

        create_button = ctk.CTkButton(button_row, text="Create Account", command=self._sign_up, **self._button_style_kwargs())
        create_button.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        self._register_login_button(create_button, "Create Account button", "Activate to create a new account.")

        help_button = ctk.CTkButton(card, text="Read Login Help", command=self._handle_help, **self._button_style_kwargs())
        help_button.pack(padx=24, pady=(0, 24), fill="x")
        self._register_login_button(help_button, "Read Login Help button", "Activate to hear login instructions.")

        # Focus order: email → password → Sign In → Create → Help → username (at the end because it is rarely needed).
        self.login_focus_order = [
            self.login_entries["email"],
            self.login_entries["password"],
            sign_in_button,
            create_button,
            help_button,
            self.login_entries["username"],
        ]
        self.login_focus_index = 0

        # Keep the focus index in sync whenever the user clicks into a field directly.
        for field_name in ("email", "password", "username"):
            entry = self.login_entries[field_name]

            def _make_entry_focus_handler(e=entry):
                def _handler(_event=None):
                    try:
                        self.login_focus_index = self.login_focus_order.index(e)
                    except (ValueError, AttributeError):
                        pass
                    self._style_login_buttons()

                return _handler

            entry.bind("<FocusIn>", _make_entry_focus_handler(), add="+")

        # Move focus to the email field via three deferred calls so it works regardless of when
        # the window finishes rendering.
        self.after_idle(lambda: self._move_to_login_focus(0))
        self.after(150, lambda: self._move_to_login_focus(0))
        self.after(400, lambda: self._move_to_login_focus(0))
        self.speech.set_screen("Login screen", "Enter email and password. Use Up and Down arrows to navigate between fields and buttons.")

    def _sign_in(self) -> None:
        # Trigger the shared auth action using sign_in mode.
        self._run_auth_action("sign_in")

    def _sign_up(self) -> None:
        # Trigger the shared auth action using sign_up mode.
        self._run_auth_action("sign_up")

    def _run_auth_action(self, action: str) -> None:
        # Read form fields, validate them, then call the AuthClient.
        try:
            username = self.username_var.get().strip()
            email = self.email_var.get().strip()
            password = self.password_var.get()
        except TclError:
            # Variable read can fail if tkinter tore down the widget (rare race condition).
            self.speech.announce("Please try again.", interrupt=True, force=True)
            self.after_idle(self.show_login)
            return
        if not email or not password:
            self.speech.announce("Email and password are required.", interrupt=True, force=True)
            messagebox.showerror("Missing information", "Email and password are required.")
            self.after_idle(lambda: self._focus_login_entry("email" if not email else "password"))
            return
        if len(password) < 6:
            self.speech.announce("Password must be at least 6 characters.", interrupt=True, force=True)
            messagebox.showerror("Password too short", "Password must be at least 6 characters.")
            self.after_idle(lambda: self._focus_login_entry("password"))
            return
        if action == "sign_up" and not username:
            self.speech.announce("Username is required to create an account.", interrupt=True, force=True)
            messagebox.showerror("Missing username", "Username is required to create an account.")
            self.after_idle(lambda: self._focus_login_entry("username"))
            return
        try:
            if action == "sign_in":
                self.auth_session = self.auth_client.sign_in(email, password)
                self.speech.announce("Signed in successfully.", interrupt=True, force=True)
            else:
                self.auth_session = self.auth_client.sign_up(email, password, username=username)
                self.speech.announce("Account created successfully.", interrupt=True, force=True)
        except AuthError as exc:
            # The server rejected the credentials — speak the error and stay on the login screen.
            self.speech.announce(str(exc), interrupt=True, force=True)
            messagebox.showerror("Authentication error", str(exc))
            self.after_idle(lambda: self._focus_login_entry("password" if password else "email"))
            return
        # Auth succeeded — advance to the main menu.
        self.show_menu()
