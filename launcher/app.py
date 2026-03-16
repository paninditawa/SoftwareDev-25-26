from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from launcher.accessibility import SpeechManager
from launcher import apples_service
from launcher.auth import AuthSession, FirebaseAuthClient, FirebaseAuthError

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTING_DIR = REPO_ROOT / "testing"
GAME_LOGIC_DIR = TESTING_DIR / "game_logic"
BATTLESHIP_DIR = TESTING_DIR / "Battleship"

PAGE_META = {
    "home": {
        "title": "Home",
        "description": "Welcome to HelloWorld GameSpace. Use Up and Down arrows to choose a page, Enter to activate the focused control, F1 for help, F2 to repeat the last message, and F3 for where-am-I.",
        "hint": "Main menu home page.",
        "type": "home",
    },
    "hangman": {
        "title": "Hangman",
        "description": "Launches the pygame Hangman game.",
        "hint": "Press Enter to load launch controls for Hangman.",
        "type": "script",
        "path": GAME_LOGIC_DIR / "hangman_game.py",
    },
    "maze": {
        "title": "Maze Game",
        "description": "Launches the accessible pygame maze game with spoken movement.",
        "hint": "Press Enter to load launch controls for Maze Game.",
        "type": "script",
        "path": GAME_LOGIC_DIR / "maze_game.py",
    },
    "madlibs": {
        "title": "Mad Libs",
        "description": "Launches the accessible pygame Mad Libs game.",
        "hint": "Press Enter to load launch controls for Mad Libs.",
        "type": "script",
        "path": GAME_LOGIC_DIR / "madlibs_game.py",
    },
    "escape": {
        "title": "Escape Room",
        "description": "Launches the accessible Escape Room adventure game.",
        "hint": "Press Enter to load launch controls for Escape Room.",
        "type": "script",
        "path": GAME_LOGIC_DIR / "escape_room_game.py",
    },
    "connect4": {
        "title": "Connect 4",
        "description": "Launches the accessible pygame Connect 4 game.",
        "hint": "Press Enter to load launch controls for Connect 4.",
        "type": "script",
        "path": GAME_LOGIC_DIR / "c4_game.py",
    },
    "apples": {
        "title": "Apples to Apples",
        "description": "Native desktop Apples to Apples using the existing SQLite-backed game logic.",
        "hint": "Press Enter to load launch controls for Apples to Apples.",
        "type": "apples",
    },
    "battleship": {
        "title": "Battleship",
        "description": "Start or stop the Python Battleship server, then launch the pygame client.",
        "hint": "Press Enter to load Battleship controls.",
        "type": "battleship",
    },
    "account": {
        "title": "Account",
        "description": "Sign out or permanently delete your Firebase account.",
        "hint": "Press Enter to load account controls.",
        "type": "account",
    },
}

MENU_ORDER = ["home", "hangman", "maze", "madlibs", "escape", "connect4", "apples", "battleship", "account"]


class GameSpaceApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("dark-blue")

        self.title("HelloWorld GameSpace Launcher")
        self.geometry("1080x720")
        self.minsize(960, 640)
        self.configure(fg_color="#f2f5fb")

        self.auth_client = FirebaseAuthClient.from_workspace(REPO_ROOT)
        self.guest_mode = not self.auth_client.is_configured()
        self.speech = SpeechManager(on_announce=self._set_status)
        self.auth_session: AuthSession | None = None
        self.server_process: subprocess.Popen | None = None
        self.current_screen = "startup"
        self.current_page_key = "home"
        self.menu_order = [key for key in MENU_ORDER if key != "account"] if self.guest_mode else list(MENU_ORDER)
        self.nav_index = self.menu_order.index("home")
        self.action_index = 0
        self.nav_mode = True
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.action_widgets: list[tk.Widget] = []
        self.action_buttons: list[ctk.CTkButton] = []
        self.login_action_buttons: list[ctk.CTkButton] = []
        self.login_action_index = 0

        self.status_var = tk.StringVar(value="Ready.")
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.client_host_var = tk.StringVar(value="127.0.0.1")
        self.client_port_var = tk.StringVar(value="5555")
        self.apples_code_var = tk.StringVar()
        self.apples_name_var = tk.StringVar()
        self.apples_token = ""
        self.apples_selected_card: str | None = None
        self.apples_judge_choice: str | None = None

        self.header = ctk.CTkLabel(
            self,
            text="HelloWorld GameSpace",
            text_color="#123a66",
            font=ctk.CTkFont(size=30, weight="bold"),
        )
        self.header.pack(fill="x", padx=24, pady=(20, 10))

        self.subheader = ctk.CTkLabel(
            self,
            text="Keyboard-first, blind-accessible launcher",
            text_color="#4d6785",
            font=ctk.CTkFont(size=15),
        )
        self.subheader.pack(fill="x", padx=24, pady=(0, 10))

        self.content = ctk.CTkFrame(self, fg_color="#ffffff", corner_radius=16)
        self.content.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        self.status_label = ctk.CTkLabel(
            self,
            textvariable=self.status_var,
            anchor="w",
            justify="left",
            wraplength=980,
            text_color="#244567",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.status_label.pack(fill="x", padx=24, pady=(0, 16))

        self._bind_global_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        apples_service.init()

        if self.guest_mode:
            self.auth_session = AuthSession(
                email="Guest Tester",
                id_token="",
                refresh_token="",
                local_id="",
            )
            self.show_menu()
        elif self.auth_client.is_configured():
            self.show_login()
        else:
            self.show_config_error()

    def _launcher_command(self, *extra_args: str) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, *extra_args]
        return [sys.executable, str(REPO_ROOT / "launch_gamespace.py"), *extra_args]

    def _set_status(self, text: str) -> None:
        self.status_var.set(f"Last message: {text}")

    def _clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        self.nav_buttons = {}
        self.action_widgets = []
        self.action_buttons = []
        self.login_action_buttons = []
        self.login_action_index = 0
        self.action_index = 0
        self.nav_mode = True

    def _bind_global_keys(self) -> None:
        self.bind_all("<F1>", self._handle_help, add="+")
        self.bind_all("<F2>", self._handle_repeat, add="+")
        self.bind_all("<F3>", self._handle_where_am_i, add="+")
        self.bind_all("<Control-h>", self._handle_help, add="+")
        self.bind_all("<Control-r>", self._handle_repeat, add="+")
        self.bind_all("<Control-w>", self._handle_where_am_i, add="+")
        self.bind_all("<Escape>", self._handle_escape, add="+")
        self.bind_all("<Up>", lambda event: self._handle_vertical(-1), add="+")
        self.bind_all("<Down>", lambda event: self._handle_vertical(1), add="+")
        self.bind_all("<Left>", self._handle_left, add="+")
        self.bind_all("<Right>", self._handle_right, add="+")
        self.bind_all("<Tab>", self._handle_tab_mode_toggle, add="+")
        self.bind_all("<Return>", self._handle_activate, add="+")
        self.bind_all("<KP_Enter>", self._handle_activate, add="+")
        self.bind_all("<space>", self._handle_activate, add="+")

    def _handle_help(self, _event=None):
        if self.current_screen == "login":
            self.speech.announce(
                "Login screen help. Tab between Email, Password, Sign In, and Create Account. Press Enter to activate the focused button. F2 repeats the last message and F3 says where you are.",
                interrupt=True,
                force=True,
            )
        elif self.current_screen == "menu":
            self.speech.announce(
                "Menu help. Use Up and Down arrows to move between pages. Press Enter on a page button to load its controls. Tab moves into action buttons. Escape returns focus to the page list.",
                interrupt=True,
                force=True,
            )
        else:
            self.speech.announce("Help is not available on this screen.", interrupt=True, force=True)
        return "break"

    def _handle_repeat(self, _event=None):
        self.speech.repeat_last()
        return "break"

    def _handle_where_am_i(self, _event=None):
        self.speech.where_am_i()
        return "break"

    def _handle_escape(self, _event=None):
        if self.current_screen == "menu" and self.current_page_key in self.nav_buttons:
            self.nav_mode = True
            self._sync_keyboard_focus()
            return "break"
        return None

    def _handle_tab_mode_toggle(self, _event=None):
        if self.current_screen != "menu":
            return None
        if self._is_text_entry(self.focus_get()):
            return None
        self.nav_mode = not self.nav_mode
        self._sync_keyboard_focus()
        return "break"

    def _handle_left(self, _event=None):
        if self.current_screen != "menu":
            return None
        if self._is_text_entry(self.focus_get()):
            return None
        self.nav_mode = True
        self._sync_keyboard_focus()
        return "break"

    def _handle_right(self, _event=None):
        if self.current_screen != "menu":
            return None
        if self._is_text_entry(self.focus_get()):
            return None
        if self.action_buttons:
            self.nav_mode = False
            self._sync_keyboard_focus()
            return "break"
        self.speech.announce("No action buttons on this page.", interrupt=True, force=True)
        return "break"

    def _handle_activate(self, _event=None):
        if self.current_screen == "menu":
            if self.nav_mode:
                # On pages with a single primary action, Enter activates it directly.
                # Use Right Arrow to enter explicit action mode on multi-action pages.
                if len(self.action_buttons) == 1:
                    self.action_buttons[0].invoke()
                    self.nav_mode = True
                    self._sync_keyboard_focus()
                elif self.action_buttons:
                    self.nav_mode = False
                    self.action_index = 0
                    self._sync_keyboard_focus()
                else:
                    self.speech.announce("No action buttons on this page.", interrupt=True, force=True)
                return "break"

            if self.action_buttons:
                self.action_buttons[self.action_index].invoke()
                return "break"
            return "break"

        if self.current_screen == "login":
            widget = self.focus_get()
            if hasattr(widget, "invoke") and not self._is_text_entry(widget):
                widget.invoke()
                return "break"
            if self.login_action_buttons:
                self.login_action_buttons[self.login_action_index].invoke()
                return "break"
            return "break"

        # Generic fallback for any future screen with invokable focused controls.
        widget = self.focus_get()
        if hasattr(widget, "invoke") and not self._is_text_entry(widget):
            widget.invoke()
            return "break"

        return None

    def _handle_vertical(self, delta: int):
        if self.current_screen == "login":
            if self._is_text_entry(self.focus_get()):
                return None
            return self._move_login_action_selection(delta)

        if self.current_screen != "menu":
            return None
        if self._is_text_entry(self.focus_get()):
            return None
        if self.nav_mode:
            return self._move_menu_selection(delta)
        return self._move_action_selection(delta)

    def _is_text_entry(self, widget) -> bool:
        if widget is None:
            return False
        try:
            return isinstance(widget, tk.Entry) or widget.winfo_class() in {"Entry", "TEntry"}
        except Exception:
            return False

    def _move_menu_selection(self, delta: int):
        if self.current_screen != "menu":
            return None
        if self._is_text_entry(self.focus_get()):
            return None

        current_index = self.menu_order.index(self.current_page_key)
        new_index = (current_index + delta) % len(self.menu_order)
        new_key = self.menu_order[new_index]
        self.nav_index = new_index
        self.select_page(new_key, announce=True)
        self.nav_mode = True
        self._sync_keyboard_focus()
        return "break"

    def _move_action_selection(self, delta: int):
        if not self.action_buttons:
            self.speech.announce("No action buttons on this page.", interrupt=True, force=True)
            return "break"
        if len(self.action_buttons) <= 1:
            # Prevent keyboard trap on single-action pages (e.g., Hangman launch).
            self.nav_mode = True
            return self._move_menu_selection(delta)
        self.action_index = (self.action_index + delta) % len(self.action_buttons)
        self.nav_mode = False
        self._sync_keyboard_focus()
        return "break"

    def _move_login_action_selection(self, delta: int):
        if not self.login_action_buttons:
            return "break"
        self.login_action_index = (self.login_action_index + delta) % len(self.login_action_buttons)
        self._sync_login_focus()
        return "break"

    def _register_login_button(self, button: ctk.CTkButton, label: str, hint: str) -> None:
        self.speech.bind_focus(button, label, hint)
        self.login_action_buttons.append(button)

        def _on_focus(_event=None):
            try:
                self.login_action_index = self.login_action_buttons.index(button)
            except ValueError:
                return
            self._style_login_buttons()

        button.bind("<FocusIn>", _on_focus, add="+")

    def _style_login_buttons(self) -> None:
        for index, button in enumerate(self.login_action_buttons):
            if index == self.login_action_index:
                button.configure(border_width=2, border_color="#f2b134")
            else:
                button.configure(border_width=0)

    def _sync_login_focus(self) -> None:
        if self.current_screen != "login" or not self.login_action_buttons:
            return
        self._style_login_buttons()
        button = self.login_action_buttons[self.login_action_index]
        button.focus_set()
        self.speech.set_focus(button.cget("text"), "Press Enter to activate.")

    def _style_nav_button(self, key: str, button: ctk.CTkButton) -> None:
        selected = key == self.current_page_key
        keyboard_cursor = self.nav_mode and selected
        if keyboard_cursor:
            button.configure(fg_color="#0f4f8c", border_width=2, border_color="#f2b134")
        elif selected:
            button.configure(fg_color="#1f6aa5", border_width=0)
        else:
            button.configure(fg_color=("#3B8ED0", "#1F6AA5"), border_width=0)

    def _style_action_buttons(self) -> None:
        for index, button in enumerate(self.action_buttons):
            keyboard_cursor = (not self.nav_mode) and index == self.action_index
            if keyboard_cursor:
                button.configure(border_width=2, border_color="#f2b134")
            else:
                button.configure(border_width=0)

    def _sync_keyboard_focus(self) -> None:
        if self.current_screen != "menu":
            return

        for key, button in self.nav_buttons.items():
            self._style_nav_button(key, button)

        self._style_action_buttons()

        if self.nav_mode:
            button = self.nav_buttons.get(self.current_page_key)
            if button is not None:
                button.focus_set()
                self.speech.set_focus(PAGE_META[self.current_page_key]["title"], PAGE_META[self.current_page_key]["hint"])
            return

        if self.action_buttons:
            button = self.action_buttons[self.action_index]
            button.focus_set()
            text = button.cget("text")
            self.speech.set_focus(text, "Press Enter to activate.")

    def show_config_error(self) -> None:
        self.current_screen = "config"
        self._clear_content()

        frame = ctk.CTkFrame(self.content)
        frame.pack(fill="both", expand=True, padx=24, pady=24)

        title = ctk.CTkLabel(frame, text="Firebase Is Not Configured", font=ctk.CTkFont(size=24, weight="bold"))
        title.pack(anchor="w", padx=24, pady=(24, 12))

        message = ctk.CTkLabel(
            frame,
            text=(
                "Add firebase_api_key to .streamlit/secrets.toml or testing/.streamlit/secrets.toml, "
                "or set FIREBASE_API_KEY before launching this desktop app."
            ),
            wraplength=780,
            justify="left",
            anchor="w",
        )
        message.pack(anchor="w", padx=24, pady=(0, 12))

        paths = ctk.CTkLabel(
            frame,
            text=f"Expected secrets locations:\n{REPO_ROOT / '.streamlit' / 'secrets.toml'}\n{TESTING_DIR / '.streamlit' / 'secrets.toml'}",
            justify="left",
            anchor="w",
        )
        paths.pack(anchor="w", padx=24, pady=(0, 24))

        self.speech.set_screen(
            "Configuration error",
            "Firebase is not configured. Add a Firebase API key in secrets before using the launcher.",
        )

    def show_login(self) -> None:
        self.current_screen = "login"
        self._clear_content()
        self.email_var.set("")
        self.password_var.set("")

        wrapper = ctk.CTkFrame(self.content, fg_color="transparent")
        wrapper.pack(expand=True)

        card = ctk.CTkFrame(wrapper, width=560, fg_color="#ffffff", corner_radius=14, border_width=1, border_color="#d7e3f2")
        card.pack(padx=40, pady=40)

        title = ctk.CTkLabel(card, text="Sign In to HelloWorld GameSpace", font=ctk.CTkFont(size=24, weight="bold"))
        title.pack(anchor="w", padx=24, pady=(24, 8))

        summary = ctk.CTkLabel(
            card,
            text="This launcher is keyboard-first and speaks focus changes. Use Tab to move through controls.",
            wraplength=460,
            justify="left",
            anchor="w",
        )
        summary.pack(anchor="w", padx=24, pady=(0, 16))

        email_label = ctk.CTkLabel(card, text="Email")
        email_label.pack(anchor="w", padx=24)
        email_entry = ctk.CTkEntry(card, textvariable=self.email_var, width=460)
        email_entry.pack(padx=24, pady=(4, 16))
        self.speech.bind_focus(email_entry, "Email field", "Type your Firebase email address.")

        password_label = ctk.CTkLabel(card, text="Password")
        password_label.pack(anchor="w", padx=24)
        password_entry = ctk.CTkEntry(card, textvariable=self.password_var, width=460, show="*")
        password_entry.pack(padx=24, pady=(4, 16))
        self.speech.bind_focus(password_entry, "Password field", "Type your password, then Tab to Sign In or Create Account.")

        button_row = ctk.CTkFrame(card, fg_color="transparent")
        button_row.pack(fill="x", padx=24, pady=(0, 12))
        button_row.grid_columnconfigure((0, 1), weight=1)

        sign_in_button = ctk.CTkButton(button_row, text="Sign In", command=self._sign_in)
        sign_in_button.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self._register_login_button(sign_in_button, "Sign In button", "Activate to sign in with the entered email and password.")

        create_button = ctk.CTkButton(button_row, text="Create Account", command=self._sign_up)
        create_button.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        self._register_login_button(create_button, "Create Account button", "Activate to create a new Firebase account.")

        help_button = ctk.CTkButton(card, text="Read Login Help", command=self._handle_help)
        help_button.pack(padx=24, pady=(0, 24), fill="x")
        self._register_login_button(help_button, "Read Login Help button", "Activate to hear login instructions again.")

        # Enter from fields should work for fast keyboard-only login flow.
        email_entry.bind("<Return>", lambda _event: self._sign_in(), add="+")
        password_entry.bind("<Return>", lambda _event: self._sign_in(), add="+")

        self.after(150, email_entry.focus_set)
        self.after(250, self._style_login_buttons)
        self.speech.set_screen(
            "Login screen",
            "Enter email and password, then choose Sign In or Create Account.",
        )

    def _sign_in(self) -> None:
        self._run_auth_action("sign_in")

    def _sign_up(self) -> None:
        self._run_auth_action("sign_up")

    def _run_auth_action(self, action: str) -> None:
        email = self.email_var.get().strip()
        password = self.password_var.get()
        if not email or not password:
            self.speech.announce("Email and password are required.", interrupt=True, force=True)
            messagebox.showerror("Missing information", "Email and password are required.")
            return
        if len(password) < 6:
            self.speech.announce("Password must be at least 6 characters.", interrupt=True, force=True)
            messagebox.showerror("Password too short", "Password must be at least 6 characters.")
            return

        try:
            if action == "sign_in":
                self.auth_session = self.auth_client.sign_in(email, password)
                self.speech.announce("Signed in successfully.", interrupt=True, force=True)
            else:
                self.auth_session = self.auth_client.sign_up(email, password)
                self.speech.announce("Account created successfully.", interrupt=True, force=True)
        except FirebaseAuthError as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            messagebox.showerror("Authentication error", str(exc))
            return

        self.show_menu()

    def show_menu(self) -> None:
        self.current_screen = "menu"
        self._clear_content()
        if self.auth_session is None:
            self.show_login()
            return

        if self.current_page_key not in self.menu_order:
            self.current_page_key = "home"

        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.pack(fill="both", expand=True)
        root.grid_columnconfigure(0, weight=0)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)

        nav = ctk.CTkFrame(root, width=300, fg_color="#eef4fb", corner_radius=14)
        nav.grid(row=0, column=0, sticky="nsw", padx=(16, 8), pady=16)
        nav.grid_propagate(False)

        details = ctk.CTkFrame(root, fg_color="#ffffff", corner_radius=14, border_width=1, border_color="#d7e3f2")
        details.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        details.grid_columnconfigure(0, weight=1)
        details.grid_rowconfigure(2, weight=1)

        mode_prefix = "Signed in as" if not self.guest_mode else "Testing as"
        welcome = ctk.CTkLabel(nav, text=f"{mode_prefix} {self.auth_session.email}", wraplength=220, justify="left")
        welcome.pack(anchor="w", padx=16, pady=(16, 10))

        nav_text = "Use Up/Down arrows to change pages."
        if self.guest_mode:
            nav_text += " Firebase account tools are hidden in guest tester mode."
        nav_help = ctk.CTkLabel(nav, text=nav_text, justify="left", wraplength=220)
        nav_help.pack(anchor="w", padx=16, pady=(0, 12))

        for key in self.menu_order:
            title = PAGE_META[key]["title"]
            button = ctk.CTkButton(nav, text=title, anchor="w", command=lambda page=key: self.select_page(page, announce=True))
            button.pack(fill="x", padx=16, pady=4)
            self.speech.bind_focus(button, title, PAGE_META[key]["hint"])
            self.nav_buttons[key] = button

        self.detail_title = ctk.CTkLabel(details, text="", font=ctk.CTkFont(size=24, weight="bold"))
        self.detail_title.grid(row=0, column=0, sticky="w", padx=24, pady=(24, 8))

        self.detail_body = ctk.CTkLabel(details, text="", wraplength=620, justify="left", anchor="w")
        self.detail_body.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))

        self.action_frame = ctk.CTkFrame(details)
        self.action_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self.action_frame.grid_columnconfigure(0, weight=1)

        self.select_page(self.current_page_key, announce=False)
        self.after(150, self._sync_keyboard_focus)
        self.speech.set_screen(
            "Main menu",
            "Choose a page with Up and Down arrows. Press Right Arrow or Enter to enter action buttons. Press Left Arrow to return to pages.",
        )

    def select_page(self, page_key: str, announce: bool = True) -> None:
        if page_key not in PAGE_META:
            return
        self.current_page_key = page_key

        for key, button in self.nav_buttons.items():
            self._style_nav_button(key, button)

        meta = PAGE_META[page_key]
        self.detail_title.configure(text=meta["title"])
        self.detail_body.configure(text=meta["description"])
        self._render_actions(page_key)
        self._sync_keyboard_focus()

        if announce:
            self.speech.set_focus(meta["title"], meta["hint"])

    def _clear_actions(self) -> None:
        for child in self.action_frame.winfo_children():
            child.destroy()
        self.action_widgets = []
        self.action_buttons = []
        self.action_index = 0

    def _add_action_button(self, text: str, command, hint: str) -> ctk.CTkButton:
        button = ctk.CTkButton(self.action_frame, text=text, command=command)
        button.pack(fill="x", pady=6)
        self.speech.bind_focus(button, text, hint)
        self.action_widgets.append(button)
        self.action_buttons.append(button)
        return button

    def _register_action_button(self, button: ctk.CTkButton, hint: str) -> None:
        text = button.cget("text")
        self.speech.bind_focus(button, text, hint)
        self.action_widgets.append(button)
        self.action_buttons.append(button)

    def _render_actions(self, page_key: str) -> None:
        self._clear_actions()
        meta = PAGE_META[page_key]
        kind = meta["type"]

        if kind == "home":
            helper = ctk.CTkLabel(
                self.action_frame,
                text="Choose a game or account option from the left menu. F1 reads help, F2 repeats, F3 tells you where you are.",
                justify="left",
                anchor="w",
                wraplength=620,
            )
            helper.pack(fill="x", pady=6)
            self.action_widgets.append(helper)
            self.action_buttons = []
            return

        if kind == "script":
            self._add_action_button(
                f"Launch {meta['title']}",
                lambda path=meta["path"], title=meta["title"]: self._launch_script(path, title),
                f"Activate to launch {meta['title']}.",
            )
            return

        if kind == "apples":
            self._render_apples_actions()
            return

        if kind == "battleship":
            self._render_battleship_actions()
            return

        if kind == "account":
            if self.guest_mode:
                info = ctk.CTkLabel(
                    self.action_frame,
                    text="Account actions are unavailable in guest tester mode.",
                    justify="left",
                    anchor="w",
                    wraplength=620,
                )
                info.pack(fill="x", pady=6)
                self.action_widgets.append(info)
                self.action_buttons = []
                return
            self._add_action_button("Sign Out", self._sign_out, "Activate to sign out and return to login.")
            self._add_action_button("Delete Account", self._delete_account, "Activate to permanently delete your Firebase account.")
            return

    def _render_battleship_actions(self) -> None:
        host_label = ctk.CTkLabel(self.action_frame, text="Server host")
        host_label.pack(anchor="w", pady=(0, 4))
        host_entry = ctk.CTkEntry(self.action_frame, textvariable=self.client_host_var)
        host_entry.pack(fill="x", pady=(0, 10))
        self.speech.bind_focus(host_entry, "Battleship host field", "Enter the server host for Battleship client connections.")

        port_label = ctk.CTkLabel(self.action_frame, text="Server port")
        port_label.pack(anchor="w", pady=(0, 4))
        port_entry = ctk.CTkEntry(self.action_frame, textvariable=self.client_port_var)
        port_entry.pack(fill="x", pady=(0, 10))
        self.speech.bind_focus(port_entry, "Battleship port field", "Enter the port number for Battleship server and client.")

        self.action_widgets.extend([host_entry, port_entry])

        self._add_action_button(
            "Start Battleship Server",
            self._start_battleship_server,
            "Activate to start the local Battleship server.",
        )
        self._add_action_button(
            "Stop Battleship Server",
            self._stop_battleship_server,
            "Activate to stop the local Battleship server.",
        )
        self._add_action_button(
            "Launch Battleship Client",
            self._launch_battleship_client,
            "Activate to launch the Battleship client.",
        )

    def _launch_script(self, script_path: Path, title: str) -> None:
        if not script_path.exists():
            message = f"Could not find {script_path.name}."
            self.speech.announce(message, interrupt=True, force=True)
            messagebox.showerror("Missing file", message)
            return
        relative_target = script_path.relative_to(REPO_ROOT).as_posix()
        subprocess.Popen(self._launcher_command("--run-target", relative_target), cwd=str(REPO_ROOT))
        self.speech.announce(f"Launching {title}.", interrupt=True, force=True)

    def _parse_port(self) -> int | None:
        value = self.client_port_var.get().strip()
        try:
            return int(value)
        except ValueError:
            self.speech.announce("Port must be a number.", interrupt=True, force=True)
            messagebox.showerror("Invalid port", "Port must be a number.")
            return None

    def _start_battleship_server(self) -> None:
        if self.server_process and self.server_process.poll() is None:
            self.speech.announce("Battleship server is already running.", interrupt=True, force=True)
            return

        port = self._parse_port()
        if port is None:
            return
        host = self.client_host_var.get().strip() or "127.0.0.1"
        server_path = BATTLESHIP_DIR / "server.py"
        relative_target = server_path.relative_to(REPO_ROOT).as_posix()
        self.server_process = subprocess.Popen(
            self._launcher_command("--run-target", relative_target, "--host", host, "--port", str(port)),
            cwd=str(REPO_ROOT),
        )
        self.speech.announce(f"Battleship server started on {host} port {port}.", interrupt=True, force=True)

    def _stop_battleship_server(self) -> None:
        if not self.server_process or self.server_process.poll() is not None:
            self.speech.announce("Battleship server is not running.", interrupt=True, force=True)
            return
        self.server_process.terminate()
        self.server_process = None
        self.speech.announce("Battleship server stopped.", interrupt=True, force=True)

    def _launch_battleship_client(self) -> None:
        port = self._parse_port()
        if port is None:
            return
        host = self.client_host_var.get().strip() or "127.0.0.1"
        client_path = BATTLESHIP_DIR / "client.py"
        relative_target = client_path.relative_to(REPO_ROOT).as_posix()
        subprocess.Popen(
            self._launcher_command("--run-target", relative_target, "--host", host, "--port", str(port)),
            cwd=str(REPO_ROOT),
        )
        self.speech.announce(f"Launching Battleship client for host {host} on port {port}.", interrupt=True, force=True)

    def _render_apples_actions(self) -> None:
        helper = ctk.CTkLabel(
            self.action_frame,
            text="Create a local game code or join an existing one. After joining, refresh to hear the latest state.",
            justify="left",
            anchor="w",
            wraplength=620,
        )
        helper.pack(fill="x", pady=(0, 10))

        code_label = ctk.CTkLabel(self.action_frame, text="Game code")
        code_label.pack(anchor="w")
        code_entry = ctk.CTkEntry(self.action_frame, textvariable=self.apples_code_var)
        code_entry.pack(fill="x", pady=(4, 10))
        self.speech.bind_focus(code_entry, "Apples game code field", "Type a game code or create a new game.")

        name_label = ctk.CTkLabel(self.action_frame, text="Player name")
        name_label.pack(anchor="w")
        name_entry = ctk.CTkEntry(self.action_frame, textvariable=self.apples_name_var)
        name_entry.pack(fill="x", pady=(4, 10))
        self.speech.bind_focus(name_entry, "Apples player name field", "Type your player name before joining.")

        self.action_widgets.extend([code_entry, name_entry])

        button_row = ctk.CTkFrame(self.action_frame, fg_color="transparent")
        button_row.pack(fill="x", pady=(0, 12))
        button_row.grid_columnconfigure((0, 1, 2), weight=1)

        create_button = ctk.CTkButton(button_row, text="Create Game", command=self._apples_create_game)
        create_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self._register_action_button(create_button, "Activate to create a new Apples to Apples game code.")

        join_button = ctk.CTkButton(button_row, text="Join Game", command=self._apples_join_game)
        join_button.grid(row=0, column=1, padx=6, sticky="ew")
        self._register_action_button(join_button, "Activate to join the current game code as the entered player name.")

        refresh_button = ctk.CTkButton(button_row, text="Refresh State", command=self._refresh_apples_page)
        refresh_button.grid(row=0, column=2, padx=(6, 0), sticky="ew")
        self._register_action_button(refresh_button, "Activate to reload Apples to Apples game state.")

        game = self._current_apples_game()
        if not game:
            info = ctk.CTkLabel(
                self.action_frame,
                text="No current Apples game selected. Create a game or enter a code and join.",
                justify="left",
                anchor="w",
                wraplength=620,
            )
            info.pack(fill="x", pady=(8, 0))
            return

        game_id = int(game["id"])
        roster = apples_service.players(game_id)
        me = apples_service.my_player(game_id, self.apples_token) if self.apples_token else None
        judge_name = next((p["name"] for p in roster if game["judge_pid"] and int(p["id"]) == int(game["judge_pid"])), "—")
        is_judge = bool(game["judge_pid"]) and me and int(me["id"]) == int(game["judge_pid"])

        status = ctk.CTkLabel(
            self.action_frame,
            text=(
                f"Code: {game['code']}\n"
                f"Phase: {game['phase']}\n"
                f"Round: {game['round_num']}\n"
                f"Judge: {judge_name}\n"
                f"Prompt: {game['green'] or '(none)'}\n"
                f"Last update: {game['last_msg']}"
            ),
            justify="left",
            anchor="w",
            wraplength=620,
        )
        status.pack(fill="x", pady=(8, 12))

        roster_title = ctk.CTkLabel(self.action_frame, text="Players", font=ctk.CTkFont(size=18, weight="bold"))
        roster_title.pack(anchor="w")
        for player in roster:
            tag = []
            if game["judge_pid"] and int(player["id"]) == int(game["judge_pid"]):
                tag.append("Judge")
            if me and int(player["id"]) == int(me["id"]):
                tag.append("You")
            suffix = f" ({', '.join(tag)})" if tag else ""
            line = ctk.CTkLabel(self.action_frame, text=f"- {player['name']}{suffix}: {player['score']}", anchor="w", justify="left")
            line.pack(fill="x")

        if game["phase"] == "lobby":
            start_button = self._add_action_button(
                "Start Apples Game",
                self._apples_start_game,
                "Activate to start Apples to Apples after at least two players have joined.",
            )
            if len(roster) < 2:
                start_button.configure(state="disabled")
            return

        if not me:
            warning = ctk.CTkLabel(
                self.action_frame,
                text="You have not joined this Apples game yet.",
                justify="left",
                anchor="w",
                wraplength=620,
            )
            warning.pack(fill="x", pady=(12, 0))
            return

        round_num = int(game["round_num"])
        if game["phase"] == "selecting":
            if is_judge:
                wait = ctk.CTkLabel(
                    self.action_frame,
                    text="You are the judge. Wait for all players to submit their cards, then refresh.",
                    justify="left",
                    anchor="w",
                    wraplength=620,
                )
                wait.pack(fill="x", pady=(12, 0))
            else:
                hand_title = ctk.CTkLabel(self.action_frame, text="Your hand", font=ctk.CTkFont(size=18, weight="bold"))
                hand_title.pack(anchor="w", pady=(12, 6))
                hand = apples_service.get_hand(game_id, int(me["id"]))
                for index, card in enumerate(hand[:apples_service.HAND_SIZE], start=1):
                    button = ctk.CTkButton(
                        self.action_frame,
                        text=f"Card {index}: {card}",
                        command=lambda selected=card: self._apples_select_card(selected),
                    )
                    button.pack(fill="x", pady=3)
                    self._register_action_button(button, card)
                selected_text = self.apples_selected_card or "No card selected."
                selected_label = ctk.CTkLabel(self.action_frame, text=f"Selected: {selected_text}", justify="left", anchor="w", wraplength=620)
                selected_label.pack(fill="x", pady=(10, 6))
                submit_button = self._add_action_button(
                    "Submit Selected Card",
                    lambda gid=game_id, rn=round_num, pid=int(me["id"]), jid=int(game["judge_pid"]): self._apples_submit_card(gid, rn, pid, jid),
                    "Activate to submit the selected red card.",
                )
                if not self.apples_selected_card:
                    submit_button.configure(state="disabled")
            return

        if game["phase"] == "judging":
            if not is_judge:
                wait = ctk.CTkLabel(
                    self.action_frame,
                    text="Waiting for the judge to pick a winner. Press Refresh State to hear updates.",
                    justify="left",
                    anchor="w",
                    wraplength=620,
                )
                wait.pack(fill="x", pady=(12, 0))
            else:
                judge_title = ctk.CTkLabel(self.action_frame, text="Judge submissions", font=ctk.CTkFont(size=18, weight="bold"))
                judge_title.pack(anchor="w", pady=(12, 6))
                submissions = apples_service.list_submissions(game_id, round_num)
                if not submissions:
                    empty = ctk.CTkLabel(self.action_frame, text="No submissions yet.", justify="left", anchor="w")
                    empty.pack(fill="x")
                else:
                    for index, card in enumerate(submissions, start=1):
                        button = ctk.CTkButton(
                            self.action_frame,
                            text=f"Winner option {index}: {card}",
                            command=lambda selected=card: self._apples_pick_winner(game_id, round_num, int(me["id"]), selected),
                        )
                        button.pack(fill="x", pady=3)
                        self._register_action_button(button, card)
            return

        if game["phase"] == "game_over":
            over = ctk.CTkLabel(
                self.action_frame,
                text="Game over. Review the scores above or create a new game.",
                justify="left",
                anchor="w",
                wraplength=620,
            )
            over.pack(fill="x", pady=(12, 0))

    def _current_apples_game(self):
        code = self.apples_code_var.get().strip().upper()
        if not code:
            return None
        return apples_service.game_by_code(code)

    def _refresh_apples_page(self) -> None:
        self.apples_selected_card = None
        self.apples_judge_choice = None
        self.select_page("apples", announce=False)
        self.speech.announce("Apples to Apples state refreshed.", interrupt=True, force=True)

    def _apples_create_game(self) -> None:
        code = apples_service.create_game(points_to_win=5)
        self.apples_code_var.set(code)
        self.apples_token = ""
        self.apples_selected_card = None
        self.select_page("apples", announce=False)
        self.speech.announce(f"Created Apples to Apples game {code}.", interrupt=True, force=True)

    def _apples_join_game(self) -> None:
        code = self.apples_code_var.get().strip().upper()
        name = self.apples_name_var.get().strip()
        if not code or not name:
            message = "Game code and player name are required to join Apples to Apples."
            self.speech.announce(message, interrupt=True, force=True)
            messagebox.showerror("Missing information", message)
            return
        try:
            self.apples_token = apples_service.join_game(code, name)
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            messagebox.showerror("Join failed", str(exc))
            return
        self.select_page("apples", announce=False)
        self.speech.announce(f"Joined Apples to Apples game {code} as {name}.", interrupt=True, force=True)

    def _apples_start_game(self) -> None:
        game = self._current_apples_game()
        if not game:
            return
        try:
            apples_service.start_game(int(game["id"]))
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            messagebox.showerror("Start game failed", str(exc))
            return
        self.select_page("apples", announce=False)
        self.speech.announce("Apples to Apples game started.", interrupt=True, force=True)

    def _apples_select_card(self, card: str) -> None:
        self.apples_selected_card = card
        self.select_page("apples", announce=False)
        self.speech.announce(f"Selected card: {card}", interrupt=True, force=True)

    def _apples_submit_card(self, game_id: int, round_num: int, player_id: int, judge_id: int) -> None:
        if not self.apples_selected_card:
            self.speech.announce("Select a card before submitting.", interrupt=True, force=True)
            return
        try:
            apples_service.submit_card(game_id, round_num, player_id, judge_id, self.apples_selected_card)
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            messagebox.showerror("Submit failed", str(exc))
            return
        submitted_card = self.apples_selected_card
        self.apples_selected_card = None
        self.select_page("apples", announce=False)
        self.speech.announce(f"Submitted card: {submitted_card}", interrupt=True, force=True)

    def _apples_pick_winner(self, game_id: int, round_num: int, judge_id: int, winning_card: str) -> None:
        try:
            apples_service.judge_pick(game_id, round_num, judge_id, winning_card)
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            messagebox.showerror("Judge pick failed", str(exc))
            return
        self.select_page("apples", announce=False)
        self.speech.announce(f"Selected winning card: {winning_card}", interrupt=True, force=True)

    def _sign_out(self) -> None:
        if self.guest_mode:
            self.speech.announce("Guest tester mode has no sign out.", interrupt=True, force=True)
            return
        self.auth_session = None
        self.speech.announce("Signed out.", interrupt=True, force=True)
        self.show_login()

    def _delete_account(self) -> None:
        if self.guest_mode:
            self.speech.announce("Guest tester mode has no account to delete.", interrupt=True, force=True)
            return
        if self.auth_session is None:
            return
        confirmed = messagebox.askyesno(
            "Delete account",
            "Delete your Firebase account permanently? This cannot be undone.",
        )
        if not confirmed:
            self.speech.announce("Account deletion cancelled.", interrupt=True, force=True)
            return

        try:
            self.auth_client.delete_account(self.auth_session)
        except FirebaseAuthError as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            messagebox.showerror("Delete account failed", str(exc))
            return

        self.auth_session = None
        self.speech.announce("Your account has been deleted.", interrupt=False, force=True)
        self.show_login()

    def _on_close(self) -> None:
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
        self.destroy()


def main() -> None:
    app = GameSpaceApp()
    app.mainloop()


if __name__ == "__main__":
    main()
