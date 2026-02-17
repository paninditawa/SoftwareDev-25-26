import streamlit as st
import subprocess
import sys
import os

def show_madlibs():
    st.title("Mad Libs")
    st.write("Welcome to the Mad Libs section of the Accessible Game Space!")
    st.write("This page is dedicated to showcasing accessible games and reviews.")
    st.write("Discover a curated list of games that are designed with accessibility in mind, along with user reviews and ratings.")

    # Path to the PyGame file
    GAME_PATH = os.path.join(os.path.dirname(__file__), "game_logic/madlibs_game.py")

    if not os.path.exists(GAME_PATH):
        st.error(f"Could not find {GAME_PATH}. Make sure it is in the same folder.")
    else:
        if st.button("▶️ Launch Mad Libs"):
            st.write("Launching game…")
            subprocess.Popen([sys.executable, GAME_PATH])