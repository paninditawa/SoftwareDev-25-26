import streamlit as st
import subprocess
import sys
import os

def show_hangman():

    st.set_page_config(page_title="Hangman Game Launcher", layout="centered")

    st.title("🎮 Hangman Game")

    st.write("""
    This launcher starts the PyGame Hangman game.

    Features:
    - 
    """)
    GAME_PATH = os.path.join(os.path.dirname(__file__), "game_logic/hangman_game.py")
    if not os.path.exists(GAME_PATH):
        st.error(f"Could not find {GAME_PATH}. Make sure it exists.")
    else:
        if st.button("▶️ Launch Hangman Game"):
            st.write("Launching game...")
            subprocess.Popen([sys.executable, GAME_PATH])
if __name__ == "__main__":
    show_hangman()