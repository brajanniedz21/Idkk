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

# The three scopes that are confirmed working end-to-end (including token
# refresh) as of 2026-07-28 — publishing depends on these, so this list
# must never include a scope that isn't verified to refresh cleanly.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# yt-analytics.readonly was added to secrets/youtube_token.json's stored
# scope list on 2026-07-28, and single API calls succeeded while the
# access token from that re-auth was still live — but refreshing a token
# with this scope (alone or combined with the others) fails with
# `invalid_scope`. That means the *refresh_token* isn't actually carrying
# this scope, even though the original access_token briefly worked with
# it — a real, reproducible inconsistency, most likely because
# yt-analytics.readonly is a Google "sensitive" scope and the OAuth
# consent screen / app configuration wasn't fully accepted for it (e.g.
# needs additional app info saved, not just the scope added to the list).
# Kept as a SEPARATE, isolated scope set — never merged into SCOPES above
# — precisely so a broken analytics grant can never break the publish
# pipeline again the way it did before this was split out.
ANALYTICS_SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]


def load_credentials() -> Credentials:
    if not TOKEN_PATH.exists():
        raise FileNotFoundError(
            f"{TOKEN_PATH} not found. Follow setup/YOUTUBE_API_SETUP.md to "
            "generate it before publishing can run."
        )
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def load_analytics_credentials():
    """Returns a Credentials object scoped to yt-analytics.readonly, or
    None if it can't actually be used (see ANALYTICS_SCOPES comment above
    for why this needs isolating from load_credentials()). Callers must
    handle None as "analytics not available right now" rather than crash."""
    if not TOKEN_PATH.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), ANALYTICS_SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    except Exception as e:
        print(f"yt-analytics.readonly credentials unusable (non-fatal): {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    try:
        c = load_credentials()
        print("YouTube credentials OK, valid:", c.valid)
    except Exception as e:
        print(f"YouTube credentials NOT configured: {e}", file=sys.stderr)
        sys.exit(1)
    ac = load_analytics_credentials()
    print("Analytics credentials:", "OK" if ac and ac.valid else "NOT available")
