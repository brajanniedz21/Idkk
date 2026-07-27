#!/usr/bin/env python3
"""Upload a finished video to YouTube via the Data API v3.

Usage:
  python3 youtube_upload.py --file path/to/video.mp4 --title "..." \
    --description "..." --tags "tag1,tag2,tag3" --category 22 \
    --privacy public

Used by Agent 4.1 (short-form) and Agent 6 (long-form). Both agents are
instructed to halt and report rather than call this script if
scripts/youtube_auth.py cannot load valid credentials.
"""
import argparse
import sys

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from youtube_auth import load_credentials


def upload(file_path, title, description, tags, category_id, privacy):
    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True, mimetype="video/mp4")

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")

    return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--tags", default="", help="comma-separated")
    parser.add_argument("--category", default="22", help="YouTube category ID")
    parser.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    args = parser.parse_args()

    try:
        result = upload(
            file_path=args.file,
            title=args.title,
            description=args.description,
            tags=[t.strip() for t in args.tags.split(",") if t.strip()],
            category_id=args.category,
            privacy=args.privacy,
        )
        video_id = result["id"]
        print(f"PUBLISHED video_id={video_id} url=https://youtu.be/{video_id}")
    except Exception as e:
        print(f"UPLOAD FAILED: {e}", file=sys.stderr)
        sys.exit(1)
