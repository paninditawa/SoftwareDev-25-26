"""
Battleship client — EchoFleet, accessibility-focused redesign.

Built for blind and low-vision players: every action is announced with rich
spatial context, the player can survey rows/columns/fleet status with hotkeys,
and pitch-coded sound cues convey board position without needing stereo audio.
Uses Supabase as the cloud backend so games work over the internet.
"""

from __future__ import annotations
import argparse
import math
import os
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

WINDOW_WIDTH = 1320
WINDOW_HEIGHT = 800

CELL = 50

LEFT_OFFSET_X = 70
RIGHT_OFFSET_X = LEFT_OFFSET_X + BOARD_SIZE * CELL + 90
BOARD_OFFSET_Y = 130

SIDEBAR_X = RIGHT_OFFSET_X + BOARD_SIZE * CELL + 60
SIDEBAR_W = WINDOW_WIDTH - SIDEBAR_X - 30

BOTTOM_PANEL_Y = BOARD_OFFSET_Y + BOARD_SIZE * CELL + 32
BOTTOM_PANEL_H = WINDOW_HEIGHT - BOTTOM_PANEL_Y - 18

SHIP_ORDER = [
    ("Aircraft Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]

C_BG = (8, 18, 32)
C_BG_DEEP = (4, 12, 22)
C_GRID_DARK = (35, 60, 88)
C_WATER_A = (20, 42, 68)
C_WATER_B = (26, 50, 78)
C_SHIP = (160, 175, 195)
C_SHIP_DARK = (110, 125, 145)
C_SHIP_DAMAGED = (185, 130, 80)
C_SHIP_SUNK = (105, 55, 55)
C_PREVIEW_OK = (70, 190, 140, 130)
C_PREVIEW_BAD = (205, 85, 75, 130)
C_CURSOR_FIRE = (255, 200, 90)
C_CURSOR_PLACE = (140, 230, 170)
C_CURSOR_INSPECT = (190, 210, 240)
C_HIT = (220, 90, 70)
C_HIT_BRIGHT = (255, 140, 110)
C_MISS = (225, 235, 245)
C_GRID = (70, 110, 150)
C_TEXT = (240, 246, 252)
C_DIM = (155, 178, 205)
C_LABEL = (240, 200, 110)
C_GOLD = (212, 175, 95)
C_KEY = (255, 235, 170)
C_KEY_BORDER = (235, 50, 50)
C_DIVIDER = (45, 75, 108)
C_OK = (130, 220, 160)
C_WARN = (250, 195, 90)
C_BORDER = (90, 130, 170)


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
    mode_prefix = ""
    if phase == "battle" and inspect_mode == "own":
        mode_prefix = "Inspecting your grid. "
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


def describe_status():
    if phase == "placement":
        if placed_count < len(SHIP_ORDER):
            name, ln = SHIP_ORDER[placed_count]
            pos = _coord_label(selected_row, selected_col)
            return f"Placing {name} (length {ln}) at {pos} {orientation}"
        return "All ships placed. Press Enter to submit."
    if phase == "waiting":
        return "Ships submitted. Waiting for opponent."
    if phase == "game_over":
        return f"{game_over_message}  —  Escape to quit"
    if supabase_error:
        return f"Connection error: {supabase_error}"
    if my_turn:
        target = _coord_label(selected_row, selected_col)
        mode = "your grid (inspect)" if inspect_mode == "own" else f"firing at {target}"
        return f"YOUR TURN — {mode}"
    return "Opponent's turn. Listen for incoming fire."


def draw_background():
    screen.fill(C_BG)
    for y in range(WINDOW_HEIGHT):
        shade = int(8 * (1 - y / WINDOW_HEIGHT))
        pygame.draw.line(screen, (C_BG[0] + shade, C_BG[1] + shade, C_BG[2] + shade),
                         (0, y), (WINDOW_WIDTH, y))


def draw_title_bar():
    bar = pygame.Rect(0, 0, WINDOW_WIDTH, 70)
    pygame.draw.rect(screen, C_BG_DEEP, bar)
    pygame.draw.line(screen, C_GOLD, (0, 68), (WINDOW_WIDTH, 68), 1)
    pygame.draw.line(screen, C_DIVIDER, (0, 70), (WINDOW_WIDTH, 70), 1)
    title = font_title.render("E C H O   F L E E T", True, C_GOLD)
    screen.blit(title, (WINDOW_WIDTH // 2 - title.get_width() // 2, 12))
    sub = font_sm.render("BATTLESHIP — ACCESSIBLE EDITION", True, C_DIM)
    screen.blit(sub, (WINDOW_WIDTH // 2 - sub.get_width() // 2, 48))


def draw_grid(offset_x, hits, show_ships, label, is_active):
    grid_w = BOARD_SIZE * CELL
    label_color = C_LABEL if is_active else C_DIM
    label_surf = font_label.render(label, True, label_color)
    label_x = offset_x + (grid_w - label_surf.get_width()) // 2
    screen.blit(label_surf, (label_x, BOARD_OFFSET_Y - 58))

    for i in range(BOARD_SIZE):
        ch = chr(ord("A") + i)
        lbl = font_axis.render(ch, True, C_GOLD)
        screen.blit(lbl, (offset_x + i * CELL + CELL // 2 - lbl.get_width() // 2,
                          BOARD_OFFSET_Y - 26))
    for i in range(BOARD_SIZE):
        lbl = font_axis.render(str(i + 1), True, C_GOLD)
        screen.blit(lbl, (offset_x - 26,
                          BOARD_OFFSET_Y + i * CELL + CELL // 2 - lbl.get_height() // 2))

    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            rect = pygame.Rect(offset_x + col * CELL, BOARD_OFFSET_Y + row * CELL, CELL, CELL)
            water = C_WATER_A if (row + col) % 2 == 0 else C_WATER_B
            pygame.draw.rect(screen, water, rect)
            pygame.draw.rect(screen, C_GRID_DARK, rect, 1)

            if show_ships and own_ships[row][col]:
                ship_name = own_ship_names[row][col]
                if ship_name and ship_name in my_sunk:
                    fill = C_SHIP_SUNK
                elif hits_on_me[row][col] is True:
                    fill = C_SHIP_DAMAGED
                else:
                    fill = C_SHIP
                inner_rect = rect.inflate(-8, -8)
                pygame.draw.rect(screen, C_SHIP_DARK, inner_rect, border_radius=3)
                pygame.draw.rect(screen, fill, inner_rect.inflate(-2, -2), border_radius=2)

            if hits is not None:
                cell = hits[row][col]
                if cell == "hit" or cell is True:
                    pygame.draw.circle(screen, C_HIT, rect.center, CELL // 3)
                    pygame.draw.circle(screen, C_HIT_BRIGHT, rect.center, CELL // 3, 2)
                    marker = font_md.render("X", True, C_TEXT)
                    screen.blit(marker, marker.get_rect(center=rect.center))
                elif cell == "miss" or cell is False:
                    pygame.draw.circle(screen, C_MISS, rect.center, CELL // 5)
                    pygame.draw.circle(screen, C_GRID, rect.center, CELL // 5, 2)


def draw_placement_preview():
    if phase != "placement" or placed_count >= len(SHIP_ORDER):
        return
    valid = _placement_valid(placed_count, selected_row, selected_col, orientation)
    colour = C_PREVIEW_OK if valid else C_PREVIEW_BAD
    surface = pygame.Surface((CELL - 6, CELL - 6), pygame.SRCALPHA)
    surface.fill(colour)
    for r, c in _ship_coords(placed_count, selected_row, selected_col, orientation):
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            rect = pygame.Rect(LEFT_OFFSET_X + c * CELL + 3,
                               BOARD_OFFSET_Y + r * CELL + 3, CELL - 6, CELL - 6)
            screen.blit(surface, rect.topleft)


def draw_cursor():
    if phase == "placement":
        ox = LEFT_OFFSET_X
        col = C_CURSOR_PLACE
    elif phase in ("battle", "game_over"):
        if inspect_mode == "own":
            ox = LEFT_OFFSET_X
            col = C_CURSOR_INSPECT
        else:
            ox = RIGHT_OFFSET_X
            col = C_CURSOR_FIRE
    else:
        return

    rect = pygame.Rect(ox + selected_col * CELL, BOARD_OFFSET_Y + selected_row * CELL, CELL, CELL)
    pulse = (math.sin(time.time() * 5) + 1) / 2
    thickness = 3 + int(pulse * 2)
    pygame.draw.rect(screen, col, rect, thickness)
    tick = 8
    for cx, cy, dx, dy in [
        (rect.left, rect.top, 1, 1),
        (rect.right, rect.top, -1, 1),
        (rect.left, rect.bottom, 1, -1),
        (rect.right, rect.bottom, -1, -1),
    ]:
        pygame.draw.line(screen, col, (cx, cy), (cx + dx * tick, cy), 3)
        pygame.draw.line(screen, col, (cx, cy), (cx, cy + dy * tick), 3)

    if jump_buffer:
        hint = font_sm.render(f"jump: {jump_buffer}_", True, C_KEY)
        bg = pygame.Rect(rect.right + 8, rect.top - 4,
                         hint.get_width() + 10, hint.get_height() + 6)
        pygame.draw.rect(screen, C_BG_DEEP, bg, border_radius=3)
        pygame.draw.rect(screen, C_GOLD, bg, 1, border_radius=3)
        screen.blit(hint, (bg.left + 5, bg.top + 3))


def _draw_ship_icon(x, y, length, hits, sunk, cell_size=12):
    pad = 2
    for i in range(length):
        rect = pygame.Rect(x + i * (cell_size + pad), y, cell_size, cell_size)
        if sunk:
            color = C_SHIP_SUNK
        elif i < hits:
            color = C_SHIP_DAMAGED
        else:
            color = C_SHIP
        pygame.draw.rect(screen, color, rect, border_radius=2)
        pygame.draw.rect(screen, C_SHIP_DARK, rect, 1, border_radius=2)
        if i < hits:
            pygame.draw.line(screen, C_HIT, rect.topleft, rect.bottomright, 2)
            pygame.draw.line(screen, C_HIT, rect.topright, rect.bottomleft, 2)


def draw_sidebar():
    panel = pygame.Rect(SIDEBAR_X - 14, BOARD_OFFSET_Y - 62,
                        SIDEBAR_W + 14, BOARD_SIZE * CELL + 80)
    pygame.draw.rect(screen, C_BG_DEEP, panel, border_radius=6)
    pygame.draw.rect(screen, C_BORDER, panel, 2, border_radius=6)
    pygame.draw.rect(screen, C_GOLD, panel.inflate(-6, -6), 1, border_radius=4)

    pad = 14
    inner_x = panel.left + pad
    inner_right = panel.right - pad

    title = font_label.render("FLEET STATUS", True, C_GOLD)
    y = panel.top + 10
    screen.blit(title, (panel.left + (panel.width - title.get_width()) // 2, y))
    y += title.get_height() + 4
    pygame.draw.line(screen, C_DIVIDER, (inner_x, y), (inner_right, y), 1)
    y += 8

    your_lbl = font_sm_bold.render("YOUR FLEET", True, C_OK)
    screen.blit(your_lbl, (inner_x, y))
    y += your_lbl.get_height() + 4

    for name, length in SHIP_ORDER:
        cells = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)
                 if own_ship_names[r][c] == name]
        placed = len(cells) >= length
        hits = sum(1 for r, c in cells if hits_on_me[r][c] is True) if placed else 0
        sunk = placed and hits >= length
        name_color = C_DIM if not placed else (C_SHIP_SUNK if sunk else C_TEXT)
        nm = font_sm.render(name, True, name_color)
        screen.blit(nm, (inner_x, y))
        ln = font_xs.render(f"({length})", True, C_DIM)
        screen.blit(ln, (inner_x + nm.get_width() + 4, y + 2))
        _draw_ship_icon(inner_x + 4, y + nm.get_height() + 2, length, hits, sunk, cell_size=12)
        y += nm.get_height() + 18

    y += 4
    pygame.draw.line(screen, C_DIVIDER, (inner_x, y), (inner_right, y), 1)
    y += 8

    their_lbl = font_sm_bold.render("ENEMY FLEET", True, C_WARN)
    screen.blit(their_lbl, (inner_x, y))
    y += their_lbl.get_height() + 4

    for name, length in SHIP_ORDER:
        sunk = name in opponent_sunk
        nm = font_sm.render(name, True, C_SHIP_SUNK if sunk else C_TEXT)
        screen.blit(nm, (inner_x, y))
        ln = font_xs.render(f"({length})", True, C_DIM)
        screen.blit(ln, (inner_x + nm.get_width() + 4, y + 2))
        status = font_sm_bold.render("SUNK", True, C_HIT) if sunk else font_sm.render("...", True, C_DIM)
        screen.blit(status, (inner_right - status.get_width(), y))
        y += nm.get_height() + 4


def draw_status_panel():
    panel = pygame.Rect(20, BOTTOM_PANEL_Y, WINDOW_WIDTH - 40, BOTTOM_PANEL_H)
    pygame.draw.rect(screen, C_BG_DEEP, panel, border_radius=6)
    pygame.draw.rect(screen, C_BORDER, panel, 2, border_radius=6)
    pygame.draw.rect(screen, C_GOLD, panel.inflate(-6, -6), 1, border_radius=4)

    pad = 14
    max_w = panel.width - pad * 2
    line_h = 22
    y = panel.top + 10

    status_line = _fit_text(font_md, describe_status(), max_w)
    screen.blit(font_md.render(status_line, True, C_TEXT), (panel.left + pad, y))
    y += font_md.get_height() + 4

    if last_spoken_text:
        spoken = _fit_text(font_sm, last_spoken_text, max_w)
        screen.blit(font_sm.render(spoken, True, C_DIM), (panel.left + pad, y))
        y += line_h

    y += 4

    if phase == "placement":
        keys = [
            ("arrows", "move"), ("J", "rotate"), ("K", "shuffle"),
            ("Enter", "confirm"), ("A-H+1-8", "jump"),
            ("R", "row"), ("C", "col"), ("F", "fleet"), ("?", "help"),
        ]
    elif phase == "battle":
        keys = [
            ("arrows", "aim"), ("Enter", "fire"), ("Tab", "inspect"),
            ("A-H+1-8", "jump"), ("R", "row"), ("C", "col"),
            ("F", "fleet"), ("H", "hits"), ("M", "misses"),
            ("L", "last"), ("?", "help"),
        ]
    else:
        keys = [("Esc", "quit")]

    x = panel.left + pad
    key_pad_x, key_pad_y, inter_pad = 7, 3, 14

    for key, action in keys:
        key_surf = font_keys.render(key, True, C_KEY)
        act_surf = font_sm.render(action, True, C_DIM)
        key_w = key_surf.get_width() + key_pad_x * 2
        key_h = key_surf.get_height() + key_pad_y * 2
        block_w = key_w + 6 + act_surf.get_width()
        if x + block_w > panel.right - pad:
            x = panel.left + pad
            y += max(line_h, key_h + 4)
        key_y = y + (act_surf.get_height() - key_h) // 2 + 1
        cap = pygame.Rect(x, key_y, key_w, key_h)
        pygame.draw.rect(screen, "red", cap, border_radius=3)
        pygame.draw.rect(screen, C_KEY_BORDER, cap, 2, border_radius=3)
        screen.blit(key_surf, (x + key_pad_x, key_y + key_pad_y - 1))
        screen.blit(act_surf, (x + key_w + 6, y + 2))
        x += block_w + inter_pad

    if supabase_error:
        err = _fit_text(font_sm, f"! Connection error: {supabase_error}", max_w)
        screen.blit(font_sm.render(err, True, C_HIT_BRIGHT), (panel.left + pad, panel.bottom - 24))


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


def _find_seadoh_font():
    here = Path(__file__).resolve().parent
    candidates = []
    for folder in (here, here.parent, _repo_root, _repo_root / "fonts",
                   _repo_root / "assets", _repo_root / "assets" / "fonts"):
        for ext in (".ttf", ".otf", ".TTF", ".OTF"):
            for name in ("Seadoh", "seadoh", "SEADOH"):
                candidates.append(folder / f"{name}{ext}")
    if sys.platform.startswith("win"):
        win_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        user_fonts = Path.home() / "AppData/Local/Microsoft/Windows/Fonts"
        for folder in (win_fonts, user_fonts):
            for ext in (".ttf", ".otf"):
                for name in ("Seadoh", "seadoh"):
                    candidates.append(folder / f"{name}{ext}")
    for p in candidates:
        try:
            if p.exists():
                return str(p)
        except OSError:
            continue
    return None


def _make_font(font_path, size, bold=False, fallback=None):
    if font_path:
        try:
            f = pygame.font.Font(font_path, size)
            if bold:
                f.set_bold(True)
            return f
        except Exception as e:
            print(f"Failed to load font {font_path}: {e}")
    candidates = fallback or ["Verdana", "Tahoma", "Trebuchet MS"]
    for name in candidates:
        if name.lower().replace(" ", "") in pygame.font.get_fonts():
            return pygame.font.SysFont(name, size, bold=bold)
    return pygame.font.SysFont(None, size, bold=bold)


def main():
    global args, phase, placed_count, orientation
    global own_ships, own_ship_names, hits_on_me, hits_on_opponent
    global selected_row, selected_col
    global lock, my_turn, opponent_ready, game_over_message, i_won
    global supabase_error, last_event, opponent_sunk, my_sunk, inspect_mode, jump_buffer
    global _layout, screen
    global font_xs, font_sm, font_sm_bold, font_md, font_label, font_keys, font_axis, font_title
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
    pygame.display.set_caption("EchoFleet Battleship")

    seadoh_path = _find_seadoh_font()
    if seadoh_path:
        print(f"[font] Using Seadoh from: {seadoh_path}")
    else:
        print("[font] Seadoh not found — drop Seadoh.ttf into the Battleship folder or set SEADOH_FONT env var.")
        env_path = os.environ.get("SEADOH_FONT")
        if env_path and Path(env_path).exists():
            seadoh_path = env_path
            print(f"[font] Loaded Seadoh from env var: {seadoh_path}")

    font_title   = _make_font(seadoh_path, 32, bold=True)
    font_label   = _make_font(seadoh_path, 22, bold=True)
    font_md      = _make_font(seadoh_path, 22, bold=False)
    font_sm      = _make_font(seadoh_path, 16, bold=False)
    font_sm_bold = _make_font(seadoh_path, 16, bold=True)
    font_xs      = _make_font(seadoh_path, 13, bold=False)
    font_keys    = _make_font(seadoh_path, 14, bold=True)
    font_axis    = _make_font(seadoh_path, 16, bold=True)

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
        draw_background()
        draw_title_bar()
        draw_grid(LEFT_OFFSET_X, hits_on_me, show_ships=True,
                  label="YOUR FLEET",
                  is_active=(phase == "placement" or
                             (phase == "battle" and inspect_mode == "own")))
        draw_grid(RIGHT_OFFSET_X, hits_on_opponent, show_ships=False,
                  label="ENEMY WATERS",
                  is_active=(phase == "battle" and inspect_mode == "fire" and my_turn))
        draw_placement_preview()
        draw_cursor()
        draw_sidebar()
        draw_status_panel()
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
                                        last_event = (
                                            f"You hit at {_coord_label(selected_row, selected_col)}."
                                        )
                                        _position_cue(selected_row, selected_col, volume=0.4).play()
                                        pygame.time.set_timer(EVT_HIT_SOUND, 200, loops=1)
                                        speak_now(
                                            f"Hit at {_coord_spoken(selected_row, selected_col)}."
                                        )
                                    if status == "win":
                                        phase = "game_over"
                                        game_over_message = "Victory! All enemy ships destroyed."
                                        i_won = True
                                        speak_now(
                                            "Victory! All enemy ships destroyed. Escape to quit."
                                        )
                                        threading.Thread(target=report_win, daemon=True).start()
                                    else:
                                        my_turn = False
                                elif status == "miss":
                                    hits_on_opponent[selected_row][selected_col] = "miss"
                                    last_event = (
                                        f"You missed at {_coord_label(selected_row, selected_col)}."
                                    )
                                    _position_cue(selected_row, selected_col, volume=0.4).play()
                                    pygame.time.set_timer(EVT_MISS_SOUND, 200, loops=1)
                                    speak_now(
                                        f"Miss at {_coord_spoken(selected_row, selected_col)}."
                                    )
                                    my_turn = False
                        except Exception as e:
                            SND_BAD.play()
                            speak_now(str(e))

                elif phase == "battle" and inspect_mode == "own":
                    speak_now("Press Tab to return to firing mode.")
                continue

    pygame.quit()


main()
