from __future__ import annotations

import json
import random
import secrets
import sqlite3
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "games" / "apples" / "apples_min.db"
HAND_SIZE = 10

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
    deck: list[str] = []
    for adjective in ADJECTIVES:
        for noun in NOUNS:
            deck.append(f"A {adjective} {noun}.")
    for adjective in ADJECTIVES:
        for noun in NOUNS:
            for verb in VERBS:
                deck.append(f"A {adjective} {noun} {verb}.")
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
    prompts: list[str] = []
    for base in GREEN_BASE:
        prompts.append(base)
        prompts.append(base + " (be honest)")
        prompts.append(base + " (say it like a robot)")
        prompts.append(base + " (in one word)")
    return prompts


GREEN_DECK = build_green_deck()
RED_DECK = build_red_deck()


def conn():
    connection = sqlite3.connect(DATA_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    return connection


def init() -> None:
    connection = conn()
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS games(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT UNIQUE,
          phase TEXT,
          round_num INTEGER,
          judge_pid INTEGER,
          green TEXT,
          rev INTEGER DEFAULT 0,
          points_to_win INTEGER DEFAULT 5,
          last_msg TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS players(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          game_id INTEGER,
          name TEXT,
          token TEXT,
          score INTEGER DEFAULT 0,
          UNIQUE(game_id, name),
          UNIQUE(game_id, token)
        );
        CREATE TABLE IF NOT EXISTS hands(
          game_id INTEGER,
          pid INTEGER,
          cards TEXT,
          PRIMARY KEY(game_id, pid)
        );
        CREATE TABLE IF NOT EXISTS subs(
          game_id INTEGER,
          round_num INTEGER,
          pid INTEGER,
          card TEXT,
          PRIMARY KEY(game_id, round_num, pid)
        );
        """
    )
    connection.commit()
    connection.close()


def bump(connection, game_id: int, message: str = "") -> None:
    connection.execute("UPDATE games SET rev = rev + 1, last_msg=? WHERE id=?", (message, game_id))


def game_by_code(code: str):
    connection = conn()
    game = connection.execute("SELECT * FROM games WHERE code=?", (code,)).fetchone()
    connection.close()
    return dict(game) if game else None


def players(game_id: int) -> list[dict]:
    connection = conn()
    rows = connection.execute("SELECT * FROM players WHERE game_id=? ORDER BY id", (game_id,)).fetchall()
    connection.close()
    return [dict(row) for row in rows]


def my_player(game_id: int, token: str | None):
    if not token:
        return None
    connection = conn()
    row = connection.execute("SELECT * FROM players WHERE game_id=? AND token=?", (game_id, token)).fetchone()
    connection.close()
    return dict(row) if row else None


def get_hand(game_id: int, player_id: int) -> list[str]:
    connection = conn()
    row = connection.execute("SELECT cards FROM hands WHERE game_id=? AND pid=?", (game_id, player_id)).fetchone()
    connection.close()
    return json.loads(row["cards"]) if row and row["cards"] else []


def set_hand(connection, game_id: int, player_id: int, cards: list[str]) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO hands(game_id, pid, cards) VALUES (?,?,?)",
        (game_id, player_id, json.dumps(cards, ensure_ascii=False)),
    )


def draw_cards(deck: list[str], count: int) -> list[str]:
    drawn: list[str] = []
    for _ in range(count):
        if not deck:
            break
        drawn.append(deck.pop())
    return drawn


def create_game(points_to_win: int = 5) -> str:
    connection = conn()
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    connection.execute(
        "INSERT INTO games(code, phase, round_num, judge_pid, green, points_to_win) VALUES (?,?,?,?,?,?)",
        (code, "lobby", 1, None, "", int(points_to_win)),
    )
    connection.commit()
    connection.close()
    return code


def join_game(code: str, name: str) -> str:
    game = game_by_code(code)
    if not game:
        raise ValueError("Invalid game code.")
    if game["phase"] != "lobby":
        raise ValueError("Game already started.")

    token = secrets.token_urlsafe(12)
    connection = conn()
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("INSERT INTO players(game_id, name, token) VALUES (?,?,?)", (game["id"], name, token))
    player_id = connection.execute(
        "SELECT id FROM players WHERE game_id=? AND token=?",
        (game["id"], token),
    ).fetchone()["id"]
    set_hand(connection, game["id"], player_id, [])
    bump(connection, game["id"], f"{name} joined.")
    connection.commit()
    connection.close()
    return token


def start_game(game_id: int) -> None:
    connection = conn()
    connection.execute("BEGIN IMMEDIATE")
    roster = connection.execute("SELECT id,name FROM players WHERE game_id=? ORDER BY id", (game_id,)).fetchall()
    if len(roster) < 2:
        connection.rollback()
        connection.close()
        raise ValueError("Need at least 2 players.")

    judge_id = int(roster[0]["id"])
    prompt = random.choice(GREEN_DECK)
    deck = RED_DECK[:]
    random.shuffle(deck)
    needed_cards = len(roster) * HAND_SIZE
    if len(deck) < needed_cards:
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
    connection = conn()
    rows = connection.execute(
        "SELECT card FROM subs WHERE game_id=? AND round_num=?",
        (game_id, round_num),
    ).fetchall()
    connection.close()
    return [row["card"] for row in rows]


def judge_pick(game_id: int, round_num: int, judge_id: int, winning_card: str) -> None:
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
