
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent / "utils")
)
from athena_client import run_athena_query


st.set_page_config(
    page_title="Wistia Video Analytics",
    page_icon="📊",
    layout="wide",
)

DB_GOLD = "wistia_analytics_gold_dev"
DB_SILVER = "wistia_analytics_silver_dev"


@st.cache_data(ttl=900, show_spinner="Loading Athena data...")
def load_data():
    # Event-level Silver data enables exact filtered KPIs.
    events = run_athena_query(
        f"""
        SELECT
            event_date,
            media_id,
            media_name,
            visitor_key,
            percent_viewed,
            country
        FROM {DB_SILVER}.viewing_events
        """
    )

    videos = run_athena_query(
        f"SELECT * FROM {DB_GOLD}.video_performance"
    )

    return events, videos


st.title("Wistia Video Analytics")
st.caption(
    "AWS S3 → Glue → Athena → Streamlit | "
    "Historical viewing data"
)

try:
    events, videos = load_data()
except Exception as exc:
    st.error(f"Unable to retrieve Athena data: {exc}")
    st.stop()

# Normalize data types.
events["event_date"] = pd.to_datetime(
    events["event_date"], errors="coerce"
)
events["percent_viewed"] = pd.to_numeric(
    events["percent_viewed"], errors="coerce"
)

events = events.dropna(subset=["event_date"])

if events.empty:
    st.warning("No viewing events were returned.")
    st.stop()

# Map media IDs to friendly names.
video_names = (
    videos[["media_id", "media_name"]]
    .drop_duplicates("media_id")
    .set_index("media_id")["media_name"]
    .to_dict()
)

# Sidebar filters.
with st.sidebar:
    st.header("Dashboard Filters")

    video_options = ["All Videos"] + sorted(
        events["media_id"].dropna().unique().tolist()
    )

    selected_video = st.selectbox(
        "Select Video",
        video_options,
        format_func=lambda v: (
            "All Videos"
            if v == "All Videos"
            else video_names.get(v, v)
        ),
    )

    min_date = events["event_date"].min().date()
    max_date = events["event_date"].max().date()

    selected_dates = st.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if st.button("Refresh Athena Data"):
        load_data.clear()
        st.rerun()

    st.caption("Athena cache: 15 minutes")

# Date picker may temporarily return only one date.
if len(selected_dates) != 2:
    st.info("Select both a start date and an end date.")
    st.stop()

start_date, end_date = selected_dates

# Apply filters locally.
filtered = events[
    events["event_date"].dt.date.between(
        start_date, end_date
    )
].copy()

if selected_video != "All Videos":
    filtered = filtered[
        filtered["media_id"] == selected_video
    ].copy()

st.caption(
    f"Showing {start_date} through {end_date} | "
    f"{'All Videos' if selected_video == 'All Videos' else video_names.get(selected_video, selected_video)}"
)

if filtered.empty:
    st.warning("No viewing events match these filters.")
    st.stop()

# Overview KPIs.
total_events = len(filtered)
unique_visitors = filtered["visitor_key"].nunique()
avg_viewed = filtered["percent_viewed"].mean() * 100
near_complete = (
    filtered["percent_viewed"] >= 0.90
).sum()

st.subheader("Overview")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Viewing Events", f"{total_events:,}")
k2.metric("Unique Visitors", f"{unique_visitors:,}")
k3.metric("Avg. Viewed", f"{avg_viewed:.2f}%")
k4.metric("Near-Complete Views", f"{near_complete:,}")

# Video performance.
st.subheader("Video Performance")

video_summary = (
    filtered.groupby("media_id", as_index=False)
    .agg(
        total_events=("media_id", "size"),
        unique_visitors=("visitor_key", "nunique"),
        avg_percent_viewed=("percent_viewed", "mean"),
    )
)

video_summary["avg_percent_viewed"] = (
    video_summary["avg_percent_viewed"] * 100
).round(2)

video_summary["media_name"] = (
    video_summary["media_id"]
    .map(video_names)
    .fillna(video_summary["media_id"])
)

fig_videos = px.bar(
    video_summary,
    x="media_name",
    y="total_events",
    color="media_name",
    title="Viewing Events by Video",
    labels={
        "media_name": "Video",
        "total_events": "Viewing Events",
    },
)
fig_videos.update_layout(showlegend=False)
st.plotly_chart(fig_videos, width="stretch")

st.dataframe(
    video_summary[
        [
            "media_name",
            "total_events",
            "unique_visitors",
            "avg_percent_viewed",
        ]
    ],
    width="stretch",
    hide_index=True,
)

# Daily trends.
st.subheader("Daily Viewing Trends")

daily = (
    filtered.groupby(
        ["event_date", "media_id"],
        as_index=False
    )
    .agg(total_events=("media_id", "size"))
)

daily["media_name"] = (
    daily["media_id"].map(video_names)
)

fig_daily = px.line(
    daily.sort_values("event_date"),
    x="event_date",
    y="total_events",
    color="media_name",
    markers=True,
    title="Daily Viewing Events by Video",
    labels={
        "event_date": "Date",
        "total_events": "Viewing Events",
        "media_name": "Video",
    },
)
st.plotly_chart(fig_daily, width="stretch")

# Geographic performance.
st.subheader("Geographic Performance")

geo = (
    filtered.groupby("country", dropna=False)
    .agg(
        total_events=("media_id", "size"),
        unique_visitors=("visitor_key", "nunique"),
    )
    .reset_index()
)

geo["country"] = geo["country"].fillna("Unknown")

fig_geo = px.bar(
    geo,
    x="country",
    y="total_events",
    title="Viewing Events by Country",
    labels={
        "country": "Country",
        "total_events": "Viewing Events",
    },
)
st.plotly_chart(fig_geo, width="stretch")

st.dataframe(
    geo,
    width="stretch",
    hide_index=True,
)

st.caption(
    "Near-complete = at least 90% viewed. "
    "KPIs are calculated from Silver event-level data. "
    "Data is historical, not live."
)
