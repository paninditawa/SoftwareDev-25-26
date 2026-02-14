import streamlit as st
import subprocess
import sys
import os

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
GAME_FILE = "connect4_streamlit/game.py"

if not os.path.exists(GAME_FILE):
    st.error(f"Could not find {GAME_FILE}. Make sure it is in the same folder.")
else:
    if st.button("▶️ Launch Connect 4"):
        st.write("Launching game…")
        subprocess.Popen([sys.executable, GAME_FILE])
        st.success("Game launched! Check your desktop window.")