"""
Apples to Apples game service for the HelloWorld GameSpace launcher.

This module runs the whole Apples to Apples card game using Supabase.  
It stores games, players, hands, and card submissions in the database.

Key concepts
------------
Game phases:  lobby → selecting → judging → game_over
  lobby     — players are joining; game has not started yet.
  selecting — each non-judge player picks a red card from their hand.
  judging   — the judge picks the best submitted red card.
  game_over — someone reached the points target.

The green deck contains prompt cards ("The most awkward family tradition:")
and the red deck contains answer cards ("A haunted microwave.").
"""
from __future__ import annotations

# Standard-library modules
import json       # used to store card lists as JSON strings in SQLite
import random     # used to shuffle decks and pick random prompts
from typing import Any  # used for type annotations
from supabase import create_client # used to connect to the hosted Supabase database
from supabase_project import SUPABASE_ANON_KEY, SUPABASE_URL #  used to get the Supabase credentials from supabase_project.py

# How many red cards each player holds in their hand at a time.
HAND_SIZE = 10

# Green deck base prompts
GREEN_BASE = [
    "The worst thing to say on a first date:",
    "The most awkward family tradition:",
    "My secret superpower is...",
    "What keeps me up at night?",
    "A terrible name for a restaurant:",
    "The fastest way to ruin a party:",
    "A thing you should never bring to a wedding:",
    "A surprising reason to call 911:",
    "A weird thing to collect:",
    "A phrase that should never be on a t-shirt:",
]

# Red deck cards (answers to the prompts)
RED_BASE = [
    "A broken elevator.",
    "An apology email to your future self.",
    "A hamster with a mortgage.",
    "A Wi-Fi router with trust issues.",
    "A voicemail from your fridge.",
    "A calendar invite that says 'be there or be square'.",
    "An accidentally sent screenshot.",
    "A typo that changes everything.",
    "A stranger's grocery list.",
    "A group chat that never stops buzzing.",
    "An autocorrect disaster.",
    "A suspiciously cheap hotel.",
    "A dog that thinks it's a cat.",
    "An overdramatic weather forecast.",
    "A microwave that beeps forever.",
    "A failed attempt at being cool.",
    "A Zoom call that won’t end.",
    "A phone battery at 1 percent.",
    "A playlist full of guilty pleasures.",
    "A neighbor who mows the lawn at 6 AM.",
    "An awkward silence that lasts too long.",
    "A forgotten password you desperately need.",
    "A sock that disappears in the laundry.",
    "A typo in an important email.",
    "A GPS that keeps rerouting.",
    "A chair that squeaks every time you move.",
    "An alarm that doesn’t wake you up.",
    "A group project where you do everything.",
    "A joke that no one understands.",
    "A meeting that could have been an email.",
    "A broken vending machine.",
    "A suspicious smell you can’t locate.",
    "A long hold music loop.",
    "An unfinished homework assignment.",
    "A dramatic reading of a text message.",
    "A chair with one slightly shorter leg.",
    "A confusing set of instructions.",
    "A pen that runs out mid-sentence.",
    "A sneeze that won’t come out.",
    "A fridge full of nothing to eat.",
    "A random burst of motivation at midnight.",
    "A keyboard that types double letters.",
    "A forgotten birthday.",
    "A really bad haircut.",
    "A painfully slow internet connection.",
    "A mystery stain.",
    "A random notification that means nothing.",
    "A door that won’t open the right way.",
    "A “quick question” that isn’t quick.",]

# initialized Supabase client
def get_supabase():
    return create_client(SUPABASE_URL.strip(), SUPABASE_ANON_KEY.strip())
supabase = get_supabase()

# Realtime channel for listening to database changes
_realtime_channel = None

# Helper functions to extract rows from Supabase results and handle errors.
def _row(result):   # returns the first row of a Supabase query result, or None if no data; raises an error if the query failed.
    if result is None:
        return None
    if hasattr(result, "status_code") and result.status_code >= 300:
        raise RuntimeError(f"Supabase error {result.status_code}: {getattr(result, 'data', None)}")
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return data

def _rows(result):  # returns all rows of a Supabase query result as a list, or an empty list if no data; raises an error if the query failed.
    if result is None:
        return []
    if hasattr(result, "status_code") and result.status_code >= 300:
        raise RuntimeError(f"Supabase error {result.status_code}: {getattr(result, 'data', None)}")
    data = getattr(result, "data", None)
    if data is None:
        return []
    return data

def _new_code(length: int = 6) -> str:  # generates a random game code of uppercase letters and digits
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(chars) for _ in range(length))

def _to_cards(value: Any) -> list[str]: # converts a database value to a list of cards; handles both JSON strings and actual lists, and returns an empty list if the value is invalid.
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [value]
    return []

def _from_cards(cards: list[str]) -> str:   # converts a list of cards to a JSON string for database storage.
    return json.dumps(cards)

def _game_or_raise(code: str) -> dict[str, Any]:    # retrieves a game by code or raises an error if not found; used to validate game existence in various operations.
    result = supabase.table("apples_games").select("*").eq("code", code).execute()
    row = _row(result)
    if not row:
        raise RuntimeError(f"Game with code '{code}' not found.")
    return row

def _computer_name() -> str:    # returns the default name for the computer player; used when creating a computer player if needed.
    return "Apple Bot"

def _is_computer_player(player_id: int) -> bool:    # determines if a player is a computer player based on their ID.
    result = supabase.table("apples_players").select("*").eq("id", player_id).execute()
    row = _row(result)
    return bool(row and (row.get("username", "").lower().startswith("computer") or row.get("user_id") == "computer"))

def _ensure_computer_player(game_id: int) -> int:   # ensures there is a computer player in the game and returns their player ID
    existing = _rows(
        supabase.table("apples_players")
        .select("*")
        .eq("game_id", game_id)
        .eq("username", _computer_name())
        .execute()
    )
    if existing:
        return int(existing[0]["id"])

    result = supabase.table("apples_players").insert({
        "game_id": game_id,
        "username": _computer_name(),
        "score": 0,
        "user_id": "computer",
    }).execute()
    row = _row(result)
    if not row:
        raise RuntimeError("Could not create computer player.")

    player_id = int(row["id"])
    set_hand(None, game_id, player_id, draw_cards(HAND_SIZE))
    return player_id

def build_green_deck() -> list[str]: # builds and returns a shuffled green deck for the current round; currently just shuffles the base prompts, but could be extended to pull from a larger pool or add dynamic prompts.
    deck = list(GREEN_BASE)
    random.shuffle(deck)
    return deck

def draw_cards(count: int = HAND_SIZE) -> list[str]:    # draws a specified number of red cards from the deck
    deck = list(RED_BASE)
    while len(deck) < count:
        deck.append(f"Extra red card {random.randint(1, 999)}.")
    random.shuffle(deck)
    return deck[:count]

def game_by_code(code: str):    # retrieves a game by the game code
    if not code:
        return None
    result = supabase.table("apples_games").select("*").eq("code", code).execute()
    return _row(result)

# Main game operations
def create_game(points_to_win: int = 5) -> str: # creates a new game with a unique code
    code = _new_code()
    payload = {
        "code": code,
        "phase": "lobby",
        "round_num": 1,
        "judge_pid": None,
        "green": "",
        "last_msg": "Waiting for players",
        "points_to_win": points_to_win,
    }
    result = supabase.table("apples_games").insert(payload).execute()
    row = _row(result)
    if not row:
        raise RuntimeError("Could not create apples game.")
    return str(row["code"])

def join_game(code: str, name: str, user_id: str) -> str:   # joins an existing game by code with the given player name and user ID
    game = _game_or_raise(code)

    existing = _rows(
        supabase.table("apples_players")
        .select("*")
        .eq("game_id", int(game["id"]))
        .eq("user_id", user_id)
        .execute()
    )
    if existing:
        return str(existing[0]["id"])

    payload = {
        "game_id": int(game["id"]),
        "username": name,
        "score": 0,
        "user_id": user_id,
    }
    result = supabase.table("apples_players").insert(payload).execute()
    row = _row(result)
    if not row:
        raise RuntimeError("Could not join Apples game.")

    player_id = int(row["id"])
    set_hand(None, int(game["id"]), player_id, draw_cards(HAND_SIZE))
    return str(player_id)

def players(game_id: int) -> list[dict]:    # retrieves the list of players in a game by game ID
    result = supabase.table("apples_players").select("*").eq("game_id", game_id).execute()
    data = getattr(result, "data", None)
    if not data:
        return []
    return [{"id": int(r["id"]), "name": r["username"], "score": int(r.get("score", 0))} for r in data]

def my_player(game_id: int, token: str | None): # retrieves the player information for the current user
    if not token:
        return None
    try:
        pid = int(token)
    except (TypeError, ValueError):
        return None
    result = supabase.table("apples_players").select("*").eq("game_id", game_id).eq("id", pid).execute()
    row = _row(result)
    if not row:
        return None
    return {"id": int(row["id"]), "name": row["username"], "score": int(row.get("score", 0))}

def get_hand(game_id: int, player_id: int) -> list[str]: # retrieves the current hand of red cards for a player in a game
    result = supabase.table("apples_hands").select("*").eq("game_id", game_id).eq("player_id", player_id).execute()
    row = _row(result)
    if not row:
        hand = draw_cards(HAND_SIZE)
        set_hand(None, game_id, player_id, hand)
        return hand
    return _to_cards(row.get("cards", "[]"))

def set_hand(connection, game_id: int, player_id: int, cards: list[str]) -> None:   # sets the hand of red cards for a player in a game
    payload = {"game_id": game_id, "player_id": player_id, "cards": _from_cards(cards)}
    result = supabase.table("apples_hands").select("*").eq("game_id", game_id).eq("player_id", player_id).execute()
    row = _row(result)
    if row:
        supabase.table("apples_hands").update(payload).eq("id", int(row["id"])).execute()
    else:
        supabase.table("apples_hands").insert(payload).execute()

def _computer_play_if_needed(game_id: int, round_num: int, judge_id: int) -> None:  # if the judge is a computer player, have all computer players submit a card automatically
    roster = players(game_id)
    for p in roster:
        if p["id"] == judge_id:
            continue
        if _is_computer_player(p["id"]):
            hand = get_hand(game_id, p["id"])
            if not hand:
                return
            card = random.choice(hand)
            submit_card(game_id, round_num, p["id"], judge_id, card)
            return

def start_game(game_id: int) -> None:   # starts the game by selecting a judge, picking the first green card, and transitioning to the selecting phase
    result = supabase.table("apples_players").select("*").eq("game_id", game_id).execute()
    players_data = getattr(result, "data", None) or []

    if not players_data:
        raise RuntimeError("Need at least one player to start.")

    if len(players_data) == 1:
        judge_id = _ensure_computer_player(game_id)
    else:
        judge_id = int(players_data[0]["id"])

    green = random.choice(build_green_deck())
    supabase.table("apples_games").update({
        "phase": "selecting",
        "judge_pid": judge_id,
        "green": green,
        "last_msg": "Round started.",
    }).eq("id", game_id).execute()

    if not _is_computer_player(judge_id):
        _computer_play_if_needed(game_id, 1, judge_id)

def _computer_judge(game_id: int, round_num: int, judge_id: int) -> None: # if the judge is a computer player, pick a winning card randomly from the submissions#
    submissions = _rows(
        supabase.table("apples_submissions")
        .select("*")
        .eq("game_id", game_id)
        .eq("round_num", round_num)
        .execute()
    )
    if not submissions:
        return
    chosen = random.choice(submissions)
    judge_pick(game_id, round_num, judge_id, chosen["card"])

def submit_card(game_id: int, round_num: int, player_id: int, judge_id: int, card: str) -> None:    # submits a red card for the current round by a player
    game_result = supabase.table("apples_games").select("*").eq("id", game_id).execute()
    game = _row(game_result)
    if not game:
        raise RuntimeError("Game not found.")
    if game.get("phase") != "selecting":
        raise RuntimeError("Game not accepting submissions.")
    if int(game.get("judge_pid", 0)) == player_id:
        raise RuntimeError("Judge may not submit.")

    hand = get_hand(game_id, player_id)
    if card not in hand:
        raise RuntimeError("Card not in hand.")

    submit_result = supabase.table("apples_submissions").insert({
        "game_id": game_id,
        "round_num": round_num,
        "player_id": player_id,
        "card": card,
    }).execute()
    if not _row(submit_result):
        raise RuntimeError("Could not submit card.")

    hand.remove(card)
    set_hand(None, game_id, player_id, hand)

    players_list = players(game_id)
    non_judge = [p for p in players_list if p["id"] != judge_id]
    subs = _rows(
        supabase.table("apples_submissions")
        .select("*")
        .eq("game_id", game_id)
        .eq("round_num", round_num)
        .execute()
    )

    # Has judge select a winner
    if len(subs) >= len(non_judge):
        supabase.table("apples_games").update({
            "phase": "judging",
            "last_msg": "Judge pick a winner.",
        }).eq("id", game_id).execute()
        if _is_computer_player(judge_id):
            _computer_judge(game_id, round_num, judge_id)

def list_submissions(game_id: int, round_num: int) -> list[str]:    # lists the submitted red cards for a given round
    result = supabase.table("apples_submissions").select("*").eq("game_id", game_id).eq("round_num", round_num).execute()
    data = getattr(result, "data", None) or []
    return [row["card"] for row in data]

def judge_pick(game_id: int, round_num: int, judge_id: int, winning_card: str) -> None: # processes the judge's pick of the winning card and awards points
    game_result = supabase.table("apples_games").select("*").eq("id", game_id).execute()
    game = _row(game_result)
    if not game:
        raise RuntimeError("Game not found.")
    if game.get("phase") != "judging":
        raise RuntimeError("Not in judging phase.")
    if int(game.get("judge_pid", 0)) != judge_id:
        raise RuntimeError("Only judge can pick.")

    submission = _row(
        supabase.table("apples_submissions")
        .select("*")
        .eq("game_id", game_id)
        .eq("round_num", round_num)
        .eq("card", winning_card)
        .execute()
    )
    if not submission:
        raise RuntimeError("Winning submission not found.")

    winner_id = int(submission["player_id"])
    winner = _row(supabase.table("apples_players").select("*").eq("id", winner_id).execute())
    if not winner:
        raise RuntimeError("Winner not found.")

    new_score = int(winner.get("score", 0)) + 1
    supabase.table("apples_players").update({"score": new_score}).eq("id", winner_id).execute()

    next_round = int(game.get("round_num", 1)) + 1
    roster = players(game_id)
    human_ids = [p["id"] for p in roster if not _is_computer_player(p["id"])]

    roster = players(game_id)
    ids = [p["id"] for p in roster]
    if judge_id in ids:
        next_judge = ids[(ids.index(judge_id) + 1) % len(ids)]
    else:
        next_judge = ids[0] if ids else judge_id

    phase = "game_over" if new_score >= int(game.get("points_to_win", 5)) else "selecting"
    supabase.table("apples_games").update({
        "phase": phase,
        "round_num": next_round,
        "judge_pid": next_judge,
        "green": random.choice(build_green_deck()),
        "last_msg": f"{winner['username']} won round {round_num}.",
    }).eq("id", game_id).execute()

    supabase.table("apples_submissions").delete().eq("game_id", game_id).execute()
    for p in players(game_id):
        set_hand(None, game_id, p["id"], draw_cards(HAND_SIZE))


    if phase == "selecting" and not _is_computer_player(next_judge):
        _computer_play_if_needed(game_id, next_round, next_judge)




def subscribe_realtime(callback):
    global _realtime_channel
    if _realtime_channel is not None:
        return


    channel = supabase.realtime.channel("apples-updates")
    for table in ["apples_games", "apples_players", "apples_hands", "apples_submissions"]:
        channel.on(
            "postgres_changes",
            {"event": "*", "schema": "public", "table": table},
            callback,
        )
    channel.subscribe()
    _realtime_channel = channel


def skip_round(game_id: int, round_num: int, judge_id: int) -> None:
    game_result = supabase.table("apples_games").select("*").eq("id", game_id).execute()
    game = _row(game_result)
    if not game:
        raise RuntimeError("Game not found.")
    if game.get("phase") != "judging":
        raise RuntimeError("Not in judging phase.")
    if int(game.get("judge_pid", 0)) != judge_id:
        raise RuntimeError("Only judge can skip the round.")


    roster = players(game_id)
    ids = [p["id"] for p in roster]
    if judge_id in ids:
        next_judge = ids[(ids.index(judge_id) + 1) % len(ids)]
    else:
        next_judge = ids[0] if ids else judge_id


    next_round = int(game.get("round_num", 1)) + 1


    supabase.table("apples_games").update({
        "phase": "selecting",
        "round_num": next_round,
        "judge_pid": next_judge,
        "green": random.choice(build_green_deck()),
        "last_msg": f"Round {round_num} was skipped. No point awarded.",
    }).eq("id", game_id).execute()


    supabase.table("apples_submissions").delete().eq("game_id", game_id).execute()
    for p in players(game_id):
        set_hand(None, game_id, p["id"], draw_cards(HAND_SIZE))


    if not _is_computer_player(next_judge):
        _computer_play_if_needed(game_id, next_round, next_judge)