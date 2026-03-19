from __future__ import annotations

import subprocess
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from launcher.services import apples_service
from launcher.ui.theme import (
    APP_BG,
    APP_BORDER,
    APP_ENTRY_BG,
    APP_MUTED,
    APP_PANEL,
    APP_PANEL_ALT,
    APP_ROW_HIGHLIGHT,
    APP_TEXT,
    _font,
)


class ActionsMixin:
    def _announce_error(self, title: str, message: str) -> None:
        self.speech.announce(message, interrupt=True, force=True)
        messagebox.showerror(title, message)

    def _clear_actions(self) -> None:
        for child in self.action_frame.winfo_children():
            child.destroy()
        self.action_widgets = []
        self.action_buttons = []
        self.action_index = 0

    def _add_action_button(self, text: str, command, hint: str) -> ctk.CTkButton:
        button = ctk.CTkButton(self.action_frame, text=text, command=command, **self._button_style_kwargs())
        button.pack(fill="x", pady=6)
        self.speech.bind_focus(button, text, hint)
        self._bind_tab_aliases(button)
        self.action_widgets.append(button)
        self.action_buttons.append(button)
        return button

    def _register_action_button(self, button: ctk.CTkButton, hint: str) -> None:
        text = button.cget("text")
        self.speech.bind_focus(button, text, hint)
        self._bind_tab_aliases(button)
        self.action_widgets.append(button)
        self.action_buttons.append(button)

    def _show_action_info(self, text: str) -> None:
        info = ctk.CTkLabel(
            self.action_frame,
            text=text,
            justify="left",
            anchor="w",
            wraplength=self._content_wraplength,
        )
        info.pack(fill="x", pady=6)
        self.action_widgets.append(info)
        self.action_buttons = []

    def _render_home_actions(self) -> None:
        self._show_action_info(
            "Choose a game or account option from the left menu. Use Up and Down arrows to navigate, Enter or Space to activate."
        )

    def _render_script_actions(self, page_key: str) -> None:
        meta = self.page_meta[page_key]
        self._add_action_button(
            f"Launch {meta['title']}",
            lambda path=meta["path"], title=meta["title"]: self._launch_script(path, title),
            f"Press Enter to launch {meta['title']}.",
        )

    def _render_account_actions(self) -> None:
        self._add_action_button("Sign Out", self._sign_out, "Press Enter to sign out and return to the login screen.")

    def _render_actions(self, page_key: str) -> None:
        self._clear_actions()
        kind = self.page_meta[page_key]["type"]
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

    def _render_battleship_actions(self) -> None:
        code_label = ctk.CTkLabel(
            self.action_frame,
            text="Room code - share this with your opponent when hosting, or enter theirs to join:",
            justify="left", anchor="w", wraplength=self._content_wraplength,
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

        port_note = ctk.CTkLabel(
            self.action_frame,
            text=f"Advanced: server runs on {self.client_host_var.get()}:{self.client_port_var.get()}",
            text_color=APP_MUTED, font=_font(14, bold=True),
            justify="left", anchor="w",
        )
        port_note.pack(anchor="w", pady=(10, 0))
        self.action_widgets.append(port_note)

    def _battleship_host(self) -> None:
        """Start the server and immediately launch a client as the host player."""
        if self.server_process and self.server_process.poll() is None:
            self.speech.announce("A game is already running. Stop it first.", interrupt=True, force=True)
            return

        port = self._parse_port()
        if port is None:
            return
        host = self.client_host_var.get().strip() or "127.0.0.1"

        import hashlib
        import time as _t

        raw = f"{host}:{port}:{_t.time()}"
        room_code = hashlib.md5(raw.encode()).hexdigest()[:6].upper()
        self.battleship_room_code_var.set(room_code)

        server_path = self.battleship_dir / "server.py"
        relative_target = server_path.relative_to(self.repo_root).as_posix()
        self.server_process = subprocess.Popen(
            self._launcher_command("--run-target", relative_target, "--host", host, "--port", str(port)),
            cwd=str(self.repo_root),
        )

        self.after(600, lambda: self._launch_battleship_client(host, port, is_host=True, room_code=room_code))
        self.speech.announce(
            f"Game started. Your room code is {' '.join(room_code)}. Share it with your opponent, then tell them to join.",
            interrupt=True, force=True,
        )

    def _battleship_join(self) -> None:
        """Join a hosted game using the room code (which maps to host:port)."""
        port = self._parse_port()
        if port is None:
            return
        host = self.client_host_var.get().strip() or "127.0.0.1"
        self._launch_battleship_client(host, port, is_host=False)

    def _launch_battleship_client(self, host: str, port: int, is_host: bool = False, room_code: str = "") -> None:
        client_path = self.battleship_dir / "client.py"
        relative_target = client_path.relative_to(self.repo_root).as_posix()

        user_id = self.auth_session.local_id if self.auth_session else ""
        username = (self.auth_session.username or self.auth_session.email) if self.auth_session else "Guest"

        subprocess.Popen(
            self._launcher_command(
                "--run-target", relative_target,
                "--host", host, "--port", str(port),
                "--user-id", user_id,
                "--username", username,
                "--launcher-pid", str(subprocess.os.getpid()),
            ),
            cwd=str(self.repo_root),
        )
        action = "Hosting" if is_host else "Joining"
        self.speech.announce(f"{action} Battleship game.", interrupt=True, force=True)

    def _launch_script(self, script_path: Path, title: str) -> None:
        if not script_path.exists():
            message = f"Could not find {script_path.name}."
            self._announce_error("Missing file", message)
            return
        import os

        env = os.environ.copy()
        if self.auth_session:
            env["HW_USER_ID"] = self.auth_session.local_id
            env["HW_USERNAME"] = self.auth_session.username or self.auth_session.email
        relative_target = script_path.relative_to(self.repo_root).as_posix()
        subprocess.Popen(self._launcher_command("--run-target", relative_target), cwd=str(self.repo_root), env=env)
        self.speech.announce(f"Launching {title}.", interrupt=True, force=True)

    def _parse_port(self) -> int | None:
        value = self.client_port_var.get().strip()
        try:
            return int(value)
        except ValueError:
            self._announce_error("Invalid port", "Port must be a number.")
            return None

    def _stop_battleship_server(self) -> None:
        if not self.server_process or self.server_process.poll() is not None:
            self.speech.announce("No game is currently running.", interrupt=True, force=True)
            return
        self.server_process.terminate()
        self.server_process = None
        self.speech.announce("Game stopped.", interrupt=True, force=True)

    def _render_scoreboard_actions(self) -> None:
        sb = self._get_scoreboard()
        if sb is None:
            info = ctk.CTkLabel(
                self.action_frame,
                text="Scoreboard unavailable - Supabase is not configured.",
                justify="left", anchor="w", wraplength=self._content_wraplength,
            )
            info.pack(fill="x", pady=6)
            self.action_buttons = []
            return

        selector_frame = ctk.CTkFrame(self.action_frame, fg_color="transparent")
        selector_frame.pack(fill="x", pady=(0, 12))

        for game_key, game_label in self.scoreboard_games:
            btn = ctk.CTkButton(
                selector_frame,
                text=game_label,
                width=100,
                command=lambda gk=game_key: self._load_scoreboard(gk),
                **self._button_style_kwargs(),
            )
            btn.pack(side="left", padx=4)
            self._register_action_button(btn, f"Show scoreboard for {game_label}.")

        self.sb_display_frame = ctk.CTkScrollableFrame(self.action_frame, fg_color=APP_BG, corner_radius=8)
        self.sb_display_frame.pack(fill="both", expand=True)

        self._add_action_button(
            "Refresh Scoreboard",
            lambda: self._load_scoreboard(self._sb_selected_game),
            "Reload the leaderboard for the current game.",
        )

        self.after(100, lambda: self._load_scoreboard(self._sb_selected_game))

    def _load_scoreboard(self, game_key: str) -> None:
        self._sb_selected_game = game_key
        sb = self._get_scoreboard()

        if not hasattr(self, "sb_display_frame") or not self.sb_display_frame.winfo_exists():
            return
        for child in self.sb_display_frame.winfo_children():
            child.destroy()

        game_label = next((lbl for gk, lbl in self.scoreboard_games if gk == game_key), game_key.title())
        title = ctk.CTkLabel(
            self.sb_display_frame,
            text=f"{game_label} - Top Players",
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
                justify="left", anchor="w", wraplength=max(280, self._content_wraplength - 40),
            ).pack(anchor="w", padx=8)
            self.speech.announce(f"No scores yet for {game_label}.", interrupt=True, force=True)
            return

        header = ctk.CTkFrame(self.sb_display_frame, fg_color=APP_PANEL_ALT, corner_radius=6)
        header.pack(fill="x", padx=4, pady=(0, 4))
        header.grid_columnconfigure(1, weight=1)
        for col, (text, width) in enumerate([("Rank", 50), ("Player", 0), ("Wins", 60)]):
            ctk.CTkLabel(header, text=text, font=_font(15, bold=True), width=width, anchor="w").grid(
                row=0, column=col, padx=8, pady=6, sticky="w"
            )

        medals = {1: "1", 2: "2", 3: "3"}
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

    def _render_apples_actions(self) -> None:
        helper = ctk.CTkLabel(
            self.action_frame,
            text="Create a local game code or join an existing one. After joining, refresh to hear the latest state.",
            justify="left", anchor="w", wraplength=self._content_wraplength,
        )
        helper.pack(fill="x", pady=(0, 10))
        self._apples_helper_label = helper

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
                justify="left", anchor="w", wraplength=self._content_wraplength,
            )
            info.pack(fill="x", pady=(8, 0))
            return

        game_id = int(game["id"])
        roster = apples_service.players(game_id)
        me = apples_service.my_player(game_id, self.apples_token) if self.apples_token else None
        judge_name = next((p["name"] for p in roster if game["judge_pid"] and int(p["id"]) == int(game["judge_pid"])), "-")
        is_judge = bool(game["judge_pid"]) and me and int(me["id"]) == int(game["judge_pid"])

        status = ctk.CTkLabel(
            self.action_frame,
            text=(
                f"Code: {game['code']}\nPhase: {game['phase']}\nRound: {game['round_num']}\n"
                f"Judge: {judge_name}\nPrompt: {game['green'] or '(none)'}\nLast update: {game['last_msg']}"
            ),
            justify="left", anchor="w", wraplength=self._content_wraplength,
        )
        status.pack(fill="x", pady=(8, 12))
        self._apples_status_label = status

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
            ctk.CTkLabel(self.action_frame, text="You have not joined this Apples game yet.", justify="left", anchor="w", wraplength=self._content_wraplength).pack(fill="x", pady=(12, 0))
            return

        round_num = int(game["round_num"])
        if game["phase"] == "selecting":
            if is_judge:
                ctk.CTkLabel(self.action_frame, text="You are the judge. Wait for all players to submit their cards, then refresh.", justify="left", anchor="w", wraplength=self._content_wraplength).pack(fill="x", pady=(12, 0))
            else:
                ctk.CTkLabel(self.action_frame, text="Your hand", font=_font(18, bold=True)).pack(anchor="w", pady=(12, 6))
                hand = apples_service.get_hand(game_id, int(me["id"]))
                for index, card in enumerate(hand[:apples_service.HAND_SIZE], start=1):
                    btn = ctk.CTkButton(self.action_frame, text=f"Card {index}: {card}", command=lambda selected=card: self._apples_select_card(selected), **self._button_style_kwargs())
                    btn.pack(fill="x", pady=3)
                    self._register_action_button(btn, card)
                selected_text = self.apples_selected_card or "No card selected."
                ctk.CTkLabel(self.action_frame, text=f"Selected: {selected_text}", justify="left", anchor="w", wraplength=self._content_wraplength).pack(fill="x", pady=(10, 6))
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
                ctk.CTkLabel(self.action_frame, text="Waiting for the judge to pick a winner. Press Refresh State to hear updates.", justify="left", anchor="w", wraplength=self._content_wraplength).pack(fill="x", pady=(12, 0))
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
            ctk.CTkLabel(self.action_frame, text="Game over. Review the scores above or create a new game.", justify="left", anchor="w", wraplength=self._content_wraplength).pack(fill="x", pady=(12, 0))

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
            self._announce_error("Missing information", message)
            return
        try:
            self.apples_token = apples_service.join_game(code, name)
        except Exception as exc:
            self._announce_error("Join failed", str(exc))
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
            self._announce_error("Start game failed", str(exc))
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
        except Exception:
            pass
        submitted_card = self.apples_selected_card
        self.apples_selected_card = None
        self.select_page("apples", announce=False)
        self.speech.announce(f"Submitted card: {submitted_card}", interrupt=True, force=True)

    def _apples_pick_winner(self, game_id: int, round_num: int, judge_id: int, winning_card: str) -> None:
        try:
            apples_service.judge_pick(game_id, round_num, judge_id, winning_card)
        except Exception as exc:
            self._announce_error("Judge pick failed", str(exc))
            return
        self.select_page("apples", announce=False)
        self.speech.announce(f"Selected winning card: {winning_card}", interrupt=True, force=True)
