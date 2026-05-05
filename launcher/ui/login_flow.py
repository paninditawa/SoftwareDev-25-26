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
    APP_ACCENT,
    APP_BORDER,
    APP_BUTTON,
    APP_BUTTON_H,
    APP_BUTTON_HOVER,
    APP_BUTTON_TEXT,
    APP_ENTRY_BG,
    APP_FOCUS,
    APP_MUTED,
    APP_PANEL,
    APP_PANEL_ALT,
    APP_TEXT,
    _font,
)
from tts import set_speech_rate, get_speech_rate


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
        # Show the highlight ring when the speed slider is focused; hide it otherwise.
        highlight = getattr(self, "_speed_slider_highlight", None)
        slider_canvas = getattr(getattr(self, "_speed_slider", None), "_canvas", None)
        is_slider = slider_canvas is not None and widget is getattr(self, "_speed_slider", None)
        if highlight is not None:
            highlight.configure(border_color=APP_FOCUS if is_slider else APP_PANEL)
        if is_slider:
            try:
                slider_canvas.focus_force()
            except Exception:
                slider_canvas.focus_set()
            self.speech.set_focus("Voice Speed slider", "Press Left or Right to adjust. Press Down to move to the next item.")
            return
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
        # Move focus to a named entry field in whichever tab is currently active.
        active = getattr(self, "_active_login_tab", None)
        if active == "Sign In":
            entry = self._si_entries.get(field_name)
        elif active == "Create Account":
            entry = self._ca_entries.get(field_name)
        else:
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

    def _bind_entry_key_feedback(self, entry: ctk.CTkEntry) -> None:
        # Speak each character as it is typed (screen-reader-style feedback).
        def _on_key(event) -> None:
            keysym = event.keysym
            if keysym == "BackSpace":
                self.speech.announce("backspace", interrupt=True, force=True)
            elif (
                event.char
                and event.char.isprintable()
                and not keysym.startswith(("Control", "Alt", "Shift", "caps_lock"))
            ):
                char_names = {
                    ".": "dot", "@": "at", "-": "dash", "_": "underscore",
                    "!": "exclamation", "#": "hash", "$": "dollar",
                    "%": "percent", "&": "and", "+": "plus", "=": "equals",
                    " ": "space",
                }
                spoken = char_names.get(event.char, event.char)
                self.speech.announce(spoken, interrupt=True, force=True)
        entry.bind("<KeyRelease>", _on_key, add="+")

    def _switch_login_tab(self, tab_name: str) -> None:
        # Switch the active tab, update display, rebuild focus, and announce.
        self._active_login_tab = tab_name
        self._update_login_tab_display()
        self._rebuild_login_focus_order()
        self.speech.announce(f"{tab_name}.", interrupt=True, force=True)
        self.after(50, lambda: self._move_to_login_focus(2))

    def _update_login_tab_display(self) -> None:
        # Style the tab buttons and show only the active tab's content frame.
        for name, btn in self._tab_buttons.items():
            if name == self._active_login_tab:
                btn.configure(fg_color=APP_ACCENT, text_color=APP_BUTTON_TEXT, border_width=3, border_color=APP_FOCUS)
            else:
                btn.configure(fg_color=APP_PANEL, text_color=APP_MUTED, border_width=2, border_color=APP_BORDER)
        for name, frame in self._tab_frames.items():
            if name == self._active_login_tab:
                frame.pack(fill="both", expand=True, pady=(8, 0))
            else:
                frame.pack_forget()

    def _rebuild_login_focus_order(self) -> None:
        # Set login_focus_order and login_action_buttons based on the active tab.
        active = getattr(self, "_active_login_tab", "Sign In")
        si_btn = self._tab_buttons["Sign In"]
        ca_btn = self._tab_buttons["Create Account"]
        if active == "Sign In":
            entries = [self._si_entries["username"], self._si_entries["password"]]
            action_btn = self._si_button
        else:
            entries = [self._ca_entries["username"], self._ca_entries["email"], self._ca_entries["password"]]
            action_btn = self._ca_button
        self.login_focus_order = [self._speed_slider, si_btn, ca_btn, *entries, action_btn, self._login_help_button]
        self.login_action_buttons = [si_btn, ca_btn, action_btn, self._login_help_button]
        self.login_focus_index = 0
        self.login_action_index = 0

    def show_login(self) -> None:
        # Build and display the login card with Sign In / Create Account tabs.
        # Detach StringVars from existing entry widgets first — otherwise CTkEntry's
        # textvariable trace fires during widget destruction and raises TclError.
        for entry in {**getattr(self, "_si_entries", {}), **getattr(self, "_ca_entries", {})}.values():
            try:
                entry.configure(textvariable="")
            except Exception:
                pass
        self.current_screen = "login"
        self._clear_content()
        self.login_entries = {}

        # Per-tab StringVars — Sign In tab.
        self._si_username_var = tk.StringVar()
        self._si_password_var = tk.StringVar()
        # Per-tab StringVars — Create Account tab.
        self._ca_username_var = tk.StringVar()
        self._ca_email_var = tk.StringVar()
        self._ca_password_var = tk.StringVar()

        # Center the card vertically inside the content area.
        wrapper = ctk.CTkFrame(self.content, fg_color="transparent")
        wrapper.pack(fill="both", expand=True, padx=16, pady=16)

        # The card is a rounded rectangle that holds all the form elements.
        card = ctk.CTkFrame(wrapper, width=600, fg_color=APP_PANEL_ALT, corner_radius=20, border_width=2, border_color=APP_BORDER)
        card.pack(fill="both", expand=True, padx=24, pady=24)

        title = ctk.CTkLabel(card, text="Enter the Arcade", text_color=APP_TEXT, font=_font(30, bold=True))
        title.pack(anchor="w", padx=24, pady=(24, 8))

        # Brief navigation hint for blind users.
        summary = ctk.CTkLabel(
            card,
            text="Use Up and Down arrows to move between fields and buttons. Switch tabs to sign in or create a new player account.",
            wraplength=460,
            justify="left",
            anchor="w",
            text_color=APP_MUTED,
            font=_font(16, bold=True),
        )
        summary.pack(anchor="w", padx=24, pady=(0, 16))
        self._login_summary_label = summary

        # Voice speed slider — first interactive element so users can
        # adjust speech rate before filling in any credentials.
        speed_frame = ctk.CTkFrame(card, fg_color="transparent")
        speed_frame.pack(fill="x", padx=24, pady=(0, 16))

        speed_label = ctk.CTkLabel(speed_frame, text="Voice Speed", text_color=APP_TEXT, font=_font(15, bold=True))
        speed_label.pack(anchor="w")

        self._speed_value_label = ctk.CTkLabel(speed_frame, text=str(get_speech_rate()), text_color=APP_MUTED, font=_font(14))
        self._speed_value_label.pack(anchor="e")

        # Highlight ring shown when the slider has keyboard focus.
        self._speed_slider_highlight = ctk.CTkFrame(
            speed_frame, fg_color="transparent", border_width=3,
            border_color=APP_PANEL, corner_radius=10,
        )
        self._speed_slider_highlight.pack(pady=(4, 0), fill="x")

        self._speed_slider = ctk.CTkSlider(
            self._speed_slider_highlight,
            from_=-10,
            to=10,
            number_of_steps=20,
            command=self._on_speed_slider_change,
        )
        self._speed_slider.set(get_speech_rate())
        self._speed_slider.pack(padx=6, pady=6, fill="x")
        # Ensure the canvas inside CTkSlider routes Left/Right to the adjustment handler,
        # and Up/Down navigate away from the slider instead of being consumed by it.
        self._speed_slider._canvas.bind("<Left>", lambda e: self._adjust_speed_slider(-1), add="+")
        self._speed_slider._canvas.bind("<Right>", lambda e: self._adjust_speed_slider(1), add="+")
        self._speed_slider._canvas.bind("<Up>", lambda e: (self._move_login_focus_by(-1), "break")[1], add="+")
        self._speed_slider._canvas.bind("<Down>", lambda e: (self._move_login_focus_by(1), "break")[1], add="+")
        self._speed_slider._canvas.configure(takefocus=True)
        self._speed_slider._canvas.bind(
            "<FocusIn>",
            lambda e: self._speed_slider_highlight.configure(border_color=APP_FOCUS),
            add="+",
        )
        self._speed_slider._canvas.bind(
            "<FocusOut>",
            lambda e: self._speed_slider_highlight.configure(border_color=APP_PANEL),
            add="+",
        )

        # Custom tab switcher — two large buttons stretching the full card width.
        self._active_login_tab = "Sign In"
        self._tab_buttons: dict[str, ctk.CTkButton] = {}
        self._tab_frames: dict[str, ctk.CTkFrame] = {}

        tab_row = ctk.CTkFrame(card, fg_color="transparent")
        tab_row.pack(fill="x", padx=24, pady=(0, 4))
        tab_row.grid_columnconfigure((0, 1), weight=1)

        si_tab_btn = ctk.CTkButton(
            tab_row, text="Sign In", height=48, font=_font(17, bold=True),
            command=lambda: self._switch_login_tab("Sign In"),
            corner_radius=14,
        )
        si_tab_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._tab_buttons["Sign In"] = si_tab_btn
        self.speech.bind_focus(
            si_tab_btn, "Sign In tab",
            "Press Right arrow to reach the Create Account tab. Press Down arrow to go to the sign in fields.",
        )
        self._bind_tab_aliases(si_tab_btn)
        si_tab_btn.bind("<Right>", lambda e: (self._switch_login_tab("Create Account"), "break")[1], add="+")
        si_tab_btn.bind("<Left>", lambda e: "break", add="+")
        si_tab_btn.bind("<Down>", lambda e: (self._move_to_login_focus(3), "break")[1], add="+")
        si_tab_btn.bind("<Up>", lambda e: (self._move_to_login_focus(0), "break")[1], add="+")

        ca_tab_btn = ctk.CTkButton(
            tab_row, text="Create Account", height=48, font=_font(17, bold=True),
            command=lambda: self._switch_login_tab("Create Account"),
            corner_radius=14,
        )
        ca_tab_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self._tab_buttons["Create Account"] = ca_tab_btn
        self.speech.bind_focus(
            ca_tab_btn, "Create Account tab",
            "Press Left arrow to reach the Sign In tab. Press Down arrow to go to the create account fields.",
        )
        self._bind_tab_aliases(ca_tab_btn)
        ca_tab_btn.bind("<Left>", lambda e: (self._switch_login_tab("Sign In"), "break")[1], add="+")
        ca_tab_btn.bind("<Right>", lambda e: "break", add="+")
        ca_tab_btn.bind("<Down>", lambda e: (self._move_to_login_focus(3), "break")[1], add="+")
        ca_tab_btn.bind("<Up>", lambda e: (self._move_to_login_focus(0), "break")[1], add="+")

        # Content area — one frame per tab, shown/hidden by _update_login_tab_display.
        tab_content = ctk.CTkFrame(
            card,
            fg_color="transparent",
            corner_radius=0,
        )
        tab_content.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        # --- Sign In frame ---
        si_frame = ctk.CTkFrame(tab_content, fg_color="transparent")
        self._tab_frames["Sign In"] = si_frame
        self._si_entries: dict[str, ctk.CTkEntry] = {}
        for field_name, var, label_text, hint, show in [
            ("username", self._si_username_var, "Username", "Type your account username or email address.", ""),
            ("password", self._si_password_var, "Password", "Type your password.", "*"),
        ]:
            ctk.CTkLabel(si_frame, text=label_text, text_color=APP_TEXT, font=_font(15, bold=True)).pack(anchor="w")
            entry = ctk.CTkEntry(
                si_frame,
                textvariable=var,
                width=460,
                show=show,
                **self._entry_style_kwargs(),
            )
            entry.pack(pady=(4, 12), fill="x")
            self.speech.bind_focus(entry, f"{label_text} field", hint)
            self._si_entries[field_name] = entry
            self._bind_entry_key_feedback(entry)

        self._si_button = ctk.CTkButton(si_frame, text="Sign In", command=self._sign_in, **self._button_style_kwargs())
        self._si_button.pack(fill="x", pady=(4, 12))
        self._register_login_button(self._si_button, "Sign In button", "Activate to sign in.")

        # --- Create Account frame ---
        ca_frame = ctk.CTkFrame(tab_content, fg_color="transparent")
        self._tab_frames["Create Account"] = ca_frame
        self._ca_entries: dict[str, ctk.CTkEntry] = {}
        for field_name, var, label_text, hint, show in [
            ("username", self._ca_username_var, "Username", "Type your desired username.", ""),
            ("email", self._ca_email_var, "Email", "Type your account email address.", ""),
            ("password", self._ca_password_var, "Password", "Type your password.", "*"),
        ]:
            ctk.CTkLabel(ca_frame, text=label_text, text_color=APP_TEXT, font=_font(15, bold=True)).pack(anchor="w")
            entry = ctk.CTkEntry(
                ca_frame,
                textvariable=var,
                width=460,
                show=show,
                **self._entry_style_kwargs(),
            )
            entry.pack(pady=(4, 12), fill="x")
            self.speech.bind_focus(entry, f"{label_text} field", hint)
            self._ca_entries[field_name] = entry
            self._bind_entry_key_feedback(entry)

        self._ca_button = ctk.CTkButton(ca_frame, text="Create Account", command=self._sign_up, **self._button_style_kwargs())
        self._ca_button.pack(fill="x", pady=(4, 12))
        self._register_login_button(self._ca_button, "Create Account button", "Activate to create a new account.")

        # Apply initial tab display (Sign In active, Create Account hidden).
        self._update_login_tab_display()

        # Help button sits below the tab view, always visible.
        self._login_help_button = ctk.CTkButton(card, text="Read Login Help", command=self._handle_help, **self._button_style_kwargs())
        self._login_help_button.pack(padx=24, pady=(0, 16), fill="x")
        self._register_login_button(self._login_help_button, "Read Login Help button", "Activate to hear login instructions.")

        # Build the initial focus order for the Sign In tab.
        self._rebuild_login_focus_order()

        # Keep the focus index in sync whenever the user clicks directly into a field.
        for entry_dict in (self._si_entries, self._ca_entries):
            for e in entry_dict.values():
                def _make_entry_focus_handler(entry=e):
                    def _handler(_event=None):
                        try:
                            self.login_focus_index = self.login_focus_order.index(entry)
                        except (ValueError, AttributeError):
                            pass
                        self._style_login_buttons()
                    return _handler
                e.bind("<FocusIn>", _make_entry_focus_handler(), add="+")

        # Start focus on the slider (index 0) so users can adjust voice speed immediately.
        self.after_idle(lambda: self._move_to_login_focus(0))
        self.after(150, lambda: self._move_to_login_focus(0))
        self.after(400, lambda: self._move_to_login_focus(0))
        self.speech.set_screen("Login screen", "Sign In tab is active. Enter email and password. Use Up and Down arrows to navigate.")

    def _sign_in(self) -> None:
        # Trigger the shared auth action using sign_in mode.
        self._run_auth_action("sign_in")

    def _sign_up(self) -> None:
        # Trigger the shared auth action using sign_up mode.
        self._run_auth_action("sign_up")

    def _run_auth_action(self, action: str) -> None:
        # Read form fields from the active tab, validate them, then call the AuthClient.
        try:
            if action == "sign_in":
                identifier = self._si_username_var.get().strip()
                password = self._si_password_var.get()
                username = ""
                # If the user typed a username (no @), look up the associated email.
                if identifier and "@" not in identifier:
                    looked_up = self.auth_client.lookup_email_by_username(identifier)
                    if looked_up:
                        email = looked_up
                    else:
                        self.speech.announce("Username not found. Please check your username or sign in with your email.", interrupt=True, force=True)
                        messagebox.showerror("Username not found", "No account found with that username. Try signing in with your email instead.")
                        self.after_idle(lambda: self._focus_login_entry("username"))
                        return
                else:
                    email = identifier
            else:
                username = self._ca_username_var.get().strip()
                email = self._ca_email_var.get().strip()
                password = self._ca_password_var.get()
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
                # Auto-register email→username mapping so username login works next time
                # for existing accounts that were created before this feature existed.
                if (
                    self.auth_session.local_id
                    and self.auth_session.username
                    and self.auth_session.id_token
                ):
                    self.auth_client._store_email_in_scores(
                        self.auth_session.local_id,
                        self.auth_session.username,
                        self.auth_session.email,
                        self.auth_session.id_token,
                    )
                self.speech.announce("Signed in successfully.", interrupt=True, force=True)
            else:
                self.auth_session = self.auth_client.sign_up(email, password, username=username)
                self.speech.announce("Account created successfully.", interrupt=True, force=True)
        except AuthError as exc:
            # The server rejected the credentials — speak the error and stay on the login screen.
            self.speech.announce(str(exc), interrupt=True, force=True)
            messagebox.showerror("Authentication error", str(exc))
            self.after_idle(lambda: self._focus_login_entry("password" if password else "username"))
            return
        # Auth succeeded — advance to the main menu.
        self.show_menu()

    def _on_speed_slider_change(self, value: float) -> None:
        rate = int(round(value))
        set_speech_rate(rate)
        self._speed_value_label.configure(text=str(rate))
        self.speech.announce(f"Voice speed {rate}", interrupt=True, force=True)

    def _adjust_speed_slider(self, delta: int) -> str:
        current = self._speed_slider.get()
        new_val = max(-10, min(10, round(current) + delta))
        self._speed_slider.set(new_val)
        self._on_speed_slider_change(new_val)
        return "break"
