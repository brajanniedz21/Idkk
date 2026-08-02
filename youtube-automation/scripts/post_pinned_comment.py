#!/usr/bin/env python3
"""
Post (and attempt to pin) a comment on a video — used for the Shorts ->
long-form funnel (owner direction 2026-07-30): every published Short gets a
pinned comment pointing viewers to the long-form catalog.

This is graceful-degradation by design: as of 2026-07-30 the OAuth token
does not yet carry the youtube.force-ssl scope this needs (see
youtube_auth.py's COMMENT_SCOPES comment), so this script exits 0 with a
clear "skipped" message rather than failing the calling publish step. A
Short publishing successfully must never be blocked by the comment step —
the video itself is the win condition, the pinned comment is a bonus.

Fixed 2026-08-02 (real bug, owner-reported): the funnel comment must
contain an actual clickable link to a real, recently-published, public
long-form video — "1-hour ambience." with no URL sends viewers nowhere.
build_funnel_text() looks this up from state/posted_history.json itself
(most recently published long-form entry) rather than relying on whoever
calls this script to remember to type a real link in by hand, the same
reason the CTA/thumbnail logic lives in scripts/ rather than being an
instruction an agent has to get right every time.

Usage:
    python3 post_pinned_comment.py --video-id <id> [--text "custom text"]
    (omit --text to auto-build "1-hour ambience: <real long-form URL>")
"""
import argparse
import json
import os
import sys

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from youtube_auth import load_comment_credentials

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")


def latest_long_form_url(posted_history_path=None):
    """The most recently published long-form video's real URL, or None if
    none exist yet. Sorted by published_at, not insertion order — a queue
    could theoretically be appended out of chronological order."""
    path = posted_history_path or os.path.join(STATE, "posted_history.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        posted = json.load(f)
    longs = posted.get("long_form", [])
    if not longs:
        return None
    longs_sorted = sorted(longs, key=lambda v: v.get("published_at") or "", reverse=True)
    return longs_sorted[0].get("url")


def build_funnel_text(posted_history_path=None):
    """The default funnel comment text: a real link when one exists, or an
    honest fallback (never a dead-end "1-hour ambience." with no URL) when
    no long-form video has been published yet at all."""
    url = latest_long_form_url(posted_history_path)
    if url:
        return f"1-hour ambience: {url}"
    return "1-hour ambience — full-length version coming soon to the channel."


def post_and_pin(video_id, text):
    creds = load_comment_credentials()
    if creds is None:
        print("SKIPPED: comment-posting credentials unavailable (youtube.force-ssl scope not "
              "granted yet — see setup/YOUTUBE_API_SETUP.md). Not a failure, just not possible yet.")
        return None

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "videoId": video_id,
            "topLevelComment": {"snippet": {"textOriginal": text}},
        }
    }
    thread = youtube.commentThreads().insert(part="snippet", body=body).execute()
    comment_id = thread["snippet"]["topLevelComment"]["id"]

    # Pinning a comment isn't a first-class Data API field — YouTube exposes
    # it via comments().setModerationStatus with moderationStatus="published"
    # plus the channel owner's own comment gets a "pin" affordance in Studio,
    # but the Data API itself has no direct "pin" endpoint as of this API
    # version. Best-effort: mark it heldForReview=False / published so it's
    # visible; actual pinning may require the channel owner to pin manually
    # in Studio if the API path isn't available. Report this plainly rather
    # than claiming a pin that didn't happen.
    try:
        youtube.comments().setModerationStatus(id=comment_id, moderationStatus="published").execute()
        pinned_note = "posted (top-level comment; YouTube Data API has no direct 'pin' endpoint — pin manually in Studio if it doesn't auto-pin as the channel owner's own comment)"
    except HttpError as e:
        pinned_note = f"posted, but moderation-status call failed (non-fatal): {e}"

    print(f"COMMENT_POSTED comment_id={comment_id} video_id={video_id} note={pinned_note}")
    return comment_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--text", default=None,
                         help="Override text; omit to auto-build the funnel text with a real long-form link.")
    args = parser.parse_args()
    text = args.text or build_funnel_text()

    try:
        post_and_pin(args.video_id, text)
    except Exception as e:
        # Never let a comment-posting failure look like a publish failure —
        # this script's own exit code is separate from youtube_upload.py's.
        print(f"COMMENT FAILED (non-fatal to the publish itself): {e}", file=sys.stderr)
        sys.exit(0)
