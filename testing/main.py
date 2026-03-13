import streamlit as st
import sys
import maze_app
import madlibs_app
import home_page
import c4_app

st.title("Accessible Game Space")

# Initialize navigation state
if "page" not in st.session_state:
    st.session_state.page = "home_page"

st.sidebar.title("Navigation")

if st.sidebar.button("Home"):
    st.session_state.page = "home_page"

if st.sidebar.button("Hangman"):
    st.session_state.page = "hangman"

if st.sidebar.button("Maze Game"):
    st.session_state.page = "maze_app"

if st.sidebar.button("Mad Libs"):
    st.session_state.page = "madlibs_app"

if st.sidebar.button("Connect 4"):
    st.session_state.page = "c4"

# Optional TTS demo: attempts to import `tts` from the repo root and speak.
if st.sidebar.checkbox("Show TTS demo"):
    if st.sidebar.button("Play welcome TTS"):
        try:
            from pathlib import Path

            repo_root = str(Path(__file__).resolve().parents[1])
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)
            import tts

            tts.speak("Welcome to Accessible Game Space")
        except Exception as e:
            st.error(f"TTS demo failed: {e}")

if st.session_state.page == "home_page":
    home_page.show_home()

elif st.session_state.page == "maze_app":
    maze_app.show_maze()

elif st.session_state.page == "madlibs_app":
    madlibs_app.show_madlibs()

elif st.session_state.page == "c4":
    c4_app.show_c4()

elif st.session_state.page == "hangman":
    hangman.show_hangman()