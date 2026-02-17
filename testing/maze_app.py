import streamlit as st
import subprocess
import sys
import os

def show_maze():

    st.set_page_config(page_title="Maze Game Launcher", layout="centered")

    st.title("🎮 Maze Game")

    st.write("""
    This is the launcher for the accessible Maze Game.

    Click the button below to start the PyGame version with:
    - Arrow key controls
    - Spacebar
    - Instant speech (TTS)
    - Blind-friendly descriptions
    - Tutorial mode
    """)

    # Path to the PyGame file
    GAME_PATH = os.path.join(os.path.dirname(__file__), "game_logic/maze_game.py")

    if not os.path.exists(GAME_PATH):
        st.error(f"Could not find {GAME_PATH}. Make sure it is in the same folder.")
    else:
        if st.button("▶️ Launch Maze Game"):
            st.write("Launching game…")
            subprocess.Popen([sys.executable, GAME_PATH])