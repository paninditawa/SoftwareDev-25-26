import pygame
import socket
import threading
import numpy as np

HOST = "127.0.0.1"
PORT = 5555
BOARD_SIZE = 8
WINDOW_SIZE = 600
CELL = WINDOW_SIZE // BOARD_SIZE

pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=2)
screen = pygame.display.set_mode((WINDOW_SIZE, WINDOW_SIZE))
pygame.display.set_caption("EchoFleet")
font = pygame.font.SysFont(None, 36)

def generate_tone(freq, duration=0.3, volume=0.5):
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = np.sin(freq * t * 2 * np.pi)  # values between -1 and 1
    audio = (tone * 32767 * volume).astype(np.int16)  # convert to int16
    stereo_audio = np.column_stack((audio, audio))  # 2D array for stereo
    return pygame.sndarray.make_sound(stereo_audio)

HIT_SOUND = generate_tone(1000)
CLOSE_SOUND = generate_tone(800)
MEDIUM_SOUND = generate_tone(500)
FAR_SOUND = generate_tone(200)
USED_SOUND = generate_tone(150, 0.15)
WIN_SOUND = generate_tone(1200, 0.6)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((HOST, PORT))
player_id = int(sock.recv(1024).decode())
print(f"Connected as Player {player_id}")

result = ""
my_turn = (player_id == 0)
used_squares = set()
lock = threading.Lock()

def listen_server():
    global result, my_turn
    while True:
        try:
            message = sock.recv(1024).decode()
            if not message:
                break
            with lock:
                result = message
                if message in ["HIT", "CLOSE", "MEDIUM", "FAR", "WIN", "USED"]:
                    my_turn = True  # enable next turn after server reply
        except Exception as e:
            print("Server connection lost:", e)
            break

threading.Thread(target=listen_server, daemon=True).start()

running = True
while running:
    screen.fill((0, 0, 0))

    # Draw grid
    for x in range(BOARD_SIZE):
        for y in range(BOARD_SIZE):
            rect = pygame.Rect(y * CELL, x * CELL, CELL, CELL)
            pygame.draw.rect(screen, (50, 50, 50), rect, 1)

    mouse_pos = pygame.mouse.get_pos()
    row = mouse_pos[1] // CELL
    col = mouse_pos[0] // CELL
    hover_rect = pygame.Rect(col * CELL, row * CELL, CELL, CELL)
    pygame.draw.rect(screen, (0, 0, 150), hover_rect, 3)

    with lock:
        turn_text = "Your Turn" if my_turn else "Opponent Turn"
    text_surface = font.render(turn_text, True, (255, 255, 255))
    screen.blit(text_surface, (10, 10))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.MOUSEBUTTONDOWN:
            with lock:
                if my_turn:
                    if (row, col) in used_squares:
                        USED_SOUND.play()
                    else:
                        try:
                            sock.sendall(f"{row},{col}".encode())
                            used_squares.add((row, col))
                            my_turn = False
                        except Exception as e:
                            print("Failed to send move:", e)

    with lock:
        if result:
            if result == "HIT":
                HIT_SOUND.play()
            elif result == "CLOSE":
                CLOSE_SOUND.play()
            elif result == "MEDIUM":
                MEDIUM_SOUND.play()
            elif result == "FAR":
                FAR_SOUND.play()
            elif result == "USED":
                USED_SOUND.play()
            elif result == "WIN":
                WIN_SOUND.play()
            result = ""

    pygame.display.flip()

pygame.quit()
sock.close()