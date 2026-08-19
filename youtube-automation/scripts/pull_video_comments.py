#!/usr/bin/env python3
"""
Pull real comment TEXT (not just the comment count Data API stats already
give us) for every published video in state/posted_history.json — owner
direction, 2026-08-02, after checking what Composio's YouTube connection
could see that this pipeline's own analytics pull couldn't: actual comment
content, which is what lets the daily analytics cycle tell a real organic
viewer reaction apart from the pipeline's own automated pinned funnel
comment (scripts/post_pinned_comment.py), and check whether the Shorts CTA
is actually working (are people typing "Luxury"?) instead of guessing from
a raw count.

Uses the same COMMENT_SCOPES credentials that already post pinned comments
(youtube_auth.load_comment_credentials()) — read access comes bundled with
that scope, no separate grant needed. Same graceful-degradation contract as
post_pinned_comment.py: if the scope isn't available, this writes a
has_comment_scope: false snapshot and exits 0, never blocking the rest of
the analytics cycle.

Usage:
    python3 pull_video_comments.py
"""
import json
import os
import sys
from datetime import datetime, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from youtube_auth import load_comment_credentials

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")

# The exact strings scripts/post_pinned_comment.py's build_funnel_text() can
# produce, past and present — used to identify the pipeline's own automated
# comment among a video's threads so it's never miscounted as organic
# engagement. Kept as a list (not just the current string) so old videos
# whose pinned comment used an earlier funnel-text version are still
# recognized correctly.
KNOWN_AUTOMATED_COMMENT_TEXTS = [
    "Manifest with ambience, full videos on my channel.",
]


def is_automated_comment(comment, channel_id):
    """True if this comment is the pipeline's own automated pinned funnel
    comment — matched by BOTH being authored by the channel itself AND
    matching a known automated text, not by author alone (the channel
    owner could plausibly leave a genuine reply some day, and text alone
    isn't enough since a real fan could theoretically type the same
    words)."""
    author_id = (comment.get("authorChannelId") or {}).get("value")
    text = comment.get("textOriginal", "")
    return author_id == channel_id and text.strip() in KNOWN_AUTOMATED_COMMENT_TEXTS


def pull_comments_for_video(youtube, video_id, channel_id):
    """All top-level comment threads for one video, classified into
    automated (the pipeline's own pinned comment) vs organic (everything
    else, including any real reply from the channel owner that isn't the
    known automated text). Returns None if comments are disabled/unavailable
    for this video (a real, valid state — not an error)."""
    try:
        resp = youtube.commentThreads().list(part="snippet", videoId=video_id, maxResults=100, order="time").execute()
    except HttpError as e:
        return {"error": f"comments unavailable: {e}", "comments": [], "automated_count": 0, "organic_count": 0, "organic_comments_mentioning_luxury": 0}

    comments = []
    automated_count = 0
    organic_count = 0
    luxury_mentions = 0
    for item in resp.get("items", []):
        snip = item["snippet"]["topLevelComment"]["snippet"]
        automated = is_automated_comment(snip, channel_id)
        text = snip.get("textOriginal", "")
        entry = {
            "comment_id": item["snippet"]["topLevelComment"]["id"],
            "author": snip.get("authorDisplayName"),
            "author_is_channel_owner": (snip.get("authorChannelId") or {}).get("value") == channel_id,
            "text": text,
            "like_count": snip.get("likeCount", 0),
            "published_at": snip.get("publishedAt"),
            "is_automated_pinned_comment": automated,
        }
        comments.append(entry)
        if automated:
            automated_count += 1
        else:
            organic_count += 1
            if "luxury" in text.lower():
                luxury_mentions += 1

    return {
        "comments": comments,
        "automated_count": automated_count,
        "organic_count": organic_count,
        "organic_comments_mentioning_luxury": luxury_mentions,
    }


def main():
    creds = load_comment_credentials()
    now = datetime.now(timezone.utc).isoformat()
    out_path = os.path.join(STATE, "video_comments.json")
    if creds is None:
        # Never clobber a real prior snapshot with an empty one just because
        # this run's credentials failed — real incident 2026-08-14: this branch
        # overwrote a 78-video real comment pull (has_comment_scope=true) with
        # an empty has_comment_scope=false file, destroying data a fresh pull
        # would have taken days to rebuild. Preserve the last real snapshot and
        # only annotate that this run couldn't refresh it.
        previous = {}
        if os.path.exists(out_path):
            try:
                with open(out_path) as f:
                    previous = json.load(f)
            except (json.JSONDecodeError, OSError):
                previous = {}
        if previous.get("has_comment_scope") and previous.get("videos"):
            out = dict(previous)
            out["last_refresh_attempt_failed_at"] = now
            out["last_refresh_attempt_note"] = (
                "youtube.force-ssl credentials unavailable this run — kept the last real "
                f"snapshot (pulled_at={previous.get('pulled_at')}) instead of overwriting it "
                "with an empty result."
            )
            print(
                f"credentials unavailable — preserved prior snapshot from {previous.get('pulled_at')} "
                f"({len(previous.get('videos', {}))} videos) instead of overwriting with empty data"
            )
        else:
            out = {
                "_comment": "Real comment TEXT (not just counts) for published videos, via youtube_auth.load_comment_credentials() — see scripts/pull_video_comments.py.",
                "pulled_at": now,
                "has_comment_scope": False,
                "note": "youtube.force-ssl credentials unavailable this run — same graceful-degradation contract as post_pinned_comment.py. Not a failure.",
                "videos": {},
            }
            print("wrote state/video_comments.json (has_comment_scope=False)")
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return

    youtube = build("youtube", "v3", credentials=creds)

    posted = json.load(open(os.path.join(STATE, "posted_history.json")))
    channel_id = None
    try:
        ch = youtube.channels().list(part="id", mine=True).execute()
        channel_id = ch["items"][0]["id"]
    except HttpError as e:
        print(f"Could not resolve own channel_id (non-fatal, automated-comment detection will be less precise): {e}", file=sys.stderr)

    videos = {}
    all_entries = posted.get("short_form", []) + posted.get("long_form", [])
    for entry in all_entries:
        vid = entry.get("video_id")
        if not vid:
            continue
        videos[vid] = pull_comments_for_video(youtube, vid, channel_id)

    out = {
        "_comment": "Real comment TEXT (not just counts) for published videos, via youtube_auth.load_comment_credentials() — see scripts/pull_video_comments.py. organic_count excludes the pipeline's own automated pinned funnel comment; organic_comments_mentioning_luxury is a real signal for whether the Shorts CTA is working, not a guess from raw comment counts.",
        "pulled_at": now,
        "has_comment_scope": True,
        "channel_id": channel_id,
        "videos": videos,
    }
    with open(os.path.join(STATE, "video_comments.json"), "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"wrote state/video_comments.json ({len(videos)} videos, has_comment_scope=True)")


if __name__ == "__main__":
    main()
