"""
Accessible Connect Four game for the HelloWorld GameSpace.

This is a two-player turn-based game on a 7-column, 6-row grid.
Players use Left/Right arrows to move a column selector and Spacebar
to drop their piece.  Every action is announced via text-to-speech so
the game is fully playable without looking at the screen.

Controls
--------
Left / Right — move the column selector
Space        — drop your piece into the selected column
J            — hear the full instructions again
Up Arrow     — restart the game
Down Arrow   — quit after the game is over
Escape       — quit at any time
"""
import pygame
import numpy as np
import sys
import threading
from pathlib import Path

from game_theme import (
    GAME_ACCENT,
    GAME_BG,
    GAME_BORDER,
    GAME_FOCUS,
    GAME_FONT_FAMILY,
    GAME_GLOW,
    GAME_PANEL,
    GAME_PANEL_ALT,
    GAME_TEXT,
)

# Ensure the project root containing `tts.py` is on sys.path.
_this_file = Path(__file__).resolve()
for _parent in _this_file.parents:
    if (_parent / "tts.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

# Cross-platform TTS helper
try:
    from tts import speak as _tts_speak
    from tts import speak_blocking as _tts_speak_blocking
    from tts import speak_interrupt as _tts_speak_interrupt
except ImportError:
    def _tts_speak(text: str):
        print(text)

    def _tts_speak_blocking(text: str):
        print(text)

    def _tts_speak_interrupt(text: str):
        print(text)

# -----------------------------
# CONFIG
# -----------------------------
ROWS = 6   # number of rows in the grid
COLS = 7   # number of columns in the grid
SQUARESIZE = 100                   # pixel size of each cell before scaling
RADIUS = int(SQUARESIZE/2 - 5)     # radius of each piece circle
WIDTH = COLS * SQUARESIZE
HEIGHT = (ROWS + 1) * SQUARESIZE  # extra row at the top for the selector arrow
SIZE = (WIDTH, HEIGHT)

# Board and UI colors
BLUE = GAME_BORDER
BLACK = GAME_TEXT
RED = GAME_ACCENT      # Player 1 piece color
YELLOW = GAME_FOCUS    # Player 2 piece color
WHITE = GAME_PANEL
BOARD_HOLE = GAME_PANEL_ALT
PIECE_TEXT = GAME_PANEL
STARTUP_PROMPT_DELAY_MS = 3500
FULL_TUTORIAL_TEXT = (
    "Welcome to Connect Four. "
    "Connect 4 is a two-player game played on a grid with seven columns. "
    "On your turn, you choose a column number, and your piece drops to the lowest open space in that column. "
    "Your goal is to make a line of four of your pieces in a row: either 4 across, 4 up and down, or 4 diagonally. "
    "I'll tell you where each piece lands so you can track the board. "
    "Take turns placing pieces, and the first player to connect four wins. "
    "Use left and right arrow keys to move the selector. "
    "Press spacebar to drop your piece. "
    "Press J at any time to hear these instructions again. "
    "Press the up arrow key to restart the game at any time. After a game, if you want to exit the game, press the down arrow key. "
    "Let's play!"
)
SKIP_PROMPT_TEXT = (
    "Welcome to Connect Four. "
    "Press Enter now to skip the full instructions and start playing. "
    "Otherwise, the instructions will begin in a moment. "
    "After the game starts, press J any time to hear the instructions again."
)


def _recommended_window_size(base_w: int, base_h: int) -> tuple[int, int]:
    screen_w = base_w
    screen_h = base_h

    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                screen_w = rect.right - rect.left
                screen_h = rect.bottom - rect.top
        except Exception:
            pass
    else:
        info = pygame.display.Info()
        if info.current_w > 0:
            screen_w = info.current_w
        if info.current_h > 0:
            screen_h = info.current_h

    width = max(base_w, min(screen_w - 40, int(screen_w * 0.96)))
    height = max(base_h, min(screen_h - 60, int(screen_h * 0.94)))
    return width, height

# -----------------------------
# TTS (cross-platform)
# -----------------------------
# Uses the shared `tts` helper (Windows uses SAPI, macOS uses `say`, other platforms use pyttsx3).
# If TTS is unavailable, this will print text instead.

def speak_block(text):
    _tts_speak_blocking(text)


def speak(text):
    _tts_speak(text)


def speak_interrupt(text):
    _tts_speak_interrupt(text)


def tts_busy() -> bool:
    """Return True while TTS audio is currently playing."""
    try:
        return pygame.mixer.music.get_busy()
    except Exception:
        return False


def start_tutorial(screen, board, selector_col):
    draw_board(screen, board, selector_col)
    speak(SKIP_PROMPT_TEXT)
    return pygame.time.get_ticks() + STARTUP_PROMPT_DELAY_MS

# -----------------------------
# SCOREBOARD
# -----------------------------

def _report_win(game_name: str) -> None:
    # Read user identity from environment variables set by the launcher.
    import os, threading
    user_id  = os.environ.get("HW_USER_ID",  "")
    username = os.environ.get("HW_USERNAME", "")
    if not user_id:
        return
    def _write():
        try:
            _repo_root = Path(__file__).resolve()
            while _repo_root != _repo_root.parent:
                if (_repo_root / "tts.py").exists():
                    break
                _repo_root = _repo_root.parent
            sys.path.insert(0, str(_repo_root))
            from launcher.services.leaderboard import Scoreboard
            sb = Scoreboard.from_workspace(_repo_root)
            sb.record_win(user_id, username, game_name)
        except Exception as exc:
            print(f"scoreboard write failed: {exc}")
    threading.Thread(target=_write, daemon=True).start()

# -----------------------------
# GAME LOGIC
# -----------------------------
def create_board():
    # Return a 6x7 numpy array filled with zeros (0 = empty, 1 = P1, 2 = P2).
    return np.zeros((ROWS, COLS), dtype=int)

def drop_piece(board, col, piece):
    # Find the lowest empty row in `col` and place `piece` there.
    # Returns True if successful, False if the column is full.
    for r in range(ROWS-1, -1, -1):
        if board[r][col] == 0:
            board[r][col] = piece
            return True
    return False

def winning_move(board, piece):
    # Check all four directions for a line of four matching pieces.
    # Horizontal
    for r in range(ROWS):
        for c in range(COLS-3):
            if all(board[r][c+i] == piece for i in range(4)):
                return True
    # Vertical
    for c in range(COLS):
        for r in range(ROWS-3):
            if all(board[r+i][c] == piece for i in range(4)):
                return True
    # Positive diagonal
    for r in range(ROWS-3):
        for c in range(COLS-3):
            if all(board[r+i][c+i] == piece for i in range(4)):
                return True
    # Negative diagonal
    for r in range(3, ROWS):
        for c in range(COLS-3):
            if all(board[r-i][c+i] == piece for i in range(4)):
                return True
    return False

def describe_column(board, col):
    # Build a text description of what is in a column, from bottom to top.
    # Used by the screen-reader announcement when the selector moves.
    pieces = []
    empty_count = 0

    def flush():
        nonlocal empty_count
        if empty_count > 0:
            pieces.append(f"{empty_count} empty")
            empty_count = 0

    for r in range(ROWS):
        cell = board[5-r][col]
        if cell == 0:
            empty_count += 1
        else:
            pieces.append("Player 1" if cell == 1 else "Player 2")
    
    flush()

    return ", ".join(pieces) if pieces else "6 empty"

def announce_column(board, col):
    # Speak the current selector column number and its contents.
    msg = f"Column {col+1} selected. Contents from bottom to top: {describe_column(board, col)}."
    speak(msg)

# -----------------------------
# DRAWING
# -----------------------------
def draw_board(screen, board, selector_col):
    # Redraw the entire board: background, selector arrow, grid, and pieces.
    screen.fill(GAME_BG)
    piece_font = pygame.font.SysFont(GAME_FONT_FAMILY, 40, bold=True)

    # Triangle arrow above the selected column
    x = selector_col * SQUARESIZE + SQUARESIZE//2
    pygame.draw.polygon(screen, BLACK, [
        (x, 60),
        (x-20, 20),
        (x+20, 20)
    ])

    # Board background
    for c in range(COLS):
        for r in range(ROWS):
            pygame.draw.rect(screen, BLUE,
                             (c*SQUARESIZE, (r+1)*SQUARESIZE, SQUARESIZE, SQUARESIZE))
            pygame.draw.circle(screen, BOARD_HOLE,
                               (c*SQUARESIZE + SQUARESIZE//2, (r+1)*SQUARESIZE + SQUARESIZE//2),
                               RADIUS)

    # Pieces
    for c in range(COLS):
        for r in range(ROWS):
            piece = board[r][c]
            color = WHITE
            if piece == 1:
                color = RED
            elif piece == 2:
                color = YELLOW

            pygame.draw.circle(screen, color,
                               (c*SQUARESIZE + SQUARESIZE//2, ((r+1)*SQUARESIZE + SQUARESIZE//2)),
                               RADIUS)
            if piece in (1, 2):
                pygame.draw.circle(
                    screen,
                    BLACK,
                    (c*SQUARESIZE + SQUARESIZE//2, ((r+1)*SQUARESIZE + SQUARESIZE//2)),
                    RADIUS,
                    3,
                )
                marker = piece_font.render("1" if piece == 1 else "2", True, PIECE_TEXT)
                screen.blit(
                    marker,
                    (
                        c*SQUARESIZE + SQUARESIZE//2 - marker.get_width()//2,
                        (r+1)*SQUARESIZE + SQUARESIZE//2 - marker.get_height()//2,
                    ),
                )

    pygame.display.update()

# -----------------------------
# MAIN GAME LOOP
# -----------------------------
def main():
    pygame.init()
    # Scale the window to fit the display while keeping aspect ratio.
    global SQUARESIZE, RADIUS, WIDTH, HEIGHT, SIZE
    target_w, target_h = _recommended_window_size(WIDTH, HEIGHT)
    square_w = max(80, target_w // COLS)
    square_h = max(80, target_h // (ROWS + 1))
    SQUARESIZE = min(square_w, square_h)
    RADIUS = int(SQUARESIZE / 2 - 5)
    WIDTH = COLS * SQUARESIZE
    HEIGHT = (ROWS + 1) * SQUARESIZE
    SIZE = (WIDTH, HEIGHT)

    screen = pygame.display.set_mode(SIZE)
    pygame.display.set_caption("Accessible Connect 4")

    board = create_board()
    turn = 1          # 1 = Player 1's turn, 2 = Player 2's turn
    selector_col = 3  # start the selector in the middle column
    game_over = False
    tutorial_done = False
    tutorial_started = False
    tutorial_finished = threading.Event()
    tutorial_deadline = start_tutorial(screen, board, selector_col)

    def _run_startup_tutorial() -> None:
        speak_block(FULL_TUTORIAL_TEXT)
        tutorial_finished.set()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                speak("Exiting Connect 4.")
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if not tutorial_done:
                    if event.key == pygame.K_RETURN:
                        tutorial_done = True
                        speak_interrupt("Skipping full instructions. Let's play.")
                        announce_column(board, selector_col)
                    continue

                # Quit is allowed only after the game ends (Down arrow).
                if event.key == pygame.K_DOWN:
                    if game_over:
                        speak("Goodbye.")
                        pygame.quit()
                        sys.exit()
                    speak("Down arrow exits after a game ends. Press escape to quit now.")
                    continue

                if event.key == pygame.K_j:
                    speak_block(FULL_TUTORIAL_TEXT)
                    draw_board(screen, board, selector_col)
                    announce_column(board, selector_col)
                    continue

                # Up arrow restarts the game at any time.
                if event.key == pygame.K_UP:
                    board = create_board()
                    turn = 1
                    selector_col = 3
                    game_over = False
                    speak("Game restarted.")
                    draw_board(screen, board, selector_col)
                    announce_column(board, selector_col)

                if not game_over:
                    if event.key == pygame.K_LEFT:
                        # Move the selector one column to the left (wraps around).
                        selector_col = (selector_col - 1) % COLS
                        draw_board(screen, board, selector_col)
                        announce_column(board, selector_col)

                    elif event.key == pygame.K_RIGHT:
                        # Move the selector one column to the right (wraps around).
                        selector_col = (selector_col + 1) % COLS
                        draw_board(screen, board, selector_col)
                        announce_column(board, selector_col)

                    elif event.key == pygame.K_SPACE:
                        # Drop the current player's piece into the selected column.
                        if drop_piece(board, selector_col, turn):

                            draw_board(screen, board, selector_col)
                            speak(f"Player {turn} dropped a piece in column {selector_col+1}.")

                            if winning_move(board, turn):
                                # Announce winner first, then post-game instructions in one call
                                # so they can never overlap or play out of order.
                                speak_block(
                                    f"Player {turn} wins in column {selector_col+1}! "
                                    "Press the up arrow key to restart, or the down arrow key to exit."
                                )
                                game_over = True
                                _report_win("connect4")  # record the win on the leaderboard
                            else:
                                turn = 2 if turn == 1 else 1  # swap turns

                        else:
                            speak("Column full. Choose another column.")

        if (
            not tutorial_started
            and not tutorial_done
            and pygame.time.get_ticks() >= tutorial_deadline
            and not tts_busy()
        ):
            tutorial_started = True
            threading.Thread(target=_run_startup_tutorial, daemon=True).start()

        if tutorial_started and not tutorial_done and tutorial_finished.is_set():
            tutorial_done = True
            announce_column(board, selector_col)

        pygame.time.wait(20)

if __name__ == "__main__":
    main()