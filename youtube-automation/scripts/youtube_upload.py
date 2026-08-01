#!/usr/bin/env python3
"""Upload a finished video to YouTube via the Data API v3.

Usage:
  python3 youtube_upload.py --file path/to/video.mp4 --title "..." \
    --description "..." --tags "tag1,tag2,tag3" --category 22 \
    --privacy public [--short] [--cta-variant cta_luxury_control]

Used by Agent 4.1 (short-form) and Agent 6 (long-form). Both agents are
instructed to halt and report rather than call this script if
scripts/youtube_auth.py cannot load valid credentials.

Agent 4.1 always passes --short, which appends a Shorts CTA as the final
line of the description. Agent 6 (long-form) never passes it. As of
2026-08-01 the exact CTA wording is a controlled experiment (see
scripts/cta_experiment.py) rather than one fixed string — pass
--cta-variant with the variant ID already assigned and stored on the
candidate at scripting time (agents/short_form/2.1_scriptwriter.md); if
omitted, the original control wording is used, so old callers/behavior are
unaffected.
"""
import argparse
import sys

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from youtube_auth import load_credentials
from cta_experiment import apply_cta, DEFAULT_VARIANT_ID, CTA_VARIANTS

# Kept for backward compatibility with any existing caller/import that still
# references the pre-experiment constant/helper directly — both now just
# delegate to scripts/cta_experiment.py, which is the real source of truth.
SHORTS_CTA = CTA_VARIANTS[DEFAULT_VARIANT_ID]


def append_shorts_cta(description, variant_id=DEFAULT_VARIANT_ID):
    """Append a Shorts CTA variant as the final line of a description.
    Idempotent and variant-aware — see scripts/cta_experiment.py's
    apply_cta()/strip_known_cta() for the actual logic."""
    return apply_cta(description, variant_id)


def upload(file_path, title, description, tags, category_id, privacy, publish_at=None,
           thumbnail_path=None, is_short=False, cta_variant_id=DEFAULT_VARIANT_ID):
    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    if is_short:
        description = append_shorts_cta(description, cta_variant_id)

    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        # Scheduled publish: YouTube requires privacyStatus=private with a
        # future publishAt (RFC3339 UTC); it flips to public automatically
        # at that timestamp. Using this lets a batch cycle upload everything
        # up front while spreading the actual go-live times across the week.
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": status,
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True, mimetype="video/mp4")

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        upload_status, response = request.next_chunk()
        if upload_status:
            print(f"Upload progress: {int(upload_status.progress() * 100)}%")

    # A real failure mode already hit once: the API can return a 200 with a
    # video ID even when YouTube silently rejects the video for a policy
    # reason (e.g. an unverified account's >15min length cap) — the video
    # never actually appears on the channel despite the "successful" response.
    # Always re-check with videos.list before trusting the upload happened.
    video_id = response["id"]
    check = youtube.videos().list(part="status", id=video_id).execute()
    if not check.get("items"):
        raise RuntimeError(
            f"Upload returned video_id={video_id} but videos.list finds no such video — "
            f"the upload was likely silently rejected (e.g. account verification/length limits, "
            f"policy strike). Do not treat this as a successful publish."
        )

    if thumbnail_path:
        # thumbnails().set requires the youtube.upload or youtube scope —
        # both already in SCOPES, no separate credential/re-auth needed.
        # A thumbnail failure should never fail the whole publish: the video
        # itself already succeeded, so log and continue rather than raising.
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_path)).execute()
        except Exception as e:
            print(f"WARNING: video published but thumbnail upload failed: {e}", file=sys.stderr)

    return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--tags", default="", help="comma-separated")
    parser.add_argument("--category", default="22", help="YouTube category ID")
    parser.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    parser.add_argument("--publish-at", default=None,
                         help="RFC3339 UTC timestamp (e.g. 2026-08-03T15:00:00Z) for scheduled publish. "
                              "Forces privacyStatus=private on upload; YouTube auto-publishes at this time. "
                              "Must be in the future or the API will reject it.")
    parser.add_argument("--thumbnail", default=None,
                         help="Path to a custom thumbnail image (run through scripts/thumbnail_optimize.py "
                              "first). Uploaded via thumbnails().set after the video itself succeeds; a "
                              "thumbnail failure is logged as a warning but does not fail the publish.")
    parser.add_argument("--short", action="store_true",
                         help="Mark this upload as a Shorts video. Appends a Shorts CTA (see --cta-variant) "
                              "as the final line of the description. Never pass this for long-form uploads.")
    parser.add_argument("--cta-variant", default=DEFAULT_VARIANT_ID, choices=list(CTA_VARIANTS),
                         help="Which CTA experiment variant to use (only meaningful with --short). Pass the "
                              "variant ID already assigned and stored on the candidate at scripting time "
                              "(see scripts/cta_experiment.py). Defaults to the control wording, unchanged "
                              "from the original pre-experiment behavior.")
    args = parser.parse_args()

    try:
        result = upload(
            file_path=args.file,
            title=args.title,
            description=args.description,
            tags=[t.strip() for t in args.tags.split(",") if t.strip()],
            category_id=args.category,
            privacy=args.privacy,
            publish_at=args.publish_at,
            thumbnail_path=args.thumbnail,
            is_short=args.short,
            cta_variant_id=args.cta_variant,
        )
        video_id = result["id"]
        scheduled_note = f" (scheduled for {args.publish_at})" if args.publish_at else ""
        print(f"PUBLISHED video_id={video_id} url=https://youtu.be/{video_id}{scheduled_note}")
    except Exception as e:
        print(f"UPLOAD FAILED: {e}", file=sys.stderr)
        sys.exit(1)
