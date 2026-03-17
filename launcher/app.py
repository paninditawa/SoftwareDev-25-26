"""
app.py is the main app file for the HelloWorld GameSpace launcher. 
It's a desktop app built with customtkinter (UI toolkit) that serves as the hub for: 
- launching various accessible games 
- viewing the community scoreboard
- managing user accounts 
It integrates with Supabase for authentication and data storage.
Finally, it includes features like keyboard navigation and text-to-speech accessibility support.
"""

# import all necessary modules and classes for the app
from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, TclError

import customtkinter as ctk

from launcher.accessibility import SpeechManager
from launcher import apples_service
from launcher.auth import AuthSession, AuthClient, AuthError
from launcher.scoreboard import Scoreboard

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTING_DIR = REPO_ROOT / "testing"
GAME_LOGIC_DIR = TESTING_DIR / "game_logic"
BATTLESHIP_DIR = TESTING_DIR / "Battleship"

# create dict of page metadata for launcher menu, including title, description, hint, and type of each page
PAGE_META = {
    "home": {
        "title": "Home",
        "description": "Welcome to HelloWorld GameSpace. Use Up and Down arrows to choose a page. Press Enter or Space to activate.",
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
        "description": "Host a new game and share your room code, or join a friend's game with their code.",
        "hint": "Press Enter to load Battleship options.",
        "type": "battleship",
    },
    "scoreboard": {
        "title": "Scoreboard",
        "description": "Community leaderboard — top wins across all HelloWorld games.",
        "hint": "Press Enter to view the scoreboard.",
        "type": "scoreboard",
    },
    "account": {
        "title": "Account",
        "description": "Sign out of your account.",
        "hint": "Press Enter to load account controls.",
        "type": "account",
    },
}

MENU_ORDER = [
    "home", "hangman", "maze", "madlibs", "escape",
    "connect4", "apples", "battleship", "scoreboard", "account",
]

# Game name: display label for the scoreboard tabs
SCOREBOARD_GAMES = [
    ("battleship", "Battleship"),
    ("hangman",    "Hangman"),
    ("maze",       "Maze Game"),
    ("escape",     "Escape Room"),
    ("connect4",   "Connect 4"),
    ("apples",     "Apples to Apples"),
]

# custom simplified palette (contrast-first, microsoft-style structure)
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
    return ctk.CTkFont(family=APP_FONT_FAMILY, size=size, weight="bold" if bold else "normal")

# main launcher window + shared app state
class GameSpaceApp(ctk.CTk):
    # sets up window + shared launcher state
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("dark-blue")

        self.title("HelloWorld GameSpace Launcher")
        self._set_initial_window_size()
        self.configure(fg_color=APP_BG)

        self.auth_client = AuthClient.from_workspace(REPO_ROOT)

        # hard stop if supabase auth missing
        if not self.auth_client.is_configured():
            raise RuntimeError("Supabase auth is required. Configure supabase_project.py before launching.")
        
        self.speech = SpeechManager(on_announce=self._set_status)
        self.auth_session: AuthSession | None = None
        self.server_process: subprocess.Popen | None = None
        self.current_screen = "startup"
        self.current_page_key = "home"
        self.menu_order = list(MENU_ORDER)
        self.nav_index = self.menu_order.index("home")
        self.action_index = 0
        self.nav_mode = True
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.action_widgets: list[tk.Widget] = []
        self.action_buttons: list[ctk.CTkButton] = []
        self.login_action_buttons: list[ctk.CTkButton] = []
        self.login_entries: dict[str, ctk.CTkEntry] = {}
        self.login_action_index = 0

        self.status_var = tk.StringVar(value="Ready.")
        self.username_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.client_host_var = tk.StringVar(value="127.0.0.1")
        self.client_port_var = tk.StringVar(value="5555")
        self.battleship_room_code_var = tk.StringVar()
        self.apples_code_var = tk.StringVar()
        self.apples_name_var = tk.StringVar()
        self.apples_token = ""
        self.apples_selected_card: str | None = None
        self.apples_judge_choice: str | None = None

        # cache scoreboard client + selected tab
        self._scoreboard: "Scoreboard | None" = None
        self._sb_selected_game: str = "battleship"

        self.header = ctk.CTkLabel(
            self,
            text="HelloWorld GameSpace",
            text_color=APP_TEXT,
            font=_font(30, bold=True),
        )
        self.header.pack(fill="x", padx=24, pady=(20, 10))

        self.subheader = ctk.CTkLabel(
            self,
            text="Keyboard-first, blind-accessible launcher",
            text_color=APP_MUTED,
            font=_font(18, bold=True),
        )
        self.subheader.pack(fill="x", padx=24, pady=(0, 10))

        self.content = ctk.CTkFrame(self, fg_color=APP_PANEL, corner_radius=16, border_width=1, border_color=APP_BORDER)
        self.content.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        self.status_label = ctk.CTkLabel(
            self,
            textvariable=self.status_var,
            anchor="w",
            justify="left",
            wraplength=980,
            text_color=APP_TEXT,
            font=_font(18, bold=True),
        )
        self.status_label.pack(fill="x", padx=24, pady=(0, 16))

        self._bind_global_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        apples_service.init()

        # first screen always login
        self.show_login()

    # sizes window from current screen size + keeps resize flexible
    def _set_initial_window_size(self) -> None:
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        width = max(720, min(screen_width - 40, int(screen_width * 0.96)))
        height = max(560, min(screen_height - 60, int(screen_height * 0.94)))
        min_width = min(960, width)
        min_height = min(640, height)
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)

        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min_width, min_height)

    # gets scoreboard client + creates once when needed
    def _get_scoreboard(self) -> "Scoreboard | None":
        if self._scoreboard is None:
            try:
                token = self.auth_session.id_token if self.auth_session else ""
                self._scoreboard = Scoreboard.from_workspace(REPO_ROOT, id_token=token)
            except Exception:
                return None
        return self._scoreboard

    # records a win for current signed-in user
    def record_win(self, game: str) -> None:
        """Call this when the logged-in user wins a game."""
        if self.auth_session is None:
            return
        sb = self._get_scoreboard()
        if sb is None:
            return
        try:
            sb.record_win(
                user_id=self.auth_session.local_id,
                username=self.auth_session.username or self.auth_session.email,
                game=game,
            )
        except Exception as exc:
            print(f"[scoreboard] record_win failed: {exc}")

    # builds python command used to launch game scripts
    def _launcher_command(self, *extra_args: str) -> list[str]:
        return [sys.executable, str(REPO_ROOT / "launch_gamespace.py"), *extra_args]

    # updates status bar text at bottom
    def _set_status(self, text: str) -> None:
        self.status_var.set(f"Last message: {text}")

    # clears current page widgets + resets nav state
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

    # binds global keyboard shortcuts
    def _bind_global_keys(self) -> None:
        # global keyboard map for whole launcher
        self.bind_all("<Up>", lambda event: self._handle_vertical(-1), add="+")
        self.bind_all("<Down>", lambda event: self._handle_vertical(1), add="+")
        self.bind_all("<Left>", self._handle_left, add="+")
        self.bind_all("<Right>", self._handle_right, add="+")
        self.bind_all("<Return>", self._handle_activate, add="+")
        self.bind_all("<KP_Enter>", self._handle_activate, add="+")
        self.bind_all("<space>", self._handle_activate, add="+")
        self.bind_all("<Escape>", self._handle_escape, add="+")
        self.bind_all("<F1>", self._handle_help, add="+")
        self.bind_all("<F2>", self._handle_repeat, add="+")
        self.bind_all("<F6>", lambda event: self._handle_pane_cycle(1), add="+")
        self.bind_all("<Shift-F6>", lambda event: self._handle_pane_cycle(-1), add="+")
        self.bind_all("<F7>", self._handle_where_am_i, add="+")

    # makes tab keys act like vertical navigation keys
    def _bind_tab_aliases(self, widget: tk.Widget) -> None:
        widget.bind("<Shift-Tab>", lambda event: self._handle_vertical(-1), add="+")
        widget.bind("<Tab>", lambda event: self._handle_vertical(1), add="+")

    # reads help message based on current screen
    def _handle_help(self, _event=None):
        if self.current_screen == "login":
            self.speech.announce(
                "Login screen help. Use Up and Down arrows to move between buttons. Press Enter or Space to activate. Username is required when creating a new account.",
                interrupt=True, force=True,
            )
        elif self.current_screen == "menu":
            self.speech.announce(
                "Menu help. Use Up and Down arrows to move between pages. Press Right Arrow or Enter to move into action buttons. Press Left Arrow to return to the page list.",
                interrupt=True, force=True,
            )
        else:
            self.speech.announce("Help is not available on this screen.", interrupt=True, force=True)
        return "break"

    # repeats last spoken accessibility message
    def _handle_repeat(self, _event=None):
        self.speech.repeat_last()
        return "break"

    # announces current screen + focus context
    def _handle_where_am_i(self, _event=None):
        self.speech.where_am_i()
        return "break"

    # closes launcher when escape is pressed
    def _handle_escape(self, _event=None):
        self.speech.announce("Escape key was hit, so closing gamespace... goodbye!", interrupt=True, force=True)
        # short delay so tts starts before app closes
        self.after(5000, self._on_close)
        return "break"

    # lets F6 jump between major launcher panes
    def _handle_pane_cycle(self, _delta: int):
        if self.current_screen != "menu":
            return None

        focus = self.focus_get()
        in_nav_pane = focus in self.nav_buttons.values()

        if in_nav_pane:
            if self._focus_first_action_target():
                return "break"
            self.speech.announce("No interactive controls are available in the details pane.", interrupt=True, force=True)
            return "break"

        self.nav_mode = True
        self._sync_keyboard_focus()
        return "break"

    # moves keyboard mode back to left menu column
    def _handle_left(self, _event=None):
        if self.current_screen != "menu":
            return None
        if self._is_text_entry(self.focus_get()):
            return None
        self.nav_mode = True
        self._sync_keyboard_focus()
        return "break"

    # moves keyboard mode to right action buttons
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

    # handles enter/space activation for focused control
    def _handle_activate(self, _event=None):
        # enter/space behavior changes by current screen + focus mode
        if self.current_screen == "menu":
            if self.nav_mode:
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

        widget = self.focus_get()
        if hasattr(widget, "invoke") and not self._is_text_entry(widget):
            widget.invoke()
            return "break"
        return None

    # handles up/down movement based on current mode
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

    # checks if focused widget is a typing field
    def _is_text_entry(self, widget) -> bool:
        if widget is None:
            return False
        try:
            return isinstance(widget, tk.Entry) or widget.winfo_class() in {"Entry", "TEntry"}
        except Exception:
            return False

    # moves highlighted page in left nav list
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

    # moves highlighted action in right action list
    def _move_action_selection(self, delta: int):
        if not self.action_buttons:
            self.speech.announce("No action buttons on this page.", interrupt=True, force=True)
            return "break"
        if len(self.action_buttons) <= 1:
            self.nav_mode = True
            return self._move_menu_selection(delta)
        self.action_index = (self.action_index + delta) % len(self.action_buttons)
        self.nav_mode = False
        self._sync_keyboard_focus()
        return "break"

    # moves highlighted login button action
    def _move_login_action_selection(self, delta: int):
        if not self.login_action_buttons:
            return "break"
        self.login_action_index = (self.login_action_index + delta) % len(self.login_action_buttons)
        self._sync_login_focus()
        return "break"

    # registers login button for keyboard + speech support
    def _register_login_button(self, button: ctk.CTkButton, label: str, hint: str) -> None:
        self.speech.bind_focus(button, label, hint)
        self._bind_tab_aliases(button)
        self.login_action_buttons.append(button)

        # syncs selected login action when button gets focus
        def _on_focus(_event=None):
            try:
                self.login_action_index = self.login_action_buttons.index(button)
            except ValueError:
                return
            self._style_login_buttons()

        button.bind("<FocusIn>", _on_focus, add="+")

    # styles login action buttons to show selected one
    def _style_login_buttons(self) -> None:
        for index, button in enumerate(self.login_action_buttons):
            if index == self.login_action_index:
                button.configure(border_width=3, border_color=APP_FOCUS)
            else:
                button.configure(border_width=0)

    # applies focus to selected login action button
    def _sync_login_focus(self) -> None:
        if self.current_screen != "login" or not self.login_action_buttons:
            return
        self._style_login_buttons()
        button = self.login_action_buttons[self.login_action_index]
        button.focus_set()
        self.speech.set_focus(button.cget("text"), "Press Enter to activate.")

    # moves cursor back into one login field
    def _focus_login_entry(self, field_name: str) -> None:
        entry = self.login_entries.get(field_name)
        if entry is None:
            return
        entry.focus_set()
        entry.icursor("end")

    # moves focus into first usable control in the details pane
    def _focus_first_action_target(self) -> bool:
        for widget in self.action_widgets:
            if widget is None:
                continue
            try:
                if not widget.winfo_exists():
                    continue
            except Exception:
                continue

            if self._is_text_entry(widget):
                widget.focus_set()
                return True

            if hasattr(widget, "invoke"):
                try:
                    if str(widget.cget("state")) == "disabled":
                        continue
                except Exception:
                    pass
                if widget in self.action_buttons:
                    self.nav_mode = False
                    self.action_index = self.action_buttons.index(widget)
                    self._sync_keyboard_focus()
                else:
                    widget.focus_set()
                return True

        return False

    # returns shared button styling for accessible contrast + sizing
    def _button_style_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "height": APP_BUTTON_H,
            "text_color": APP_BUTTON_TEXT,
            "fg_color": APP_BUTTON,
            "hover_color": APP_BUTTON_HOVER,
            "font": _font(16, bold=True),
            "border_width": 1,
            "border_color": APP_BORDER,
        }
        return kwargs

    # styles left nav button by selected/active state
    def _style_nav_button(self, key: str, button: ctk.CTkButton) -> None:
        selected = key == self.current_page_key
        keyboard_cursor = self.nav_mode and selected
        if keyboard_cursor:
            button.configure(fg_color=APP_ACCENT_STRONG, border_width=3, border_color=APP_FOCUS)
        elif selected:
            button.configure(fg_color=APP_ACCENT, border_width=2, border_color=APP_BORDER)
        else:
            button.configure(fg_color=(APP_ACCENT_SOFT, APP_ACCENT), border_width=1, border_color=APP_BORDER)

    # styles right action buttons by selected/active state
    def _style_action_buttons(self) -> None:
        for index, button in enumerate(self.action_buttons):
            keyboard_cursor = (not self.nav_mode) and index == self.action_index
            if keyboard_cursor:
                button.configure(border_width=3, border_color=APP_FOCUS)
            else:
                button.configure(border_width=1, border_color=APP_BORDER)

    # syncs keyboard focus with nav/action selection state
    def _sync_keyboard_focus(self) -> None:
        # keep visual highlight + keyboard focus in same spot
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

    # builds + displays login screen ui
    def show_login(self) -> None:
        # rebuild login ui from scratch each time
        self.current_screen = "login"
        self._clear_content()
        self.login_entries = {}
        self.username_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()

        wrapper = ctk.CTkFrame(self.content, fg_color="transparent")
        wrapper.pack(expand=True)

        card = ctk.CTkFrame(wrapper, width=560, fg_color=APP_PANEL, corner_radius=14, border_width=2, border_color=APP_BORDER)
        card.pack(padx=40, pady=40)

        title = ctk.CTkLabel(card, text="Sign In to HelloWorld GameSpace", text_color=APP_TEXT, font=_font(28, bold=True))
        title.pack(anchor="w", padx=24, pady=(24, 8))

        summary = ctk.CTkLabel(
            card,
            text="Use Up and Down arrows to move between buttons. Username is required when creating a new account.",
            wraplength=460, justify="left", anchor="w",
            text_color=APP_MUTED,
            font=_font(16, bold=True),
        )
        summary.pack(anchor="w", padx=24, pady=(0, 16))

        email_entry_widget: ctk.CTkEntry | None = None
        for field_name, var, label_text, hint, show in [
            ("username", self.username_var, "Username (for new accounts)", "Type a username when creating a new account.", ""),
            ("email", self.email_var,       "Email",                       "Type your account email address.",             ""),
            ("password", self.password_var, "Password",                    "Type your password.",                          "*"),
        ]:
            ctk.CTkLabel(card, text=label_text, text_color=APP_TEXT, font=_font(15, bold=True)).pack(anchor="w", padx=24)
            entry = ctk.CTkEntry(card, textvariable=var, width=460, height=42, show=show, fg_color=APP_ENTRY_BG, border_color=APP_BORDER, text_color=APP_TEXT)
            entry.pack(padx=24, pady=(4, 16))
            self.speech.bind_focus(entry, f"{label_text} field", hint)
            self.login_entries[field_name] = entry
            if field_name == "email":
                # keep ref so cursor starts in email field
                email_entry_widget = entry

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

        if email_entry_widget is not None:
            self.after(150, email_entry_widget.focus_set)  # move cursor into the email field
        self.after(250, self._style_login_buttons)
        self.speech.set_screen("Login screen", "Enter email and password. Use Up and Down arrows to move between buttons.")

    # starts sign-in flow
    def _sign_in(self) -> None:
        self._run_auth_action("sign_in")

    # starts account creation flow
    def _sign_up(self) -> None:
        self._run_auth_action("sign_up")

    # validates auth form + calls sign-in/sign-up api
    def _run_auth_action(self, action: str) -> None:
        # validate fields first, then call supabase auth
        try:
            username = self.username_var.get().strip()
            email = self.email_var.get().strip()
            password = self.password_var.get()
        except TclError:
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
            self.speech.announce(str(exc), interrupt=True, force=True)
            messagebox.showerror("Authentication error", str(exc))
            self.after_idle(lambda: self._focus_login_entry("password" if password else "email"))
            return
        self.show_menu()

    # builds + displays main menu ui
    def show_menu(self) -> None:
        # main app layout: left nav + right details/actions
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

        nav = ctk.CTkFrame(root, width=300, fg_color=APP_PANEL_ALT, corner_radius=14, border_width=1, border_color=APP_BORDER)
        nav.grid(row=0, column=0, sticky="nsw", padx=(16, 8), pady=16)
        nav.grid_propagate(False)

        details = ctk.CTkFrame(root, fg_color=APP_PANEL, corner_radius=14, border_width=2, border_color=APP_BORDER)
        details.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        details.grid_columnconfigure(0, weight=1)
        details.grid_rowconfigure(2, weight=1)

        mode_prefix = "Signed in as"
        display_name = self.auth_session.username or self.auth_session.email
        welcome = ctk.CTkLabel(nav, text=f"{mode_prefix} {display_name}", wraplength=220, justify="left", text_color=APP_TEXT, font=_font(17, bold=True))
        welcome.pack(anchor="w", padx=16, pady=(16, 10))

        nav_text = "Use Up/Down arrows to change pages. Press F6 to jump between the page list and the details pane."
        ctk.CTkLabel(nav, text=nav_text, justify="left", wraplength=220, text_color=APP_MUTED, font=_font(15, bold=True)).pack(anchor="w", padx=16, pady=(0, 12))

        for key in self.menu_order:
            title = PAGE_META[key]["title"]
            button = ctk.CTkButton(nav, text=title, anchor="w", command=lambda page=key: self.select_page(page, announce=True), **self._button_style_kwargs())
            button.pack(fill="x", padx=16, pady=4)
            self.speech.bind_focus(button, title, PAGE_META[key]["hint"])
            self._bind_tab_aliases(button)
            self.nav_buttons[key] = button

        self.detail_title = ctk.CTkLabel(details, text="", text_color=APP_TEXT, font=_font(26, bold=True))
        self.detail_title.grid(row=0, column=0, sticky="w", padx=24, pady=(24, 8))

        self.detail_body = ctk.CTkLabel(details, text="", wraplength=620, justify="left", anchor="w", text_color=APP_MUTED, font=_font(16, bold=True))
        self.detail_body.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))

        self.action_frame = ctk.CTkFrame(details)
        self.action_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self.action_frame.grid_columnconfigure(0, weight=1)

        self.select_page(self.current_page_key, announce=False)
        self.after(150, self._sync_keyboard_focus)
        self.speech.set_screen(
            "Main menu",
            "Use Up and Down arrows to choose a page. Press Right Arrow or Enter to activate. Press Left Arrow to go back. Press F6 to jump between panes.",
        )

    # updates selected page + redraws details/actions
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

    # clears right-side action area widgets
    def _clear_actions(self) -> None:
        for child in self.action_frame.winfo_children():
            child.destroy()
        self.action_widgets = []
        self.action_buttons = []
        self.action_index = 0

    # creates a standard action button in right panel
    def _add_action_button(self, text: str, command, hint: str) -> ctk.CTkButton:
        button = ctk.CTkButton(self.action_frame, text=text, command=command, **self._button_style_kwargs())
        button.pack(fill="x", pady=6)
        self.speech.bind_focus(button, text, hint)
        self._bind_tab_aliases(button)
        self.action_widgets.append(button)
        self.action_buttons.append(button)
        return button

    # registers externally created action button
    def _register_action_button(self, button: ctk.CTkButton, hint: str) -> None:
        text = button.cget("text")
        self.speech.bind_focus(button, text, hint)
        self._bind_tab_aliases(button)
        self.action_widgets.append(button)
        self.action_buttons.append(button)

    # shows an informational label in action area
    def _show_action_info(self, text: str) -> None:
        info = ctk.CTkLabel(
            self.action_frame,
            text=text,
            justify="left",
            anchor="w",
            wraplength=620,
        )
        info.pack(fill="x", pady=6)
        self.action_widgets.append(info)
        self.action_buttons = []

    # renders home page actions/help text
    def _render_home_actions(self) -> None:
        self._show_action_info(
            "Choose a game or account option from the left menu. Use Up and Down arrows to navigate, Enter or Space to activate."
        )

    # renders one launch button for script-based pages
    def _render_script_actions(self, page_key: str) -> None:
        meta = PAGE_META[page_key]
        self._add_action_button(
            f"Launch {meta['title']}",
            lambda path=meta["path"], title=meta["title"]: self._launch_script(path, title),
            f"Activate to launch {meta['title']}.",
        )

    # renders account page actions
    def _render_account_actions(self) -> None:
        self._add_action_button("Sign Out", self._sign_out, "Activate to sign out and return to login.")

    # routes page type to correct action renderer
    def _render_actions(self, page_key: str) -> None:
        # page type -> renderer map keeps routing simple
        self._clear_actions()
        kind = PAGE_META[page_key]["type"]
        renderers = {
            "home": self._render_home_actions,
            "script": lambda: self._render_script_actions(page_key),
            "apples": self._render_apples_actions,
            "battleship": self._render_battleship_actions,
            "scoreboard": self._render_scoreboard_actions,
            "account": self._render_account_actions,
        }
        renderer = renderers.get(kind)
        if renderer is not None:
            renderer()

    # renders battleship page controls
    def _render_battleship_actions(self) -> None:
        # room code input + host/join/stop controls
        code_label = ctk.CTkLabel(
            self.action_frame,
            text="Room code — share this with your opponent when hosting, or enter theirs to join:",
            justify="left", anchor="w", wraplength=620,
        )
        code_label.pack(anchor="w", pady=(0, 4))
        code_entry = ctk.CTkEntry(self.action_frame, textvariable=self.battleship_room_code_var, width=200, fg_color=APP_ENTRY_BG, border_color=APP_BORDER, text_color=APP_TEXT)
        code_entry.pack(anchor="w", pady=(0, 14))
        self.speech.bind_focus(code_entry, "Room code field", "Enter or read out the room code.")
        self.action_widgets.append(code_entry)

        self._add_action_button(
            "Host Game",
            self._battleship_host,
            "Starts a new game and starts the server. Your room code will appear in the field above.",
        )
        self._add_action_button(
            "Join Game",
            self._battleship_join,
            "Joins an existing game using the room code in the field above.",
        )
        self._add_action_button(
            "Stop Game",
            self._stop_battleship_server,
            "Stops the running game server.",
        )

        # small note for current host/port values
        port_note = ctk.CTkLabel(
            self.action_frame,
            text=f"Advanced: server runs on {self.client_host_var.get()}:{self.client_port_var.get()}",
            text_color=APP_MUTED, font=_font(14, bold=True),
            justify="left", anchor="w",
        )
        port_note.pack(anchor="w", pady=(10, 0))
        self.action_widgets.append(port_note)

    # starts battleship server + host client
    def _battleship_host(self) -> None:
        """Start the server and immediately launch a client as the host player."""
        if self.server_process and self.server_process.poll() is None:
            self.speech.announce("A game is already running. Stop it first.", interrupt=True, force=True)
            return

        port = self._parse_port()
        if port is None:
            return
        host = self.client_host_var.get().strip() or "127.0.0.1"

        # make short room code from host/port/time
        import hashlib, time as _t
        raw = f"{host}:{port}:{_t.time()}"
        room_code = hashlib.md5(raw.encode()).hexdigest()[:6].upper()
        self.battleship_room_code_var.set(room_code)

        server_path = BATTLESHIP_DIR / "server.py"
        relative_target = server_path.relative_to(REPO_ROOT).as_posix()
        self.server_process = subprocess.Popen(
            self._launcher_command("--run-target", relative_target, "--host", host, "--port", str(port)),
            cwd=str(REPO_ROOT),
        )

        # tiny wait so server starts before client tries connect
        self.after(600, lambda: self._launch_battleship_client(host, port, is_host=True, room_code=room_code))
        self.speech.announce(
            f"Game started. Your room code is {' '.join(room_code)}. Share it with your opponent, then tell them to join.",
            interrupt=True, force=True,
        )

    # joins existing battleship server as client
    def _battleship_join(self) -> None:
        """Join a hosted game using the room code (which maps to host:port)."""
        port = self._parse_port()
        if port is None:
            return
        host = self.client_host_var.get().strip() or "127.0.0.1"
        self._launch_battleship_client(host, port, is_host=False)

    # launches battleship client process
    def _launch_battleship_client(self, host: str, port: int, is_host: bool = False, room_code: str = "") -> None:
        client_path = BATTLESHIP_DIR / "client.py"
        relative_target = client_path.relative_to(REPO_ROOT).as_posix()

        # pass user id/name so game can report wins back
        user_id   = self.auth_session.local_id   if self.auth_session else ""
        username  = (self.auth_session.username or self.auth_session.email) if self.auth_session else "Guest"

        subprocess.Popen(
            self._launcher_command(
                "--run-target", relative_target,
                "--host", host, "--port", str(port),
                "--user-id", user_id,
                "--username", username,
                "--launcher-pid", str(subprocess.os.getpid()),
            ),
            cwd=str(REPO_ROOT),
        )
        action = "Hosting" if is_host else "Joining"
        self.speech.announce(f"{action} Battleship game.", interrupt=True, force=True)

    # launches one of pygame script files
    def _launch_script(self, script_path: Path, title: str) -> None:
        if not script_path.exists():
            message = f"Could not find {script_path.name}."
            self.speech.announce(message, interrupt=True, force=True)
            messagebox.showerror("Missing file", message)
            return
        import os
        env = os.environ.copy()
        if self.auth_session:
            env["HW_USER_ID"]  = self.auth_session.local_id
            env["HW_USERNAME"] = self.auth_session.username or self.auth_session.email
        relative_target = script_path.relative_to(REPO_ROOT).as_posix()
        subprocess.Popen(self._launcher_command("--run-target", relative_target), cwd=str(REPO_ROOT), env=env)
        self.speech.announce(f"Launching {title}.", interrupt=True, force=True)

    # parses port text field into integer
    def _parse_port(self) -> int | None:
        value = self.client_port_var.get().strip()
        try:
            return int(value)
        except ValueError:
            self.speech.announce("Port must be a number.", interrupt=True, force=True)
            messagebox.showerror("Invalid port", "Port must be a number.")
            return None

    # stops running battleship server process
    def _stop_battleship_server(self) -> None:
        if not self.server_process or self.server_process.poll() is not None:
            self.speech.announce("No game is currently running.", interrupt=True, force=True)
            return
        self.server_process.terminate()
        self.server_process = None
        self.speech.announce("Game stopped.", interrupt=True, force=True)

    # renders scoreboard page controls + list area
    def _render_scoreboard_actions(self) -> None:
        # top row game tabs + scroll area for ranking rows
        sb = self._get_scoreboard()
        if sb is None:
            info = ctk.CTkLabel(
                self.action_frame,
                text="Scoreboard unavailable — Supabase is not configured.",
                justify="left", anchor="w", wraplength=620,
            )
            info.pack(fill="x", pady=6)
            self.action_buttons = []
            return

        # game tabs across top
        selector_frame = ctk.CTkFrame(self.action_frame, fg_color="transparent")
        selector_frame.pack(fill="x", pady=(0, 12))

        for game_key, game_label in SCOREBOARD_GAMES:
            btn = ctk.CTkButton(
                selector_frame,
                text=game_label,
                width=100,
                command=lambda gk=game_key: self._load_scoreboard(gk),
                **self._button_style_kwargs(),
            )
            btn.pack(side="left", padx=4)
            self._register_action_button(btn, f"Show scoreboard for {game_label}.")

        # leaderboard list area
        self.sb_display_frame = ctk.CTkScrollableFrame(self.action_frame, fg_color=APP_BG, corner_radius=8)
        self.sb_display_frame.pack(fill="both", expand=True)

        self._add_action_button(
            "Refresh Scoreboard",
            lambda: self._load_scoreboard(self._sb_selected_game),
            "Reload the leaderboard for the current game.",
        )

        # load default tab after ui mounts
        self.after(100, lambda: self._load_scoreboard(self._sb_selected_game))

    # loads scoreboard rows for chosen game tab
    def _load_scoreboard(self, game_key: str) -> None:
        self._sb_selected_game = game_key
        sb = self._get_scoreboard()

        # clear old rows before drawing new game rows
        if not hasattr(self, "sb_display_frame") or not self.sb_display_frame.winfo_exists():
            return
        for child in self.sb_display_frame.winfo_children():
            child.destroy()

        game_label = next((lbl for gk, lbl in SCOREBOARD_GAMES if gk == game_key), game_key.title())
        title = ctk.CTkLabel(
            self.sb_display_frame,
            text=f"🏆  {game_label} — Top Players",
            font=_font(18, bold=True),
            anchor="w",
        )
        title.pack(anchor="w", padx=8, pady=(8, 12))

        rows: list[dict] = []
        if sb:
            try:
                rows = sb.top_scores(game_key, limit=10)
            except Exception as exc:
                ctk.CTkLabel(self.sb_display_frame, text=f"Error fetching scores: {exc}", anchor="w").pack(anchor="w", padx=8)
                return

        if not rows:
            ctk.CTkLabel(
                self.sb_display_frame,
                text="No scores recorded yet. Play a game to be the first on the board!",
                justify="left", anchor="w", wraplength=560,
            ).pack(anchor="w", padx=8)
            self.speech.announce(f"No scores yet for {game_label}.", interrupt=True, force=True)
            return

        # column header row
        header = ctk.CTkFrame(self.sb_display_frame, fg_color=APP_PANEL_ALT, corner_radius=6)
        header.pack(fill="x", padx=4, pady=(0, 4))
        header.grid_columnconfigure(1, weight=1)
        for col, (text, width) in enumerate([("Rank", 50), ("Player", 0), ("Wins", 60)]):
            ctk.CTkLabel(header, text=text, font=_font(15, bold=True), width=width, anchor="w").grid(
                row=0, column=col, padx=8, pady=6, sticky="w"
            )

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        announce_lines = [f"{game_label} leaderboard."]
        for rank, row in enumerate(rows, start=1):
            bg = APP_ROW_HIGHLIGHT if rank == 1 else APP_PANEL
            entry_frame = ctk.CTkFrame(self.sb_display_frame, fg_color=bg, corner_radius=6)
            entry_frame.pack(fill="x", padx=4, pady=2)
            entry_frame.grid_columnconfigure(1, weight=1)

            rank_text = f"{medals.get(rank, str(rank))}"
            uname = row.get("username", "Unknown")
            wins = row.get("wins", 0)

            ctk.CTkLabel(entry_frame, text=rank_text, width=50, anchor="w").grid(row=0, column=0, padx=8, pady=6, sticky="w")
            ctk.CTkLabel(entry_frame, text=uname, anchor="w").grid(row=0, column=1, padx=8, pady=6, sticky="w")
            ctk.CTkLabel(entry_frame, text=str(wins), width=60, anchor="e").grid(row=0, column=2, padx=8, pady=6, sticky="e")

            announce_lines.append(f"Rank {rank}: {uname}, {wins} win{'s' if wins != 1 else ''}.")

        self.speech.announce(" ".join(announce_lines), interrupt=True, force=True)

    # renders apples page controls + phase-specific ui
    def _render_apples_actions(self) -> None:
        # apples page shows code/name + phase-specific controls
        helper = ctk.CTkLabel(
            self.action_frame,
            text="Create a local game code or join an existing one. After joining, refresh to hear the latest state.",
            justify="left", anchor="w", wraplength=620,
        )
        helper.pack(fill="x", pady=(0, 10))

        code_label = ctk.CTkLabel(self.action_frame, text="Game code")
        code_label.pack(anchor="w")
        code_entry = ctk.CTkEntry(self.action_frame, textvariable=self.apples_code_var, fg_color=APP_ENTRY_BG, border_color=APP_BORDER, text_color=APP_TEXT)
        code_entry.pack(fill="x", pady=(4, 10))
        self.speech.bind_focus(code_entry, "Apples game code field", "Type a game code or create a new game.")

        name_label = ctk.CTkLabel(self.action_frame, text="Player name")
        name_label.pack(anchor="w")
        name_entry = ctk.CTkEntry(self.action_frame, textvariable=self.apples_name_var, fg_color=APP_ENTRY_BG, border_color=APP_BORDER, text_color=APP_TEXT)
        name_entry.pack(fill="x", pady=(4, 10))
        self.speech.bind_focus(name_entry, "Apples player name field", "Type your player name before joining.")

        self.action_widgets.extend([code_entry, name_entry])

        button_row = ctk.CTkFrame(self.action_frame, fg_color="transparent")
        button_row.pack(fill="x", pady=(0, 12))
        button_row.grid_columnconfigure((0, 1, 2), weight=1)

        create_button = ctk.CTkButton(button_row, text="Create Game", command=self._apples_create_game, **self._button_style_kwargs())
        create_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self._register_action_button(create_button, "Activate to create a new Apples to Apples game code.")

        join_button = ctk.CTkButton(button_row, text="Join Game", command=self._apples_join_game, **self._button_style_kwargs())
        join_button.grid(row=0, column=1, padx=6, sticky="ew")
        self._register_action_button(join_button, "Activate to join the current game code as the entered player name.")

        refresh_button = ctk.CTkButton(button_row, text="Refresh State", command=self._refresh_apples_page, **self._button_style_kwargs())
        refresh_button.grid(row=0, column=2, padx=(6, 0), sticky="ew")
        self._register_action_button(refresh_button, "Activate to reload Apples to Apples game state.")

        game = self._current_apples_game()
        if not game:
            info = ctk.CTkLabel(
                self.action_frame,
                text="No current Apples game selected. Create a game or enter a code and join.",
                justify="left", anchor="w", wraplength=620,
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
                f"Code: {game['code']}\nPhase: {game['phase']}\nRound: {game['round_num']}\n"
                f"Judge: {judge_name}\nPrompt: {game['green'] or '(none)'}\nLast update: {game['last_msg']}"
            ),
            justify="left", anchor="w", wraplength=620,
        )
        status.pack(fill="x", pady=(8, 12))

        ctk.CTkLabel(self.action_frame, text="Players", font=_font(18, bold=True)).pack(anchor="w")
        for player in roster:
            tag = []
            if game["judge_pid"] and int(player["id"]) == int(game["judge_pid"]):
                tag.append("Judge")
            if me and int(player["id"]) == int(me["id"]):
                tag.append("You")
            suffix = f" ({', '.join(tag)})" if tag else ""
            ctk.CTkLabel(self.action_frame, text=f"- {player['name']}{suffix}: {player['score']}", anchor="w", justify="left").pack(fill="x")

        if game["phase"] == "lobby":
            start_button = self._add_action_button(
                "Start Apples Game", self._apples_start_game,
                "Activate to start Apples to Apples after at least two players have joined.",
            )
            if len(roster) < 2:
                start_button.configure(state="disabled")
            return

        if not me:
            ctk.CTkLabel(self.action_frame, text="You have not joined this Apples game yet.", justify="left", anchor="w", wraplength=620).pack(fill="x", pady=(12, 0))
            return

        round_num = int(game["round_num"])
        if game["phase"] == "selecting":
            if is_judge:
                ctk.CTkLabel(self.action_frame, text="You are the judge. Wait for all players to submit their cards, then refresh.", justify="left", anchor="w", wraplength=620).pack(fill="x", pady=(12, 0))
            else:
                ctk.CTkLabel(self.action_frame, text="Your hand", font=_font(18, bold=True)).pack(anchor="w", pady=(12, 6))
                hand = apples_service.get_hand(game_id, int(me["id"]))
                for index, card in enumerate(hand[:apples_service.HAND_SIZE], start=1):
                    btn = ctk.CTkButton(self.action_frame, text=f"Card {index}: {card}", command=lambda selected=card: self._apples_select_card(selected), **self._button_style_kwargs())
                    btn.pack(fill="x", pady=3)
                    self._register_action_button(btn, card)
                selected_text = self.apples_selected_card or "No card selected."
                ctk.CTkLabel(self.action_frame, text=f"Selected: {selected_text}", justify="left", anchor="w", wraplength=620).pack(fill="x", pady=(10, 6))
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
                ctk.CTkLabel(self.action_frame, text="Waiting for the judge to pick a winner. Press Refresh State to hear updates.", justify="left", anchor="w", wraplength=620).pack(fill="x", pady=(12, 0))
            else:
                ctk.CTkLabel(self.action_frame, text="Judge submissions", font=_font(18, bold=True)).pack(anchor="w", pady=(12, 6))
                submissions = apples_service.list_submissions(game_id, round_num)
                if not submissions:
                    ctk.CTkLabel(self.action_frame, text="No submissions yet.", justify="left", anchor="w").pack(fill="x")
                else:
                    for index, card in enumerate(submissions, start=1):
                        btn = ctk.CTkButton(self.action_frame, text=f"Winner option {index}: {card}", command=lambda selected=card: self._apples_pick_winner(game_id, round_num, int(me["id"]), selected), **self._button_style_kwargs())
                        btn.pack(fill="x", pady=3)
                        self._register_action_button(btn, card)
            return

        if game["phase"] == "game_over":
            ctk.CTkLabel(self.action_frame, text="Game over. Review the scores above or create a new game.", justify="left", anchor="w", wraplength=620).pack(fill="x", pady=(12, 0))

    # gets current apples game from typed code
    def _current_apples_game(self):
        code = self.apples_code_var.get().strip().upper()
        if not code:
            return None
        return apples_service.game_by_code(code)

    # refreshes apples page + clears temporary picks
    def _refresh_apples_page(self) -> None:
        # clear local selections + redraw apples page
        self.apples_selected_card = None
        self.apples_judge_choice = None
        self.select_page("apples", announce=False)
        self.speech.announce("Apples to Apples state refreshed.", interrupt=True, force=True)

    # creates new apples game code
    def _apples_create_game(self) -> None:
        code = apples_service.create_game(points_to_win=5)
        self.apples_code_var.set(code)
        self.apples_token = ""
        self.apples_selected_card = None
        self.select_page("apples", announce=False)
        self.speech.announce(f"Created Apples to Apples game {code}.", interrupt=True, force=True)

    # joins apples game with code + player name
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

    # starts apples game after lobby stage
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

    # stores currently selected apples card
    def _apples_select_card(self, card: str) -> None:
        self.apples_selected_card = card
        self.select_page("apples", announce=False)
        self.speech.announce(f"Selected card: {card}", interrupt=True, force=True)

    # submits selected apples card for this round
    def _apples_submit_card(self, game_id: int, round_num: int, player_id: int, judge_id: int) -> None:
        if not self.apples_selected_card:
            self.speech.announce("Select a card before submitting.", interrupt=True, force=True)
            return
        try:
            apples_service.submit_card(game_id, round_num, player_id, judge_id, self.apples_selected_card)
        except Exception:
            pass
        submitted_card = self.apples_selected_card
        self.apples_selected_card = None
        self.select_page("apples", announce=False)
        self.speech.announce(f"Submitted card: {submitted_card}", interrupt=True, force=True)

    # chooses winning apples card as judge
    def _apples_pick_winner(self, game_id: int, round_num: int, judge_id: int, winning_card: str) -> None:
        try:
            apples_service.judge_pick(game_id, round_num, judge_id, winning_card)
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            messagebox.showerror("Judge pick failed", str(exc))
            return
        self.select_page("apples", announce=False)
        self.speech.announce(f"Selected winning card: {winning_card}", interrupt=True, force=True)

    # clears auth session + returns to login screen
    def _sign_out(self) -> None:
        self.auth_session = None
        self.speech.announce("Signed out.", interrupt=True, force=True)
        self.after_idle(self.show_login)

    # closes launcher + stops background server if running
    def _on_close(self) -> None:
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
        self.destroy()


    # runs launcher app event loop
def main() -> None:
    app = GameSpaceApp()
    app.mainloop()


if __name__ == "__main__":
    main()