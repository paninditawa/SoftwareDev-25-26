import random

BOARD_SIZE = 8
SHIP_LENGTH = 3
NUM_SHIPS = 3


class Game:
    def __init__(self):
        self.ships = [self.place_ships(), self.place_ships()]
        self.shots = [set(), set()]
        self.turn = 0

    def place_ships(self):
        ships = []
        while len(ships) < NUM_SHIPS * SHIP_LENGTH:
            row = random.randint(0, BOARD_SIZE - 1)
            col = random.randint(0, BOARD_SIZE - SHIP_LENGTH)
            coords = [(row, col + i) for i in range(SHIP_LENGTH)]
            if not any(c in ships for c in coords):
                ships.extend(coords)
        return ships

    def distance(self, ships, row, col):
        return min(abs(r - row) + abs(c - col) for r, c in ships)

    def process_move(self, player, row, col):
        if player != self.turn:
            return "WAIT"

        if (row, col) in self.shots[player]:
            return "USED"

        self.shots[player].add((row, col))
        opponent = 1 - player

        if (row, col) in self.ships[opponent]:
            self.ships[opponent].remove((row, col))
            if not self.ships[opponent]:
                return "WIN"
            return "HIT"

        dist = self.distance(self.ships[opponent], row, col)

        self.turn = opponent

        if dist <= 1:
            return "CLOSE"
        elif dist <= 3:
            return "MEDIUM"
        else:
            return "FAR"