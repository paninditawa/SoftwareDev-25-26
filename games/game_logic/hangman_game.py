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

#Imports required libraries
from __future__ import annotations
import pygame
import sys
import random
import time
import queue
import threading
import math
import re
from array import array
from pathlib import Path

# Ensure repo root containing tts.py is on sys.path.
_this_file = Path(__file__).resolve()
for _parent in _this_file.parents:
    if (_parent / "tts.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

# Text-to-speech setup 
try:
    from tts import speak as _tts_speak, speak_interrupt as _tts_speak_interrupt
except ImportError:
    def _tts_speak(text: str):
        print(text)

    def _tts_speak_interrupt(text: str):
        print(text)

#Setting up speech recognition
_sr_available = False
try:
    import speech_recognition as sr
    _sr_available = True
except ImportError:
    pass

#GUI constants
WIDTH = 1000
HEIGHT = 700
FPS = 60
BG_COLOR = (239, 247, 255)
TEXT_COLOR = (24, 50, 79)
ACCENT_COLOR = (255, 95, 143)
WARNING_COLOR = (255, 122, 69)
MUTED_TEXT = (81, 102, 130)
FOCUS_COLOR = (255, 230, 109)
RADIUS = 24
SPACE = 20
WORDS = ["SOFTWARE", "DEVELOPMENT", "TECHNOLOGY", "STUDENT", "ASSOCIATION", "UNITY", "COMMUNITY"]
SAMPLE_RATE = 22050


# Adjust window size based on screen
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

    # Clamp size to fit the visible screen instead of forcing the base size.
    # This keeps the full UI reachable on smaller laptop displays.
    usable_w = min(screen_w - 40, int(screen_w * 0.96))
    usable_h = min(screen_h - 60, int(screen_h * 0.94))
    width = max(640, min(base_w, usable_w))
    height = max(560, min(base_h, usable_h))
    return width, height

# Generate a short beep sound (used when listening)
def _make_tone(frequency: int, duration: float, volume: float = 0.25) -> pygame.mixer.Sound | None:
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
        sample_count = max(1, int(SAMPLE_RATE * duration))
        samples = array("h")
        amplitude = int(32767 * max(0.0, min(volume, 1.0)))
        for index in range(sample_count):
            frame = int(amplitude * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE))
            samples.append(frame)
        return pygame.mixer.Sound(buffer=samples.tobytes())
    except Exception:
        return None

# Track last spoken message for UI display
last_spoken = ""

# Extract a spoken letter from voice input
def speak(text: str, interrupt: bool = False) -> None:
    global last_spoken
    last_spoken = text
    if interrupt:
        _tts_speak_interrupt(text)
    else:
        _tts_speak(text)

#Says who wins
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

# Extract commands like "start", "quit", etc.
def _extract_letter(text: str) -> str | None:
    text = re.sub(r"[^A-Z\s'-]", " ", text.upper())
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    spoken_names = {
        "AY": "A", "BEE": "B", "BE": "B", "SEE": "C", "CEE": "C", "SEA": "C", "DEE": "D",
        "EE": "E", "EF": "F", "GEE": "G", "AITCH": "H", "EYE": "I",
        "JAY": "J", "KAY": "K", "EL": "L", "EM": "M", "EN": "N",
        "OH": "O", "PEE": "P", "CUE": "Q", "QUE": "Q", "QUEUE": "Q", "AR": "R", "ARE": "R",
        "ESS": "S", "TEE": "T", "TEA": "T", "YOU": "U", "VEE": "V",
        "WEE": "W", "DOUBLE YOU": "W", "DOUBLE-YOU": "W",
        "EKS": "X", "EX": "X", "WHY": "Y", "ZED": "Z", "ZEE": "Z",
        # NATO words help when recognition returns phonetic alphabet terms.
        "ALFA": "A", "ALPHA": "A", "BRAVO": "B", "CHARLIE": "C", "DELTA": "D",
        "ECHO": "E", "FOXTROT": "F", "GOLF": "G", "HOTEL": "H", "INDIA": "I",
        "JULIETT": "J", "JULIET": "J", "KILO": "K", "LIMA": "L", "MIKE": "M",
        "NOVEMBER": "N", "OSCAR": "O", "PAPA": "P", "ROMEO": "R", "SIERRA": "S",
        "TANGO": "T", "UNIFORM": "U", "VICTOR": "V", "WHISKEY": "W", "XRAY": "X", "X RAY": "X",
        "YANKEE": "Y", "ZULU": "Z",
    }

    for prefix in [
        "THE LETTER IS", "I GUESS", "LETTER", "I THINK", "TRY", "GUESS",
        "MY GUESS IS", "HOW ABOUT", "MAYBE", "I'LL SAY", "I SAY",
    ]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    if not text:
        return None

    if text in spoken_names:
        return spoken_names[text]

    if len(text) == 1 and text.isalpha():
        return text

    words = text.split()

    # Look for two-word names like "DOUBLE YOU" anywhere in the phrase.
    for i in range(len(words) - 1):
        pair = f"{words[i]} {words[i + 1]}"
        if pair in spoken_names:
            return spoken_names[pair]

    # Then check single-word spoken names like "BEE" or "BRAVO".
    for word in words:
        if word in spoken_names:
            return spoken_names[word]

    letter_words = [w for w in words if len(w) == 1 and w.isalpha()]
    if len(letter_words) == 1:
        return letter_words[0]

    return None

# Extract commands like "start", "quit", etc.
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

# Voice listener (runs in background thread)
class VoiceListener:
    def __init__(self):
        self.result_queue: queue.Queue[str] = queue.Queue()
        self._recognizer = None
        self._mic = None
        self.unavailable_reason = "SpeechRecognition is not installed."

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
                self.unavailable_reason = ""
            except Exception as exc:
                self._mic = None
                self.unavailable_reason = f"Microphone setup failed: {exc}"

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

# Main Hangman Game Class
class HangmanGame:
    def __init__(self):
        pygame.init()
        global WIDTH, HEIGHT
        WIDTH, HEIGHT = _recommended_window_size(WIDTH, HEIGHT)
        self.win = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Hangman")
        self.clock = pygame.time.Clock()

        self.font = pygame.font.SysFont("trebuchetms", 36, bold=True)
        self.word_font = pygame.font.SysFont("trebuchetms", 38, bold=True)
        self.title_font = pygame.font.SysFont("trebuchetms", 62, bold=True)
        self.small_font = pygame.font.SysFont("trebuchetms", 24, bold=False)
        self.snd_listen = _make_tone(880, 0.06, 0.25)

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
            self.detail_text = self.voice.unavailable_reason or "Keyboard mode: left/right move, enter guess, up/down status"
            speak(
                "Voice input is unavailable. Keyboard mode is active. "
                "Install SpeechRecognition and PyAudio, or check microphone permissions and the default input device. "
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

    # Reset game state
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

    # Create A–Z letter buttons
    def create_buttons(self) -> None:
        self.letters = []
        grid_width = (RADIUS * 2 + SPACE) * 13
        x_start = round((WIDTH - grid_width) / 2)
        y_start = HEIGHT - 150
        A = 65
        for i in range(26):
            x = x_start + SPACE * 2 + ((RADIUS * 2 + SPACE) * (i % 13))
            y = y_start + ((i // 13) * (SPACE + RADIUS * 2))
            self.letters.append([x, y, chr(A + i), True])

    def _fit_text(self, font: pygame.font.Font, text: str, max_width: int) -> str:
        fitted = text
        while fitted and font.size(fitted)[0] > max_width:
            fitted = fitted[:-1]
        return fitted

    def _draw_centered_text(self, font: pygame.font.Font, text: str, color: tuple[int, int, int], center_x: int, y: int, max_width: int) -> None:
        fitted = self._fit_text(font, text, max_width)
        rendered = font.render(fitted, True, color)
        self.win.blit(rendered, (center_x - rendered.get_width() / 2, y))

    def _draw_wrapped_text(self, font: pygame.font.Font, text: str, color: tuple[int, int, int], x: int, y: int, max_width: int, line_gap: int = 8) -> int:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = word if not current else f"{current} {word}"
            if font.size(trial)[0] <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        line_height = font.get_linesize()
        for index, line in enumerate(lines):
            rendered = font.render(line, True, color)
            self.win.blit(rendered, (x, y + index * (line_height + line_gap)))
        return len(lines) * line_height + max(0, len(lines) - 1) * line_gap

    def _start_game(self) -> None:
        self.reset_game()
        self.state = "playing"
        self.status_text = "Game in progress"
        self.detail_text = "Use left/right + ENTER, up/down for status, or hold SPACEBAR and say a letter"


    # Process a guessed letter
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

    #Will handle the state of the game after t ends
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

    #Moves the selected letter
    def _move_selection(self, step: int) -> None:
        for _ in range(26):
            self.selected_index = (self.selected_index + step) % 26
            if self.letters[self.selected_index][3]:
                break
        speak(self.letters[self.selected_index][2])

    #Allows user to use keyboard to pick letters
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

    #Analyzes input recieved from user speech
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

    #Draws the handman figure depending on current game status
    def draw_hangman(self) -> None:
        panel = pygame.Rect(40, 135, 360, 360)
        pygame.draw.rect(self.win, (211, 231, 255), panel, border_radius=28)
        pygame.draw.rect(self.win, (72, 215, 255), panel, 3, border_radius=28)

        x = 110
        y = 445
        pygame.draw.line(self.win, (72, 215, 255), (x, y), (x + 210, y), 8)
        pygame.draw.line(self.win, (72, 215, 255), (x + 90, y), (x + 90, y - 280), 8)
        pygame.draw.line(self.win, (72, 215, 255), (x + 90, y - 280), (x + 210, y - 280), 8)
        pygame.draw.line(self.win, (72, 215, 255), (x + 210, y - 280), (x + 210, y - 230), 6)
        if self.hangman >= 1:
            pygame.draw.circle(self.win, FOCUS_COLOR, (x + 210, y - 200), 30, 4)
        if self.hangman >= 2:
            pygame.draw.line(self.win, TEXT_COLOR, (x + 210, y - 170), (x + 210, y - 95), 5)
        if self.hangman >= 3:
            pygame.draw.line(self.win, TEXT_COLOR, (x + 210, y - 150), (x + 168, y - 130), 5)
        if self.hangman >= 4:
            pygame.draw.line(self.win, TEXT_COLOR, (x + 210, y - 150), (x + 252, y - 130), 5)
        if self.hangman >= 5:
            pygame.draw.line(self.win, TEXT_COLOR, (x + 210, y - 95), (x + 178, y - 52), 5)
        if self.hangman >= 6:
            pygame.draw.line(self.win, TEXT_COLOR, (x + 210, y - 95), (x + 242, y - 52), 5)

    #Draws the menu for the user to pick from
    def draw_menu(self) -> None:
        self.win.fill(BG_COLOR)
        pygame.draw.rect(self.win, (255, 255, 255), (24, 24, WIDTH - 48, HEIGHT - 48), border_radius=32)
        pygame.draw.rect(self.win, (72, 215, 255), (24, 24, WIDTH - 48, HEIGHT - 48), 3, border_radius=32)
        max_w = WIDTH - 140
        title = self.title_font.render("HANGMAN", True, TEXT_COLOR)
        self.win.blit(title, (WIDTH / 2 - title.get_width() / 2, 135))

        badge = self.small_font.render("VOICE ARCADE MODE", True, BG_COLOR)
        badge_box = pygame.Rect(WIDTH / 2 - badge.get_width() / 2 - 16, 90, badge.get_width() + 32, 40)
        pygame.draw.rect(self.win, FOCUS_COLOR, badge_box, border_radius=20)
        self.win.blit(badge, (badge_box.x + 16, badge_box.y + 8))

        menu_line = "Hold SPACE and say start, or press ENTER to begin"
        text = self.word_font.render(self._fit_text(self.word_font, menu_line, max_w - 40), True, TEXT_COLOR)
        prompt_box = pygame.Rect(90, 260, WIDTH - 180, 96)
        pygame.draw.rect(self.win, (223, 238, 255), prompt_box, border_radius=24)
        pygame.draw.rect(self.win, ACCENT_COLOR, prompt_box, 3, border_radius=24)
        self.win.blit(text, (WIDTH / 2 - text.get_width() / 2, prompt_box.y + 26))

        #Handles user voice input
        mic_status = "Microphone: ON" if self.voice.available else "Microphone: OFF (keyboard mode)"
        while mic_status and self.small_font.size(mic_status)[0] > max_w:
            mic_status = mic_status[:-1]
        mic_color = ACCENT_COLOR if self.voice.available else WARNING_COLOR
        mic_text = self.small_font.render(mic_status, True, mic_color)
        self.win.blit(mic_text, (WIDTH / 2 - mic_text.get_width() / 2, 390))

        hint = self.small_font.render("ESC exits", True, MUTED_TEXT)
        self.win.blit(hint, (WIDTH / 2 - hint.get_width() / 2, 430))
        pygame.display.update()

    #Draws out the game
    def draw_game(self) -> None:
        self.win.fill(BG_COLOR)
        pygame.draw.rect(self.win, (255, 255, 255), (20, 20, WIDTH - 40, HEIGHT - 40), border_radius=32)
        pygame.draw.rect(self.win, (72, 215, 255), (20, 20, WIDTH - 40, HEIGHT - 40), 3, border_radius=32)

        title = self.title_font.render("HANGMAN", True, TEXT_COLOR)
        self.win.blit(title, (WIDTH / 2 - title.get_width() / 2, 28))

        top_bar = pygame.Rect(410, 110, WIDTH - 450, 110)
        pygame.draw.rect(self.win, (223, 238, 255), top_bar, border_radius=24)
        pygame.draw.rect(self.win, ACCENT_COLOR, top_bar, 3, border_radius=24)

        status_height = self._draw_wrapped_text(
            self.small_font,
            self.status_text,
            TEXT_COLOR,
            top_bar.x + 18,
            top_bar.y + 12,
            top_bar.width - 36,
            line_gap=4,
        )
        detail = self.small_font.render(f"Wrong guesses left: {6 - self.hangman}", True, MUTED_TEXT)
        self.win.blit(detail, (top_bar.x + 18, top_bar.y + 18 + status_height))

        word_area_x = 410
        word_area_w = WIDTH - 450
        slot_w = min(62, max(40, (word_area_w - 20) // max(1, len(self.word))))
        gap = 8
        total_w = len(self.word) * slot_w + (len(self.word) - 1) * gap
        start_x = word_area_x + max(0, (word_area_w - total_w) // 2)
        for index, letter in enumerate(self.word):
            x = start_x + index * (slot_w + gap)
            y = 255
            pygame.draw.rect(self.win, (223, 238, 255), (x, y, slot_w, 66), border_radius=16)
            pygame.draw.rect(self.win, (72, 215, 255), (x, y, slot_w, 66), 2, border_radius=16)
            shown = letter if letter in self.guessed else "_"
            text = self.word_font.render(shown, True, TEXT_COLOR)
            self.win.blit(text, (x + slot_w / 2 - text.get_width() / 2, y + 12))

        guessed_text = self.detail_text if self.detail_text else "Guess one letter at a time"
        guessed_box = pygame.Rect(410, 340, WIDTH - 450, 88)
        pygame.draw.rect(self.win, (235, 244, 255), guessed_box, border_radius=20)
        pygame.draw.rect(self.win, (72, 215, 255), guessed_box, 2, border_radius=20)
        self._draw_wrapped_text(
            self.small_font,
            guessed_text,
            MUTED_TEXT,
            guessed_box.x + 16,
            guessed_box.y + 14,
            guessed_box.width - 32,
            line_gap=4,
        )

        #Shows all the letters to choose from
        for i, letter in enumerate(self.letters):
            x, y, ltr, visible = letter
            if visible:
                if i == self.selected_index:
                    pygame.draw.circle(self.win, ACCENT_COLOR, (x, y), RADIUS + 6)
                    pygame.draw.circle(self.win, FOCUS_COLOR, (x, y), RADIUS + 6, 3)
                pygame.draw.circle(self.win, (223, 238, 255), (x, y), RADIUS)
                pygame.draw.circle(self.win, TEXT_COLOR, (x, y), RADIUS, 3)
                text_color = BG_COLOR if i == self.selected_index else TEXT_COLOR
                txt = self.font.render(ltr, True, text_color)
                self.win.blit(txt, (x - txt.get_width() / 2, y - txt.get_height() / 2))
            else:
                pygame.draw.circle(self.win, (235, 244, 255), (x, y), RADIUS)
                pygame.draw.circle(self.win, (138, 165, 199), (x, y), RADIUS, 2)
                txt = self.font.render(ltr, True, (138, 165, 199))
                self.win.blit(txt, (x - txt.get_width() / 2, y - txt.get_height() / 2))

        if self.voice.available and self.listening:
            listen_box = pygame.Rect(410, 440, 180, 34)
            pygame.draw.rect(self.win, FOCUS_COLOR, listen_box, border_radius=16)
            listening = self.small_font.render("Listening...", True, BG_COLOR)
            self.win.blit(listening, (listen_box.x + 16, listen_box.y + 4))

        if last_spoken:
            spoken_line = "Last: " + last_spoken
            spoken_box = pygame.Rect(600, 438, WIDTH - 640, 38)
            pygame.draw.rect(self.win, (235, 244, 255), spoken_box, border_radius=16)
            pygame.draw.rect(self.win, (138, 165, 199), spoken_box, 2, border_radius=16)
            last = self.small_font.render(self._fit_text(self.small_font, spoken_line, spoken_box.width - 24), True, MUTED_TEXT)
            self.win.blit(last, (spoken_box.x + 12, spoken_box.y + 6))

        hint = self.small_font.render("Left/Right move letters | Up/Down status | ENTER guesses | Hold SPACE to speak", True, MUTED_TEXT)
        hint_line = hint
        if hint.get_width() > WIDTH - 20:
            hint_text = "L/R letters | Up/Down status | ENTER guess | Hold SPACE"
            hint_line = self.small_font.render(hint_text, True, MUTED_TEXT)
        self.win.blit(hint_line, (WIDTH / 2 - hint_line.get_width() / 2, HEIGHT - 205))

        self.draw_hangman()
        pygame.display.update()

    #Tells the user the result of the game
    def draw_result(self) -> None:
        self.win.fill(BG_COLOR)
        pygame.draw.rect(self.win, (255, 255, 255), (24, 24, WIDTH - 48, HEIGHT - 48), border_radius=32)
        pygame.draw.rect(self.win, (72, 215, 255), (24, 24, WIDTH - 48, HEIGHT - 48), 3, border_radius=32)
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

        #Fits text onto screen
        while msg and self.title_font.size(msg)[0] > WIDTH - 40:
            msg = msg[:-1]
        result_color = FOCUS_COLOR if self.result == "win" else WARNING_COLOR
        text = self.title_font.render(msg, True, result_color)
        self.win.blit(text, (WIDTH / 2 - text.get_width() / 2, 250))

        #Fits text onto screen
        while sub_line and self.word_font.size(sub_line)[0] > WIDTH - 40:
            sub_line = sub_line[:-1]
        sub = self.word_font.render(sub_line, True, TEXT_COLOR)
        info_box = pygame.Rect(130, 360, WIDTH - 260, 90)
        pygame.draw.rect(self.win, (223, 238, 255), info_box, border_radius=24)
        pygame.draw.rect(self.win, ACCENT_COLOR, info_box, 3, border_radius=24)
        self.win.blit(sub, (WIDTH / 2 - sub.get_width() / 2, 387))

        pygame.display.update()

    #Runs the game
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

                #Listns for user input
                if self.voice.available:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE and not self.listening:
                        self.listening = True
                        self.status_text = "Listening..."
                        if self.snd_listen is not None:
                            self.snd_listen.play()
                        self.voice.listen_once()
                else:
                    if event.type == pygame.KEYDOWN and self.state == "playing" and event.key == pygame.K_SPACE:
                        letter = self.letters[self.selected_index]
                        if letter[3]:
                            self._process_letter_guess(letter[2])

                #Allows user to continue playing
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
           
            #Listens and handles user speech inpit
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

#Runs the game
if __name__ == "__main__":
    game = HangmanGame()
    game.run()
