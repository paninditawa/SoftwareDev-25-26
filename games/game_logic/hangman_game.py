"""
Voice-first Hangman with keyboard fallback.

Interaction model matches Escape Room / Mad Libs:
- Hold SPACEBAR to speak one command.
- Arrow keys move through letter buttons.
- ENTER guesses the selected letter.
- Up/Down reads status.
- ESC exits.

The visual hangman drawing and letter grid remain available.
"""

from __future__ import annotations

import pygame
import sys
import random
import time
import queue
import threading
from pathlib import Path

# Ensure repo root containing tts.py is on sys.path.
_this_file = Path(__file__).resolve()
for _parent in _this_file.parents:
    if (_parent / "tts.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

try:
    from tts import speak as _tts_speak, speak_interrupt as _tts_speak_interrupt
except ImportError:
    def _tts_speak(text: str):
        print(text)

    def _tts_speak_interrupt(text: str):
        print(text)

_sr_available = False
try:
    import speech_recognition as sr
    _sr_available = True
except ImportError:
    pass

WIDTH = 1000
HEIGHT = 700
FPS = 60
BG_COLOR = (248, 250, 252)
TEXT_COLOR = (16, 37, 63)
ACCENT_COLOR = (14, 92, 168)
WARNING_COLOR = (176, 83, 0)
MUTED_TEXT = (66, 85, 109)
FOCUS_COLOR = (255, 191, 71)
RADIUS = 24
SPACE = 20
WORDS = ["SOFTWARE", "DEVELOPMENT", "TECHNOLOGY", "STUDENT", "ASSOCIATION", "UNITY", "COMMUNITY"]


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

last_spoken = ""


def speak(text: str, interrupt: bool = False) -> None:
    global last_spoken
    last_spoken = text
    if interrupt:
        _tts_speak_interrupt(text)
    else:
        _tts_speak(text)


def _report_win() -> None:
    import os

    user_id = os.environ.get("HW_USER_ID", "")
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
            from launcher.services.leaderboard import Scoreboard

            sb = Scoreboard.from_workspace(_repo_root)
            sb.record_win(user_id, username, "hangman")
        except Exception as exc:
            print(f"scoreboard write failed: {exc}")

    threading.Thread(target=_write, daemon=True).start()


def _extract_letter(text: str) -> str | None:
    text = text.upper().strip()

    spoken_names = {
        "AY": "A", "BEE": "B", "BE": "B", "SEE": "C", "CEE": "C", "SEA": "C", "DEE": "D",
        "EE": "E", "EF": "F", "GEE": "G", "AITCH": "H", "EYE": "I",
        "JAY": "J", "KAY": "K", "EL": "L", "EM": "M", "EN": "N",
        "OH": "O", "PEE": "P", "CUE": "Q", "QUE": "Q", "QUEUE": "Q", "AR": "R", "ARE": "R",
        "ESS": "S", "TEE": "T", "TEA": "T", "YOU": "U", "VEE": "V",
        "WEE": "W", "DOUBLE YOU": "W", "DOUBLE-YOU": "W",
        "EKS": "X", "EX": "X", "WHY": "Y", "ZED": "Z", "ZEE": "Z",
    }

    for prefix in [
        "THE LETTER IS", "I GUESS", "LETTER", "I THINK", "TRY", "GUESS",
        "MY GUESS IS", "HOW ABOUT", "MAYBE", "I'LL SAY", "I SAY",
    ]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    if len(text) == 1 and text.isalpha():
        return text

    for name, letter in spoken_names.items():
        if text == name:
            return letter

    words = text.split()
    letter_words = [w for w in words if len(w) == 1 and w.isalpha()]
    if len(letter_words) == 1:
        return letter_words[0]

    return None


def _extract_command(text: str) -> str | None:
    text = text.lower().strip()
    if any(w in text for w in ["status", "how am i doing", "progress", "how many"]):
        return "status"
    if any(w in text for w in ["restart", "new game", "start over", "reset", "play again"]):
        return "restart"
    if any(w in text for w in ["start", "begin", "play"]):
        return "start"
    if any(w in text for w in ["quit", "exit", "close", "stop"]):
        return "quit"
    return None


class VoiceListener:
    def __init__(self):
        self.result_queue: queue.Queue[str] = queue.Queue()
        self._recognizer = None
        self._mic = None

        if _sr_available:
            self._recognizer = sr.Recognizer()
            try:
                self._mic = sr.Microphone()
                with self._mic as source:
                    # Longer calibration window gives a more accurate noise floor.
                    self._recognizer.adjust_for_ambient_noise(source, duration=1.0)
                # Nudge threshold down so quiet speech is reliably detected,
                # then pin it so dynamic adjustment can't drift it upward mid-session.
                self._recognizer.energy_threshold = max(
                    self._recognizer.energy_threshold * 0.8, 200
                )
                self._recognizer.dynamic_energy_threshold = False
                self._recognizer.pause_threshold = 0.9
            except Exception:
                self._mic = None

    @property
    def available(self) -> bool:
        return self._recognizer is not None and self._mic is not None

    def listen_once(self) -> None:
        if not self.available:
            self.result_queue.put("")
            return

        def _work() -> None:
            try:
                with self._mic as source:
                    audio = self._recognizer.listen(source, timeout=5, phrase_time_limit=10)
            except Exception:
                self.result_queue.put("")
                return
            # Retry recognition once in case of a transient API or network error.
            for _attempt in range(2):
                try:
                    text = self._recognizer.recognize_google(audio, language="en-US")
                    self.result_queue.put(text.lower().strip())
                    return
                except Exception:
                    if _attempt == 0:
                        continue
                    break
            self.result_queue.put("")

        threading.Thread(target=_work, daemon=True).start()

    def get_result(self) -> str | None:
        try:
            return self.result_queue.get_nowait()
        except queue.Empty:
            return None


class HangmanGame:
    def __init__(self):
        pygame.init()
        global WIDTH, HEIGHT
        WIDTH, HEIGHT = _recommended_window_size(WIDTH, HEIGHT)
        self.win = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Hangman")
        self.clock = pygame.time.Clock()

        self.font = pygame.font.SysFont("segoeui", 44, bold=False)
        self.word_font = pygame.font.SysFont("segoeui", 40, bold=False)
        self.title_font = pygame.font.SysFont("segoeui", 66, bold=False)
        self.small_font = pygame.font.SysFont("segoeui", 24, bold=False)

        self.voice = VoiceListener()
        self.listening = False

        self.state = "menu"
        self.status_text = "Hold SPACEBAR to speak"
        self.detail_text = "Say start to begin"
        self.result_announced = False

        self.letters: list[list] = []
        self.selected_index = 0
        self.create_buttons()
        self.reset_game(announce=False)

        if self.voice.available:
            speak(
                "Welcome to Hangman. Hold spacebar to speak commands. "
                "Use left and right arrows to move letters, up or down for status, and press enter to guess. "
                "Say start to begin.",
                interrupt=True,
            )
        else:
            self.status_text = "Voice input unavailable"
            self.detail_text = "Keyboard mode: left/right move, enter guess, up/down status"
            speak(
                "Voice input is unavailable. Keyboard mode is active. "
                "Use left and right arrows and enter to guess letters. Press up or down for status."
            )

    def _elapsed_text(self) -> str:
        elapsed = max(0, int(time.time() - self.start_time))
        minutes, seconds = divmod(elapsed, 60)
        return f"{minutes} minutes and {seconds} seconds"

    def _speak_status(self) -> None:
        guessed_letters = ", ".join(sorted(self.guessed)) if self.guessed else "none yet"
        word_spoken = ", ".join((l if l in self.guessed else "blank") for l in self.word)
        msg = (
            f"The word has {len(self.word)} letters. "
            f"So far: {word_spoken}. "
            f"You have {6 - self.hangman} wrong guesses remaining. "
            f"Letters guessed: {guessed_letters}."
        )
        speak(msg, interrupt=True)

    def reset_game(self, announce: bool = True) -> None:
        self.word = random.choice(WORDS)
        self.guessed: list[str] = []
        self.hangman = 0
        self.start_time = time.time()
        self.selected_index = 0
        self.result_announced = False
        for letter in self.letters:
            letter[3] = True

        self.status_text = "Use left/right + ENTER, or hold SPACEBAR to speak"
        self.detail_text = "Guess one letter at a time"

        if announce:
            speak(f"New game. The word has {len(self.word)} letters.", interrupt=True)

    def create_buttons(self) -> None:
        x_start = round((WIDTH - (RADIUS * 2 + SPACE) * 13) / 2)
        y_start = 540
        A = 65
        for i in range(26):
            x = x_start + SPACE * 2 + ((RADIUS * 2 + SPACE) * (i % 13))
            y = y_start + ((i // 13) * (SPACE + RADIUS * 2))
            self.letters.append([x, y, chr(A + i), True])

    def _start_game(self) -> None:
        self.reset_game()
        self.state = "playing"
        self.status_text = "Game in progress"
        self.detail_text = "Use left/right + ENTER, up/down for status, or hold SPACEBAR and say a letter"

    def _process_letter_guess(self, ltr: str) -> None:
        match = next((l for l in self.letters if l[2] == ltr), None)
        if match is None:
            return
        if not match[3]:
            speak(f"{ltr} was already guessed.", interrupt=True)
            self.status_text = f"{ltr} already guessed"
            return

        match[3] = False
        self.guessed.append(ltr)

        if ltr in self.word:
            count = self.word.count(ltr)
            plural = "time" if count == 1 else "times"
            speak(f"{ltr} is in the word, {count} {plural}.", interrupt=True)
            self.status_text = f"Good guess: {ltr}"
        else:
            self.hangman += 1
            remaining = 6 - self.hangman
            speak(f"{ltr} is not in the word. {remaining} wrong guesses remaining.", interrupt=True)
            self.status_text = f"Wrong guess: {ltr}"

        self.detail_text = f"Guessed letters: {', '.join(sorted(self.guessed)) if self.guessed else 'none'}"

    def check_game_over(self) -> None:
        won = all(letter in self.guessed for letter in self.word)
        if won:
            self.state = "result"
            self.result = "win"
            self.result_announced = False
            _report_win()
        elif self.hangman == 6:
            self.state = "result"
            self.result = "lose"
            self.result_announced = False

    def _move_selection(self, step: int) -> None:
        for _ in range(26):
            self.selected_index = (self.selected_index + step) % 26
            if self.letters[self.selected_index][3]:
                break
        speak(self.letters[self.selected_index][2])

    def _handle_playing_keyboard(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_LEFT:
            self._move_selection(-1)
        elif event.key == pygame.K_RIGHT:
            self._move_selection(1)
        elif event.key in (pygame.K_UP, pygame.K_DOWN):
            self._speak_status()
        elif event.key == pygame.K_RETURN:
            letter = self.letters[self.selected_index]
            if letter[3]:
                self._process_letter_guess(letter[2])

    def _process_voice_text(self, text: str) -> None:
        if not text:
            self.status_text = "I did not catch that"
            self.detail_text = "Try again and speak clearly"
            speak("I did not catch that. Please try again.", interrupt=True)
            return

        cmd = _extract_command(text)
        if cmd == "quit":
            speak("Goodbye.", interrupt=True)
            pygame.quit()
            sys.exit()

        if self.state == "menu":
            if cmd in ("start", "restart"):
                self._start_game()
                return
            if cmd == "status":
                speak("You are on the Hangman start menu. Say start to begin.", interrupt=True)
                return
            speak("Say start to begin, or quit to exit.", interrupt=True)
            return

        if self.state == "playing":
            if cmd == "status":
                self._speak_status()
                return
            if cmd in ("restart", "start"):
                self._start_game()
                return

            letter = _extract_letter(text)
            if letter:
                self._process_letter_guess(letter)
            else:
                speak("Say a single letter, status, restart, or quit.", interrupt=True)
            return

        if self.state == "result":
            if cmd in ("restart", "start"):
                self._start_game()
                return
            if cmd == "status":
                if self.result == "win":
                    speak("You won. Say restart to play again, or quit.", interrupt=True)
                else:
                    speak(f"You lost. The word was {self.word}. Say restart to try again, or quit.", interrupt=True)
                return
            speak("Say restart to play again, or quit.", interrupt=True)

    def draw_hangman(self) -> None:
        x = 150
        y = 450
        pygame.draw.line(self.win, TEXT_COLOR, (x, y), (x + 200, y), 5)
        pygame.draw.line(self.win, TEXT_COLOR, (x + 100, y), (x + 100, y - 300), 5)
        pygame.draw.line(self.win, TEXT_COLOR, (x + 100, y - 300), (x + 200, y - 300), 5)
        pygame.draw.line(self.win, TEXT_COLOR, (x + 200, y - 300), (x + 200, y - 250), 5)
        if self.hangman >= 1:
            pygame.draw.circle(self.win, TEXT_COLOR, (x + 200, y - 220), 30, 3)
        if self.hangman >= 2:
            pygame.draw.line(self.win, TEXT_COLOR, (x + 200, y - 190), (x + 200, y - 120), 3)
        if self.hangman >= 3:
            pygame.draw.line(self.win, TEXT_COLOR, (x + 200, y - 170), (x + 160, y - 150), 3)
        if self.hangman >= 4:
            pygame.draw.line(self.win, TEXT_COLOR, (x + 200, y - 170), (x + 240, y - 150), 3)
        if self.hangman >= 5:
            pygame.draw.line(self.win, TEXT_COLOR, (x + 200, y - 120), (x + 170, y - 80), 3)
        if self.hangman >= 6:
            pygame.draw.line(self.win, TEXT_COLOR, (x + 200, y - 120), (x + 230, y - 80), 3)

    def draw_menu(self) -> None:
        self.win.fill(BG_COLOR)
        max_w = WIDTH - 40
        title = self.title_font.render("Hangman", True, TEXT_COLOR)
        self.win.blit(title, (WIDTH / 2 - title.get_width() / 2, 190))

        menu_line = "Hold SPACE and say start, or press ENTER to begin"
        while menu_line and self.word_font.size(menu_line)[0] > max_w:
            menu_line = menu_line[:-1]
        text = self.word_font.render(menu_line, True, TEXT_COLOR)
        self.win.blit(text, (WIDTH / 2 - text.get_width() / 2, 330))

        mic_status = "Microphone: ON" if self.voice.available else "Microphone: OFF (keyboard mode)"
        while mic_status and self.small_font.size(mic_status)[0] > max_w:
            mic_status = mic_status[:-1]
        mic_color = ACCENT_COLOR if self.voice.available else WARNING_COLOR
        mic_text = self.small_font.render(mic_status, True, mic_color)
        self.win.blit(mic_text, (WIDTH / 2 - mic_text.get_width() / 2, 410))

        hint = self.small_font.render("ESC exits", True, MUTED_TEXT)
        self.win.blit(hint, (WIDTH / 2 - hint.get_width() / 2, 455))
        pygame.display.update()

    def draw_game(self) -> None:
        self.win.fill(BG_COLOR)
        title = self.title_font.render("Hangman", True, TEXT_COLOR)
        self.win.blit(title, (WIDTH / 2 - title.get_width() / 2, 20))

        display_word = "".join((letter + " ") if letter in self.guessed else "_ " for letter in self.word)
        text = self.word_font.render(display_word, True, TEXT_COLOR)
        self.win.blit(text, (WIDTH / 2 - text.get_width() / 2, 250))

        for i, letter in enumerate(self.letters):
            x, y, ltr, visible = letter
            if visible:
                if i == self.selected_index:
                    pygame.draw.circle(self.win, ACCENT_COLOR, (x, y), RADIUS)
                pygame.draw.circle(self.win, TEXT_COLOR, (x, y), RADIUS, 3)
                text_color = BG_COLOR if i == self.selected_index else TEXT_COLOR
                txt = self.font.render(ltr, True, text_color)
                self.win.blit(txt, (x - txt.get_width() / 2, y - txt.get_height() / 2))

        if self.voice.available and self.listening:
            listening = self.small_font.render("Listening...", True, FOCUS_COLOR)
            self.win.blit(listening, (10, 132))

        if last_spoken:
            spoken_line = "Last: " + last_spoken
            while spoken_line and self.small_font.size(spoken_line)[0] > WIDTH - 20:
                spoken_line = spoken_line[:-1]
            last = self.small_font.render(spoken_line, True, MUTED_TEXT)
            self.win.blit(last, (10, 105))

        hint = self.small_font.render("Left/Right move letters | Up/Down status | ENTER guesses | Hold SPACE to speak", True, MUTED_TEXT)
        hint_line = hint
        if hint.get_width() > WIDTH - 20:
            hint_text = "L/R letters | Up/Down status | ENTER guess | Hold SPACE"
            hint_line = self.small_font.render(hint_text, True, MUTED_TEXT)
        self.win.blit(hint_line, (WIDTH / 2 - hint_line.get_width() / 2, 468))

        self.draw_hangman()
        pygame.display.update()

    def draw_result(self) -> None:
        self.win.fill(BG_COLOR)
        if self.result == "win":
            msg = "YOU WON!"
            sub_line = "Say restart or press ENTER to play again"
            if not self.result_announced:
                speak(f"You won! It took you {self._elapsed_text()}. Say restart or press enter to play again.", interrupt=True)
                self.result_announced = True
        else:
            msg = f"YOU LOST! Word was {self.word}"
            sub_line = "Say restart or press ENTER to try again"
            if not self.result_announced:
                speak(
                    f"You lost. The word was {self.word}. It took you {self._elapsed_text()}. "
                    "Say restart or press enter to play again.",
                    interrupt=True,
                )
                self.result_announced = True

        while msg and self.title_font.size(msg)[0] > WIDTH - 40:
            msg = msg[:-1]
        text = self.title_font.render(msg, True, TEXT_COLOR)
        self.win.blit(text, (WIDTH / 2 - text.get_width() / 2, 280))

        while sub_line and self.word_font.size(sub_line)[0] > WIDTH - 40:
            sub_line = sub_line[:-1]
        sub = self.word_font.render(sub_line, True, TEXT_COLOR)
        self.win.blit(sub, (WIDTH / 2 - sub.get_width() / 2, 390))

        pygame.display.update()

    def run(self) -> None:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    speak("Exiting Hangman.", interrupt=True)
                    pygame.quit()
                    sys.exit()

                if self.voice.available:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE and not self.listening:
                        self.listening = True
                        self.status_text = "Listening..."
                        self.voice.listen_once()
                else:
                    if event.type == pygame.KEYDOWN and self.state == "playing" and event.key == pygame.K_SPACE:
                        letter = self.letters[self.selected_index]
                        if letter[3]:
                            self._process_letter_guess(letter[2])

                if self.state == "menu":
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                        self._start_game()
                elif self.state == "playing":
                    self._handle_playing_keyboard(event)
                elif self.state == "result":
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                        self._start_game()
                    elif event.type == pygame.KEYDOWN and event.key in (pygame.K_UP, pygame.K_DOWN):
                        if self.result == "win":
                            speak("You won. Press enter or say restart to play again.", interrupt=True)
                        else:
                            speak(f"You lost. The word was {self.word}. Press enter or say restart.", interrupt=True)

            if self.listening:
                result = self.voice.get_result()
                if result is not None:
                    self.listening = False
                    self._process_voice_text(result)
                    if self.voice.available and self.state == "playing":
                        self.status_text = "Hold SPACEBAR to speak"

            if self.state == "menu":
                self.draw_menu()
            elif self.state == "playing":
                self.draw_game()
                self.check_game_over()
            elif self.state == "result":
                self.draw_result()

            self.clock.tick(FPS)


if __name__ == "__main__":
    game = HangmanGame()
    game.run()
