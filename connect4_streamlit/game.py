import pygame
import numpy as np
import sys
import win32com.client

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
# WINDOWS SAPI TTS (bulletproof)
# -----------------------------
speaker = win32com.client.Dispatch("SAPI.SpVoice")

def speak(text):
    speaker.Speak(text)

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
        cell = board[r][col]
        if cell == 0:
            empty_count += 1
        else:
            flush()
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
    screen.fill(BLACK)

    # Selector arrow
    x = selector_col * SQUARESIZE + SQUARESIZE//2
    pygame.draw.polygon(screen, WHITE, [
        (x, 20),
        (x-20, 60),
        (x+20, 60)
    ])

    # Board background
    for c in range(COLS):
        for r in range(ROWS):
            pygame.draw.rect(screen, BLUE,
                             (c*SQUARESIZE, (r+1)*SQUARESIZE, SQUARESIZE, SQUARESIZE))
            pygame.draw.circle(screen, BLACK,
                               (c*SQUARESIZE + SQUARESIZE//2, (r+1)*SQUARESIZE + SQUARESIZE//2),
                               RADIUS)

    # Pieces
    for c in range(COLS):
        for r in range(ROWS):
            piece = board[r][c]
            color = BLACK
            if piece == 1:
                color = RED
            elif piece == 2:
                color = YELLOW

            pygame.draw.circle(screen, color,
                               (c*SQUARESIZE + SQUARESIZE//2, HEIGHT - (r*SQUARESIZE + SQUARESIZE//2)),
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

    # Tutorial
    speak(
        "Welcome to Connect Four. "
        "Use left and right arrow keys to move the selector. "
        "Press spacebar to drop your piece. "
        "Press R to restart the game at any time."
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
                if game_over and event.key == pygame.K_0:
                    speak("Goodbye.")
                    pygame.quit()
                    sys.exit()

                # Restart
                if event.key == pygame.K_r:
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
                            if winning_move(board, turn):
                                speak(f"Player {turn} wins in column {selector_col+1}.")
                                game_over = True
                                speak("Press zero to exit the game.")
                            else:
                                speak(f"Player {turn} dropped a piece in column {selector_col+1}.")
                                turn = 2 if turn == 1 else 1

                            draw_board(screen, board, selector_col)
                        else:
                            speak("Column full. Choose another column.")

        pygame.time.wait(20)

if __name__ == "__main__":
    main()