"""
Battleship game service for the HelloWorld GameSpace launcher.

Replaces the local socket server with Supabase so room codes work
over the internet without sharing IP addresses.

Game phases:  lobby → placement → battle → game_over
  lobby     — waiting for second player to join
  placement — both players are placing ships
  battle    — players take turns firing
  game_over — one player sunk all opponent ships

Required Supabase tables (run this SQL in the Supabase SQL editor):

  create table battleship_games (
    id        uuid primary key default gen_random_uuid(),
    code      text unique not null,
    phase     text not null default 'lobby',
    turn      int not null default 0,
    last_msg  text not null default '',
    created_at timestamptz default now()
  );

  create table battleship_players (
    id         uuid primary key default gen_random_uuid(),
    game_id    uuid references battleship_games(id) on delete cascade,
    player_num int not null,
    user_id    text not null,
    username   text not null,
    ready      boolean not null default false,
    ships      text not null default '[]',
    shots      text not null default '[]'
  );

  alter table battleship_games enable row level security;
  alter table battleship_players enable row level security;
  create policy "allow all" on battleship_games for all using (true) with check (true);
  create policy "allow all" on battleship_players for all using (true) with check (true);
"""
from __future__ import annotations

import json
import random
from typing import Any

from supabase import create_client
from supabase_project import SUPABASE_ANON_KEY, SUPABASE_URL

BOARD_SIZE = 8
SHIPS = [
    ("Aircraft Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]


def _get_supabase():
    return create_client(SUPABASE_URL.strip(), SUPABASE_ANON_KEY.strip())

supabase = _get_supabase()


def _row(result):
    if result is None:
        return None
    if hasattr(result, "status_code") and result.status_code >= 300:
        raise RuntimeError(f"Supabase error {result.status_code}: {getattr(result, 'data', None)}")
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return data


def _rows(result):
    if result is None:
        return []
    if hasattr(result, "status_code") and result.status_code >= 300:
        raise RuntimeError(f"Supabase error {result.status_code}: {getattr(result, 'data', None)}")
    data = getattr(result, "data", None)
    return data if data else []


def _new_code(length: int = 6) -> str:
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(chars) for _ in range(length))


def _to_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    return []


def _ship_coords(row: int, col: int, length: int, orient: str) -> list[tuple[int, int]]:
    if orient == "H":
        return [(row, col + i) for i in range(length)]
    return [(row + i, col) for i in range(length)]


def _validate_ships(ships: list[dict]) -> str | None:
    """Returns an error string if invalid, None if valid."""
    if len(ships) != len(SHIPS):
        return f"Need exactly {len(SHIPS)} ships, got {len(ships)}"
    occupied: set[tuple[int, int]] = set()
    for entry in ships:
        name = entry.get("name", "")
        row = int(entry.get("row", 0))
        col = int(entry.get("col", 0))
        orient = str(entry.get("orient", "H")).upper()
        match = next((s for s in SHIPS if s[0].lower() == name.lower()), None)
        if not match:
            return f"Unknown ship: {name}"
        length = match[1]
        if orient not in ("H", "V"):
            return f"Invalid orientation: {orient}"
        coords = _ship_coords(row, col, length, orient)
        for r, c in coords:
            if r < 0 or r >= BOARD_SIZE or c < 0 or c >= BOARD_SIZE:
                return f"Ship {name} is out of bounds"
            if (r, c) in occupied:
                return f"Ship {name} overlaps another ship"
            occupied.add((r, c))
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_game() -> str:
    """Creates a new game in Supabase and returns the 6-char room code."""
    code = _new_code()
    result = supabase.table("battleship_games").insert({
        "code": code,
        "phase": "lobby",
        "turn": 0,
        "last_msg": "Waiting for opponent to join.",
    }).execute()
    row = _row(result)
    if not row:
        raise RuntimeError("Could not create Battleship game.")
    return str(row["code"])


def join_game(code: str, username: str, user_id: str) -> int:
    """
    Joins a game by code. Returns player_num (0 = host, 1 = joiner).
    Transitions lobby → placement when both players are in.
    """
    result = supabase.table("battleship_games").select("*").eq("code", code.upper()).execute()
    game = _row(result)
    if not game:
        raise RuntimeError(f"Game '{code}' not found.")

    game_id = game["id"]
    existing = _rows(
        supabase.table("battleship_players").select("*").eq("game_id", game_id).execute()
    )

    # Rejoin only if the game is already in progress (reconnect after a crash)
    if game.get("phase") != "lobby":
        for p in existing:
            if p.get("user_id") == user_id:
                return int(p["player_num"])
        raise RuntimeError("This game is already in progress.")

    # Still in lobby — add as the next player slot
    if len(existing) >= 2:
        raise RuntimeError("Game is already full.")

    player_num = len(existing)
    supabase.table("battleship_players").insert({
        "game_id": game_id,
        "player_num": player_num,
        "user_id": user_id,
        "username": username,
        "ready": False,
        "ships": json.dumps([]),
        "shots": json.dumps([]),
    }).execute()

    if player_num == 1:
        supabase.table("battleship_games").update({
            "phase": "placement",
            "last_msg": "Both players joined. Place your ships.",
        }).eq("id", game_id).execute()

    return player_num


def get_game(code: str) -> dict | None:
    """Returns the game row for the given code, or None."""
    result = supabase.table("battleship_games").select("*").eq("code", code.upper()).execute()
    return _row(result)


def get_player(game_id: str, player_num: int) -> dict | None:
    """Returns the player row for the given game and player_num."""
    result = (
        supabase.table("battleship_players")
        .select("*")
        .eq("game_id", game_id)
        .eq("player_num", player_num)
        .execute()
    )
    return _row(result)


def place_ships(game_id: str, player_num: int, ships: list[dict]) -> None:
    """
    Validates and saves a player's complete ship layout, marks them ready.
    Transitions to battle phase if both players are now ready.

    ships: list of {name, row, col, orient}
    """
    error = _validate_ships(ships)
    if error:
        raise RuntimeError(error)

    player = get_player(game_id, player_num)
    if not player:
        raise RuntimeError("Player not found.")

    supabase.table("battleship_players").update({
        "ships": json.dumps(ships),
        "ready": True,
    }).eq("id", player["id"]).execute()

    other = get_player(game_id, 1 - player_num)
    if other and other.get("ready"):
        supabase.table("battleship_games").update({
            "phase": "battle",
            "turn": 0,
            "last_msg": "Battle begins! Player 1's turn.",
        }).eq("id", game_id).execute()


def fire(game_id: str, player_num: int, row: int, col: int) -> dict:
    """
    Fires at (row, col) on behalf of player_num.
    Returns {status: "miss"|"hit"|"win", ship_name: str|None, sunk: bool}.
    Updates game state in Supabase.
    """
    game_result = supabase.table("battleship_games").select("*").eq("id", game_id).execute()
    game = _row(game_result)
    if not game:
        raise RuntimeError("Game not found.")
    if game.get("phase") != "battle":
        raise RuntimeError("Not in battle phase.")
    if int(game.get("turn", 0)) != player_num:
        raise RuntimeError("Not your turn.")

    player = get_player(game_id, player_num)
    if not player:
        raise RuntimeError("Player not found.")

    my_shots = _to_list(player.get("shots", "[]"))
    if any(int(s["row"]) == row and int(s["col"]) == col for s in my_shots):
        raise RuntimeError("Already fired at that cell.")

    opponent = get_player(game_id, 1 - player_num)
    if not opponent:
        raise RuntimeError("Opponent not found.")

    opponent_ships = _to_list(opponent.get("ships", "[]"))

    hit_ship_name: str | None = None
    sunk = False
    is_hit = False

    for ship_entry in opponent_ships:
        name = ship_entry["name"]
        s_row, s_col = int(ship_entry["row"]), int(ship_entry["col"])
        orient = str(ship_entry.get("orient", "H")).upper()
        match = next((s for s in SHIPS if s[0].lower() == name.lower()), None)
        if not match:
            continue
        coords = _ship_coords(s_row, s_col, match[1], orient)
        if (row, col) in coords:
            is_hit = True
            hit_ship_name = name
            prev_hits = {(int(s["row"]), int(s["col"])) for s in my_shots if s.get("result") == "hit"}
            prev_hits.add((row, col))
            sunk = all(c in prev_hits for c in coords)
            break

    result_str = "hit" if is_hit else "miss"
    my_shots.append({"row": row, "col": col, "result": result_str, "ship_name": hit_ship_name, "sunk": sunk})
    supabase.table("battleship_players").update({"shots": json.dumps(my_shots)}).eq("id", player["id"]).execute()

    # Check win: all opponent ship cells now hit
    all_opponent_coords: set[tuple[int, int]] = set()
    for ship_entry in opponent_ships:
        match = next((s for s in SHIPS if s[0].lower() == ship_entry["name"].lower()), None)
        if match:
            all_opponent_coords.update(
                _ship_coords(int(ship_entry["row"]), int(ship_entry["col"]), match[1], str(ship_entry.get("orient", "H")).upper())
            )

    my_hit_coords = {(int(s["row"]), int(s["col"])) for s in my_shots if s.get("result") == "hit"}
    won = all_opponent_coords.issubset(my_hit_coords)

    if won:
        supabase.table("battleship_games").update({
            "phase": "game_over",
            "last_msg": f"{player['username']} wins!",
        }).eq("id", game_id).execute()
        return {"status": "win", "ship_name": hit_ship_name, "sunk": sunk}

    next_turn = 1 - player_num
    status_word = "Hit" if is_hit else "Miss"
    sunk_note = f" Sunk the {hit_ship_name}!" if sunk else ""
    supabase.table("battleship_games").update({
        "turn": next_turn,
        "last_msg": f"{status_word}!{sunk_note} Player {next_turn + 1}'s turn.",
    }).eq("id", game_id).execute()

    return {"status": result_str, "ship_name": hit_ship_name, "sunk": sunk}


def poll_state(game_id: str, player_num: int) -> dict:
    """
    Returns all state the pygame client needs in one call:
      game: {phase, turn, last_msg, code}
      my_shots: [{row, col, result, ship_name, sunk}]
      opponent_shots: shots fired AT this player (from opponent's record)
      opponent_ready: bool
      both_players_in: bool
    """
    game_result = supabase.table("battleship_games").select("*").eq("id", game_id).execute()
    game = _row(game_result)
    if not game:
        return {}

    me = get_player(game_id, player_num)
    opponent = get_player(game_id, 1 - player_num)

    return {
        "game": {
            "phase": game.get("phase", "lobby"),
            "turn": int(game.get("turn", 0)),
            "last_msg": game.get("last_msg", ""),
            "code": game.get("code", ""),
        },
        "my_shots": _to_list(me.get("shots", "[]")) if me else [],
        "opponent_shots": _to_list(opponent.get("shots", "[]")) if opponent else [],
        "opponent_ready": bool(opponent.get("ready")) if opponent else False,
        "both_players_in": opponent is not None,
    }
