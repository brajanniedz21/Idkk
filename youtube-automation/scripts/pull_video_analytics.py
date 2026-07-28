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
from youtube_auth import load_credentials, load_analytics_credentials  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")


def main():
    from googleapiclient.discovery import build

    creds = load_credentials()  # base scopes only — must never be allowed to fail publishing
    analytics_creds = load_analytics_credentials()  # separate, isolated — None if unusable
    has_analytics_scope = analytics_creds is not None

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
    daily_series = []
    if has_analytics_scope:
        yta = build("youtubeAnalytics", "v2", credentials=analytics_creds)
        try:
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
            print(f"Analytics API per-video query failed (non-fatal, falling back to Data API only): {e}", file=sys.stderr)

        # Channel-level day-by-day trend — real historical series (YouTube
        # retains this regardless of when it's queried, so no local
        # snapshot history is needed to plot a trend line).
        try:
            earliest_publish = min((e.get("published_at") for e in entries if e.get("published_at")), default=None)
            start_date = (earliest_publish or "2026-01-01")[:10]
            resp2 = yta.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                metrics="views,estimatedMinutesWatched",
                dimensions="day",
                sort="day",
            ).execute()
            headers2 = [h["name"] for h in resp2.get("columnHeaders", [])]
            for row in resp2.get("rows", []):
                rowd = dict(zip(headers2, row))
                daily_series.append({
                    "date": rowd["day"],
                    "views": rowd.get("views", 0),
                    "minutes_watched": rowd.get("estimatedMinutesWatched", 0),
                })
        except Exception as e:
            print(f"Analytics API daily-trend query failed (non-fatal): {e}", file=sys.stderr)

    # Traffic sources — where views actually come from (search, suggested,
    # external, etc.). Real API dimension, verified live 2026-07-28.
    traffic_sources = []
    if has_analytics_scope:
        try:
            resp3 = yta.reports().query(
                ids="channel==MINE",
                startDate="2020-01-01",
                endDate=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                metrics="views",
                dimensions="insightTrafficSourceType",
                sort="-views",
            ).execute()
            for r in resp3.get("rows", []):
                traffic_sources.append({"source": r[0], "views": r[1]})
        except Exception as e:
            print(f"Analytics API traffic-source query failed (non-fatal): {e}", file=sys.stderr)

    # Audience retention curve for the single most-viewed video — real
    # per-video retention data (% of the video elapsed vs. % of audience
    # still watching). Verified live 2026-07-28.
    retention_curve = None
    retention_video = None
    if has_analytics_scope and entries:
        try:
            top = max(entries, key=lambda e: int((stats_by_id.get(e["video_id"], {}) or {}).get("viewCount") or 0))
            resp4 = yta.reports().query(
                ids="channel==MINE",
                startDate="2020-01-01",
                endDate=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                metrics="audienceWatchRatio",
                dimensions="elapsedVideoTimeRatio",
                filters=f"video=={top['video_id']}",
                sort="elapsedVideoTimeRatio",
            ).execute()
            points = [{"elapsed": r[0], "ratio": r[1]} for r in resp4.get("rows", [])]
            if points:
                retention_curve = points
                retention_video = {"video_id": top["video_id"], "title": top.get("title", "—")}
        except Exception as e:
            print(f"Analytics API retention-curve query failed (non-fatal): {e}", file=sys.stderr)

    # Subscribers gained/lost — channel-level, all-time.
    subs_gained, subs_lost = None, None
    if has_analytics_scope:
        try:
            resp5 = yta.reports().query(
                ids="channel==MINE",
                startDate="2020-01-01",
                endDate=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                metrics="subscribersGained,subscribersLost",
            ).execute()
            if resp5.get("rows"):
                subs_gained, subs_lost = resp5["rows"][0]
        except Exception as e:
            print(f"Analytics API subscribers query failed (non-fatal): {e}", file=sys.stderr)

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
        "ctr_impressions_note": (
            "Impressions and click-through rate are NOT available here — they're exclusive to the "
            "YouTube Studio UI and aren't exposed by the public YouTube Analytics API at all (not a "
            "scope/permission issue, confirmed by a live 400 'Unknown identifier (impressions)' test "
            "2026-07-28). If you need exact CTR numbers, that means opening YouTube Studio directly; "
            "there's no API path to automate pulling it."
        ),
        "videos": videos,
        "daily_series": daily_series,
        "traffic_sources": traffic_sources,
        "retention_curve": retention_curve,
        "retention_video": retention_video,
        "subscribers_gained": subs_gained,
        "subscribers_lost": subs_lost,
    }
    with open(os.path.join(STATE, "video_analytics.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote state/video_analytics.json ({len(videos)} videos, analytics_scope={has_analytics_scope})")


if __name__ == "__main__":
    main()
