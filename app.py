import streamlit as st
import datetime
import os
from storage import get_storage, save_uploaded_photo
from analytics import render_analytics_tab

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

# Fetch check-in data
recent_entries = storage.get_recent_checkins(limit=50)
latest = storage.get_latest_checkin()

# Mobile tab navigation
tab_checkin, tab_analytics, tab_history = st.tabs(["✍️ Check-In", "📊 Analytics", "📋 History"])

# ==============================================================================
# TAB 1: Check-In Form
# ==============================================================================
with tab_checkin:
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

        # Mobile Photo Attachment Feature
        st.markdown("##### 📷 Attach a Photo *(Optional)*")
        photo_mode = st.radio(
            "Photo source:",
            options=["None", "📸 Camera Snapshot", "📁 Upload Image"],
            horizontal=True,
            label_visibility="collapsed",
        )
        photo_file = None
        if photo_mode == "📸 Camera Snapshot":
            photo_file = st.camera_input("Take a photo")
        elif photo_mode == "📁 Upload Image":
            photo_file = st.file_uploader("Upload photo", type=["jpg", "jpeg", "png"])

        submitted = st.form_submit_button("Save Check-in", use_container_width=True)

    if submitted:
        if not name.strip():
            st.warning("Please enter your name before submitting.")
        else:
            photo_path = save_uploaded_photo(photo_file) if photo_file else None
            success = storage.save_checkin(name=name, mood=mood, note=note, photo_path=photo_path)
            if success:
                st.session_state["just_submitted"] = True
                st.rerun()

    # Quick preview of latest submission
    if latest:
        with st.expander("👁️ View Latest Saved Check-In", expanded=False):
            st.markdown(f"**Name**: {latest.get('name')} | **Mood**: {latest.get('mood')}")
            if latest.get("note"):
                st.markdown(f"**Focus**: {latest.get('note')}")
            if latest.get("photo_path") and os.path.exists(latest["photo_path"]):
                st.image(latest["photo_path"], caption="Latest photo", use_container_width=True)


# ==============================================================================
# TAB 2: Analytics & Visualizations
# ==============================================================================
with tab_analytics:
    render_analytics_tab(recent_entries)


# ==============================================================================
# TAB 3: History Feed
# ==============================================================================
with tab_history:
    st.subheader(f"History ({len(recent_entries)} entries)")
    if not recent_entries:
        st.info("No check-ins recorded yet.")
    else:
        for entry in recent_entries:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"### {entry.get('name', 'Anonymous')}")
                    st.markdown(f"**Status**: {entry.get('mood', '')}")
                    if entry.get("note"):
                        st.caption(f"💭 {entry.get('note')}")
                with c2:
                    st.caption(f"🕒 {entry.get('created_at', '')}")

                # Display attached photo if present
                photo_path = entry.get("photo_path")
                if photo_path and os.path.exists(photo_path):
                    st.image(photo_path, caption="Photo check-in", use_container_width=True)
