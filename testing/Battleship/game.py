import random
from typing import Dict, List, Optional, Set, Tuple

BOARD_SIZE = 8
SHIPS = [
    ("Aircraft Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]

Coordinate = Tuple[int, int]


class Ship:
    def __init__(self, name: str, length: int, coords: List[Coordinate]):
        self.name = name
        self.length = length
        self.coords: Set[Coordinate] = set(coords)
        self.hits: Set[Coordinate] = set()

    def hit(self, coord: Coordinate) -> bool:
        if coord in self.coords:
            self.hits.add(coord)
            return True
        return False

    def is_sunk(self) -> bool:
        return self.hits == self.coords


class Game:
    def __init__(self):
        self.ships: List[List[Ship]] = [[], []]
        self.shots: List[Set[Coordinate]] = [set(), set()]
        self.ready: List[bool] = [False, False]
        self.turn: int = 0

    def _ship_coords(self, row: int, col: int, length: int, orientation: str) -> Optional[List[Coordinate]]:
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

        occupied: Set[Coordinate] = set()
        for ship in self.ships[player]:
            occupied.update(ship.coords)

        if any(c in occupied for c in coords):
            return False, "Ship overlaps another ship"

        self.ships[player].append(Ship(matching[0][0], length, coords))
        return True, "OK"

    def set_ready(self, player: int) -> Tuple[bool, str]:
        if self.ready[player]:
            return False, "Already ready"
        if len(self.ships[player]) != len(SHIPS):
            return False, "Must place all ships before ready"
        self.ready[player] = True
        return True, "READY"

    def all_ready(self) -> bool:
        return self.ready[0] and self.ready[1]

    def is_player_turn(self, player: int) -> bool:
        return self.turn == player

    def process_fire(self, player: int, row: int, col: int) -> Dict:
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
        for ship in self.ships[player]:
            if coord in ship.coords:
                return ship.name
        return None
