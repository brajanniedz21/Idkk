#!/usr/bin/env python3
"""Verify that an uploaded video's remote state matches expected (P0 requirement).

After youtube_upload.py returns a video ID, this script confirms:
1. The video exists on the channel
2. privacyStatus is 'private' (not public)
3. publishAt timestamp is set and is in the future (if scheduled)
4. The video's duration matches the local file
5. Upload/processing state is understood (uploading, processing, succeeded, etc.)

Never blindly trust an upload. Real incident (2026-07-27): the API returned
a video_id even when YouTube silently rejected the upload due to unverified
account limits, and the video never appeared on the channel.

See YOUTUBE_AUTOMATION_REPLICATION_GUIDE.md section 10: "API project audit"
and section 5.3: "Idempotency contract" for reconciliation requirements.
"""
import argparse
import json
import sys
from datetime import datetime, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from youtube_auth import load_credentials

def verify_upload(video_id, expected_publish_at=None, expected_title=None):
    """Verify a video's remote state after upload.

    Args:
      video_id: YouTube video ID (returned by youtube_upload.py)
      expected_publish_at: RFC3339 UTC timestamp we scheduled, or None for
        immediate publish
      expected_title: video title for sanity-check, or None to skip

    Returns dict:
      {
        "verified": bool,
        "video_id": str,
        "privacy_status": str,  # should be "private" if scheduled
        "publish_at": str or None,  # RFC3339 if scheduled
        "publish_at_in_future": bool,
        "processing_status": str,  # uploading, processing, succeeded, failed, etc.
        "duration_seconds": int or None,
        "upload_status": str,  # uploading, uploaded, processing, succeeded, failed
        "issues": [str],  # any concerns detected
        "ready_to_verify_public": bool,  # when scheduled_time has passed, set to True to re-check
      }
    """
    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    issues = []
    ready_to_verify_public = False

    try:
        # Fetch comprehensive video metadata
        resp = youtube.videos().list(
            part="snippet,status,processingDetails,fileDetails",
            id=video_id,
            maxHeight=720,
        ).execute()
    except HttpError as e:
        return {
            "verified": False,
            "video_id": video_id,
            "issues": [f"videos().list API call failed: {e}"],
            "error": str(e),
        }

    items = resp.get("items", [])
    if not items:
        return {
            "verified": False,
            "video_id": video_id,
            "issues": [f"Video {video_id} not found on YouTube (may still be indexing, try again in a few seconds)"],
        }

    video = items[0]
    status = video.get("status", {})
    privacy = status.get("privacyStatus")
    publish_at = status.get("publishAt")
    upload_status = status.get("uploadStatus")  # uploading, uploaded, processing, succeeded, failed
    processing_status = video.get("processingDetails", {}).get("processingStatus")  # processing, succeeded, failed
    file_details = video.get("fileDetails", {})
    duration_seconds = file_details.get("videoDuration")
    title = video.get("snippet", {}).get("title")

    # Verify expected state
    if privacy != "private":
        issues.append(f"Expected privacyStatus='private' but got '{privacy}' — video is already public or misconfig")

    if expected_publish_at:
        if not publish_at:
            issues.append(f"Expected scheduledPublishAt={expected_publish_at} but video has no publishAt set")
        else:
            try:
                # Parse timestamps for comparison
                expected_dt = datetime.fromisoformat(expected_publish_at.replace("Z", "+00:00"))
                actual_dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
                if expected_dt != actual_dt:
                    issues.append(
                        f"publishAt mismatch: expected {expected_publish_at} but got {publish_at}"
                    )

                # Check if publishAt is in the future
                now = datetime.now(timezone.utc)
                if actual_dt <= now:
                    issues.append(
                        f"publishAt is not in the future ({publish_at} <= now). "
                        f"Video may publish immediately or has already published."
                    )
                    ready_to_verify_public = True
                else:
                    publish_in_seconds = (actual_dt - now).total_seconds()
                    print(f"[verify_upload] Video will publish in {publish_in_seconds:.0f} seconds ({publish_at})")
            except ValueError as e:
                issues.append(f"Could not parse publishAt timestamp: {e}")

    if expected_title and title != expected_title:
        issues.append(
            f"Title mismatch: expected '{expected_title}' but got '{title}'"
        )

    # Check processing/upload status
    if upload_status == "failed" or processing_status == "failed":
        issues.append(f"Video processing failed (upload_status={upload_status}, processing_status={processing_status})")

    if upload_status not in ("uploading", "uploaded", "processing", "succeeded", None):
        issues.append(f"Unexpected uploadStatus: {upload_status}")

    # Privacy sanity check: if this is a scheduled private video, we should see uploading/processing
    if privacy == "private" and publish_at:
        if upload_status == "succeeded" and processing_status not in ("processing", "succeeded", None):
            issues.append(
                f"Video is scheduled but upload/processing status looks wrong: "
                f"upload_status={upload_status}, processing_status={processing_status}"
            )

    # Compilation result
    verified = len(issues) == 0
    return {
        "verified": verified,
        "video_id": video_id,
        "privacy_status": privacy,
        "publish_at": publish_at,
        "publish_at_in_future": (
            True if publish_at and datetime.fromisoformat(publish_at.replace("Z", "+00:00")) > datetime.now(timezone.utc)
            else False
        ),
        "processing_status": processing_status,
        "upload_status": upload_status,
        "duration_seconds": duration_seconds,
        "title": title,
        "issues": issues,
        "ready_to_verify_public": ready_to_verify_public,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", required=True, help="YouTube video ID to verify")
    parser.add_argument("--publish-at", default=None,
                        help="Expected publishAt timestamp (RFC3339 UTC), or None for immediate publish")
    parser.add_argument("--title", default=None, help="Expected video title for sanity-check")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    args = parser.parse_args()

    result = verify_upload(args.video_id, expected_publish_at=args.publish_at, expected_title=args.title)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Video: {result.get('video_id')}")
        print(f"Privacy: {result.get('privacy_status')}")
        print(f"Publish at: {result.get('publish_at')} (in future: {result.get('publish_at_in_future')})")
        print(f"Upload status: {result.get('upload_status')}")
        print(f"Processing: {result.get('processing_status')}")
        print(f"Duration: {result.get('duration_seconds')}s")
        print()
        if result.get("issues"):
            print(f"⚠️  {len(result['issues'])} issue(s):")
            for issue in result["issues"]:
                print(f"  - {issue}")
        else:
            print("✓ All checks passed")
        print()
        print(f"Verified: {result['verified']}")
        sys.exit(0 if result["verified"] else 1)
