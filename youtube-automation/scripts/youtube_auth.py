#!/usr/bin/env python3
"""Load YouTube API credentials from youtube-automation/secrets/, refreshing the
access token from the stored refresh token as needed. Never prompts a browser
flow here — that one-time step is documented in setup/YOUTUBE_API_SETUP.md and
must already have produced secrets/youtube_token.json before this script is used.
"""
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = REPO_ROOT / "secrets"
TOKEN_PATH = SECRETS_DIR / "youtube_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def load_credentials() -> Credentials:
    if not TOKEN_PATH.exists():
        raise FileNotFoundError(
            f"{TOKEN_PATH} not found. Follow setup/YOUTUBE_API_SETUP.md to "
            "generate it before publishing can run."
        )
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return creds


if __name__ == "__main__":
    try:
        c = load_credentials()
        print("YouTube credentials OK, valid:", c.valid)
    except Exception as e:
        print(f"YouTube credentials NOT configured: {e}", file=sys.stderr)
        sys.exit(1)
