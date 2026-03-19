"""
Game logic for Battleship — EchoFleet.
Handles ship placement, turn management, and fire processing.
"""

import random
from typing import Dict, List, Optional, Set, Tuple

# Board size and ship definitions
BOARD_SIZE = 8
SHIPS = [
    ("Aircraft Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]

Coordinate = Tuple[int, int]  # (row, col) board position


class Ship:
    def __init__(self, name: str, length: int, coords: List[Coordinate]):
        """
        Represents a single ship on the board.

        Params:
        name (str) - ship name,
        length (int) - number of cells,
        coords (List[Coordinate]) - cells the ship occupies
        """
        self.name = name
        self.length = length
        self.coords: Set[Coordinate] = set(coords)
        self.hits: Set[Coordinate] = set()

    def hit(self, coord: Coordinate) -> bool:
        """
        Registers a hit if the coordinate matches a ship cell.

        Returns:
        bool - True if it was a hit
        """
        if coord in self.coords:
            self.hits.add(coord)
            return True
        return False

    def is_sunk(self) -> bool:
        """Returns True if all cells have been hit."""
        return self.hits == self.coords


class Game:
    def __init__(self):
        """Initializes an empty game with two players, no ships placed."""
        self.ships: List[List[Ship]] = [[], []]   # ships[0] / ships[1] for each player
        self.shots: List[Set[Coordinate]] = [set(), set()]  # cells already fired at
        self.ready: List[bool] = [False, False]  # whether each player has confirmed all ships
        self.turn: int = 0  # index of the player whose turn it is (0 goes first)

    def _ship_coords(self, row: int, col: int, length: int, orientation: str) -> Optional[List[Coordinate]]:
        """
        Calculates the list of coordinates a ship would occupy.

        Returns:
        List[Coordinate] or None if placement is out of bounds or orientation is invalid
        """
        if orientation not in ("H", "V"):
            return None
        if orientation == "H":
            if col + length > BOARD_SIZE:
                return None
            return [(row, col + i) for i in range(length)]
        else:
            if row + length > BOARD_SIZE:
                return None
            return [(row + i, col) for i in range(length)]

    def place_ship(self, player: int, ship_name: str, row: int, col: int, orientation: str) -> Tuple[bool, str]:
        """
        Places a ship for the given player if the position is valid.

        Returns:
        Tuple of (success (bool), message (str))
        """
        if self.ready[player]:
            return False, "Already ready"

        matching = [s for s in SHIPS if s[0].lower() == ship_name.lower()]
        if not matching:
            return False, f"Unknown ship: {ship_name}"

        length = matching[0][1]
        orientation = orientation.upper()

        coords = self._ship_coords(row, col, length, orientation)
        if coords is None:
            return False, "Ship would be out of bounds or invalid orientation"

        # Check for overlap with already placed ships
        occupied: Set[Coordinate] = set()
        for ship in self.ships[player]:
            occupied.update(ship.coords)

        if any(c in occupied for c in coords):
            return False, "Ship overlaps another ship"

        self.ships[player].append(Ship(matching[0][0], length, coords))
        return True, "OK"

    def set_ready(self, player: int) -> Tuple[bool, str]:
        """
        Marks a player as ready if all ships have been placed.

        Returns:
        Tuple of (success (bool), message (str))
        """
        if self.ready[player]:
            return False, "Already ready"
        if len(self.ships[player]) != len(SHIPS):
            return False, "Must place all ships before ready"
        self.ready[player] = True
        return True, "READY"

    def all_ready(self) -> bool:
        """Returns True if both players are ready."""
        return self.ready[0] and self.ready[1]

    def is_player_turn(self, player: int) -> bool:
        """Returns True if it is the given player's turn."""
        return self.turn == player

    def process_fire(self, player: int, row: int, col: int) -> Dict:
        """
        Processes a fire action from a player.

        Returns:
        Dict with 'status' key. Possible statuses:
          NOT_READY - game hasn't started yet
          WAIT      - it's not this player's turn
          USED      - cell was already fired at
          MISS      - shot missed all ships
          HIT       - shot hit a ship; also contains 'ship' (str), 'sunk' (bool), 'win' (bool)
        """
        if not self.all_ready():
            return {"status": "NOT_READY"}

        if player != self.turn:
            return {"status": "WAIT"}

        if (row, col) in self.shots[player]:
            return {"status": "USED"}

        self.shots[player].add((row, col))
        opponent = 1 - player

        for ship in self.ships[opponent]:
            if ship.hit((row, col)):
                sunk = ship.is_sunk()
                win = all(s.is_sunk() for s in self.ships[opponent])
                if not win:
                    self.turn = opponent
                return {"status": "HIT", "ship": ship.name, "sunk": sunk, "win": win}

        self.turn = opponent
        return {"status": "MISS"}

    def ship_at(self, player: int, coord: Coordinate) -> Optional[str]:
        """
        Returns the name of the ship at a given coordinate, or None if empty.

        Params:
        player (int) - player index,
        coord (Coordinate) - cell to check
        """
        for ship in self.ships[player]:
            if coord in ship.coords:
                return ship.name
        return None