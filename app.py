import streamlit as st
import datetime

st.set_page_config(page_title="My Mobile App", layout="centered")

st.title("📱 Daily Check-In")
st.caption(f"Today is {datetime.date.today().strftime('%A, %B %d, %Y')}")

with st.form("checkin_form"):
    name = st.text_input("Your Name", value="Explorer")
    mood = st.select_slider("How are you feeling?", options=["😴 Tired", "🙂 Normal", "🔥 Energized", "🚀 Unstoppable"])
    note = st.text_area("Today's key focus or thought:", placeholder="Type here...")
    submitted = st.form_submit_button("Save Check-in")

if submitted:
    st.success(f"Entry recorded for {name}! Status: {mood}")
    if note:
        st.info(f"Focus: {note}")
    st.balloons()
