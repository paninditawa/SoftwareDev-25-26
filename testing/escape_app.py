import streamlit as st
import subprocess
import sys
import os


def show_escape_room():
    st.title("Accessible Escape Room")

    st.write("""
    An immersive, fully voice-navigable escape room adventure designed for 
    blind and visually impaired players.

    **Features:**
    - 3 themed levels: The Haunted Library, The Sunken Laboratory, The Space Station
    - Multiple interconnected rooms per level with unique puzzles
    - 5 puzzle types: riddles, sequences, sound counting, combination locks, direction mazes
    - Full text-to-speech narration of every action and description
    - Optional voice command support (say "go north", "hint", "inventory", etc.)
    - Audio tones for navigation feedback, success, failure, and unlocking
    - Keyboard-only controls: arrow keys, Enter, H for hints, I for inventory

    **Controls:**
    - Arrow keys / WASD — navigate menus and puzzle options
    - Enter / Space — confirm selection
    - H — hear a hint for the current puzzle
    - R — repeat room description (or replay tones)
    - I — check your inventory
    - N / E / W or Arrow keys — move between rooms
    - M — toggle voice commands (microphone)
    - Escape — go back / pause
    """)

    GAME_PATH = os.path.join(os.path.dirname(__file__), "game_logic", "escape_room_game.py")

    if not os.path.exists(GAME_PATH):
        st.error(f"Could not find {GAME_PATH}. Make sure it exists in game_logic/.")
    else:
        if st.button("▶️ Launch Escape Room"):
            st.write("Launching game…")
            subprocess.Popen([sys.executable, GAME_PATH])


if __name__ == "__main__":
    show_escape_room()