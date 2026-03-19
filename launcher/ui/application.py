"""
app.py is the main app file for the HelloWorld GameSpace launcher. 
It's a desktop app built with customtkinter (UI toolkit) that serves as the hub for: 
- launching various accessible games 
- viewing the community scoreboard
- managing user accounts 
It integrates with Supabase for authentication and data storage.
Finally, it includes features like keyboard navigation and text-to-speech accessibility support.
"""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from launcher.services.speech import SpeechManager
from launcher.services import apples_service
from launcher.services.auth_client import AuthSession, AuthClient
from launcher.ui.action_pages import ActionsMixin
from launcher.ui.login_flow import LoginMixin
from launcher.ui.navigation_flow import NavigationMixin
from launcher.services.leaderboard import Scoreboard
from launcher.ui.theme import (
    APP_ACCENT,
    APP_ACCENT_SOFT,
    APP_ACCENT_STRONG,
    APP_BG,
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
    APP_ROW_HIGHLIGHT,
    APP_TEXT,
    _font,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GAMES_DIR = REPO_ROOT / "games"
GAME_LOGIC_DIR = GAMES_DIR / "game_logic"
BATTLESHIP_DIR = GAMES_DIR / "Battleship"


def _script_page(title: str, description: str, path: Path) -> dict[str, object]:
    return {
        "title": title,
        "description": description,
        "hint": f"{title}. Press the Right Arrow key to play {title}.",
        "type": "script",
        "path": path,
    }


def _simple_page(title: str, description: str, action_hint: str, page_type: str) -> dict[str, str]:
    return {
        "title": title,
        "description": description,
        "hint": f"{title}. Press the Right Arrow key to {action_hint}.",
        "type": page_type,
    }

PAGE_META = {
    "home": {
        "title": "Home",
        "description": "Welcome to HelloWorld GameSpace. Use Up and Down arrows to choose a page. Press Right Arrow or Enter to move to the action buttons.",
        "hint": "Home page. Press Right Arrow or Enter to view page controls.",
        "type": "home",
    },
    "hangman": _script_page("Hangman", "Launches the pygame Hangman game.", GAME_LOGIC_DIR / "hangman_game.py"),
    "maze": _script_page("Maze Game", "Launches the accessible pygame maze game with spoken movement.", GAME_LOGIC_DIR / "maze_game.py"),
    "madlibs": _script_page("Mad Libs", "Launches the accessible pygame Mad Libs game.", GAME_LOGIC_DIR / "madlibs_game.py"),
    "escape": _script_page("Escape Room", "Launches the accessible Escape Room adventure game.", GAME_LOGIC_DIR / "escape_room_game.py"),
    "connect4": _script_page("Connect 4", "Launches the accessible pygame Connect 4 game.", GAME_LOGIC_DIR / "c4_game.py"),
    "apples": _simple_page(
        "Apples to Apples",
        "Native desktop Apples to Apples using the existing SQLite-backed game logic.",
        "open Apples to Apples",
        "apples",
    ),
    "battleship": _simple_page(
        "Battleship",
        "Host a new game and share your room code, or join a friend's game with their code.",
        "open Battleship options",
        "battleship",
    ),
    "scoreboard": _simple_page(
        "Scoreboard",
        "Community leaderboard - top wins across all HelloWorld games.",
        "view the Scoreboard",
        "scoreboard",
    ),
    "account": _simple_page("Account", "Sign out of your account.", "manage your account", "account"),
}

MENU_ORDER = [
    "home", "hangman", "maze", "madlibs", "escape",
    "connect4", "apples", "battleship", "scoreboard", "account",
]

SCOREBOARD_GAMES = [
    ("battleship", "Battleship"),
    ("hangman",    "Hangman"),
    ("maze",       "Maze Game"),
    ("escape",     "Escape Room"),
    ("connect4",   "Connect 4"),
    ("apples",     "Apples to Apples"),
]

class GameSpaceApp(ActionsMixin, NavigationMixin, LoginMixin, ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("dark-blue")

        self.title("HelloWorld GameSpace Launcher")
        self._set_initial_window_size()
        self.configure(fg_color=APP_BG)

        self.auth_client = AuthClient.from_workspace(REPO_ROOT)

        if not self.auth_client.is_configured():
            raise RuntimeError("Supabase auth is required. Configure supabase_project.py before launching.")
        
        self.speech = SpeechManager(on_announce=self._set_status)
        self.auth_session: AuthSession | None = None
        self.server_process: subprocess.Popen | None = None
        self.current_screen = "startup"
        self.current_page_key = "home"
        self.page_meta = PAGE_META
        self.repo_root = REPO_ROOT
        self.battleship_dir = BATTLESHIP_DIR
        self.scoreboard_games = SCOREBOARD_GAMES
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
        self.login_focus_order: list[tk.Widget] = []
        self.login_focus_index: int = 0
        self._content_wraplength = 620

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
            wraplength=900,
            text_color=APP_TEXT,
            font=_font(18, bold=True),
        )
        self.status_label.pack(fill="x", padx=24, pady=(0, 16))

        self.bind("<Configure>", self._on_window_resize, add="+")

        self._bind_global_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        apples_service.init()

        self.show_login()

    def _set_initial_window_size(self) -> None:
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        origin_x = 0
        origin_y = 0

        if sys.platform.startswith("win"):
            try:
                import ctypes
                from ctypes import wintypes

                rect = wintypes.RECT()
                SPI_GETWORKAREA = 0x0030
                if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                    origin_x = rect.left
                    origin_y = rect.top
                    screen_width = rect.right - rect.left
                    screen_height = rect.bottom - rect.top
            except Exception:
                pass

        width = max(720, min(screen_width - 40, int(screen_width * 0.96)))
        height = max(560, min(screen_height - 60, int(screen_height * 0.94)))
        min_width = min(960, width)
        min_height = min(640, height)
        x = origin_x + max(0, (screen_width - width) // 2)
        y = origin_y + max(0, (screen_height - height) // 2)

        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min_width, min_height)

    def _get_scoreboard(self) -> "Scoreboard | None":
        if self._scoreboard is None:
            try:
                token = self.auth_session.id_token if self.auth_session else ""
                self._scoreboard = Scoreboard.from_workspace(REPO_ROOT, id_token=token)
            except Exception:
                return None
        return self._scoreboard

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

    def _launcher_command(self, *extra_args: str) -> list[str]:
        return [sys.executable, str(REPO_ROOT / "launch_gamespace.py"), *extra_args]

    def _set_status(self, text: str) -> None:
        self.status_var.set(f"Last message: {text}")

    def _on_window_resize(self, _event=None) -> None:
        self._update_wraplengths()

    def _update_wraplengths(self) -> None:
        width = max(720, self.winfo_width())
        status_wrap = max(360, width - 120)
        detail_wrap = max(320, width - 500)
        login_wrap = max(320, width - 220)
        nav_wrap = 220
        self._content_wraplength = detail_wrap

        try:
            self.status_label.configure(wraplength=status_wrap)
        except Exception:
            pass

        for attr, wrap in [
            ("detail_body", detail_wrap),
            ("_login_summary_label", login_wrap),
            ("_nav_help_label", nav_wrap),
            ("_apples_helper_label", detail_wrap),
            ("_apples_status_label", detail_wrap),
        ]:
            widget = getattr(self, attr, None)
            if widget is not None:
                try:
                    widget.configure(wraplength=wrap)
                except Exception:
                    pass

    def _clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        self.nav_buttons = {}
        self.action_widgets = []
        self.action_buttons = []
        self.login_action_buttons = []
        self.login_action_index = 0
        self.login_focus_order = []
        self.login_focus_index = 0
        self.action_index = 0
        self.nav_mode = True

    def _bind_global_keys(self) -> None:
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

    def _bind_tab_aliases(self, widget: tk.Widget) -> None:
        widget.bind("<Shift-Tab>", lambda event: self._handle_vertical(-1), add="+")
        widget.bind("<Tab>", lambda event: self._handle_vertical(1), add="+")

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

    def _handle_repeat(self, _event=None):
        self.speech.repeat_last()
        return "break"

    def _handle_where_am_i(self, _event=None):
        self.speech.where_am_i()
        return "break"

    def _handle_escape(self, _event=None):
        self.speech.announce("Escape key was hit, so closing gamespace... goodbye!", interrupt=True, force=True)
        self.after(5000, self._on_close)
        return "break"

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

    def _sign_out(self) -> None:
        self.auth_session = None
        self.speech.announce("Signed out.", interrupt=True, force=True)
        self.after_idle(self.show_login)

    def _on_close(self) -> None:
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
        self.destroy()


def main() -> None:
    app = GameSpaceApp()
    app.mainloop()


if __name__ == "__main__":
    main()
