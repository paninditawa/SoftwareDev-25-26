import pygame
import numpy as np
import sys
import time
from pathlib import Path

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
except ImportError:
    def _tts_speak(text: str):
        print(text)

# -----------------------------
# CONFIG
# -----------------------------
ROWS = 6
COLS = 7
SQUARESIZE = 100
RADIUS = int(SQUARESIZE/2 - 5)
WIDTH = COLS * SQUARESIZE
HEIGHT = (ROWS + 1) * SQUARESIZE
SIZE = (WIDTH, HEIGHT)

BLUE = (0, 0, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
WHITE = (255, 255, 255)

# -----------------------------
# TTS (cross-platform)
# -----------------------------
# Uses the shared `tts` helper (Windows uses SAPI, macOS uses `say`, other platforms use pyttsx3).
# If TTS is unavailable, this will print text instead.

def speak_block(text):
    _tts_speak(text)


def speak(text):
    _tts_speak(text)

# -----------------------------
# GAME LOGIC
# -----------------------------
def create_board():
    return np.zeros((ROWS, COLS), dtype=int)

def drop_piece(board, col, piece):
    for r in range(ROWS-1, -1, -1):
        if board[r][col] == 0:
            board[r][col] = piece
            return True
    return False

def winning_move(board, piece):
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
            pieces.append("Red" if cell == 1 else "Yellow")
    
    flush()

    return ", ".join(pieces) if pieces else "6 empty"

def announce_column(board, col):
    msg = f"Column {col+1} selected. Contents from bottom to top: {describe_column(board, col)}."
    speak(msg)

# -----------------------------
# DRAWING
# -----------------------------
def draw_board(screen, board, selector_col):
    screen.fill(WHITE)

    # Selector arrow
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
            pygame.draw.circle(screen, WHITE,
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

    pygame.display.update()

# -----------------------------
# MAIN GAME LOOP
# -----------------------------
def main():
    pygame.init()
    screen = pygame.display.set_mode(SIZE)
    pygame.display.set_caption("Accessible Connect 4")

    board = create_board()
    turn = 1
    selector_col = 3
    game_over = False

    time.sleep(2) # brief pause before tutorial starts

    # Tutorial
    speak_block(
        "Welcome to Connect Four. "
        "Connect 4 is a two‑player game played on a grid with seven columns. "
        "On your turn, you choose a column number, and your piece drops to the lowest open space in that column. "
        "Your goal is to make a line of four of your pieces in a row: either 4 across, 4 up and down, or 4 diagonally. "
        "I’ll tell you where each piece lands so you can track the board. "
        "Take turns placing pieces, and the first player to connect four wins. "
        "Use left and right arrow keys to move the selector. "
        "Press spacebar to drop your piece. "
        "Press the up arrow key to restart the game at any time. After a game, if you want to exit the game, press the down arrow key. "
        "Let's play! "
    )

    draw_board(screen, board, selector_col)
    announce_column(board, selector_col)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:

                # Quit after win
                if event.key == pygame.K_DOWN:
                    speak("Goodbye.")
                    pygame.quit()
                    sys.exit()

                # Restart
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
                        selector_col = (selector_col - 1) % COLS
                        draw_board(screen, board, selector_col)
                        announce_column(board, selector_col)
                        
                    elif event.key == pygame.K_RIGHT:
                        selector_col = (selector_col + 1) % COLS
                        draw_board(screen, board, selector_col)
                        announce_column(board, selector_col)
                        
                    elif event.key == pygame.K_SPACE:
                        if drop_piece(board, selector_col, turn):

                            draw_board(screen, board, selector_col)
                            speak(f"Player {turn} dropped a piece in column {selector_col+1}.")

                            if winning_move(board, turn):
                                speak_block(f"Player {turn} wins in column {selector_col+1}.")
                                game_over = True
                                speak_block("Press the up arrow key to restart game. Press the down arrow key to exit the game.")
                            else:
                                turn = 2 if turn == 1 else 1

                        else:
                            speak("Column full. Choose another column.")

        pygame.time.wait(20)

if __name__ == "__main__":
    main()