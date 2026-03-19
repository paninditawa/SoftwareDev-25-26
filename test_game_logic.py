"""
HelloWorld GameSpace — unit tests for all game logic modules.
Covers Battleship, Connect Four, Escape Room, Maze, Mad Libs, and Hangman.
Run with: python test_game_logic.py
"""

import sys
import random
from pathlib import Path

# paths to each game dir
REPO_ROOT = Path(__file__).resolve().parent
BATTLESHIP_DIR = REPO_ROOT / "games" / "Battleship"
GAME_LOGIC_DIR = REPO_ROOT / "games" / "game_logic"

# add both dirs to path so imports work
sys.path.insert(0, str(BATTLESHIP_DIR))
sys.path.insert(0, str(GAME_LOGIC_DIR))

import unittest


# battleship — game.py

class TestBattleshipShip(unittest.TestCase):
    """Tests for the Ship class in game.py."""

    def setUp(self):
        """Create a fresh Ship before each test."""
        from game import Ship
        self.ship = Ship("Destroyer", 2, [(0, 0), (0, 1)])

    def test_ship_not_sunk_on_creation(self):
        """A new ship should not be sunk."""
        self.assertFalse(self.ship.is_sunk())

    def test_hit_returns_true_for_valid_coord(self):
        """Hitting a cell the ship occupies should return True."""
        self.assertTrue(self.ship.hit((0, 0)))

    def test_hit_returns_false_for_missed_coord(self):
        """Hitting a cell the ship does not occupy should return False."""
        self.assertFalse(self.ship.hit((5, 5)))

    def test_ship_sinks_after_all_cells_hit(self):
        """Ship should report sunk after every cell is hit."""
        self.ship.hit((0, 0))
        self.ship.hit((0, 1))
        self.assertTrue(self.ship.is_sunk())

    def test_ship_not_sunk_after_partial_hit(self):
        """Ship should not be sunk after only one of two cells is hit."""
        self.ship.hit((0, 0))
        self.assertFalse(self.ship.is_sunk())


class TestBattleshipPlacement(unittest.TestCase):
    """Tests for ship placement validation in the Game class."""

    def setUp(self):
        """Create a fresh Game before each test."""
        from game import Game
        self.game = Game()

    def test_valid_horizontal_placement(self):
        """Placing a ship horizontally within bounds should succeed."""
        ok, msg = self.game.place_ship(0, "Destroyer", 0, 0, "H")
        self.assertTrue(ok)

    def test_valid_vertical_placement(self):
        """Placing a ship vertically within bounds should succeed."""
        ok, msg = self.game.place_ship(0, "Destroyer", 0, 0, "V")
        self.assertTrue(ok)

    def test_placement_out_of_bounds_horizontal(self):
        """Placing a ship that extends past the board edge should fail."""
        ok, msg = self.game.place_ship(0, "Aircraft Carrier", 0, 6, "H")
        self.assertFalse(ok)

    def test_placement_out_of_bounds_vertical(self):
        """Placing a ship that extends past the board edge vertically should fail."""
        ok, msg = self.game.place_ship(0, "Aircraft Carrier", 6, 0, "V")
        self.assertFalse(ok)

    def test_overlapping_ships_rejected(self):
        """Placing two ships on the same cell should fail."""
        self.game.place_ship(0, "Destroyer", 0, 0, "H")
        ok, msg = self.game.place_ship(0, "Submarine", 0, 0, "H")
        self.assertFalse(ok)

    def test_unknown_ship_name_rejected(self):
        """Placing a ship with an unknown name should fail."""
        ok, msg = self.game.place_ship(0, "SpaceShip", 0, 0, "H")
        self.assertFalse(ok)

    def test_invalid_orientation_rejected(self):
        """Placing a ship with an invalid orientation should fail."""
        ok, msg = self.game.place_ship(0, "Destroyer", 0, 0, "X")
        self.assertFalse(ok)

    def test_cannot_place_after_ready(self):
        """Placing ships after a player marks ready should fail."""
        from game import SHIPS
        for i, (name, _) in enumerate(SHIPS):
            self.game.place_ship(0, name, i, 0, "H")
        self.game.set_ready(0)
        ok, msg = self.game.place_ship(0, "Destroyer", 7, 7, "H")
        self.assertFalse(ok)


class TestBattleshipReadyAndFire(unittest.TestCase):
    """Tests for the ready system and firing mechanics."""

    def _place_all_ships(self, player):
        """Helper — places all ships for one player in valid positions."""
        from game import SHIPS
        for i, (name, _) in enumerate(SHIPS):
            self.game.place_ship(player, name, i, 0, "H")

    def setUp(self):
        """Create a game w/ all ships placed for both players."""
        from game import Game
        self.game = Game()
        self._place_all_ships(0)
        self._place_all_ships(1)

    def test_set_ready_succeeds_after_all_ships_placed(self):
        """Setting ready should succeed once all ships are placed."""
        ok, _ = self.game.set_ready(0)
        self.assertTrue(ok)

    def test_cannot_set_ready_twice(self):
        """Setting ready twice should fail the second time."""
        self.game.set_ready(0)
        ok, _ = self.game.set_ready(0)
        self.assertFalse(ok)

    def test_all_ready_true_when_both_players_ready(self):
        """all_ready() should return True only when both players are ready."""
        self.game.set_ready(0)
        self.assertFalse(self.game.all_ready())
        self.game.set_ready(1)
        self.assertTrue(self.game.all_ready())

    def test_fire_miss_on_empty_cell(self):
        """Firing at an empty cell should return MISS."""
        self.game.set_ready(0)
        self.game.set_ready(1)
        result = self.game.process_fire(0, 7, 7)
        self.assertEqual(result["status"], "MISS")

    def test_fire_hit_on_ship_cell(self):
        """Firing at a ship cell should return HIT."""
        self.game.set_ready(0)
        self.game.set_ready(1)
        # player 1's ships are at row i, col 0
        result = self.game.process_fire(0, 0, 0)
        self.assertEqual(result["status"], "HIT")

    def test_fire_used_on_repeated_cell(self):
        """Firing at an already-fired cell should return USED."""
        self.game.set_ready(0)
        self.game.set_ready(1)
        self.game.process_fire(0, 7, 7)
        self.game.process_fire(1, 7, 7)  # give turn back to p0
        result = self.game.process_fire(0, 7, 7)
        self.assertEqual(result["status"], "USED")

    def test_fire_wait_when_not_players_turn(self):
        """Firing out of turn should return WAIT."""
        self.game.set_ready(0)
        self.game.set_ready(1)
        result = self.game.process_fire(1, 0, 0)
        self.assertEqual(result["status"], "WAIT")

    def test_fire_not_ready_before_game_starts(self):
        """Firing before both players are ready should return NOT_READY."""
        result = self.game.process_fire(0, 0, 0)
        self.assertEqual(result["status"], "NOT_READY")

    def test_turn_switches_after_miss(self):
        """After a miss, the turn should switch to the other player."""
        self.game.set_ready(0)
        self.game.set_ready(1)
        self.game.process_fire(0, 7, 7)  # miss
        self.assertEqual(self.game.turn, 1)

    def test_win_detected_when_all_ships_sunk(self):
        """Sinking all opponent ships should result in a WIN status."""
        self.game.set_ready(0)
        self.game.set_ready(1)

        # fully sink every ship except the last one
        for ship in self.game.ships[1][:-1]:
            for coord in list(ship.coords):
                ship.hit(coord)

        # on the last ship, hit all cells except one
        last_ship = self.game.ships[1][-1]
        remaining = list(last_ship.coords)
        for coord in remaining[:-1]:
            last_ship.hit(coord)

        # force p0's turn and fire the final cell thru process_fire
        self.game.turn = 0
        final_coord = remaining[-1]
        result = self.game.process_fire(0, final_coord[0], final_coord[1])

        self.assertEqual(result["status"], "HIT")
        self.assertTrue(result.get("win"), "expected win=True but got: " + str(result))


# connect four — c4_game.py

class TestConnectFour(unittest.TestCase):
    """Tests for the Connect Four logic functions."""

    def setUp(self):
        """Import game functions before each test."""
        from c4_game import create_board, drop_piece, winning_move, describe_column
        self.create_board = create_board
        self.drop_piece = drop_piece
        self.winning_move = winning_move
        self.describe_column = describe_column

    def test_board_starts_empty(self):
        """A new board should contain all zeros."""
        board = self.create_board()
        self.assertEqual(board.sum(), 0)

    def test_board_dimensions(self):
        """Board should be 6 rows by 7 columns."""
        board = self.create_board()
        self.assertEqual(board.shape, (6, 7))

    def test_drop_piece_places_at_bottom(self):
        """Dropping a piece should place it in the lowest available row."""
        board = self.create_board()
        self.drop_piece(board, 0, 1)
        self.assertEqual(board[5][0], 1)

    def test_drop_piece_stacks(self):
        """Dropping two pieces in the same column should stack them."""
        board = self.create_board()
        self.drop_piece(board, 3, 1)
        self.drop_piece(board, 3, 2)
        self.assertEqual(board[5][3], 1)
        self.assertEqual(board[4][3], 2)

    def test_drop_piece_full_column_returns_false(self):
        """Dropping into a full column should return False."""
        board = self.create_board()
        for _ in range(6):
            self.drop_piece(board, 0, 1)
        result = self.drop_piece(board, 0, 1)
        self.assertFalse(result)

    def test_horizontal_win_detected(self):
        """Four in a row horizontally should be detected as a win."""
        board = self.create_board()
        for col in range(4):
            self.drop_piece(board, col, 1)
        self.assertTrue(self.winning_move(board, 1))

    def test_vertical_win_detected(self):
        """Four in a row vertically should be detected as a win."""
        board = self.create_board()
        for _ in range(4):
            self.drop_piece(board, 0, 1)
        self.assertTrue(self.winning_move(board, 1))

    def test_diagonal_win_detected(self):
        """Four in a diagonal should be detected as a win."""
        board = self.create_board()
        # build bottom-left to top-right diagonal for p1
        for col in range(4):
            for filler in range(col):
                self.drop_piece(board, col, 2)
            self.drop_piece(board, col, 1)
        self.assertTrue(self.winning_move(board, 1))

    def test_no_win_on_empty_board(self):
        """An empty board should not report a win for either player."""
        board = self.create_board()
        self.assertFalse(self.winning_move(board, 1))
        self.assertFalse(self.winning_move(board, 2))

    def test_describe_column_empty(self):
        """An empty column should be described as 6 empty."""
        board = self.create_board()
        desc = self.describe_column(board, 0)
        self.assertIn("empty", desc)

    def test_describe_column_with_piece(self):
        """A column with one piece should mention that player."""
        board = self.create_board()
        self.drop_piece(board, 0, 1)
        desc = self.describe_column(board, 0)
        self.assertIn("Player 1", desc)


# escape room — escape_room_game.py

class TestEscapeRoomPuzzles(unittest.TestCase):
    """Tests for the Puzzle, SoundPuzzle, and SequencePuzzle classes."""

    def test_puzzle_correct_answer_accepted(self):
        """Submitting the correct answer should mark the puzzle as solved."""
        from escape_room_game import Puzzle
        p = Puzzle("Test", "A riddle.", "map", "Hint.", choices=["map", "globe"])
        correct, _ = p.attempt("map")
        self.assertTrue(correct)
        self.assertTrue(p.solved)

    def test_puzzle_wrong_answer_rejected(self):
        """Submitting the wrong answer should not mark the puzzle as solved."""
        from escape_room_game import Puzzle
        p = Puzzle("Test", "A riddle.", "map", "Hint.", choices=["map", "globe"])
        correct, _ = p.attempt("globe")
        self.assertFalse(correct)
        self.assertFalse(p.solved)

    def test_puzzle_answer_substring_match(self):
        """Answer embedded in a longer spoken phrase should still be accepted."""
        from escape_room_game import Puzzle
        p = Puzzle("Test", "A riddle.", "map", "Hint.")
        correct, _ = p.attempt("I think the answer is map")
        self.assertTrue(correct)

    def test_puzzle_reward_in_response(self):
        """Solving a puzzle with a reward should mention the reward."""
        from escape_room_game import Puzzle
        p = Puzzle("Test", "A riddle.", "key", "Hint.", reward="brass key")
        _, msg = p.attempt("key")
        self.assertIn("brass key", msg)

    def test_sound_puzzle_correct_count(self):
        """Saying the correct count for a sound puzzle should solve it."""
        from escape_room_game import SoundPuzzle
        p = SoundPuzzle("Chimes", "Listen.", 5, "Count the chimes.")
        correct, _ = p.attempt("five")
        self.assertTrue(correct)

    def test_sound_puzzle_wrong_count(self):
        """Saying the wrong count should not solve a sound puzzle."""
        from escape_room_game import SoundPuzzle
        p = SoundPuzzle("Chimes", "Listen.", 5, "Count the chimes.")
        correct, _ = p.attempt("three")
        self.assertFalse(correct)

    def test_sequence_puzzle_correct_order(self):
        """Completing a sequence in order should solve the puzzle."""
        from escape_room_game import SequencePuzzle
        p = SequencePuzzle("Valves", "Turn valves.", ["red", "blue", "green"], "Hint.")
        p.attempt("red")
        p.attempt("blue")
        correct, _ = p.attempt("green")
        self.assertTrue(correct)
        self.assertTrue(p.solved)

    def test_sequence_puzzle_wrong_order_resets(self):
        """Saying the wrong step in a sequence should reset progress."""
        from escape_room_game import SequencePuzzle
        p = SequencePuzzle("Valves", "Turn valves.", ["red", "blue", "green"], "Hint.")
        p.attempt("red")
        p.attempt("green")  # wrong — should be blue
        self.assertEqual(p.progress, 0)

    def test_room_all_solved_true_when_no_puzzles(self):
        """A room with no puzzles should always report all_solved as True."""
        from escape_room_game import Room
        r = Room("Empty Room", "Nothing here.")
        self.assertTrue(r.all_solved())

    def test_room_all_solved_false_when_unsolved_puzzle(self):
        """A room with an unsolved puzzle should report all_solved as False."""
        from escape_room_game import Room, Puzzle
        p = Puzzle("Riddle", "Desc.", "answer", "Hint.")
        r = Room("Room", "Desc.", puzzles=[p])
        self.assertFalse(r.all_solved())

    def test_build_levels_returns_three_levels(self):
        """build_levels() should return exactly three level objects."""
        from escape_room_game import build_levels
        levels = build_levels()
        self.assertEqual(len(levels), 3)

    def test_each_level_has_start_and_escape_room(self):
        """Each level should have both a start room and an escape room defined."""
        from escape_room_game import build_levels
        for level in build_levels():
            self.assertIn(level.start_room, level.rooms)
            self.assertIn(level.escape_room, level.rooms)


# maze game — maze_game.py

class TestMazeGeneration(unittest.TestCase):
    """Tests for maze generation and movement logic."""

    def test_maze_generates_passages(self):
        """generate_maze should return a non-empty set of passages."""
        from maze_game import generate_maze
        passages = generate_maze(5, 5)
        self.assertGreater(len(passages), 0)

    def test_maze_all_cells_reachable(self):
        """Every cell in the maze should be reachable from (0,0) via DFS."""
        from maze_game import generate_maze, can_move
        cols, rows = 7, 7
        passages = generate_maze(cols, rows)

        visited = set()
        stack = [(0, 0)]
        while stack:
            c, r = stack.pop()
            if (c, r) in visited:
                continue
            visited.add((c, r))
            for dc, dr in [(-1,0),(1,0),(0,-1),(0,1)]:
                nc, nr = c + dc, r + dr
                if 0 <= nc < cols and 0 <= nr < rows and can_move(passages, c, r, nc, nr):
                    stack.append((nc, nr))

        self.assertEqual(len(visited), cols * rows)

    def test_can_move_returns_false_for_no_passage(self):
        """can_move should return False when no passage exists between two cells."""
        from maze_game import can_move
        # empty passage set means no connections at all
        self.assertFalse(can_move(set(), 0, 0, 0, 1))

    def test_can_move_returns_true_for_existing_passage(self):
        """can_move should return True when a passage exists between two cells."""
        from maze_game import can_move
        passages = {frozenset([(0, 0), (0, 1)])}
        self.assertTrue(can_move(passages, 0, 0, 0, 1))

    def test_maze_passage_count_reasonable(self):
        """A 5x5 maze should have exactly 24 passages (spanning tree = cols*rows - 1 edges)."""
        from maze_game import generate_maze
        passages = generate_maze(5, 5)
        self.assertEqual(len(passages), 5 * 5 - 1)


# mad libs — madlibs_game.py

class TestMadLibs(unittest.TestCase):
    """Tests for Mad Libs story data and word option structure."""

    def test_three_stories_defined(self):
        """There should be exactly three Mad Libs stories available."""
        from madlibs_game import MADLIBS_STORIES
        self.assertEqual(len(MADLIBS_STORIES), 3)

    def test_each_story_has_required_keys(self):
        """Each story must have title, prompts, and story keys."""
        from madlibs_game import MADLIBS_STORIES
        for key, story in MADLIBS_STORIES.items():
            self.assertIn("title", story, f"story '{key}' missing title")
            self.assertIn("prompts", story, f"story '{key}' missing prompts")
            self.assertIn("story", story, f"story '{key}' missing story template")

    def test_story_prompts_match_template_slots(self):
        """Story template should fill correctly with the number of prompts provided."""
        from madlibs_game import MADLIBS_STORIES
        for key, story in MADLIBS_STORIES.items():
            prompt_count = len(story["prompts"])
            dummy_words = ["test"] * prompt_count
            try:
                filled = story["story"].format(*dummy_words)
                self.assertIsInstance(filled, str)
            except IndexError as e:
                self.fail(f"story '{key}' has more template slots than prompts: {e}")

    def test_word_options_exist_for_common_types(self):
        """Common word types like adjective and noun should have option lists."""
        from madlibs_game import WORD_OPTIONS
        for word_type in ["adjective", "noun", "verb"]:
            self.assertIn(word_type, WORD_OPTIONS)
            self.assertGreater(len(WORD_OPTIONS[word_type]), 0)

    def test_story_template_fills_correctly(self):
        """A story template should fill without errors when given the right number of words."""
        from madlibs_game import MADLIBS_STORIES
        for key, story in MADLIBS_STORIES.items():
            dummy_words = ["test"] * len(story["prompts"])
            try:
                filled = story["story"].format(*dummy_words)
                self.assertIsInstance(filled, str)
            except Exception as e:
                self.fail(f"story '{key}' failed to fill: {e}")

    def test_select_story_from_command_by_number(self):
        """Saying '1' should select the first story."""
        from madlibs_game import VoiceMadLibsGame
        import pygame
        pygame.init()
        pygame.display.set_mode((100, 100))
        try:
            game = VoiceMadLibsGame.__new__(VoiceMadLibsGame)
            game.story_keys = ["adventure", "school", "animal"]
            result = game._select_story_from_command("1")
            self.assertEqual(result, "adventure")
        finally:
            pygame.quit()

    def test_select_story_from_command_by_name(self):
        """Saying a story name keyword should select that story."""
        from madlibs_game import VoiceMadLibsGame
        import pygame
        pygame.init()
        pygame.display.set_mode((100, 100))
        try:
            game = VoiceMadLibsGame.__new__(VoiceMadLibsGame)
            game.story_keys = ["adventure", "school", "animal"]
            result = game._select_story_from_command("school")
            self.assertEqual(result, "school")
        finally:
            pygame.quit()


# hangman — hangman_game.py

class TestHangman(unittest.TestCase):
    """Tests for Hangman letter extraction and game state logic."""

    def test_extract_letter_single_letter(self):
        """Saying a single letter should extract that letter."""
        from hangman_game import _extract_letter
        self.assertEqual(_extract_letter("B"), "B")

    def test_extract_letter_spoken_name(self):
        """Saying 'bee' should extract the letter B."""
        from hangman_game import _extract_letter
        self.assertEqual(_extract_letter("bee"), "B")

    def test_extract_letter_nato(self):
        """Saying 'bravo' (NATO alphabet) should extract B."""
        from hangman_game import _extract_letter
        self.assertEqual(_extract_letter("bravo"), "B")

    def test_extract_letter_from_phrase(self):
        """Saying 'I guess the letter B' should extract B."""
        from hangman_game import _extract_letter
        self.assertEqual(_extract_letter("I guess the letter B"), "B")

    def test_extract_letter_returns_none_for_garbage(self):
        """Gibberish input should return None."""
        from hangman_game import _extract_letter
        self.assertIsNone(_extract_letter("xyzzy blorp"))

    def test_extract_command_status(self):
        """Saying 'status' should return the status command."""
        from hangman_game import _extract_command
        self.assertEqual(_extract_command("how am i doing"), "status")

    def test_extract_command_restart(self):
        """Saying 'play again' should return the restart command."""
        from hangman_game import _extract_command
        self.assertEqual(_extract_command("play again"), "restart")

    def test_extract_command_quit(self):
        """Saying 'quit' should return the quit command."""
        from hangman_game import _extract_command
        self.assertEqual(_extract_command("quit"), "quit")

    def test_extract_command_none_for_unknown(self):
        """An unrecognized phrase should return None."""
        from hangman_game import _extract_command
        self.assertIsNone(_extract_command("banana"))

    def test_words_list_not_empty(self):
        """The word list used in Hangman should not be empty."""
        from hangman_game import WORDS
        self.assertGreater(len(WORDS), 0)

    def test_words_list_all_uppercase(self):
        """All words in the Hangman word list should be uppercase."""
        from hangman_game import WORDS
        for word in WORDS:
            self.assertEqual(word, word.upper(), f"word '{word}' is not uppercase")


if __name__ == "__main__":
    unittest.main(verbosity=2)