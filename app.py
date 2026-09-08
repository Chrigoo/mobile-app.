import streamlit as st
import datetime
from storage import get_storage

st.set_page_config(page_title="My Mobile App", layout="centered", page_icon="📱")

storage = get_storage()

st.title("📱 Daily Check-In")
st.caption(f"Today is {datetime.date.today().strftime('%A, %B %d, %Y')}")

# Backend status banner
if storage.backend_name == "Local SQLite":
    st.info(
        "💾 **Local Storage Active** (entries saved to `checkins.db`). "
        "To sync with **Supabase** or **Google Sheets**, add credentials to `.streamlit/secrets.toml`.",
        icon="ℹ️",
    )
elif storage.backend_name == "Supabase":
    st.success("☁️ **Supabase Connected** — your check-ins are synced to Supabase!", icon="✅")
elif storage.backend_name == "Google Sheets":
    st.success("📊 **Google Sheets Connected** — your check-ins are synced to Google Sheets!", icon="✅")

# Handle post-submission celebration notification
if st.session_state.get("just_submitted"):
    st.success("🎉 Check-in saved successfully! Your inputs are preserved.")
    st.balloons()
    st.session_state["just_submitted"] = False

# Retrieve latest check-in to pre-populate inputs across page refreshes
latest = storage.get_latest_checkin()

reset_clicked = st.session_state.pop("reset_form", False)

if latest and not reset_clicked:
    default_name = latest.get("name", "Explorer")
    default_mood = latest.get("mood", "🙂 Normal")
    default_note = latest.get("note", "")
else:
    default_name = latest.get("name", "Explorer") if latest else "Explorer"
    default_mood = "🙂 Normal"
    default_note = ""

mood_options = ["😴 Tired", "🙂 Normal", "🔥 Energized", "🚀 Unstoppable"]
mood_index = mood_options.index(default_mood) if default_mood in mood_options else 1

header_col, reset_col = st.columns([3, 1])
with header_col:
    st.subheader("Your Check-In")
with reset_col:
    if st.button("🔄 Clear Form", help="Reset fields to enter a new record"):
        st.session_state["reset_form"] = True
        st.rerun()

with st.form("checkin_form"):
    name = st.text_input("Your Name", value=default_name)
    mood = st.select_slider(
        "How are you feeling?",
        options=mood_options,
        value=mood_options[mood_index],
    )
    note = st.text_area("Today's key focus or thought:", value=default_note, placeholder="Type here...")
    submitted = st.form_submit_button("Save Check-in", use_container_width=True)

if submitted:
    if not name.strip():
        st.warning("Please enter your name before submitting.")
    else:
        success = storage.save_checkin(name=name, mood=mood, note=note)
        if success:
            st.session_state["just_submitted"] = True
            st.rerun()

# Display check-in history
recent_entries = storage.get_recent_checkins(limit=15)
if recent_entries:
    st.divider()
    with st.expander(f"📋 Check-In History ({len(recent_entries)})", expanded=True):
        for entry in recent_entries:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"**{entry.get('name', 'Anonymous')}** — {entry.get('mood', '')}")
                    if entry.get("note"):
                        st.caption(f"💭 {entry.get('note')}")
                with c2:
                    st.caption(f"🕒 {entry.get('created_at', '')}")

