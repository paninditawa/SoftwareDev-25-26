"""
Battleship client — EchoFleet, accessibility-focused redesign.

Built for blind and low-vision players: every action is announced with rich
spatial context, the player can survey rows/columns/fleet status with hotkeys,
and pitch-coded sound cues convey board position without needing stereo audio.
Uses Supabase as the cloud backend so games work over the internet.
"""

from __future__ import annotations
import argparse
import sys
import threading
import time
from pathlib import Path
import numpy as np
import pygame

_repo_root = Path(__file__).resolve()
while _repo_root != _repo_root.parent:
    if (_repo_root / "tts.py").exists():
        break
    _repo_root = _repo_root.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:
    from tts import speak as _tts_speak, speak_interrupt as _tts_speak_interrupt
except ImportError:
    def _tts_speak(text: str): print(text)
    def _tts_speak_interrupt(text: str): print(text)

try:
    from launcher.services import battleship_service
except ImportError as e:
    print(f"Could not import battleship_service: {e}")
    sys.exit(1)

last_spoken_text = ""


def speak(text: str, interrupt: bool = False) -> None:
    global last_spoken_text
    last_spoken_text = text
    if interrupt:
        _tts_speak_interrupt(text)
    else:
        _tts_speak(text)


def speak_now(text: str) -> None:
    speak(text, interrupt=True)


BOARD_SIZE = 8
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 580
CELL = min(WINDOW_WIDTH // (BOARD_SIZE * 2 + 2), WINDOW_HEIGHT // (BOARD_SIZE + 2))

LEFT_OFFSET_X = 40
RIGHT_OFFSET_X = LEFT_OFFSET_X + BOARD_SIZE * CELL + 40
BOARD_OFFSET_Y = 52

SHIP_ORDER = [
    ("Aircraft Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]

C_BG = (18, 29, 43)
C_GRID = (125, 150, 179)
C_SHIP = (120, 145, 171)
C_PREVIEW = (14, 92, 168, 140)
C_BAD = (176, 83, 0, 140)
C_SELECT = (255, 191, 71)
C_HIT = (198, 88, 0)
C_MISS = (236, 241, 247)
C_TEXT = (248, 250, 252)
C_DIM = (201, 212, 224)
C_LABEL = (255, 232, 166)


def _tone(freq, duration=0.25, volume=0.55, envelope="decay"):
    sr = 44100
    n = int(sr * duration)
    t = np.linspace(0, duration, n, False)
    wave = np.sin(freq * t * 2 * np.pi)
    if envelope == "decay":
        env = np.exp(-t * 3)
    elif envelope == "soft":
        attack = np.minimum(t / 0.04, 1.0)
        release = np.minimum((duration - t) / 0.08, 1.0)
        env = np.clip(attack * release, 0, 1)
    else:
        env = np.ones_like(t)
        fade = int(sr * 0.01)
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
    audio = (wave * env * 32767 * volume).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack((audio, audio)))


def _chord(freqs, duration=0.4, volume=0.5, envelope="decay"):
    sr = 44100
    n = int(sr * duration)
    t = np.linspace(0, duration, n, False)
    wave = np.zeros_like(t)
    for f in freqs:
        wave += np.sin(f * t * 2 * np.pi)
    wave /= max(len(freqs), 1)
    if envelope == "decay":
        env = np.exp(-t * 2.5)
    elif envelope == "soft":
        attack = np.minimum(t / 0.04, 1.0)
        release = np.minimum((duration - t) / 0.12, 1.0)
        env = np.clip(attack * release, 0, 1)
    else:
        env = np.ones_like(t)
    audio = (wave * env * 32767 * volume).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack((audio, audio)))


def _sequence(notes, volume=0.5):
    sr = 44100
    pieces = []
    for freq, dur in notes:
        n = int(sr * dur)
        t = np.linspace(0, dur, n, False)
        env = np.exp(-t * 4)
        pieces.append(np.sin(freq * t * 2 * np.pi) * env)
    wave = np.concatenate(pieces)
    audio = (wave * 32767 * volume).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack((audio, audio)))


def _row_pitch(row): return 880.0 * (0.85 ** row)
def _col_pitch(col): return 440.0 * (1.08 ** col)


def _position_cue(row, col, volume=0.45):
    return _sequence([(_col_pitch(col), 0.08), (_row_pitch(row), 0.10)], volume=volume)


def parse_args():
    p = argparse.ArgumentParser(description="Battleship client")
    p.add_argument("--game-code", default="")
    p.add_argument("--game-id", default="")
    p.add_argument("--player-num", type=int, default=0)
    p.add_argument("--user-id", default="")
    p.add_argument("--username", default="Player")
    p.add_argument("--launcher-pid", type=int, default=0)
    return p.parse_args()


def _make_random_layout():
    import random
    board = [[False] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    result = []
    for _, length in SHIP_ORDER:
        for _ in range(1000):
            orient = random.choice(("H", "V"))
            row = random.randint(0, BOARD_SIZE - 1)
            col = random.randint(0, BOARD_SIZE - 1)
            coords = (
                [(row, col + i) for i in range(length)] if orient == "H"
                else [(row + i, col) for i in range(length)]
            )
            if any(r >= BOARD_SIZE or c >= BOARD_SIZE for r, c in coords):
                continue
            if any(board[r][c] for r, c in coords):
                continue
            for r, c in coords:
                board[r][c] = True
            result.append((row, col, orient))
            break
    return result


def _ship_coords(ship_index, row, col, orient):
    _, length = SHIP_ORDER[ship_index]
    return (
        [(row, col + i) for i in range(length)] if orient == "H"
        else [(row + i, col) for i in range(length)]
    )


def _placement_valid(ship_index, row, col, orient):
    coords = _ship_coords(ship_index, row, col, orient)
    if any(r < 0 or r >= BOARD_SIZE or c < 0 or c >= BOARD_SIZE for r, c in coords):
        return False
    confirmed = set()
    for i in range(placed_count):
        confirmed.update(_ship_coords(i, *_layout[i][:2], _layout[i][2]))
    return not any(coord in confirmed for coord in coords)


def _mark_confirmed(ship_index):
    name = SHIP_ORDER[ship_index][0]
    for r, c in _ship_coords(ship_index, *_layout[ship_index][:2], _layout[ship_index][2]):
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            own_ships[r][c] = True
            own_ship_names[r][c] = name


def _sync_cursor_to_ship():
    global selected_row, selected_col, orientation
    if placed_count < len(SHIP_ORDER):
        selected_row, selected_col, orientation = _layout[placed_count]


def report_win():
    if not args.user_id:
        return
    try:
        from launcher.services.leaderboard import Scoreboard
        sb = Scoreboard.from_workspace(_repo_root)
        sb.record_win(args.user_id, args.username, "battleship")
    except Exception as exc:
        print(f"scoreboard write failed: {exc}")


def _coord_label(row, col): return f"{chr(ord('A') + col)}{row + 1}"
def _coord_spoken(row, col): return f"{chr(ord('A') + col)} {row + 1}"


def _describe_own_cell(row, col):
    if hits_on_me[row][col] is True:
        name = own_ship_names[row][col] or "your ship"
        return f"hit on your {name.lower()}"
    if hits_on_me[row][col] is False:
        return "opponent missed here"
    if own_ships[row][col]:
        name = own_ship_names[row][col] or "ship"
        return f"your {name.lower()}"
    return "empty water"


def _describe_fire_cell(row, col):
    cell = hits_on_opponent[row][col]
    if cell == "hit":
        return "hit confirmed"
    if cell == "miss":
        return "you missed here"
    return "unfired"


def _describe_cell(row, col):
    if inspect_mode == "own" or phase == "placement":
        return _describe_own_cell(row, col)
    return _describe_fire_cell(row, col)


def survey_row():
    row = selected_row
    parts = [f"Row {row + 1}:"]
    on_own = inspect_mode == "own" or phase == "placement"
    for c in range(BOARD_SIZE):
        col_letter = chr(ord('A') + c)
        state = _describe_own_cell(row, c) if on_own else _describe_fire_cell(row, c)
        parts.append(f"{col_letter}, {state}.")
    speak_now(" ".join(parts))


def survey_column():
    col = selected_col
    parts = [f"Column {chr(ord('A') + col)}:"]
    on_own = inspect_mode == "own" or phase == "placement"
    for r in range(BOARD_SIZE):
        state = _describe_own_cell(r, col) if on_own else _describe_fire_cell(r, col)
        parts.append(f"{r + 1}, {state}.")
    speak_now(" ".join(parts))


def _own_ship_status():
    results = []
    for name, length in SHIP_ORDER:
        cells = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)
                 if own_ship_names[r][c] == name]
        if len(cells) < length:
            results.append(f"{name}: not placed")
            continue
        hits = sum(1 for r, c in cells if hits_on_me[r][c] is True)
        if hits == 0:
            results.append(f"Your {name}: afloat")
        elif hits >= length:
            results.append(f"Your {name}: sunk")
        else:
            results.append(f"Your {name}: hit {hits} of {length}")
    return results


def _opponent_ship_status():
    results = []
    total_hits = sum(1 for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)
                     if hits_on_opponent[r][c] == "hit")
    for name, _ in SHIP_ORDER:
        if name in opponent_sunk:
            results.append(f"Their {name}: sunk")
        else:
            results.append(f"Their {name}: unknown")
    results.insert(0, f"You have landed {total_hits} hits total.")
    return results


def survey_fleet():
    parts = ["Fleet report."]
    parts.extend(_own_ship_status())
    parts.extend(_opponent_ship_status())
    speak_now(" ".join(parts))


def survey_hits():
    hits = [_coord_spoken(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)
            if hits_on_opponent[r][c] == "hit"]
    if not hits:
        speak_now("No hits yet.")
        return
    speak_now(f"Your hits: {', '.join(hits)}.")


def survey_misses():
    misses = [_coord_spoken(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)
              if hits_on_opponent[r][c] == "miss"]
    if not misses:
        speak_now("No misses yet.")
        return
    if len(misses) > 16:
        speak_now(f"You have {len(misses)} misses. Most recent: {', '.join(misses[-8:])}.")
    else:
        speak_now(f"Your misses: {', '.join(misses)}.")


def survey_turn(): speak_now(describe_status())


def survey_last():
    if last_event:
        speak_now(last_event)
    else:
        speak_now("No recent events.")


def survey_help():
    if phase == "placement":
        speak_now(
            "Placement controls. Arrow keys move ship. J rotates. "
            "Enter or space confirms each ship. Press Enter again when all placed to submit. "
            "K shuffles to a new random layout. "
            "Letter then number jumps to a coordinate. "
            "R reads row, C reads column, F reads fleet, T reads turn, "
            "question mark reads help, escape quits."
        )
    elif phase == "battle":
        speak_now(
            "Battle controls. Arrow keys move the cursor. "
            "Enter or space fires. Tab toggles inspection of your own grid. "
            "Letter then number jumps to a coordinate. "
            "R reads row, C reads column, F reads fleet, "
            "H reads hits, M reads misses, L repeats last event, "
            "T reads turn, question mark reads help, escape quits."
        )
    else:
        speak_now("Escape to quit.")


def announce_move():
    _position_cue(selected_row, selected_col).play()
    label = _coord_spoken(selected_row, selected_col)
    state = _describe_cell(selected_row, selected_col)
    mode_prefix = "Inspecting your grid. " if (phase == "battle" and inspect_mode == "own") else ""
    speak_now(f"{mode_prefix}{label}, {state}.")


def poll_supabase() -> None:
    global phase, my_turn, hits_on_me, hits_on_opponent
    global game_over_message, i_won, opponent_ready, supabase_error
    global last_event, my_sunk

    announced_incoming: set[tuple[int, int]] = set()

    while True:
        time.sleep(1)
        try:
            state = battleship_service.poll_state(args.game_id, args.player_num)
            if not state:
                supabase_error = "Could not reach game."
                continue

            with lock:
                game_info = state["game"]
                service_phase = game_info["phase"]

                for shot in state["opponent_shots"]:
                    r, c = int(shot["row"]), int(shot["col"])
                    is_hit = shot["result"] == "hit"
                    hits_on_me[r][c] = is_hit
                    if (r, c) not in announced_incoming:
                        announced_incoming.add((r, c))
                        if is_hit:
                            ship_name = own_ship_names[r][c] or "ship"
                            ship_cells = [
                                (rr, cc) for rr in range(BOARD_SIZE) for cc in range(BOARD_SIZE)
                                if own_ship_names[rr][cc] == ship_name
                            ]
                            ship_hits = sum(1 for rr, cc in ship_cells if hits_on_me[rr][cc] is True)
                            sunk = ship_hits >= len(ship_cells) and len(ship_cells) > 0
                            if sunk and ship_name not in my_sunk:
                                my_sunk.add(ship_name)
                                last_event = f"Opponent sunk your {ship_name} at {_coord_label(r, c)}."
                                _position_cue(r, c, volume=0.4).play()
                                pygame.time.set_timer(EVT_INCOMING_SUNK, 200, loops=1)
                                speak_now(
                                    f"Incoming hit at {_coord_spoken(r, c)}. "
                                    f"They sunk your {ship_name}!"
                                )
                            else:
                                last_event = f"Opponent hit your {ship_name} at {_coord_label(r, c)}."
                                _position_cue(r, c, volume=0.4).play()
                                pygame.time.set_timer(EVT_INCOMING_HIT, 200, loops=1)
                                speak_now(
                                    f"Incoming hit at {_coord_spoken(r, c)}. "
                                    f"They hit your {ship_name}."
                                )
                        else:
                            last_event = f"Opponent missed at {_coord_label(r, c)}."
                            _position_cue(r, c, volume=0.4).play()
                            pygame.time.set_timer(EVT_INCOMING_MISS, 200, loops=1)
                            speak_now(f"Opponent missed at {_coord_spoken(r, c)}.")

                for shot in state["my_shots"]:
                    r, c = int(shot["row"]), int(shot["col"])
                    hits_on_opponent[r][c] = "hit" if shot["result"] == "hit" else "miss"

                opponent_ready = state["opponent_ready"]

                if service_phase == "battle" and phase in ("placement", "waiting"):
                    phase = "battle"
                    SND_START.play()
                    speak_now("Battle stations. The game begins.")

                elif service_phase == "game_over" and phase != "game_over":
                    phase = "game_over"
                    last_msg = game_info.get("last_msg", "Game over.")
                    game_over_message = last_msg
                    i_won = args.username in last_msg and "wins" in last_msg.lower()
                    if i_won:
                        SND_WIN.play()
                        speak_now("Victory! All enemy ships destroyed. Escape to quit.")
                        threading.Thread(target=report_win, daemon=True).start()
                    else:
                        SND_LOSE.play()
                        speak_now("Defeat. Your fleet is sunk. Escape to quit.")

                if service_phase == "battle":
                    new_my_turn = (int(game_info["turn"]) == args.player_num)
                    if new_my_turn and not my_turn:
                        SND_YOUR_TURN.play()
                        speak_now("Your turn. Choose a target.")
                        last_event = "Your turn."
                    my_turn = new_my_turn

                supabase_error = ""

        except Exception as e:
            supabase_error = str(e)


def _fit_text(font, text, max_width):
    if font.size(text)[0] <= max_width:
        return text
    trimmed = text
    while trimmed and font.size(trimmed + "...")[0] > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + "...") if trimmed else "..."


def describe_status() -> str:
    if phase == "placement":
        if placed_count < len(SHIP_ORDER):
            name, ln = SHIP_ORDER[placed_count]
            pos = _coord_label(selected_row, selected_col)
            return f"Placing {name} (len {ln}) at {pos} {orientation} — arrows, J rotate, Enter confirm"
        return "All ships placed. Press Enter to submit."
    if phase == "waiting":
        return "Ships submitted. Waiting for opponent."
    if phase == "game_over":
        return f"{game_over_message}  —  Escape to quit"
    if supabase_error:
        return f"Connection error: {supabase_error}"
    if my_turn:
        if inspect_mode == "own":
            return "YOUR TURN — inspecting your grid (Tab to return to firing)"
        target = _coord_label(selected_row, selected_col)
        return f"YOUR TURN — aiming at {target}, Enter or Space to fire"
    return "Opponent's turn…"


def draw_grid(offset_x: int, hits, show_ships: bool) -> None:
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            rect = pygame.Rect(offset_x + col * CELL, BOARD_OFFSET_Y + row * CELL, CELL, CELL)
            pygame.draw.rect(screen, C_GRID, rect, 1)
            if show_ships and own_ships[row][col]:
                pygame.draw.rect(screen, C_SHIP, rect.inflate(-4, -4), border_radius=2)
            if hits is not None:
                cell = hits[row][col]
                if cell == "hit" or cell is True:
                    pygame.draw.circle(screen, C_HIT, rect.center, CELL // 3)
                    marker = font_sm.render("X", True, C_TEXT)
                    screen.blit(marker, marker.get_rect(center=rect.center))
                elif cell == "miss" or cell is False:
                    pygame.draw.circle(screen, C_MISS, rect.center, CELL // 4)
                    marker = font_sm.render("O", True, C_BG)
                    screen.blit(marker, marker.get_rect(center=rect.center))


def draw_placement_preview() -> None:
    if phase != "placement" or placed_count >= len(SHIP_ORDER):
        return
    valid = _placement_valid(placed_count, selected_row, selected_col, orientation)
    colour = C_PREVIEW if valid else C_BAD
    surface = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
    surface.fill(colour)
    for r, c in _ship_coords(placed_count, selected_row, selected_col, orientation):
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            rect = pygame.Rect(LEFT_OFFSET_X + c * CELL, BOARD_OFFSET_Y + r * CELL, CELL, CELL)
            screen.blit(surface, rect.topleft)


def draw_cursor() -> None:
    if phase == "placement":
        ox = LEFT_OFFSET_X
    elif phase in ("battle", "game_over"):
        ox = LEFT_OFFSET_X if inspect_mode == "own" else RIGHT_OFFSET_X
    else:
        return
    rect = pygame.Rect(ox + selected_col * CELL, BOARD_OFFSET_Y + selected_row * CELL, CELL, CELL)
    pygame.draw.rect(screen, C_SELECT, rect, 3)


def draw_labels() -> None:
    screen.blit(font_md.render("YOUR SHIPS", True, C_LABEL), (LEFT_OFFSET_X, 4))
    screen.blit(font_md.render("FIRE HERE", True, C_LABEL), (RIGHT_OFFSET_X, 4))
    for i in range(BOARD_SIZE):
        ch = chr(ord("A") + i)
        for ox in (LEFT_OFFSET_X, RIGHT_OFFSET_X):
            lbl = font_sm.render(ch, True, C_DIM)
            screen.blit(lbl, (ox + i * CELL + CELL // 2 - 5, BOARD_OFFSET_Y - 18))
    for i in range(BOARD_SIZE):
        for ox in (LEFT_OFFSET_X - 28, RIGHT_OFFSET_X - 28):
            lbl = font_sm.render(str(i + 1), True, C_DIM)
            screen.blit(lbl, (ox, BOARD_OFFSET_Y + i * CELL + CELL // 2 - 8))


def draw_status() -> None:
    y = BOARD_OFFSET_Y + BOARD_SIZE * CELL + 10
    max_w = WINDOW_WIDTH - 40
    screen.blit(font_md.render(_fit_text(font_md, describe_status(), max_w), True, C_TEXT), (20, y))
    if last_spoken_text:
        screen.blit(font_sm.render(_fit_text(font_sm, last_spoken_text, max_w), True, C_DIM), (20, y + 28))
    if supabase_error:
        screen.blit(font_sm.render(_fit_text(font_sm, f"Error: {supabase_error}", max_w), True, C_HIT), (20, y + 50))


jump_buffer: str = ""


def _try_apply_jump():
    global selected_row, selected_col, jump_buffer
    if len(jump_buffer) < 2:
        return
    letter = jump_buffer[0]
    try:
        num = int(jump_buffer[1:])
    except ValueError:
        jump_buffer = ""
        return
    col = ord(letter) - ord('A')
    row = num - 1
    if 0 <= col < BOARD_SIZE and 0 <= row < BOARD_SIZE:
        if phase == "placement" and placed_count < len(SHIP_ORDER):
            _, length = SHIP_ORDER[placed_count]
            if orientation == "H":
                col = min(col, BOARD_SIZE - length)
            else:
                row = min(row, BOARD_SIZE - length)
            selected_row, selected_col = row, col
            _layout[placed_count] = (selected_row, selected_col, orientation)
        else:
            selected_row, selected_col = row, col
        jump_buffer = ""
        announce_move()
    else:
        jump_buffer = ""
        speak_now("Out of range.")


def main():
    global args, phase, placed_count, orientation
    global own_ships, own_ship_names, hits_on_me, hits_on_opponent
    global selected_row, selected_col
    global lock, my_turn, opponent_ready, game_over_message, i_won
    global supabase_error, last_event, opponent_sunk, my_sunk, inspect_mode, jump_buffer
    global _layout, screen, font_sm, font_md
    global SND_HIT, SND_MISS, SND_SUNK, SND_WIN, SND_LOSE, SND_MOVE, SND_USED
    global SND_BAD, SND_START, SND_YOUR_TURN, SND_INCOMING_HIT, SND_INCOMING_MISS, SND_INCOMING_SUNK
    global EVT_HIT_SOUND, EVT_MISS_SOUND, EVT_SUNK_SOUND
    global EVT_INCOMING_HIT, EVT_INCOMING_MISS, EVT_INCOMING_SUNK

    args = parse_args()

    phase = "placement"
    placed_count = 0
    orientation = "H"
    own_ships = [[False] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    own_ship_names = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    hits_on_me = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    hits_on_opponent = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    selected_row = 0
    selected_col = 0
    inspect_mode = "fire"
    jump_buffer = ""
    last_event = ""
    opponent_sunk = set()
    my_sunk = set()

    lock = threading.Lock()
    my_turn = False
    opponent_ready = False
    game_over_message = ""
    i_won = False
    supabase_error = ""

    _layout = _make_random_layout()
    _sync_cursor_to_ship()

    pygame.init()
    pygame.mixer.init(frequency=44100, size=-16, channels=2)
    pygame.mixer.set_num_channels(16)

    SND_MOVE         = _tone(620, 0.05, 0.20, "pulse")
    SND_HIT          = _sequence([(880, 0.10), (1320, 0.18)], volume=0.55)
    SND_MISS         = _tone(220, 0.20, 0.45, "decay")
    SND_SUNK         = _sequence([(1320, 0.10), (1100, 0.10), (880, 0.10),
                                  (660, 0.20), (440, 0.30)], volume=0.55)
    SND_INCOMING_HIT  = _chord([180, 270, 360], 0.45, 0.55, "decay")
    SND_INCOMING_MISS = _sequence([(800, 0.08), (1100, 0.12)], volume=0.35)
    SND_INCOMING_SUNK = _sequence([(440, 0.15), (330, 0.20), (220, 0.30),
                                   (165, 0.45)], volume=0.6)
    SND_WIN          = _sequence([(523, 0.15), (659, 0.15), (784, 0.15),
                                  (1047, 0.25), (1319, 0.40)], volume=0.6)
    SND_LOSE         = _sequence([(330, 0.25), (262, 0.30), (196, 0.50)], volume=0.55)
    SND_USED         = _tone(140, 0.15, 0.35, "decay")
    SND_BAD          = _tone(160, 0.12, 0.40, "decay")
    SND_START        = _sequence([(523, 0.10), (659, 0.10), (784, 0.18)], volume=0.5)
    SND_YOUR_TURN    = _sequence([(880, 0.08), (1100, 0.12)], volume=0.4)

    EVT_HIT_SOUND    = pygame.USEREVENT + 1
    EVT_MISS_SOUND   = pygame.USEREVENT + 2
    EVT_SUNK_SOUND   = pygame.USEREVENT + 3
    EVT_INCOMING_HIT  = pygame.USEREVENT + 4
    EVT_INCOMING_MISS = pygame.USEREVENT + 5
    EVT_INCOMING_SUNK = pygame.USEREVENT + 6

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    font_sm = pygame.font.SysFont("segoeui", 22, bold=False)
    font_md = pygame.font.SysFont("segoeui", 28, bold=False)
    pygame.display.set_caption("EchoFleet Battleship")

    speak_now(
        f"Connected as player {args.player_num + 1}. Placement phase. "
        "A random layout is loaded. Arrow keys to nudge each ship, "
        "J to rotate, K to shuffle layouts, Enter to confirm each ship. "
        "Press Enter again when all ships are placed to submit. "
        "Press question mark at any time for the full command list."
    )

    threading.Thread(target=poll_supabase, daemon=True).start()

    clock = pygame.time.Clock()
    running = True

    while running:
        screen.fill(C_BG)
        draw_grid(LEFT_OFFSET_X, hits_on_me, show_ships=True)
        draw_grid(RIGHT_OFFSET_X, hits_on_opponent, show_ships=False)
        draw_placement_preview()
        draw_cursor()
        draw_labels()
        draw_status()
        pygame.display.flip()
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == EVT_HIT_SOUND:
                SND_HIT.play()
            elif event.type == EVT_MISS_SOUND:
                SND_MISS.play()
            elif event.type == EVT_SUNK_SOUND:
                SND_SUNK.play()
            elif event.type == EVT_INCOMING_HIT:
                SND_INCOMING_HIT.play()
            elif event.type == EVT_INCOMING_MISS:
                SND_INCOMING_MISS.play()
            elif event.type == EVT_INCOMING_SUNK:
                SND_INCOMING_SUNK.play()

            if event.type != pygame.KEYDOWN:
                continue

            key = event.key

            if key == pygame.K_ESCAPE:
                speak_now("Leaving game.")
                running = False
                break

            unicode_char = event.unicode.upper() if event.unicode else ""
            if unicode_char and len(unicode_char) == 1 and 'A' <= unicode_char <= 'H':
                if phase in ("placement", "battle"):
                    jump_buffer = unicode_char
                    speak_now(f"Jump to column {unicode_char}, awaiting row.")
                    continue
            if unicode_char and len(unicode_char) == 1 and '1' <= unicode_char <= '8':
                if jump_buffer and jump_buffer[0].isalpha():
                    jump_buffer += unicode_char
                    _try_apply_jump()
                    continue
            if key == pygame.K_BACKSPACE and jump_buffer:
                jump_buffer = ""
                speak_now("Jump cancelled.")
                continue

            dr = dc = 0
            if key == pygame.K_UP:    dr = -1
            elif key == pygame.K_DOWN:  dr = 1
            elif key == pygame.K_LEFT:  dc = -1
            elif key == pygame.K_RIGHT: dc = 1

            if dr or dc:
                jump_buffer = ""
                SND_MOVE.play()
                if phase == "placement" and placed_count < len(SHIP_ORDER):
                    _, length = SHIP_ORDER[placed_count]
                    nr = max(0, min(BOARD_SIZE - 1, selected_row + dr))
                    nc = max(0, min(BOARD_SIZE - 1, selected_col + dc))
                    if orientation == "H":
                        nc = min(nc, BOARD_SIZE - length)
                    else:
                        nr = min(nr, BOARD_SIZE - length)
                    selected_row, selected_col = nr, nc
                    _layout[placed_count] = (selected_row, selected_col, orientation)
                    announce_move()
                elif phase == "battle":
                    selected_row = max(0, min(BOARD_SIZE - 1, selected_row + dr))
                    selected_col = max(0, min(BOARD_SIZE - 1, selected_col + dc))
                    announce_move()
                continue

            if key == pygame.K_j:
                if phase == "placement" and placed_count < len(SHIP_ORDER):
                    orientation = "V" if orientation == "H" else "H"
                    _, length = SHIP_ORDER[placed_count]
                    if orientation == "H":
                        selected_col = min(selected_col, BOARD_SIZE - length)
                    else:
                        selected_row = min(selected_row, BOARD_SIZE - length)
                    _layout[placed_count] = (selected_row, selected_col, orientation)
                    word = "horizontal" if orientation == "H" else "vertical"
                    speak_now(f"Rotated to {word}, now at {_coord_spoken(selected_row, selected_col)}.")
                elif phase == "game_over":
                    speak_now("Rematch is not available. Escape to quit.")
                continue

            if key == pygame.K_k and phase == "placement":
                if placed_count == 0:
                    _layout = _make_random_layout()
                    _sync_cursor_to_ship()
                    speak_now(
                        f"New random layout. First ship: {SHIP_ORDER[0][0]} "
                        f"at {_coord_spoken(selected_row, selected_col)}."
                    )
                else:
                    speak_now("Cannot shuffle after ships have been confirmed.")
                continue

            if key == pygame.K_TAB and phase == "battle":
                inspect_mode = "own" if inspect_mode == "fire" else "fire"
                if inspect_mode == "own":
                    speak_now("Inspecting your own grid. Tab again to return to firing.")
                else:
                    speak_now("Aiming at enemy waters.")
                announce_move()
                continue

            if key == pygame.K_r:
                survey_row(); continue
            if key == pygame.K_c:
                survey_column(); continue
            if key == pygame.K_f:
                survey_fleet(); continue
            if key == pygame.K_h and phase == "battle":
                survey_hits(); continue
            if key == pygame.K_m and phase == "battle":
                survey_misses(); continue
            if key == pygame.K_l and phase in ("battle", "game_over"):
                survey_last(); continue
            if key == pygame.K_t:
                survey_turn(); continue
            if (key == pygame.K_SLASH and (event.mod & pygame.KMOD_SHIFT)) or event.unicode == "?":
                survey_help(); continue

            if key in (pygame.K_RETURN, pygame.K_SPACE):
                if phase == "placement" and placed_count < len(SHIP_ORDER):
                    if _placement_valid(placed_count, selected_row, selected_col, orientation):
                        idx = placed_count
                        placed_count += 1
                        _mark_confirmed(idx)
                        name, _ = SHIP_ORDER[idx]
                        if placed_count < len(SHIP_ORDER):
                            _sync_cursor_to_ship()
                            next_name, next_len = SHIP_ORDER[placed_count]
                            speak_now(
                                f"{name} confirmed. Next: {next_name}, length {next_len}, "
                                f"at {_coord_spoken(selected_row, selected_col)}."
                            )
                        else:
                            speak_now(f"{name} confirmed. All ships placed. Press Enter to submit.")
                    else:
                        SND_BAD.play()
                        speak_now("Can't place there. Move the ship to a clear position.")

                elif phase == "placement" and placed_count >= len(SHIP_ORDER):
                    ships_list = [
                        {
                            "name": SHIP_ORDER[i][0],
                            "row": _layout[i][0],
                            "col": _layout[i][1],
                            "orient": _layout[i][2],
                        }
                        for i in range(len(SHIP_ORDER))
                    ]
                    try:
                        battleship_service.place_ships(args.game_id, args.player_num, ships_list)
                        phase = "waiting"
                        speak_now("Ships submitted. Waiting for opponent.")
                    except Exception as e:
                        SND_BAD.play()
                        speak_now(f"Could not submit ships: {e}")

                elif phase == "battle" and my_turn and inspect_mode == "fire":
                    if hits_on_opponent[selected_row][selected_col] in ("hit", "miss"):
                        SND_USED.play()
                        speak_now(
                            f"Already fired at {_coord_spoken(selected_row, selected_col)}. "
                            "Pick another target."
                        )
                    else:
                        try:
                            result = battleship_service.fire(
                                args.game_id, args.player_num, selected_row, selected_col
                            )
                            status = result["status"]
                            with lock:
                                if status in ("hit", "win"):
                                    hits_on_opponent[selected_row][selected_col] = "hit"
                                    ship_name = result.get("ship_name") or "ship"
                                    sunk = result.get("sunk", False)
                                    if sunk:
                                        opponent_sunk.add(ship_name)
                                        last_event = (
                                            f"You sunk their {ship_name} "
                                            f"at {_coord_label(selected_row, selected_col)}!"
                                        )
                                        _position_cue(selected_row, selected_col, volume=0.4).play()
                                        pygame.time.set_timer(EVT_SUNK_SOUND, 200, loops=1)
                                        speak_now(
                                            f"Direct hit at {_coord_spoken(selected_row, selected_col)}. "
                                            f"You sunk their {ship_name}!"
                                        )
                                    else:
                                        last_event = f"You hit at {_coord_label(selected_row, selected_col)}."
                                        _position_cue(selected_row, selected_col, volume=0.4).play()
                                        pygame.time.set_timer(EVT_HIT_SOUND, 200, loops=1)
                                        speak_now(f"Hit at {_coord_spoken(selected_row, selected_col)}.")
                                    if status == "win":
                                        phase = "game_over"
                                        game_over_message = "Victory! All enemy ships destroyed."
                                        i_won = True
                                        speak_now("Victory! All enemy ships destroyed. Escape to quit.")
                                        threading.Thread(target=report_win, daemon=True).start()
                                    else:
                                        my_turn = False
                                elif status == "miss":
                                    hits_on_opponent[selected_row][selected_col] = "miss"
                                    last_event = f"You missed at {_coord_label(selected_row, selected_col)}."
                                    _position_cue(selected_row, selected_col, volume=0.4).play()
                                    pygame.time.set_timer(EVT_MISS_SOUND, 200, loops=1)
                                    speak_now(f"Miss at {_coord_spoken(selected_row, selected_col)}.")
                                    my_turn = False
                        except Exception as e:
                            SND_BAD.play()
                            speak_now(str(e))

                elif phase == "battle" and inspect_mode == "own":
                    speak_now("Press Tab to return to firing mode.")
                continue

    pygame.quit()


main()
