import streamlit as st
import page1
import page2
import home

st.title("Accessible Game Space")

st.badge(label= "I LOVE THIS SPACE!", color = "red", width = 2100)

home_pressed = st.sidebar.button("Click me to go to the home page")

page1pressed = st.sidebar.button("Click me to go to page 1")

page2pressed = st.sidebar.button("Click me to go to page 2")

if home_pressed:
    home.show_home()
    home_pressed = False
elif page1pressed:
    page1.show_page1()
    page1pressed = False
elif page2pressed:
    page2.page2()
    page2pressed = False