import socket
import threading
from game import Game

HOST = "0.0.0.0"
PORT = 5555

game = Game()


def handle_client(conn, player_id):
    conn.sendall(str(player_id).encode())

    while True:
        try:
            data = conn.recv(1024).decode()
            if not data:
                break

            row, col = map(int, data.split(","))
            result = game.process_move(player_id, row, col)
            conn.sendall(result.encode())

        except:
            break

    conn.close()


def start():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(2)
    print("Server running on port", PORT)

    for player_id in range(2):
        conn, addr = server.accept()
        print("Player connected:", addr)
        threading.Thread(target=handle_client, args=(conn, player_id)).start()


if __name__ == "__main__":
    start()