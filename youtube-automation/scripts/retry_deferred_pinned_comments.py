#!/usr/bin/env python3
"""
Retry the Shorts->long-form pinned-comment funnel for previously
deferred/failed attempts, now that some of those videos may have gone
public since their scheduled publishAt passed.

Real bug found 2026-08-05 (daily analytics cycle diagnosis): every pinned
-comment attempt made at publish time on a *scheduled* (privacyStatus=
private, publishAt in the future) upload was a guaranteed commentThreads
.insert 403 -- YouTube refuses comments on a non-public video regardless
of channel-owner permissions. 12 consecutive attempts since 2026-08-04
failed/were skipped this way, vs. 6/6 successes before that (when every
publish in that window happened to already be public). post_pinned_comment
.py was fixed the same day to check privacyStatus first and return
'deferred_until_public' instead of attempting a call that can only fail --
this script is the other half: sweep every short with a deferred/failed-
because-not-public status and retry now that time has passed.

Usage:
    python3 scripts/retry_deferred_pinned_comments.py [--dry-run]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_pinned_comment import build_funnel_text, post_and_pin, video_is_public  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
QUEUE_PATH = os.path.join(STATE, "short_form_queue.json")

DEFERRED_MARKERS = ("deferred_until_public", "not yet public", "not attempted this pass")


def needs_retry(status):
    if not status:
        return False
    s = status.lower()
    return any(marker in s for marker in DEFERRED_MARKERS) or (
        "403" in s and ("forbidden" in s or "insufficient permissions" in s)
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report what would be retried without posting anything.")
    args = parser.parse_args()

    with open(QUEUE_PATH) as f:
        q = json.load(f)

    candidates = [
        it for it in q["queue"]
        if it.get("status") == "published"
        and it.get("published_video_id")
        and needs_retry(it.get("pinned_comment_status"))
    ]

    print(f"Found {len(candidates)} short(s) with a deferred/likely-not-public pinned-comment status.")

    retried = 0
    now_public = 0
    still_private = 0
    posted_ok = 0

    for it in candidates:
        vid = it["published_video_id"]
        is_public = video_is_public(vid)
        if is_public is not True:
            still_private += 1
            print(f"  {it['id']} ({vid}): still not public -- leaving as-is")
            continue

        now_public += 1
        retried += 1
        if args.dry_run:
            print(f"  {it['id']} ({vid}): now public -- WOULD retry pinned comment (dry-run)")
            continue

        result = post_and_pin(vid, build_funnel_text())
        if result and result != "deferred_until_public":
            it["pinned_comment_status"] = f"posted (retried after going public; comment_id={result})"
            posted_ok += 1
            print(f"  {it['id']} ({vid}): posted successfully on retry")
        elif result == "deferred_until_public":
            # Should not happen since we just confirmed public, but stay honest if it does.
            it["pinned_comment_status"] = "deferred_until_public (unexpected -- video_is_public() said True but post_and_pin() deferred again)"
        else:
            it["pinned_comment_status"] = "failed on retry: post_and_pin() returned no comment_id (see stderr)"

    if not args.dry_run and retried:
        with open(QUEUE_PATH, "w") as f:
            json.dump(q, f, indent=2)
        # Re-read and confirm it still parses, per the publisher spec's own discipline.
        with open(QUEUE_PATH) as f:
            json.load(f)

    print(
        f"\nSummary: {len(candidates)} candidates checked, {now_public} now public "
        f"({posted_ok} posted successfully), {still_private} still private/scheduled."
    )


if __name__ == "__main__":
    main()
