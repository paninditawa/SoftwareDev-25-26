import streamlit as st
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

if st.sidebar.button("Maze Game"):
    st.session_state.page = "maze_app"

if st.sidebar.button("Mad Libs"):
    st.session_state.page = "madlibs_app"

if st.sidebar.button("Connect 4"):
    st.session_state.page = "c4"

if st.session_state.page == "home_page":
    home_page.show_home()

elif st.session_state.page == "maze_app":
    maze_app.show_maze()

elif st.session_state.page == "madlibs_app":
    madlibs_app.show_madlibs()

elif st.session_state.page == "c4":
    c4_app.show_c4()