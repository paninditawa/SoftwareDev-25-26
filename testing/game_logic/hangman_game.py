import pygame
import sys
import random
import time
import queue
import threading
from pathlib import Path
 
try:
    from tts import speak as _tts_speak, speak_interrupt as _tts_speak_interrupt
except ImportError:
    def _tts_speak(text):
        print(text)
    def _tts_speak_interrupt(text):
        print(text)
 
_sr_available = False
try:
    import speech_recognition as sr
    _sr_available = True
except ImportError:
    pass
 
_this_file = Path(__file__).resolve()
for _parent in _this_file.parents:
    if (_parent / "tts.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break
 
try:
    from tts import speak as _tts_speak
except ImportError:
    def _tts_speak(text: str):
        print(text)
 
WIDTH = 1000
HEIGHT = 700
FPS = 60
BG_COLOR = (248, 250, 252)
TEXT_COLOR = (16, 37, 63)
ACCENT_COLOR = (14, 92, 168)
WARNING_COLOR = (176, 83, 0)
MUTED_TEXT = (66, 85, 109)
RADIUS = 24
SPACE = 20
WORDS = ["SOFTWARE", "DEVELOPMENT", "TECHNOLOGY", "STUDENT", "ASSOCIATION", "UNITY", "COMMUNITY"]
 
 
def speak(text):
    _tts_speak(text)
 
 
def speak_block(text):
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
            from launcher.scoreboard import Scoreboard
            sb = Scoreboard.from_workspace(_repo_root)
            sb.record_win(user_id, username, "hangman")
        except Exception as exc:
            print(f"scoreboard write failed: {exc}")
 
    threading.Thread(target=_write, daemon=True).start()
 
 
def _extract_letter(text: str) -> str | None:
    text = text.upper().strip()
 
    spoken_names = {
        "AY": "A", "BEE": "B", "SEE": "C", "CEE": "C", "DEE": "D",
        "EE": "E", "EF": "F", "GEE": "G", "AITCH": "H", "EYE": "I",
        "JAY": "J", "KAY": "K", "EL": "L", "EM": "M", "EN": "N",
        "OH": "O", "PEE": "P", "CUE": "Q", "QUE": "Q", "AR": "R",
        "ESS": "S", "TEE": "T", "YOU": "U", "VEE": "V", "WEE": "W",
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
    if any(w in text for w in ["restart", "new game", "start over", "reset"]):
        return "restart"
    if any(w in text for w in ["quit", "exit", "close", "stop"]):
        return "quit"
    return None
 
 
class SpeechListener:
 
    def __init__(self, result_queue: queue.Queue):
        self.result_queue = result_queue
        self._stop_event = threading.Event()
        self._thread = None
        self.active = False
 
        if not _sr_available:
            print("[STT] speech_recognition not installed — voice input disabled.")
            return
 
        try:
            self.recognizer = sr.Recognizer()
            self.recognizer.pause_threshold = 0.6
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.mic = sr.Microphone()
 
            with self.mic as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
 
            self.active = True
        except Exception as e:
            print(f"[STT] Microphone init failed: {e}")
 
    def start(self):
        if not self.active:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
 
    def stop(self):
        self._stop_event.set()
 
    def _listen_loop(self):
        while not self._stop_event.is_set():
            try:
                with self.mic as source:
                    audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=4)
                text = self.recognizer.recognize_google(audio)
 
                command = _extract_command(text)
                if command:
                    self.result_queue.put(("command", command))
                    continue
 
                letter = _extract_letter(text)
                if letter:
                    self.result_queue.put(("letter", letter))
 
            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"[STT] Google STT error: {e}")
                time.sleep(2)
            except Exception as e:
                print(f"[STT] Unexpected error: {e}")
                time.sleep(1)
 
 
class HangmanGame:
 
    def __init__(self):
        pygame.init()
        self.win = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
        pygame.display.set_caption("Hangman")
        self.clock = pygame.time.Clock()
 
        self.font = pygame.font.SysFont(None, 48, bold=True)
        self.word_font = pygame.font.SysFont(None, 44, bold=True)
        self.title_font = pygame.font.SysFont(None, 74, bold=True)
        self.small_font = pygame.font.SysFont(None, 28, bold=True)
 
        self.state = "menu"
        self.letters = []
        self.selected_index = 0
        self.create_buttons()
 
        self._stt_queue: queue.Queue = queue.Queue()
        self._listener = SpeechListener(self._stt_queue)
 
        self.reset_game()
 
        welcome = (
            "Welcome to Hangman! "
            "Say a letter to guess it, or use the arrow keys and press Space or Enter. "
            "Say 'status' to hear your progress, 'restart' for a new game, or 'quit' to exit."
        )
        if self._listener.active:
            welcome += " Microphone is ready."
        else:
            welcome += " Note: microphone not available, using keyboard only."
        self.speak(welcome)
 
    def speak(self, text):
        speak(text)
 
    def speak_block(self, text):
        speak_block(text)
 
    def _elapsed_text(self):
        elapsed = max(0, int(time.time() - self.start_time))
        minutes, seconds = divmod(elapsed, 60)
        return f"{minutes} minutes and {seconds} seconds"
 
    def _speak_status(self):
        guessed_letters = ", ".join(sorted(self.guessed)) if self.guessed else "none yet"
        word_spoken = ", ".join(
            (l if l in self.guessed else "blank") for l in self.word
        )
        msg = (
            f"The word has {len(self.word)} letters. "
            f"So far: {word_spoken}. "
            f"You have {6 - self.hangman} wrong guesses remaining. "
            f"Letters guessed: {guessed_letters}."
        )
        self.speak(msg)
 
    def reset_game(self):
        self.word = random.choice(WORDS)
        self.guessed = []
        self.hangman = 0
        self.start_time = time.time()
        self.selected_index = 0
        for letter in self.letters:
            letter[3] = True
        self.speak_block(f"New game! The word has {len(self.word)} letters. Good luck!")
 
    def create_buttons(self):
        x_start = round((WIDTH - (RADIUS * 2 + SPACE) * 13) / 2)
        y_start = 540
        A = 65
        for i in range(26):
            x = x_start + SPACE * 2 + ((RADIUS * 2 + SPACE) * (i % 13))
            y = y_start + ((i // 13) * (SPACE + RADIUS * 2))
            self.letters.append([x, y, chr(A + i), True])
 
    def _process_letter_guess(self, ltr: str):
        match = next((l for l in self.letters if l[2] == ltr), None)
        if match is None:
            return
        if not match[3]:
            self.speak(f"{ltr} was already guessed.")
            return
 
        match[3] = False
        self.guessed.append(ltr)
 
        if ltr in self.word:
            count = self.word.count(ltr)
            plural = "time" if count == 1 else "times"
            self.speak(f"{ltr} is in the word, {count} {plural}!")
        else:
            self.hangman += 1
            remaining = 6 - self.hangman
            self.speak(f"{ltr} is not in the word. {remaining} wrong guesses remaining.")
 
    def check_game_over(self):
        won = all(letter in self.guessed for letter in self.word)
        if won:
            self.state = "result"
            self.result = "win"
            _report_win()
        elif self.hangman == 6:
            self.state = "result"
            self.result = "lose"
 
    def _drain_stt_queue(self):
        while not self._stt_queue.empty():
            try:
                kind, value = self._stt_queue.get_nowait()
            except queue.Empty:
                break
 
            if kind == "letter" and self.state == "playing":
                self._process_letter_guess(value)
            elif kind == "command":
                if value == "status" and self.state == "playing":
                    self._speak_status()
                elif value == "restart":
                    self.reset_game()
                    self.state = "playing"
                elif value == "quit":
                    self.speak("Goodbye!")
                    pygame.quit()
                    sys.exit()
 
    def handle_game_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
 
        if event.key == pygame.K_LEFT:
            for _ in range(26):
                self.selected_index = (self.selected_index - 1) % 26
                if self.letters[self.selected_index][3]:
                    break
            self.speak(self.letters[self.selected_index][2])
 
        elif event.key == pygame.K_RIGHT:
            for _ in range(26):
                self.selected_index = (self.selected_index + 1) % 26
                if self.letters[self.selected_index][3]:
                    break
            self.speak(self.letters[self.selected_index][2])
 
        elif event.key == pygame.K_UP:
            for _ in range(26):
                self.selected_index = (self.selected_index - 13) % 26
                if self.letters[self.selected_index][3]:
                    break
            self.speak(self.letters[self.selected_index][2])
 
        elif event.key == pygame.K_DOWN:
            for _ in range(26):
                self.selected_index = (self.selected_index + 13) % 26
                if self.letters[self.selected_index][3]:
                    break
            self.speak(self.letters[self.selected_index][2])
 
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            letter = self.letters[self.selected_index]
            if letter[3]:
                self._process_letter_guess(letter[2])
 
        elif pygame.K_a <= event.key <= pygame.K_z:
            ltr = chr(event.key - pygame.K_a + ord('A'))
            self._process_letter_guess(ltr)
 
        elif event.key == pygame.K_F1:
            self._speak_status()
 
    def draw_hangman(self):
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
 
    def draw_menu(self):
        self.win.fill(BG_COLOR)
        title = self.title_font.render("Hangman", 1, TEXT_COLOR)
        self.win.blit(title, (WIDTH / 2 - title.get_width() / 2, 200))
        text = self.word_font.render("Press SPACE or say 'start' to begin", 1, TEXT_COLOR)
        self.win.blit(text, (WIDTH / 2 - text.get_width() / 2, 350))
        mic_status = "Microphone: ON - voice + keyboard" if self._listener.active else "Microphone: OFF - keyboard only"
        mic_color = ACCENT_COLOR if self._listener.active else WARNING_COLOR
        mic_text = self.small_font.render(mic_status, 1, mic_color)
        self.win.blit(mic_text, (WIDTH / 2 - mic_text.get_width() / 2, 430))
        pygame.display.update()
 
    def draw_game(self):
        self.win.fill(BG_COLOR)
        title = self.title_font.render("Hangman", 1, TEXT_COLOR)
        self.win.blit(title, (WIDTH / 2 - title.get_width() / 2, 20))
 
        display_word = ""
        for letter in self.word:
            display_word += (letter + " ") if letter in self.guessed else "_ "
        text = self.word_font.render(display_word, 1, TEXT_COLOR)
        self.win.blit(text, (500, 250))
 
        for i, letter in enumerate(self.letters):
            x, y, ltr, visible = letter
            if visible:
                if i == self.selected_index:
                    pygame.draw.circle(self.win, ACCENT_COLOR, (x, y), RADIUS)
                pygame.draw.circle(self.win, TEXT_COLOR, (x, y), RADIUS, 3)
                text_color = BG_COLOR if i == self.selected_index else TEXT_COLOR
                txt = self.font.render(ltr, 1, text_color)
                self.win.blit(txt, (x - txt.get_width() / 2, y - txt.get_height() / 2))
 
        if self._listener.active:
            mic_surf = self.small_font.render("Listening... microphone on", 1, ACCENT_COLOR)
            self.win.blit(mic_surf, (10, HEIGHT - 30))
 
        hint = self.small_font.render("F1 = read status | Say 'status' anytime", 1, MUTED_TEXT)
        self.win.blit(hint, (WIDTH / 2 - hint.get_width() / 2, HEIGHT - 30))
 
        self.draw_hangman()
        pygame.display.update()
 
    def draw_result(self):
        self.win.fill(BG_COLOR)
        if self.result == "win":
            msg = "YOU WON!"
            self.speak(f"You won! It took you {self._elapsed_text()}")
        else:
            msg = f"YOU LOST! Word was {self.word}"
            self.speak(f"You lost. The word was {self.word}. It took you {self._elapsed_text()}. Say restart or press Space to play again.")
        text = self.title_font.render(msg, 1, TEXT_COLOR)
        self.win.blit(text, (WIDTH / 2 - text.get_width() / 2, 300))
        sub = self.word_font.render("Say 'restart' or press SPACE for new game", 1, TEXT_COLOR)
        self.win.blit(sub, (WIDTH / 2 - sub.get_width() / 2, 400))
        pygame.display.update()
 
    def run(self):
        self._listener.start()
 
        while True:
            self.clock.tick(FPS)
            self._drain_stt_queue()
 
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._listener.stop()
                    pygame.quit()
                    sys.exit()
 
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.speak("Exiting Hangman.")
                    self._listener.stop()
                    pygame.quit()
                    sys.exit()
 
                if self.state == "menu":
                    if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                        self.reset_game()
                        self.state = "playing"
                elif self.state == "playing":
                    self.handle_game_input(event)
                elif self.state == "result":
                    if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                        self.reset_game()
                        self.state = "playing"
            if self.state == "menu":
                self.draw_menu()
                while not self._stt_queue.empty():
                    try:
                        kind, value = self._stt_queue.get_nowait()
                        if kind == "command" and value == "restart":
                            self.reset_game()
                            self.state = "playing"
                    except queue.Empty:
                        break
            elif self.state == "playing":
                self.draw_game()
                self.check_game_over()
            elif self.state == "result":
                self.draw_result()
if __name__ == "__main__":
    game = HangmanGame()
    game.run()