"""
Analytics and visualization module for Daily Check-In application.
Computes metrics, streaks, weekly goals, and prepares chart datasets.
"""

from collections import Counter
import datetime
from typing import List, Dict, Any, Tuple
import pandas as pd
import altair as alt
import streamlit as st

MOOD_MAP = {
    "😴 Tired": 1,
    "🙂 Normal": 2,
    "🔥 Energized": 3,
    "🚀 Unstoppable": 4,
}

MOOD_COLORS = {
    "😴 Tired": "#718096",
    "🙂 Normal": "#4299E1",
    "🔥 Energized": "#ED8936",
    "🚀 Unstoppable": "#48BB78",
}


def parse_entry_date(created_at_str: str) -> datetime.date:
    """Parse a date from standard created_at string."""
    try:
        # Expected format: YYYY-MM-DD HH:MM:SS or ISO
        clean_str = created_at_str.split("T")[0].split(" ")[0]
        return datetime.datetime.strptime(clean_str, "%Y-%m-%d").date()
    except Exception:
        return datetime.date.today()


def compute_streak(entries: List[Dict[str, Any]]) -> int:
    """
    Calculate consecutive daily check-in streak ending today or yesterday.
    """
    if not entries:
        return 0

    dates = {parse_entry_date(e.get("created_at", "")) for e in entries if e.get("created_at")}
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    # Streak must be active either today or yesterday
    if today in dates:
        curr = today
    elif yesterday in dates:
        curr = yesterday
    else:
        return 0

    streak = 0
    while curr in dates:
        streak += 1
        curr -= datetime.timedelta(days=1)

    return streak


def compute_metrics(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute high-level summary metrics.
    """
    total = len(entries)
    if total == 0:
        return {
            "total": 0,
            "streak": 0,
            "top_mood": "None yet",
            "avg_energy": 0.0,
        }

    streak = compute_streak(entries)
    moods = [e.get("mood") for e in entries if e.get("mood")]
    most_common = Counter(moods).most_common(1)
    top_mood = most_common[0][0] if most_common else "🙂 Normal"

    scores = [MOOD_MAP.get(m, 2) for m in moods if m in MOOD_MAP]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return {
        "total": total,
        "streak": streak,
        "top_mood": top_mood,
        "avg_energy": round(avg_score, 1),
    }


def compute_weekly_progress(entries: List[Dict[str, Any]], goal_days: int = 7) -> Tuple[int, float]:
    """
    Calculate number of distinct check-in days in current week (Monday-Sunday)
    and progress ratio towards goal.
    """
    if not entries:
        return 0, 0.0

    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)

    dates = {parse_entry_date(e.get("created_at", "")) for e in entries if e.get("created_at")}
    days_this_week = sum(1 for d in dates if monday <= d <= sunday)
    ratio = min(days_this_week / goal_days, 1.0)
    return days_this_week, ratio


def render_analytics_tab(entries: List[Dict[str, Any]]):
    """
    Renders metrics, weekly goal progress bar, and interactive charts.
    """
    if not entries:
        st.info("📊 No check-in records found yet. Submit your first check-in to see analytics!", icon="ℹ️")
        return

    metrics = compute_metrics(entries)

    # 1. Summary Metric Cards
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Total Check-Ins", value=metrics["total"])
    with col2:
        st.metric(label="Day Streak", value=f"{metrics['streak']} 🔥" if metrics['streak'] > 0 else "0 days")
    with col3:
        st.metric(label="Top Mood", value=metrics["top_mood"])

    # 2. Weekly Goal Progress Bar
    days_this_week, progress_ratio = compute_weekly_progress(entries, goal_days=7)
    st.write("")
    st.write(f"🎯 **Weekly Goal**: **{days_this_week}/7** days completed this week")
    st.progress(progress_ratio)

    st.divider()

    # 3. Mood Distribution Bar Chart
    st.subheader("Mood Distribution")
    # Tally counts for all 4 predefined moods
    mood_counts = {m: 0 for m in MOOD_MAP}
    for e in entries:
        m = e.get("mood")
        if m in mood_counts:
            mood_counts[m] += 1

    dist_df = pd.DataFrame([
        {"Mood": m, "Count": c} for m, c in mood_counts.items()
    ])

    bar_chart = (
        alt.Chart(dist_df)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X("Mood:N", sort=list(MOOD_MAP.keys()), title="Mood"),
            y=alt.Y("Count:Q", title="Check-Ins", axis=alt.Axis(tickMinStep=1)),
            color=alt.Color("Mood:N", scale=alt.Scale(
                domain=list(MOOD_COLORS.keys()),
                range=list(MOOD_COLORS.values()),
            ), legend=None),
            tooltip=["Mood", "Count"],
        )
        .properties(height=240)
    )
    st.altair_chart(bar_chart, use_container_width=True)

    # 4. Energy Trend Over Time Line Chart
    st.subheader("Energy Trend Over Time")
    # Reverse to chronological order (oldest to newest)
    chronological = list(reversed(entries))
    trend_rows = []
    for e in chronological:
        created_at = e.get("created_at", "")
        mood = e.get("mood", "")
        if mood in MOOD_MAP:
            trend_rows.append({
                "Timestamp": created_at,
                "Energy Score": MOOD_MAP[mood],
                "Mood": mood,
                "Note": e.get("note", ""),
            })

    if trend_rows:
        trend_df = pd.DataFrame(trend_rows)
        line_chart = (
            alt.Chart(trend_df)
            .mark_line(point=True, color="#4299E1", strokeWidth=3)
            .encode(
                x=alt.X("Timestamp:N", title="Date & Time", sort=None),
                y=alt.Y(
                    "Energy Score:Q",
                    title="Energy Level",
                    scale=alt.Scale(domain=[1, 4]),
                    axis=alt.Axis(
                        values=[1, 2, 3, 4],
                        labelExpr="datum.value == 1 ? '😴 Tired' : datum.value == 2 ? '🙂 Normal' : datum.value == 3 ? '🔥 Energized' : '🚀 Unstoppable'"
                    ),
                ),
                tooltip=["Timestamp", "Mood", "Note"],
            )
            .properties(height=260)
        )
        st.altair_chart(line_chart, use_container_width=True)
    else:
        st.caption("Not enough entries for trend analysis yet.")

