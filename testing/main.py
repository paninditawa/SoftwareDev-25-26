import streamlit as st
import page1
import page2
import home
import c4_app

st.title("Accessible Game Space")

st.badge(label= "I LOVE THIS SPACE!", color = "red", width = 2100)

# Initialize navigation state
if "page" not in st.session_state:
    st.session_state.page = "home"

st.sidebar.title("Navigation")

if st.sidebar.button("Home"):
    st.session_state.page = "home"

if st.sidebar.button("Page 1"):
    st.session_state.page = "page1"

if st.sidebar.button("Page 2"):
    st.session_state.page = "page2"

if st.sidebar.button("Connect 4"):
    st.session_state.page = "c4"

if st.session_state.page == "home":
    home.show_home()

elif st.session_state.page == "page1":
    page1.show_page1()

elif st.session_state.page == "page2":
    page2.page2()

elif st.session_state.page == "c4":
    c4_app.show_c4()