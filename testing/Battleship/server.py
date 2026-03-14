import socket
import threading
import traceback
from game import Game, SHIPS

import argparse

HOST = "0.0.0.0"
PORT = 5555

game = Game()
connections = [None, None]
lock = threading.Lock()


def parse_args():
    p = argparse.ArgumentParser(description="Battleship server")
    p.add_argument("--host", default=HOST, help="Host to bind to (0.0.0.0 for all interfaces)")
    p.add_argument("--port", type=int, default=PORT, help="Port to listen on")
    return p.parse_args()


def _send(player_id: int, message: str):
    conn = connections[player_id]
    if not conn:
        return
    try:
        print(f"send({player_id}): {message}")
        conn.sendall((message + "\n").encode())
    except Exception:
        pass


def broadcast(message: str):
    for i in range(2):
        _send(i, message)


def handle_client(conn, player_id: int):
    connections[player_id] = conn
    _send(player_id, f"PLAYER {player_id}")
    _send(player_id, "INFO Place ships using: PLACE <ship> <row> <col> <H/V> then READY when done.")

    buffer = ""
    while True:
        try:
            data = conn.recv(1024).decode()
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                parts = line.split()
                cmd = parts[0].upper()
                print(f"recv({player_id}): {line}")

                if cmd == "PLACE" and len(parts) >= 5:
                    # Support either "PLACE <ship_index> <row> <col> <orient>" or
                    # "PLACE <ship name> <row> <col> <orient>" (where ship name may include spaces).
                    row = parts[-3]
                    col = parts[-2]
                    orient = parts[-1]
                    ship_id_or_name = " ".join(parts[1:-3])
                    try:
                        row_i = int(row)
                        col_i = int(col)
                    except ValueError:
                        _send(player_id, "PLACE_ERR Invalid coordinates")
                        continue

                    # Accept either a ship index (0-4) or a ship name.
                    ship_name = None
                    try:
                        ship_index = int(ship_id_or_name)
                        if 0 <= ship_index < len(SHIPS):
                            ship_name = SHIPS[ship_index][0]
                    except ValueError:
                        pass

                    if ship_name is None:
                        ship_name = ship_id_or_name

                    ok, msg = game.place_ship(player_id, ship_name, row_i, col_i, orient)
                    if ok:
                        _send(player_id, "PLACE_OK")
                        if len(game.ships[player_id]) == len(SHIPS):
                            _send(player_id, "ALL_SHIPS_PLACED")
                    else:
                        _send(player_id, f"PLACE_ERR {msg}")

                elif cmd == "READY":
                    ok, msg = game.set_ready(player_id)
                    if ok:
                        _send(player_id, "READY_OK")
                        if game.all_ready():
                            broadcast("START")
                            _send(game.turn, "YOUR_TURN")
                            _send(1 - game.turn, "OPPONENT_TURN")
                        else:
                            _send(player_id, "WAITING_FOR_OPPONENT")
                            _send(1 - player_id, "OPPONENT_READY")
                    else:
                        _send(player_id, f"READY_ERR {msg}")

                elif cmd == "FIRE" and len(parts) == 3:
                    try:
                        row_i = int(parts[1])
                        col_i = int(parts[2])
                    except ValueError:
                        _send(player_id, "RESULT ERROR Invalid coordinates")
                        continue

                    result = game.process_fire(player_id, row_i, col_i)
                    status = result.get("status")

                    if status == "WAIT":
                        _send(player_id, "RESULT WAIT")
                        continue

                    if status == "NOT_READY":
                        _send(player_id, "RESULT NOT_READY")
                        continue

                    if status == "USED":
                        _send(player_id, "RESULT USED")
                        continue

                    if status == "MISS":
                        _send(player_id, f"RESULT MISS {row_i} {col_i}")
                        _send(1 - player_id, f"OPPONENT_FIRE {row_i} {col_i} MISS")
                        _send(1 - player_id, "YOUR_TURN")
                        _send(player_id, "OPPONENT_TURN")
                        continue

                    if status == "HIT":
                        ship = result.get("ship", "Ship")
                        sunk = result.get("sunk", False)
                        win = result.get("win", False)
                        _send(player_id, f"RESULT HIT {row_i} {col_i} {ship} {sunk}")
                        _send(1 - player_id, f"OPPONENT_FIRE {row_i} {col_i} HIT {ship} {sunk}")
                        if win:
                            _send(player_id, "WIN")
                            _send(1 - player_id, "LOSE")
                        else:
                            _send(1 - player_id, "YOUR_TURN")
                            _send(player_id, "OPPONENT_TURN")
                        continue

                else:
                    _send(player_id, "ERROR Unknown command")

        except Exception as e:
            print(f"Exception in client handler ({player_id}):", e)
            traceback.print_exc()
            try:
                _send(player_id, f"ERROR {e}")
            except Exception:
                pass
            break

    conn.close()
    connections[player_id] = None


def start(host: str, port: int):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((host, port))
    except OSError as e:
        raise SystemExit(
            f"Failed to bind {host}:{port} - {e}.\n"
            "Ensure no other server is running on that port, or use --port to pick a different one."
        )

    server.listen(2)
    print(f"Server running on {host}:{port} (0.0.0.0 binds everywhere)")

    for player_id in range(2):
        conn, addr = server.accept()
        print("Player connected:", addr)
        threading.Thread(target=handle_client, args=(conn, player_id)).start()


if __name__ == "__main__":
    args = parse_args()
    start(args.host, args.port)
