#!/usr/bin/env python3
"""
Post a top-level comment on a video (non-blocking, best-effort only) — used
for the Shorts -> long-form funnel (owner direction 2026-07-30): every
published Short gets a comment pointing viewers to the long-form catalog.

IMPORTANT: This script posts a comment, it does NOT pin it. YouTube's Data
API has no direct pin endpoint as of 2026-08 (see post_and_pin() comments).
Actual pinning requires manual Studio action by the channel owner, or relies
on YouTube's auto-pin affordance for the channel owner's own comments. Report
accurately as 'posted_unpinned', not 'pinned' (P0 production requirement).

This is graceful-degradation by design: the OAuth token may not yet carry the
youtube.force-ssl scope this needs (see youtube_auth.py's COMMENT_SCOPES
comment), so this script exits 0 with a clear "skipped" message rather than
failing the calling publish step. A Short publishing successfully must never
be blocked by the comment step — the video itself is the win condition, the
comment is a non-blocking bonus.

Fixed 2026-08-02 (real bug, owner-reported): the funnel comment must
contain an actual clickable link to a real, recently-published, public
long-form video — "1-hour ambience." with no URL sends viewers nowhere.
build_funnel_text() briefly looked this up from state/posted_history.json
itself (most recently published long-form entry).

Changed 2026-08-02 (owner direction): the owner reviewed the auto-linked
version and asked for a fixed, no-link line instead — "Manifest with
ambience, full videos on my channel." — pointing viewers to the channel in
general rather than one specific video. build_funnel_text() now returns
this fixed string; latest_long_form_url() is kept only because
build_funnel_text() still accepts a posted_history_path override for
testability, not because it's used to build the text anymore.

Return values (post_and_pin function):
  - 'deferred_until_public': video is not public yet, retry later
  - comment_id (string): comment was posted successfully; YouTube will
      auto-pin if appropriate for channel owner, else requires manual Studio pin
  - None: comment scope not available, skipped gracefully (not a failure)

Usage:
    python3 post_pinned_comment.py --video-id <id> [--text "custom text"]
    (omit --text to use the default funnel text)
"""
import argparse
import json
import os
import sys

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from youtube_auth import load_comment_credentials, load_credentials

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")


def latest_long_form_url(posted_history_path=None):
    """The most recently published long-form video's real URL, or None if
    none exist yet. Sorted by published_at, not insertion order — a queue
    could theoretically be appended out of chronological order. Not used by
    build_funnel_text() as of 2026-08-02 (owner switched to a fixed, no-link
    line) — kept as a standalone utility in case a future funnel design
    needs a real link again."""
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


FUNNEL_TEXT = "Manifest with ambience, full videos on my channel."


def build_funnel_text(posted_history_path=None):
    """The default funnel comment text (owner direction, 2026-08-02): a
    fixed line pointing viewers to the channel in general, not a specific
    video link. posted_history_path is accepted but unused — kept so
    existing callers (and tests) don't need to change their call shape."""
    return FUNNEL_TEXT


def video_is_public(video_id):
    """Check the video's actual current privacyStatus via the base (already
    -verified) publish credentials, not the comment-scope ones. Real bug
    found 2026-08-05 (analytics cycle diagnosis): every pinned-comment
    attempt on a scheduled upload (privacyStatus=private, publishAt in the
    future) was hitting a guaranteed commentThreads.insert 403 — YouTube
    does not allow commenting on a not-yet-public video regardless of the
    channel owner's own permissions. 12 consecutive attempts since
    2026-08-04 failed/were skipped this way, vs. 6/6 successes before that
    (when every publish in that window happened to be immediate/already-
    public). Checking first turns a guaranteed, noisy 403 into an honest
    'deferred' status instead."""
    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.videos().list(part="status", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        return None  # video not found/not yet indexed -- treat as unknown, not a hard false
    return items[0]["status"].get("privacyStatus") == "public"


def post_and_pin(video_id, text):
    is_public = video_is_public(video_id)
    if is_public is False:
        print(f"DEFERRED: video {video_id} is not public yet (still private/scheduled) -- "
              "commentThreads.insert always fails 403 on a non-public video, so not attempting "
              "it now. Retry this same call once the video's scheduled publishAt has passed.")
        return "deferred_until_public"

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

    # Posting a top-level comment via Data API — YouTube exposes moderation
    # via comments().setModerationStatus with moderationStatus="published"
    # plus the channel owner's own comment gets a "pin" affordance in Studio,
    # but the Data API itself has no direct "pin" endpoint as of this API
    # version. Best-effort: mark it heldForReview=False / published so it's
    # visible; actual pinning may require the channel owner to pin manually
    # in Studio if the API path isn't available. Report this accurately as
    # 'posted_unpinned' per P0 production requirement, never as 'pinned'.
    try:
        youtube.comments().setModerationStatus(id=comment_id, moderationStatus="published").execute()
        comment_status = "posted_unpinned"
        note = "top-level comment posted; YouTube Data API has no direct 'pin' endpoint — manual pin in Studio or auto-pin as channel owner's comment may apply"
    except HttpError as e:
        comment_status = "posted_unpinned"
        note = f"posted, but moderation-status call failed (non-fatal): {e}"

    print(f"COMMENT_POSTED comment_id={comment_id} video_id={video_id} status={comment_status} note={note}")
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
