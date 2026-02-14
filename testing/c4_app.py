import streamlit as st
import subprocess
import sys
import os

def show_c4():
    st.set_page_config(page_title="Connect 4 Launcher", layout="centered")

    st.title("🎮 Accessible Connect 4")

    st.write("""
    This is the launcher for the accessible Connect 4 game.

    Click the button below to start the PyGame version with:
    - Arrow key controls
    - Spacebar drop
    - Instant speech (TTS)
    - Blind-friendly column descriptions
    - Tutorial mode
    """)

    # Path to the PyGame file
    GAME_PATH = os.path.join(os.path.dirname(__file__), "connect4/c4_game.py")

    if not os.path.exists(GAME_PATH):
        st.error(f"Could not find {GAME_PATH}. Make sure it is in the same folder.")
    else:
        if st.button("▶️ Launch Connect 4"):
            st.write("Launching game…")
            subprocess.Popen([sys.executable, GAME_PATH])
