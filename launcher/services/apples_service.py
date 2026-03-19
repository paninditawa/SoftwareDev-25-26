"""
Apples to Apples game service for the HelloWorld GameSpace launcher.

This module runs the whole Apples to Apples card game locally using
SQLite.  It stores games, players, hands, and card submissions in a
small database file (apples_min.db) inside the games/apples/ folder.

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
import secrets    # used to generate cryptographically safe game codes and tokens
import sqlite3    # local database for game state
from pathlib import Path  # cross-platform file path handling

# Path to the SQLite database file, relative to this source file.
DATA_PATH = Path(__file__).resolve().parents[2] / "games" / "apples" / "apples_min.db"
# How many red cards each player holds in their hand at a time.
HAND_SIZE = 10

# --- Green deck base prompts (each gets three variants added automatically) ---
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

# --- Word lists used to procedurally generate the red (answer) deck ---
ADJECTIVES = [
    "haunted", "tiny", "gigantic", "mysterious", "unreasonably confident", "overly dramatic", "cursed", "sparkly",
    "noisy", "invisible", "self-aware", "gluten-free", "sad", "legendary", "suspicious", "extremely polite", "weird",
    "ancient", "futuristic", "sticky", "chaotic", "friendly", "aggressively helpful", "melancholy", "radioactive",
]

NOUNS = [
    "microwave", "toaster", "pigeon", "raccoon", "spoon", "calculator", "group chat", "sock", "email thread",
    "rubber duck", "elevator", "vacuum", "meme", "cactus", "hamster", "printer", "Wi-Fi router", "doorbell",
    "traffic cone", "treadmill", "calendar invite", "laptop", "spaghetti", "stapler", "thermostat",
]

VERBS = [
    "that only works when you cry",
    "that judges you silently",
    "that demands compliments",
    "that whispers spoilers",
    "that starts a union",
    "that writes apology emails",
    "that insists it's your manager",
    "that resets your personality",
]


def build_red_deck() -> list[str]:
    # Build the full red (answer) deck by combining adjectives, nouns, and optional verb clauses.
    deck: list[str] = []
    for adjective in ADJECTIVES:
        for noun in NOUNS:
            deck.append(f"A {adjective} {noun}.")
    for adjective in ADJECTIVES:
        for noun in NOUNS:
            for verb in VERBS:
                deck.append(f"A {adjective} {noun} {verb}.")
    # A few hand-written bonus cards for variety.
    deck += [
        "Existing.",
        "Centaurs.",
        "Passive-aggressive notes.",
        "A perfectly timed Wi-Fi outage.",
        "Saying 'per my last email' out loud.",
        "Wearing socks in the shower.",
        "An inspirational tattoo misspelling.",
        "Glitter spaghetti.",
        "A tiny violin playing just for you.",
    ]
    return deck


def build_green_deck() -> list[str]:
    # Expand each base prompt into four variants for more variety.
    prompts: list[str] = []
    for base in GREEN_BASE:
        prompts.append(base)
        prompts.append(base + " (be honest)")
        prompts.append(base + " (say it like a robot)")
        prompts.append(base + " (in one word)")
    return prompts


# Pre-build the decks once when the module is imported (they are read-only).
GREEN_DECK = build_green_deck()
RED_DECK = build_red_deck()


def conn():
    # Open a new SQLite connection to the game database; WAL mode allows concurrent reads.
    connection = sqlite3.connect(DATA_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row  # rows are accessible by column name
    connection.execute("PRAGMA journal_mode=WAL;")
    return connection


def init() -> None:
    # Create all required tables if they do not exist yet (safe to call multiple times).
    connection = conn()
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS games(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT UNIQUE,           -- short room code players share
          phase TEXT,                 -- lobby | selecting | judging | game_over
          round_num INTEGER,          -- current round number
          judge_pid INTEGER,          -- player ID of the current judge
          green TEXT,                 -- current green-card prompt
          rev INTEGER DEFAULT 0,      -- revision counter, incremented on every state change
          points_to_win INTEGER DEFAULT 5,
          last_msg TEXT DEFAULT ''    -- human-readable description of the last state change
        );
        CREATE TABLE IF NOT EXISTS players(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          game_id INTEGER,
          name TEXT,
          token TEXT,                  -- secret token each player uses to identify themselves
          score INTEGER DEFAULT 0,
          UNIQUE(game_id, name),
          UNIQUE(game_id, token)
        );
        CREATE TABLE IF NOT EXISTS hands(
          game_id INTEGER,
          pid INTEGER,
          cards TEXT,                  -- JSON array of red card strings
          PRIMARY KEY(game_id, pid)
        );
        CREATE TABLE IF NOT EXISTS subs(
          game_id INTEGER,
          round_num INTEGER,
          pid INTEGER,
          card TEXT,                   -- the red card this player submitted this round
          PRIMARY KEY(game_id, round_num, pid)
        );
        """
    )
    connection.commit()
    connection.close()


def bump(connection, game_id: int, message: str = "") -> None:
    # Increment the game's revision counter and store a human-readable message.
    # Callers must commit the transaction after calling this.
    connection.execute("UPDATE games SET rev = rev + 1, last_msg=? WHERE id=?", (message, game_id))


def game_by_code(code: str):
    # Look up a game record by its room code; returns None if not found.
    connection = conn()
    game = connection.execute("SELECT * FROM games WHERE code=?", (code,)).fetchone()
    connection.close()
    return dict(game) if game else None


def players(game_id: int) -> list[dict]:
    # Return all players in join order for the given game.
    connection = conn()
    rows = connection.execute("SELECT * FROM players WHERE game_id=? ORDER BY id", (game_id,)).fetchall()
    connection.close()
    return [dict(row) for row in rows]


def my_player(game_id: int, token: str | None):
    # Find a player by their secret token; returns None if token is missing or invalid.
    if not token:
        return None
    connection = conn()
    row = connection.execute("SELECT * FROM players WHERE game_id=? AND token=?", (game_id, token)).fetchone()
    connection.close()
    return dict(row) if row else None


def get_hand(game_id: int, player_id: int) -> list[str]:
    # Return the list of red cards in a player's hand (decoded from JSON).
    connection = conn()
    row = connection.execute("SELECT cards FROM hands WHERE game_id=? AND pid=?", (game_id, player_id)).fetchone()
    connection.close()
    return json.loads(row["cards"]) if row and row["cards"] else []


def set_hand(connection, game_id: int, player_id: int, cards: list[str]) -> None:
    # Write a player's hand back to the database (upsert).
    connection.execute(
        "INSERT OR REPLACE INTO hands(game_id, pid, cards) VALUES (?,?,?)",
        (game_id, player_id, json.dumps(cards, ensure_ascii=False)),
    )


def draw_cards(deck: list[str], count: int) -> list[str]:
    # Pop `count` cards off the end of the deck list and return them.
    drawn: list[str] = []
    for _ in range(count):
        if not deck:
            break
        drawn.append(deck.pop())
    return drawn


def create_game(points_to_win: int = 5) -> str:
    # Insert a new game row in the lobby phase and return its unique room code.
    connection = conn()
    # Generate a 6-character code using unambiguous characters (no 0/O or 1/I confusion).
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    connection.execute(
        "INSERT INTO games(code, phase, round_num, judge_pid, green, points_to_win) VALUES (?,?,?,?,?,?)",
        (code, "lobby", 1, None, "", int(points_to_win)),
    )
    connection.commit()
    connection.close()
    return code


def join_game(code: str, name: str) -> str:
    # Add a player to a lobby-phase game and return their secret token.
    game = game_by_code(code)
    if not game:
        raise ValueError("Invalid game code.")
    if game["phase"] != "lobby":
        raise ValueError("Game already started.")

    token = secrets.token_urlsafe(12)  # random token unique to this player
    connection = conn()
    connection.execute("BEGIN IMMEDIATE")  # exclusive lock to prevent duplicate names
    connection.execute("INSERT INTO players(game_id, name, token) VALUES (?,?,?)", (game["id"], name, token))
    player_id = connection.execute(
        "SELECT id FROM players WHERE game_id=? AND token=?",
        (game["id"], token),
    ).fetchone()["id"]
    set_hand(connection, game["id"], player_id, [])  # start with an empty hand
    bump(connection, game["id"], f"{name} joined.")
    connection.commit()
    connection.close()
    return token


def start_game(game_id: int) -> None:
    # Transition the game from lobby to the first selecting round.
    # Each player is dealt HAND_SIZE cards and the first judge is chosen.
    connection = conn()
    connection.execute("BEGIN IMMEDIATE")
    roster = connection.execute("SELECT id,name FROM players WHERE game_id=? ORDER BY id", (game_id,)).fetchall()
    if len(roster) < 2:
        connection.rollback()
        connection.close()
        raise ValueError("Need at least 2 players.")

    judge_id = int(roster[0]["id"])  # first player to join becomes the first judge
    prompt = random.choice(GREEN_DECK)
    deck = RED_DECK[:]
    random.shuffle(deck)
    needed_cards = len(roster) * HAND_SIZE
    if len(deck) < needed_cards:
        # Deck is very small for a large group; allow duplicates.
        deck = random.choices(RED_DECK, k=needed_cards)

    for player in roster:
        hand = draw_cards(deck, HAND_SIZE)
        set_hand(connection, game_id, int(player["id"]), hand)

    connection.execute(
        "UPDATE games SET phase='selecting', judge_pid=?, green=?, round_num=1 WHERE id=?",
        (judge_id, prompt, game_id),
    )
    bump(connection, game_id, "Game started. Selecting phase.")
    connection.commit()
    connection.close()


def submit_card(game_id: int, round_num: int, player_id: int, judge_id: int, card: str) -> None:
    # Record a player's red-card submission for this round.
    # When all non-judge players have submitted, the game automatically moves to judging.
    if player_id == judge_id:
        raise ValueError("Judge cannot submit.")

    connection = conn()
    connection.execute("BEGIN IMMEDIATE")
    game = connection.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if game["phase"] != "selecting":
        connection.rollback()
        connection.close()
        raise ValueError("Not selecting.")

    hand = json.loads(
        connection.execute(
            "SELECT cards FROM hands WHERE game_id=? AND pid=?",
            (game_id, player_id),
        ).fetchone()["cards"]
    )
    if card not in hand:
        connection.rollback()
        connection.close()
        raise ValueError("Card not in hand.")

    connection.execute(
        "INSERT INTO subs(game_id, round_num, pid, card) VALUES (?,?,?,?)",
        (game_id, round_num, player_id, card),
    )
    hand.remove(card)
    set_hand(connection, game_id, player_id, hand)
    bump(connection, game_id, "Card submitted.")

    total_players = connection.execute("SELECT COUNT(*) n FROM players WHERE game_id=?", (game_id,)).fetchone()["n"]
    total_submissions = connection.execute(
        "SELECT COUNT(*) n FROM subs WHERE game_id=? AND round_num=?",
        (game_id, round_num),
    ).fetchone()["n"]
    if total_submissions >= total_players - 1:
        connection.execute("UPDATE games SET phase='judging' WHERE id=?", (game_id,))
        bump(connection, game_id, "All submissions received. Judging phase.")

    connection.commit()
    connection.close()


def list_submissions(game_id: int, round_num: int) -> list[str]:
    # Return all submitted red cards for the current round (shown to the judge).
    connection = conn()
    rows = connection.execute(
        "SELECT card FROM subs WHERE game_id=? AND round_num=?",
        (game_id, round_num),
    ).fetchall()
    connection.close()
    return [row["card"] for row in rows]


def judge_pick(game_id: int, round_num: int, judge_id: int, winning_card: str) -> None:
    # The judge chooses a winning red card, the author gets a point, and a new round begins.
    # If someone reaches points_to_win, the game ends.
    connection = conn()
    connection.execute("BEGIN IMMEDIATE")
    game = connection.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if game["phase"] != "judging":
        connection.rollback()
        connection.close()
        raise ValueError("Not judging.")
    if int(game["judge_pid"]) != int(judge_id):
        connection.rollback()
        connection.close()
        raise ValueError("Only judge can pick.")

    row = connection.execute(
        "SELECT pid FROM subs WHERE game_id=? AND round_num=? AND card=?",
        (game_id, round_num, winning_card),
    ).fetchone()
    if not row:
        connection.rollback()
        connection.close()
        raise ValueError("Invalid winner.")

    winner_id = int(row["pid"])
    connection.execute("UPDATE players SET score=score+1 WHERE game_id=? AND id=?", (game_id, winner_id))

    points_to_win = int(game["points_to_win"])
    winner = connection.execute(
        "SELECT name,score FROM players WHERE game_id=? AND id=?",
        (game_id, winner_id),
    ).fetchone()
    if int(winner["score"]) >= points_to_win:
        connection.execute("UPDATE games SET phase='game_over' WHERE id=?", (game_id,))
        bump(connection, game_id, f"{winner['name']} wins! Game over.")
        connection.commit()
        connection.close()
        return

    player_ids = [int(row["id"]) for row in connection.execute("SELECT id FROM players WHERE game_id=? ORDER BY id", (game_id,)).fetchall()]
    current_index = player_ids.index(int(judge_id))
    next_judge = player_ids[(current_index + 1) % len(player_ids)]

    prompt = random.choice(GREEN_DECK)
    for player_id in player_ids:
        hand = json.loads(
            connection.execute(
                "SELECT cards FROM hands WHERE game_id=? AND pid=?",
                (game_id, player_id),
            ).fetchone()["cards"]
        )
        needed = max(0, HAND_SIZE - len(hand))
        refill_deck = RED_DECK[:]
        random.shuffle(refill_deck)
        hand.extend(draw_cards(refill_deck, needed))
        set_hand(connection, game_id, player_id, hand)

    connection.execute(
        "UPDATE games SET phase='selecting', round_num=round_num+1, judge_pid=?, green=? WHERE id=?",
        (next_judge, prompt, game_id),
    )
    bump(connection, game_id, f"Round winner: {winner['name']}. New round selecting.")
    connection.commit()
    connection.close()
