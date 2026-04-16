import pygame
import threading
import queue
import random
import sys
import numpy as np
from pathlib import Path

# ensure the project root containing `tts.py` is on sys.path
# tts.py is used as the text-to-speech voiceover module used across the project
_this_file = Path(__file__).resolve()
for _parent in _this_file.parents:
    if (_parent / "tts.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

# use TTS helper for speech output
try:
    from tts import speak as _tts_speak
except ImportError:
    def _tts_speak(text: str):
        # display the error messageif tts helper is not available
        print(text)

# the sample rate is sets the number of audio samples per second
SAMPLE_RATE = 44100

# establish some basic colors and screen dimensions
WHITE  = (255, 255, 255)
BLACK  = (0,   0,   0)
BLUE   = (14,  92, 168)
GREEN  = (0,  126, 106)
YELLOW = (255, 191,  71)
GRAY   = (208, 218, 230)
DARK   = (18,   24,  33)

# set screen dimensions, later adjusted to fit within the user's display
SCREEN_W, SCREEN_H = 820, 720

# 
def _recommended_window_size(base_w: int, base_h: int) -> tuple[int, int]:
    screen_w = base_w
    screen_h = base_h

    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                screen_w = rect.right - rect.left
                screen_h = rect.bottom - rect.top
        except Exception:
            pass
    else:
        info = pygame.display.Info()
        if info.current_w > 0:
            screen_w = info.current_w
        if info.current_h > 0:
            screen_h = info.current_h

    width = max(base_w, min(screen_w - 40, int(screen_w * 0.96)))
    height = max(base_h, min(screen_h - 60, int(screen_h * 0.94)))
    return width, height

# ---------------------------------------------------------------------------
# Speech engine — cross-platform wrapper around the `tts` helper.
# ---------------------------------------------------------------------------
class SpeechEngine:
    def __init__(self):
        self._q = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        while True:
            text = self._q.get()
            if text is None:
                break
            try:
                _tts_speak(text)
            except Exception as e:
                print(f"TTS error: {e}")

    def speak(self, text, interrupt=False):
        """Queue speech; if interrupt=True, discard pending items first."""
        if interrupt:
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
        self._q.put(text)

    def stop(self):
        self._q.put(None)

# ---------------------------------------------------------------------------
# Scoreboard
# ---------------------------------------------------------------------------

def _report_win() -> None:
    import os
    user_id  = os.environ.get("HW_USER_ID",  "")
    username = os.environ.get("HW_USERNAME", "")
    if not user_id:
        return
    def _write():
        try:
            _repo_root = Path(__file__).resolve()
            while _repo_root != _repo_root.parent:
                if (_repo_root / "tts.py").exists():
                    break
                _repo_root = _repo_root.parent
            sys.path.insert(0, str(_repo_root))
            from launcher.scoreboard import Scoreboard
            sb = Scoreboard.from_workspace(_repo_root)
            sb.record_win(user_id, username, "maze")
        except Exception as exc:
            print(f"scoreboard write failed: {exc}")
    threading.Thread(target=_write, daemon=True).start()

# ---------------------------------------------------------------------------
# Sound generation — produces tones with numpy, no external audio files needed.
# ---------------------------------------------------------------------------
def _make_tone(freq, duration, volume=0.5, wave='sine', fade=True):
    frames = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, frames, endpoint=False)
    if wave == 'sine':
        arr = np.sin(2 * np.pi * freq * t)
    else:  # square
        arr = np.sign(np.sin(2 * np.pi * freq * t))
    if fade:
        arr *= np.linspace(1.0, 0.0, frames)
    arr = (arr * volume * 32767).astype(np.int16)
    stereo = np.column_stack([arr, arr])
    return pygame.sndarray.make_sound(stereo)

def _make_win_sound():
    freqs = [261, 329, 392, 523, 659]
    parts = []
    for f in freqs:
        frames = int(SAMPLE_RATE * 0.14)
        t = np.linspace(0, 0.14, frames, endpoint=False)
        arr = np.sin(2 * np.pi * f * t) * np.linspace(1.0, 0.0, frames)
        parts.append(arr)
    combined = np.concatenate(parts)
    combined = (combined * 0.6 * 32767).astype(np.int16)
    stereo = np.column_stack([combined, combined])
    return pygame.sndarray.make_sound(stereo)

# ---------------------------------------------------------------------------
# Maze generation — recursive DFS (backtracker).
# ---------------------------------------------------------------------------
def generate_maze(cols, rows):
    sys.setrecursionlimit(cols * rows * 4 + 500)
    visited = [[False] * rows for _ in range(cols)]
    passages = set()

    def dfs(c, r):
        visited[c][r] = True
        dirs = [(-1,0),(1,0),(0,-1),(0,1)]
        random.shuffle(dirs)
        for dc, dr in dirs:
            nc, nr = c + dc, r + dr
            if 0 <= nc < cols and 0 <= nr < rows and not visited[nc][nr]:
                passages.add(frozenset([(c, r), (nc, nr)]))
                dfs(nc, nr)

    dfs(0, 0)
    return passages

def can_move(passages, c, r, nc, nr):
    return frozenset([(c, r), (nc, nr)]) in passages

# ---------------------------------------------------------------------------
# Size-selection screen
# ---------------------------------------------------------------------------
class SizeSelectScreen:
    def __init__(self, screen, speech):
        self.screen  = screen
        self.speech  = speech
        self.size    = 10
        self.min_sz  = 5
        self.max_sz  = 25
        self.done    = False
        self.font    = pygame.font.SysFont("segoeui", 36, bold=False)
        self.big     = pygame.font.SysFont("segoeui", 62, bold=False)
        self.small   = pygame.font.SysFont("segoeui", 28, bold=False)
        self.speech.speak(
            "Welcome to Accessible Maze Game. "
            "Use UP and DOWN arrows to choose maze size. "
            f"Current size is {self.size} by {self.size}. "
            "Press ENTER to start. Press I for full instructions."
        )

    def handle(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_UP and self.size < self.max_sz:
            self.size += 1
            self.speech.speak(f"Size {self.size} by {self.size}", interrupt=True)
        elif event.key == pygame.K_DOWN and self.size > self.min_sz:
            self.size -= 1
            self.speech.speak(f"Size {self.size} by {self.size}", interrupt=True)
        elif event.key == pygame.K_SPACE:
            self.speech.speak(f"Current size is {self.size} by {self.size}", interrupt=True)
        elif event.key == pygame.K_i:
            self.speech.speak(
                "Instructions. "
                "Use UP and DOWN arrows to choose your maze size. "
                "Press ENTER to start. "
                "In the maze, use arrow keys to move. "
                "Press SPACE to hear which directions are open or blocked. "
                "Press Q to quit back to this menu. "
                "Press R to reset the maze with the same size. "
                "Good luck!",
                interrupt=True
            )
        elif event.key == pygame.K_RETURN:
            self.speech.speak(
                f"Starting {self.size} by {self.size} maze.",
                interrupt=True
            )
            self.done = True

    def draw(self):
        self.screen.fill(DARK)
        w = self.screen.get_width()

        title = self.big.render("Accessible Maze", True, YELLOW)
        self.screen.blit(title, (w//2 - title.get_width()//2, 80))

        sub = self.font.render("A game for the visually impaired", True, WHITE)
        self.screen.blit(sub, (w//2 - sub.get_width()//2, 155))

        size_txt = self.big.render(f"Size: {self.size} x {self.size}", True, GREEN)
        self.screen.blit(size_txt, (w//2 - size_txt.get_width()//2, 240))

        lines = [
            "UP / DOWN  — change maze size",
            "SPACE      — hear current size",
            "ENTER      — start game",
            "I          — hear full instructions",
            "",
            "In game:",
            "ARROWS     — move",
            "SPACE      — scan directions (tones + speech)",
            "Q          — quit to menu",
            "R          — reset maze (same size)",
            "",
            "On win screen:",
            "ENTER      — new maze (same size)",
            "SPACE      — return to this menu",
        ]
        for i, line in enumerate(lines):
            surf = self.small.render(line, True, WHITE if line else DARK)
            self.screen.blit(surf, (w//2 - 180, 340 + i * 32))

        pygame.display.flip()

# ---------------------------------------------------------------------------
# Main game
# ---------------------------------------------------------------------------
class MazeGame:
    DIRS = [
        ("Top",    0, -1, pygame.K_UP),
        ("Bottom", 0,  1, pygame.K_DOWN),
        ("Left",  -1,  0, pygame.K_LEFT),
        ("Right",  1,  0, pygame.K_RIGHT),
    ]

    def __init__(self, screen, speech, cols, rows):
        self.screen  = screen
        self.speech  = speech
        self.cols    = cols
        self.rows    = rows
        self.tile    = min(680 // max(cols, rows), 56)
        self.font    = pygame.font.SysFont("segoeui", 30, bold=False)
        self.big     = pygame.font.SysFont("segoeui", 50, bold=False)
        self.small   = pygame.font.SysFont("segoeui", 24, bold=False)

        # Sounds
        self.snd_move    = _make_tone(520,  0.09)
        self.snd_wall    = _make_tone(110,  0.18, wave='square')
        self.snd_win     = _make_win_sound()
        self.snd_open    = _make_tone(660,  0.07)
        self.snd_blocked = _make_tone(180,  0.07, wave='square')

        self.reset()

    def reset(self):
        self.passages = generate_maze(self.cols, self.rows)
        self.player   = [0, 0]
        self.exit_pos = [self.cols - 1, self.rows - 1]
        self.won      = False
        self.moves    = 0

    # ------------------------------------------------------------------
    def _open_dirs(self, c=None, r=None):
        if c is None:
            c, r = self.player
        result = {}
        for name, dc, dr, *_ in self.DIRS:
            nc, nr = c + dc, r + dr
            in_bounds = 0 <= nc < self.cols and 0 <= nr < self.rows
            result[name] = in_bounds and can_move(self.passages, c, r, nc, nr)
        return result

    def _announce_position(self):
        c, r   = self.player
        dirs   = self._open_dirs()
        opens  = [d for d, v in dirs.items() if v]
        dist   = abs(c - self.exit_pos[0]) + abs(r - self.exit_pos[1])

        open_str = ", ".join(opens) if opens else "none"
        parts = [
            f"Column {c}, row {r}.",
            f"Open: {open_str}.",
            f"Exit is {dist} step{'s' if dist != 1 else ''} away.",
        ]
        self.speech.speak(" ".join(parts), interrupt=True)

    def _scan_tones(self):
        """Play a tone per direction (open=high, blocked=low) then speak."""
        dirs = self._open_dirs()
        for name, *_ in self.DIRS:
            if dirs[name]:
                self.snd_open.play()
            else:
                self.snd_blocked.play()
            pygame.time.wait(120)
        # Wait for audio device to clear before TTS speaks
        pygame.time.wait(300)
        self._announce_position()

    # ------------------------------------------------------------------
    def handle_input(self, event):
        if event.type != pygame.KEYDOWN:
            return None

        if self.won:
            if event.key == pygame.K_RETURN:
                self.reset()
            elif event.key == pygame.K_SPACE:
                return "menu"
            return None

        c, r = self.player

        # Directional movement
        for name, dc, dr, k1 in self.DIRS:
            if event.key == k1:
                nc, nr = c + dc, r + dr
                in_bounds = 0 <= nc < self.cols and 0 <= nr < self.rows
                if in_bounds and can_move(self.passages, c, r, nc, nr):
                    self.player = [nc, nr]
                    self.snd_move.play()
                    self.moves += 1
                    if self.player == self.exit_pos:
                        self.won = True
                        self.snd_win.play()
                        _report_win()
                        self.speech.speak(
                            f"Congratulations! You reached the exit in {self.moves} move{'s' if self.moves != 1 else ''}! "
                            "Press Enter for a new maze or Space to return to the menu.",
                            interrupt=True
                        )
                else:
                    self.snd_wall.play()
                return None

        if event.key == pygame.K_SPACE:
            self._announce_position()
        elif event.key == pygame.K_q:
            self.speech.speak("Returning to menu.", interrupt=True)
            return "menu"
        elif event.key == pygame.K_r:
            self.speech.speak("Maze reset.", interrupt=True)
            self.reset()

        return None

    # ------------------------------------------------------------------
    def draw(self):
        self.screen.fill(DARK)
        screen_w = self.screen.get_width()
        screen_h = self.screen.get_height()
        t  = self.tile
        ox = (SCREEN_W - self.cols * t) // 2
        oy = 40 + (SCREEN_H - 80 - self.rows * t) // 2

        # --- Maze rendering: floor + explicit walls ---
        WALL_COLOR  = (232, 238, 245)
        FLOOR_COLOR = (38, 48, 64)
        WALL_W      = max(2, t // 6)

        # Draw all cell floors
        for r in range(self.rows):
            for c in range(self.cols):
                x, y = ox + c * t, oy + r * t
                pygame.draw.rect(self.screen, FLOOR_COLOR, (x, y, t, t))

        # Outer border
        pygame.draw.rect(self.screen, WALL_COLOR,
                         (ox, oy, self.cols * t, self.rows * t), WALL_W)

        # Internal walls — draw only where no passage exists
        for r in range(self.rows):
            for c in range(self.cols):
                x, y = ox + c * t, oy + r * t
                # East wall
                if c + 1 < self.cols and not can_move(self.passages, c, r, c+1, r):
                    pygame.draw.line(self.screen, WALL_COLOR,
                                     (x + t, y), (x + t, y + t), WALL_W)
                # South wall
                if r + 1 < self.rows and not can_move(self.passages, c, r, c, r+1):
                    pygame.draw.line(self.screen, WALL_COLOR,
                                     (x, y + t), (x + t, y + t), WALL_W)

        # Exit marker
        ex = ox + self.exit_pos[0] * t
        ey = oy + self.exit_pos[1] * t
        pygame.draw.rect(self.screen, GREEN, (ex+3, ey+3, t-6, t-6))
        pygame.draw.rect(self.screen, WHITE, (ex+3, ey+3, t-6, t-6), 3)
        lbl = self.small.render("EXIT", True, BLACK)
        self.screen.blit(lbl, (ex + t//2 - lbl.get_width()//2, ey + t//2 - lbl.get_height()//2))

        # Player
        px = ox + self.player[0] * t
        py = oy + self.player[1] * t
        pygame.draw.circle(self.screen, BLUE, (px + t//2, py + t//2), t//2 - 3)
        pygame.draw.circle(self.screen, WHITE, (px + t//2, py + t//2), t//2 - 3, 3)
        you = self.small.render("YOU", True, WHITE)
        self.screen.blit(you, (px + t//2 - you.get_width()//2, py + t//2 - you.get_height()//2))

        # HUD top
        hud = self.small.render(
            "ARROWS=move  SPACE=scan  Q=quit  R=reset  (win: ENTER=new  SPACE=menu)",
            True, GRAY
        )
        hud_text = "ARROWS=move   SPACE=scan directions   (win: ENTER=new maze   SPACE=menu)"
        while hud_text and self.small.size(hud_text)[0] > screen_w - 20:
            hud_text = hud_text[:-1]
        hud = self.small.render(hud_text, True, GRAY)
        self.screen.blit(hud, (screen_w//2 - hud.get_width()//2, 10))

        # HUD bottom
        pos_text = (
            f"Position: ({self.player[0]}, {self.player[1]})   "
            f"Exit: ({self.exit_pos[0]}, {self.exit_pos[1]})   "
            f"Moves: {self.moves}"
        )
        while pos_text and self.font.size(pos_text)[0] > screen_w - 20:
            pos_text = pos_text[:-1]
        pos = self.font.render(pos_text, True, WHITE)
        self.screen.blit(pos, (screen_w//2 - pos.get_width()//2, screen_h - 28))

        # Win overlay
        if self.won:
            overlay = pygame.Surface((SCREEN_W, 90), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.screen.blit(overlay, (0, SCREEN_H//2 - 45))
            win = self.big.render(
                f"YOU WIN!  {self.moves} moves   ENTER=new maze   SPACE=menu", True, YELLOW
            )
            self.screen.blit(win, (SCREEN_W//2 - win.get_width()//2, SCREEN_H//2 - 22))

        pygame.display.flip()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    pygame.init()
    pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
    global SCREEN_W, SCREEN_H
    SCREEN_W, SCREEN_H = _recommended_window_size(SCREEN_W, SCREEN_H)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Accessible Maze Game")

    speech   = SpeechEngine()
    clock    = pygame.time.Clock()
    state    = "menu"
    selector = SizeSelectScreen(screen, speech)
    game     = None

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                speech.stop()
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                speech.speak("Exiting Maze Game.", interrupt=True)
                speech.stop()
                pygame.quit()
                sys.exit()

            if state == "menu":
                selector.handle(event)
                if selector.done:
                    game  = MazeGame(screen, speech, selector.size, selector.size)
                    state = "game"
            elif state == "game":
                result = game.handle_input(event)
                if result == "menu":
                    selector = SizeSelectScreen(screen, speech)
                    state    = "menu"

        if state == "menu":
            selector.draw()
        elif state == "game":
            game.draw()

        clock.tick(60)

if __name__ == "__main__":
    main()