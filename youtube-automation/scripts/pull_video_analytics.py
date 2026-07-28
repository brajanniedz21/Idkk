#!/usr/bin/env python3
"""Pull per-video stats for everything in state/posted_history.json and
write a structured snapshot to state/video_analytics.json for the daily
analytics cycle and the dashboard's Analytics tab.

Two data sources, queried independently since they run on different
pipelines with different lag characteristics:
  - Data API (videos.list part=statistics): views/likes/comments, updates
    close to real-time, works with the youtube.readonly scope.
  - Analytics API (youtubeAnalytics.reports().query): watch time, average
    view duration/percentage — needs the yt-analytics.readonly scope and
    has a known processing lag (can be empty for a day or two on a very
    new channel/video, which is normal, not a bug).

Usage:
    python3 scripts/pull_video_analytics.py
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from youtube_auth import load_credentials  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")


def main():
    from googleapiclient.discovery import build

    creds = load_credentials()
    has_analytics_scope = "https://www.googleapis.com/auth/yt-analytics.readonly" in creds.scopes

    posted = json.load(open(os.path.join(STATE, "posted_history.json")))
    entries = [{**v, "format": "short"} for v in posted.get("short_form", [])]
    entries += [{**v, "format": "long"} for v in posted.get("long_form", [])]

    if not entries:
        out = {
            "_comment": "Structured per-video stats, pulled daily. Consumed by the Analytics tab in dashboard/index.html (see scripts/generate_dashboard.py) and by agents/0_orchestrator.md's daily analytics cycle.",
            "pulled_at": datetime.now(timezone.utc).isoformat(),
            "has_analytics_scope": has_analytics_scope,
            "videos": [],
        }
        json.dump(out, open(os.path.join(STATE, "video_analytics.json"), "w"), indent=2)
        print("no posted videos yet; wrote empty snapshot")
        return

    yt = build("youtube", "v3", credentials=creds)
    ids = [e["video_id"] for e in entries]
    stats_by_id = {}
    for i in range(0, len(ids), 50):  # videos.list allows up to 50 ids per call
        chunk = ids[i : i + 50]
        resp = yt.videos().list(part="statistics", id=",".join(chunk)).execute()
        for item in resp.get("items", []):
            stats_by_id[item["id"]] = item["statistics"]

    analytics_by_id = {}
    if has_analytics_scope:
        try:
            yta = build("youtubeAnalytics", "v2", credentials=creds)
            resp = yta.reports().query(
                ids="channel==MINE",
                startDate="2020-01-01",
                endDate=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                metrics="views,estimatedMinutesWatched,averageViewDuration",
                dimensions="video",
                sort="-views",
                maxResults=200,
            ).execute()
            headers = [h["name"] for h in resp.get("columnHeaders", [])]
            for row in resp.get("rows", []):
                rowd = dict(zip(headers, row))
                analytics_by_id[rowd["video"]] = rowd
        except Exception as e:
            print(f"Analytics API query failed (non-fatal, falling back to Data API only): {e}", file=sys.stderr)

    videos = []
    for e in entries:
        vid = e["video_id"]
        st = stats_by_id.get(vid, {})
        an = analytics_by_id.get(vid, {})
        videos.append({
            "video_id": vid,
            "title": e.get("title", "—"),
            "format": e["format"],
            "url": e.get("url", f"https://youtu.be/{vid}"),
            "published_at": e.get("published_at"),
            "views": int(st.get("viewCount", 0)) if st.get("viewCount") is not None else None,
            "likes": int(st.get("likeCount", 0)) if st.get("likeCount") is not None else None,
            "comments": int(st.get("commentCount", 0)) if st.get("commentCount") is not None else None,
            "estimated_minutes_watched": an.get("estimatedMinutesWatched"),
            "avg_view_duration_sec": an.get("averageViewDuration"),
            "avg_view_percentage": an.get("averageViewPercentage"),
        })

    videos.sort(key=lambda v: v.get("published_at") or "", reverse=True)

    out = {
        "_comment": "Structured per-video stats, pulled daily. Consumed by the Analytics tab in dashboard/index.html (see scripts/generate_dashboard.py) and by agents/0_orchestrator.md's daily analytics cycle.",
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "has_analytics_scope": has_analytics_scope,
        "analytics_data_note": (
            "estimated_minutes_watched/avg_view_duration_sec/avg_view_percentage will be null until "
            "YouTube's Analytics reporting pipeline catches up (known lag, especially on a new channel "
            "— can be a day or two behind the public view counter). views/likes/comments are near-real-time."
        ) if has_analytics_scope else "yt-analytics.readonly scope not authorized — only Data API stats (views/likes/comments) available.",
        "videos": videos,
    }
    with open(os.path.join(STATE, "video_analytics.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote state/video_analytics.json ({len(videos)} videos, analytics_scope={has_analytics_scope})")


if __name__ == "__main__":
    main()
