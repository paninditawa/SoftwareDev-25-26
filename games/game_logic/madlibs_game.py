"""
Voice-first Mad Libs game.

Controls:
- Hold SPACEBAR to speak a command.
- ESC closes the game.

This version mirrors the Escape Room interaction model:
state-driven voice commands, spoken prompts, and minimal keyboard input.
"""

from __future__ import annotations

import pygame
import numpy as np
import sys
import queue
import threading
import time
from pathlib import Path

# Ensure the project root containing `tts.py` is on sys.path.
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
    import speech_recognition as sr  # pyright: ignore[reportMissingImports]
    _sr_available = True
except ImportError:
    pass

# =============================================
# CONFIG
# =============================================
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
BG_COLOR = (248, 250, 252)
TEXT_COLOR = (16, 37, 63)
MUTED_TEXT = (39, 68, 95)
ACCENT_COLOR = (14, 92, 168)
FOCUS_COLOR = (255, 191, 71)
ERROR_COLOR = (176, 83, 0)
SAMPLE_RATE = 44100


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


def _tone(freq: float, dur: float = 0.12, vol: float = 0.35):
    frames = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, frames, endpoint=False)
    arr = np.sin(2 * np.pi * freq * t) * np.linspace(1.0, 0.0, frames)
    arr = (arr * vol * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack([arr, arr]))


def _chord(freqs: list[float], dur: float = 0.24, vol: float = 0.30):
    frames = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, frames, endpoint=False)
    arr = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    arr = arr * np.linspace(1.0, 0.0, frames)
    arr = (arr * vol * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack([arr, arr]))

# =============================================
# TTS
# =============================================
last_spoken = ""


def speak(text: str, interrupt: bool = False) -> None:
    global last_spoken
    last_spoken = text
    if interrupt:
        _tts_speak_interrupt(text)
    else:
        _tts_speak(text)


# =============================================
# MAD LIBS DATA
# =============================================
MADLIBS_STORIES = {
    "adventure": {
        "title": "The Magical Adventure",
        "prompts": [
            ("An adjective", "adjective"),
            ("A noun", "noun"),
            ("A verb in present tense", "verb"),
            ("An adjective", "adjective"),
            ("A plural noun", "noun_plural"),
            ("A number", "number"),
            ("An adverb", "adverb"),
            ("A noun", "noun"),
            ("A verb", "verb"),
            ("An adjective", "adjective"),
        ],
        "story": """Once upon a time, a {0} {1} decided to {2}.
The {3} {4} were glowing with {5} different colors.
{6}, the {1} began to {7} across the {8} landscape.
Everything seemed {9} and magical.""",
    },
    "school": {
        "title": "A Day at School",
        "prompts": [
            ("A noun", "noun"),
            ("An adjective", "adjective"),
            ("A verb", "verb"),
            ("A number", "number"),
            ("A noun", "noun"),
            ("An adjective", "adjective"),
            ("A verb in past tense", "verb_past"),
            ("A noun", "noun"),
            ("A funny adjective", "adjective"),
            ("A noun", "noun"),
        ],
        "story": """I walked into the {0} and saw something {1}.
My teacher started to {2} while {3} students watched.
The {4} on the desk was so {5}.
Suddenly, the principal {6} through the door holding a {7}.
Everything became {8}, and we all cheered for the {9}.""",
    },
    "animal": {
        "title": "The Unusual Animal",
        "prompts": [
            ("An animal", "noun"),
            ("A color", "color"),
            ("An adjective", "adjective"),
            ("A food", "noun"),
            ("A noun", "noun"),
            ("A verb", "verb"),
            ("A number", "number"),
            ("An adjective", "adjective"),
            ("A noun", "noun"),
            ("An adverb", "adverb"),
        ],
        "story": """A {0} with {1} fur was the most {2} creature.
It loved to eat {3} and sleep on {4}.
Every day it would {5} for {6} hours.
Its {7} {8} made everyone laugh {9}.""",
    },
}

WORD_OPTIONS = {
    "adjective": ["happy", "scary", "silly", "mysterious", "curious", "bold", "gentle", "wild"],
    "noun": ["dragon", "robot", "wizard", "forest", "castle", "treasure", "magic", "adventure"],
    "noun_plural": ["flowers", "cars", "books", "stars", "mountains", "islands", "crystals", "dreams"],
    "verb": ["runs", "flies", "dances", "sings", "jumps", "swims", "climbs", "explores"],
    "verb_past": ["ran", "flew", "danced", "sang", "jumped", "swam", "climbed", "explored"],
    "number": ["3", "7", "13", "42", "100", "1000", "2", "99"],
    "adverb": ["quickly", "slowly", "happily", "quietly", "loudly", "gently", "wildly", "carefully"],
    "color": ["red", "blue", "green", "purple", "golden", "silver", "rainbow", "midnight"],
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "first": 1,
    "second": 2,
    "third": 3,
}


class VoiceListener:
    def __init__(self):
        self.result_queue: queue.Queue[str] = queue.Queue()
        self._recognizer = None
        self._mic = None
        self.unavailable_reason = "SpeechRecognition is not installed in this environment."

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
                self.unavailable_reason = f"Microphone setup failed ({type(exc).__name__}): {exc}"

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


class VoiceMadLibsGame:
    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        global WINDOW_WIDTH, WINDOW_HEIGHT
        WINDOW_WIDTH, WINDOW_HEIGHT = _recommended_window_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Voice Mad Libs")

        self.title_font = pygame.font.SysFont("segoeui", 56, bold=False)
        self.text_font = pygame.font.SysFont("segoeui", 34, bold=False)
        self.small_font = pygame.font.SysFont("segoeui", 26, bold=False)
        self.clock = pygame.time.Clock()

        # escape-room style cue sounds
        self.snd_listen = _tone(880, 0.06, 0.25)
        self.snd_good = _chord([523, 659, 784], 0.22, 0.28)
        self.snd_bad = _tone(220, 0.16, 0.35)
        self.snd_win = _chord([523, 659, 784, 1047], 0.45, 0.32)

        self.voice = VoiceListener()
        self.listening = False
        self.state = "menu"  # menu, story_select, playing, results

        self.story_keys = list(MADLIBS_STORIES.keys())
        self.current_story_key: str | None = None
        self.current_prompt_idx = 0
        self.user_words: list[str] = []
        self.final_story_text = ""

        self.status_text = "Hold SPACEBAR to speak"
        self.detail_text = "Say start to begin"
        # Set to the pygame tick time after which we start watching for TTS silence
        # to speak the post-story options prompt.
        self._options_prompt_after: int = 0
        self._pending_options_prompt: bool = False

    def _draw_wrapped_center(self, text: str, font, color, center_y: int, max_width: int) -> int:
        words = text.split()
        lines: list[str] = []
        current = []
        for word in words:
            test = " ".join(current + [word])
            if font.size(test)[0] <= max_width:
                current.append(word)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [word]
        if current:
            lines.append(" ".join(current))

        line_h = font.get_height() + 6
        top = center_y - (len(lines) * line_h) // 2
        for i, line in enumerate(lines):
            surf = font.render(line, True, color)
            self.screen.blit(surf, (self.screen.get_width() // 2 - surf.get_width() // 2, top + i * line_h))
        return top + len(lines) * line_h

    def draw(self) -> None:
        self.screen.fill(BG_COLOR)
        screen_w = self.screen.get_width()
        max_w = max(420, screen_w - 80)

        title = self.title_font.render("Voice Mad Libs", True, TEXT_COLOR)
        self.screen.blit(title, (screen_w // 2 - title.get_width() // 2, 70))

        state_line = self.text_font.render(f"State: {self.state}", True, ACCENT_COLOR)
        self.screen.blit(state_line, (screen_w // 2 - state_line.get_width() // 2, 160))

        self._draw_wrapped_center(self.status_text, self.text_font, TEXT_COLOR, 255, max_w)

        self._draw_wrapped_center(self.detail_text, self.small_font, MUTED_TEXT, 330, max_w)

        if self.listening:
            pygame.draw.circle(self.screen, FOCUS_COLOR, (screen_w // 2, 430), 18)
            pygame.draw.circle(self.screen, BG_COLOR, (screen_w // 2, 430), 18, 3)
            listening = self.small_font.render("Listening...", True, FOCUS_COLOR)
            self.screen.blit(listening, (screen_w // 2 - listening.get_width() // 2, 465))

        if last_spoken:
            self._draw_wrapped_center("Last: " + last_spoken, self.small_font, MUTED_TEXT, self.screen.get_height() - 60, max_w)

        pygame.display.flip()

    def _story_title(self) -> str:
        if not self.current_story_key:
            return ""
        return MADLIBS_STORIES[self.current_story_key]["title"]

    def _announce_story_options(self) -> None:
        pieces = []
        for index, key in enumerate(self.story_keys, start=1):
            pieces.append(f"{index}: {MADLIBS_STORIES[key]['title']}")
        speak("Choose a story. " + ". ".join(pieces) + ". Say a number or story name.", interrupt=True)

    def _announce_current_prompt(self) -> None:
        story = MADLIBS_STORIES[self.current_story_key]
        prompt_text, word_type = story["prompts"][self.current_prompt_idx]
        options = WORD_OPTIONS.get(word_type, [])
        hint = ", ".join(options[:5]) if options else "any word you like"

        self.detail_text = f"Word {self.current_prompt_idx + 1}/{len(story['prompts'])}: {prompt_text}"
        speak(
            f"Word {self.current_prompt_idx + 1}. {prompt_text}. "
            f"Example options: {hint}. "
            "Say your word now. Say options to hear suggestions again.",
            interrupt=True,
        )

    def _select_story_from_command(self, cmd: str) -> str | None:
        for i, key in enumerate(self.story_keys, start=1):
            if f"{i}" in cmd:
                return key

        for word, idx in NUMBER_WORDS.items():
            if word in cmd and 1 <= idx <= len(self.story_keys):
                return self.story_keys[idx - 1]

        for key in self.story_keys:
            title = MADLIBS_STORIES[key]["title"].lower()
            if key in cmd or title in cmd:
                return key
            for token in title.split():
                if len(token) > 3 and token in cmd:
                    return key

        return None

    def _extract_option_by_index(self, cmd: str, options: list[str]) -> str | None:
        for i in range(1, len(options) + 1):
            if f"option {i}" in cmd or f"number {i}" in cmd or f"{i}" == cmd.strip():
                return options[i - 1]
        for word, idx in NUMBER_WORDS.items():
            if word in cmd and 1 <= idx <= len(options):
                return options[idx - 1]
        return None

    def _advance_word(self) -> None:
        story = MADLIBS_STORIES[self.current_story_key]
        self.current_prompt_idx += 1

        if self.current_prompt_idx >= len(story["prompts"]):
            self.final_story_text = story["story"].format(*self.user_words)
            self.state = "results"
            self.status_text = "Story complete"
            self.detail_text = "Say read story, play again, or choose story"
            self.snd_win.play()
            speak("Your story is complete. Here it is.", interrupt=True)
            speak(self.final_story_text, interrupt=False)
            # Schedule the options prompt for after TTS goes quiet (gate: 1.5 s minimum).
            self._pending_options_prompt = True
            self._options_prompt_after = pygame.time.get_ticks() + 1500
            return

        self._announce_current_prompt()

    def process_command(self, cmd: str) -> None:
        if not cmd:
            self.snd_bad.play()
            speak("I did not catch that. Hold space and try again.", interrupt=True)
            self.status_text = "Try again"
            return

        self.status_text = f'You said: "{cmd[:40]}"'

        if self.state == "menu":
            self._handle_menu(cmd)
        elif self.state == "story_select":
            self._handle_story_select(cmd)
        elif self.state == "playing":
            self._handle_playing(cmd)
        elif self.state == "results":
            self._handle_results(cmd)

    def _handle_menu(self, cmd: str) -> None:
        if any(w in cmd for w in ["start", "play", "begin", "go"]):
            self.state = "story_select"
            self.detail_text = "Choose a story"
            self._announce_story_options()
            return

        if any(w in cmd for w in ["help", "instructions", "how"]):
            speak(
                "This is voice Mad Libs. Hold spacebar to speak. "
                "Say start, then choose a story by number or name. "
                "I will ask for one word at a time. You can say options, repeat, status, or your answer. "
                "Say quit anytime to exit.",
                interrupt=True,
            )
            return

        if any(w in cmd for w in ["quit", "exit", "bye"]):
            speak("Goodbye.", interrupt=True)
            pygame.quit()
            sys.exit()

        speak("Say start to begin, help for instructions, or quit to exit.", interrupt=True)

    def _handle_story_select(self, cmd: str) -> None:
        if any(w in cmd for w in ["back", "menu", "cancel"]):
            self.state = "menu"
            self.detail_text = "Say start to begin"
            speak("Back to menu. Say start to begin.", interrupt=True)
            return

        if "repeat" in cmd or "list" in cmd:
            self._announce_story_options()
            return

        selected = self._select_story_from_command(cmd)
        if selected is None:
            self.snd_bad.play()
            speak("I could not match that. Say story 1, 2, or 3, or say the story name.", interrupt=True)
            return

        self.current_story_key = selected
        self.current_prompt_idx = 0
        self.user_words = []
        self.state = "playing"
        self.detail_text = f"Playing {self._story_title()}"
        self.snd_good.play()
        speak(f"Starting {self._story_title()}.", interrupt=True)
        time.sleep(0.2)
        self._announce_current_prompt()

    def _handle_playing(self, cmd: str) -> None:
        story = MADLIBS_STORIES[self.current_story_key]
        prompt_text, word_type = story["prompts"][self.current_prompt_idx]
        options = WORD_OPTIONS.get(word_type, [])

        if any(w in cmd for w in ["quit", "exit", "bye"]):
            speak("Goodbye.", interrupt=True)
            pygame.quit()
            sys.exit()

        if any(w in cmd for w in ["status", "where am i", "progress"]):
            speak(
                f"You are on word {self.current_prompt_idx + 1} of {len(story['prompts'])}. "
                f"Prompt: {prompt_text}. "
                f"Words chosen: {', '.join(self.user_words) if self.user_words else 'none yet'}.",
                interrupt=True,
            )
            return

        if "help" in cmd:
            speak(
                "Say your answer word. "
                "Say options to hear suggestions, repeat to hear the prompt again, status for progress, or menu to choose a new story.",
                interrupt=True,
            )
            return

        if "menu" in cmd or "choose story" in cmd:
            self.state = "story_select"
            self.detail_text = "Choose a story"
            self._announce_story_options()
            return

        if "repeat" in cmd:
            self._announce_current_prompt()
            return

        if "options" in cmd or "suggest" in cmd:
            if options:
                speak("Options are: " + ", ".join(options) + ".", interrupt=True)
            else:
                speak("No preset options for this prompt. Say any word you like.", interrupt=True)
            return

        chosen = None
        if options:
            chosen = self._extract_option_by_index(cmd, options)
            if not chosen:
                for option in options:
                    if option.lower() in cmd:
                        chosen = option
                        break

        if not chosen:
            chosen = cmd.strip()

        if not chosen:
            self.snd_bad.play()
            speak("Please say a word.", interrupt=True)
            return

        self.user_words.append(chosen)
        self.snd_good.play()
        speak(f"Saved word {self.current_prompt_idx + 1}: {chosen}.", interrupt=True)
        self._advance_word()

    def _handle_results(self, cmd: str) -> None:
        if any(w in cmd for w in ["read", "story", "again", "repeat"]):
            speak(self.final_story_text, interrupt=True)
            # Re-schedule the options prompt for after the story finishes playing.
            self._pending_options_prompt = True
            self._options_prompt_after = pygame.time.get_ticks() + 1500
            return

        if "play again" in cmd or "restart" in cmd:
            self.current_prompt_idx = 0
            self.user_words = []
            self.state = "playing"
            speak(f"Restarting {self._story_title()}.", interrupt=True)
            self._announce_current_prompt()
            return

        if "choose" in cmd or "menu" in cmd or "different" in cmd:
            self.state = "story_select"
            self._announce_story_options()
            return

        if any(w in cmd for w in ["quit", "exit", "bye"]):
            speak("Goodbye.", interrupt=True)
            pygame.quit()
            sys.exit()

        self.snd_bad.play()
        speak("Say read story, play again, choose story, or quit.", interrupt=True)

    def run(self) -> None:
        if not self.voice.available:
            self.status_text = "Voice input unavailable"
            self.detail_text = self.voice.unavailable_reason or "Microphone unavailable for an unknown reason."
            speak(
                "Voice input is unavailable. "
                "This version uses spacebar and speech recognition only. "
                "Please install and enable SpeechRecognition and PyAudio, or check microphone permissions and the default input device, then restart.",
                interrupt=True,
            )

        else:
            speak(
                "Welcome to voice Mad Libs. "
                "Hold spacebar to speak commands. Say start to begin.",
                interrupt=True,
            )

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    speak("Exiting voice Mad Libs.", interrupt=True)
                    pygame.quit()
                    sys.exit()

                if not self.voice.available:
                    continue

                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE and not self.listening:
                    self.listening = True
                    self.status_text = "Listening..."
                    self.snd_listen.play()
                    self.voice.listen_once()

            if self.listening:
                result = self.voice.get_result()
                if result is not None:
                    self.listening = False
                    self.process_command(result)
                    self.status_text = "Hold SPACEBAR to speak"

            # Once the story TTS goes quiet, speak the post-story options.
            if (
                self._pending_options_prompt
                and pygame.time.get_ticks() >= self._options_prompt_after
                and not pygame.mixer.get_busy()
            ):
                self._pending_options_prompt = False
                speak(
                    "Say read story to hear it again, "
                    "play again to replay with new words, "
                    "choose story for a different one, or quit to exit.",
                    interrupt=False,
                )

            self.draw()
            self.clock.tick(30)


if __name__ == "__main__":
    game = VoiceMadLibsGame()
    game.run()
