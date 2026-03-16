
import pygame
import sys
import random
import math
import time
from pathlib import Path

# import PyAudio as pyaudio
# import speech_recognition as sr

# # Initialize recognizer
# r = sr.Recognizer()

# # Use the default microphone as the audio source
# with sr.Microphone() as source:
#     print("Listening... please speak now.")
#     r.adjust_for_ambient_noise(source)  # Optional: reduce background noise
#     audio = r.listen(source)  # Capture the audio

# try:
#     # Recognize speech using Google Web Speech API
#     text = r.recognize_google(audio)
#     print("You said:", text)
# except sr.UnknownValueError:
#     print("Sorry, could not understand what you said.")
# except sr.RequestError as e:
#     print(f"Could not request results; check your internet connection. Error: {e}")


WIDTH = 1000
HEIGHT = 700
FPS = 60
BG_COLOR = (255,255,255)
TEXT_COLOR = (0,0,0)
RADIUS = 24
SPACE = 20
WORDS = ["HANNAH","ANINDITA","SIA","ANISHA","ZIXUAN","SOFTWARE","DEVELOPMENT"]

# Ensure the project root containing `tts.py` is on sys.path.
_this_file = Path(__file__).resolve()
for _parent in _this_file.parents:
    if (_parent / "tts.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

# Use TTS helper (cross-platform) for speech output
try:
    from tts import speak as _tts_speak
except ImportError:
    def _tts_speak(text: str):
        # Fallback: print to stdout if tts helper is not available
        print(text)

# --- Audio constants ---
SAMPLE_RATE = 44100
def speak(text):
    """Speak text (may be non-blocking depending on backend)."""
    _tts_speak(text)


def speak_block(text):
    """Speak text and wait (backend-dependent behavior)."""
    _tts_speak(text)

class HangmanGame:

    def __init__(self):

        pygame.init()

        self.win = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
        pygame.display.set_caption("Hangman")
        

        self.clock = pygame.time.Clock()

        self.font = pygame.font.SysFont("comicsans",45)
        self.word_font = pygame.font.SysFont("comicsans",40)
        self.title_font = pygame.font.SysFont("comicsans",70)

        self.state = "menu"

        self.letters = []
        self.selected_index = 0
        self.create_buttons()

        self.reset_game()
        self.speak("Welcome to Hangman! Your goal is to guess a word letter by letter. Start by saying any letter!")

    def speak(self, text):
        speak(text)

    def speak_block(self, text):
        speak_block(text)

    def _elapsed_text(self):
        elapsed = max(0, int(time.time() - self.start_time))
        minutes, seconds = divmod(elapsed, 60)
        return f"{minutes} minutes and {seconds} seconds"

    def reset_game(self):

        self.word = random.choice(WORDS)
        self.guessed = []
        self.hangman = 0
        self.start_time = time.time()
        self.selected_index = 0

        for letter in self.letters:
            letter[3] = True
        self.speak_block(f"The word has {len(self.word)} letters!")


    def create_buttons(self):

        x_start = round((WIDTH - (RADIUS*2 + SPACE)*13)/2)
        y_start = 540

        A = 65

        for i in range(26):

            x = x_start + SPACE*2 + ((RADIUS*2 + SPACE) * (i % 13))
            y = y_start + ((i // 13) * (SPACE + RADIUS*2))

            self.letters.append([x,y,chr(A+i),True])

    def draw_hangman(self):

        x = 150
        y = 450
        pygame.draw.line(self.win, TEXT_COLOR, (x, y), (x+200, y), 5)
        pygame.draw.line(self.win, TEXT_COLOR, (x+100, y), (x+100, y-300), 5)
        pygame.draw.line(self.win, TEXT_COLOR, (x+100, y-300), (x+200, y-300), 5)
        pygame.draw.line(self.win, TEXT_COLOR, (x+200, y-300), (x+200, y-250), 5)
        if self.hangman >= 1:  
            pygame.draw.circle(self.win, TEXT_COLOR, (x+200, y-220), 30, 3)
        if self.hangman >= 2:  
            pygame.draw.line(self.win, TEXT_COLOR, (x+200, y-190), (x+200, y-120), 3)
        if self.hangman >= 3: 
            pygame.draw.line(self.win, TEXT_COLOR, (x+200, y-170), (x+160, y-150), 3)
        if self.hangman >= 4: 
            pygame.draw.line(self.win, TEXT_COLOR, (x+200, y-170), (x+240, y-150), 3)
        if self.hangman >= 5:  
            pygame.draw.line(self.win, TEXT_COLOR, (x+200, y-120), (x+170, y-80), 3)
        if self.hangman >= 6:  
            pygame.draw.line(self.win, TEXT_COLOR, (x+200, y-120), (x+230, y-80), 3)

    def draw_menu(self):

        self.win.fill(BG_COLOR)

        title = self.title_font.render("Hangman",1,TEXT_COLOR)
        self.win.blit(title,(WIDTH/2 - title.get_width()/2,200))

        text = self.word_font.render("Press SPACE or ENTER to Start",1,TEXT_COLOR)
        self.win.blit(text,(WIDTH/2 - text.get_width()/2,350))

        pygame.display.update()


    def draw_game(self):

        self.win.fill(BG_COLOR)

        title = self.title_font.render("Hangman",1,TEXT_COLOR)
        self.win.blit(title,(WIDTH/2 - title.get_width()/2,20))

        display_word = ""

        for letter in self.word:

            if letter in self.guessed:
                display_word += letter + " "
            else:
                display_word += "_ "

        text = self.word_font.render(display_word,1,TEXT_COLOR)
        self.win.blit(text,(500,250))


        for i, letter in enumerate(self.letters):

            x,y,ltr,visible = letter

            if visible:

                if i == self.selected_index:
                    pygame.draw.circle(self.win, (255, 165, 0), (x,y), RADIUS)
                pygame.draw.circle(self.win, TEXT_COLOR, (x,y), RADIUS, 3)

                txt = self.font.render(ltr,1,TEXT_COLOR)

                self.win.blit(txt,(x - txt.get_width()/2,y - txt.get_height()/2))

        self.draw_hangman()

        pygame.display.update()

    def draw_result(self):

        self.win.fill(BG_COLOR)

        if self.result == "win":
            msg = "YOU WON!"
            self.speak(f"You won! It took you {self._elapsed_text()}")
        else:
            msg = f"YOU LOST! Word was {self.word}"
            self.speak(f"You lost. The word was {self.word}. It took you {self._elapsed_text()}")

        text = self.title_font.render(msg,1,TEXT_COLOR)

        self.win.blit(text,(WIDTH/2 - text.get_width()/2,350))

        pygame.display.update()

    def handle_game_input(self,event):

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
                letter[3] = False
                ltr = letter[2]
                self.guessed.append(ltr)
                if ltr in self.word:
                    self.speak(f"{ltr} is in the word!")
                else:
                    self.hangman += 1
                    self.speak(f"{ltr} is not in the word.")

    def check_game_over(self):

        won = True

        for letter in self.word:
            if letter not in self.guessed:
                won = False
                break

        if won:
            self.state = "result"
            self.result = "win"

        if self.hangman == 6:
            self.state = "result"
            self.result = "lose"


    def run(self):

        while True:

            self.clock.tick(FPS)

            for event in pygame.event.get():

                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.speak("Exiting Hangman.")
                    pygame.quit()
                    sys.exit()

                if self.state == "menu":

                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                        self.reset_game()
                        self.state = "playing"

                elif self.state == "playing":
                    self.handle_game_input(event)

                elif self.state == "result":

                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                        self.state = "menu"


            if self.state == "menu":
                self.draw_menu()

            elif self.state == "playing":
                self.draw_game()
                self.check_game_over()

            elif self.state == "result":
                self.draw_result()
if __name__ == "__main__":

    game = HangmanGame()
    game.run()
