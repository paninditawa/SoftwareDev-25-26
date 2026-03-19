"""
Battleship client using pygame. Connects to a server, handles ship placement, 
completes actions based on turns, and displays game state.
"""

from __future__ import annotations
import argparse
import socket
import sys
import threading
import time
from pathlib import Path
import numpy as np
import pygame

# Find tts.py so it can be imported regardless of current working directory
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

last_spoken_text = ""

def speak(text: str, interrupt: bool = False):
    """
    Speaks the given text aloud using TTS.

    Params: 
    text (str) - text to speak, 
    interrupt (bool) - whether to interrupt current speech
    """
    global last_spoken_text
    last_spoken_text = text
    if interrupt:
        _tts_speak_interrupt(text)
    else:
        _tts_speak(text)

speak_interrupt = lambda text: speak(text, interrupt=True)

# Network settings
HOST = "127.0.0.1"
PORT = 5555

# Board and window dimensions
BOARD_SIZE = 8
WINDOW_WIDTH = 860
WINDOW_HEIGHT = 480
CELL = min(WINDOW_WIDTH // (BOARD_SIZE * 2 + 2), WINDOW_HEIGHT // (BOARD_SIZE + 2))

# Board offsets for your ships (left) and opponent ships (right)
LEFT_OFFSET_X = 20
RIGHT_OFFSET_X = LEFT_OFFSET_X + BOARD_SIZE * CELL + 40
BOARD_OFFSET_Y = 40

# Ships to place in order, with their lengths
SHIP_ORDER = [
    ("Aircraft Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]

# Color palette
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

pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=2)

def _tone(freq: float, duration: float = 0.25, volume: float = 0.55) -> pygame.mixer.Sound:
    """
    Generates a simple sine wave tone as a pygame Sound object.

    Params: 
    freq (float) - frequency in Hz, 
    duration (float) - length in seconds,
    volume (float) - amplitude scale
    
    Returns: 
    pygame.mixer.Sound
    """
    sr = 44100
    t = np.linspace(0, duration, int(sr * duration), False)
    wave = np.sin(freq * t * 2 * np.pi) * np.exp(-t * 3)
    audio = (wave * 32767 * volume).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack((audio, audio)))

# Sound effects for various game events
SND_HIT = _tone(980, 0.30)
SND_MISS = _tone(280, 0.25)
SND_SINK = _tone(1200, 0.50)
SND_WIN = _tone(1400, 0.70)
SND_LOSE = _tone(200, 0.70)
SND_MOVE = _tone(600, 0.08, 0.25)
SND_USED = _tone(150, 0.15, 0.35)
SND_BAD = _tone(180, 0.12, 0.40)


def parse_args():
    """Parses command-line arguments for host, port, user ID, username, and launcher PID."""
    p = argparse.ArgumentParser(description="Battleship client")
    p.add_argument("--host", default=HOST)
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--user-id", default="")
    p.add_argument("--username", default="Player")
    p.add_argument("--launcher-pid", type=int, default=0)
    return p.parse_args()

args = parse_args()

# Connect to server and receive assigned player ID
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((args.host, args.port))
welcome = sock.recv(1024).decode().strip()
try:
    player_id = int(welcome.split()[-1])
except Exception:
    player_id = 0

speak(f"Connected as player {player_id + 1}. Arrow keys to adjust each ship, R to rotate, Enter to confirm.")

# Game state variables
phase = "placement"
placed_count = 0
orientation = "H"

own_ships = [[False] * BOARD_SIZE for _ in range(BOARD_SIZE)]
hits_on_me = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
hits_on_opponent = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]

selected_row = 0
selected_col = 0

# Pending placement data while waiting for server confirmation
pending_row = None
pending_col = None
pending_orient = None
pending_index = None

lock = threading.Lock()
my_turn = False
ready = False
opponent_ready = False
awaiting_place_response = False
last_place_time = 0.0
server_connected = True
server_error = ""
game_over_message = ""
i_won = False
_place_ok_count = 0


def _make_random_layout() -> list[tuple[int, int, str]]:
    """
    Generates a random valid ship layout for the board.

    Returns: 
    list of (row, col, orientation) tuples, 
    one per ship in SHIP_ORDER
    """
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

# Generate initial random layout; player can adjust ships before confirming
_layout = _make_random_layout()


def _ship_coords(ship_index: int, row: int, col: int, orient: str) -> list[tuple[int, int]]:
    """
    Returns the list of (row, col) cells a ship occupies.

    Params: 
    ship_index (int), 
    row (int), 
    col (int), 
    orient (str) - 'H' or 'V'

    Returns: 
    list of (row, col) tuples
    """
    _, length = SHIP_ORDER[ship_index]
    return (
        [(row, col + i) for i in range(length)] if orient == "H"
        else [(row + i, col) for i in range(length)]
    )

def _placement_valid(ship_index: int, row: int, col: int, orient: str) -> bool:
    """
    Checks whether a ship can be placed at the given position without going
    out of bounds or overlapping already-confirmed ships.

    Returns: 
    bool
    """
    coords = _ship_coords(ship_index, row, col, orient)
    if any(r < 0 or r >= BOARD_SIZE or c < 0 or c >= BOARD_SIZE for r, c in coords):
        return False
    # Only check against already-confirmed ships, not the current one
    confirmed: set[tuple[int, int]] = set()
    for i in range(placed_count):
        confirmed.update(_ship_coords(i, *_layout[i][:2], _layout[i][2]))
    return not any(coord in confirmed for coord in coords)

def _mark_confirmed(ship_index: int) -> None:
    """Marks all cells of a confirmed ship as occupied on own_ships."""
    for r, c in _ship_coords(ship_index, *_layout[ship_index][:2], _layout[ship_index][2]):
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            own_ships[r][c] = True

def _sync_cursor_to_ship() -> None:
    """Moves the cursor to the starting position of the next ship to be placed."""
    global selected_row, selected_col, orientation
    if placed_count < len(SHIP_ORDER):
        selected_row, selected_col, orientation = _layout[placed_count]

_sync_cursor_to_ship()


def send_line(line: str) -> None:
    """Sends a newline-terminated string to the server."""
    try:
        sock.sendall((line + "\n").encode())
    except Exception as e:
        print("Send failed:", e)

def report_win() -> None:
    """Records a win to the scoreboard if a user ID is provided."""
    if not args.user_id:
        return
    try:
        sys.path.insert(0, str(_repo_root))
        from launcher.services.leaderboard import Scoreboard
        sb = Scoreboard.from_workspace(_repo_root)
        sb.record_win(args.user_id, args.username, "battleship")
    except Exception as exc:
        print(f"scoreboard write failed: {exc}")


def describe_status() -> str:
    """Returns a status string describing the current game phase and available actions."""
    if phase == "placement":
        if awaiting_place_response:
            return "Confirming placement…"
        if placed_count < len(SHIP_ORDER):
            name, ln = SHIP_ORDER[placed_count]
            return f"Placing {name} (len {ln}) — arrows to nudge, R to rotate, Enter to confirm"
        return "All ships placed. Waiting for opponent."
    if phase == "waiting":
        return "Waiting for opponent."
    if phase == "game_over":
        return f"{game_over_message}  —  R to rematch, Q to quit"
    return "YOUR TURN — arrows to aim, Enter or Space to fire" if my_turn else "Opponent's turn…"


def listen_server() -> None:
    """
    Runs in a background thread. Reads messages from the server and updates
    game state accordingly.
    """
    global my_turn, phase, ready, opponent_ready, placed_count
    global awaiting_place_response, pending_row, pending_col, pending_orient, pending_index
    global own_ships, hits_on_me, hits_on_opponent, server_connected, server_error
    global game_over_message, i_won, _place_ok_count, _layout

    buffer = ""
    while True:
        try:
            data = sock.recv(1024).decode()
            if not data:
                server_connected = False
                server_error = "Server disconnected."
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                with lock:
                    parts = line.split()
                    cmd = parts[0].upper()

                    if cmd == "START":
                        phase = "battle"
                        speak("Game on.")

                    elif cmd == "YOUR_TURN":
                        my_turn = True
                        speak("Your turn.")

                    elif cmd == "OPPONENT_TURN":
                        my_turn = False

                    elif cmd == "READY_OK":
                        ready = True
                        phase = "waiting"
                        speak("Ready. Waiting for opponent.")

                    elif cmd == "OPPONENT_READY":
                        opponent_ready = True

                    elif cmd == "RESET":
                        # Reset all state for a new game
                        phase = "placement"
                        placed_count = 0
                        orientation = "H"
                        own_ships = [[False] * BOARD_SIZE for _ in range(BOARD_SIZE)]
                        hits_on_me = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
                        hits_on_opponent = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
                        ready = opponent_ready = my_turn = False
                        awaiting_place_response = False
                        pending_row = pending_col = pending_orient = pending_index = None
                        game_over_message = ""
                        i_won = False
                        _place_ok_count = 0
                        _layout = _make_random_layout()
                        _sync_cursor_to_ship()
                        speak("New game. Arrow keys to adjust ships, Enter to confirm each one.")

                    elif cmd == "PLACE_OK":
                        _place_ok_count += 1
                        _mark_confirmed(pending_index if pending_index is not None else placed_count - 1)
                        awaiting_place_response = False
                        pending_row = pending_col = pending_orient = pending_index = None
                        if _place_ok_count >= len(SHIP_ORDER) and not ready:
                            send_line("READY")

                    elif cmd == "PLACE_ERR":
                        if pending_index is not None and placed_count > pending_index:
                            placed_count = pending_index
                        awaiting_place_response = False
                        pending_index = pending_row = pending_col = pending_orient = None
                        speak("Can't place there. Move the ship and try again.")

                    elif cmd == "RESULT":
                        sub = parts[1] if len(parts) > 1 else ""
                        if sub == "MISS":
                            r, c = int(parts[2]), int(parts[3])
                            hits_on_opponent[r][c] = "miss"
                            SND_MISS.play()
                        elif sub == "HIT":
                            r, c = int(parts[2]), int(parts[3])
                            sunk = parts[5] == "True"
                            hits_on_opponent[r][c] = "hit"
                            (SND_SINK if sunk else SND_HIT).play()
                        elif sub == "USED":
                            SND_USED.play()
                        elif sub == "WIN":
                            i_won = True
                            game_over_message = "You win!"
                            phase = "game_over"
                            SND_WIN.play()
                            speak("You win!")
                            threading.Thread(target=report_win, daemon=True).start()
                        elif sub == "LOSE":
                            game_over_message = "You lose."
                            phase = "game_over"
                            SND_LOSE.play()
                            speak("You lose.")

                    elif cmd == "OPPONENT_FIRE":
                        r, c = int(parts[1]), int(parts[2])
                        hits_on_me[r][c] = True if parts[3] == "HIT" else False

        except Exception as e:
            server_connected = False
            server_error = str(e)
            break


threading.Thread(target=listen_server, daemon=True).start()

# Initialize pygame display and fonts
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
font_sm = pygame.font.SysFont("segoeui", 22, bold=False)
font_md = pygame.font.SysFont("segoeui", 28, bold=False)
pygame.display.set_caption("EchoFleet Battleship")


def _fit_text(font, text: str, max_width: int) -> str:
    """
    Trims text with "..." if it exceeds max_width pixels.

    Returns:
    str
    """
    if font.size(text)[0] <= max_width:
        return text
    trimmed = text
    while trimmed and font.size(trimmed + "...")[0] > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + "...") if trimmed else "..."


def draw_grid(offset_x: int, hits, show_ships: bool) -> None:
    """
    Draws one of the two game grids, including ship tiles and hit/miss markers.
    
    Params: 
    offset_x (int) - horizontal offset, 
    hits - 2D list of hit data,
    show_ships (bool) - whether to reveal ship positions
    """
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
    """
    Draws a transparent preview of the current ship being placed.
    Shows green if valid position, red if invalid.
    """
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
    """Draws the selection cursor on whichever grid is currently active."""
    if phase == "placement":
        ox = LEFT_OFFSET_X
    elif phase in ("battle", "game_over"):
        ox = RIGHT_OFFSET_X
    else:
        return
    rect = pygame.Rect(ox + selected_col * CELL, BOARD_OFFSET_Y + selected_row * CELL, CELL, CELL)
    pygame.draw.rect(screen, C_SELECT, rect, 3)


def draw_labels() -> None:
    """Draws the column letters and row numbers along both grids."""
    for i in range(BOARD_SIZE):
        ch = chr(ord("A") + i)
        for ox in (LEFT_OFFSET_X, RIGHT_OFFSET_X):
            lbl = font_sm.render(ch, True, C_DIM)
            screen.blit(lbl, (ox + i * CELL + CELL // 2 - 5, BOARD_OFFSET_Y - 18))
        for ox in (LEFT_OFFSET_X - 18, RIGHT_OFFSET_X - 18):
            lbl = font_sm.render(str(i + 1), True, C_DIM)
            screen.blit(lbl, (ox, BOARD_OFFSET_Y + i * CELL + CELL // 2 - 8))
    screen.blit(font_md.render("YOUR SHIPS", True, C_LABEL), (LEFT_OFFSET_X, BOARD_OFFSET_Y - 26))
    screen.blit(font_md.render("FIRE HERE", True, C_LABEL), (RIGHT_OFFSET_X, BOARD_OFFSET_Y - 26))


def draw_status() -> None:
    """Draws the status bar at the bottom, including the last spoken TTS line and any errors."""
    y = BOARD_OFFSET_Y + BOARD_SIZE * CELL + 10
    max_w = WINDOW_WIDTH - 40
    line = _fit_text(font_md, describe_status(), max_w)
    screen.blit(font_md.render(line, True, C_TEXT), (20, y))
    if last_spoken_text:
        spoken = _fit_text(font_sm, f"↗ {last_spoken_text}", max_w)
        screen.blit(font_sm.render(spoken, True, C_DIM), (20, y + 28))
    if not server_connected:
        err = _fit_text(font_sm, f"Disconnected: {server_error}", max_w)
        screen.blit(font_sm.render(err, True, C_HIT), (20, y + 50))


# Main game loop
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

    # Time out placement confirmation if server doesn't respond
    if awaiting_place_response and time.time() - last_place_time > 3:
        awaiting_place_response = False

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type != pygame.KEYDOWN:
            continue

        key = event.key

        # Arrow key movement
        dr = dc = 0
        if key == pygame.K_UP: dr = -1
        elif key == pygame.K_DOWN: dr = 1
        elif key == pygame.K_LEFT: dc = -1
        elif key == pygame.K_RIGHT: dc = 1

        if dr or dc:
            SND_MOVE.play()
            if phase == "placement" and placed_count < len(SHIP_ORDER):
                _, length = SHIP_ORDER[placed_count]
                nr = max(0, min(BOARD_SIZE - 1, selected_row + dr))
                nc = max(0, min(BOARD_SIZE - 1, selected_col + dc))
                # Clamp so the whole ship stays on the board
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

        if key == pygame.K_r:
            if phase == "placement" and placed_count < len(SHIP_ORDER):
                orientation = "V" if orientation == "H" else "H"
                # Clamp after rotation so ship stays on board
                _, length = SHIP_ORDER[placed_count]
                if orientation == "H":
                    selected_col = min(selected_col, BOARD_SIZE - length)
                else:
                    selected_row = min(selected_row, BOARD_SIZE - length)
                _layout[placed_count] = (selected_row, selected_col, orientation)
                speak(f"Rotated to {orientation}")
            elif phase == "game_over":
                send_line("REMATCH")
                speak("Rematch requested.")

        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            if phase == "placement" and not awaiting_place_response and placed_count < len(SHIP_ORDER):
                if _placement_valid(placed_count, selected_row, selected_col, orientation):
                    pending_row = selected_row
                    pending_col = selected_col
                    pending_orient = orientation
                    pending_index = placed_count
                    placed_count += 1
                    send_line(f"PLACE {pending_index} {pending_row} {pending_col} {pending_orient}")
                    awaiting_place_response = True
                    last_place_time = time.time()
                    name, _ = SHIP_ORDER[pending_index]
                    speak(f"{name} confirmed.")
                    if placed_count < len(SHIP_ORDER):
                        _sync_cursor_to_ship()
                else:
                    SND_BAD.play()
                    speak("Can't place there.")
            elif phase == "placement" and placed_count >= len(SHIP_ORDER) and not ready:
                send_line("READY")
                speak("Ready. Waiting for opponent.")
            elif phase == "battle" and my_turn:
                send_line(f"FIRE {selected_row} {selected_col}")
                speak(f"Firing row {selected_row + 1}, {chr(ord('A') + selected_col)}.")

        elif key in (pygame.K_q, pygame.K_ESCAPE) and phase == "game_over":
            send_line("QUIT")
            running = False

        elif key == pygame.K_t:
            SND_HIT.play()

pygame.quit()
try:
    sock.close()
except Exception:
    pass