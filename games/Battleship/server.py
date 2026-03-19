"""
Battleship server — EchoFleet.
Auto-shuts down once both players disconnect (no orphan processes).
"""
from __future__ import annotations

import argparse
import os
import socket
import threading
import traceback

from game import Game, SHIPS

# network settings
HOST = "0.0.0.0"
PORT = 5555

# game state
game = Game()
connections: list[socket.socket | None] = [None, None]
lock = threading.Lock()

game_over = False                   # set True after WIN/LOSE broadcast
rematch_requests: set[int] = set()  # tracks which players requested rematch

# track connected players so we know when to shut down
connected_count = 0
connected_lock = threading.Lock()


def parse_args() -> argparse.Namespace:
    """Parses CLI args for host and port."""
    p = argparse.ArgumentParser(description="EchoFleet Battleship server")
    p.add_argument("--host", default=HOST)
    p.add_argument("--port", type=int, default=PORT)
    return p.parse_args()


def _send(player_id: int, message: str) -> None:
    """Sends a newline-terminated msg to a specific player."""
    conn = connections[player_id]
    if not conn:
        return
    try:
        conn.sendall((message + "\n").encode())
    except Exception:
        pass


def broadcast(message: str) -> None:
    """Sends a msg to both players."""
    for i in range(2):
        _send(i, message)


def handle_client(conn: socket.socket, player_id: int) -> None:
    """
    Handles all incoming msgs from a single client in its own thread.
    Processes placement, ready, fire, rematch, and quit cmds.

    Params:
    conn (socket.socket) - client connection,
    player_id (int) - 0 or 1
    """
    global game, game_over, rematch_requests, connected_count

    connections[player_id] = conn
    _send(player_id, f"PLAYER {player_id}")
    _send(player_id, "INFO Place ships: PLACE <ship_index> <row> <col> <H/V> then READY.")

    buffer = ""
    try:
        while True:
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

                if cmd == "PLACE" and len(parts) >= 5:
                    row_str = parts[-3]
                    col_str = parts[-2]
                    orient_str = parts[-1]
                    ship_token = " ".join(parts[1:-3])
                    try:
                        row_i = int(row_str)
                        col_i = int(col_str)
                    except ValueError:
                        _send(player_id, "PLACE_ERR Invalid coordinates")
                        continue

                    # resolve ship name from index or raw token
                    ship_name: str | None = None
                    try:
                        idx = int(ship_token)
                        if 0 <= idx < len(SHIPS):
                            ship_name = SHIPS[idx][0]
                    except ValueError:
                        pass
                    if ship_name is None:
                        ship_name = ship_token

                    ok, msg = game.place_ship(player_id, ship_name, row_i, col_i, orient_str)
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

                    if status in ("WAIT", "NOT_READY"):
                        _send(player_id, f"RESULT {status}")
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
                            game_over = True
                            rematch_requests.clear()
                            _send(player_id, "RESULT WIN")
                            _send(1 - player_id, "RESULT LOSE")
                        else:
                            _send(1 - player_id, "YOUR_TURN")
                            _send(player_id, "OPPONENT_TURN")
                        continue

                elif cmd == "REMATCH":
                    if not game_over:
                        _send(player_id, "ERROR Not in game-over state")
                    else:
                        rematch_requests.add(player_id)
                        _send(player_id, "REMATCH_OK")
                        if len(rematch_requests) == 2:
                            # both players agreed — reset all state + start over
                            game = Game()
                            game_over = False
                            rematch_requests.clear()
                            broadcast("RESET")

                elif cmd == "QUIT":
                    break

                else:
                    _send(player_id, "ERROR Unknown command")

    except Exception as exc:
        print(f"[server] error in handler for player {player_id}: {exc}")
        traceback.print_exc()

    finally:
        conn.close()
        connections[player_id] = None
        print(f"[server] player {player_id} disconnected.")

        with connected_lock:
            connected_count -= 1
            remaining = connected_count

        if remaining == 0:
            print("[server] both players disconnected — shutting down.")
            os._exit(0)


def start(host: str, port: int) -> None:
    """
    Binds the server socket, accepts both players, and starts handler threads.

    Params:
    host (str) - address to bind to,
    port (int) - port to listen on
    """
    global connected_count

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((host, port))
    except OSError as e:
        raise SystemExit(f"Failed to bind {host}:{port} — {e}")

    server.listen(2)
    print(f"[server] listening on {host}:{port}")

    for player_id in range(2):
        conn, addr = server.accept()
        print(f"[server] player {player_id} connected from {addr}")
        with connected_lock:
            connected_count += 1
        threading.Thread(target=handle_client, args=(conn, player_id), daemon=True).start()

    # keep main thread alive while daemon threads handle clients
    threading.Event().wait()


if __name__ == "__main__":
    args = parse_args()
    start(args.host, args.port)