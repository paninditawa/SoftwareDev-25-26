import pygame
import sys
import time
from pathlib import Path

# Ensure the project root containing `tts.py` is on sys.path.
_this_file = Path(__file__).resolve()
for _parent in _this_file.parents:
    if (_parent / "tts.py").exists():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

# Cross-platform TTS helper
try:
    from tts import speak as _tts_speak
except ImportError:
    def _tts_speak(text: str):
        print(text)

# =============================================
# CONFIG
# =============================================
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
FONT_SIZE = 30
TITLE_FONT_SIZE = 48
BG_COLOR = (248, 250, 252)
TEXT_COLOR = (16, 37, 63)
OPTION_COLOR = (14, 92, 168)
SELECTED_OPTION_COLOR = (176, 83, 0)
HIGHLIGHT_COLOR = (255, 191, 71)

# =============================================
# TTS (cross-platform)
# =============================================
# Uses the shared `tts` helper (Windows uses SAPI, macOS uses `say`, other platforms use pyttsx3).
# If TTS is not available, falls back to printing.

def speak(text):
    """Speak text (may be non-blocking depending on backend)."""
    _tts_speak(text)


def speak_block(text):
    """Speak text and wait (backend-dependent behavior)."""
    _tts_speak(text)

# =============================================
# MAD LIBS TEMPLATES
# =============================================
MADLIBS_STORIES = {
    "adventure": {
        "title": "The Magical Adventure",
        "prompts": [
            ("An adjective (e.g., happy, scary)", "adjective"),
            ("A noun (e.g., dragon, robot)", "noun"),
            ("A verb in present tense (e.g., runs, flies)", "verb"),
            ("An adjective", "adjective"),
            ("A plural noun (e.g., flowers, cars)", "noun_plural"),
            ("A number", "number"),
            ("An adverb (e.g., quickly, slowly)", "adverb"),
            ("A noun", "noun"),
            ("A verb", "verb"),
            ("An adjective", "adjective"),
        ],
        "story": """Once upon a time, a {0} {1} decided to {2}. 
The {3} {4} were glowing with {5} different colors. 
{6}, the {1} began to {7} across the {8} landscape.
Everything seemed {9} and magical."""
    },
    
    "school": {
        "title": "A Day at School",
        "prompts": [
            ("A noun (e.g., classroom, library)", "noun"),
            ("An adjective", "adjective"),
            ("A verb (e.g., dance, teach)", "verb"),
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
Everything became {8}, and we all cheered for the {9}."""
    },
    
    "animal": {
        "title": "The Unusual Animal",
        "prompts": [
            ("An animal (e.g., penguin, elephant)", "noun"),
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
Its {7} {8} made everyone laugh {9}."""
    }
}

# =============================================
# WORD OPTION BANKS
# =============================================
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

# =============================================
# GAME STATE & RENDERING
# =============================================
class MadLibsGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
        pygame.display.set_caption("Accessible Mad Libs Game")
        self.font = pygame.font.Font(None, FONT_SIZE)
        self.title_font = pygame.font.Font(None, TITLE_FONT_SIZE)
        self.clock = pygame.time.Clock()
        
        self.state = "menu"  # menu, story_select, playing, results
        self.current_story = None
        self.current_prompt_idx = 0
        self.user_words = []
        self.current_option_idx = 0
        
    def draw_text(self, text, font, color, x, y, max_width=None, centered=False):
        """Draw text with word wrapping"""
        if max_width is None:
            max_width = WINDOW_WIDTH - 40
        
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = " ".join(current_line + [word])
            text_surf = font.render(test_line, True, color)
            if text_surf.get_width() > max_width:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
            else:
                current_line.append(word)
        
        if current_line:
            lines.append(" ".join(current_line))
        
        for i, line in enumerate(lines):
            surf = font.render(line, True, color)
            rect = surf.get_rect()
            if centered:
                rect.centerx = WINDOW_WIDTH // 2
            else:
                rect.x = 20
            rect.y = y + (i * (FONT_SIZE + 10))
            self.screen.blit(surf, rect)
        
        return y + (len(lines) * (FONT_SIZE + 10))
    
    def draw_menu(self):
        """Draw story selection menu"""
        self.screen.fill(BG_COLOR)
        
        y = 50
        y = self.draw_text("Welcome to Mad Libs!", self.title_font, TEXT_COLOR, 20, y, centered=True)
        y += 20
        y = self.draw_text("An accessible word game where YOU provide the words!", self.font, TEXT_COLOR, 20, y)
        y += 40
        
        y = self.draw_text("Use arrow keys to select a story, then press SPACE to start.", self.font, TEXT_COLOR, 20, y)
        y += 30
        
        stories = list(MADLIBS_STORIES.keys())
        for i, story_key in enumerate(stories):
            story_data = MADLIBS_STORIES[story_key]
            color = SELECTED_OPTION_COLOR if i == self.current_option_idx else OPTION_COLOR
            y = self.draw_text(f"→ {i+1}. {story_data['title']}", self.font, color, 40, y)
            if i == self.current_option_idx:
                y = self.draw_text(f"   ({len(story_data['prompts'])} words to choose)", self.font, TEXT_COLOR, 60, y)
        
        y += 40
        y = self.draw_text("Press UP/DOWN arrows to navigate. Press SPACE to select.", self.font, TEXT_COLOR, 20, y)
        
        pygame.display.update()
    
    def draw_word_selection(self):
        """Draw word selection screen during gameplay"""
        self.screen.fill(BG_COLOR)
        
        y = 40
        y = self.draw_text(f"Mad Libs - Word {self.current_prompt_idx + 1} of {len(self.current_story['prompts'])}", 
                          self.title_font, TEXT_COLOR, 20, y)
        y += 30
        
        # Current prompt
        prompt_text = self.current_story["prompts"][self.current_prompt_idx][0]
        y = self.draw_text(f"Enter: {prompt_text}", self.font, OPTION_COLOR, 20, y)
        y += 30
        
        # Words already chosen
        if self.user_words:
            y = self.draw_text(f"Words so far: {', '.join(self.user_words)}", self.font, TEXT_COLOR, 20, y)
            y += 20
        
        # Options
        y = self.draw_text("Choose from suggestions:", self.font, TEXT_COLOR, 20, y)
        y += 20
        
        word_type = self.current_story["prompts"][self.current_prompt_idx][1]
        options = WORD_OPTIONS.get(word_type, ["word1", "word2"])
        
        for i, word in enumerate(options):
            color = SELECTED_OPTION_COLOR if i == self.current_option_idx else OPTION_COLOR
            prefix = "→ " if i == self.current_option_idx else "  "
            y = self.draw_text(f"{prefix}{i+1}. {word}", self.font, color, 40, y)
        
        y += 30
        y = self.draw_text("Use UP/DOWN to navigate, SPACE to select", self.font, TEXT_COLOR, 20, y)
        
        pygame.display.update()
    
    def draw_results(self, story_text):
        """Draw completed story"""
        self.screen.fill(BG_COLOR)
        
        y = 40
        y = self.draw_text("Your Mad Libs Story!", self.title_font, TEXT_COLOR, 20, y)
        y += 30
        
        y = self.draw_text(story_text, self.font, TEXT_COLOR, 20, y, max_width=WINDOW_WIDTH - 40)
        
        y += 40
        y = self.draw_text("Press SPACE to play again.", self.font, TEXT_COLOR, 20, y)
        
        pygame.display.update()
    
    def handle_menu_input(self, event):
        """Handle input on menu screen"""
        if event.type == pygame.KEYDOWN:
            stories = list(MADLIBS_STORIES.keys())
            
            if event.key == pygame.K_UP:
                self.current_option_idx = (self.current_option_idx - 1) % len(stories)
                story_title = MADLIBS_STORIES[stories[self.current_option_idx]]["title"]
                speak(story_title)
            
            elif event.key == pygame.K_DOWN:
                self.current_option_idx = (self.current_option_idx + 1) % len(stories)
                story_title = MADLIBS_STORIES[stories[self.current_option_idx]]["title"]
                speak(story_title)
            
            elif event.key == pygame.K_SPACE:
                self.current_story = MADLIBS_STORIES[stories[self.current_option_idx]]
                self.current_prompt_idx = 0
                self.user_words = []
                self.current_option_idx = 0
                self.state = "playing"

                speak_block(f"Starting {self.current_story['title']}. Let's begin!")
                self.announce_prompt()
    
    def announce_prompt(self):
        """Announce current prompt via TTS"""
        if self.current_prompt_idx < len(self.current_story["prompts"]):
            prompt_text = self.current_story["prompts"][self.current_prompt_idx][0]
            word_type = self.current_story["prompts"][self.current_prompt_idx][1]
            options = WORD_OPTIONS.get(word_type, ["option1", "option2"])
            
            msg = f"Word {self.current_prompt_idx + 1}: {prompt_text}. "
            msg += f"Options: {', '.join(options[:5])}. "
            msg += "Use arrow keys to navigate, spacebar to select."
            
            speak(msg)
    
    def handle_word_selection_input(self, event):
        """Handle input during word selection"""
        if event.type == pygame.KEYDOWN:
            word_type = self.current_story["prompts"][self.current_prompt_idx][1]
            options = WORD_OPTIONS.get(word_type, ["word1", "word2"])
            
            if event.key == pygame.K_UP:
                self.current_option_idx = (self.current_option_idx - 1) % len(options)
                speak(options[self.current_option_idx])
            
            elif event.key == pygame.K_DOWN:
                self.current_option_idx = (self.current_option_idx + 1) % len(options)
                speak(options[self.current_option_idx])
            
            elif event.key == pygame.K_SPACE:
                word = options[self.current_option_idx]
                self.user_words.append(word)
                speak(f"Selected: {word}")
                self.advance_to_next_word()
    
    def advance_to_next_word(self):
        """Move to next word or show results"""
        self.current_prompt_idx += 1
        self.current_option_idx = 0
        
        if self.current_prompt_idx >= len(self.current_story["prompts"]):
            # Story complete
            story_text = self.current_story["story"].format(*self.user_words)
            self.state = "results"
            speak_block("Your story is complete! Let me read it to you.")
            speak_block(story_text)
            speak("Press space to play again.")
            self.final_story_text = story_text
        else:
            self.announce_prompt()
    
    def handle_results_input(self, event):
        """Handle input on results screen"""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                self.state = "menu"
                self.current_option_idx = 0
                speak("Returning to menu. Select a story to play.")
    
    def run(self):
        """Main game loop"""
        speak_block("Welcome to Accessible Mad Libs! You will choose words to complete fun stories. "
                   "Use arrow keys to navigate, spacebar to select.")
        
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    speak("Exiting Mad Libs.")
                    pygame.quit()
                    sys.exit()
                
                if self.state == "menu":
                    self.handle_menu_input(event)
                elif self.state == "playing":
                    self.handle_word_selection_input(event)
                elif self.state == "results":
                    self.handle_results_input(event)
            
            # Draw appropriate screen
            if self.state == "menu":
                self.draw_menu()
            elif self.state == "playing":
                self.draw_word_selection()
            elif self.state == "results":
                self.draw_results(self.final_story_text)
            
            self.clock.tick(30)

# =============================================
# MAIN
# =============================================
if __name__ == "__main__":
    game = MadLibsGame()
    game.run()
