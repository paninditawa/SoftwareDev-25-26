# import Streamlit for UI
import streamlit as st

# import system utilities for subprocesses
import sys
import subprocess

# import Path for file path handling
from pathlib import Path

# import individual game modules
import maze_app
import madlibs_app
import home_page
import c4_app
import hangman

# Display main title of game space
st.title("HelloWorld - An Accessible Game Space")

# Initialize navigation state
if "page" not in st.session_state:
    st.session_state.page = "home_page"

# create sidebar nav. menu and update session state after button clicks to home or individual game page.
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

if st.sidebar.button("Apples to Apples"):
    st.session_state.page = "apples"

if st.sidebar.button("Battleship"):
    st.session_state.page = "battleship"

# load correct page based on session state and show content
if st.session_state.page == "home_page":
    home_page.show_home()

elif st.session_state.page == "maze_app":
    maze_app.show_maze()

elif st.session_state.page == "madlibs_app":
    madlibs_app.show_madlibs()

elif st.session_state.page == "c4":
    c4_app.show_c4()

elif st.session_state.page == "apples":
    st.write("### Apples to Apples")
    st.write("Use the sidebar fields and arrow keys to play. (Streamlit handles focus.)")
    apples_path = Path(__file__).resolve().parents[0] / "apples" / "apples_app.py"
    try:
        import runpy
        runpy.run_path(str(apples_path), run_name="__main__")
    except Exception as e:
        st.error(f"Failed to launch Apples to Apples: {e}")

elif st.session_state.page == "battleship":
    st.write("### Battleship")
    st.write("Start the local server, then launch the client. Use keyboard arrow keys and Enter.")

    battleship_dir = Path(__file__).resolve().parents[0] / "Battleship"
    server_path = battleship_dir / "server.py"
    client_path = battleship_dir / "client.py"

    def _find_free_port() -> int:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    server_proc = st.session_state.get("battleship_server")
    server_port = st.session_state.get("battleship_port")
    if server_proc and server_proc.poll() is None:
        st.success(f"Server is running on port {server_port}")
        if st.button("Stop server"):
            server_proc.terminate()
            st.session_state["battleship_server"] = None
            st.session_state["battleship_port"] = None
    else:
        if st.button("Start server"):
            port = _find_free_port()
            st.session_state["battleship_port"] = port
            st.session_state["battleship_server"] = subprocess.Popen(
                [sys.executable, str(server_path), "--port", str(port)]
            )

    if st.button("Launch client"):
        if server_proc and server_proc.poll() is None and server_port:
            subprocess.Popen(
                [sys.executable, str(client_path), "--port", str(server_port)]
            )
        else:
            st.error("Start the Battleship server first before launching the client.")

elif st.session_state.page == "hangman":
    hangman.show_hangman()
