import argparse
import os
import pygame
import socket
import threading
import time
import numpy as np
import sys
from pathlib import Path

# Ensure the repo root (where `tts.py` lives) is on sys.path so the shared TTS helper can be imported.
# This walks up the directory tree until it finds tts.py.
_repo_root = Path(__file__).resolve()
while _repo_root != _repo_root.parent:
    if (_repo_root / "tts.py").exists():
        break
    _repo_root = _repo_root.parent

if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Cross-platform TTS helper
try:
    from tts import speak as _tts_speak, speak_interrupt as _tts_speak_interrupt
except ImportError:
    def _tts_speak(text: str):
        print(text)

    def _tts_speak_interrupt(text: str):
        print(text)

# Track the most recent spoken text so we can show it on-screen (useful if audio isn't audible).
last_spoken_text = ""

def tts_speak(text: str, interrupt: bool = False):
    """Speak text while also recording it for on-screen display."""
    global last_spoken_text
    last_spoken_text = text
    if interrupt:
        _tts_speak_interrupt(text)
    else:
        _tts_speak(text)


# Keep existing code paths working with speak()/speak_interrupt().
# This allows the rest of the file to continue using `speak()` without changes.
speak = tts_speak
speak_interrupt = lambda text: tts_speak(text, interrupt=True)

HOST = "127.0.0.1"
PORT = 5555
BOARD_SIZE = 8
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 440
CELL = min(WINDOW_WIDTH // (BOARD_SIZE * 2), WINDOW_HEIGHT // BOARD_SIZE)

pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=2)
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("EchoFleet Battleship")
font = pygame.font.SysFont(None, 24)

# Simple tone generator for feedback.
def generate_tone(freq, duration=0.3, volume=0.5):
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = np.sin(freq * t * 2 * np.pi)
    audio = (tone * 32767 * volume).astype(np.int16)
    stereo_audio = np.column_stack((audio, audio))
    return pygame.sndarray.make_sound(stereo_audio)

HIT_SOUND = generate_tone(1000)
MISS_SOUND = generate_tone(300)
USED_SOUND = generate_tone(150, 0.15)
WIN_SOUND = generate_tone(1200, 0.6)

SHIP_ORDER = [
    ("Aircraft Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]


def parse_args():
    p = argparse.ArgumentParser(description="Battleship client")
    p.add_argument("--host", default=HOST, help="Server IP / host")
    p.add_argument("--port", type=int, default=PORT, help="Server port")
    return p.parse_args()

args = parse_args()

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((args.host, args.port))
# Server sends a welcome line like "PLAYER 0"; parse player ID.
welcome = sock.recv(1024).decode().strip()
if welcome.startswith("PLAYER"):
    try:
        player_id = int(welcome.split()[1])
    except Exception:
        player_id = 0
else:
    try:
        player_id = int(welcome)
    except Exception:
        player_id = 0
print(f"Connected as Player {player_id} to {args.host}:{args.port}")
speak(f"Connected as player {player_id}")

# Game state
phase = "placement"  # or "battle"
placed_count = 0  # how many ships have been successfully placed
orientation = "H"
own_ships = [[False] * BOARD_SIZE for _ in range(BOARD_SIZE)]
hits_on_me = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
hits_on_opponent = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]

selected_row = 0
selected_col = 0

# Store the coordinates/orientation of the last ship placement request so we can
# mark it correctly once the server confirms placement.
pending_placement_row = None
pending_placement_col = None
pending_placement_orientation = None
pending_ship_index = None

lock = threading.Lock()
my_turn = False
ready = False
opponent_ready = False
awaiting_place_response = False
last_place_request_time = 0.0
last_server_line = ""
last_send_line = ""
last_send_error = ""
server_connected = True
server_error = ""

# Game over state
game_over_message = ""


def describe_status():
    if phase == "placement":
        if awaiting_place_response:
            return "Waiting for server to confirm placement (press space to retry)."
        if placed_count < len(SHIP_ORDER):
            ship_name, ship_len = SHIP_ORDER[placed_count]
            return f"Placing {ship_name} ({ship_len}) orientation {orientation}. Press R to rotate."
        return "All ships placed. Waiting for opponent."
    if phase == "waiting":
        return "Waiting for opponent to finish placement."
    if phase == "game_over":
        return "Game over: press R to rematch or Q to quit."
    return "Your turn" if my_turn else "Opponent's turn"


def send_line(line: str):
    global last_send_line, last_send_error
    last_send_line = line
    last_send_error = ""
    try:
        print(">>", line)
        sock.sendall((line + "\n").encode())
    except Exception as e:
        last_send_error = str(e)
        print("Send failed:", e)


def mark_ship_placement(ship_index: int, row: int, col: int, orient: str):
    name, length = SHIP_ORDER[ship_index]
    coords = []
    if orient == "H":
        coords = [(row, col + i) for i in range(length)]
    else:
        coords = [(row + i, col) for i in range(length)]
    for r, c in coords:
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            own_ships[r][c] = True


def listen_server():
    global my_turn, phase, ready, opponent_ready, placed_count, awaiting_place_response
    global pending_placement_row, pending_placement_col, pending_placement_orientation, pending_ship_index
    global own_ships, hits_on_me, hits_on_opponent, selected_row, selected_col, orientation
    global server_connected, server_error, game_over_message
    buffer = ""
    while True:
        try:
            data = sock.recv(1024).decode()
            if not data:
                server_connected = False
                server_error = "Server disconnected"
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
                    last_server_line = line
                    print("<<", line)

                    if cmd == "START":
                        phase = "battle"
                        speak("Both players ready. Battle begins.")

                    elif cmd == "YOUR_TURN":
                        my_turn = True
                        speak("Your turn.")

                    elif cmd == "OPPONENT_TURN":
                        my_turn = False
                        speak("Opponent's turn.")

                    elif cmd == "READY_OK":
                        ready = True
                        phase = "waiting"
                        speak("Ready. Waiting for opponent.")

                    elif cmd == "WAITING_FOR_OPPONENT":
                        speak("Waiting for opponent to finish placing ships.")

                    elif cmd == "OPPONENT_READY":
                        opponent_ready = True
                        speak("Opponent is ready.")

                    elif cmd == "RESET":
                        # Server requested a new game - reset local state.
                        phase = "placement"
                        placed_count = 0
                        orientation = "H"
                        own_ships = [[False] * BOARD_SIZE for _ in range(BOARD_SIZE)]
                        hits_on_me = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
                        hits_on_opponent = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
                        selected_row = 0
                        selected_col = 0
                        ready = False
                        opponent_ready = False
                        my_turn = False
                        awaiting_place_response = False
                        pending_placement_row = None
                        pending_placement_col = None
                        pending_placement_orientation = None
                        pending_ship_index = None
                        game_over_message = ""
                        speak("Starting a new game. Place your ships.")

                    elif cmd == "PLACE_OK":
                        # Confirm the ship we placed (optimistic placement already advanced the UI)
                        ship_index = pending_ship_index if pending_ship_index is not None else placed_count
                        if pending_placement_row is not None:
                            mark_ship_placement(
                                ship_index,
                                pending_placement_row,
                                pending_placement_col,
                                pending_placement_orientation,
                            )
                        else:
                            mark_ship_placement(ship_index, selected_row, selected_col, orientation)
                        speak("Ship placed.")
                        awaiting_place_response = False
                        pending_placement_row = None
                        pending_placement_col = None
                        pending_placement_orientation = None
                        pending_ship_index = None
                        if placed_count >= len(SHIP_ORDER):
                            send_line("READY")

                    elif cmd == "ALL_SHIPS_PLACED":
                        speak("All ships placed.")

                    elif cmd == "PLACE_ERR":
                        # Rollback optimistic placement if we already advanced the UI
                        if pending_ship_index is not None and placed_count > pending_ship_index:
                            placed_count = pending_ship_index
                        awaiting_place_response = False
                        pending_ship_index = None
                        pending_placement_row = None
                        pending_placement_col = None
                        pending_placement_orientation = None
                        message = " ".join(parts[1:])
                        speak(f"Placement error: {message}")

                    elif cmd == "RESULT":
                        if parts[1] == "MISS":
                            r, c = int(parts[2]), int(parts[3])
                            hits_on_opponent[r][c] = "miss"
                            MISS_SOUND.play()
                            speak("Miss")
                        elif parts[1] == "HIT":
                            r, c = int(parts[2]), int(parts[3])
                            ship = parts[4]
                            sunk = parts[5] == "True"
                            hits_on_opponent[r][c] = "hit"
                            HIT_SOUND.play()
                            if sunk:
                                speak(f"Hit. You sunk the {ship}.")
                            else:
                                speak(f"Hit {ship}.")
                        elif parts[1] == "USED":
                            USED_SOUND.play()
                            speak("Already fired there.")
                        elif parts[1] == "WIN":
                            WIN_SOUND.play()
                            game_over_message = "You win!"
                            phase = "game_over"
                            speak(f"{game_over_message} Press R to rematch or Q to quit.")
                        elif parts[1] == "LOSE":
                            WIN_SOUND.play()
                            game_over_message = "You lose."
                            phase = "game_over"
                            speak(f"{game_over_message} Press R to rematch or Q to quit.")

                    elif cmd == "OPPONENT_FIRE":
                        r, c = int(parts[1]), int(parts[2])
                        hit_miss = parts[3]
                        if hit_miss == "HIT":
                            hits_on_me[r][c] = True
                            speak("Opponent hit your ship.")
                        else:
                            hits_on_me[r][c] = False
                            speak("Opponent missed.")

                    else:
                        # Helpful debug output if server sends something unexpected.
                        print("Unknown server message:", line)
                        speak(f"Server said: {line}")

        except Exception as e:
            server_connected = False
            server_error = str(e)
            print("Server connection lost:", e)
            break


threading.Thread(target=listen_server, daemon=True).start()

speak("Battleship. Use arrow keys to move, R to rotate during placement, and Enter or Space to confirm.")

running = True

while running:
    screen.fill((0, 0, 0))

    # Draw own grid on the left, opponent grid on the right
    def draw_grid(offset_x: int, hits, show_ships: bool):
        for x in range(BOARD_SIZE):
            for y in range(BOARD_SIZE):
                rect = pygame.Rect(offset_x + y * CELL, 10 + x * CELL, CELL, CELL)
                pygame.draw.rect(screen, (50, 50, 50), rect, 1)

                if show_ships and own_ships[x][y]:
                    pygame.draw.rect(screen, (120, 120, 120), rect)

                if hits is not None:
                    cell = hits[x][y]
                    if cell == "hit" or cell is True:
                        pygame.draw.circle(screen, (200, 0, 0), rect.center, CELL // 4)
                    elif cell == "miss" or cell is False:
                        pygame.draw.circle(screen, (255, 255, 255), rect.center, CELL // 4)

    draw_grid(20, hits_on_me, show_ships=True)
    draw_grid(420, hits_on_opponent, show_ships=False)

    # Preview current ship placement (blue translucent overlay)
    if phase == "placement" and placed_count < len(SHIP_ORDER):
        ship_name, ship_len = SHIP_ORDER[placed_count]
        preview = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        preview.fill((0, 0, 255, 100))
        for i in range(ship_len):
            r = selected_row + (i if orientation == "V" else 0)
            c = selected_col + (i if orientation == "H" else 0)
            if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
                rect = pygame.Rect(20 + c * CELL, 10 + r * CELL, CELL, CELL)
                screen.blit(preview, rect.topleft)

    # Selection highlight
    selection_x = 20 if phase == "placement" else 420
    hover_rect = pygame.Rect(selection_x + selected_col * CELL, 10 + selected_row * CELL, CELL, CELL)
    pygame.draw.rect(screen, (0, 0, 150), hover_rect, 3)

    status_text = describe_status()
    status_surface = font.render(status_text, True, (255, 255, 255))
    screen.blit(status_surface, (20, WINDOW_HEIGHT - 50))

    if last_spoken_text:
        spoken_surface = font.render(f"Spoke: {last_spoken_text}", True, (200, 200, 50))
        screen.blit(spoken_surface, (20, WINDOW_HEIGHT - 30))

    if game_over_message:
        game_over_surface = font.render(game_over_message, True, (255, 255, 255))
        screen.blit(game_over_surface, (20, WINDOW_HEIGHT - 10))

    if last_server_line:
        debug_surface = font.render(f"Server: {last_server_line}", True, (200, 200, 200))
        screen.blit(debug_surface, (20, WINDOW_HEIGHT - 70))

    if last_send_line:
        debug_surface = font.render(f"Sent: {last_send_line}", True, (200, 200, 200))
        screen.blit(debug_surface, (20, WINDOW_HEIGHT - 90))

    if last_send_error:
        debug_surface = font.render(f"Send error: {last_send_error}", True, (255, 100, 100))
        screen.blit(debug_surface, (20, WINDOW_HEIGHT - 110))

    if not server_connected:
        debug_surface = font.render(f"Server disconnected: {server_error}", True, (255, 100, 100))
        screen.blit(debug_surface, (20, WINDOW_HEIGHT - 130))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                if selected_row > 0:
                    selected_row -= 1
                    speak_interrupt(f"Selected row {selected_row + 1}, column {selected_col + 1}")
            elif event.key == pygame.K_DOWN:
                if selected_row < BOARD_SIZE - 1:
                    selected_row += 1
                    speak_interrupt(f"Selected row {selected_row + 1}, column {selected_col + 1}")
            elif event.key == pygame.K_LEFT:
                if selected_col > 0:
                    selected_col -= 1
                    speak_interrupt(f"Selected row {selected_row + 1}, column {selected_col + 1}")
            elif event.key == pygame.K_RIGHT:
                if selected_col < BOARD_SIZE - 1:
                    selected_col += 1
                    speak_interrupt(f"Selected row {selected_row + 1}, column {selected_col + 1}")
            elif event.key == pygame.K_r and phase == "placement":
                orientation = "V" if orientation == "H" else "H"
                speak(f"Orientation {orientation}")
            elif event.key == pygame.K_r and phase == "game_over":
                send_line("REMATCH")
                game_over_message = "Rematch requested. Waiting for opponent."
                speak(game_over_message)
            elif event.key == pygame.K_t:
                # Test audio output (plays a short tone)
                tone = generate_tone(800, duration=0.2)
                tone.play()
                last_spoken_text = "Audio test tone"
            elif event.key in (pygame.K_q, pygame.K_ESCAPE) and phase == "game_over":
                # Quit the client (keep the server running)
                send_line("QUIT")
                running = False
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if phase == "placement":
                    if not awaiting_place_response and placed_count < len(SHIP_ORDER):
                        ship_name, _ = SHIP_ORDER[placed_count]
                        pending_placement_row = selected_row
                        pending_placement_col = selected_col
                        pending_placement_orientation = orientation
                        pending_ship_index = placed_count
                        # Optimistically advance to next ship so the UI updates even if the server response is delayed.
                        placed_count += 1
                        # Send the ship index (0-4) to avoid spaces in the command
                        send_line(f"PLACE {pending_ship_index} {selected_row} {selected_col} {orientation}")
                        awaiting_place_response = True
                        last_place_request_time = time.time()
                        speak(f"Placing {ship_name} at row {selected_row + 1}, column {selected_col + 1} {orientation}")
                    elif awaiting_place_response and pending_ship_index is not None and time.time() - last_place_request_time > 1:
                        # Retry in case the server response was lost
                        send_line(f"PLACE {pending_ship_index} {pending_placement_row} {pending_placement_col} {pending_placement_orientation}")
                        last_place_request_time = time.time()
                        speak("Retrying placement.")
                    elif not ready and placed_count >= len(SHIP_ORDER):
                        # All ships have been placed locally; tell the server we're ready.
                        send_line("READY")
                        speak("Ready. Waiting for opponent.")
                elif phase == "game_over":
                    # Ignore fire commands after game end.
                    pass
                else:
                    if my_turn:
                        send_line(f"FIRE {selected_row} {selected_col}")
                        speak(f"Firing at row {selected_row + 1}, column {selected_col + 1}")

    # If we haven't heard back from the server after a placement request, allow retry.
    if awaiting_place_response and time.time() - last_place_request_time > 3:
        awaiting_place_response = False
        speak("No response from server. You can press space again to retry placement.")

    pygame.display.flip()

pygame.quit()
sock.close()
