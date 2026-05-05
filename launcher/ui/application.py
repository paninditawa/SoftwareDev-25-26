"""
app.py is the main app file for the HelloWorld GameSpace launcher. 
It's a desktop app built with customtkinter (UI toolkit) that serves as the hub for: 
- launching various accessible games 
- viewing the community scoreboard
- managing user accounts 
It integrates with Supabase for authentication and data storage.
Finally, it includes features like keyboard navigation and text-to-speech accessibility support.
"""

# annotations keeps type hints as strings (avoids forward-reference issues)
from __future__ import annotations

# subprocess launches game processes without blocking the launcher
import subprocess
# sys gives access to the Python runtime (e.g. the executable path)
import sys
# tkinter is the base GUI library; customtkinter wraps it with nicer widgets
import tkinter as tk
# Path provides safe, OS-independent file/folder path handling
from pathlib import Path
# messagebox shows native pop-up dialogs (errors, confirmations)
from tkinter import messagebox

# customtkinter provides modern-looking widgets on top of tkinter
import customtkinter as ctk

# SpeechManager handles all text-to-speech announcements
from launcher.services.speech import SpeechManager
# apples_service manages the Apples to Apples SQLite database
from launcher.services import apples_service
# AuthSession holds logged-in user data; AuthClient talks to Supabase
from launcher.services.auth_client import AuthSession, AuthClient
# ActionsMixin provides all game-panel UI methods
from launcher.ui.action_pages import ActionsMixin
# LoginMixin provides the login / sign-up screen
from launcher.ui.login_flow import LoginMixin
# NavigationMixin provides keyboard navigation handlers
from launcher.ui.navigation_flow import NavigationMixin
# Scoreboard reads and writes win counts on Supabase
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
from launcher.services.chat_service import ChatService

# project root is three levels up from this file (launcher/ui/application.py)
REPO_ROOT = Path(__file__).resolve().parents[2]
# paths to the top-level games folder and its subfolders
GAMES_DIR = REPO_ROOT / "games"
GAME_LOGIC_DIR = GAMES_DIR / "game_logic"
BATTLESHIP_DIR = GAMES_DIR / "Battleship"


def _script_page(title: str, description: str, path: Path) -> dict[str, object]:
    # builds a PAGE_META entry for pages that launch an external .py script
    return {
        "title": title,
        "description": description,
        "hint": f"Press the Right Arrow key to play {title}.",
        "type": "script",
        "path": path,
    }


def _simple_page(title: str, description: str, action_hint: str, page_type: str) -> dict[str, str]:
    # builds a PAGE_META entry for pages that are handled entirely inside the launcher
    return {
        "title": title,
        "description": description,
        "hint": f"Press the Right Arrow key to {action_hint}.",
        "type": page_type,
    }

# PAGE_META stores display text and routing info for every page in the left nav
PAGE_META = {
    "home": {
        "title": "Home",
        "description": "Welcome to HelloWorld GameSpace. Use Up and Down arrows to choose a page. Press Right Arrow or Enter to move to the action buttons.",
        "hint": "Press Right Arrow or Enter to view page controls.",
        "type": "home",
    },
    "hangman": _script_page("Hangman", "Launches the pygame Hangman game.", GAME_LOGIC_DIR / "hangman_game.py"),
    "maze": _script_page("Maze Game", "Launches the accessible pygame maze game with spoken movement.", GAME_LOGIC_DIR / "maze_game.py"),
    "madlibs": _script_page("Mad Libs", "Launches the accessible pygame Mad Libs game.", GAME_LOGIC_DIR / "madlibs_game.py"),
    "escape": _script_page("Escape Room", "Launches the accessible Escape Room adventure game.", GAME_LOGIC_DIR / "escape_room_game.py"),
    "connect4": _script_page("Connect 4", "Launches the accessible pygame Connect 4 game.", GAME_LOGIC_DIR / "c4_game.py"),
    "apples": _simple_page(
        "Apples to Apples",
        "Host a new game and share your room code, or join a friend's game with their code.",
        "Press enter to launch Apples to Apples",
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
    "chat": _simple_page(
        "Chat",
        "Community chat for all games - share tips, strategies, and connect with other players.",
        "open the community chat",
        "chat",
    ),
    "account": _simple_page("Account", "Sign out of your account.", "manage your account", "account"),
}

# MENU_ORDER controls the order pages appear in the left-hand navigation list
MENU_ORDER = [
    "home", "hangman", "maze", "madlibs", "escape",
    "connect4", "apples", "battleship", "scoreboard", "chat", "account",
]

# SCOREBOARD_GAMES lists (page_key, display_label) pairs shown on the scoreboard page
SCOREBOARD_GAMES = [
    ("battleship", "Battleship"),
    ("hangman",    "Hangman"),
    ("maze",       "Maze Game"),
    ("escape",     "Escape Room"),
    ("connect4",   "Connect 4"),
    ("apples",     "Apples to Apples"),
]

# GameSpaceApp is the main application window — it mixes in navigation, login, and action logic
class GameSpaceApp(ActionsMixin, NavigationMixin, LoginMixin, ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        # use the light theme and a dark-blue accent colour
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("dark-blue")

        self.title("HelloWorld GameSpace Launcher")
        self._set_initial_window_size()
        self.configure(fg_color=APP_BG)

        # AuthClient reads Supabase credentials so users can sign in
        self.auth_client = AuthClient.from_workspace(REPO_ROOT)

        if not self.auth_client.is_configured():
            raise RuntimeError("Supabase auth is required. Configure supabase_project.py before launching.")
        
        # SpeechManager handles all spoken announcements for blind users
        self.speech = SpeechManager(on_announce=self._set_status)
        # auth_session holds user data once someone signs in (None = logged out)
        self.auth_session: AuthSession | None = None
        # server_process tracks the Battleship server subprocess (None when not running)
        self.server_process: subprocess.Popen | None = None
        # current_screen tracks which top-level view is visible ("login", "menu", etc.)
        self.current_screen = "startup"
        # current_page_key is the selected left-nav item key
        self.current_page_key = "home"
        self.page_meta = PAGE_META
        self.repo_root = REPO_ROOT
        self.battleship_dir = BATTLESHIP_DIR
        self.scoreboard_games = SCOREBOARD_GAMES
        self.menu_order = list(MENU_ORDER)
        # nav_index is the position of the selected page in the left nav list
        self.nav_index = self.menu_order.index("home")
        # action_index is the position of the selected button in the right action panel
        self.action_index = 0
        # nav_mode = True means keyboard focus is in the left nav; False = right panel
        self.nav_mode = True
        # nav_buttons maps page keys to their left-nav CTkButton widgets
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        # action_widgets includes all interactive widgets in the right panel
        self.action_widgets: list[tk.Widget] = []
        # action_buttons is the subset of action_widgets that can be activated with Enter
        self.action_buttons: list[ctk.CTkButton] = []
        # login_* variables track focus state on the login screen
        self.login_action_buttons: list[ctk.CTkButton] = []
        self.login_entries: dict[str, ctk.CTkEntry] = {}
        self.login_action_index = 0
        self.login_focus_order: list[tk.Widget] = []
        self.login_focus_index: int = 0
        # max pixel width for text labels in the right-side content panel
        self._content_wraplength = 620

        # StringVars are tkinter's observable string values; bound to entry fields
        self.status_var = tk.StringVar(value="Ready.")
        self.username_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.client_host_var = tk.StringVar(value="127.0.0.1")
        self.client_port_var = tk.StringVar(value="5555")
        self.battleship_room_code_var = tk.StringVar()
        self.apples_code_var = tk.StringVar()
        self.apples_name_var = tk.StringVar()
        # apples_token is the player auth token returned by the Apples game server
        self.apples_token = ""
        # these track what card the user has selected in the Apples game UI
        self.apples_selected_card: str | None = None
        self.apples_judge_choice: str | None = None
        self.apples_screen = "home" # sets the current screen within the Apples game
        self.apples_game_id: int | None = None # the current Apples game ID
        self._apples_realtime_subscribed = False # real-time updates for the Apples game
        self._apples_refresh_button: ctk.CTkButton | None = None # the Refresh State button in the Apples UI
        self._apples_helper_label = None # in Apples UI; gives instructions or feedback based on the game state
        self._apples_status_label = None # in Apples UI; shows the current prompt, judge, round, etc.
        self._apples_info_label = None # in Apples UI; shows info about the user's hand, points, etc.


        # cached Scoreboard client (created on first use)
        self._scoreboard: "Scoreboard | None" = None
        # which game's scores to show when the scoreboard tab is open
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

        # re-calculate text wrap widths whenever the window is resized
        self.bind("<Configure>", self._on_window_resize, add="+")

        # attach all keyboard shortcuts (arrows, enter, space, escape, f, j)
        self._bind_global_keys()
        # intercept the window's X button so cleanup code runs before closing
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # show the login screen as the first thing the user sees
        self.show_login()

        # Initialize chat service
        self.chat_service = ChatService.from_workspace(
            Path(__file__).parent.parent, 
            id_token=session.id_token if (session := self.auth_session) else "",)

    def _set_initial_window_size(self) -> None:
        # start with tkinter's reported screen dimensions as a fallback
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
                # SPI_GETWORKAREA returns the usable desktop area (excludes taskbar)
                if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                    origin_x = rect.left
                    origin_y = rect.top
                    screen_width = rect.right - rect.left
                    screen_height = rect.bottom - rect.top
            except Exception:
                pass

        # calculate a window size that fills most of the screen, with minimum limits
        width = max(720, min(screen_width - 40, int(screen_width * 0.96)))
        height = max(560, min(screen_height - 60, int(screen_height * 0.94)))
        min_width = min(960, width)
        min_height = min(640, height)
        # centre the window on the usable desktop area
        x = origin_x + max(0, (screen_width - width) // 2)
        y = origin_y + max(0, (screen_height - height) // 2)

        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min_width, min_height)

    def _get_scoreboard(self) -> "Scoreboard | None":
        # create and cache a Scoreboard client on first call; return None if unavailable
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
        # returns a shell command that re-invokes the launcher with extra arguments
        return [sys.executable, str(REPO_ROOT / "launch_gamespace.py"), *extra_args]

    def _set_status(self, text: str) -> None:
        # writes the latest TTS message into the status bar at the bottom of the window
        self.status_var.set(f"Last message: {text}")

    def _on_window_resize(self, _event=None) -> None:
        # called whenever the window is resized; update text wrap widths to match
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
        self.bind_all("<f>", self._handle_help, add="+")
        self.bind_all("<j>", self._handle_repeat, add="+")

    def _bind_tab_aliases(self, widget: tk.Widget) -> None:
        widget.bind("<Shift-Tab>", lambda event: self._handle_vertical(-1), add="+")
        widget.bind("<Tab>", lambda event: self._handle_vertical(1), add="+")

    def _handle_help(self, _event=None):
        if self.current_screen == "login":
            self.speech.announce(
                "Login screen help. Use Up and Down arrows to move between buttons. Press Enter or Space to select. "
                "Username is required when creating a new account. "
                "Press F to hear help again. Press J to repeat the last announcement.",
                interrupt=True, force=True,
            )
        elif self.current_screen == "menu":
            self.speech.announce(
                "Menu help. Use Up and Down arrows to move between pages. Press Right Arrow or Enter to move into action buttons. "
                "Press Left Arrow to return to the page list. "
                "Press F to hear help again. Press J to repeat the last announcement.",
                interrupt=True, force=True,
            )
            if self.current_page_key == "apples":   # extra help for the Apples page
                if self.apples_screen == "home":
                    self.speech.announce(
                        "Apples home help. Use Up and Down arrows to move between buttons. Create or join a game. Start the game when ready. Open the live game page after starting.",
                        interrupt=True, force=True,
                )
                else:
                    self.speech.announce(
                        "Apples game help. Use Up and Down arrows to move through controls and cards. Press Enter or Space to select. Press Q to return to Apples home.",
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
    
    # allows for players to press Q to return to the Apples homepage
    def _handle_apples_back_home(self, _event=None):
        if self.current_screen == "menu" and self.current_page_key == "apples" and self.apples_screen == "game":
            self.apples_screen = "home"
            self.select_page("apples", announce=False)
            self.speech.announce("Returned to Apples home page.", interrupt=True, force=True)
            return "break"
        return None
    
    def _render_apples_actions(self) -> None:
        if self.apples_screen == "game":
            self._render_apples_game_screen()
        else:
            self._render_apples_home_screen()


    def _render_apples_home_screen(self) -> None:
        helper = ctk.CTkLabel(
            self.action_frame,
            text=(
                "Apples to Apples home. Use Up and Down arrows to move between controls. "
                "Press Enter or Space to select. Create a game or type a code and join. "
                "Press Start Game when everyone is ready. Open Game Page moves to the live game page. "
                "Press Q during the live game to return here."
            ),
            justify="left",
            anchor="w",
            wraplength=self._content_wraplength,
        )
        helper.pack(fill="x", pady=(0, 12))
        self._apples_helper_label = helper


        ctk.CTkLabel(self.action_frame, text="Game code", text_color=APP_TEXT, font=_font(15, bold=True)).pack(anchor="w")
        code_entry = ctk.CTkEntry(
            self.action_frame,
            textvariable=self.apples_code_var,
            fg_color=APP_ENTRY_BG,
            border_color=APP_BORDER,
            text_color=APP_TEXT,
        )
        code_entry.pack(fill="x", pady=(4, 10))
        self.speech.bind_focus(code_entry, "Apples game code field", "Type a game code to join or reopen a game.")
        self.action_widgets.append(code_entry)


        player_name = self.auth_session.username or self.auth_session.email
        player_info = ctk.CTkLabel(
            self.action_frame,
            text=f"Player: {player_name}",
            justify="left",
            anchor="w",
            text_color=APP_TEXT,
            font=_font(15, bold=True),
        )
        player_info.pack(anchor="w", pady=(0, 8))
        self.action_widgets.append(player_info)


        self._add_action_button("Read Instructions", self._apples_read_instructions, "Hear Apples to Apples game instructions.")
        self._add_action_button("Create Game", self._apples_create_game, "Create a new Apples to Apples game code.")
        self._add_action_button("Join Game", self._apples_join_game, "Join the current Apples to Apples game code.")
        self._add_action_button("Start Game", self._apples_start_game, "Start the current Apples to Apples game.")
        self._add_action_button("Open Game Page", lambda: self._apples_open_game(announce=True), "Open the separate live Apples to Apples game page.")


        game = self._current_apples_game()
        if not game:
            info = ctk.CTkLabel(
                self.action_frame,
                text="No Apples to Apples game selected yet. Create a game or type a code and join.",
                justify="left",
                anchor="w",
                wraplength=self._content_wraplength,
            )
            info.pack(fill="x", pady=(10, 0))
            self._apples_info_label = info
            return


        roster = apples_service.players(int(game["id"]))
        judge_name = next(
            (p["name"] for p in roster if game.get("judge_pid") and int(p["id"]) == int(game["judge_pid"])),
            "—",
        )

        status = ctk.CTkLabel(
            self.action_frame,
            text=(
                f"Current code: {game['code']}\n"
                f"Phase: {game['phase']}\n"
                f"Round: {game['round_num']}\n"
                f"Judge: {judge_name}\n"
                f"Prompt: {game['green'] or '(none yet)'}\n"
                f"Last update: {game['last_msg']}"
                "Use the up and down arrow keys to hear the card options, then press Enter or Space to select a card."
            ),
            justify="left",
            anchor="w",
            wraplength=self._content_wraplength,
        )
        status.pack(fill="x", pady=(12, 10))
        self._apples_status_label = status


        ctk.CTkLabel(self.action_frame, text="Players", font=_font(18, bold=True)).pack(anchor="w")
        for player in roster:
            suffix = " (Judge)" if game.get("judge_pid") and int(player["id"]) == int(game["judge_pid"]) else ""
            ctk.CTkLabel(
                self.action_frame,
                text=f"- {player['name']}{suffix}: {player['score']}",
                anchor="w",
                justify="left",
            ).pack(fill="x")


    def _apples_skip_round(self, game_id: int, round_num: int, judge_id: int) -> None:
        try:
            apples_service.skip_round(game_id, round_num, judge_id)
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            return


        self._apples_open_game(announce=False)
        self.after(150, lambda: self.speech.announce("No point awarded. Round skipped.", interrupt=True, force=True))
        self.after(350, self._announce_apples_state)


    def _render_apples_game_screen(self) -> None:
        game = self._current_apples_game()
        if not game:
            self.apples_screen = "home"
            self._render_apples_home_screen()
            return


        game_id = int(game["id"])
        roster = apples_service.players(game_id)
        me = apples_service.my_player(game_id, self.apples_token) if self.apples_token else None
        judge_name = next(
            (p["name"] for p in roster if game.get("judge_pid") and int(p["id"]) == int(game["judge_pid"])),
            "—",
        )
        is_judge = bool(game.get("judge_pid")) and me and int(me["id"]) == int(game["judge_pid"])


        helper = ctk.CTkLabel(
            self.action_frame,
            text=(
                "Live Apples game page. Press Q to return to Apples home. "
                "Use Up and Down arrows to move between controls. Press Enter or Space to select."
            ),
            justify="left",
            anchor="w",
            wraplength=self._content_wraplength,
        )
        helper.pack(fill="x", pady=(0, 10))
        self._apples_helper_label = helper


        top_row = ctk.CTkFrame(self.action_frame, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 12))
        top_row.grid_columnconfigure((0, 1, 2), weight=1)


        repeat_button = ctk.CTkButton(top_row, text="Read Game State", command=self._announce_apples_state, **self._button_style_kwargs())
        repeat_button.grid(row=0, column=0, padx=(6, 0), sticky="ew")
        self._register_action_button(repeat_button, "Hear the current round, prompt, and role.")


        refresh_button = ctk.CTkButton(top_row, text="Refresh State", command=self._refresh_apples_page, **self._button_style_kwargs())
        refresh_button.grid(row=0, column=1, padx=(0, 6), sticky="ew")
        self._register_action_button(refresh_button, "Reload the current Apples game state.")
        self._apples_refresh_button = refresh_button


        home_button = ctk.CTkButton(top_row, text="Back to Apples Home", command=lambda: self._handle_apples_back_home(), **self._button_style_kwargs())
        home_button.grid(row=0, column=2, padx=6, sticky="ew")
        self._register_action_button(home_button, "Return to Apples home page.")


        round_label = ctk.CTkLabel(
            self.action_frame,
            text=f"Round {game['round_num']} — Judge: {judge_name}",
            justify="left",
            anchor="w",
            wraplength=self._content_wraplength,
            font=_font(18, bold=True),
        )
        round_label.pack(fill="x", pady=(4, 0))


        prompt_label = ctk.CTkLabel(
            self.action_frame,
            text=f"Prompt: {game['green'] or '(no prompt yet)'}",
            justify="left",
            anchor="w",
            wraplength=self._content_wraplength,
        )
        prompt_label.pack(fill="x", pady=(0, 8))


        status = ctk.CTkLabel(
            self.action_frame,
            text=(
                f"Code: {game['code']}\n"
                f"Phase: {game['phase']}\n"
                f"Last update: {game['last_msg']}"
            ),
            justify="left",
            anchor="w",
            wraplength=self._content_wraplength,
        )
        status.pack(fill="x", pady=(0, 12))
        self._apples_status_label = status


        ctk.CTkLabel(self.action_frame, text="Players", font=_font(18, bold=True)).pack(anchor="w")
        for player in roster:
            tags = []
            if game.get("judge_pid") and int(player["id"]) == int(game["judge_pid"]):
                tags.append("Judge")
            if me and int(player["id"]) == int(me["id"]):
                tags.append("You")
            suffix = f" ({', '.join(tags)})" if tags else ""
            ctk.CTkLabel(
                self.action_frame,
                text=f"- {player['name']}{suffix}: {player['score']}",
                anchor="w",
                justify="left",
            ).pack(fill="x")


        if not me:
            self._show_action_info("You have not joined this game yet. Press Q to return home and join the game.")
            return


        round_num = int(game["round_num"])


        if game["phase"] == "lobby":
            self._show_action_info("Game is still in the lobby. Press Q to return home and start the game.")
            return


        if game["phase"] == "selecting":
            if is_judge:
                self._show_action_info("You are the judge. Wait for the other player to submit, then press Refresh State or Read Game State.")
            else:
                self._show_action_info("You are a player. Move to a card and press Enter or Space to submit it immediately.")
                hand = apples_service.get_hand(game_id, int(me["id"]))
                for index, card in enumerate(hand[:10], start=1):
                    btn = ctk.CTkButton(
                        self.action_frame,
                        text=f"Card {index}: {card}",
                        command=lambda selected=card, gid=game_id, rn=round_num, pid=int(me["id"]), jid=int(game["judge_pid"]): self._apples_select_and_submit(gid, rn, pid, jid, selected),
                        **self._button_style_kwargs(),
                    )
                    btn.pack(fill="x", pady=3)
                    self.action_widgets.append(btn)
                    self.action_buttons.append(btn)
            return


        if game["phase"] == "judging":
            if not is_judge:
                self._show_action_info("Waiting for the judge to pick a winner. Press Refresh State or Read Game State.")
            else:
                self._show_action_info("You are the judge. Move to a winning card and press Enter or Space.")
                submissions = apples_service.list_submissions(game_id, round_num)
                skip_btn = ctk.CTkButton(
                    self.action_frame,
                    text="No Point This Round",
                    command=lambda gid=game_id, rn=round_num, jid=int(me["id"]): self._apples_skip_round(gid, rn, jid),
                    **self._button_style_kwargs(),
                )
                skip_btn.pack(fill="x", pady=(6, 8))
                self.action_widgets.append(skip_btn)
                self.action_buttons.append(skip_btn)
                if not submissions:
                    ctk.CTkLabel(self.action_frame, text="No submissions yet.", justify="left", anchor="w").pack(fill="x")
                else:
                    for index, card in enumerate(submissions, start=1):
                        btn = ctk.CTkButton(
                            self.action_frame,
                            text=f"Winner option {index}: {card}",
                            command=lambda selected=card, gid=game_id, rn=round_num, jid=int(me["id"]): self._apples_pick_winner(gid, rn, jid, selected),
                            **self._button_style_kwargs(),
                        )
                        btn.pack(fill="x", pady=3)
                        self.action_widgets.append(btn)
                        self.action_buttons.append(btn)
            return


        if game["phase"] == "game_over":
            self._show_action_info("Game over. Press Q to return to Apples home, or create another game there.")


    def _apples_read_instructions(self) -> None:
        self.speech.announce(
                "Apples to Apples instructions. "
                "From the Apples home page, create a game or use the game code, then press enter on the Join Game button. "
                "Press Start Game when everyone is ready, then open the live game page. "
                "On the live game page, use Up and Down arrows to move between buttons and cards. "
                "Press Enter or Space to select the focused button or card. "
                "If you are a player, pressing enter or a space on a card submits it immediately. "
                "If you are the judge, choose the winning card. "
                "You may also choose No Point This Round to skip awarding a point. "
                "Use Read Game State to hear the current round, prompt, judge, role, and phase. "
                "Use Refresh State to reload the latest game data from the server. "
                "Press Q at any time on the live game page to return to the Apples home page.",
            interrupt=True,
            force=True,
        )


    def _apples_open_game(self, announce: bool = True) -> None:
        game = self._current_apples_game()
        if not game:
            self.speech.announce("No Apples game selected yet.", interrupt=True, force=True)
            return
        self.apples_screen = "game"
        self.select_page("apples", announce=False)
        self.after(100, self._focus_apples_game_default)
        if announce:
            self.after(180, self._announce_apples_state)


    def _focus_apples_game_default(self) -> None:
        btn = getattr(self, "_apples_read_state_button", None)
        if btn is not None and btn.winfo_exists() and btn in self.action_buttons:
            self.nav_mode = False
            self.action_index = self.action_buttons.index(btn)
            self._sync_keyboard_focus()


    def _current_apples_game(self):
        code = self.apples_code_var.get().strip().upper()
        if not code:
            return None
        return apples_service.game_by_code(code)


    def _announce_apples_state(self) -> None:
        game = self._current_apples_game()
        if not game:
            return
        roster = apples_service.players(int(game["id"]))
        me = apples_service.my_player(int(game["id"]), self.apples_token) if self.apples_token else None
        judge_name = next(
            (p["name"] for p in roster if game.get("judge_pid") and int(p["id"]) == int(game["judge_pid"])),
            "—",
        )
        is_judge = bool(game.get("judge_pid")) and me and int(me["id"]) == int(game["judge_pid"])
        role = "the judge" if is_judge else "a player"
        self.speech.announce(
            f"Round {game['round_num']}. Prompt: {game['green'] or 'none'}. Judge: {judge_name}. You are {role}. Phase: {game['phase']}.",
            interrupt=True,
            force=True,
        )


    def _refresh_apples_page(self) -> None:
        if self.apples_screen == "game":
            self._apples_open_game(announce=True)
        else:
            self.select_page("apples", announce=False)
            game = self._current_apples_game()
            if game:
                self.after(120, self._announce_apples_state)


    def _apples_create_game(self) -> None:
        if not self.auth_session:
            self.speech.announce("Sign in to create an Apples game.", interrupt=True, force=True)
            return
        try:
            code = apples_service.create_game(points_to_win=5)
            self.apples_code_var.set(code)
            self.apples_selected_card = None
            self.speech.announce(f"Apples game created. Code {code}.", interrupt=True, force=True)
            self.select_page("apples", announce=False)
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)


    def _apples_join_game(self) -> None:
        code = self.apples_code_var.get().strip().upper()
        if not code:
            self.speech.announce("Enter a game code to join.", interrupt=True, force=True)
            return
        if not self.auth_session:
            self.speech.announce("Sign in to join Apples.", interrupt=True, force=True)
            return


        username = self.auth_session.username or self.auth_session.email or "Guest"
        user_id = (
            getattr(self.auth_session, "local_id", None)
            or getattr(self.auth_session, "user_id", None)
            or getattr(self.auth_session, "id", None)
        )
        if not user_id:
            self.speech.announce("Could not determine user id. Please sign in again.", interrupt=True, force=True)
            return


        try:
            self.apples_token = apples_service.join_game(code, username, user_id=user_id)
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            return


        self.apples_code_var.set(code)
        self.apples_selected_card = None
        self.select_page("apples", announce=False)
        self.speech.announce(f"Joined Apples game {code} as {username}.", interrupt=True, force=True)


    def _apples_start_game(self) -> None:
        game = self._current_apples_game()
        if not game:
            self.speech.announce("Create or join a game first.", interrupt=True, force=True)
            return
        try:
            apples_service.start_game(int(game["id"]))
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            return
        self._apples_open_game(announce=True)


    def _apples_select_and_submit(self, game_id: int, round_num: int, player_id: int, judge_id: int, card: str) -> None:
        self.apples_selected_card = card
        self._apples_submit_card(game_id, round_num, player_id, judge_id)


    def _apples_submit_card(self, game_id: int, round_num: int, player_id: int, judge_id: int) -> None:
        if not self.apples_selected_card:
            self.speech.announce("Select a card first.", interrupt=True, force=True)
            return
        try:
            apples_service.submit_card(game_id, round_num, player_id, judge_id, self.apples_selected_card)
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            return


        selected = self.apples_selected_card
        self.apples_selected_card = None
        self._apples_open_game(announce=False)
        self.after(150, lambda: self.speech.announce(f"Submitted card: {selected}.", interrupt=True, force=True))
        self.after(350, self._announce_apples_state)


    def _apples_pick_winner(self, game_id: int, round_num: int, judge_id: int, winning_card: str) -> None:
        try:
            apples_service.judge_pick(game_id, round_num, judge_id, winning_card)
        except Exception as exc:
            self.speech.announce(str(exc), interrupt=True, force=True)
            return

        self._apples_open_game(announce=False)
        self.after(150, lambda: self.speech.announce(f"Selected winning card: {winning_card}.", interrupt=True, force=True))
        self.after(350, self._announce_apples_state)

# button styles
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

# Sign out button
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
