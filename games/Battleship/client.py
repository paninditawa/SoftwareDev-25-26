"""
Battleship client — EchoFleet (Supabase backend).
Polls Supabase for game state every second instead of using a local socket server.
"""

from __future__ import annotations
import argparse
import sys
import threading
import time
from pathlib import Path
import numpy as np
import pygame

# Walk up dirs to find repo root (where tts.py and launcher/ live)
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


def speak(text: str, interrupt: bool = False):
    global last_spoken_text
    last_spoken_text = text
    if interrupt:
        _tts_speak_interrupt(text)
    else:
        _tts_speak(text)


speak_interrupt = lambda text: speak(text, interrupt=True)

# board + window dimensions
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


def _tone(freq: float, duration: float = 0.25, volume: float = 0.55) -> pygame.mixer.Sound:
    sr = 44100
    t = np.linspace(0, duration, int(sr * duration), False)
    wave = np.sin(freq * t * 2 * np.pi) * np.exp(-t * 3)
    audio = (wave * 32767 * volume).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack((audio, audio)))


def parse_args():
    p = argparse.ArgumentParser(description="Battleship client")
    p.add_argument("--game-code", default="")
    p.add_argument("--game-id", default="")
    p.add_argument("--player-num", type=int, default=0)
    p.add_argument("--user-id", default="")
    p.add_argument("--username", default="Player")
    p.add_argument("--launcher-pid", type=int, default=0)
    return p.parse_args()


def _make_random_layout() -> list[tuple[int, int, str]]:
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


def _ship_coords(ship_index: int, row: int, col: int, orient: str) -> list[tuple[int, int]]:
    _, length = SHIP_ORDER[ship_index]
    return (
        [(row, col + i) for i in range(length)] if orient == "H"
        else [(row + i, col) for i in range(length)]
    )


def _placement_valid(ship_index: int, row: int, col: int, orient: str) -> bool:
    coords = _ship_coords(ship_index, row, col, orient)
    if any(r < 0 or r >= BOARD_SIZE or c < 0 or c >= BOARD_SIZE for r, c in coords):
        return False
    confirmed: set[tuple[int, int]] = set()
    for i in range(placed_count):
        confirmed.update(_ship_coords(i, *_layout[i][:2], _layout[i][2]))
    return not any(coord in confirmed for coord in coords)


def _mark_confirmed(ship_index: int) -> None:
    for r, c in _ship_coords(ship_index, *_layout[ship_index][:2], _layout[ship_index][2]):
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            own_ships[r][c] = True


def _sync_cursor_to_ship() -> None:
    global selected_row, selected_col, orientation
    if placed_count < len(SHIP_ORDER):
        selected_row, selected_col, orientation = _layout[placed_count]


def report_win() -> None:
    if not args.user_id:
        return
    try:
        from launcher.services.leaderboard import Scoreboard
        sb = Scoreboard.from_workspace(_repo_root)
        sb.record_win(args.user_id, args.username, "battleship")
    except Exception as exc:
        print(f"scoreboard write failed: {exc}")


def describe_status() -> str:
    if phase == "placement":
        if placed_count < len(SHIP_ORDER):
            name, ln = SHIP_ORDER[placed_count]
            return f"Placing {name} (len {ln}) — arrows to nudge, J to rotate, Enter to confirm"
        return "All ships placed. Press Enter to submit."
    if phase == "waiting":
        return "Ships submitted. Waiting for opponent…"
    if phase == "game_over":
        return f"{game_over_message}  —  Escape to quit"
    if supabase_error:
        return f"Connection error: {supabase_error}"
    return "YOUR TURN — arrows to aim, Enter or Space to fire" if my_turn else "Opponent's turn…"


def poll_supabase() -> None:
    global phase, my_turn, hits_on_me, hits_on_opponent
    global game_over_message, i_won, opponent_ready, supabase_error

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

                # Sync opponent's shots → my board (hits on me)
                for shot in state["opponent_shots"]:
                    r, c = int(shot["row"]), int(shot["col"])
                    hits_on_me[r][c] = "hit" if shot["result"] == "hit" else "miss"

                # Sync my shots → opponent board display
                for shot in state["my_shots"]:
                    r, c = int(shot["row"]), int(shot["col"])
                    hits_on_opponent[r][c] = "hit" if shot["result"] == "hit" else "miss"

                opponent_ready = state["opponent_ready"]

                if service_phase == "battle" and phase in ("placement", "waiting"):
                    phase = "battle"
                    speak_interrupt("Battle begins!")

                elif service_phase == "game_over" and phase != "game_over":
                    phase = "game_over"
                    last_msg = game_info.get("last_msg", "Game over.")
                    game_over_message = last_msg
                    i_won = args.username in last_msg and "wins" in last_msg.lower()
                    if i_won:
                        SND_WIN.play()
                        speak_interrupt("You win!")
                        threading.Thread(target=report_win, daemon=True).start()
                    else:
                        SND_LOSE.play()
                        speak_interrupt("You lose.")

                if service_phase == "battle":
                    my_turn = (int(game_info["turn"]) == args.player_num)

                supabase_error = ""

        except Exception as e:
            supabase_error = str(e)


def _fit_text(font, text: str, max_width: int) -> str:
    if font.size(text)[0] <= max_width:
        return text
    trimmed = text
    while trimmed and font.size(trimmed + "...")[0] > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + "...") if trimmed else "..."


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
        ox = RIGHT_OFFSET_X
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
    line = _fit_text(font_md, describe_status(), max_w)
    screen.blit(font_md.render(line, True, C_TEXT), (20, y))
    if last_spoken_text:
        spoken = _fit_text(font_sm, f"↗ {last_spoken_text}", max_w)
        screen.blit(font_sm.render(spoken, True, C_DIM), (20, y + 28))
    if supabase_error:
        err = _fit_text(font_sm, f"Error: {supabase_error}", max_w)
        screen.blit(font_sm.render(err, True, C_HIT), (20, y + 50))


def main() -> None:
    global args, phase, placed_count, orientation
    global own_ships, hits_on_me, hits_on_opponent, selected_row, selected_col
    global lock, my_turn, opponent_ready, game_over_message, i_won
    global supabase_error, screen, font_sm, font_md, _layout
    global SND_HIT, SND_MISS, SND_SINK, SND_WIN, SND_LOSE, SND_MOVE, SND_USED, SND_BAD

    args = parse_args()

    speak_interrupt(
        f"Connected as player {args.player_num + 1}. "
        "Arrow keys to adjust each ship, J to rotate, Enter to confirm each ship, "
        "then Enter again to submit all ships."
    )

    phase = "placement"
    placed_count = 0
    orientation = "H"
    own_ships = [[False] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    hits_on_me = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    hits_on_opponent = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    selected_row = 0
    selected_col = 0

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

    SND_HIT  = _tone(980,  0.30)
    SND_MISS = _tone(280,  0.25)
    SND_SINK = _tone(1200, 0.50)
    SND_WIN  = _tone(1400, 0.70)
    SND_LOSE = _tone(200,  0.70)
    SND_MOVE = _tone(600,  0.08, 0.25)
    SND_USED = _tone(150,  0.15, 0.35)
    SND_BAD  = _tone(180,  0.12, 0.40)

    screen  = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    font_sm = pygame.font.SysFont("segoeui", 22, bold=False)
    font_md = pygame.font.SysFont("segoeui", 28, bold=False)
    pygame.display.set_caption("EchoFleet Battleship")

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

            if event.type != pygame.KEYDOWN:
                continue

            key = event.key

            if key == pygame.K_ESCAPE:
                speak_interrupt("Leaving game.")
                running = False
                break

            dr = dc = 0
            if key == pygame.K_UP:    dr = -1
            elif key == pygame.K_DOWN:  dr = 1
            elif key == pygame.K_LEFT:  dc = -1
            elif key == pygame.K_RIGHT: dc = 1

            if dr or dc:
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
                    speak_interrupt(f"Row {selected_row + 1}, column {selected_col + 1}")
                elif phase == "battle":
                    selected_row = max(0, min(BOARD_SIZE - 1, selected_row + dr))
                    selected_col = max(0, min(BOARD_SIZE - 1, selected_col + dc))
                    speak_interrupt(f"Row {selected_row + 1}, {chr(ord('A') + selected_col)}")
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
                    speak_interrupt(f"Rotated to {orientation}")

            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                if phase == "placement" and placed_count < len(SHIP_ORDER):
                    if _placement_valid(placed_count, selected_row, selected_col, orientation):
                        idx = placed_count
                        placed_count += 1
                        _mark_confirmed(idx)
                        name, _ = SHIP_ORDER[idx]
                        speak_interrupt(f"{name} confirmed.")
                        if placed_count < len(SHIP_ORDER):
                            _sync_cursor_to_ship()
                        else:
                            speak_interrupt("All ships placed. Press Enter to submit.")
                    else:
                        SND_BAD.play()
                        speak_interrupt("Can't place there.")

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
                        speak_interrupt("Ships submitted. Waiting for opponent.")
                    except Exception as e:
                        SND_BAD.play()
                        speak_interrupt(f"Could not submit: {e}")

                elif phase == "battle" and my_turn:
                    try:
                        result = battleship_service.fire(args.game_id, args.player_num, selected_row, selected_col)
                        status = result["status"]
                        with lock:
                            if status in ("hit", "win"):
                                hits_on_opponent[selected_row][selected_col] = "hit"
                                (SND_SINK if result.get("sunk") else SND_HIT).play()
                                if status == "win":
                                    phase = "game_over"
                                    game_over_message = "You win!"
                                    i_won = True
                                    speak_interrupt("You win!")
                                    threading.Thread(target=report_win, daemon=True).start()
                                else:
                                    my_turn = False
                            elif status == "miss":
                                hits_on_opponent[selected_row][selected_col] = "miss"
                                SND_MISS.play()
                                my_turn = False
                    except Exception as e:
                        SND_BAD.play()
                        speak_interrupt(str(e))

    pygame.quit()


main()
