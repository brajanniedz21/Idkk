#!/usr/bin/env python3
"""
Pull real channel-level totals (subscriber count, lifetime channel views,
video count) via youtube.channels().list(mine=true) — owner direction,
2026-08-02, after checking Composio's YouTube connection and finding these
numbers weren't shown anywhere on the dashboard despite the pipeline's own
base credentials (youtube_auth.load_credentials(), youtube.readonly scope)
already being able to pull them.

Usage:
    python3 pull_channel_stats.py
"""
import json
import os
from datetime import datetime, timezone

from googleapiclient.discovery import build

from youtube_auth import load_credentials

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")


def pull_channel_stats():
    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="statistics", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("channels().list(mine=True) returned no items — cannot resolve own channel stats")
    stats = items[0]["statistics"]
    return {
        "channel_id": items[0]["id"],
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "lifetime_view_count": int(stats.get("viewCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "hidden_subscriber_count": stats.get("hiddenSubscriberCount", False),
    }


def main():
    now = datetime.now(timezone.utc).isoformat()
    stats = pull_channel_stats()
    out = {
        "_comment": "Real channel-level totals (subscriber count, lifetime views, video count) via youtube.channels().list(mine=true) — see scripts/pull_channel_stats.py. Read by scripts/generate_dashboard.py.",
        "pulled_at": now,
        **stats,
    }
    with open(os.path.join(STATE, "channel_stats.json"), "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"wrote state/channel_stats.json (subscribers={stats['subscriber_count']}, lifetime_views={stats['lifetime_view_count']})")


if __name__ == "__main__":
    main()
