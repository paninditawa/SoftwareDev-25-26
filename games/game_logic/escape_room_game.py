"""Accessible Escape Room — fully voice-activated for blind players.

Hold SPACEBAR to speak a command. Release to submit.
"""

from __future__ import annotations

import pygame
import numpy as np
import sys
import time
import random
import threading
import queue
from pathlib import Path

#tts
_this_file = Path(__file__).resolve()
for _parent in _this_file.parents:
    if (_parent / "tts.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

try:
    from tts import speak as _tts_speak, speak_interrupt as _tts_speak_interrupt
except ImportError:
    def _tts_speak(text):
        print(text)
    def _tts_speak_interrupt(text):
        print(text)

_sr_available = False
try:
    import speech_recognition as sr  # pyright: ignore[reportMissingImports]
    _sr_available = True
except ImportError:
    pass

#audio tone
SAMPLE_RATE = 44100
SCREEN_W, SCREEN_H = 600, 400


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


def _tone(freq, dur=0.15, vol=0.4):
    frames = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, frames, endpoint=False)
    arr = np.sin(2 * np.pi * freq * t) * np.linspace(1.0, 0.0, frames)
    arr = (arr * vol * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack([arr, arr]))


def _chord(freqs, dur=0.4, vol=0.35):
    frames = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, frames, endpoint=False)
    arr = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    arr = arr * np.linspace(1.0, 0.0, frames)
    arr = (arr * vol * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack([arr, arr]))


last_spoken = ""


def speak(text, interrupt=False):
    global last_spoken
    last_spoken = text
    if interrupt:
        _tts_speak_interrupt(text)
    else:
        _tts_speak(text)

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
            from launcher.services.leaderboard import Scoreboard
            sb = Scoreboard.from_workspace(_repo_root)
            sb.record_win(user_id, username, "escape")
        except Exception as exc:
            print(f"scoreboard write failed: {exc}")
    threading.Thread(target=_write, daemon=True).start()

#the riddles

class Puzzle:
    def __init__(self, name, description, answer, hint, reward=None, choices=None):
        self.name = name
        self.description = description
        self.answer = answer.lower().strip()
        self.hint = hint
        self.reward = reward
        self.choices = choices or []
        self.solved = False

    def describe(self):
        msg = self.description
        if self.choices:
            msg += " Your options are: " + ", ".join(self.choices) + "."
        return msg

    def attempt(self, spoken):
        spoken = spoken.lower().strip()
        if self.answer in spoken:
            self.solved = True
            if self.reward:
                return True, "Correct! You found " + self.reward + "."
            return True, "Correct!"
        for c in self.choices:
            if c.lower() in spoken and c.lower() == self.answer:
                self.solved = True
                if self.reward:
                    return True, "Correct! You found " + self.reward + "."
                return True, "Correct!"
        return False, "That's not it. Say hint if you need help."


class SoundPuzzle(Puzzle):
    def __init__(self, name, description, count, hint, reward=None):
        super().__init__(name, description, str(count), hint, reward)
        self.count = count
        self.choices = []
        self._played = False

    def describe(self):
        return self.description + " Listen carefully and tell me how many you hear."

    def play_tones(self, snd):
        self._played = True
        for _ in range(self.count):
            snd.play()
            pygame.time.wait(500)

    def attempt(self, spoken):
        spoken = spoken.lower().strip()
        words = spoken.split()
        number_words = {
            "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
            "won": "1", "to": "2", "too": "2", "for": "4",
        }
        for w in words:
            check = number_words.get(w, w)
            if check == str(self.count):
                self.solved = True
                if self.reward:
                    return True, "That's right! You found " + self.reward + "."
                return True, "That's right!"
        return False, "Not quite. Say repeat to hear them again, or hint for help."


class SequencePuzzle(Puzzle):
    def __init__(self, name, description, sequence, hint, reward=None):
        super().__init__(name, description, "", hint, reward)
        self.sequence = [s.lower() for s in sequence]
        self.progress = 0

    def describe(self):
        if self.progress > 0:
            return str(self.progress) + " of " + str(len(self.sequence)) + " done. What's next?"
        return self.description

    def attempt(self, spoken):
        spoken = spoken.lower().strip()
        expected = self.sequence[self.progress]
        if expected in spoken:
            self.progress += 1
            if self.progress >= len(self.sequence):
                self.solved = True
                if self.reward:
                    return True, "Sequence complete! You found " + self.reward + "."
                return True, "Sequence complete!"
            return True, "Good. " + str(len(self.sequence) - self.progress) + " left. What's next?"
        self.progress = 0
        return False, "Wrong, starting over. " + self.description


#the room
class Room:
    def __init__(self, name, description, puzzles=None, connections=None, locked_by=None):
        self.name = name
        self.description = description
        self.puzzles = puzzles or []
        self.connections = connections or {}
        self.locked_by = locked_by
        self.visited = False

    def all_solved(self):
        return all(p.solved for p in self.puzzles) if self.puzzles else True

    def describe_full(self):
        msg = self.description
        unsolved = [p for p in self.puzzles if not p.solved]
        if unsolved:
            first = unsolved[0]
            msg += " " + first.describe()
            if len(unsolved) > 1:
                others = ", ".join(p.name for p in unsolved[1:])
                msg += " There's also: " + others + "."
        else:
            msg += " You've solved everything here."
        if self.connections:
            exits = list(self.connections.keys())
            msg += " You can go " + ", ".join(exits) + "."
        return msg


class Level:
    def __init__(self, name, intro, rooms, start_room, escape_room):
        self.name = name
        self.intro = intro
        self.rooms = rooms
        self.start_room = start_room
        self.escape_room = escape_room


def build_levels():
    levels = []

    #haunted library
    r = {}
    r["entrance"] = Room(
        "The Entrance Hall",
        "You're in a cold entrance hall. It smells like dust and old paper. There's a carved inscription on the door ahead.",
        puzzles=[
            Puzzle(
                "The Door Inscription",
                "The inscription reads: I have cities but no houses, forests but no trees, and water but no fish. What am I?",
                "map", "Think about something you'd look at to plan a journey.",
                reward="brass key",
                choices=["map", "painting", "globe", "book"],
            ),
        ],
        connections={"north": "reading room", "east": "closet"},
    )
    r["closet"] = Room(
        "The Storage Closet",
        "A tiny closet full of old scrolls. One scroll has the numbers 3, 1, 4 written on it. There's a locked chest.",
        puzzles=[
            Puzzle(
                "The Locked Chest",
                "The chest has a combination lock. The scroll says the first three digits of pi. What's the code?",
                "314", "Pi starts with 3.14.",
                reward="silver coin",
                choices=["314", "341", "413", "143"],
            ),
        ],
        connections={"west": "entrance"},
    )
    r["reading room"] = Room(
        "The Reading Room",
        "Tall bookshelves surround you. A ghostly voice echoes through the room.",
        puzzles=[
            Puzzle(
                "The Ghost's Riddle",
                "The ghost whispers: The more you take, the more you leave behind. What am I?",
                "footsteps", "Think about walking.",
                choices=["footsteps", "memories", "breaths", "shadows"],
            ),
            SoundPuzzle(
                "The Chiming Clock",
                "A grandfather clock starts chiming.",
                5, "Count each chime carefully.",
                reward="clock gear",
            ),
        ],
        connections={"south": "entrance", "north": "vault"},
    )
    r["vault"] = Room(
        "The Archive Vault",
        "Moonlight streams through a cracked ceiling. An ancient portal glows in front of you.",
        puzzles=[
            Puzzle(
                "The Portal",
                "The portal asks: What has hands but can't clap?",
                "clock", "It tells time.",
                choices=["clock", "statue", "puppet", "painting"],
            ),
        ],
        connections={"south": "reading room"},
        locked_by="brass key",
    )
    levels.append(Level("The Haunted Library",
        "You're trapped in an ancient library full of riddles and secrets. Find the portal in the Archive Vault to escape.",
        r, "entrance", "vault"))

    #sunken lab
    r = {}
    r["airlock"] = Room(
        "The Airlock",
        "You're inside a submarine's airlock. Water drips from the riveted walls.",
        puzzles=[
            SequencePuzzle(
                "The Pressure Valves",
                "To equalize pressure, turn the valves in order. The sign says: red, blue, green. Say each color one at a time.",
                ["red", "blue", "green"],
                "Follow the sign: red first, then blue, then green.",
                reward="oxygen tank",
            ),
        ],
        connections={"north": "lab", "east": "supply room"},
    )
    r["supply room"] = Room(
        "The Supply Room",
        "Shelves of chemicals and tools. A locked cabinet hums with electricity.",
        puzzles=[
            Puzzle(
                "The Chemical Puzzle",
                "The label reads: I'm the element with atomic number 8, and I start with the letter O. What am I?",
                "oxygen", "It's what you breathe.",
                choices=["oxygen", "osmium", "oganesson", "gold"],
                reward="power cell",
            ),
        ],
        connections={"west": "airlock"},
    )
    r["lab"] = Room(
        "The Main Laboratory",
        "Monitors flicker around you. A central console needs power.",
        puzzles=[
            Puzzle(
                "The Console Override",
                "The console needs a code. A sticky note says: the year the Titanic sank.",
                "1912", "The Titanic sank in 1912.",
                reward="escape pod key",
                choices=["1912", "1905", "1920", "1898"],
            ),
            Puzzle(
                "The Sonar Riddle",
                "The sonar system asks: I travel faster through water than air, and I can't exist in a vacuum. What am I?",
                "sound", "Think about what sonar uses.",
                choices=["sound", "light", "radio", "electricity"],
            ),
        ],
        connections={"south": "airlock", "north": "escape pod"},
    )
    r["escape pod"] = Room(
        "The Escape Pod Bay",
        "Three escape pods line the wall. Only one works. Insert the key and you're free!",
        puzzles=[
            Puzzle(
                "The Final Hatch",
                "The hatch asks: What gets wetter the more it dries?",
                "towel", "You use it after a shower.",
                choices=["towel", "sponge", "paper", "cloth"],
            ),
        ],
        connections={"south": "lab"},
        locked_by="escape pod key",
    )
    levels.append(Level("The Sunken Laboratory",
        "You're trapped in an underwater research station that's losing power. Reach the escape pod before the station floods!",
        r, "airlock", "escape pod"))

    #space station
    r = {}
    r["docking bay"] = Room(
        "The Docking Bay",
        "You float in zero gravity inside a damaged space station. Red warning lights flash around you.",
        puzzles=[
            SoundPuzzle(
                "The Alarm Code",
                "The alarm is beeping in a pattern.",
                7, "Count each individual beep.",
                reward="security badge",
            ),
        ],
        connections={"east": "life support", "north": "bridge"},
    )
    r["life support"] = Room(
        "Life Support",
        "Oxygen recyclers hum around you. A cracked display shows a problem.",
        puzzles=[
            Puzzle(
                "The Oxygen Math",
                "You have 3 tanks, each lasting 4 hours. You need 10 hours total. How many more hours of oxygen do you need?",
                "2", "3 times 4 is 12. 12 minus 10 is what?",
                reward="repair kit",
                choices=["2", "4", "1", "3"],
            ),
            SequencePuzzle(
                "The Filter Sequence",
                "Replace the air filters in order. The manual says: carbon, then hepa, then UV. Say each one.",
                ["carbon", "hepa", "uv"],
                "Carbon first, hepa second, UV last.",
                reward="master key card",
            ),
        ],
        connections={"west": "docking bay"},
    )
    r["bridge"] = Room(
        "The Bridge",
        "The command bridge. Stars fill the viewport ahead of you.",
        puzzles=[
            Puzzle(
                "The Captain's Riddle",
                "The captain's log asks: I'm not alive, but I grow. I don't have lungs, but I need air. Water kills me. What am I?",
                "fire", "Think about something dangerous on a space station.",
                choices=["fire", "rust", "mold", "virus"],
                reward="ignition key",
            ),
        ],
        connections={"south": "docking bay", "west": "shuttle bay"},
    )
    r["shuttle bay"] = Room(
        "The Shuttle Bay",
        "An emergency shuttle waits. Insert the ignition key and solve the final challenge to escape!",
        puzzles=[
            Puzzle(
                "The Launch Code",
                "The shuttle computer asks: What force keeps you on Earth but doesn't exist in this station?",
                "gravity", "You're floating because there's no...",
                choices=["gravity", "magnetism", "friction", "pressure"],
            ),
        ],
        connections={"east": "bridge"},
        locked_by="ignition key",
    )
    levels.append(Level("The Space Station",
        "A catastrophic failure has left you stranded on an orbital station. Reach the emergency shuttle before life support fails!",
        r, "docking bay", "shuttle bay"))

    return levels


#listens to voice commands.
class VoiceListener:
    def __init__(self):
        self.result_queue = queue.Queue()
        self._recognizer = None
        self._mic = None
        if _sr_available:
            self._recognizer = sr.Recognizer()
            try:
                self._mic = sr.Microphone()
                with self._mic as source:
                    self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
            except Exception:
                self._mic = None

    @property
    def available(self):
        return self._recognizer is not None and self._mic is not None

    def listen_once(self):
        if not self.available:
            self.result_queue.put("")
            return
        def _work():
            try:
                with self._mic as source:
                    audio = self._recognizer.listen(source, timeout=5, phrase_time_limit=8)
                text = self._recognizer.recognize_google(audio)
                self.result_queue.put(text.lower().strip())
            except Exception:
                self.result_queue.put("")
        threading.Thread(target=_work, daemon=True).start()

    def get_result(self):
        try:
            return self.result_queue.get_nowait()
        except queue.Empty:
            return None


class EscapeRoomGame:
    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
        global SCREEN_W, SCREEN_H
        SCREEN_W, SCREEN_H = _recommended_window_size(SCREEN_W, SCREEN_H)
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Escape Room")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoeui", 36, bold=False)
        self.small_font = pygame.font.SysFont("segoeui", 26, bold=False)

        self.snd_good = _chord([523, 659, 784], 0.35)
        self.snd_bad = _tone(200, 0.3)
        self.snd_move = _tone(440, 0.08)
        self.snd_beep = _tone(600, 0.15)
        self.snd_unlock = _chord([440, 554, 659, 880], 0.5)
        self.snd_win = _chord([523, 659, 784, 1047], 0.6, 0.5)
        self.snd_listen = _tone(880, 0.06, 0.3)

        self.voice = VoiceListener()
        self.keyboard_mode = not self.voice.available
        self.levels = build_levels()
        self.state = "menu"
        self.current_level = None
        self.current_room = None
        self.inventory = []
        self.completed = set()
        self.listening = False
        self.command_buffer = ""
        self.status_text = "Type a command and press ENTER" if self.keyboard_mode else "Hold SPACEBAR to speak"

    def _fit_text(self, text, font, max_width):
        if font.size(text)[0] <= max_width:
            return text
        trimmed = text
        while trimmed and font.size(trimmed + "...")[0] > max_width:
            trimmed = trimmed[:-1]
        return (trimmed + "...") if trimmed else "..."

    def draw(self):
        self.screen.fill((14, 20, 28))
        w = self.screen.get_width()
        h = self.screen.get_height()
        status = self._fit_text(self.status_text, self.font, w - 40)
        surf = self.font.render(status, True, (242, 246, 252))
        self.screen.blit(surf, (w // 2 - surf.get_width() // 2, h // 2 - 40))

        if self.keyboard_mode:
            typed = self.command_buffer[-48:] if self.command_buffer else ""
            prompt_line = self._fit_text("Type command + ENTER: " + typed, self.small_font, w - 40)
            prompt = self.small_font.render(prompt_line, True, (214, 224, 236))
            self.screen.blit(prompt, (w // 2 - prompt.get_width() // 2, h // 2 + 8))

        if self.listening:
            pygame.draw.circle(self.screen, (255, 191, 71), (w // 2, h // 2 + 30), 14)
            pygame.draw.circle(self.screen, (14, 20, 28), (w // 2, h // 2 + 30), 14, 3)
            s = self.small_font.render("Listening... hold space", True, (255, 191, 71))
            self.screen.blit(s, (w // 2 - s.get_width() // 2, h // 2 + 50))

        pygame.display.flip()

    def process_command(self, cmd):
        if not cmd:
            speak("I didn't catch that. Try again.", interrupt=True)
            return

        self.status_text = 'You said: "' + cmd[:50] + '"'

        if self.state == "menu":
            self._handle_menu(cmd)
        elif self.state == "level_select":
            self._handle_level_select(cmd)
        elif self.state == "playing":
            self._handle_playing(cmd)
        elif self.state == "victory":
            self._handle_victory(cmd)

    def _handle_menu(self, cmd):
        if any(w in cmd for w in ["start", "play", "begin", "go", "yes"]):
            self.state = "level_select"
            self._announce_levels()
        elif any(w in cmd for w in ["help", "instructions", "how", "what"]):
            speak(
                "This is a voice-activated escape room. "
                "Hold spacebar to speak, then let go. "
                "If voice is unavailable, type a command and press enter. "
                "You'll explore rooms, solve puzzles, and collect items to escape. "
                "Say things like: look around, go north, hint, inventory, or solve followed by your answer. "
                "Say start to begin."
            )
        elif any(w in cmd for w in ["quit", "exit", "bye"]):
            speak("Goodbye!")
            pygame.quit()
            sys.exit()
        else:
            speak("Say start to play, help for instructions, or quit to exit.")

    def _announce_levels(self):
        msg = "Choose a level. "
        for i, lv in enumerate(self.levels):
            done = " Already completed." if i in self.completed else ""
            msg += str(i + 1) + ", " + lv.name + "." + done + " "
        msg += "Say the number or name."
        speak(msg)

    def _handle_level_select(self, cmd):
        if any(w in cmd for w in ["back", "menu", "cancel"]):
            self.state = "menu"
            speak("Say start, help, or quit.")
            return

        picked = None
        for i, lv in enumerate(self.levels):
            if str(i + 1) in cmd:
                picked = i
                break
            words = lv.name.lower().split()
            for w in words:
                if len(w) > 3 and w in cmd:
                    picked = i
                    break
            if picked is not None:
                break

        num_words = {"one": 0, "first": 0, "two": 1, "second": 1, "three": 2, "third": 2}
        if picked is None:
            for word, idx in num_words.items():
                if word in cmd and idx < len(self.levels):
                    picked = idx
                    break

        if picked is not None:
            self._start_level(picked)
        else:
            speak("Say 1, 2, or 3, or the level name.")

    def _start_level(self, idx):
        self.current_level = self.levels[idx]
        self.inventory = []
        for room in self.current_level.rooms.values():
            room.visited = False
            for p in room.puzzles:
                p.solved = False
                if isinstance(p, SequencePuzzle):
                    p.progress = 0
                if isinstance(p, SoundPuzzle):
                    p._played = False
        self.state = "playing"
        speak(self.current_level.intro)
        time.sleep(0.3)
        self._enter_room(self.current_level.start_room)

    def _enter_room(self, room_key):
        room = self.current_level.rooms[room_key]

        if room.locked_by:
            has_key = any(room.locked_by.lower() in item.lower() for item in self.inventory)
            if not has_key:
                self.snd_bad.play()
                speak("It's locked. You need the " + room.locked_by + ".")
                return
            if not room.visited:
                self.snd_unlock.play()
                speak("You use the " + room.locked_by + " to unlock it.")
                time.sleep(0.3)

        self.current_room = room
        room.visited = True
        self.snd_move.play()
        speak(room.describe_full())

        #sound puzle tones
        unsolved = [p for p in room.puzzles if not p.solved]
        if unsolved and isinstance(unsolved[0], SoundPuzzle) and not unsolved[0]._played:
            pygame.time.wait(500)
            unsolved[0].play_tones(self.snd_beep)
            speak("How many was that?")

        if room_key == self.current_level.escape_room and room.all_solved():
            self._win()

    def _win(self):
        idx = self.levels.index(self.current_level)
        self.completed.add(idx)
        self.state = "victory"
        self.snd_win.play()
        _report_win()
        speak("You escaped " + self.current_level.name + "! Say continue for another level, or quit to exit.")

    def _handle_playing(self, cmd):
        room = self.current_room

        if any(w in cmd for w in ["look", "around", "where", "describe", "room"]):
            speak(room.describe_full())
            return

        if "help" in cmd:
            speak(
                "Say look around to hear the room. "
                "Go followed by a direction to move. "
                "Say a puzzle name to hear it. "
                "Say solve and your answer to try. "
                "Hint for a clue. Inventory for your items."
            )
            return

        if any(w in cmd for w in ["inventory", "items", "bag", "carrying"]):
            if self.inventory:
                speak("You have: " + ", ".join(self.inventory) + ".")
            else:
                speak("You're not carrying anything yet.")
            return

        for direction in ["north", "south", "east", "west"]:
            if direction in cmd:
                if direction in room.connections:
                    self._enter_room(room.connections[direction])
                else:
                    speak("You can't go " + direction + " from here.")
                return

        if "hint" in cmd:
            unsolved = [p for p in room.puzzles if not p.solved]
            if unsolved:
                speak(unsolved[0].hint)
            else:
                speak("Everything here is solved. Try another room.")
            return

        if any(w in cmd for w in ["repeat", "again", "replay"]):
            for p in room.puzzles:
                if isinstance(p, SoundPuzzle) and not p.solved:
                    speak("Here they are again.")
                    pygame.time.wait(500)
                    p.play_tones(self.snd_beep)
                    speak("How many was that?")
                    return
            speak("Nothing to repeat.")
            return

        for p in room.puzzles:
            if not p.solved:
                last_word = p.name.lower().split()[-1]
                if last_word in cmd:
                    speak(p.describe())
                    if isinstance(p, SoundPuzzle) and not p._played:
                        pygame.time.wait(500)
                        p.play_tones(self.snd_beep)
                        speak("How many was that?")
                    return

        if any(w in cmd for w in ["solve", "answer", "guess", "try"]):
            answer = cmd
            for w in ["solve", "answer", "guess", "try"]:
                answer = answer.replace(w, "").strip()
            self._try_solve(answer)
            return

        unsolved = [p for p in room.puzzles if not p.solved]
        if unsolved:
            self._try_solve(cmd)
            return

        speak("I'm not sure what you mean. Say help for commands.")

    def _try_solve(self, answer):
        room = self.current_room
        unsolved = [p for p in room.puzzles if not p.solved]
        if not unsolved:
            speak("Nothing left to solve here.")
            return

        for p in unsolved:
            correct, msg = p.attempt(answer)
            if correct:
                self.snd_good.play()
                speak(msg)
                if p.reward and p.reward not in self.inventory:
                    self.inventory.append(p.reward)
                if room.all_solved():
                    if self.current_level.rooms.get(self.current_level.escape_room) is room:
                        time.sleep(0.5)
                        self._win()
                    else:
                        exits = ", ".join(room.connections.keys())
                        speak("You solved everything in this room. You can go " + exits + ".")
                else:
                    #next puzzlee gets read
                    still_unsolved = [q for q in room.puzzles if not q.solved]
                    if still_unsolved:
                        nxt = still_unsolved[0]
                        speak("Next up: " + nxt.describe())
                        if isinstance(nxt, SoundPuzzle) and not nxt._played:
                            pygame.time.wait(500)
                            nxt.play_tones(self.snd_beep)
                            speak("How many was that?")
                return
            self.snd_bad.play()
            speak(msg)
            return

    def _handle_victory(self, cmd):
        if any(w in cmd for w in ["continue", "next", "more", "yes", "level"]):
            if len(self.completed) >= len(self.levels):
                speak("You beat every level! Say quit to exit or play again to restart.")
            else:
                self.state = "level_select"
                self._announce_levels()
        elif any(w in cmd for w in ["quit", "exit", "bye"]):
            speak("Thanks for playing!")
            pygame.quit()
            sys.exit()
        elif any(w in cmd for w in ["again", "restart"]):
            self.completed.clear()
            self.state = "level_select"
            self._announce_levels()
        else:
            speak("Say continue for another level, or quit to exit.")

    def run(self):
        time.sleep(0.5)

        if self.keyboard_mode:
            speak(
                "Welcome to the Escape Room. "
                "Voice commands are unavailable right now. "
                "You can still play by typing commands and pressing enter. "
                "Type start to begin, or help for instructions."
            )
            self.status_text = "Type a command and press ENTER"
        else:
            speak(
                "Welcome to the Escape Room. "
                "Hold the spacebar to speak, then let go. "
                "Say start to begin, or help for instructions."
            )
            self.status_text = "Hold SPACEBAR to speak"

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    speak("Exiting Escape Room.", interrupt=True)
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.KEYDOWN:
                    if self.keyboard_mode:
                        if event.key == pygame.K_RETURN:
                            typed = self.command_buffer.strip()
                            self.command_buffer = ""
                            if typed:
                                self.process_command(typed.lower())
                                self.status_text = "Type a command and press ENTER"
                        elif event.key == pygame.K_BACKSPACE:
                            self.command_buffer = self.command_buffer[:-1]
                        elif event.key == pygame.K_ESCAPE:
                            pygame.quit()
                            sys.exit()
                        elif event.unicode and event.unicode.isprintable():
                            self.command_buffer += event.unicode
                    elif event.key == pygame.K_SPACE and not self.listening:
                        self.listening = True
                        self.snd_listen.play()
                        self.status_text = "Listening..."
                        self.voice.listen_once()

            if self.listening:
                result = self.voice.get_result()
                if result is not None:
                    self.listening = False
                    if result:
                        self.process_command(result)
                    else:
                        speak("I didn't catch that. Hold spacebar and try again.", interrupt=True)
                    self.status_text = "Hold SPACEBAR to speak"

            self.draw()
            self.clock.tick(30)


if __name__ == "__main__":
    game = EscapeRoomGame()
    game.run()